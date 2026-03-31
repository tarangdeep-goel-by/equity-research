"""CLI commands for alert system."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from flowtracker.alert_display import (
    display_alert_added,
    display_alert_history,
    display_alert_removed,
    display_alerts,
    display_triggered_alerts,
)
from flowtracker.alert_engine import check_all_alerts
from flowtracker.alert_models import Alert
from flowtracker.store import FlowStore

_CONDITION_TYPES = [
    "price_above", "price_below", "pe_above", "pe_below",
    "fii_pct_below", "mf_pct_above", "rsi_below", "rsi_above",
    "pledge_above", "dcf_upside_above",
]

app = typer.Typer(
    name="alert",
    help="Condition-based alerts — price, PE, RSI, ownership, pledge thresholds",
    no_args_is_help=True,
)
console = Console()


@app.command()
def add(
    symbol: Annotated[str, typer.Argument(help="Stock symbol")],
    condition_type: Annotated[str, typer.Argument(help=f"Condition: {', '.join(_CONDITION_TYPES)}")],
    threshold: Annotated[float, typer.Argument(help="Threshold value")],
    notes: Annotated[str | None, typer.Option("--notes", "-n", help="Notes")] = None,
) -> None:
    """Create a new alert."""
    symbol = symbol.upper()
    if condition_type not in _CONDITION_TYPES:
        console.print(f"[red]Invalid condition: {condition_type}[/]")
        console.print(f"Valid: {', '.join(_CONDITION_TYPES)}")
        raise typer.Exit(1)

    alert = Alert(symbol=symbol, condition_type=condition_type, threshold=threshold, notes=notes)
    with FlowStore() as store:
        store.upsert_alert(alert)
    display_alert_added(symbol, condition_type, threshold)


@app.command("list")
def list_alerts() -> None:
    """Show all active alerts."""
    with FlowStore() as store:
        alerts = store.get_active_alerts()
    display_alerts(alerts)


@app.command()
def check() -> None:
    """Run all active alerts against current data."""
    with FlowStore() as store:
        triggered = check_all_alerts(store)
    display_triggered_alerts(triggered)


@app.command()
def remove(
    alert_id: Annotated[int, typer.Argument(help="Alert ID to deactivate")],
) -> None:
    """Deactivate an alert."""
    with FlowStore() as store:
        removed = store.deactivate_alert(alert_id)
    if removed:
        display_alert_removed(alert_id)
    else:
        console.print(f"[yellow]Alert #{alert_id} not found.[/]")


@app.command()
def history(
    limit: Annotated[int, typer.Option("--limit", "-l", help="Number of records")] = 20,
) -> None:
    """Show alert trigger history."""
    with FlowStore() as store:
        hist = store.get_alert_history(limit)
    display_alert_history(hist)
