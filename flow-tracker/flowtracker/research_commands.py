"""Research report CLI commands."""

from __future__ import annotations

import subprocess
import sys
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="research",
    help="Generate deep-dive research reports",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fundamentals(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Skip Screener/yfinance fetch, use cached DB data")] = False,
) -> None:
    """Generate a fundamentals HTML report for a stock.

    Pulls data from the store (quarterly, annual, ratios, valuation),
    renders a Jinja2 template, and opens the report in the browser.

    Use --skip-fetch to generate from cached data without re-fetching.
    """
    symbol = symbol.upper()

    # Step 1: Optionally fetch fresh data
    if not skip_fetch:
        console.print(f"\n[bold]Fetching data for {symbol}...[/]")
        try:
            from flowtracker.screener_client import ScreenerClient, ScreenerError
            from flowtracker.store import FlowStore

            with ScreenerClient() as sc:
                console.print(f"  Fetching from Screener.in...")
                html = sc.fetch_company_page(symbol)
                quarters = sc.parse_quarterly_from_html(symbol, html)
                ratios = sc.parse_ratios_from_html(symbol, html)
                excel_bytes = sc.download_excel(symbol)
                annual_fin = sc.parse_annual_financials(symbol, excel_bytes)
                annual_eps = sc.parse_annual_eps(symbol, excel_bytes)

                if not quarters:
                    quarters = sc.parse_quarterly_results(symbol, excel_bytes)

                with FlowStore() as store:
                    if quarters:
                        store.upsert_quarterly_results(quarters)
                        console.print(f"  Quarterly: [green]{len(quarters)}[/] records")
                    if annual_fin:
                        store.upsert_annual_financials(annual_fin)
                        console.print(f"  Annual: [green]{len(annual_fin)}[/] records")
                    if ratios:
                        store.upsert_screener_ratios(ratios)
                        console.print(f"  Ratios: [green]{len(ratios)}[/] records")

                # Historical P/E
                if annual_eps:
                    from flowtracker.fund_client import FundClient
                    client = FundClient()
                    snapshots = client.compute_historical_pe(symbol, annual_eps)
                    if snapshots:
                        with FlowStore() as store:
                            store.upsert_valuation_snapshots(snapshots)
                        console.print(f"  P/E snapshots: [green]{len(snapshots)}[/] records")

        except Exception as e:
            console.print(f"[yellow]Fetch warning: {e}[/]")
            console.print("[yellow]Continuing with cached data...[/]")

    # Step 2: Collect data from store
    console.print(f"\n[bold]Collecting data from store...[/]")
    from flowtracker.research.data_collector import collect_fundamentals_data
    data = collect_fundamentals_data(symbol)
    console.print(f"  PE history: {len(data.get('pe_history', []))} points")
    console.print(f"  Quarterly: {len(data.get('quarterly_results', []))} records")
    console.print(f"  Annual: {len(data.get('annual_financials', []))} records")
    console.print(f"  Ratios: {len(data.get('screener_ratios', []))} records")

    # Step 3: Render template
    console.print(f"\n[bold]Rendering report...[/]")
    from flowtracker.research.fundamentals import render_fundamentals_report
    output_path = render_fundamentals_report(symbol, data)
    console.print(f"  Written to: [cyan]{output_path}[/]")

    # Step 4: Open in browser
    subprocess.run(["open", str(output_path)], check=False)
    console.print(f"\n[bold green]Done.[/] Report opened in browser.")
