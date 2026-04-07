"""Peer data refresh and sector benchmark computation.

After refresh_for_research() populates data for the subject stock, this module
fetches financial metrics for ALL peers in the peer_comparison table, then
computes sector-level benchmarks (median, percentiles) for ~13 key metrics.

Caching: FMP free tier = 250 req/day. Before fetching for any peer, we check
whether data already exists in the DB. Financial fundamentals change quarterly,
so any existing record is considered fresh. Valuation snapshots (yfinance) are
checked for 7-day freshness since prices change daily.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta

from rich.console import Console

logger = logging.getLogger(__name__)

# (metric_name, source_table, column_name)
# Primary: Screener peer_comparison (always available)
# Secondary: yfinance valuation_snapshot (fetched per peer)
# Tertiary: FMP tables (may 403 on free tier for .NS stocks)
_BENCHMARK_METRICS: list[tuple[str, str, str]] = [
    # Screener peer table — always available for peers
    ("pe", "peer_comparison", "pe"),
    ("market_cap", "peer_comparison", "market_cap"),
    ("roce", "peer_comparison", "roce"),
    ("div_yield", "peer_comparison", "div_yield"),
    # yfinance valuation_snapshot — fetched for subject + peers
    ("pb", "valuation_snapshot", "pb_ratio"),
    ("forward_pe", "valuation_snapshot", "forward_pe"),
    ("trailing_pe", "valuation_snapshot", "trailing_pe"),
    ("enterprise_to_ebitda", "valuation_snapshot", "enterprise_to_ebitda"),
    ("profit_margin", "valuation_snapshot", "profit_margins"),
    ("operating_margin", "valuation_snapshot", "operating_margins"),
    ("beta", "valuation_snapshot", "beta"),
    # FMP tables — may not be available on free tier
    ("roe_fmp", "fmp_key_metrics", "roe"),
    ("roic_fmp", "fmp_key_metrics", "roic"),
    ("debt_to_equity", "fmp_key_metrics", "debt_to_equity"),
    ("revenue_growth", "fmp_financial_growth", "revenue_growth"),
    ("net_income_growth", "fmp_financial_growth", "net_income_growth"),
]


def _resolve_peer_symbol(peer: dict, conn) -> str | None:  # noqa: ANN001
    """Resolve a usable ticker symbol for a peer from the peer_comparison row.

    Strategy:
    1. Use peer_symbol if already populated in the DB.
    2. Look up peer_name in index_constituents (Nifty 500 mapping).
    3. Fall back to peer_name directly — works for single-word names that
       match ticker symbols (e.g. "Infosys" won't work, but "NAUKRI" might).
    """
    # 1. Explicit peer_symbol
    sym = peer.get("peer_symbol")
    if sym:
        # Strip exchange suffix if present
        return sym.replace(".NS", "").replace(".BO", "").strip()

    name = peer.get("peer_name", "").strip()
    if not name:
        return None

    # 2. Look up in index_constituents by company_name (case-insensitive LIKE)
    row = conn.execute(
        "SELECT symbol FROM index_constituents WHERE company_name LIKE ? LIMIT 1",
        (f"%{name}%",),
    ).fetchone()
    if row:
        return row[0]

    # 3. If peer_name looks like a ticker (all caps, no spaces), try it directly
    if re.match(r"^[A-Z][A-Z0-9&-]+$", name):
        return name

    return None


def _has_fmp_data(conn, table: str, symbol: str) -> bool:  # noqa: ANN001
    """Check if ANY record exists in an FMP table for this symbol.

    Financial fundamentals (key_metrics, financial_growth, dcf) change at most
    quarterly, so any existing record counts as cached.
    """
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE symbol = ? LIMIT 1",  # noqa: S608
        (symbol,),
    ).fetchone()
    return row is not None


def _has_fresh_valuation(conn, symbol: str, days: int = 7) -> bool:  # noqa: ANN001
    """Check if valuation_snapshot has a record within `days` days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT 1 FROM valuation_snapshot WHERE symbol = ? AND date >= ? LIMIT 1",
        (symbol, cutoff),
    ).fetchone()
    return row is not None


