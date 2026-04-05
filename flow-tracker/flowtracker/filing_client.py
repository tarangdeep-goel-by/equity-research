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

# Filing subcategories we care about for research (strict set — concalls, decks, results)
_RESEARCH_SUBCATEGORIES = {
    "Investor Presentation",
    "Earnings Call Transcript",
    "Analyst / Investor Meet",       # Often concall transcripts on BSE
    "Financial Results",
}

# Keywords in headlines that indicate research-relevant filings
_RESEARCH_KEYWORDS = [
    "transcript", "concall", "earnings call",
    "investor presentation", "investor deck",
    "financial result", "quarterly result",
    "analyst meet",
]

# Default PDF storage location — in vault alongside research
_DEFAULT_FILING_DIR = Path.home() / "vault" / "stocks"


def _parse_bse_date(date_str: str) -> str | None:
    """Parse BSE date formats to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    # Handle .NET JSON date: /Date(1234567890000)/
    m = re.search(r"/Date\((\d+)\)/", date_str)
    if m:
        ts = int(m.group(1)) / 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    # Handle common date formats (including "14 Aug 2025")
    for fmt in ("%d %b %Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_bonus_multiplier(ratio_text: str) -> float | None:
    """Parse bonus ratio text to share multiplier. '1:1' -> 2.0, '2:1' -> 1.5"""
    if not ratio_text:
        return None
    m = re.search(r"(\d+)\s*:\s*(\d+)", ratio_text)
    if m:
        new_shares = int(m.group(1))
        existing_shares = int(m.group(2))
        if existing_shares > 0:
            return (new_shares + existing_shares) / existing_shares
    return None


def _parse_split_multiplier(details: str) -> float | None:
    """Parse split details to multiplier. 'Rs.10/- to Rs.2/-' -> 5.0"""
    if not details:
        return None
    m = re.search(r"(?:from|From)\s*(?:Rs\.?|₹)\s*(\d+).*?(?:to|To)\s*(?:Rs\.?|₹)\s*(\d+)", details)
    if m:
        old_face = int(m.group(1))
        new_face = int(m.group(2))
        if new_face > 0:
            return old_face / new_face
    return None


def _parse_dividend_amount(details: str) -> float | None:
    """Parse dividend amount from details text."""
    if not details:
        return None
    # Try "Rs. 10/- Per Share" or "Rs 5 Per Share" first
    m = re.search(r"(?:Rs\.?|₹)\s*([\d.]+)", details)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    # Fallback: plain number like "5.50"
    details = details.strip()
    try:
        return float(details)
    except ValueError:
        pass
    return None


class FilingClient:
    """Client for BSE/NSE corporate filings."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
        )
        self._scrip_cache: dict[str, str] = {}

    def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs) -> httpx.Response:
        """HTTP request with exponential backoff + jitter."""
        import random
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("BSE request failed (attempt %d/%d): %s — retrying in %.1fs",
                                  attempt + 1, max_retries + 1, exc, wait)
                    time.sleep(wait)
        raise last_exc or httpx.HTTPError(f"Failed after {max_retries + 1} attempts: {url}")

    # -- BSE Scrip Code Lookup --

    def get_bse_code(self, symbol: str) -> str | None:
        """Look up BSE scrip code for an NSE symbol.

        Searches BSE and validates against known company name from
        index_constituents to avoid symbol collisions (e.g., NSE HAL =
        Hindustan Aeronautics, not BSE's Haldyn Glass).
        """
        if symbol in self._scrip_cache:
            return self._scrip_cache[symbol]

        try:
            resp = self._request_with_retry(
                "GET", f"{_BSE_API}/PeerSmartSearch/w",
                params={"Type": "SS", "text": symbol},
            )
            resp.raise_for_status()
            html = resp.text

            # Parse ALL candidates: liclick('542726','IndiaMART InterMESH Ltd')
            candidates = re.findall(r"liclick\('(\d+)','([^']+)'\)", html)
            if not candidates:
                return None

            # Try to validate against known company name
            known_name = self._get_known_company_name(symbol)
            if known_name and len(candidates) > 1:
                best_code = self._match_bse_candidate(candidates, known_name, symbol)
                if best_code:
                    self._scrip_cache[symbol] = best_code
                    return best_code

            # Fallback: first result (original behavior)
            code = candidates[0][0]
            self._scrip_cache[symbol] = code
            return code
        except Exception as e:
            logger.warning("BSE code lookup failed for %s: %s", symbol, e)
            return None

    def _get_known_company_name(self, symbol: str) -> str | None:
        """Get company name from index_constituents for validation."""
        try:
            from flowtracker.store import FlowStore
            with FlowStore() as store:
                row = store._conn.execute(
                    "SELECT company_name FROM index_constituents WHERE symbol = ? LIMIT 1",
                    (symbol,),
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def _match_bse_candidate(
        self, candidates: list[tuple[str, str]], known_name: str, symbol: str,
    ) -> str | None:
        """Find the BSE candidate that best matches the known company name.

        Uses word overlap scoring — the candidate sharing the most significant
        words with the known name wins.
        """
        # Normalize for comparison
        stop_words = {"ltd", "limited", "the", "of", "and", "&", "co", "inc", "corp"}

        def _significant_words(name: str) -> set[str]:
            return {w.lower() for w in re.split(r'[\s\-\.\,]+', name)
                    if len(w) > 1 and w.lower() not in stop_words}

        known_words = _significant_words(known_name)
        if not known_words:
            return None

        best_code = None
        best_score = 0

        for code, bse_name in candidates:
            bse_words = _significant_words(bse_name)
            overlap = len(known_words & bse_words)
            score = overlap / max(len(known_words), 1)

            if score > best_score:
                best_score = score
                best_code = code

        # Require at least 30% word overlap to accept
        if best_score >= 0.3:
            logger.info(
                "BSE lookup for %s: matched '%s' (score=%.2f) from %d candidates",
                symbol,
                next((name for code, name in candidates if code == best_code), "?"),
                best_score, len(candidates),
            )
            return best_code

        logger.warning(
            "BSE lookup for %s: no good match for '%s' among %d candidates (best score=%.2f)",
            symbol, known_name, len(candidates), best_score,
        )
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
                resp = self._request_with_retry(
                    "GET", f"{_BSE_API}/AnnSubCategoryGetData/w",
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
        """Fetch only research-relevant filings (concalls, investor decks, results).

        Tighter filter than fetch_filings — excludes board meetings, press releases,
        acquisitions, and general announcements to reduce noise.
        """
        all_filings = self.fetch_filings(symbol, from_date=from_date)
        return [
            f for f in all_filings
            if f.subcategory in _RESEARCH_SUBCATEGORIES
            or f.category == "Result"
            or any(kw in f.headline.lower() for kw in _RESEARCH_KEYWORDS)
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

        # Determine file type from headline/subcategory
        hl = filing.headline.lower()
        sc = (filing.subcategory or "").lower()
        if "transcript" in hl or "transcript" in sc or "concall" in hl:
            ftype = "concall"
        elif "analyst" in sc and ("transcript" in hl or "concall" in hl or "earnings" in hl):
            # "Analyst / Investor Meet" with transcript-like headline = concall
            ftype = "concall"
        elif "investor presentation" in sc or "investor presentation" in hl or "investor deck" in hl:
            ftype = "investor_deck"
        elif "analyst" in sc and ("presentation" in hl or "investor" in hl):
            # "Analyst / Investor Meet" with presentation-like headline = investor deck
            ftype = "investor_deck"
        elif "financial result" in sc or ("financial result" in hl and "newspaper" not in hl):
            ftype = "results"
        elif "annual report" in hl:
            ftype = "annual_report"
        else:
            ftype = _safe_dirname(filing.subcategory or filing.category)

        # Determine FY quarter from filing date
        fy_quarter = _filing_date_to_fy_quarter(filing.filing_date)

        # Build local path: {base}/{symbol}/filings/{FY-Q}/{type}.pdf
        dir_path = base_dir / filing.symbol / "filings" / fy_quarter
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{ftype}.pdf"

        # Skip if primary file already exists (same type for this quarter)
        if file_path.exists() and file_path.stat().st_size > 0:
            # Check if this is likely the same file (size-based dedup)
            if filing.file_size and abs(file_path.stat().st_size - filing.file_size) < 1024:
                return file_path
            # Different file for same type+quarter — append date
            file_path = dir_path / f"{ftype}_{filing.filing_date}.pdf"
            if file_path.exists() and file_path.stat().st_size > 0:
                return file_path

        import time

        for attempt in range(3):
            try:
                resp = self._client.get(url)
                if resp.status_code == 200 and len(resp.content) > 100:
                    file_path.write_bytes(resp.content)
                    logger.info("Downloaded %s (%d KB)", file_path.name, len(resp.content) // 1024)
                    return file_path
                if resp.status_code in (404,):
                    # Permanent failure — don't retry
                    logger.warning("Not found (404) for %s", filing.attachment_name)
                    return None
                if attempt < 2:
                    # 406/5xx — transient, retry with backoff
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.warning("Empty or failed download for %s (status %s after %d attempts)",
                               filing.attachment_name, resp.status_code, attempt + 1)
                return None
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.warning("Download failed for %s: %s", filing.attachment_name, e)
                return None
        return None

    def download_url(
        self, url: str, symbol: str, category: str, filename: str,
        base_dir: Path | None = None,
    ) -> Path | None:
        """Download a file from a direct URL (for NSE annual reports)."""
        if base_dir is None:
            base_dir = _DEFAULT_FILING_DIR

        dir_path = base_dir / symbol / "filings" / "annual"
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

    # -- Corporate Actions --

    def fetch_corporate_actions(self, symbol: str) -> list[dict]:
        """Fetch corporate actions from BSE API.

        Returns list of dicts with keys: symbol, ex_date, action_type,
        ratio_text, multiplier, dividend_amount, source.
        """
        bse_code = self.get_bse_code(symbol)
        if not bse_code:
            logger.warning("No BSE code found for %s", symbol)
            return []

        try:
            resp = self._request_with_retry(
                "GET", f"{_BSE_API}/CorporateAction/w",
                params={"scripcode": bse_code, "index": "", "sector": "", "status": ""},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("BSE corporate actions failed for %s: %s", symbol, e)
            return []

        actions = []

        # Table1 = Bonuses (better structured, has ratio)
        for row in data.get("Table1", []):
            ex_date = _parse_bse_date(row.get("BCRD_FROM", ""))
            if not ex_date:
                continue
            ratio_text = row.get("VALUE", "")
            multiplier = _parse_bonus_multiplier(ratio_text)
            actions.append({
                "symbol": symbol.upper(),
                "ex_date": ex_date,
                "action_type": "bonus",
                "ratio_text": ratio_text,
                "multiplier": multiplier,
                "dividend_amount": None,
                "source": "bse",
            })

        # Table2 = All actions (splits, spinoffs, buybacks, dividends)
        for row in data.get("Table2", []):
            purpose_code = (row.get("purpose_code") or row.get("Purpose_Code") or "").strip()
            ex_date = _parse_bse_date(row.get("Ex_date") or row.get("ex_date") or "")
            if not ex_date:
                continue
            details = row.get("Details") or row.get("details") or row.get("PURPOSE") or ""

            if purpose_code == "SS":  # Stock Split
                multiplier = _parse_split_multiplier(details)
                actions.append({
                    "symbol": symbol.upper(),
                    "ex_date": ex_date,
                    "action_type": "split",
                    "ratio_text": details,
                    "multiplier": multiplier,
                    "dividend_amount": None,
                    "source": "bse",
                })
            elif purpose_code == "SO":  # Spinoff/Demerger
                actions.append({
                    "symbol": symbol.upper(),
                    "ex_date": ex_date,
                    "action_type": "spinoff",
                    "ratio_text": details,
                    "multiplier": None,
                    "dividend_amount": None,
                    "source": "bse",
                })
            elif purpose_code == "BGM":  # Buyback
                actions.append({
                    "symbol": symbol.upper(),
                    "ex_date": ex_date,
                    "action_type": "buyback",
                    "ratio_text": details,
                    "multiplier": None,
                    "dividend_amount": None,
                    "source": "bse",
                })
            elif purpose_code == "DP":  # Dividend
                amount = _parse_dividend_amount(details)
                actions.append({
                    "symbol": symbol.upper(),
                    "ex_date": ex_date,
                    "action_type": "dividend",
                    "ratio_text": details,
                    "multiplier": None,
                    "dividend_amount": amount,
                    "source": "bse",
                })

        # Deduplicate bonuses (Table1 + Table2 may overlap)
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict] = []
        for a in actions:
            key = (a["symbol"], a["ex_date"], a["action_type"])
            if key not in seen:
                seen.add(key)
                deduped.append(a)

        return deduped

    def fetch_yfinance_corporate_actions(self, symbol: str) -> list[dict]:
        """Fetch splits/dividends from yfinance for deeper history."""
        import yfinance as yf

        actions: list[dict] = []
        try:
            ticker = yf.Ticker(f"{symbol}.NS")

            # Splits (includes bonuses -- yfinance can't distinguish)
            splits = ticker.splits
            if splits is not None and len(splits) > 0:
                for date_idx, multiplier in splits.items():
                    if multiplier != 0 and multiplier != 1.0:
                        actions.append({
                            "symbol": symbol.upper(),
                            "ex_date": date_idx.strftime("%Y-%m-%d"),
                            "action_type": "split",
                            "ratio_text": f"yfinance: {multiplier:.1f}x",
                            "multiplier": float(multiplier),
                            "dividend_amount": None,
                            "source": "yfinance",
                        })

            # Dividends
            dividends = ticker.dividends
            if dividends is not None and len(dividends) > 0:
                for date_idx, amount in dividends.items():
                    if amount > 0:
                        actions.append({
                            "symbol": symbol.upper(),
                            "ex_date": date_idx.strftime("%Y-%m-%d"),
                            "action_type": "dividend",
                            "ratio_text": f"Rs.{amount:.2f} per share (split-adjusted)",
                            "multiplier": None,
                            "dividend_amount": float(amount),
                            "source": "yfinance",
                        })
        except Exception as e:
            logger.warning("yfinance corporate actions failed for %s: %s", symbol, e)

        return actions

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FilingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _safe_dirname(name: str) -> str:
    """Convert a category name to a safe directory name."""
    return re.sub(r'[^a-zA-Z0-9_-]+', '_', name).strip('_').lower()


def _filing_date_to_fy_quarter(date_str: str) -> str:
    """Convert filing date to Indian FY quarter folder name.

    Filing dates map to the quarter they report on:
    Jan-Mar filing → Q3 results (Oct-Dec quarter)
    Apr-Jun filing → Q4 results (Jan-Mar quarter)
    Jul-Sep filing → Q1 results (Apr-Jun quarter)
    Oct-Dec filing → Q2 results (Jul-Sep quarter)
    """
    try:
        y, m = int(date_str[:4]), int(date_str[5:7])
    except (ValueError, IndexError):
        return "unknown"

    if m in (1, 2, 3):
        return f"FY{str(y)[2:]}-Q3"
    elif m in (4, 5, 6):
        return f"FY{str(y)[2:]}-Q4"
    elif m in (7, 8, 9):
        return f"FY{str(y + 1)[2:]}-Q1"
    else:
        return f"FY{str(y + 1)[2:]}-Q2"
