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
) -> None:
    """Generate a fundamentals HTML report for a stock.

    Fetches fresh data from Screener.in, yfinance, and NSE,
    then renders a Jinja2 template and opens the report in the browser.
    """
    symbol = symbol.upper()
    doc_links: dict = {}
    screener_charts: dict = {}
    screener_growth: dict = {}
    screener_shareholders: dict = {}

    # Step 1: Fetch fresh data
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

            # Parse document URLs (concalls, annual reports)
            doc_links = sc.parse_documents_from_html(html)

            # Fetch chart data (PE, price+DMA+volume) from Screener API
            screener_charts = sc.fetch_chart_data(symbol, html)
            if screener_charts:
                console.print(f"  Charts: [green]{len(screener_charts)}[/] datasets from Screener API")

            # Fetch growth rates from Screener HTML
            screener_growth = sc.parse_growth_rates_from_html(html)
            if screener_growth:
                console.print(f"  Growth rates: [green]{len(screener_growth)}[/] metrics from Screener")

            # Fetch detailed shareholder data (MF schemes, FIIs) from Screener API
            screener_shareholders = sc.fetch_shareholder_details(html)
            if screener_shareholders:
                dii_count = len(screener_shareholders.get("dii", []))
                fii_count = len(screener_shareholders.get("fii", []))
                console.print(f"  Shareholders: [green]{dii_count}[/] MF schemes, [green]{fii_count}[/] FIIs from Screener")

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

    except Exception as e:
        console.print(f"[yellow]Fetch warning: {e}[/]")
        console.print("[yellow]Continuing with cached data...[/]")

    # Shareholding from NSE (separate try — NSE can be flaky)
    try:
        from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError
        from flowtracker.store import FlowStore

        console.print(f"  Fetching shareholding from NSE...")
        with NSEHoldingClient() as nse:
            records, pledges = nse.fetch_latest_quarters(symbol, num_quarters=8)
            if records:
                with FlowStore() as store:
                    store.upsert_shareholding(records)
                    if pledges:
                        store.upsert_promoter_pledges(pledges)
                quarters_fetched = len({r.quarter_end for r in records})
                console.print(f"  Shareholding: [green]{quarters_fetched}[/] quarters, {len(records)} records")
            else:
                console.print(f"  [yellow]No shareholding data from NSE[/]")
    except Exception as e:
        console.print(f"[yellow]Shareholding fetch warning: {e}[/]")

    # Step 2: Collect data from store
    console.print(f"\n[bold]Collecting data from store...[/]")
    from flowtracker.research.data_collector import collect_fundamentals_data
    data = collect_fundamentals_data(symbol)
    console.print(f"  Quarterly: {len(data.get('quarterly_results', []))} records")
    console.print(f"  Annual: {len(data.get('annual_financials', []))} records")
    console.print(f"  Ratios: {len(data.get('screener_ratios', []))} records")
    console.print(f"  Shareholding: {len(data.get('shareholding_history', []))} quarters")
    console.print(f"  MF holdings: {len(data.get('mf_holdings', []))} schemes")

    # Add document links, chart data, and growth rates, then apply Screener overrides
    data["document_links"] = doc_links
    data["screener_charts"] = screener_charts
    if screener_growth:
        data["growth_rates"] = screener_growth  # override computed rates

    if screener_shareholders:
        data["screener_shareholders"] = screener_shareholders

    from flowtracker.research.data_collector import apply_screener_charts
    apply_screener_charts(data)

    # Step 3: Render template
    console.print(f"\n[bold]Rendering report...[/]")
    from flowtracker.research.fundamentals import render_fundamentals_report
    output_path = render_fundamentals_report(symbol, data)
    console.print(f"  Written to: [cyan]{output_path}[/]")

    # Step 4: Open in browser
    subprocess.run(["open", str(output_path)], check=False)
    console.print(f"\n[bold green]Done.[/] Report opened in browser.")
