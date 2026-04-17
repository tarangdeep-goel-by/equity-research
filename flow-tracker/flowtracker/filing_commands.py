"""CLI commands for corporate filings — fetch, download, browse."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from flowtracker.filing_client import FilingClient
from flowtracker.store import FlowStore

app = typer.Typer(
    name="filings",
    help="Corporate filings — investor presentations, concalls, annual reports from BSE/NSE",
    no_args_is_help=True,
)
console = Console()


@app.command()
def fetch(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    years: Annotated[int, typer.Option("-y", "--years", help="Years of history")] = 3,
    download: Annotated[bool, typer.Option("--download", help="Also download PDFs")] = False,
) -> None:
    """Fetch corporate filings from BSE and optionally download PDFs."""
    from_date = date.today().replace(year=date.today().year - years)

    with FilingClient() as client, FlowStore() as store:
        console.print(f"[dim]Fetching filings for {symbol.upper()} from BSE...[/]")
        filings = client.fetch_research_filings(symbol.upper(), from_date=from_date)

        if not filings:
            console.print(f"[yellow]No filings found for {symbol.upper()}[/]")
            raise typer.Exit(1)

        count = store.upsert_filings(filings)
        console.print(f"Found [green]{len(filings)}[/] research filings, stored {count}")

        if download:
            console.print(f"[dim]Downloading PDFs...[/]")
            downloaded = 0
            for f in filings:
                path = client.download_filing(f)
                if path:
                    store.update_filing_path(f.news_id, str(path))
                    downloaded += 1
            console.print(f"Downloaded [green]{downloaded}[/] PDFs")

    # Show summary
    _show_filing_summary(filings, symbol.upper())


@app.command()
def download(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
) -> None:
    """Download all PDFs for a stock's filings."""
    with FlowStore() as store:
        filings = store.get_filings(symbol.upper())

    if not filings:
        console.print(f"[yellow]No filings in DB for {symbol.upper()}. Run 'filings fetch' first.[/]")
        raise typer.Exit(1)

    with FilingClient() as client, FlowStore() as store:
        downloaded = 0
        skipped = 0
        for f in filings:
            if f.local_path and Path(f.local_path).exists():
                skipped += 1
                continue
            path = client.download_filing(f)
            if path:
                store.update_filing_path(f.news_id, str(path))
                downloaded += 1

        console.print(Panel(
            f"Downloaded {downloaded} new PDFs, skipped {skipped} (already on disk)",
            title=f"Filing Downloads — {symbol.upper()}",
            border_style="green",
        ))


@app.command(name="list")
def list_filings(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    category: Annotated[str | None, typer.Option("-c", "--category", help="Filter by category")] = None,
    limit: Annotated[int, typer.Option("-n", "--limit", help="Number to show")] = 30,
) -> None:
    """List stored filings for a stock."""
    with FlowStore() as store:
        filings = store.get_filings(symbol.upper(), category=category, limit=limit)

    if not filings:
        console.print(f"[yellow]No filings for {symbol.upper()}[/]")
        return

    table = Table(title=f"Corporate Filings — {symbol.upper()}", show_header=True, header_style="bold cyan")
    table.add_column("Date", width=12)
    table.add_column("Category", width=16)
    table.add_column("Subcategory", width=22)
    table.add_column("Headline", width=50)
    table.add_column("PDF", width=4)

    for f in filings:
        has_pdf = "[green]Y[/]" if f.local_path and Path(f.local_path).exists() else "[dim]N[/]"
        table.add_row(
            f.filing_date,
            f.category[:16],
            f.subcategory[:22],
            f.headline[:50],
            has_pdf,
        )

    console.print(table)


