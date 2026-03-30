"""Fundamentals CLI commands."""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress

from flowtracker.fund_client import FundClient, YFinanceError
from flowtracker.screener_client import ScreenerClient, ScreenerError
from flowtracker.fund_display import (
    display_live_snapshot,
    display_peer_comparison,
    display_quarterly_history,
    display_valuation_band,
)
from flowtracker.store import FlowStore

app = typer.Typer(
    name="fund",
    help="Fundamentals: valuation, earnings, peer comparison",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    symbol: Annotated[str | None, typer.Option("-s", "--symbol", help="Fetch for specific symbol")] = None,
    valuation_only: Annotated[bool, typer.Option("--valuation-only", help="Only fetch valuation snapshot")] = False,
) -> None:
    """Fetch valuation snapshots from yfinance.

    Fetches daily valuation metrics (P/E, P/B, margins, beta, etc.) for all
    Nifty 500 stocks. Quarterly results come from Screener.in via 'fund backfill'.
    """
    with FlowStore() as store:
        if symbol:
            symbols = [symbol.upper()]
        else:
            # Use scanner symbols (Nifty 500) instead of watchlist
            symbols = store.get_all_scanner_symbols()
            if not symbols:
                console.print("[yellow]No index constituents. Run 'flowtrack scan refresh' first.[/]")
                raise typer.Exit(1)

    client = FundClient()
    total = len(symbols)

    with Progress(console=console) as progress:
        task = progress.add_task("Fetching valuations...", total=total)

        with FlowStore() as store:
            for i, sym in enumerate(symbols):
                progress.update(task, description=f"[bold]{sym}[/]")

                try:
                    snap = client.fetch_valuation_snapshot(sym)
                    store.upsert_valuation_snapshot(snap)
                except YFinanceError as e:
                    console.print(f"  [red]x[/] {sym}: {e}")

                progress.advance(task)

                if i < total - 1:
                    time.sleep(0.3)

    console.print(f"\n[bold]Done.[/] Fetched valuation snapshots for {total} stock(s).")


