"""Research report CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
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


@app.command()
def thesis(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
    no_agent: Annotated[bool, typer.Option("--no-agent", help="Skip agent, use data-only report (fallback to fundamentals)")] = False,
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Skip data refresh, use cached DB data")] = False,
    model: Annotated[str | None, typer.Option("--model", help="Claude model override")] = None,
) -> None:
    """Generate an AI-powered equity research thesis.

    Uses Claude as a multi-turn research agent with access to all FlowTracker data.
    The agent queries data, cross-references signals, and produces a Markdown report.

    Use --no-agent to fall back to the data-only HTML fundamentals report.
    Use --skip-fetch to skip refreshing data from live sources.
    """
    symbol = symbol.upper()

    if no_agent:
        console.print("[yellow]--no-agent: falling back to fundamentals report[/]")
        fundamentals(symbol=symbol)
        return

    if not skip_fetch:
        console.print(f"\n[bold]Refreshing data for {symbol}...[/]")
        from flowtracker.research.refresh import refresh_for_research
        summary = refresh_for_research(symbol, console)
        total = sum(summary.values())
        console.print(f"\n[dim]Refresh complete: {total} total records across {len(summary)} sources[/]")

    console.print(f"\n[bold]Generating research thesis for {symbol}...[/]")
    console.print("[dim]Agent will query data, analyze, and produce a Markdown report.[/]")
    console.print("[dim]This may take 1-3 minutes.[/]\n")

    try:
        from flowtracker.research.agent import generate_thesis
        output_path = generate_thesis(symbol, model=model)
        console.print(f"\n[bold green]Done.[/] Report: [cyan]{output_path}[/]")

        reports_path = Path(__file__).parent.parent / "reports" / f"{symbol.lower()}-thesis.md"
        if reports_path.exists():
            console.print(f"  Also: [cyan]{reports_path}[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


# All available tool names for the data command
_DATA_TOOLS = [
    "company_info", "quarterly_results", "annual_financials", "screener_ratios",
    "valuation_snapshot", "valuation_band", "pe_history",
    "shareholding", "shareholding_changes", "insider_transactions",
    "bulk_block_deals", "mf_holdings", "delivery_trend", "promoter_pledge",
    "consensus_estimate", "earnings_surprises",
    "macro_snapshot", "fii_dii_streak", "fii_dii_flows",
    "chart_data", "peer_comparison", "shareholder_detail", "expense_breakdown",
    "recent_filings", "composite_score",
]


@app.command()
def data(
    tool_name: Annotated[str, typer.Argument(help=f"Tool to query: {', '.join(_DATA_TOOLS)}")],
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")] = "",
    raw: Annotated[bool, typer.Option("--raw", help="Print raw JSON instead of pretty")] = False,
) -> None:
    """Query any research data tool directly. Prints JSON output.

    Examples:
        flowtrack research data shareholding_changes -s INDIAMART
        flowtrack research data macro_snapshot
        flowtrack research data composite_score -s RELIANCE
    """
    if tool_name not in _DATA_TOOLS:
        console.print(f"[red]Unknown tool: {tool_name}[/]")
        console.print(f"Available: {', '.join(_DATA_TOOLS)}")
        raise typer.Exit(1)

    symbol = symbol.upper() if symbol else ""

    no_symbol = {"macro_snapshot", "fii_dii_streak", "fii_dii_flows"}
    if tool_name not in no_symbol and not symbol:
        console.print("[red]--symbol / -s is required for this tool[/]")
        raise typer.Exit(1)

    from flowtracker.research.data_api import ResearchDataAPI

    method_map = {
        "company_info": lambda api: api.get_company_info(symbol),
        "quarterly_results": lambda api: api.get_quarterly_results(symbol),
        "annual_financials": lambda api: api.get_annual_financials(symbol),
        "screener_ratios": lambda api: api.get_screener_ratios(symbol),
        "valuation_snapshot": lambda api: api.get_valuation_snapshot(symbol),
        "valuation_band": lambda api: api.get_valuation_band(symbol),
        "pe_history": lambda api: api.get_pe_history(symbol),
        "shareholding": lambda api: api.get_shareholding(symbol),
        "shareholding_changes": lambda api: api.get_shareholding_changes(symbol),
        "insider_transactions": lambda api: api.get_insider_transactions(symbol),
        "bulk_block_deals": lambda api: api.get_bulk_block_deals(symbol),
        "mf_holdings": lambda api: api.get_mf_holdings(symbol),
        "delivery_trend": lambda api: api.get_delivery_trend(symbol),
        "promoter_pledge": lambda api: api.get_promoter_pledge(symbol),
        "consensus_estimate": lambda api: api.get_consensus_estimate(symbol),
        "earnings_surprises": lambda api: api.get_earnings_surprises(symbol),
        "macro_snapshot": lambda api: api.get_macro_snapshot(),
        "fii_dii_streak": lambda api: api.get_fii_dii_streak(),
        "fii_dii_flows": lambda api: api.get_fii_dii_flows(),
        "chart_data": lambda api: api.get_chart_data(symbol, "pe"),
        "peer_comparison": lambda api: api.get_peer_comparison(symbol),
        "shareholder_detail": lambda api: api.get_shareholder_detail(symbol),
        "expense_breakdown": lambda api: api.get_expense_breakdown(symbol),
        "recent_filings": lambda api: api.get_recent_filings(symbol),
        "composite_score": lambda api: _get_score(symbol),
    }

    with ResearchDataAPI() as api:
        result = method_map[tool_name](api)

    if raw:
        print(json.dumps(result, default=str))
    else:
        console.print_json(json.dumps(result, default=str))


def _get_score(symbol: str) -> dict:
    """Get composite score as a dict."""
    from flowtracker.screener_engine import ScreenerEngine
    from flowtracker.store import FlowStore

    with FlowStore() as store:
        engine = ScreenerEngine(store)
        score = engine.score_stock(symbol)
    if not score:
        return {"error": "No data"}
    return {
        "symbol": score.symbol,
        "composite_score": score.composite_score,
        "factors": [
            {"factor": f.factor, "score": f.score, "raw_value": f.raw_value, "detail": f.detail}
            for f in score.factors
        ],
    }
