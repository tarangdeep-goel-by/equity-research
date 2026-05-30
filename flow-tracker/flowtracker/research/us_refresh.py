"""Fetch fresh US data for a stock before the research agent runs (US add-on, P3.4).

US analogue of :func:`flowtracker.research.refresh.refresh_for_research`. Pulls
each US source through the EXISTING ingestion clients (no new fetching logic) and
routes the results into the ``us_*`` tables. Mirrors the reference orchestrator's
style: per-source non-fatal try/except (one failing source never aborts the
others), an ``_ok`` / ``_skip`` logging pattern, and a ``{source: count}`` summary.

Sources pulled (summary-dict keys):
  * ``annual_financials`` / ``quarterly_financials`` — SEC EDGAR companyfacts.
  * ``daily_prices`` — yfinance daily OHLCV (via ``us_ingest``).
  * ``valuation_snapshot`` — yfinance point-in-time snapshot.
  * ``consensus_estimates`` — yfinance analyst consensus.
  * ``insider_transactions`` — SEC EDGAR Form 4.
  * ``institutional_13f`` — SEC EDGAR 13F (manager-indexed; see below).

13F handling
------------
13F filings are indexed at EDGAR by MANAGER, not by issuer, and there is no free
complete issuer → all-managers reverse index (building one needs a curated fund
universe — out of scope for the validation slice per P3.3). So ``refresh_us``
SKIPS 13F by default, recording ``_skip("institutional_13f", ...)``. Callers that
already know which managers to pull can pass ``manager_ciks=[...]`` to fetch those
managers' latest holdings (issuer rows are filtered to ``symbol`` before upsert).

Rate limits: the EDGAR clients already throttle to ≤10 req/s and the yfinance
path is cached, so this orchestrator does no extra sleeping — it just avoids
hammering by making one pass per source.
"""

from __future__ import annotations

import logging
import time

from rich.console import Console

logger = logging.getLogger(__name__)

# US markets in symbol_registry, in lookup-preference order.
_US_MARKETS = ("NASDAQ", "NYSE")


def _resolve_symbol(store, symbol: str) -> tuple[str | None, str]:
    """Return ``(cik, market)`` for ``symbol``.

    Prefers the symbol_registry entry (across US markets) for both CIK + market;
    falls back to live CIK resolution via ``EdgarClient.cik_for`` with a default
    market of ``NASDAQ`` when the symbol is not registered.
    """
    for market in _US_MARKETS:
        entry = store.get_symbol_registry_entry(symbol, market)
        if entry:
            return entry.get("cik"), entry.get("market") or market

    # Not registered — resolve CIK live, default market NASDAQ.
    from flowtracker.edgar_client import EdgarClient

    try:
        with EdgarClient() as ec:
            cik = ec.cik_for(symbol)
    except Exception as e:  # pragma: no cover — network failure is non-fatal
        logger.warning("[us_refresh] %s: CIK resolution failed: %s", symbol, e)
        cik = None
    return cik, "NASDAQ"


