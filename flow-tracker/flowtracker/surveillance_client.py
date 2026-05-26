"""NSE/BSE surveillance flag clients (ASM/ESM/GSM).

Cookie preflight + 403-retry pattern mirrors ``scan_client.py`` verbatim for
the NSE side. The BSE side is a graceful HTML scrape: BSE's ESM page is an
Angular SPA that loads its data via an XHR we have not been able to
reverse-engineer from the public JS bundle (the lazy chunks containing the
ESM route do not surface a clean ``/api/...`` URL). We therefore:

1. GET ``https://www.bseindia.com/markets/equity/EQReports/ESM.html``
2. Parse any inline JSON or static ``<table>`` rows the page may contain.
3. If nothing is found (SPA shell only), return ``[]`` rather than raising —
   matches the pragmatic stance taken in ``fda_client.py`` for FDA's
   JS-rendered dashboard. The class exposes ``json_endpoint`` so a future
   contributor who discovers the live XHR URL can swap it in without
   reshaping callers.

``fetch_all_flags()`` runs both clients and concatenates the lists; an
error in one source does not block the other — the call site decides
whether to raise.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime

import httpx

from flowtracker.surveillance_models import SurveillanceFlag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared HTTP knobs (mirror scan_client.py)
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds


# ---------------------------------------------------------------------------
# NSE side (ASM + GSM)
# ---------------------------------------------------------------------------

_NSE_BASE = "https://www.nseindia.com"
_NSE_ASM_API = f"{_NSE_BASE}/api/reportASM"
_NSE_GSM_API = f"{_NSE_BASE}/api/reportGSM"
_NSE_ASM_PREFLIGHT = f"{_NSE_BASE}/reports/asm"
_NSE_GSM_PREFLIGHT = f"{_NSE_BASE}/reports/gsm"


class SurveillanceFetchError(Exception):
    """Raised when an NSE/BSE surveillance fetch permanently fails."""


class NSESurveillanceClient:
    """NSE ASM + GSM surveillance flag fetcher.

    Same cookie + 403-retry pattern as :class:`NSEIndexClient` in
    ``scan_client.py``: a preflight GET on the human-facing report page
    acquires the cookies the JSON API requires; on a 403 we drop cookies and
    retry up to ``MAX_RETRIES`` with exponential backoff.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    # -- cookie warmup -----------------------------------------------------

    def _ensure_cookies(self, preflight_url: str) -> None:
        """Hit the human-facing report page to acquire session cookies."""
        resp = self._client.get(preflight_url)
        resp.raise_for_status()
        self._has_cookies = True

    def _fetch_json(self, api_url: str, preflight_url: str) -> dict | list:
        """GET ``api_url`` with cookie warmup + 403-retry. Returns parsed JSON."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies(preflight_url)
                # Per-call Referer matches the human-facing page.
                resp = self._client.get(api_url, headers={"Referer": preflight_url})
                if resp.status_code == 403:
                    logger.warning(
                        "Got 403 from %s (attempt %d), refreshing cookies",
                        api_url, attempt + 1,
                    )
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001 — retry surface
                last_error = e
                logger.warning(
                    "Attempt %d failed for %s: %s", attempt + 1, api_url, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
        raise SurveillanceFetchError(
            f"Failed after {MAX_RETRIES} attempts for {api_url}: {last_error}"
        )

    # -- public API --------------------------------------------------------

    def fetch_asm(self) -> list[SurveillanceFlag]:
        """Fetch the current NSE ASM list (long-term + short-term combined)."""
        data = self._fetch_json(_NSE_ASM_API, _NSE_ASM_PREFLIGHT)
        return _parse_nse_asm(data)

    def fetch_gsm(self) -> list[SurveillanceFlag]:
        """Fetch the current NSE GSM list."""
        data = self._fetch_json(_NSE_GSM_API, _NSE_GSM_PREFLIGHT)
        return _parse_nse_gsm(data)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NSESurveillanceClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# BSE side (ESM)
# ---------------------------------------------------------------------------

_BSE_ESM_HTML = "https://www.bseindia.com/markets/equity/EQReports/ESM.html"


class BSESurveillanceClient:
    """BSE ESM surveillance flag fetcher.

    Best-effort. BSE's ESM page is a JS-rendered Angular SPA; the data
    arrives via an XHR whose URL is buried in lazy chunks we have not been
    able to grep cleanly. Today we:

    - GET the public HTML and try to harvest data from any inline JSON
      payload or static ``<table>`` rows the server may include.
    - If only the SPA shell is returned (common today), return ``[]`` so the
      composite ``fetch_all_flags`` call still succeeds.
    - Expose ``json_endpoint`` so a future contributor who discovers the
      live XHR URL can plug it in without API churn.

    Tests cover both the SPA-shell case (returns empty) and a static-table
    fixture (returns parsed flags) so the parser is exercised even though
    the live page does not currently return one.
    """

    def __init__(self, *, json_endpoint: str | None = None) -> None:
        self.json_endpoint = json_endpoint
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )

    def fetch_esm(self) -> list[SurveillanceFlag]:
        """Fetch the current BSE ESM list.

        Tries the configured ``json_endpoint`` first if one is set, then
        falls back to ``httpx`` HTML scrape, then to a Playwright
        rendered-HTML scrape (handles the Angular SPA case). Returns
        ``[]`` if none of the paths yield rows — typical when no ESM
        flags are currently active.

        Note: BSE's Akamai Bot Manager actively blocks headless browsers
        too (returns ``Access Denied`` even to fully-rendered Chromium).
        The Playwright fallback unblocks the *parsing* path so that any
        future relaxation of the Akamai rule (or use behind a residential
        proxy) immediately produces data — but on a clean dev machine
        today, this path will also return empty.
        """
        if self.json_endpoint:
            try:
                resp = self._client.get(self.json_endpoint)
                resp.raise_for_status()
                if "json" in resp.headers.get("content-type", "").lower():
                    return _parse_bse_esm_json(resp.json())
            except Exception as e:  # noqa: BLE001 — fall through to HTML scrape
                logger.warning("BSE ESM JSON endpoint failed (%s); HTML fallback", e)

        last_error: Exception | None = None
        httpx_html: str | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(_BSE_ESM_HTML)
                resp.raise_for_status()
                httpx_html = resp.text
                flags = _parse_bse_esm_html(httpx_html)
                if flags:
                    return flags
                # httpx returned 200 but the parser found nothing (SPA shell
                # case). Try the Playwright fallback below.
                break
            except Exception as e:  # noqa: BLE001 — retry surface
                last_error = e
                logger.warning(
                    "BSE ESM HTML attempt %d failed: %s", attempt + 1, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        # Playwright fallback — JS-rendered HTML for the Angular SPA.
        rendered_flags = _try_js_rendered_esm()
        if rendered_flags is not None:
            if rendered_flags:
                logger.info(
                    "BSE ESM: %d flags extracted via Playwright fallback",
                    len(rendered_flags),
                )
            return rendered_flags

        if httpx_html is not None:
            # httpx succeeded earlier but yielded an empty parse and JS
            # fallback also failed — return [] (matches the pre-existing
            # graceful behavior).
            return []

        raise SurveillanceFetchError(
            f"BSE ESM fetch failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BSESurveillanceClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Playwright fallback (BSE ESM SPA-shell rescue)
# ---------------------------------------------------------------------------


def _try_js_rendered_esm() -> list[SurveillanceFlag] | None:
    """Render the BSE ESM page with Playwright and parse the result.

    Returns the parsed flag list (possibly empty), or ``None`` if the
    Playwright fetch itself failed (browser missing, navigation timeout,
    or Akamai block returning an Access-Denied shell). The caller treats
    ``None`` as "JS path unavailable; fall through to httpx behavior".
    """
    try:
        # Lazy import — keep js_fetch / Playwright out of the happy httpx
        # path. The import succeeds even with no browser installed; the
        # browser-missing case is raised as JSFetchError on first fetch.
        from flowtracker.js_fetch import JSFetchError, fetch_rendered_html
    except ImportError as exc:  # pragma: no cover — js_fetch is a sibling
        logger.warning("BSE ESM: js_fetch not importable (%s)", exc)
        return None

    try:
        html = fetch_rendered_html(
            _BSE_ESM_HTML,
            wait_for_selector="table",
            timeout_ms=30_000,
        )
    except JSFetchError as exc:
        # Common today: Akamai 403 → tiny "Access Denied" body → "table"
        # selector never appears → JSFetchError. Log at info, return None
        # so the caller's graceful-empty path takes over.
        logger.info("BSE ESM JS-render fallback unavailable: %s", exc)
        return None

    if "Access Denied" in html:
        logger.info(
            "BSE ESM JS-render: Akamai access-denied (%d bytes)", len(html),
        )
        return []

    flags = _parse_bse_esm_html(html)
    logger.info(
        "BSE ESM JS-render: parsed %d flag(s) from %d bytes",
        len(flags), len(html),
    )
    return flags


# ---------------------------------------------------------------------------
# Top-level helper
# ---------------------------------------------------------------------------


def fetch_all_flags() -> list[SurveillanceFlag]:
    """Fetch ASM + GSM (NSE) + ESM (BSE) and return the merged list.

    Each source is wrapped in its own try/except so a partial outage on one
    exchange does not block the other. Errors are logged at WARNING level
    and contribute zero rows to the result.
    """
    flags: list[SurveillanceFlag] = []

    try:
        with NSESurveillanceClient() as nse:
            flags.extend(nse.fetch_asm())
    except Exception as e:  # noqa: BLE001
        logger.warning("NSE ASM fetch failed: %s", e)
    try:
        with NSESurveillanceClient() as nse:
            flags.extend(nse.fetch_gsm())
    except Exception as e:  # noqa: BLE001
        logger.warning("NSE GSM fetch failed: %s", e)
    try:
        with BSESurveillanceClient() as bse:
            flags.extend(bse.fetch_esm())
    except Exception as e:  # noqa: BLE001
        logger.warning("BSE ESM fetch failed: %s", e)

    return flags


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_nse_date(raw: str | None) -> str:
    """Normalize NSE date strings to ISO ``YYYY-MM-DD``.

    NSE publishes dates as ``DD-MMM-YYYY`` (ASM) or ``DD-MMM-YYYY HH:MM:SS``
    (GSM). Falls back to today's date if parsing fails — better to keep the
    row than drop it for a date wobble.
    """
    if not raw:
        return date.today().isoformat()
    head = str(raw).strip().split(" ", 1)[0]
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def _parse_nse_asm(payload: dict | list) -> list[SurveillanceFlag]:
    """Convert NSE ``/api/reportASM`` JSON into ``SurveillanceFlag`` rows.

    NSE returns a dict with ``longterm`` and ``shortterm`` sub-dicts, each
    holding a ``data`` list. Both bucket types collapse into ``alert_type =
    "ASM"`` — the long/short distinction is preserved in ``reason`` via the
    upstream ``survDesc`` which spells out "Long Term" / "Short Term".
    """
    flags: list[SurveillanceFlag] = []
    if not isinstance(payload, dict):
        return flags
    for bucket in ("longterm", "shortterm"):
        sub = payload.get(bucket) or {}
        for row in sub.get("data", []) or []:
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            flags.append(SurveillanceFlag(
                symbol=sym.upper(),
                alert_type="ASM",
                stage=row.get("asmSurvIndicator"),
                exchange="NSE",
                effective_date=_parse_nse_date(row.get("asmTime")),
                reason=row.get("survDesc"),
            ))
    return flags


def _parse_nse_gsm(payload: dict | list) -> list[SurveillanceFlag]:
    """Convert NSE ``/api/reportGSM`` JSON into ``SurveillanceFlag`` rows.

    NSE returns either a bare list of rows or a dict wrapping ``data``;
    we tolerate both for forward-compat.
    """
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        # Some NSE endpoints wrap in {"data": [...]}; handle both.
        if isinstance(payload.get("data"), list):
            rows = payload["data"]

    flags: list[SurveillanceFlag] = []
    for row in rows:
        sym = (row.get("symbol") or "").strip()
        if not sym:
            continue
        flags.append(SurveillanceFlag(
            symbol=sym.upper(),
            alert_type="GSM",
            stage=row.get("gsmStage"),
            exchange="NSE",
            effective_date=_parse_nse_date(row.get("gsmTime")),
            reason=row.get("survDesc"),
        ))
    return flags


def _parse_bse_esm_json(payload: dict | list) -> list[SurveillanceFlag]:
    """Convert a hypothetical BSE ESM JSON response into ``SurveillanceFlag`` rows.

    Shape mirrors the patterns seen across other BSE ``/BseIndiaAPI/api/.../w``
    endpoints (``Table`` / ``Data`` / plain list of dicts). Field name
    variations are checked permissively because BSE's column casing is
    inconsistent across endpoints.
    """
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        for key in ("Table", "Data", "data", "Records", "records"):
            v = payload.get(key)
            if isinstance(v, list):
                rows = [r for r in v if isinstance(r, dict)]
                break

    flags: list[SurveillanceFlag] = []
    for row in rows:
        sym = (
            row.get("Symbol")
            or row.get("symbol")
            or row.get("ScripCode")
            or row.get("scrip_code")
            or row.get("scripcd")
            or ""
        )
        sym = str(sym).strip()
        if not sym:
            continue
        stage = (
            row.get("Stage")
            or row.get("ESMStage")
            or row.get("ESMSurvIndicator")
            or row.get("Stagename")
        )
        eff = (
            row.get("EffectiveDate")
            or row.get("EffectiveFrom")
            or row.get("EffDate")
            or row.get("Date")
        )
        flags.append(SurveillanceFlag(
            symbol=sym.upper(),
            alert_type="ESM",
            stage=str(stage) if stage else None,
            exchange="BSE",
            effective_date=_parse_nse_date(str(eff) if eff else None),
            reason=row.get("Reason") or row.get("Remarks"),
        ))
    return flags


# Static table parser: BSE's legacy non-SPA reports sometimes embed the data
# in an HTML <table>. The Angular SPA shell does not, but we keep the parser
# so the regression test covers it and so a "scrape works again" upstream
# change does not require code changes.
_TABLE_BLOCK_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_ROW_BLOCK_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_BLOCK_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Inline-JSON patterns we have seen on legacy BSE pages
_INLINE_JSON_RE = re.compile(
    r"window\.__ESM_DATA__\s*=\s*(\[.*?\]|\{.*?\});", re.DOTALL,
)


def _clean_cell(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_STRIP_RE.sub("", html)).strip()


def _parse_bse_esm_html(html: str) -> list[SurveillanceFlag]:
    """Best-effort ESM HTML parser. Returns ``[]`` for the SPA-shell case."""
    # 1. Inline JSON window assignment (legacy BSE pages occasionally have this).
    m = _INLINE_JSON_RE.search(html)
    if m:
        try:
            return _parse_bse_esm_json(json.loads(m.group(1)))
        except json.JSONDecodeError:
            logger.warning("BSE ESM inline JSON failed to parse; falling through")

    # 2. Static <table> rows. Header row must contain "Symbol" or "Scrip" for
    #    us to recognise it as the ESM list (the page can include other tables).
    flags: list[SurveillanceFlag] = []
    for table_html in _TABLE_BLOCK_RE.findall(html):
        rows = _ROW_BLOCK_RE.findall(table_html)
        if len(rows) < 2:
            continue
        header_cells = [_clean_cell(c).lower() for c in _CELL_BLOCK_RE.findall(rows[0])]
        if not any("symbol" in h or "scrip" in h for h in header_cells):
            continue
        # Build column-index map for tolerated header names.
        idx = {}
        for i, h in enumerate(header_cells):
            if "symbol" in h or "scrip" in h:
                idx.setdefault("symbol", i)
            if "stage" in h:
                idx.setdefault("stage", i)
            if "effective" in h or "date" in h:
                idx.setdefault("date", i)
            if "reason" in h or "remark" in h:
                idx.setdefault("reason", i)
        if "symbol" not in idx:
            continue
        for row_html in rows[1:]:
            cells = [_clean_cell(c) for c in _CELL_BLOCK_RE.findall(row_html)]
            if not cells:
                continue
            sym = cells[idx["symbol"]] if idx["symbol"] < len(cells) else ""
            if not sym:
                continue
            stage = cells[idx["stage"]] if "stage" in idx and idx["stage"] < len(cells) else None
            eff = cells[idx["date"]] if "date" in idx and idx["date"] < len(cells) else None
            reason = cells[idx["reason"]] if "reason" in idx and idx["reason"] < len(cells) else None
            flags.append(SurveillanceFlag(
                symbol=sym.upper(),
                alert_type="ESM",
                stage=stage or None,
                exchange="BSE",
                effective_date=_parse_nse_date(eff),
                reason=reason or None,
            ))
    return flags