@app.command()
def show(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Live fetch — display current fundamentals snapshot."""
    client = FundClient()
    try:
        snap = client.get_live_snapshot(symbol.upper())
    except YFinanceError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    display_live_snapshot(snap)


@app.command()
def history(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    quarters: Annotated[int, typer.Option("-q", "--quarters", help="Number of quarters to show")] = 8,
) -> None:
    """Display stored quarterly earnings trajectory."""
    with FlowStore() as store:
        results = store.get_quarterly_results(symbol.upper(), limit=quarters)

    display_quarterly_history(results, symbol.upper())


@app.command()
def peers(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    with_peers: Annotated[str | None, typer.Option("--with", help="Comma-separated peer symbols (e.g. TCS,INFY,WIPRO)")] = None,
) -> None:
    """Live fetch peer comparison."""
    client = FundClient()

    # Determine peer list
    if with_peers:
        peer_symbols = [s.strip().upper() for s in with_peers.split(",")]
    else:
        # Auto-detect: get sector from yfinance, find watchlist stocks in same sector
        try:
            snap = client.get_live_snapshot(symbol.upper())
        except YFinanceError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)

        if not snap.sector:
            console.print("[yellow]Cannot detect sector. Use --with to specify peers explicitly.[/]")
            raise typer.Exit(1)

        with FlowStore() as store:
            watchlist = store.get_watchlist()

        # Check each watchlist stock for same sector
        peer_symbols = []
        for w in watchlist:
            if w.symbol == symbol.upper():
                continue
            try:
                ws = client.get_live_snapshot(w.symbol)
                if ws.sector == snap.sector:
                    peer_symbols.append(w.symbol)
                time.sleep(0.5)
            except YFinanceError:
                continue

        if not peer_symbols:
            console.print(f"[yellow]No watchlist peers found in sector '{snap.sector}'. Use --with to specify.[/]")
            raise typer.Exit(1)

    # Always include the target symbol first
    all_symbols = [symbol.upper()] + [s for s in peer_symbols if s != symbol.upper()]

    # Fetch snapshots
    snapshots = []
    for sym in all_symbols:
        try:
            snapshots.append(client.get_live_snapshot(sym))
            time.sleep(0.5)
        except YFinanceError as e:
            console.print(f"[yellow]Skipping {sym}: {e}[/]")

    if not snapshots:
        console.print("[red]No data fetched for any peer.[/]")
        raise typer.Exit(1)

    # Build ownership data from store
    ownership_data: dict[str, dict] = {}
    with FlowStore() as store:
        for sym in all_symbols:
            changes = store.get_shareholding_changes(sym)
            fii = next((c for c in changes if c.category == "FII"), None)
            mf = next((c for c in changes if c.category == "MF"), None)
            ownership_data[sym] = {
                "fii_pct": fii.curr_pct if fii else 0,
                "fii_change": fii.change_pct if fii else None,
                "mf_pct": mf.curr_pct if mf else 0,
                "mf_change": mf.change_pct if mf else None,
            }

    display_peer_comparison(snapshots, ownership_data)


@app.command()
def valuation(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    period: Annotated[str, typer.Option("--period", help="Period: 1y, 2y, 3y")] = "3y",
) -> None:
    """Display valuation bands from stored snapshots."""
    period_map = {"1y": 365, "2y": 730, "3y": 1095}
    days = period_map.get(period)
    if days is None:
        console.print(f"[red]Invalid period '{period}'. Use 1y, 2y, or 3y.[/]")
        raise typer.Exit(1)

    metrics = ["pe_trailing", "ev_ebitda", "pb_ratio"]
    bands = []

    with FlowStore() as store:
        for metric in metrics:
            band = store.get_valuation_band(symbol.upper(), metric, days)
            if band is not None:
                bands.append(band)

    display_valuation_band(bands)


@app.command()
def backfill(
    symbol: Annotated[str | None, typer.Option("-s", "--symbol", help="Backfill single stock")] = None,
    quarters_only: Annotated[bool, typer.Option("--quarters-only", help="Only fetch Screener.in quarterly data")] = False,
    valuation_only: Annotated[bool, typer.Option("--valuation-only", help="Only compute historical P/E")] = False,
) -> None:
    """Backfill 10yr historical data from Screener.in + yfinance.

    Downloads quarterly results (10Q) and annual EPS (10yr) from Screener.in,
    then computes historical weekly P/E from annual EPS + yfinance prices.
    """
    # Get symbols to backfill
    if symbol:
        symbols = [symbol.upper()]
    else:
        with FlowStore() as store:
            watchlist = store.get_watchlist()
        if not watchlist:
            console.print("[red]Watchlist is empty. Add stocks first: flowtrack holding add SYMBOL[/]")
            raise typer.Exit(1)
        symbols = [w.symbol for w in watchlist]

    client = FundClient()
    total_quarters = 0
    total_annual = 0
    total_ratios = 0
    total_pe_snapshots = 0
    errors: list[str] = []

    # Stream 1: Screener.in HTML + Excel → quarterly, annual, ratios
    if not valuation_only:
        console.print(f"\n[bold]Stream 1: Screener.in quarterly + annual + ratios[/]")
        try:
            with ScreenerClient() as sc:
                with Progress() as progress:
                    task = progress.add_task("Fetching from Screener.in", total=len(symbols))
                    annual_eps_cache: dict[str, list] = {}

                    for sym in symbols:
                        progress.update(task, description=f"[cyan]{sym}[/]")
                        try:
                            # 1. Fetch HTML page
                            html = sc.fetch_company_page(sym)

                            # 2. Parse quarterly from HTML (primary)
                            quarters = sc.parse_quarterly_from_html(sym, html)

                            # 3. Download Excel for annual financials (expense sub-items)
                            excel_bytes = sc.download_excel(sym)
                            annual = sc.parse_annual_eps(sym, excel_bytes)
                            annual_fin = sc.parse_annual_financials(sym, excel_bytes)

                            # 4. Parse ratios from HTML
                            ratios = sc.parse_ratios_from_html(sym, html)

                            # 5. Fallback: if HTML quarterly parsing failed, use Excel
                            if not quarters:
                                quarters = sc.parse_quarterly_results(sym, excel_bytes)

                            with FlowStore() as store:
                                if quarters:
                                    store.upsert_quarterly_results(quarters)
                                    total_quarters += len(quarters)
                                if annual_fin:
                                    store.upsert_annual_financials(annual_fin)
                                    total_annual += len(annual_fin)
                                if ratios:
                                    store.upsert_screener_ratios(ratios)
                                    total_ratios += len(ratios)

                                annual_eps_cache[sym] = annual

                        except ScreenerError as e:
                            errors.append(f"{sym}: {e}")

                        progress.advance(task)
                        time.sleep(3)  # Rate limit

        except ScreenerError as e:
            console.print(f"[red]Screener.in login failed: {e}[/]")
            raise typer.Exit(1)

        console.print(f"  Quarterly results: [green]{total_quarters}[/] records for {len(symbols)} stocks")
        console.print(f"  Annual financials: [green]{total_annual}[/] records")
        console.print(f"  Screener ratios: [green]{total_ratios}[/] records")
    else:
        # Still need annual EPS for P/E computation — load from Screener.in
        annual_eps_cache = {}
        try:
            with ScreenerClient() as sc:
                for sym in symbols:
                    try:
                        _, annual, _ = sc.fetch_all_with_annual(sym)
                        annual_eps_cache[sym] = annual
                    except ScreenerError as e:
                        errors.append(f"{sym}: {e}")
                    time.sleep(3)
        except ScreenerError as e:
            console.print(f"[red]Screener.in login failed: {e}[/]")
            raise typer.Exit(1)

    # Stream 2: Historical P/E from yfinance prices + annual EPS
    if not quarters_only:
        console.print(f"\n[bold]Stream 2: Historical P/E computation[/]")
        with Progress() as progress:
            task = progress.add_task("Computing historical P/E", total=len(symbols))

            for sym in symbols:
                progress.update(task, description=f"[cyan]{sym}[/]")
                annual = annual_eps_cache.get(sym, [])
                if not annual:
                    progress.advance(task)
                    continue

                try:
                    snapshots = client.compute_historical_pe(sym, annual)
                    if snapshots:
                        with FlowStore() as store:
                            store.upsert_valuation_snapshots(snapshots)
                        total_pe_snapshots += len(snapshots)
                except YFinanceError as e:
                    errors.append(f"{sym} (P/E): {e}")

                progress.advance(task)
                time.sleep(0.5)

        console.print(f"  P/E snapshots: [green]{total_pe_snapshots}[/] records")

    # Summary
    console.print(f"\n[bold]Backfill complete.[/]")
    if errors:
        console.print(f"[yellow]Errors ({len(errors)}):[/]")
        for e in errors:
            console.print(f"  [red]• {e}[/]")


def _resolve_screener_ids(
    sc: ScreenerClient, store: FlowStore, symbol: str
) -> tuple[str, str]:
    """Get (company_id, warehouse_id) from cache or fetch + cache."""
    cached = store.get_screener_ids(symbol)
    if cached:
        return cached
    company_id, warehouse_id = sc._get_both_ids(symbol)
    store.upsert_screener_ids(symbol, company_id, warehouse_id)
    return company_id, warehouse_id


@app.command()
def charts(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="Stock symbol")
    ],
    chart_type: Annotated[
        str,
        typer.Option(
            "-t",
            "--type",
            help="Chart type: price, pe, sales_margin, ev_ebitda, pbv, mcap_sales",
        ),
    ] = "pe",
) -> None:
    """Fetch and display Screener.in chart data."""
    symbol = symbol.upper()
    try:
        with ScreenerClient() as sc:
            with FlowStore() as store:
                company_id, _ = _resolve_screener_ids(sc, store, symbol)
                console.print(f"[dim]Fetching {chart_type} chart for {symbol}...[/]")
                data = sc.fetch_chart_data_by_type(company_id, chart_type)
                datasets = data.get("datasets", [])
                if not datasets:
                    console.print("[yellow]No chart data returned.[/]")
                    raise typer.Exit(1)
                count = store.upsert_chart_data(symbol, chart_type, datasets)
                console.print(f"[green]Stored {count} data points.[/]")

        # Display summary table
        from rich.table import Table

        table = Table(
            title=f"{symbol} — {chart_type} chart",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Metric", style="bold")
        table.add_column("Points", justify="right")
        table.add_column("Latest Date")
        table.add_column("Latest Value", justify="right")

        for ds in datasets:
            metric = ds.get("metric", ds.get("label", "?"))
            values = ds.get("values", [])
            if values:
                latest = values[-1]
                latest_date = str(latest[0])
                latest_val = f"{latest[1]:,.2f}" if latest[1] is not None else "—"
            else:
                latest_date = "—"
                latest_val = "—"
            table.add_row(metric, str(len(values)), latest_date, latest_val)

        console.print(table)

    except ScreenerError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def peer(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="Stock symbol")
    ],
) -> None:
    """Fetch and display peer comparison from Screener.in."""
    symbol = symbol.upper()
    try:
        with ScreenerClient() as sc:
            with FlowStore() as store:
                _, warehouse_id = _resolve_screener_ids(sc, store, symbol)
                console.print(f"[dim]Fetching peers for {symbol}...[/]")
                peers = sc.fetch_peers(warehouse_id)
                if not peers:
                    console.print("[yellow]No peer data returned.[/]")
                    raise typer.Exit(1)
                count = store.upsert_peers(symbol, peers)
                console.print(f"[green]Stored {count} peers.[/]")

        # Display table
        from rich.table import Table

        table = Table(
            title=f"{symbol} — Peer Comparison",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Name", style="bold", max_width=25)
        table.add_column("CMP", justify="right")
        table.add_column("P/E", justify="right")
        table.add_column("Mkt Cap (Cr)", justify="right")
        table.add_column("Div Yld %", justify="right")
        table.add_column("NP Qtr", justify="right")
        table.add_column("Qtr Profit Var %", justify="right")
        table.add_column("Sales Qtr", justify="right")
        table.add_column("ROCE %", justify="right")

        def _fv(val: object) -> str:
            if val is None or val == "":
                return "—"
            if isinstance(val, float):
                return f"{val:,.1f}"
            return str(val)

        for p in peers:
            name = p.get("name", p.get("sno", "?"))
            table.add_row(
                str(name),
                _fv(p.get("cmp") or p.get("cmp_rs")),
                _fv(p.get("pe") or p.get("p_e")),
                _fv(p.get("market_cap") or p.get("market_cap_cr")),
                _fv(p.get("div_yield") or p.get("div_yld_pct")),
                _fv(p.get("np_qtr") or p.get("np_qtr_cr")),
                _fv(p.get("qtr_profit_var") or p.get("qtr_profit_var_pct")),
                _fv(p.get("sales_qtr") or p.get("sales_qtr_cr")),
                _fv(p.get("roce") or p.get("roce_pct")),
            )

        console.print(table)

    except ScreenerError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)


@app.command()
def schedules(
    symbol: Annotated[
        str, typer.Option("-s", "--symbol", help="Stock symbol")
    ],
    section: Annotated[
        str,
        typer.Option(
            "--section",
            help="Section: quarters, profit-loss, balance-sheet, cash-flow",
        ),
    ] = "profit-loss",
    parent: Annotated[
        str,
        typer.Option(
            "--parent",
            help="Parent line item (e.g. Sales, Expenses, Borrowings)",
        ),
    ] = "Sales",
) -> None:
    """Fetch and display schedule breakdowns from Screener.in."""
    symbol = symbol.upper()
    try:
        with ScreenerClient() as sc:
            with FlowStore() as store:
                company_id, _ = _resolve_screener_ids(sc, store, symbol)
                console.print(f"[dim]Fetching {section}/{parent} schedule for {symbol}...[/]")
                data = sc.fetch_schedules(company_id, section, parent)
                if not data:
                    console.print("[yellow]No schedule data returned.[/]")
                    raise typer.Exit(1)
                count = store.upsert_schedules(symbol, section, parent, data)
                console.print(f"[green]Stored {count} schedule data points.[/]")

        # Display table
        from rich.table import Table

        # Collect all periods from sub-items
        all_periods: list[str] = []
        for sub_item, periods in data.items():
            if isinstance(periods, dict):
                for p in periods:
                    if p not in all_periods:
                        all_periods.append(p)

        # Show last 8 periods
        display_periods = all_periods[-8:] if len(all_periods) > 8 else all_periods

        table = Table(
            title=f"{symbol} — {section} / {parent}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Sub-item", style="bold", max_width=30)
        for p in display_periods:
            table.add_column(p, justify="right")

        for sub_item, periods in data.items():
            if not isinstance(periods, dict):
                continue
            row = [sub_item]
            for p in display_periods:
                val = periods.get(p)
                if val is None:
                    row.append("—")
                else:
                    try:
                        row.append(f"{float(str(val).replace(',', '').replace('%', '')):,.1f}")
                    except (ValueError, TypeError):
                        row.append(str(val))
            table.add_row(*row)

        console.print(table)

    except ScreenerError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)
