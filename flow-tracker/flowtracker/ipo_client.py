"""NSE + BSE IPO / SME pipeline clients.

Two clients, both context-managed.

``NSEIPOClient`` covers the main NSE endpoints:
- Upcoming issues (mainboard + SME) — ``/api/all-upcoming-issues``
- Current issues with subscription multiples — ``/api/ipo-current-issue``
- New listings today — ``/api/new-listing-today``

All NSE endpoints require a cookie preflight (hit the public-issues market
data page first). Pattern lifted from ``scan_client.py``.

``BSEIPOClient`` covers BSE SME upcoming. BSE's public IPO page is a JS-
rendered SPA (the JSON endpoints behind it returned 1814-byte HTML placeholders
during probing on 2026-05-26), so the SME fetch is best-effort — wrapped in
try/except by the caller (``ipo_commands.fetch``) so SME failure never breaks
the NSE mainboard pull. Pattern lifted from ``filing_client.py``.

Field-name reference for NSE responses (observed shape, fields may be absent
on individual rows — parsing is defensive):
- ``companyName`` / ``name`` — issuer
- ``symbol`` / ``sym`` — listed symbol (often null for upcoming)
- ``series`` / ``segment`` — "EQ" mainboard, "SME" SME
- ``issueStartDate`` / ``biddingStartDate`` — open
- ``issueEndDate`` / ``biddingEndDate`` — close
- ``listingDate`` — listing
- ``issuePrice`` / ``priceRange`` — band
- ``issueSize`` — total size (₹ Cr)
- ``lotSize`` / ``marketLot`` — lot
- ``qib`` / ``nII`` / ``rII`` / ``employee`` / ``total`` — subscription multiples
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime

import httpx

from flowtracker.ipo_models import IPOIssue, IPOListing, IPOSubscription

logger = logging.getLogger(__name__)


_NSE_BASE = "https://www.nseindia.com"
# Preflights tried in order — NSE rotates the public-issues landing path
# occasionally and bot-detection sometimes 404s a fresh hit. Falling back
# to the home page always works for cookie acquisition.
_NSE_PREFLIGHT_CANDIDATES = (
    f"{_NSE_BASE}/market-data/all-upcoming-issues-public-issues",
    f"{_NSE_BASE}/market-data/new-stock-exchange-listings-recent",
    f"{_NSE_BASE}/",
)
_NSE_PREFLIGHT = _NSE_PREFLIGHT_CANDIDATES[0]  # display/referer header
_NSE_API_UPCOMING = f"{_NSE_BASE}/api/all-upcoming-issues"
_NSE_API_CURRENT = f"{_NSE_BASE}/api/ipo-current-issue"
_NSE_API_LISTING = f"{_NSE_BASE}/api/new-listing-today"

_BSE_BASE = "https://www.bseindia.com"
_BSE_SME_PAGE = f"{_BSE_BASE}/markets/PublicIssues/IPOIssues_new.aspx"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": _NSE_PREFLIGHT,
}

_BSE_HEADERS = {
    "User-Agent": _HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _BSE_BASE,
    "Origin": _BSE_BASE,
}

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0


class NSEIPOError(Exception):
    """Raised when NSE IPO fetch permanently fails."""


# ---------------------------------------------------------------------------
# Parsing helpers


def _parse_date(raw: object) -> str | None:
    """Convert a variety of date formats to ISO YYYY-MM-DD or None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("-", "na", "null", "none"):
        return None
    for fmt in (
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s.split("T")[0] if "T" in s else s, fmt).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            continue
    # Last-ditch: digits-only ISO prefix
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    return None


def _parse_price_band(raw: object) -> tuple[float | None, float | None]:
    """Parse strings like '100-110', '₹100 to ₹110', '110.50' → (low, high)."""
    if raw is None:
        return (None, None)
    s = str(raw).strip()
    if not s:
        return (None, None)
    nums = re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))
    if not nums:
        return (None, None)
    if len(nums) == 1:
        v = float(nums[0])
        return (v, v)
    return (float(nums[0]), float(nums[1]))