def _get_latest_metric(conn, table: str, column: str, symbol: str) -> float | None:  # noqa: ANN001
    """Get the most recent value of a metric for a symbol from any table.

    Handles different table schemas:
    - peer_comparison: uses peer_symbol for peer lookups, symbol for subject
    - valuation_snapshot: has date column, order by date
    - fmp_*: has date column, order by date
    """
    try:
        if table == "peer_comparison":
            # For peers: look up by peer_symbol. For subject: look up by symbol=peer_symbol
            row = conn.execute(
                f"SELECT {column} FROM {table} WHERE peer_symbol = ? LIMIT 1",  # noqa: S608
                (symbol,),
            ).fetchone()
        elif table == "valuation_snapshot":
            row = conn.execute(
                f"SELECT {column} FROM {table} WHERE symbol = ? ORDER BY date DESC LIMIT 1",  # noqa: S608
                (symbol,),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT {column} FROM {table} WHERE symbol = ? ORDER BY date DESC LIMIT 1",  # noqa: S608
                (symbol,),
            ).fetchone()
    except Exception:
        return None

    if row and row[0] is not None:
        try:
            val = float(row[0])
            # Filter out obviously invalid values
            if val != val:  # NaN check
                return None
            return val
        except (ValueError, TypeError):
            return None
    return None


def _compute_benchmarks(
    store,  # noqa: ANN001
    symbol: str,
    peer_symbols: list[str],
    console: Console | None,
) -> int:
    """Compute and store sector benchmarks for each metric.

    For each metric, collects the subject's value and all peer values from the
    DB, then calls store.upsert_sector_benchmark().

    Returns count of benchmarks computed.
    """
    conn = store._conn  # noqa: SLF001
    count = 0

    for metric_name, table, column in _BENCHMARK_METRICS:
        # Subject value
        subject_value = _get_latest_metric(conn, table, column, symbol)

        # Collect peer values (skip None)
        peer_values: list[float] = []
        for ps in peer_symbols:
            val = _get_latest_metric(conn, table, column, ps)
            if val is not None:
                peer_values.append(val)

        if not peer_values and subject_value is None:
            continue  # no data at all for this metric

        store.upsert_sector_benchmark(symbol, metric_name, subject_value, peer_values)
        count += 1

    if console:
        console.print(f"  [green]\u2713[/] sector_benchmarks: {count} metrics computed")

    return count


