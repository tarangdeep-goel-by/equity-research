"""NSE shareholding XBRL client for quarterly institutional ownership data."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET

import httpx

from flowtracker.holding_models import NSEShareholdingMaster, ShareholdingRecord

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_MASTER_URL = f"{_BASE_URL}/api/corporate-share-holdings-master"
_PREFLIGHT_URL = f"{_BASE_URL}/companies-listing/corporate-filings-shareholding-pattern"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": _PREFLIGHT_URL,
}

MAX_RETRIES = 3
BACKOFF_BASE = 1

# XBRL context ref mapping: category key -> normalized category
# Newer format: "InstitutionsForeign_ContextI" (suffix _ContextI)
# Older format: "InstitutionsForeignI" (suffix I only)
_XBRL_CATEGORY_MAP = {
    "ShareholdingOfPromoterAndPromoterGroup": "Promoter",
    "InstitutionsForeign": "FII",
    "InstitutionsDomestic": "DII",
    "MutualFundsOrUTI": "MF",
    "MutualFundsOrUti": "MF",  # older format uses lowercase 'ti'
    "InsuranceCompanies": "Insurance",
    "NonInstitutions": "Public",
}

# The XBRL element name we look for shareholding percentage
_PERCENTAGE_TAG = "ShareholdingAsAPercentageOfTotalNumberOfShares"


class NSEHoldingError(Exception):
    """Raised when NSE shareholding fetch fails."""


class NSEHoldingClient:
    """Client for NSE India shareholding XBRL data."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=90.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the shareholding page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_master(self, symbol: str) -> list[NSEShareholdingMaster]:
        """Fetch list of quarterly shareholding filings for a symbol.

        Returns list of NSEShareholdingMaster with XBRL URLs.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(
                    _MASTER_URL,
                    params={"index": "equities", "symbol": symbol.upper()},
                )

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()

                results: list[NSEShareholdingMaster] = []
                for item in data:
                    # The API returns items with fields like:
                    # symbol, companyName, date (e.g. "31-Dec-2025"), xbrl (URL)
                    try:
                        xbrl_url = item.get("xbrl", "")
                        if not xbrl_url:
                            continue
                        results.append(NSEShareholdingMaster(
                            symbol=item.get("symbol", symbol.upper()),
                            company_name=item.get("companyName", ""),
                            quarter_end=item.get("date", ""),
                            xbrl_url=xbrl_url,
                        ))
                    except Exception:
                        continue

                return results

            except NSEHoldingError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d for %s master failed: %s", attempt + 1, symbol, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise NSEHoldingError(f"Failed to fetch master for {symbol}: {last_error}")

    def fetch_shareholding(self, xbrl_url: str, symbol: str) -> list[ShareholdingRecord]:
        """Download and parse XBRL XML to extract shareholding percentages.

        XBRL files at nsearchives.nseindia.com don't need auth — direct download.
        """
        try:
            # Direct download, no NSE cookies needed for archive files
            resp = self._client.get(xbrl_url)
            resp.raise_for_status()

            return self._parse_xbrl(resp.content, symbol)
        except Exception as e:
            raise NSEHoldingError(f"Failed to fetch XBRL from {xbrl_url}: {e}")

    def fetch_latest_quarters(
        self, symbol: str, num_quarters: int = 4,
    ) -> list[ShareholdingRecord]:
        """Convenience: fetch master + parse the N most recent XBRL filings."""
        master = self.fetch_master(symbol)
        if not master:
            raise NSEHoldingError(f"No shareholding filings found for {symbol}")

        # Take the most recent N filings
        filings = master[:num_quarters]
        all_records: list[ShareholdingRecord] = []

        for filing in filings:
            try:
                records = self.fetch_shareholding(filing.xbrl_url, symbol.upper())
                all_records.extend(records)
                logger.info("Parsed %s %s: %d records", symbol, filing.quarter_end, len(records))
                time.sleep(0.5)  # Be polite to NSE
            except NSEHoldingError as e:
                logger.warning("Skipping %s %s: %s", symbol, filing.quarter_end, e)

        return all_records

    def _parse_xbrl(self, content: bytes, symbol: str) -> list[ShareholdingRecord]:
        """Parse XBRL XML and extract shareholding percentages.

        Looks for elements with tag containing 'ShareholdingAsAPercentageOfTotalNumberOfShares'
        and context ID ending in '_ContextI' (which represents the "as of date" context).

        The quarter_end date is extracted from the context's instant element.
        """
        root = ET.fromstring(content)

        # Find the namespace — XBRL files have varying namespace prefixes
        # We'll search by local name
        records: list[ShareholdingRecord] = []
        quarter_end: str | None = None

        # First, extract the date from context elements
        for elem in root.iter():
            local = _local_name(elem.tag)
            if local == "context":
                ctx_id = elem.get("id", "")
                if not ctx_id:
                    continue
                # Look for instant date in this context
                for child in elem.iter():
                    if _local_name(child.tag) == "instant" and child.text:
                        # Use the first context with an instant date
                        if quarter_end is None:
                            quarter_end = child.text.strip()
                        break

        if not quarter_end:
            logger.warning("No quarter_end date found in XBRL for %s", symbol)
            return []

        # Now extract shareholding percentages
        # The tag name is always "ShareholdingAsAPercentageOfTotalNumberOfShares"
        # The category is encoded in the contextRef (e.g. "InstitutionsForeign_ContextI")
        #
        # Detect format: newer XBRL uses decimals (0.5001 = 50.01%), older uses
        # actual percentages (50.07). Check the total (ShareholdingPattern_ContextI)
        # to determine which format.
        is_decimal = False
        raw_values: list[tuple[str, float]] = []

        for elem in root.iter():
            local = _local_name(elem.tag)
            if local != _PERCENTAGE_TAG:
                continue

            ctx_ref = elem.get("contextRef", "")

            # Handle both formats:
            # Newer: "InstitutionsForeign_ContextI" -> strip "_ContextI"
            # Older: "InstitutionsForeignI" -> strip trailing "I"
            if ctx_ref.endswith("_ContextI"):
                ctx_key = ctx_ref[: -len("_ContextI")]
            elif ctx_ref.endswith("I") and not ctx_ref.endswith("UTI"):
                ctx_key = ctx_ref[:-1]
            else:
                continue

            try:
                val = float(elem.text.strip()) if elem.text else None
            except (ValueError, AttributeError):
                continue

            if val is None:
                continue

            # Check the total to detect format
            if ctx_key == "ShareholdingPattern":
                is_decimal = val <= 2.0  # ~1.0 for decimal, ~100 for percentage
                continue

            if ctx_key in _XBRL_CATEGORY_MAP:
                raw_values.append((ctx_key, val))

        for ctx_key, val in raw_values:
            category = _XBRL_CATEGORY_MAP[ctx_key]
            pct = round(val * 100, 2) if is_decimal else round(val, 2)
            records.append(ShareholdingRecord(
                symbol=symbol.upper(),
                quarter_end=quarter_end,
                category=category,
                percentage=pct,
            ))

        return records

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NSEHoldingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _local_name(tag: str) -> str:
    """Extract local name from a possibly namespaced XML tag.

    '{http://example.com}ElementName' -> 'ElementName'
    'ElementName' -> 'ElementName'
    """
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
