"""Screener-vs-yfinance share-count sanity reconciliation.

Background: NESTLEIND had a 2x share-count divergence between Screener.in
(source of truth) and yfinance, partially fixed in PR #114. This module
provides a generic divergence check + universe scanner so the long tail
of similar bugs can be flagged.

Screener-side share count is read from the most recent
``quarterly_balance_sheet`` row (populated by the Screener Excel parser).
The yfinance value is fetched live via ``yfinance.Ticker(...).info``.

This is read-only validation — no new tables, no writes. Results are
returned as plain dicts for downstream display / programmatic use.
"""

from __future__ import annotations

from typing import Any

import yfinance as yf

from flowtracker.fund_client import nse_symbol
from flowtracker.store import FlowStore


def _get_screener_shares(store: FlowStore, symbol: str) -> float | None:
    """Most recent Screener-sourced shares_outstanding from quarterly_balance_sheet.

    Returns None if no row exists or the latest row's shares_outstanding is null.
    """
    rows = store.get_quarterly_balance_sheet(symbol, limit=1)
    if not rows:
        return None
    val = rows[0].get("shares_outstanding")
    return float(val) if val is not None else None


def _get_yfinance_shares(symbol: str) -> float | None:
    """Live yfinance ``sharesOutstanding`` for the symbol (auto-suffixes ``.NS``)."""
    try:
        ticker = yf.Ticker(nse_symbol(symbol))
        val = ticker.info.get("sharesOutstanding")
    except Exception:
        return None
    return float(val) if val is not None else None


def _divergence_pct(a: float, b: float) -> float:
    """Symmetric percent divergence: |a - b| / max(|a|, |b|) * 100.

    Using max-denominator avoids the asymmetry of picking one side as the
    reference (a 2x error reads as 50% with this formula vs 100%/-50%
    depending on which side you divide by).
    """
    denom = max(abs(a), abs(b))
    if denom == 0:
        return 0.0
    return abs(a - b) / denom * 100.0


def check_share_count_divergence(
    symbol: str,
    *,
    threshold_pct: float = 10.0,
    store: FlowStore | None = None,
) -> dict[str, Any]:
    """Compare Screener vs yfinance shares_outstanding for a single symbol.

    Returns a dict shaped one of two ways:

    * Both sides present:
      ``{symbol, screener_shares, yfinance_shares, divergence_pct, flagged}``
    * Missing data:
      ``{symbol, status: "missing_screener" | "missing_yfinance" | "both_missing"}``

    Args:
        symbol: NSE symbol (uppercase, no suffix).
        threshold_pct: ``flagged=True`` if divergence_pct exceeds this.
        store: Reuse an open FlowStore; otherwise open a fresh one.
    """
    symbol = symbol.upper()
    own_store = store is None
    s = store if store is not None else FlowStore()
    try:
        screener = _get_screener_shares(s, symbol)
    finally:
        if own_store:
            s.close()

    yfinance = _get_yfinance_shares(symbol)

    if screener is None and yfinance is None:
        return {"symbol": symbol, "status": "both_missing"}
    if screener is None:
        return {"symbol": symbol, "status": "missing_screener"}
    if yfinance is None:
        return {"symbol": symbol, "status": "missing_yfinance"}

    div = _divergence_pct(screener, yfinance)
    return {
        "symbol": symbol,
        "screener_shares": screener,
        "yfinance_shares": yfinance,
        "divergence_pct": div,
        "flagged": div > threshold_pct,
    }


def scan_universe_divergence(
    symbols: list[str] | None = None,
    threshold_pct: float = 10.0,
    *,
    store: FlowStore | None = None,
) -> list[dict[str, Any]]:
    """Run the divergence check across a universe of symbols.

    When ``symbols`` is None, scans every symbol in ``company_snapshot``
    (the canonical universe). Results are sorted by ``divergence_pct``
    descending; rows missing data sort to the end.

    Args:
        symbols: Optional explicit symbol list. None = whole company_snapshot.
        threshold_pct: Forwarded to per-symbol check.
        store: Reuse an open FlowStore; otherwise open a fresh one.
    """
    own_store = store is None
    s = store if store is not None else FlowStore()
    try:
        if symbols is None:
            rows = s._conn.execute(
                "SELECT symbol FROM company_snapshot ORDER BY symbol"
            ).fetchall()
            symbols = [r["symbol"] for r in rows]

        results = [
            check_share_count_divergence(sym, threshold_pct=threshold_pct, store=s)
            for sym in symbols
        ]
    finally:
        if own_store:
            s.close()

    # Sort: rows with divergence_pct first (desc), then missing-data rows.
    def _sort_key(r: dict) -> tuple[int, float]:
        if "divergence_pct" in r:
            return (0, -r["divergence_pct"])
        return (1, 0.0)

    results.sort(key=_sort_key)
    return results