def refresh_peers(symbol: str, console: Console | None = None) -> dict[str, int]:
    """Fetch financial data for all peers of a stock, then compute sector benchmarks.

    Returns summary dict: {peers_found, peers_fetched, peers_cached,
                           peers_skipped, benchmarks_computed}
    """
    import time as _time
    symbol = symbol.upper()
    peer_start = _time.time()
    logger.info("[peer_refresh] %s: started", symbol)

    def _log(msg: str) -> None:
        if console:
            console.print(msg)

    from flowtracker.store import FlowStore

    with FlowStore() as store:
        conn = store._conn  # noqa: SLF001

        # --- Get peer list ---
        peers = store.get_peers(symbol)
        peers_found = len(peers)
        _log(f"\n[bold]Peer refresh for {symbol}[/] — {peers_found} peers in DB")

        if not peers:
            _log("  [yellow]\u2717[/] No peers found. Run refresh_for_research() first.")
            return {
                "peers_found": 0,
                "peers_fetched": 0,
                "peers_cached": 0,
                "peers_skipped": 0,
                "benchmarks_computed": 0,
            }

        # --- Resolve peer symbols ---
        resolved: list[tuple[str, str]] = []  # (peer_name, ticker_symbol)
        for peer in peers:
            ps = _resolve_peer_symbol(peer, conn)
            if ps:
                resolved.append((peer.get("peer_name", ""), ps))
            else:
                _log(f"  [dim]? {peer.get('peer_name', '?')} — could not resolve symbol, skipping[/]")

        # Merge Yahoo-recommended peers from peer_links table
        yahoo_peers = store.get_peer_links(symbol)
        existing_syms = {s for _, s in resolved}
        for yp in yahoo_peers:
            ys = yp["peer_symbol"]
            if ys and ys != symbol and ys not in existing_syms:
                resolved.append((ys, ys))
                existing_syms.add(ys)

        _log(f"  Resolved {len(resolved)}/{peers_found} peer symbols")

        # --- Fetch data per peer ---
        from flowtracker.fmp_client import FMPClient
        from flowtracker.fund_client import FundClient

        try:
            fmp = FMPClient()
        except (FileNotFoundError, ValueError) as e:
            _log(f"  [yellow]\u2717[/] FMP client: {e}")
            fmp = None

        fc = FundClient()

        peers_fetched = 0
        peers_cached = 0
        peers_skipped = 0
        fetched_symbols: list[str] = []
        cutoff_str = (date.today() - timedelta(days=7)).isoformat()

        for peer_name, peer_sym in resolved:
            # Check company_snapshot cache first (flywheel)
            snapshot = store.get_company_snapshot(peer_sym)
            if snapshot and snapshot.get("yfinance_updated_at"):
                yf_ts = snapshot["yfinance_updated_at"][:10]
                if yf_ts >= cutoff_str:
                    peers_cached += 1
                    fetched_symbols.append(peer_sym)
                    continue

            # Peers already have Screener data (pe, market_cap, roce) from peer_comparison.
            # We only need yfinance valuation_snapshot for additional metrics.
            val_cached = _has_fresh_valuation(conn, peer_sym, days=7)

            if val_cached:
                peers_cached += 1
                _log(f"  [dim]\u2713 {peer_sym} — cached[/]")
                fetched_symbols.append(peer_sym)
                continue

            _log(f"  [cyan]\u2193[/] {peer_sym} ({peer_name})")

            try:
                # yfinance valuation snapshot (PB, margins, beta, forward PE, etc.)
                try:
                    snap = fc.fetch_valuation_snapshot(peer_sym)
                    if snap:
                        store.upsert_valuation_snapshot(snap)
                        # Build company_snapshot for this peer (flywheel)
                        try:
                            from flowtracker.research.snapshot_builder import build_company_snapshot
                            build_company_snapshot(peer_sym, store)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("yfinance snapshot for %s: %s", peer_sym, e)

                # FMP data (optional — may 403 on free tier for .NS stocks)
                if fmp is not None:
                    fmp_cached = _has_fmp_data(conn, "fmp_key_metrics", peer_sym)
                    if not fmp_cached:
                        try:
                            metrics = fmp.fetch_key_metrics(peer_sym, limit=1)
                            if metrics:
                                store.upsert_fmp_key_metrics(metrics)
                            time.sleep(0.5)
                        except Exception:
                            pass  # FMP failures are expected on free tier
                        try:
                            growth = fmp.fetch_financial_growth(peer_sym, limit=1)
                            if growth:
                                store.upsert_fmp_financial_growth(growth)
                            time.sleep(0.5)
                        except Exception:
                            pass

                peers_fetched += 1
                fetched_symbols.append(peer_sym)

            except Exception as e:
                _log(f"  [yellow]\u2717[/] {peer_sym}: {e}")
                peers_skipped += 1

        _log(
            f"\n  Fetched: {peers_fetched} | Cached: {peers_cached} | "
            f"Skipped: {peers_skipped}"
        )

        # --- Compute sector benchmarks ---
        _log("\n[bold]Sector benchmarks[/]")
        benchmarks_computed = _compute_benchmarks(store, symbol, fetched_symbols, console)

    result = {
        "peers_found": peers_found,
        "peers_fetched": peers_fetched,
        "peers_cached": peers_cached,
        "peers_skipped": peers_skipped,
        "benchmarks_computed": benchmarks_computed,
    }
    logger.info("[peer_refresh] %s: done %.1fs, %d peers fetched, %d cached, %d benchmarks",
                symbol, _time.time() - peer_start, peers_fetched, peers_cached, benchmarks_computed)
    return result
