"""niftyindices.com index-level PE / PB / Dividend-Yield historical client.

The niftyindices PE/PB/Div-Yield endpoint is a POST-form returning a JSON
envelope wrapping a stringified JSON array:

    POST https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString
    Content-Type: application/json; charset=utf-8
    Body: {"cinfo": "{'name':'<TRADING_NAME>',
                      'startDate':'DD-MMM-YYYY',
                      'endDate':'DD-MMM-YYYY',
                      'indexName':'<DISPLAY_NAME>'}"}

    Response: {"d": "<JSON-encoded list of
                     {RequestNumber, Index Name, DATE 'DD MMM YYYY',
                      pe, pb, divYield} rows>"}

The site caps each request at **365 days** of history; for longer ranges
the client paginates internally.

The ``name`` field uses the short *trading* name from IndexMapping.json
(e.g. "NIFTY SMLCAP 250") while ``indexName`` uses the canonical *display*
name (e.g. "NIFTY SMALLCAP 250"). Both are required.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta

import httpx

from flowtracker.indexpe_models import IndexValuation

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString"
_REFERER = "https://www.niftyindices.com/reports/historical-data"

MAX_RETRIES = 3
BACKOFF_BASE = 1
PAGE_DAYS = 360  # niftyindices caps at 365; leave headroom for inclusive edges

# (display indexName, posted-form `name` value).
# `name` maps to Trading_Index_Name in IndexMapping.json — when the trading
# name differs from the display name (e.g. SMLCAP vs SMALLCAP) the POST
# returns an empty array unless the abbreviation is used.
#
# Trading-name slugs probed live against niftyindices.com on 2026-05-27
# (each name returns >0 rows for a 10-day Jan 2025 window). When the
# default display==trading name returns [], the trading name is hard-coded.
INDEX_NAME_MAP: dict[str, str] = {
    # Broad-market (covered since PR #148)
    "NIFTY 50": "NIFTY 50",
    "NIFTY 500": "NIFTY 500",
    "NIFTY MIDCAP 150": "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250": "NIFTY SMLCAP 250",
    # Sectoral (10) — all use display==trading except FINANCIAL SERVICES
    "NIFTY BANK": "NIFTY BANK",
    "NIFTY IT": "NIFTY IT",
    "NIFTY PHARMA": "NIFTY PHARMA",
    "NIFTY AUTO": "NIFTY AUTO",
    "NIFTY FMCG": "NIFTY FMCG",
    "NIFTY METAL": "NIFTY METAL",
    "NIFTY ENERGY": "NIFTY ENERGY",
    "NIFTY REALTY": "NIFTY REALTY",
    "NIFTY PSU BANK": "NIFTY PSU BANK",
    "NIFTY FINANCIAL SERVICES": "NIFTY FIN SERVICE",
    # Thematic (12) — many use trading-name abbreviations
    "NIFTY INDIA CONSUMPTION": "NIFTY CONSUMPTION",
    "NIFTY INDIA MANUFACTURING": "NIFTY INDIA MFG",
    "NIFTY INFRASTRUCTURE": "NIFTY INFRA",
    "NIFTY SERVICES SECTOR": "NIFTY SERV SECTOR",
    "NIFTY MNC": "NIFTY MNC",
    "NIFTY MEDIA": "NIFTY MEDIA",
    "NIFTY HEALTHCARE INDEX": "NIFTY HEALTHCARE",
    "NIFTY OIL & GAS": "NIFTY OIL AND GAS",
    "NIFTY PRIVATE BANK": "NIFTY PVT BANK",
    "NIFTY CONSUMER DURABLES": "NIFTY CONSR DURBL",
    "NIFTY CPSE": "NIFTY CPSE",
    "NIFTY INDIA DEFENCE": "NIFTY IND DEFENCE",
}

# Subsets for backfill-by-group ergonomics.
BROAD_INDICES: list[str] = [
    "NIFTY 50",
    "NIFTY 500",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
]
SECTORAL_INDICES: list[str] = [
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY PSU BANK",
    "NIFTY FINANCIAL SERVICES",
]
THEMATIC_INDICES: list[str] = [
    "NIFTY INDIA CONSUMPTION",
    "NIFTY INDIA MANUFACTURING",
    "NIFTY INFRASTRUCTURE",
    "NIFTY SERVICES SECTOR",
    "NIFTY MNC",
    "NIFTY MEDIA",
    "NIFTY HEALTHCARE INDEX",
    "NIFTY OIL & GAS",
    "NIFTY PRIVATE BANK",
    "NIFTY CONSUMER DURABLES",
    "NIFTY CPSE",
    "NIFTY INDIA DEFENCE",
]

SUPPORTED_INDICES: list[str] = list(INDEX_NAME_MAP.keys())


class IndexValuationFetchError(Exception):
    """Raised when an index-valuation fetch permanently fails."""


class IndexValuationClient:
    """Client for niftyindices.com historical PE/PB/Div-Yield data."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json; charset=utf-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": _REFERER,
                "Origin": "https://www.niftyindices.com",
            },
        )

    # ---- public API -----------------------------------------------------

    def fetch_range(
        self,
        index_name: str,
        start_date: date,
        end_date: date,
    ) -> list[IndexValuation]:
        """Fetch PE/PB/Div-Yield rows for an index across [start, end].

        Transparently paginates in ~360-day chunks (niftyindices caps at
        365 per call). Returns rows ordered oldest-first; empty list if the
        endpoint has no data for the range.
        """
        display_name = index_name.strip().upper()
        if display_name not in INDEX_NAME_MAP:
            raise IndexValuationFetchError(
                f"Unsupported index '{index_name}'. "
                f"Supported: {sorted(INDEX_NAME_MAP)}"
            )
        posted_name = INDEX_NAME_MAP[display_name]

        if start_date > end_date:
            raise IndexValuationFetchError(
                f"start_date {start_date} > end_date {end_date}"
            )

        all_rows: list[IndexValuation] = []
        cursor = start_date
        while cursor <= end_date:
            chunk_end = min(cursor + timedelta(days=PAGE_DAYS - 1), end_date)
            rows = self._fetch_chunk(display_name, posted_name, cursor, chunk_end)
            all_rows.extend(rows)
            cursor = chunk_end + timedelta(days=1)
            if cursor <= end_date:
                # be polite to the upstream between paginated chunks
                time.sleep(0.5)

        # Dedupe by (date, index_name) and sort oldest-first.
        seen: dict[tuple[str, str], IndexValuation] = {}
        for r in all_rows:
            seen[(r.date, r.index_name)] = r
        return sorted(seen.values(), key=lambda v: v.date)

    def fetch_latest(self, index_name: str) -> IndexValuation | None:
        """Fetch the most recent index-valuation row available.

        Pulls the last ~10 trading days and returns the latest non-empty
        row. Returns None when no data is available (holidays, outage).
        """
        today = date.today()
        rows = self.fetch_range(index_name, today - timedelta(days=10), today)
        if not rows:
            return None
        return rows[-1]

    # ---- internals ------------------------------------------------------

    def _fetch_chunk(
        self,
        display_name: str,
        posted_name: str,
        start: date,
        end: date,
    ) -> list[IndexValuation]:
        """Single HTTP call for a <=365-day window."""
        start_str = start.strftime("%d-%b-%Y")
        end_str = end.strftime("%d-%b-%Y")
        inner = (
            "{'name':'" + posted_name + "',"
            "'startDate':'" + start_str + "',"
            "'endDate':'" + end_str + "',"
            "'indexName':'" + display_name + "'}"
        )
        payload = json.dumps({"cinfo": inner})

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.post(_ENDPOINT, content=payload)
                resp.raise_for_status()
                return self._parse_response(resp.text, display_name)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "indexpe %s [%s..%s] attempt %d/%d failed: %s",
                    display_name, start, end, attempt + 1, MAX_RETRIES, exc,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        logger.error(
            "indexpe fetch for %s [%s..%s] permanently failed", display_name, start, end,
        )
        return []

    def _parse_response(self, body: str, display_name: str) -> list[IndexValuation]:
        """Parse the niftyindices double-wrapped JSON envelope into models."""
        return parse_pepb_response(body, display_name)

    # ---- lifecycle ------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "IndexValuationClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def parse_pepb_response(body: str, display_name: str) -> list[IndexValuation]:
    """Parse a niftyindices PE/PB response body for ``display_name``.

    Exposed as a module-level helper so the parser is exercised without
    standing up the HTTP client (golden-fixture tests).
    """
    try:
        outer = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("indexpe response was not valid JSON (len=%d)", len(body))
        return []

    inner_raw = outer.get("d")
    if not inner_raw:
        return []
    if isinstance(inner_raw, str):
        try:
            inner = json.loads(inner_raw)
        except json.JSONDecodeError:
            logger.warning("indexpe inner payload was not valid JSON")
            return []
    else:
        inner = inner_raw

    out: list[IndexValuation] = []
    canonical = display_name.strip().upper()
    for row in inner:
        try:
            d_iso = _parse_date(row.get("DATE", ""))
            if not d_iso:
                continue
            out.append(
                IndexValuation(
                    date=d_iso,
                    index_name=canonical,
                    pe=_parse_float_or_none(row.get("pe")),
                    pb=_parse_float_or_none(row.get("pb")),
                    dividend_yield=_parse_float_or_none(row.get("divYield")),
                )
            )
        except (ValueError, TypeError) as exc:
            logger.debug("skipping malformed indexpe row %r: %s", row, exc)
            continue
    return out


def _parse_date(val: str | object) -> str | None:
    """Convert niftyindices "DD MMM YYYY" to ISO ``YYYY-MM-DD``."""
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_float_or_none(val: object) -> float | None:
    """Parse a value into a float; tolerate ``""``, ``"-"``, ``None``."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in {"-", "—", "NA", "N/A"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None
