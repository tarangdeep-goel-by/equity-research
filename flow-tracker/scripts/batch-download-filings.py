#!/usr/bin/env python3
"""Batch download concall transcripts + investor decks for Nifty 250 stocks.

Downloads from BSE to ~/vault/stocks/{SYMBOL}/filings/{FY-Q}/concall.pdf
Free — just HTTP downloads, no API keys needed.

Usage:
    uv run python scripts/batch-download-filings.py              # all 250
    uv run python scripts/batch-download-filings.py --limit 50   # first 50
    uv run python scripts/batch-download-filings.py --resume     # skip already downloaded
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from flowtracker.store import FlowStore
from flowtracker.filing_client import FilingClient

console = Console()


def get_nifty_250_symbols() -> list[str]:
    """Get Nifty 250 symbols from index_constituents."""
    with FlowStore() as store:
        rows = store._conn.execute(
            "SELECT symbol FROM index_constituents ORDER BY symbol LIMIT 250"
        ).fetchall()
    return [r[0] for r in rows]


def count_existing_concalls(symbol: str) -> int:
    """Count concall PDFs already in vault for a symbol."""
    vault = Path.home() / "vault" / "stocks" / symbol / "filings"
    if not vault.exists():
        return 0
    return len(list(vault.glob("*/concall.pdf")))


def download_filings_for_symbol(fc: FilingClient, symbol: str) -> dict:
    """Download research filings for one stock. Returns summary."""
    result = {"symbol": symbol, "filings_found": 0, "downloaded": 0, "errors": 0}

    try:
        filings = fc.fetch_research_filings(symbol)
        result["filings_found"] = len(filings)
    except Exception as e:
        result["errors"] = 1
        result["error_msg"] = str(e)[:100]
        return result

    for filing in filings:
        try:
            path = fc.download_filing(filing)
            if path:
                result["downloaded"] += 1
        except Exception:
            result["errors"] += 1

    return result


def main():
    parser = argparse.ArgumentParser(description="Batch download concall PDFs for Nifty 250")
    parser.add_argument("--limit", type=int, default=250, help="Number of stocks (default: 250)")
    parser.add_argument("--resume", action="store_true", help="Skip stocks with >=4 concalls already")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between stocks (rate limit)")
    args = parser.parse_args()

    symbols = get_nifty_250_symbols()[:args.limit]
    console.print(f"\n[bold]Batch Filing Download — {len(symbols)} stocks[/]\n")

    # Check what's already downloaded
    if args.resume:
        to_download = []
        skipped = 0
        for sym in symbols:
            existing = count_existing_concalls(sym)
            if existing >= 4:
                skipped += 1
            else:
                to_download.append(sym)
        console.print(f"[dim]Resume mode: skipping {skipped} stocks with >=4 concalls[/]")
        symbols = to_download

    console.print(f"Downloading filings for {len(symbols)} stocks...\n")

    fc = FilingClient()
    total_downloaded = 0
    total_errors = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading", total=len(symbols))

        for i, symbol in enumerate(symbols):
            progress.update(task, description=f"{symbol:12s}")

            result = download_filings_for_symbol(fc, symbol)
            total_downloaded += result["downloaded"]
            total_errors += result["errors"]

            if result["downloaded"] > 0:
                progress.console.print(
                    f"  [green]✓[/] {symbol}: {result['filings_found']} filings, "
                    f"{result['downloaded']} PDFs downloaded"
                )
            elif result.get("error_msg"):
                progress.console.print(
                    f"  [yellow]⚠[/] {symbol}: {result['error_msg']}"
                )

            progress.advance(task)
            time.sleep(args.sleep)

    # Summary
    console.print(f"\n[bold]Done![/]")
    console.print(f"  Stocks processed: {len(symbols)}")
    console.print(f"  PDFs downloaded:  {total_downloaded}")
    console.print(f"  Errors:           {total_errors}")

    # Count total concalls in vault
    vault = Path.home() / "vault" / "stocks"
    total_concalls = 0
    stocks_with = 0
    if vault.exists():
        for stock_dir in vault.iterdir():
            concalls = list(stock_dir.glob("filings/*/concall.pdf"))
            if concalls:
                stocks_with += 1
                total_concalls += len(concalls)
    console.print(f"\n  Vault total: {stocks_with} stocks, {total_concalls} concall PDFs")


if __name__ == "__main__":
    main()
