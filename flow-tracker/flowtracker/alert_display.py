"""Rich display formatters for alert system."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.alert_models import Alert, TriggeredAlert

console = Console()


def display_alerts(alerts: list[Alert]) -> None:
    """Show all active alerts."""
    if not alerts:
        console.print("[yellow]No active alerts. Use 'flowtrack alert add' to create one.[/]")
        return

    table = Table(
        title="Active Alerts",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", justify="right", width=5)
    table.add_column("Symbol", width=12)
    table.add_column("Condition", width=18)
    table.add_column("Threshold", justify="right", width=12)
    table.add_column("Last Triggered", width=20)
    table.add_column("Notes", width=20)

    for a in alerts:
        table.add_row(
            str(a.id) if a.id else "—",
            a.symbol,
            a.condition_type,
            f"{a.threshold:,.2f}",
            a.last_triggered or "never",
            a.notes or "",
        )

    console.print(table)


def display_triggered_alerts(triggered: list[TriggeredAlert]) -> None:
    """Show triggered alerts or all-clear message."""
    if not triggered:
        console.print(Panel(
            "[green]All clear — no alerts triggered.[/]",
            title="Alert Check",
            border_style="green",
        ))
        return

    lines: list[str] = []
    for t in triggered:
        lines.append(f"[red]⚠[/] {t.message}")

    console.print(Panel(
        "\n".join(lines),
        title=f"Triggered Alerts ({len(triggered)})",
        border_style="red",
    ))


def display_alert_history(history: list[dict]) -> None:
    """Show alert trigger history."""
    if not history:
        console.print("[yellow]No alert history yet.[/]")
        return

    table = Table(
        title="Alert History",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Triggered At", width=20)
    table.add_column("Symbol", width=12)
    table.add_column("Condition", width=18)
    table.add_column("Value", justify="right", width=12)
    table.add_column("Message", min_width=30)

    for h in history:
        table.add_row(
            h.get("triggered_at", ""),
            h.get("symbol", ""),
            h.get("condition_type", ""),
            f"{h['current_value']:,.2f}" if h.get("current_value") else "—",
            h.get("message", ""),
        )

    console.print(table)


def display_alert_added(symbol: str, condition_type: str, threshold: float) -> None:
    """Show confirmation after adding an alert."""
    console.print(Panel(
        f"Alert set: {symbol} {condition_type} @ {threshold:,.2f}",
        title="Alert Created",
        border_style="green",
    ))


def display_alert_removed(alert_id: int) -> None:
    """Show confirmation after deactivating an alert."""
    console.print(Panel(
        f"Alert #{alert_id} deactivated",
        title="Alert Removed",
        border_style="yellow",
    ))