def _parse_float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        s = str(raw).replace(",", "").strip()
        if not s or s == "-":
            return None
        # Strip non-numeric suffix like "₹" or " Cr"
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None
    except (ValueError, TypeError):
        return None


def _parse_int(raw: object) -> int | None:
    f = _parse_float(raw)
    return int(f) if f is not None else None


def _classify_segment(raw_series: object) -> str:
    """Map series/segment field → 'MAIN' | 'SME'. Default MAIN."""
    if raw_series is None:
        return "MAIN"
    s = str(raw_series).strip().upper()
    if "SME" in s or s == "SM":
        return "SME"
    return "MAIN"


# ---------------------------------------------------------------------------
# NSE client


class NSEIPOClient:
    """Client for NSE IPO calendar, subscription, and listing endpoints."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the public-issues page to acquire session cookies.

        Tries each preflight candidate in order and accepts the first 2xx —
        NSE's public-issues landing path 404s intermittently (observed
        2026-05-26 after rapid probes); the home page always works as a
        cookie source.
        """
        last_status = None
        for url in _NSE_PREFLIGHT_CANDIDATES:
            try:
                resp = self._client.get(url)
                last_status = resp.status_code
                if 200 <= resp.status_code < 300:
                    self._has_cookies = True
                    return
            except Exception as e:
                last_status = f"err: {e}"
        raise NSEIPOError(
            f"NSE preflight failed across {len(_NSE_PREFLIGHT_CANDIDATES)} "
            f"candidates (last status: {last_status})"
        )

    def _get_json(self, url: str) -> object:
        """GET with cookie refresh + retry on 403. Returns parsed JSON."""
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()
                resp = self._client.get(url)
                if resp.status_code == 403:
                    logger.warning(
                        "NSE 403 on %s (attempt %d) — refreshing cookies",
                        url,
                        attempt + 1,
                    )
                    self._has_cookies = False
                    time.sleep(_BACKOFF_BASE * (2**attempt))
                    continue
                resp.raise_for_status()
                # Empty body sometimes — return [] rather than raise
                if not resp.text.strip():
                    return []
                try:
                    return resp.json()
                except ValueError:
                    # Some endpoints return text 'missing index' on no data
                    logger.debug("NSE %s returned non-JSON: %r", url, resp.text[:120])
                    return []
            except Exception as e:
                last_error = e
                logger.warning(
                    "NSE fetch %s failed (attempt %d): %s", url, attempt + 1, e
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2**attempt))
        raise NSEIPOError(
            f"Failed after {_MAX_RETRIES} attempts: {url} ({last_error})"
        )

    # -- Endpoints --

    def fetch_upcoming(self) -> list[IPOIssue]:
        """Fetch upcoming IPO issues (mainboard + SME) from NSE.

        Pulls both ``?category=ipo`` (mainboard) and ``?category=sme`` so the
        caller gets a unified calendar. Empty responses are normal — NSE
        returns ``[]`` or ``{}`` between IPO windows.
        """
        out: list[IPOIssue] = []
        for category, segment_default in (("ipo", "MAIN"), ("sme", "SME")):
            url = f"{_NSE_API_UPCOMING}?category={category}"
            try:
                data = self._get_json(url)
            except NSEIPOError as e:
                logger.warning("NSE upcoming %s skipped: %s", category, e)
                continue
            for row in _coerce_list(data):
                issue = self._parse_upcoming_row(row, segment_default)
                if issue is not None:
                    out.append(issue)
        return out

    def fetch_subscription(self) -> list[IPOSubscription]:
        """Fetch current-issue subscription multiples from NSE."""
        try:
            data = self._get_json(_NSE_API_CURRENT)
        except NSEIPOError as e:
            logger.warning("NSE current-issue subscription skipped: %s", e)
            return []
        today = date.today().strftime("%Y-%m-%d")
        out: list[IPOSubscription] = []
        for row in _coerce_list(data):
            sub = self._parse_subscription_row(row, today)
            if sub is not None:
                out.append(sub)
        return out

    def fetch_listings(self) -> list[IPOListing]:
        """Fetch newly listed equities from NSE."""
        url = f"{_NSE_API_LISTING}?index=Equity"
        try:
            data = self._get_json(url)
        except NSEIPOError as e:
            logger.warning("NSE new-listing skipped: %s", e)
            return []
        rows: list[dict] = []
        if isinstance(data, dict):
            rows = list(data.get("data") or [])
        elif isinstance(data, list):
            rows = data
        out: list[IPOListing] = []
        for row in rows:
            listing = self._parse_listing_row(row)
            if listing is not None:
                out.append(listing)
        return out

    # -- Row parsers --

    def _parse_upcoming_row(
        self, row: dict, segment_default: str
    ) -> IPOIssue | None:
        if not isinstance(row, dict):
            return None
        issuer = (
            row.get("companyName")
            or row.get("name")
            or row.get("issuerName")
            or row.get("compName")
        )
        if not issuer:
            return None
        low, high = _parse_price_band(
            row.get("priceRange")
            or row.get("issuePrice")
            or row.get("price")
            or ""
        )
        segment = _classify_segment(row.get("series") or row.get("segment")) or segment_default
        if segment != "SME" and segment_default == "SME":
            segment = "SME"
        return IPOIssue(
            issuer_name=str(issuer).strip(),
            symbol=_clean_symbol(row.get("symbol") or row.get("sym")),
            segment=segment,
            exchange="NSE",
            open_date=_parse_date(
                row.get("issueStartDate") or row.get("biddingStartDate") or row.get("openDate")
            ),
            close_date=_parse_date(
                row.get("issueEndDate") or row.get("biddingEndDate") or row.get("closeDate")
            ),
            listing_date=_parse_date(row.get("listingDate")),
            price_band_low=low,
            price_band_high=high,
            issue_size_cr=_parse_float(row.get("issueSize") or row.get("size")),
            lot_size=_parse_int(row.get("lotSize") or row.get("marketLot")),
        )

    def _parse_subscription_row(
        self, row: dict, as_of_date: str
    ) -> IPOSubscription | None:
        if not isinstance(row, dict):
            return None
        issuer = (
            row.get("companyName") or row.get("name") or row.get("issuerName")
        )
        if not issuer:
            return None
        return IPOSubscription(
            issuer_name=str(issuer).strip(),
            as_of_date=as_of_date,
            qib_times=_parse_float(row.get("qib") or row.get("QIB")),
            nii_times=_parse_float(row.get("nII") or row.get("nii") or row.get("NII")),
            retail_times=_parse_float(
                row.get("rII") or row.get("retail") or row.get("Retail")
            ),
            employee_times=_parse_float(
                row.get("employee") or row.get("Employee")
            ),
            total_times=_parse_float(row.get("total") or row.get("Total")),
        )

    def _parse_listing_row(self, row: dict) -> IPOListing | None:
        if not isinstance(row, dict):
            return None
        symbol = _clean_symbol(row.get("symbol") or row.get("sym"))
        if not symbol:
            return None
        issuer = (
            row.get("companyName") or row.get("name") or row.get("issuerName") or symbol
        )
        listing_date = _parse_date(
            row.get("listingDate") or row.get("date") or date.today().isoformat()
        )
        if not listing_date:
            listing_date = date.today().strftime("%Y-%m-%d")
        list_price = _parse_float(row.get("listingPrice") or row.get("issuePrice"))
        close = _parse_float(
            row.get("lastTradedPrice") or row.get("ltp") or row.get("close")
        )
        pop = _parse_float(row.get("pChange") or row.get("changePct"))
        if pop is None and list_price and close:
            pop = (close - list_price) / list_price * 100.0
        return IPOListing(
            symbol=symbol,
            issuer_name=str(issuer).strip(),
            listing_date=listing_date,
            listing_price=list_price,
            listing_day_close=close,
            listing_pop_pct=pop,
        )

    # -- Lifecycle --

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NSEIPOClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# BSE SME client (best-effort)


