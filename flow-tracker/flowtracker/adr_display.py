"""Rich display formatters for ADR/GDR program directory rows."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def display_adr_programs(rows: list[dict]) -> None:
    """Render a list of DR program dicts (from ``FlowStore.get_adr_programs``).

    Empty input prints a dim hint rather than an empty table — the most
    common cause is forgetting to run ``flowtrack adr refresh`` first.
    """
    if not rows:
        console.print(
            "[dim]No ADR/GDR programs in store. Run 'flowtrack adr refresh' first.[/dim]"
        )
        return

    table = Table(title="Indian ADR/GDR Programs")
    table.add_column("NSE", style="cyan")
    table.add_column("Company", style="white")
    table.add_column("US Ticker", style="green")
    table.add_column("Type", justify="center")
    table.add_column("Sponsorship", style="dim")
    table.add_column("Depositary", style="white")
    table.add_column("Ratio", style="dim")

    for r in rows:
        table.add_row(
            r.get("nse_symbol") or "[dim]—[/dim]",
            (r.get("company_name") or "")[:42],
            r.get("us_ticker") or "[dim]—[/dim]",
            r.get("program_type") or "[dim]—[/dim]",
            r.get("sponsorship") or "[dim]—[/dim]",
            r.get("depositary") or "[dim]—[/dim]",
            r.get("ratio") or "[dim]—[/dim]",
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} program(s).[/dim]")
