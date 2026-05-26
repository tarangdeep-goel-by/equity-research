"""Rich display formatters for NSE/BSE surveillance flags."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


_REASON_MAX = 60


def _truncate(text: str | None, limit: int = _REASON_MAX) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def display_surveillance_flags(rows: list[dict]) -> None:
    """Render a list of stored surveillance-flag dicts.

    Empty input prints a hint about ``flowtrack surveillance fetch`` rather
    than an empty table — the most common cause is a fresh DB.
    """
    if not rows:
        console.print(
            "[dim]No surveillance flags in store. Run 'flowtrack surveillance fetch' first.[/dim]"
        )
        return

    table = Table(title="NSE/BSE Surveillance Flags")
    table.add_column("Exchange", style="cyan", width=8)
    table.add_column("Type", style="bold yellow", width=6)
    table.add_column("Symbol", style="white", width=14)
    table.add_column("Stage", style="magenta", width=12)
    table.add_column("Effective", style="dim", width=12)
    table.add_column("Reason", style="white")

    for r in rows:
        table.add_row(
            r.get("exchange") or "—",
            r.get("alert_type") or "—",
            r.get("symbol") or "—",
            r.get("stage") or "—",
            r.get("effective_date") or "—",
            _truncate(r.get("reason")),
        )

    console.print(table)
    by_type = Counter(r.get("alert_type") for r in rows)
    by_exch = Counter(r.get("exchange") for r in rows)
    counts_type = ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))
    counts_exch = ", ".join(f"{k}={v}" for k, v in sorted(by_exch.items()))
    console.print(
        f"[dim]{len(rows)} flag(s)  |  by type: {counts_type}  |  by exchange: {counts_exch}[/dim]"
    )


def display_symbol_check(symbol: str, rows: list[dict]) -> None:
    """Render the per-symbol surveillance lookup result."""
    if not rows:
        console.print(Panel(
            f"[green]No surveillance flags found for {symbol}.[/green]",
            title=f"Surveillance — {symbol}",
            border_style="green",
        ))
        return

    lines = [
        f"[bold red]{symbol} is under surveillance[/bold red] — "
        f"{len(rows)} active flag(s).",
        "",
    ]
    for r in rows:
        stage = r.get("stage") or "—"
        reason = r.get("reason") or "—"
        lines.append(
            f"  [yellow]{r.get('alert_type','—')}[/yellow] "
            f"({r.get('exchange','—')})  Stage: [magenta]{stage}[/magenta]  "
            f"Effective: [dim]{r.get('effective_date','—')}[/dim]"
        )
        lines.append(f"    {_truncate(reason, 120)}")
    console.print(Panel(
        "\n".join(lines),
        title=f"Surveillance — {symbol}",
        border_style="red",
    ))


def display_fetch_summary(counts: dict[str, int]) -> None:
    """Render the post-fetch summary (counts per alert_type / exchange)."""
    table = Table(title="Surveillance Fetch Summary")
    table.add_column("Bucket", style="cyan")
    table.add_column("Count", justify="right")
    total = 0
    for k in ("ASM", "GSM", "ESM"):
        v = int(counts.get(k, 0))
        total += v
        table.add_row(k, str(v))
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total}[/bold]")
    console.print(table)
