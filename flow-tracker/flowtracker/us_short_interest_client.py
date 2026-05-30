"""US short-interest client — Nasdaq's per-symbol short-interest API.

Short interest (shares sold short, days-to-cover) is the canonical US
ownership-depth sentiment metric, published twice a month on settlement
dates by FINRA and surfaced per-symbol by Nasdaq. This is the US analogue
slot alongside ``us_insider_transactions`` (Form 4) and
``us_institutional_holdings`` (13F).

Source: ``https://api.nasdaq.com/api/quote/{symbol}/short-interest`` — an
undocumented-but-stable JSON endpoint that returns the full bi-monthly
settlement-date history (``shortInterestTable.rows``) with shares short,
average daily share volume, and days-to-cover. It requires a browser-like
``User-Agent``/``Accept`` or it returns 403.

Numbers in the response are human-formatted strings ("138,782,718"); the
parser strips commas and coerces. Settlement dates are ``MM/DD/YYYY`` and are
normalized to ``YYYY-MM-DD`` to match the store convention. Pure parsing lives
in ``parse_short_interest`` so it is unit-testable without network.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.nasdaq.com/api/quote/{symbol}/short-interest"
# Nasdaq's API 403s plain clients; a browser-like header set is required.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _to_float(val) -> float | None:
    """Coerce a Nasdaq numeric string ("138,782,718" / "2.7446" / "") to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("$", "")
    if not s or s in ("--", "N/A", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_date(val: str | None) -> str | None:
    """``MM/DD/YYYY`` → ``YYYY-MM-DD``. Pass through already-ISO or unparseable."""
    if not val:
        return None
    s = str(val).strip()
    parts = s.split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        mm, dd, yyyy = parts
        return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return s


def parse_short_interest(payload: dict, symbol: str, market: str = "NASDAQ") -> list[dict]:
    """Parse a Nasdaq short-interest JSON payload into us_short_interest rows.

    Returns ``[]`` for an empty / error / shapeless payload (never raises).
    Each row: symbol, market, currency, settlement_date, short_interest,
    avg_daily_volume, days_to_cover.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or {}
    table = (data.get("shortInterestTable") or {}) if isinstance(data, dict) else {}
    rows = table.get("rows") or []
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        settlement = _norm_date(r.get("settlementDate"))
        if not settlement:
            continue
        out.append({
            "symbol": symbol.upper(),
            "market": market,
            "currency": "USD",
            "settlement_date": settlement,
            "short_interest": _to_float(r.get("interest")),
            "avg_daily_volume": _to_float(r.get("avgDailyShareVolume")),
            "days_to_cover": _to_float(r.get("daysToCover")),
        })
    return out


def fetch_us_short_interest(
    symbol: str,
    *,
    market: str = "NASDAQ",
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch + parse Nasdaq short interest for ``symbol``.

    Returns parsed rows (most-recent-first ordering is left to the store query).
    On any HTTP/parse failure returns ``[]`` and logs — callers (refresh_us)
    treat short interest as a best-effort source.
    """
    url = _BASE.format(symbol=symbol.upper())
    params = {"assetClass": "stocks"}
    owns_client = client is None
    client = client or httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001 — best-effort source
        logger.warning("short_interest fetch failed for %s: %s", symbol, e)
        return []
    finally:
        if owns_client:
            client.close()
    return parse_short_interest(payload, symbol, market)
