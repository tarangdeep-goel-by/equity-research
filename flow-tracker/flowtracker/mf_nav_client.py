"""mfapi.in client for daily per-scheme NAV history.

Endpoint: ``GET https://api.mfapi.in/mf/{scheme_code}`` — returns the
full NAV history since the scheme's regulatory inception (Direct Plans
trace back to 2013-01-01 when SEBI mandated the separate-plan
structure).

Response shape (truncated):

.. code-block:: json

    {
      "meta": {"scheme_code": 118955, "scheme_name": "...", ...},
      "status": "SUCCESS",
      "data": [
        {"date": "26-05-2026", "nav": "2158.76200"},
        {"date": "23-05-2026", "nav": "2155.00100"},
        ...
      ]
    }

This client only fetches; storage and display live in the store /
``mf_commands`` layer. We deliberately do not cap history at ingestion
— the row count for 30 schemes × ~3300 trading days is ~100k rows,
which is trivial for SQLite.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import httpx

from flowtracker.mf_nav_models import MFSchemeNav

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.mfapi.in/mf/{scheme_code}"
MAX_RETRIES = 3
BACKOFF_BASE = 1.0

# ---------------------------------------------------------------------------
# Curated top-30 equity scheme universe.
#
# These are AMFI scheme codes for the Direct Plan / Growth option of
# major Indian equity funds (large/mid/small/flexi/multi/focused/ELSS/
# value/contra/index/sectoral). Selected by AUM and category coverage,
# probed against ``api.mfapi.in/mf`` on 2026-05-27 — every code below
# returns >2500 data points (>~10 years of history; small-cap and ELSS
# funds with later inception dates carry shorter series).
#
# Storage in SQLite is fully indexed by ``scheme_code``; growing this
# list later is a no-op for the schema. The list is intentionally a
# top-level constant so cron + ad-hoc backfill share one source of
# truth.
# ---------------------------------------------------------------------------
EQUITY_SCHEMES: list[tuple[int, str]] = [
    # Flexi Cap (5)
    (118955, "HDFC Flexi Cap Fund"),
    (122639, "Parag Parikh Flexi Cap Fund"),
    (120166, "Kotak Flexicap Fund"),
    (120564, "Aditya Birla Sun Life Flexi Cap Fund"),
    (120662, "UTI Flexi Cap Fund"),
    # Large Cap (4)
    (118825, "Mirae Asset Large Cap Fund"),
    (118632, "Nippon India Large Cap Fund"),
    (119598, "SBI Large Cap Fund"),
    (120586, "ICICI Prudential Large Cap Fund"),
    # Mid Cap (3)
    (118989, "HDFC Mid Cap Fund"),
    (119775, "Kotak Midcap Fund"),
    (127042, "Motilal Oswal Midcap Fund"),
    # Small Cap (3)
    (118778, "Nippon India Small Cap Fund"),
    (125497, "SBI Small Cap Fund"),
    (130503, "HDFC Small Cap Fund"),
    # Large & Mid (2)
    (118834, "Mirae Asset Large & Midcap Fund"),
    (130498, "HDFC Large and Mid Cap Fund"),
    # Multi Cap (2)
    (118650, "Nippon India Multi Cap Fund"),
    (120599, "ICICI Prudential Multicap Fund"),
    # Focused (2)
    (120468, "Axis Focused Fund"),
    (119727, "SBI Focused Fund"),
    # ELSS (2)
    (135781, "Mirae Asset ELSS Tax Saver Fund"),
    (120503, "Axis ELSS Tax Saver Fund"),
    # Value / Contra (2)
    (120323, "ICICI Prudential Value Fund"),
    (119835, "SBI Contra Fund"),
    # Index (3)
    (120716, "UTI Nifty 50 Index Fund"),
    (151728, "HDFC BSE 500 Index Fund"),
    (153161, "ICICI Prudential Nifty 500 Index Fund"),
    # Sectoral Equity (2)
    (118589, "Nippon India Banking & Financial Services Fund"),
    (135800, "Tata Digital India Fund"),
]


class MFNavFetchError(Exception):
    """Raised when an mfapi.in fetch permanently fails."""


class MFNavClient:
    """Fetch daily NAV history from mfapi.in for one or many schemes."""

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
                "Accept": "application/json",
            },
        )

    # ---- public API -----------------------------------------------------

    def fetch_scheme(
        self,
        scheme_code: int,
        *,
        since: str | None = None,
    ) -> list[MFSchemeNav]:
        """Fetch a single scheme's NAV history.

        ``since``: ISO date ``YYYY-MM-DD`` lower bound. Rows older than
        this are filtered out. Pass ``None`` for the full inception-to-date
        history.
        """
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(_BASE_URL.format(scheme_code=scheme_code))
                resp.raise_for_status()
                body = resp.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "mfapi scheme %s attempt %d/%d failed: %s",
                    scheme_code, attempt + 1, MAX_RETRIES, exc,
                )
                if attempt == MAX_RETRIES - 1:
                    raise MFNavFetchError(
                        f"mfapi fetch for scheme {scheme_code} permanently failed: {exc}"
                    ) from exc
                time.sleep(BACKOFF_BASE * (2 ** attempt))

        meta = body.get("meta") or {}
        scheme_name = str(meta.get("scheme_name") or "").strip()
        data = body.get("data") or []

        out: list[MFSchemeNav] = []
        for entry in data:
            raw_date = entry.get("date")
            raw_nav = entry.get("nav")
            iso = _to_iso(raw_date)
            if iso is None:
                continue
            if since is not None and iso < since:
                continue
            try:
                nav_val = float(raw_nav)
            except (TypeError, ValueError):
                continue
            out.append(
                MFSchemeNav(
                    scheme_code=scheme_code,
                    scheme_name=scheme_name,
                    date=iso,
                    nav=nav_val,
                )
            )
        # mfapi returns newest-first; normalise to oldest-first to match
        # the rest of the codebase's time-series convention.
        out.sort(key=lambda r: r.date)
        return out

    def fetch_universe(
        self,
        schemes: list[tuple[int, str]] | None = None,
        *,
        since: str | None = None,
        polite_delay: float = 0.3,
    ) -> dict[int, list[MFSchemeNav]]:
        """Fetch NAVs for many schemes, return code → rows mapping.

        Defaults to the curated ``EQUITY_SCHEMES`` universe. Per-scheme
        failures are logged and the scheme key is omitted from the
        result (caller can detect missing entries against the input
        list).
        """
        targets = schemes if schemes is not None else EQUITY_SCHEMES
        result: dict[int, list[MFSchemeNav]] = {}
        for code, _label in targets:
            try:
                rows = self.fetch_scheme(code, since=since)
                result[code] = rows
            except MFNavFetchError as exc:
                logger.warning("Skipping scheme %s: %s", code, exc)
            time.sleep(polite_delay)
        return result

    @staticmethod
    def default_since(years: int) -> str:
        """ISO ``YYYY-MM-DD`` lower bound ``years`` years before today."""
        return (date.today() - timedelta(days=years * 366)).isoformat()

    # ---- lifecycle ------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MFNavClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _to_iso(raw: object) -> str | None:
    """Convert mfapi's ``DD-MM-YYYY`` to ISO ``YYYY-MM-DD``.

    Returns ``None`` for any unparseable input (logged at the caller
    level so a single bad row doesn't blow up a full backfill).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    parts = s.split("-")
    if len(parts) != 3:
        return None
    dd, mm, yyyy = parts
    if len(dd) != 2 or len(mm) != 2 or len(yyyy) != 4:
        return None
    if not (dd.isdigit() and mm.isdigit() and yyyy.isdigit()):
        return None
    return f"{yyyy}-{mm}-{dd}"