@app.command()
def annual_reports(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    download_flag: Annotated[bool, typer.Option("--download", help="Download the PDFs")] = False,
) -> None:
    """Fetch and optionally download annual reports from NSE."""
    with FilingClient() as client:
        console.print(f"[dim]Fetching annual reports for {symbol.upper()} from NSE...[/]")
        reports = client.fetch_annual_reports(symbol.upper())

        if not reports:
            console.print(f"[yellow]No annual reports found for {symbol.upper()}[/]")
            raise typer.Exit(1)

        table = Table(title=f"Annual Reports — {symbol.upper()}", show_header=True, header_style="bold cyan")
        table.add_column("Year", width=12)
        table.add_column("Company", width=30)
        table.add_column("URL", width=50)

        for r in reports:
            table.add_row(
                f"{r['from_year']}-{r['to_year']}",
                (r['company_name'] or '')[:30],
                (r['url'] or '')[:50],
            )

        console.print(table)

        if download_flag:
            for r in reports:
                url = r.get('url')
                if url:
                    fname = f"annual_report_{r['from_year']}_{r['to_year']}.pdf"
                    path = client.download_url(
                        url, symbol.upper(), "annual_reports", fname,
                    )
                    if path:
                        console.print(f"  [green]+[/] {path.name}")


@app.command()
def open_filing(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    index: Annotated[int, typer.Argument(help="Filing index (from 'filings list')")] = 1,
) -> None:
    """Open a downloaded filing PDF."""
    import subprocess

    with FlowStore() as store:
        filings = store.get_filings(symbol.upper(), limit=100)

    if not filings or index < 1 or index > len(filings):
        console.print(f"[yellow]Invalid index. Use 'filings list {symbol}' to see available filings.[/]")
        raise typer.Exit(1)

    filing = filings[index - 1]
    if filing.local_path and Path(filing.local_path).exists():
        subprocess.run(["open", filing.local_path])
        console.print(f"Opened: {filing.headline[:60]}")
    else:
        console.print(f"[yellow]PDF not downloaded. Run 'filings download {symbol}' first.[/]")


@app.command(name="extract")
def extract_concalls_cmd(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    quarters: Annotated[int, typer.Option("--quarters", "-q", help="Number of quarters to extract")] = 4,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Claude model to use")] = None,
) -> None:
    """Extract structured insights from concall PDFs using AI."""
    import asyncio

    from flowtracker.research.concall_extractor import extract_concalls
    from flowtracker.research.data_api import ResearchDataAPI

    # Look up industry for sector-specific KPI extraction
    industry = None
    try:
        with ResearchDataAPI() as api:
            industry = api._get_industry(symbol.upper())
            if industry == "Unknown":
                industry = None
    except Exception:
        pass

    result = asyncio.run(
        extract_concalls(symbol.upper(), quarters, model or "claude-sonnet-4-20250514", industry=industry)
    )

    console.print(f"[green]\u2713[/] Extracted {result['quarters_analyzed']} quarters for {symbol.upper()}")
    console.print(f"  Saved to: ~/vault/stocks/{symbol.upper()}/fundamentals/concall_extraction_v2.json")


@app.command(name="download-ar")
def download_ar_cmd(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    years: Annotated[int, typer.Option("--years", "-y", help="Number of recent fiscal years to download")] = 3,
) -> None:
    """Download annual report PDFs for the last N FYs to the vault.

    URLs come from company_documents (populated by Screener). PDFs land at
    ~/vault/stocks/{SYMBOL}/filings/FY??/annual_report.pdf.
    """
    from flowtracker.research.ar_downloader import ensure_annual_reports, list_ar_urls

    available = list_ar_urls(symbol.upper(), max_years=years)
    if not available:
        console.print(f"[yellow]No AR URLs tracked for {symbol.upper()}[/]")
        return
    console.print(f"Tracked AR URLs for {symbol.upper()}: {[a['fy_label'] for a in available]}")
    downloaded = ensure_annual_reports(symbol.upper(), max_years=years)
    console.print(f"[green]\u2713[/] Downloaded {downloaded} new AR PDF(s)")


