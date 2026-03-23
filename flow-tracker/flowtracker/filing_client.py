"""BSE corporate filings client — fetches announcements and downloads PDFs."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from flowtracker.filing_models import CorporateFiling

logger = logging.getLogger(__name__)

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_BSE_ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"
_BSE_ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis"
_NSE_API = "https://www.nseindia.com/api"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}

# Filing categories we care about for research
_RESEARCH_CATEGORIES = {
    "Investor Presentation",
    "Earnings Call Transcript",
    "Analyst / Investor Meet",
    "Press Release / Media Release",
    "Financial Results",
    "Board Meeting",
    "Acquisition",
    "General",
}

# Default PDF storage location
_DEFAULT_FILING_DIR = Path.home() / ".local" / "share" / "flowtracker" / "filings"


class FilingClient:
    """Client for BSE/NSE corporate filings."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
        )
        self._scrip_cache: dict[str, str] = {}

    # -- BSE Scrip Code Lookup --

    def get_bse_code(self, symbol: str) -> str | None:
        """Look up BSE scrip code for an NSE symbol."""
        if symbol in self._scrip_cache:
            return self._scrip_cache[symbol]

        try:
            resp = self._client.get(
                f"{_BSE_API}/PeerSmartSearch/w",
                params={"Type": "SS", "text": symbol},
            )
            resp.raise_for_status()
            html = resp.text

            # Parse: liclick('542726','IndiaMART InterMESH Ltd')
            match = re.search(r"liclick\('(\d+)','([^']+)'\)", html)
            if match:
                code = match.group(1)
                self._scrip_cache[symbol] = code
                return code

            return None
        except Exception as e:
            logger.warning("BSE code lookup failed for %s: %s", symbol, e)
            return None

    # -- Fetch Filings --

    def fetch_filings(
        self, symbol: str, from_date: date | None = None, to_date: date | None = None,
        category: str = "-1",
    ) -> list[CorporateFiling]:
        """Fetch corporate filings from BSE for a symbol.

        Args:
            symbol: NSE symbol (e.g., "INDIAMART")
            from_date: Start date (default: 3 years ago)
            to_date: End date (default: today)
            category: BSE category filter, "-1" for all
        """
        bse_code = self.get_bse_code(symbol)
        if not bse_code:
            logger.warning("No BSE code found for %s", symbol)
            return []

        if to_date is None:
            to_date = date.today()
        if from_date is None:
            from_date = to_date - timedelta(days=365 * 3)

        all_filings: list[CorporateFiling] = []
        page = 1

        while True:
            try:
                resp = self._client.get(
                    f"{_BSE_API}/AnnSubCategoryGetData/w",
                    params={
                        "pageno": str(page),
                        "strCat": category,
                        "subcategory": "-1",
                        "strPrevDate": from_date.strftime("%Y%m%d"),
                        "strToDate": to_date.strftime("%Y%m%d"),
                        "strSearch": "P",
                        "strscrip": bse_code,
                        "strType": "C",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                table = data.get("Table", [])
                if not table:
                    break

                for item in table:
                    filing = self._parse_filing(item, symbol, bse_code)
                    if filing:
                        all_filings.append(filing)

                # Check if more pages
                total = data.get("Table1", [{}])[0].get("ROWCNT", 0)
                if page * 50 >= total:
                    break

                page += 1
                time.sleep(0.5)

            except Exception as e:
                logger.warning("Failed to fetch page %d for %s: %s", page, symbol, e)
                break

        return all_filings

    def fetch_research_filings(
        self, symbol: str, from_date: date | None = None,
    ) -> list[CorporateFiling]:
        """Fetch only research-relevant filings (investor decks, concalls, results)."""
        all_filings = self.fetch_filings(symbol, from_date=from_date)
        return [
            f for f in all_filings
            if f.subcategory in _RESEARCH_CATEGORIES
            or f.category in ("Result", "Board Meeting")
            or any(kw in f.headline.lower() for kw in [
                "investor", "concall", "earnings", "transcript",
                "presentation", "analyst", "financial result",
            ])
        ]

    def fetch_annual_reports(self, symbol: str) -> list[dict]:
        """Fetch annual report download links from NSE."""
        try:
            # NSE needs cookie preflight
            nse_client = httpx.Client(
                headers={
                    "User-Agent": _HEADERS["User-Agent"],
                    "Accept": "application/json",
                    "Referer": "https://www.nseindia.com/",
                },
                follow_redirects=True,
                timeout=30.0,
            )
            nse_client.get("https://www.nseindia.com/")
            time.sleep(1)

            resp = nse_client.get(
                f"{_NSE_API}/annual-reports",
                params={"index": "equities", "symbol": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            nse_client.close()

            reports = []
            for item in data.get("data", []):
                reports.append({
                    "symbol": symbol,
                    "from_year": item.get("fromYr"),
                    "to_year": item.get("toYr"),
                    "url": item.get("fileName"),
                    "company_name": item.get("companyName"),
                })
            return reports

        except Exception as e:
            logger.warning("Failed to fetch annual reports for %s: %s", symbol, e)
            return []

    # -- Download PDFs --

    def download_filing(
        self, filing: CorporateFiling, base_dir: Path | None = None,
    ) -> Path | None:
        """Download a filing PDF to local storage.

        Stores in: {base_dir}/{symbol}/{category}/{date}_{headline_slug}.pdf
        """
        if base_dir is None:
            base_dir = _DEFAULT_FILING_DIR

        # Build download URL
        if filing.pdf_flag == 0:
            url = f"{_BSE_ATTACH_LIVE}/{filing.attachment_name}"
        else:
            url = f"{_BSE_ATTACH_HIS}/{filing.attachment_name}"

        # Build local path
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', filing.headline[:60]).strip('_').lower()
        dir_path = base_dir / filing.symbol / _safe_dirname(filing.subcategory or filing.category)
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{filing.filing_date}_{slug}.pdf"

        # Skip if already downloaded
        if file_path.exists() and file_path.stat().st_size > 0:
            return file_path

        try:
            resp = self._client.get(url)
            if resp.status_code == 200 and len(resp.content) > 100:
                file_path.write_bytes(resp.content)
                logger.info("Downloaded %s (%d KB)", file_path.name, len(resp.content) // 1024)
                return file_path
            else:
                logger.warning("Empty or failed download for %s", filing.attachment_name)
                return None
        except Exception as e:
            logger.warning("Download failed for %s: %s", filing.attachment_name, e)
            return None

    def download_url(
        self, url: str, symbol: str, category: str, filename: str,
        base_dir: Path | None = None,
    ) -> Path | None:
        """Download a file from a direct URL (for NSE annual reports)."""
        if base_dir is None:
            base_dir = _DEFAULT_FILING_DIR

        dir_path = base_dir / symbol / _safe_dirname(category)
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / filename

        if file_path.exists() and file_path.stat().st_size > 0:
            return file_path

        try:
            resp = self._client.get(url)
            if resp.status_code == 200 and len(resp.content) > 100:
                file_path.write_bytes(resp.content)
                logger.info("Downloaded %s (%d KB)", file_path.name, len(resp.content) // 1024)
                return file_path
            return None
        except Exception as e:
            logger.warning("Download failed for %s: %s", url, e)
            return None

    # -- Parsing --

    def _parse_filing(
        self, item: dict, symbol: str, bse_code: str,
    ) -> CorporateFiling | None:
        """Parse a BSE filing API response item."""
        try:
            attachment = item.get("ATTACHMENTNAME", "")
            if not attachment:
                return None

            # Parse date
            dt_str = item.get("NEWS_DT", "") or item.get("DT_TM", "")
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", ""))
                filing_date = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                filing_date = ""

            return CorporateFiling(
                symbol=symbol,
                bse_scrip_code=bse_code,
                filing_date=filing_date,
                category=item.get("CATEGORYNAME", ""),
                subcategory=item.get("SUBCATNAME", ""),
                headline=(item.get("HEADLINE") or item.get("NEWSSUB") or "")[:500],
                attachment_name=attachment,
                pdf_flag=item.get("PDFFLAG", 0),
                file_size=item.get("Fld_Attachsize"),
                news_id=item.get("NEWSID"),
            )
        except Exception as e:
            logger.debug("Failed to parse filing: %s", e)
            return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FilingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _safe_dirname(name: str) -> str:
    """Convert a category name to a safe directory name."""
    return re.sub(r'[^a-zA-Z0-9_-]+', '_', name).strip('_').lower()
