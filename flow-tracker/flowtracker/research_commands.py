"""Research report CLI commands."""

from __future__ import annotations

import asyncio
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
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    no_agent: Annotated[bool, typer.Option("--no-agent", help="Skip agent, use data-only report (fallback to fundamentals)")] = False,
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Skip data refresh")] = False,
    skip_verify: Annotated[bool, typer.Option("--skip-verify", help="Skip verification step")] = False,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Override model for all agents")] = None,
    verify_model: Annotated[str | None, typer.Option("--verify-model", help="Override model for verifiers")] = None,
) -> None:
    """Generate comprehensive multi-agent equity research thesis.

    Runs 7 specialist agents in parallel (business, financials, ownership,
    valuation, risk, technical, sector), verifies their reports, then synthesizes
    everything into a final research document.

    Use --no-agent to fall back to the data-only HTML fundamentals report.
    Use --skip-fetch to skip refreshing data from live sources.
    Use --skip-verify to skip the verification step.
    """
    import logging
    import webbrowser

    # Ensure agent logs are visible in CLI output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from flowtracker.research.agent import format_cost_summary, run_all_agents, run_synthesis_agent
    from flowtracker.research.assembly import assemble_final_report

    symbol = symbol.upper()

    if no_agent:
        console.print("[yellow]--no-agent: falling back to fundamentals report[/]")
        fundamentals(symbol=symbol)
        return

    # Phase 0: Data refresh
    if not skip_fetch:
        console.print(f"\n[bold]Phase 0: Data Refresh for {symbol}[/]")
        from flowtracker.research.refresh import refresh_for_research
        refresh_for_research(symbol, console)

        console.print("\n[bold]Refreshing peer data...[/]")
        from flowtracker.research.peer_refresh import refresh_peers
        refresh_peers(symbol, console)

    # Phase 0b: Concall extraction (auto-run if stale or missing)
    from pathlib import Path
    from datetime import date, timedelta
    extraction_path = Path.home() / "vault" / "stocks" / symbol / "fundamentals" / "concall_extraction_v2.json"
    extraction_fresh = False
    if extraction_path.exists():
        import os
        mtime = date.fromtimestamp(os.path.getmtime(extraction_path))
        extraction_fresh = (date.today() - mtime) < timedelta(days=30)

    if not extraction_fresh:
        console.print(f"\n[bold]Phase 0b: Concall Pipeline[/]")

        # Step 1: Fetch + download filing PDFs from BSE
        if not skip_fetch:
            try:
                from flowtracker.filing_client import FilingClient
                fc = FilingClient()
                filings = fc.fetch_research_filings(symbol)
                downloaded = 0
                for filing in filings:
                    path = fc.download_filing(filing)
                    if path:
                        downloaded += 1
                console.print(f"  [green]✓[/] Filings: {len(filings)} found, {downloaded} PDFs downloaded")
            except Exception as e:
                console.print(f"  [yellow]⚠[/] Filing download: {e}")

        # Step 2: Check for concall PDFs now that we've downloaded
        from flowtracker.research.concall_extractor import _find_concall_pdfs
        concall_pdfs = _find_concall_pdfs(symbol, quarters=4)
        if concall_pdfs:
            console.print(f"  Found {len(concall_pdfs)} concall PDFs")
            console.print("  Extracting concall insights (this costs ~$0.20-0.40)...")
            try:
                from flowtracker.research.concall_extractor import extract_concalls
                result = asyncio.run(extract_concalls(symbol, quarters=4))
                console.print(f"  [green]✓[/] Extracted {result.get('quarters_analyzed', 0)} quarters")
            except Exception as e:
                console.print(f"  [yellow]⚠[/] Concall extraction failed: {e}")
                console.print("  [dim]Agents will work without concall data[/]")
        else:
            console.print(f"  [dim]No concall PDFs found for {symbol} after download. Agents will work without concall data.[/]")
    else:
        console.print(f"\n[dim]Concall extraction is fresh (<30 days). Skipping.[/]")

    # Phase 1 + 1.5: Specialist agents (parallel) + Verification
    console.print(f"\n[bold]Phase 1: Running 7 specialist agents for {symbol}...[/]")
    console.print("Agents: business, financials, ownership, valuation, risk, technical, sector")
    console.print("This may take 3-8 minutes.\n")

    envelopes = asyncio.run(run_all_agents(
        symbol=symbol,
        model=model,
        verify=not skip_verify,
        verify_model=verify_model,
    ))

    if not envelopes:
        console.print("[red]All agents failed. No reports generated.[/]")
        raise typer.Exit(1)

    console.print(f"\n[green]✓[/] {len(envelopes)} specialist reports complete")

    # Phase 2: Synthesis
    console.print(f"\n[bold]Phase 2: Synthesis agent[/]")
    synthesis = asyncio.run(run_synthesis_agent(symbol, model))
    console.print("[green]✓[/] Synthesis complete")

    # Phase 3: Assembly
    console.print(f"\n[bold]Phase 3: Assembling final report[/]")
    md_path, html_path = assemble_final_report(symbol, envelopes, synthesis)
    console.print(f"[green]✓[/] Report assembled")

    # Cost summary
    all_envelopes = {**envelopes, "synthesis": synthesis}
    console.print(format_cost_summary(all_envelopes))

    # Output paths
    console.print(f"\n[bold]Output:[/]")
    console.print(f"  Markdown: {md_path}")
    console.print(f"  HTML:     {html_path}")
    console.print(f"  Reports:  ~/vault/stocks/{symbol}/reports/")
    console.print(f"  Briefings: ~/vault/stocks/{symbol}/briefings/")

    # Open HTML in browser
    webbrowser.open(f"file://{html_path}")


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
    "upcoming_catalysts",
    "sector_overview", "sector_flows", "sector_valuations",
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
        "upcoming_catalysts": lambda api: api.get_upcoming_catalysts(symbol),
        "sector_overview": lambda api: api.get_sector_overview_metrics(symbol),
        "sector_flows": lambda api: api.get_sector_flows(symbol),
        "sector_valuations": lambda api: api.get_sector_valuations(symbol),
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