_BSE_TABLE_ROW_RE = re.compile(
    r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL
)
_BSE_TABLE_CELL_RE = re.compile(
    r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", s)).strip()


class BSEIPOClient:
    """Client for BSE SME upcoming IPOs.

    BSE's IPO page is a JS-rendered SPA. We attempt an HTML fetch of the
    public page and parse any embedded tables. If the page returns the SPA
    shell with no IPO rows (the observed case as of 2026-05-26), this client
    returns an empty list and logs a warning — the caller treats SME data
    as best-effort.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_BSE_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )

    def fetch_upcoming_sme(self) -> list[IPOIssue]:
        """Best-effort fetch of BSE SME upcoming issues.

        Tries plain ``httpx`` first, then a Playwright JS-rendered fetch if
        the httpx response is the SPA shell. Returns ``[]`` if neither
        path yields rows.

        Note: BSE serves ``Access Denied`` to headless Chromium too (Akamai
        Bot Manager), so the Playwright fallback usually returns the same
        empty shell on a clean dev machine. The wiring is intentional —
        the parsing path is now ready for the day BSE relaxes the rule or
        the client runs behind a residential proxy.
        """
        # Path 1: plain httpx
        httpx_html: str | None = None
        try:
            resp = self._client.get(_BSE_SME_PAGE)
            resp.raise_for_status()
            httpx_html = resp.text or ""
        except Exception as e:
            logger.warning("BSE SME page httpx fetch failed: %s", e)

        if httpx_html and "<table" in httpx_html.lower():
            rows = self._parse_sme_html(httpx_html)
            if rows:
                return rows

        # Path 2: Playwright fallback
        rendered = _try_js_rendered_sme()
        if rendered is not None:
            if rendered:
                logger.info(
                    "BSE SME: %d issue(s) extracted via Playwright fallback",
                    len(rendered),
                )
            return rendered

        if httpx_html is not None:
            logger.info(
                "BSE SME page returned SPA shell and JS-render fallback also "
                "yielded nothing — likely no live SME IPO. (%d bytes httpx)",
                len(httpx_html),
            )
        return []

    def _parse_sme_html(self, html: str) -> list[IPOIssue]:
        """Parse BSE SME HTML (httpx or rendered) for IPO rows."""
        out: list[IPOIssue] = []
        for tr in _BSE_TABLE_ROW_RE.findall(html):
            cells = [_strip_html(c) for c in _BSE_TABLE_CELL_RE.findall(tr)]
            if len(cells) < 4:
                continue
            issue = self._parse_sme_row(cells)
            if issue is not None:
                out.append(issue)
        if not out:
            logger.info("BSE SME table present but no parseable rows extracted.")
        return out

    def _parse_sme_row(self, cells: list[str]) -> IPOIssue | None:
        """Parse one BSE SME row.

        BSE column order historically: Issuer | Type | Open | Close | Price |
        Issue Size | Status | ... — but this varies. We pick the first
        non-empty cell as issuer and best-effort extract dates from any cell
        that parses as a date.
        """
        # Filter header rows
        joined = " | ".join(cells).lower()
        if "company" in joined and "open" in joined and "close" in joined:
            return None
        issuer = cells[0]
        if not issuer or len(issuer) < 3:
            return None
        # Skip rows that are clearly not issues
        if issuer.lower() in {"company name", "issuer", "name"}:
            return None
        dates: list[str] = []
        non_date_cells: list[str] = []
        for c in cells[1:]:
            d = _parse_date(c)
            if d:
                dates.append(d)
            else:
                non_date_cells.append(c)
        open_d = dates[0] if dates else None
        close_d = dates[1] if len(dates) > 1 else None
        listing_d = dates[2] if len(dates) > 2 else None
        # Try to find a price band cell — must be from non-date cells so we
        # don't misparse "05-Jun-2026" as a 5–2026 band.
        band_low, band_high = (None, None)
        size_cr = None
        for c in non_date_cells:
            if re.search(r"\d", c) and ("-" in c or "to" in c.lower()):
                low, high = _parse_price_band(c)
                if low and high and high < 100_000:
                    band_low, band_high = low, high
                    break
        for c in non_date_cells:
            if "cr" in c.lower() or "₹" in c:
                size_cr = _parse_float(c)
                if size_cr:
                    break
        return IPOIssue(
            issuer_name=issuer,
            symbol=None,
            segment="SME",
            exchange="BSE",
            open_date=open_d,
            close_date=close_d,
            listing_date=listing_d,
            price_band_low=band_low,
            price_band_high=band_high,
            issue_size_cr=size_cr,
            lot_size=None,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BSEIPOClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Playwright fallback (BSE SME SPA-shell rescue)


def _try_js_rendered_sme() -> list[IPOIssue] | None:
    """Render the BSE SME IPO page with Playwright and parse the result.

    Returns the parsed issue list (possibly empty), or ``None`` if the
    Playwright fetch itself failed (browser missing, navigation timeout,
    or Akamai 403). The caller treats ``None`` as "JS path unavailable;
    fall through to graceful-empty".

    BSE's Akamai Bot Manager today returns a tiny "Access Denied" body to
    headless Chromium just as it does to plain httpx — so this path
    usually returns ``[]`` on a stock dev machine. The wiring exists so
    that any future relaxation (or use behind a residential proxy)
    immediately produces data.
    """
    try:
        # Lazy import — keep js_fetch / Playwright out of the happy httpx
        # path. Falls back to None on any browser-init / nav failure.
        from flowtracker.js_fetch import JSFetchError, fetch_rendered_html
    except ImportError as exc:  # pragma: no cover — js_fetch is a sibling
        logger.warning("BSE SME: js_fetch not importable (%s)", exc)
        return None

    try:
        html = fetch_rendered_html(
            _BSE_SME_PAGE,
            wait_for_selector="table",
            timeout_ms=30_000,
        )
    except JSFetchError as exc:
        logger.info("BSE SME JS-render fallback unavailable: %s", exc)
        return None

    if "Access Denied" in html:
        logger.info(
            "BSE SME JS-render: Akamai access-denied (%d bytes)", len(html),
        )
        return []

    # Parse via the same module-level table regex used by httpx path.
    out: list[IPOIssue] = []
    bse_client = BSEIPOClient.__new__(BSEIPOClient)  # parse-only (no httpx)
    for tr in _BSE_TABLE_ROW_RE.findall(html):
        cells = [_strip_html(c) for c in _BSE_TABLE_CELL_RE.findall(tr)]
        if len(cells) < 4:
            continue
        issue = bse_client._parse_sme_row(cells)
        if issue is not None:
            out.append(issue)
    logger.info(
        "BSE SME JS-render: parsed %d issue(s) from %d bytes", len(out), len(html),
    )
    return out


# ---------------------------------------------------------------------------
# Local helpers


def _coerce_list(data: object) -> list[dict]:
    """Coerce NSE's polymorphic envelope (list | dict-with-data | empty) → list."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("data", "rows", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        # Top-level dict that itself is a single row
        if any(
            k in data for k in ("companyName", "issuerName", "symbol", "sym")
        ):
            return [data]
    return []


def _clean_symbol(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s or s in ("-", "NA", "NULL", "NONE"):
        return None
    return s
