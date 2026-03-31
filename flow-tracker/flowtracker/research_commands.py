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
def business(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Skip data refresh, use cached DB data")] = False,
    model: Annotated[str | None, typer.Option("--model", help="Claude model override")] = None,
) -> None:
    """Generate a business profile — what the company does, how it makes money.

    Lightweight qualitative analysis. Skips financial pipeline entirely.
    Uses Screener about text + web search to build a business profile.
    """
    symbol = symbol.upper()

    if not skip_fetch:
        console.print(f"\n[bold]Refreshing data for {symbol}...[/]")
        from flowtracker.research.refresh import refresh_for_research
        summary = refresh_for_research(symbol, console)
        total = sum(summary.values())
        console.print(f"\n[dim]Refresh complete: {total} records across {len(summary)} sources[/]")

    console.print(f"\n[bold]Generating business profile for {symbol}...[/]")
    console.print("[dim]Agent will research the business and produce a profile.[/]\n")

    try:
        from flowtracker.research.agent import generate_business_profile
        output_path = generate_business_profile(symbol, model=model)
        console.print(f"\n[bold green]Done.[/] Report: [cyan]{output_path}[/]")

        # Also show vault path
        from pathlib import Path as _P
        vault_md = _P.home() / "vault" / "stocks" / symbol / "profile.md"
        if vault_md.exists():
            console.print(f"  Markdown: [cyan]{vault_md}[/]")

        # Open HTML in browser
        subprocess.run(["open", str(output_path)], check=False)
        console.print(f"\n[bold green]Report opened in browser.[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


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
    "company_info", "company_profile", "company_documents",
    "quarterly_results", "annual_financials", "screener_ratios",
    "valuation_snapshot", "valuation_band", "pe_history",
    "shareholding", "shareholding_changes", "insider_transactions",
    "bulk_block_deals", "mf_holdings", "delivery_trend", "promoter_pledge",
    "consensus_estimate", "earnings_surprises",
    "macro_snapshot", "fii_dii_streak", "fii_dii_flows",
    "chart_data", "peer_comparison", "shareholder_detail", "expense_breakdown",
    "recent_filings", "composite_score",
    "dcf_valuation", "dcf_history", "technical_indicators",
    "dupont_decomposition", "key_metrics_history", "financial_growth_rates",
    "analyst_grades", "price_targets", "fair_value",
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
        "company_profile": lambda api: api.get_company_profile(symbol),
        "company_documents": lambda api: api.get_company_documents(symbol),
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
        "dcf_valuation": lambda api: api.get_dcf_valuation(symbol),
        "dcf_history": lambda api: api.get_dcf_history(symbol),
        "technical_indicators": lambda api: api.get_technical_indicators(symbol),
        "dupont_decomposition": lambda api: api.get_dupont_decomposition(symbol),
        "key_metrics_history": lambda api: api.get_key_metrics_history(symbol),
        "financial_growth_rates": lambda api: api.get_financial_growth_rates(symbol),
        "analyst_grades": lambda api: api.get_analyst_grades(symbol),
        "price_targets": lambda api: api.get_price_targets(symbol),
        "fair_value": lambda api: api.get_fair_value(symbol),
    }

    with ResearchDataAPI() as api:
        result = method_map[tool_name](api)

    if raw:
        print(json.dumps(result, default=str))
    else:
        console.print_json(json.dumps(result, default=str))


@app.command("thesis-check")
def thesis_check(
    symbol: Annotated[str, typer.Option("-s", "--symbol", help="Stock symbol")],
) -> None:
    """Quick condition check for a tracked stock's thesis.

    Reads the tracker file at ~/vault/stocks/{SYMBOL}/thesis-tracker.md,
    evaluates conditions against fresh data, and updates statuses.
    """
    symbol = symbol.upper()
    from flowtracker.research.thesis_tracker import (
        load_tracker, evaluate_conditions, update_tracker_file,
    )
    from flowtracker.store import FlowStore

    tracker = load_tracker(symbol)
    if not tracker:
        console.print(f"[yellow]No thesis tracker found for {symbol}.[/]")
        console.print(f"[dim]Expected: ~/vault/stocks/{symbol}/thesis-tracker.md[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Thesis Check — {symbol}[/]")
    if tracker.entry_price:
        console.print(f"[dim]Entry: ₹{tracker.entry_price:,.2f} on {tracker.entry_date or '?'}[/]")

    with FlowStore() as store:
        conditions = evaluate_conditions(tracker, store)

    update_tracker_file(tracker)

    from rich.table import Table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", width=8)
    table.add_column("Condition", min_width=30)
    table.add_column("Metric", width=35)
    table.add_column("Threshold", justify="right", width=12)

    for c in conditions:
        status_map = {
            "passing": "[green]✓ PASS[/]",
            "failing": "[red]✗ FAIL[/]",
            "stale": "[yellow]? STALE[/]",
            "pending": "[dim]· PEND[/]",
        }
        table.add_row(
            status_map.get(c.status, c.status),
            c.label,
            c.metric,
            f"{c.operator} {c.threshold}",
        )

    console.print(table)

    passing = sum(1 for c in conditions if c.status == "passing")
    total = len(conditions)
    color = "green" if passing == total else "yellow" if passing > total // 2 else "red"
    console.print(f"\n[{color}]{passing}/{total} conditions passing[/{color}]")


@app.command("thesis-status")
def thesis_status() -> None:
    """Summary of all tracked stocks with condition status."""
    from flowtracker.research.thesis_tracker import get_all_trackers, evaluate_conditions
    from flowtracker.store import FlowStore

    trackers = get_all_trackers()
    if not trackers:
        console.print("[yellow]No thesis trackers found in ~/vault/stocks/.[/]")
        raise typer.Exit(1)

    from rich.table import Table
    table = Table(title="Thesis Tracker Status", show_header=True, header_style="bold cyan")
    table.add_column("Symbol", width=12)
    table.add_column("Entry ₹", justify="right", width=10)
    table.add_column("Conditions", width=15)
    table.add_column("Status", width=10)

    with FlowStore() as store:
        for tracker in trackers:
            evaluate_conditions(tracker, store)

            passing = sum(1 for c in tracker.conditions if c.status == "passing")
            failing = sum(1 for c in tracker.conditions if c.status == "failing")
            stale = sum(1 for c in tracker.conditions if c.status == "stale")
            total = len(tracker.conditions)

            cond_str = f"[green]{passing}✓[/] [red]{failing}✗[/]"
            if stale:
                cond_str += f" [yellow]{stale}?[/]"

            if passing == total:
                status = "[green]STRONG[/]"
            elif passing > total // 2:
                status = "[yellow]MIXED[/]"
            else:
                status = "[red]WEAK[/]"

            table.add_row(
                tracker.symbol,
                f"{tracker.entry_price:,.2f}" if tracker.entry_price else "—",
                cond_str,
                status,
            )

    console.print(table)


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