@app.command()
def compare(
    symbols: Annotated[list[str], typer.Argument(help="2-5 stock symbols to compare")],
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Use cached data only")] = False,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Override model")] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-run agents even if briefings exist")] = False,
) -> None:
    """Compare 2-5 stocks side-by-side with AI-generated comparative analysis."""
    import webbrowser

    if len(symbols) < 2:
        console.print("[red]Need at least 2 symbols to compare[/red]")
        raise typer.Exit(1)
    if len(symbols) > 5:
        console.print("[red]Maximum 5 symbols for comparison[/red]")
        raise typer.Exit(1)

    symbols = [s.upper() for s in symbols]
    console.print(f"[bold]Comparing: {' vs '.join(symbols)}[/bold]")

    from flowtracker.research.agent import run_comparison_agent

    envelope = asyncio.run(run_comparison_agent(
        symbols=symbols,
        model=model,
        skip_fetch=skip_fetch,
        force=force,
    ))

    from flowtracker.research.assembly import assemble_comparison_report

    html_path, md_path = assemble_comparison_report(symbols, envelope)

    console.print(f"\n[green]Report saved:[/green] {html_path}")

    webbrowser.open(f"file://{html_path}")


VALID_AGENTS = {"business", "financials", "ownership", "valuation", "risk", "technical", "sector"}
VALID_AGENTS_WITH_SYNTHESIS = VALID_AGENTS | {"synthesis"}


