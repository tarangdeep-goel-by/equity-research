#!/usr/bin/env python3
"""One-time backfill for Nifty 250 — fills all DB tables with historical data.

Run this ONCE to populate the database. After this, cron scripts keep data fresh.

Usage:
    uv run python scripts/backfill-nifty250.py                    # everything
    uv run python scripts/backfill-nifty250.py --step valuation    # just one step
    uv run python scripts/backfill-nifty250.py --limit 50          # first 50 stocks
    uv run python scripts/backfill-nifty250.py --resume            # skip fresh data
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

console = Console()


def get_nifty_250() -> list[str]:
    from flowtracker.store import FlowStore
    with FlowStore() as store:
        rows = store._conn.execute(
            "SELECT symbol FROM index_constituents ORDER BY symbol LIMIT 250"
        ).fetchall()
    return [r[0] for r in rows]


def step_valuation(symbols: list[str], sleep: float = 0.5):
    """Fetch yfinance valuation snapshot for all stocks."""
    from flowtracker.fund_client import FundClient
    from flowtracker.store import FlowStore

    console.print("\n[bold]Step: Valuation Snapshots (yfinance)[/]")
    fc = FundClient()
    ok = 0
    with FlowStore() as store:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as p:
            task = p.add_task("Valuation", total=len(symbols))
            for sym in symbols:
                p.update(task, description=sym)
                try:
                    snaps = fc.fetch_valuation_snapshot(sym)
                    if snaps:
                        store.upsert_valuation_snapshot(snaps)
                        ok += 1
                except Exception:
                    pass
                p.advance(task)
                time.sleep(sleep)
    console.print(f"  [green]✓[/] {ok}/{len(symbols)} stocks")


def step_estimates(symbols: list[str], sleep: float = 0.5):
    """Fetch consensus estimates + earnings surprises."""
    from flowtracker.estimates_client import EstimatesClient
    from flowtracker.store import FlowStore

    console.print("\n[bold]Step: Consensus Estimates + Earnings Surprises (yfinance)[/]")
    ec = EstimatesClient()
    ok = 0
    with FlowStore() as store:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as p:
            task = p.add_task("Estimates", total=len(symbols))
            for sym in symbols:
                p.update(task, description=sym)
                try:
                    est = ec.fetch_estimates(sym)
                    if est:
                        store.upsert_consensus_estimates(est)
                    surp = ec.fetch_surprises(sym)
                    if surp:
                        store.upsert_earnings_surprises(surp)
                    ok += 1
                except Exception:
                    pass
                p.advance(task)
                time.sleep(sleep)
    console.print(f"  [green]✓[/] {ok}/{len(symbols)} stocks")


def step_shareholding(symbols: list[str], sleep: float = 1.0):
    """Fetch shareholding patterns from NSE XBRL."""
    console.print("\n[bold]Step: Shareholding + Pledge (NSE XBRL)[/]")
    console.print("  [dim]This uses the scan commands which batch-fetch shareholding[/]")

    import subprocess
    result = subprocess.run(
        ["uv", "run", "flowtrack", "scan", "fetch"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent),
    )
    if result.returncode == 0:
        console.print(f"  [green]✓[/] Shareholding scan complete")
    else:
        console.print(f"  [yellow]⚠[/] Scan error: {result.stderr[:200]}")


def step_screener(symbols: list[str], sleep: float = 2.0):
    """Fetch quarterly results + annual financials + ratios from Screener.in."""
    from flowtracker.screener_client import ScreenerClient
    from flowtracker.store import FlowStore

    console.print("\n[bold]Step: Quarterly/Annual Financials + Ratios (Screener.in)[/]")
    console.print(f"  [dim]Rate limited: {sleep}s between stocks (Screener blocks aggressive scraping)[/]")
    ok = 0

    with FlowStore() as store, ScreenerClient() as sc:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as p:
            task = p.add_task("Screener", total=len(symbols))
            for sym in symbols:
                p.update(task, description=sym)
                try:
                    html = sc.fetch_company_page(sym)
                    if not html:
                        p.advance(task)
                        continue

                    # Quarterly results
                    from flowtracker.screener_client import parse_quarterly_from_html
                    qr = parse_quarterly_from_html(html, sym)
                    if qr:
                        store.upsert_quarterly_results(qr)

                    # Annual financials (via Excel export)
                    from flowtracker.screener_client import _extract_ids_from_html
                    _, wid = _extract_ids_from_html(html)
                    if wid:
                        try:
                            from flowtracker.screener_client import parse_annual_financials
                            excel = sc.fetch_excel_export(wid)
                            af = parse_annual_financials(excel, sym)
                            if af:
                                store.upsert_annual_financials(af)
                        except Exception:
                            pass

                    # Ratios
                    from flowtracker.screener_client import parse_ratios_from_html
                    ratios = parse_ratios_from_html(html, sym)
                    if ratios:
                        store.upsert_screener_ratios(ratios)

                    ok += 1
                except Exception:
                    pass
                p.advance(task)
                time.sleep(sleep)
    console.print(f"  [green]✓[/] {ok}/{len(symbols)} stocks")


def step_filings(symbols: list[str], sleep: float = 1.0):
    """Download concall + investor deck PDFs from BSE."""
    from flowtracker.filing_client import FilingClient
    from dateutil.relativedelta import relativedelta

    console.print("\n[bold]Step: Concall + Investor Deck PDFs (BSE)[/]")
    cutoff = date.today() - relativedelta(years=5)

    fc = FilingClient()
    total_downloaded = 0
    _RELEVANT = ["transcript", "concall", "earnings call", "investor presentation", "investor deck"]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as p:
        task = p.add_task("Filings", total=len(symbols))
        for sym in symbols:
            p.update(task, description=sym)
            try:
                filings = fc.fetch_research_filings(sym, from_date=cutoff)
                for filing in filings:
                    hl = filing.headline.lower()
                    sc = (filing.subcategory or "").lower()
                    is_relevant = any(kw in hl or kw in sc for kw in _RELEVANT)
                    if "analyst" in sc and any(kw in hl for kw in ["investor", "transcript", "presentation", "earnings"]):
                        is_relevant = True
                    if not is_relevant:
                        continue
                    try:
                        path = fc.download_filing(filing)
                        if path:
                            total_downloaded += 1
                    except Exception:
                        pass
            except Exception:
                pass
            p.advance(task)
            time.sleep(sleep)
    console.print(f"  [green]✓[/] {total_downloaded} PDFs downloaded across {len(symbols)} stocks")


STEPS = {
    "valuation": step_valuation,
    "estimates": step_estimates,
    "shareholding": step_shareholding,
    "screener": step_screener,
    "filings": step_filings,
}


def main():
    parser = argparse.ArgumentParser(description="Backfill Nifty 250 data")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--step", choices=list(STEPS.keys()), help="Run single step")
    parser.add_argument("--sleep", type=float, default=None, help="Override sleep between requests")
    args = parser.parse_args()

    symbols = get_nifty_250()[:args.limit]
    console.print(f"[bold]Nifty 250 Backfill — {len(symbols)} stocks[/]")

    if args.step:
        fn = STEPS[args.step]
        kwargs = {"sleep": args.sleep} if args.sleep else {}
        fn(symbols, **kwargs)
    else:
        # Run all steps in order (cheapest/fastest first)
        console.print("\nRunning all steps: valuation → estimates → shareholding → screener → filings\n")
        step_valuation(symbols, sleep=args.sleep or 0.5)
        step_estimates(symbols, sleep=args.sleep or 0.5)
        step_shareholding(symbols)
        step_screener(symbols, sleep=args.sleep or 2.0)
        step_filings(symbols, sleep=args.sleep or 1.0)

    console.print("\n[bold green]Backfill complete![/]")


if __name__ == "__main__":
    main()