@app.command(name="extract-ar")
def extract_ar_cmd(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    years: Annotated[int, typer.Option("--years", "-y", help="Number of recent fiscal years to extract")] = 2,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Claude model to use")] = None,
    full: Annotated[bool, typer.Option("--full", help="Include heavy sections (notes_to_financials, financial_statements)")] = False,
    force: Annotated[bool, typer.Option("--force", help="Re-extract all years, ignoring cached JSONs")] = False,
    download: Annotated[bool, typer.Option("--download/--no-download", help="Download missing AR PDFs first")] = True,
) -> None:
    """Extract structured insights from annual report PDFs via Docling + AI.

    Reads ~/vault/stocks/{SYMBOL}/filings/FY??/annual_report.pdf (up to N most
    recent years). Extracts chairman_letter, mdna, risk_management, auditor_report,
    corporate_governance, brsr, related_party, segmental by default. Pass --full
    to also include notes_to_financials + financial_statements. Builds a
    cross-year evolution narrative comparing the years.
    """
    import asyncio

    from flowtracker.research.ar_downloader import ensure_annual_reports
    from flowtracker.research.annual_report_extractor import (
        ensure_annual_report_data,
        extract_annual_reports,
    )

    if download:
        n = ensure_annual_reports(symbol.upper(), max_years=years)
        if n:
            console.print(f"Downloaded {n} new AR PDF(s)")

    runner = extract_annual_reports if force else ensure_annual_report_data
    result = asyncio.run(runner(symbol.upper(), years=years, model=model or "claude-sonnet-4-6", full=full))

    if result is None:
        console.print(f"[yellow]No annual_report.pdf found for {symbol.upper()}[/]")
        console.print(f"  Try: flowtrack filings download-ar -s {symbol.upper()}")
        return
    console.print(f"[green]\u2713[/] AR extraction: {result.get('years_analyzed')} for {symbol.upper()}")
    console.print(f"  Per-year JSONs: ~/vault/stocks/{symbol.upper()}/fundamentals/annual_report_FY*.json")
    console.print(f"  Cross-year narrative: ~/vault/stocks/{symbol.upper()}/fundamentals/annual_report_cross_year.json")


@app.command(name="extract-deck")
def extract_decks_cmd(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Stock symbol")],
    quarters: Annotated[int, typer.Option("--quarters", "-q", help="Number of deck quarters to extract")] = 4,
    model: Annotated[str | None, typer.Option("--model", "-m", help="Claude model to use")] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-extract all quarters, ignoring cached JSON")] = False,
) -> None:
    """Extract structured insights from investor-deck PDFs via Docling + AI.

    Reads ~/vault/stocks/{SYMBOL}/filings/FY??-Q?/investor_deck.pdf (up to N most
    recent quarters). Docling converts each PDF to markdown (cached), then Claude
    extracts segment_performance, strategic_priorities, outlook, charts, etc. Output
    lands at ~/vault/stocks/{SYMBOL}/fundamentals/deck_extraction.json.
    """
    import asyncio

    from flowtracker.research.deck_extractor import ensure_deck_data, extract_decks

    runner = extract_decks if force else ensure_deck_data
    result = asyncio.run(runner(symbol.upper(), quarters=quarters, model=model or "claude-sonnet-4-6"))

    if result is None:
        console.print(f"[yellow]No investor_deck.pdf found for {symbol.upper()}[/]")
        console.print(f"  Expected at: ~/vault/stocks/{symbol.upper()}/filings/FY??-Q?/investor_deck.pdf")
        return
    console.print(f"[green]\u2713[/] Deck extraction: {result.get('quarters_analyzed', 0)} quarters for {symbol.upper()}")
    console.print(f"  Saved to: ~/vault/stocks/{symbol.upper()}/fundamentals/deck_extraction.json")


def _show_filing_summary(filings: list, symbol: str) -> None:
    """Show summary of fetched filings by category."""
    cats: dict[str, int] = {}
    for f in filings:
        key = f.subcategory or f.category
        cats[key] = cats.get(key, 0) + 1

    table = Table(title=f"Filing Summary — {symbol}", show_header=True, header_style="bold cyan")
    table.add_column("Category", width=30)
    table.add_column("Count", justify="right", width=6)

    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        table.add_row(cat, str(count))

    console.print(table)