def refresh_us(
    symbol: str,
    store=None,
    console: Console | None = None,
    *,
    manager_ciks: list[str] | None = None,
) -> dict[str, int]:
    """Fetch fresh US data for ``symbol`` into the ``us_*`` tables.

    Each source is pulled with an independent non-fatal try/except so one failing
    source never aborts the rest. Returns a ``{source: record_count}`` summary.

    Args:
        symbol: US ticker (case-insensitive).
        store: an open ``FlowStore``. If ``None``, one is opened for this call.
        console: optional Rich console for progress output.
        manager_ciks: optional list of 13F manager CIKs to pull. When omitted,
            13F is skipped (manager-indexed; issuer reverse lookup deferred).
    """
    symbol = symbol.upper()
    refresh_start = time.time()
    logger.info("[us_refresh] %s: started", symbol)
    summary: dict[str, int] = {}

    def _log(msg: str) -> None:
        if console:
            console.print(msg)

    def _ok(name: str, count: int) -> None:
        summary[name] = count
        _log(f"  [green]✓[/] {name}: {count} records")
        logger.info("[us_refresh] %s: %s ok %d records", symbol, name, count)

    def _skip(name: str, err: str) -> None:
        summary[name] = 0
        _log(f"  [yellow]✗[/] {name}: {err}")
        logger.warning("[us_refresh] %s: %s skipped: %s", symbol, name, err)

    own_store = store is None
    if own_store:
        from flowtracker.store import FlowStore

        store = FlowStore()

    try:
        cik, market = _resolve_symbol(store, symbol)
        _log(f"\n[bold]US refresh: {symbol}[/] (market={market}, cik={cik or 'unresolved'})")

        # Register the symbol up front so run-market auto-resolution is reliable
        # on later runs (WS-1). COALESCE-safe upsert — never nulls existing data.
        try:
            store.upsert_symbol_registry(symbol, market, cik=cik)
        except Exception as e:  # pragma: no cover — registration is best-effort
            logger.warning("[us_refresh] %s: registry upsert failed: %s", symbol, e)

        # Capture the GICS-style sector from yfinance and persist it on the
        # registry so data_api._us_industry_from_registry can map it to a
        # sector_kpis industry (e.g. 'Technology' → 'IT - Software'). Without
        # this, industry resolves to "Unknown" live, breaking D&A defaults and
        # sector_kpis. Non-fatal like every other source. COALESCE-safe upsert.
        try:
            from flowtracker.fund_client import FundClient
            from flowtracker.market import Market

            info = FundClient()._info(symbol, Market(market))
            sector = (info.get("sector") or "").strip() or None
            if sector:
                store.upsert_symbol_registry(symbol, market, sector=sector, gics=sector)
                _ok("registry_sector", 1)
            else:
                _skip("registry_sector", "no sector in yfinance info")
        except Exception as e:  # pragma: no cover — best-effort, non-fatal
            _skip("registry_sector", str(e))

        # --- 1. EDGAR fundamentals (annual + quarterly) ---
        try:
            if not cik:
                raise ValueError("no CIK resolved")
            from flowtracker.edgar_client import EdgarClient

            with EdgarClient() as ec:
                facts = ec.fetch_company_facts(cik)
                annual = ec.normalize_annual(facts, symbol, market=market)
                quarterly = ec.normalize_quarterly(facts, symbol, market=market)
            if annual:
                store.upsert_us_annual_financials(annual)
                _ok("annual_financials", len(annual))
            else:
                _skip("annual_financials", "no data parsed")
            if quarterly:
                store.upsert_us_quarterly_financials(quarterly)
                _ok("quarterly_financials", len(quarterly))
            else:
                _skip("quarterly_financials", "no data parsed")
        except Exception as e:
            _skip("annual_financials", str(e))
            _skip("quarterly_financials", str(e))

        # --- 2. Daily prices (yfinance) ---
        try:
            from flowtracker.market import Market
            from flowtracker.us_ingest import fetch_us_daily_prices

            rows = fetch_us_daily_prices(symbol, market=Market(market))
            if rows:
                store.upsert_us_daily_prices(rows)
                _ok("daily_prices", len(rows))
            else:
                _skip("daily_prices", "no data")
        except Exception as e:
            _skip("daily_prices", str(e))

        # --- 3. Valuation snapshot (yfinance) ---
        try:
            from flowtracker.market import Market
            from flowtracker.us_ingest import fetch_us_valuation_snapshot

            snap = fetch_us_valuation_snapshot(symbol, market=Market(market))
            if snap:
                store.upsert_us_valuation_snapshot([snap])
                _ok("valuation_snapshot", 1)
            else:
                _skip("valuation_snapshot", "no data")
        except Exception as e:
            _skip("valuation_snapshot", str(e))

        # --- 4. Consensus estimates (yfinance) ---
        try:
            from flowtracker.market import Market
            from flowtracker.us_ingest import fetch_us_consensus_estimates

            est = fetch_us_consensus_estimates(symbol, market=Market(market))
            if est:
                store.upsert_us_consensus_estimates([est])
                _ok("consensus_estimates", 1)
            else:
                _skip("consensus_estimates", "no data")
        except Exception as e:
            _skip("consensus_estimates", str(e))

        # --- 5. Insider transactions (EDGAR Form 4) ---
        try:
            from flowtracker.edgar_ownership import EdgarOwnershipClient

            with EdgarOwnershipClient() as oc:
                trades = oc.fetch_insider_transactions(symbol, cik=cik, market=market)
            if trades:
                store.upsert_us_insider_transactions(trades)
                _ok("insider_transactions", len(trades))
            else:
                _skip("insider_transactions", "no data")
        except Exception as e:
            _skip("insider_transactions", str(e))

        # --- 6. 13F institutional holdings (manager-indexed) ---
        # 13F is filed by the MANAGER; there is no free issuer→managers reverse
        # index (out of scope per P3.3). Skip unless explicit manager CIKs are
        # provided, in which case pull those managers and keep this issuer's rows.
        if not manager_ciks:
            _skip("institutional_13f", "manager-indexed; reverse lookup deferred")
        else:
            try:
                from flowtracker.edgar_ownership import EdgarOwnershipClient

                kept: list[dict] = []
                with EdgarOwnershipClient() as oc:
                    for mgr in manager_ciks:
                        holdings = oc.fetch_13f_for_manager(mgr, market=market)
                        kept.extend(h for h in holdings if h.get("symbol") == symbol)
                if kept:
                    store.upsert_us_institutional_holdings(kept)
                    _ok("institutional_13f", len(kept))
                else:
                    _skip("institutional_13f", f"no {symbol} holdings in {len(manager_ciks)} manager(s)")
            except Exception as e:
                _skip("institutional_13f", str(e))
    finally:
        if own_store:
            store.close()

    total = sum(summary.values())
    logger.info(
        "[us_refresh] %s: done %.1fs, %d sources, %d total records",
        symbol, time.time() - refresh_start, len(summary), total,
    )
    return summary
