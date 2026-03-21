"""Flow Tracker CLI — FII/DII institutional flow tracker for Indian markets."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from flowtracker.client import NSEClient, NSEFetchError
from flowtracker.display import (
    display_fetch_result,
    display_flows_table,
    display_no_data,
    display_streak,
    display_summary,
)
from flowtracker.fund_commands import app as fund_app
from flowtracker.holding_commands import app as holding_app
from flowtracker.mf_commands import app as mf_app
from flowtracker.scan_commands import app as scan_app
from flowtracker.commodity_commands import app as gold_app
from flowtracker.macro_commands import app as macro_app
from flowtracker.bhavcopy_commands import app as bhavcopy_app
from flowtracker.deals_commands import app as deals_app
from flowtracker.insider_commands import app as insider_app
from flowtracker.estimates_commands import app as estimates_app
from flowtracker.sector_commands import app as sector_app
from flowtracker.models import DailyFlow
from flowtracker.store import FlowStore
from flowtracker.utils import parse_period

app = typer.Typer(
    name="flowtrack",
    help="FII/DII institutional flow tracker for Indian markets",
    no_args_is_help=True,
)
app.add_typer(fund_app)
app.add_typer(mf_app)
app.add_typer(holding_app)
app.add_typer(scan_app)
app.add_typer(gold_app)
app.add_typer(macro_app)
app.add_typer(bhavcopy_app)
app.add_typer(deals_app)
app.add_typer(insider_app)
app.add_typer(estimates_app)
app.add_typer(sector_app)
console = Console()


@app.command()
def fetch() -> None:
    """Fetch today's FII/DII data from NSE and store in local database."""
    try:
        with NSEClient() as client:
            flows = client.fetch_daily()
    except NSEFetchError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        store.upsert_flows(flows)

    display_fetch_result(flows)


@app.command()
def summary() -> None:
    """Show most recent day's FII/DII flows."""
    with FlowStore() as store:
        pair = store.get_latest()

    if pair is None:
        display_no_data("Run 'flowtrack fetch' first.")
        raise typer.Exit(1)

    display_summary(pair)


@app.command()
def flows(
    period: Annotated[str, typer.Option("-p", "--period", help="Period like '7d' or '30d'")] = "7d",
) -> None:
    """Show historical FII/DII flows for the given period."""
    try:
        days = parse_period(period)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        data = store.get_flows(days)

    display_flows_table(data, period)


@app.command()
def streak() -> None:
    """Show current FII/DII buying/selling streaks."""
    with FlowStore() as store:
        fii_streak = store.get_streak("FII")
        dii_streak = store.get_streak("DII")

    if fii_streak is None and dii_streak is None:
        display_no_data("Run 'flowtrack fetch' to accumulate data.")
        raise typer.Exit(1)

    display_streak(fii_streak, dii_streak)


@app.command()
def backfill(
    file: Annotated[Path, typer.Argument(help="Path to CSV or XLSX file with historical FII/DII data")],
) -> None:
    """Import historical FII/DII data from a CSV or XLSX file."""
    if not file.exists():
        console.print(f"[red]File not found: {file}[/]")
        raise typer.Exit(1)

    suffix = file.suffix.lower()
    try:
        if suffix == ".csv":
            all_flows = _parse_csv(file)
        elif suffix in (".xlsx", ".xls"):
            all_flows = _parse_xlsx(file)
        else:
            console.print(f"[red]Unsupported file type: {suffix} (use .csv or .xlsx)[/]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to parse {file.name}: {e}[/]")
        raise typer.Exit(1)

    if not all_flows:
        console.print("[yellow]No valid rows found in file.[/]")
        raise typer.Exit(1)

    with FlowStore() as store:
        count = store.upsert_flows(all_flows)

    dates = sorted({f.date for f in all_flows})
    console.print(
        f"\n[bold]Imported {count} records[/] "
        f"({len(dates)} trading days, {dates[0]} to {dates[-1]})"
    )


def _parse_csv(file: Path) -> list[DailyFlow]:
    """Parse CSV with columns: Date, FII_Gross_Purchase, FII_Gross_Sales, FII_Net_Purchase/Sales, DII_Gross_Purchase, DII_Gross_Sales, DII_Net_Purchase/Sales."""
    flows: list[DailyFlow] = []
    with open(file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = _parse_date(row["Date"])
                flows.append(DailyFlow(
                    date=d, category="FII",
                    buy_value=_float(row["FII_Gross_Purchase"]),
                    sell_value=_float(row["FII_Gross_Sales"]),
                    net_value=_float(row["FII_Net_Purchase/Sales"]),
                ))
                flows.append(DailyFlow(
                    date=d, category="DII",
                    buy_value=_float(row["DII_Gross_Purchase"]),
                    sell_value=_float(row["DII_Gross_Sales"]),
                    net_value=_float(row["DII_Net_Purchase/Sales"]),
                ))
            except (KeyError, ValueError):
                continue
    return flows


def _parse_xlsx(file: Path) -> list[DailyFlow]:
    """Parse XLSX with same column structure as CSV."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required for XLSX import — run: uv pip install openpyxl")

    wb = openpyxl.load_workbook(file, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    headers = [str(h).strip() for h in rows[0]]
    flows: list[DailyFlow] = []
    for row in rows[1:]:
        rec = dict(zip(headers, row))
        try:
            d = _parse_date(rec["Date"])
            flows.append(DailyFlow(
                date=d, category="FII",
                buy_value=float(rec["FII_Gross_Purchase"]),
                sell_value=float(rec["FII_Gross_Sales"]),
                net_value=float(rec["FII_Net_Purchase/Sales"]),
            ))
            flows.append(DailyFlow(
                date=d, category="DII",
                buy_value=float(rec["DII_Gross_Purchase"]),
                sell_value=float(rec["DII_Gross_Sales"]),
                net_value=float(rec["DII_Net_Purchase/Sales"]),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return flows


def _parse_date(val: object) -> date:
    """Parse date from string or datetime object."""
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    # Try DD-MM-YYYY first (CSV format)
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _float(val: object) -> float:
    """Parse float from string or number, stripping commas."""
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).replace(",", "").strip())