@app.command("run")
def run_agent(
    agents: Annotated[str, typer.Argument(help="Agents to run: business,risk,synthesis (comma-separated) or 'all'")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol (e.g. INDIAMART)")],
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch", help="Skip data refresh")] = False,
    verify: Annotated[bool, typer.Option("--verify", help="Run verification after agents")] = False,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Override model for agent")] = None,
    assemble: Annotated[bool, typer.Option("--assemble", help="Assemble final report from all existing briefings after running")] = False,
) -> None:
    """Run specialist research agents on a stock.

    Run one or more agents by name (comma-separated), then optionally
    synthesize and assemble using existing briefings for the rest.

    Examples:
      flowtrack research run business -s HDFCBANK          # just business
      flowtrack research run business,risk -s HDFCBANK     # re-run two agents
      flowtrack research run synthesis -s HDFCBANK         # just re-synthesize from existing briefings
      flowtrack research run business,risk,synthesis -s HDFCBANK --assemble  # re-run two + synthesize + assemble HTML
    """
    symbol = symbol.upper()
    agent_list = [a.strip().lower() for a in agents.split(",")]

    # Validate
    for agent in agent_list:
        if agent not in VALID_AGENTS_WITH_SYNTHESIS:
            console.print(f"[red]Unknown agent: {agent}[/]")
            console.print(f"Valid agents: {', '.join(sorted(VALID_AGENTS_WITH_SYNTHESIS))}")
            raise typer.Exit(1)

    specialist_agents = [a for a in agent_list if a in VALID_AGENTS]
    run_synthesis = "synthesis" in agent_list

    # Show what exists in vault
    from flowtracker.research.briefing import load_all_briefings
    existing = load_all_briefings(symbol)
    if existing:
        console.print(f"\n[dim]Existing briefings in vault: {', '.join(sorted(existing.keys()))}[/]")
        reusing = set(existing.keys()) - set(specialist_agents) - {"synthesis"}
        if reusing:
            console.print(f"[dim]Will reuse: {', '.join(sorted(reusing))}[/]")

    # Data refresh (only if running specialists, not for synthesis-only)
    if specialist_agents and not skip_fetch:
        console.print(f"\n[bold]Refreshing data for {symbol}...[/]")
        needs_full = any(a != "business" for a in specialist_agents)
        if needs_full:
            from flowtracker.research.refresh import refresh_for_research
            summary = refresh_for_research(symbol, console)
        else:
            from flowtracker.research.refresh import refresh_for_business
            summary = refresh_for_business(symbol, console)
        total = sum(summary.values())
        console.print(f"[dim]Refresh complete: {total} records across {len(summary)} sources[/]")

        from flowtracker.research.peer_refresh import refresh_peers
        console.print(f"\n[bold]Refreshing peer data...[/]")
        refresh_peers(symbol, console)

    # Run specialist agents
    total_cost = 0.0
    for agent in specialist_agents:
        console.print(f"\n[bold]Running {agent} agent for {symbol}...[/]")

        try:
            from flowtracker.research.agent import run_single_agent
            envelope = asyncio.run(run_single_agent(agent, symbol, model=model))
        except Exception as e:
            console.print(f"[red]{agent} agent error: {e}[/]")
            continue

        cost = envelope.cost
        total_cost += cost.total_cost_usd
        duration_m = int(cost.duration_seconds) // 60
        duration_s = int(cost.duration_seconds) % 60
        console.print(f"  [green]✓[/] {agent}: {len(envelope.report):,} chars, ${cost.total_cost_usd:.2f}, {duration_m}m {duration_s:02d}s")

    # Run synthesis
    if run_synthesis:
        console.print(f"\n[bold]Running synthesis agent for {symbol}...[/]")
        try:
            from flowtracker.research.agent import run_synthesis_agent
            synthesis = asyncio.run(run_synthesis_agent(symbol, model))
            total_cost += synthesis.cost.total_cost_usd
            console.print(f"  [green]✓[/] synthesis: {len(synthesis.report):,} chars, ${synthesis.cost.total_cost_usd:.2f}")
        except Exception as e:
            console.print(f"[red]Synthesis error: {e}[/]")

    # Assemble final report if requested
    if assemble:
        console.print(f"\n[bold]Assembling final report...[/]")
        try:
            from flowtracker.research.agent import run_synthesis_agent
            from flowtracker.research.assembly import assemble_final_report
            from flowtracker.research.briefing import load_envelope

            # Load all specialist envelopes (mix of fresh + existing)
            specialist_envelopes = {}
            for name in VALID_AGENTS:
                env = load_envelope(symbol, name)
                if env and env.report:
                    specialist_envelopes[name] = env

            # Load synthesis (just ran or from vault)
            syn_env = load_envelope(symbol, "synthesis")
            if syn_env and syn_env.report:
                md_path, html_path = assemble_final_report(symbol, specialist_envelopes, syn_env)
                console.print(f"  [green]✓[/] Assembled: {html_path}")

                import webbrowser
                webbrowser.open(f"file://{html_path}")
            else:
                console.print("[yellow]No synthesis report found — run synthesis first[/]")
        except Exception as e:
            console.print(f"[red]Assembly error: {e}[/]")

    console.print(f"\n[bold]Total cost: ${total_cost:.2f}[/]")
    console.print(f"[dim]Reports: ~/vault/stocks/{symbol}/reports/[/]")
    console.print(f"[dim]Briefings: ~/vault/stocks/{symbol}/briefings/[/]")


@app.command()
def verify(
    agent: Annotated[str, typer.Argument(help="Agent to verify: business|financials|ownership|valuation|risk|technical")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    model: Annotated[str | None, typer.Option("--model", "-m", help="Override model for verifier")] = None,
) -> None:
    """Verify an existing specialist report (checks data accuracy)."""
    console.print("[yellow]Verification not yet implemented — coming in T16[/yellow]")


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
