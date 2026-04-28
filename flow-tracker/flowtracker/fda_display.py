"""Rich display for FDA inspection / drug-enforcement records.

Renders the openFDA-sourced rows persisted in `fda_inspections`. Pairs with
`flowtracker.fda_commands.fda list -s SYMBOL`.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def display_fda_inspections(rows: list[dict]) -> None:
    """Render stored FDA inspection rows as a Rich table.

    ``rows`` is the dict-list returned by ``FlowStore.get_fda_inspections``.
    Empty input prints a dim-styled "no records" line.
    """
    if not rows:
        console.print("[dim]No FDA inspection records on file for this symbol.[/dim]")
        return

    table = Table(title="USFDA Inspection / Enforcement Records")
    table.add_column("Inspection Date", style="cyan")
    table.add_column("Posted", style="dim")
    table.add_column("Classification", justify="center")
    table.add_column("Country", style="white")
    table.add_column("Firm", style="white")
    table.add_column("FEI / Recall #", style="dim")
    table.add_column("Product Area", style="white", overflow="fold")

    for r in rows:
        cls = r.get("classification") or ""
        # Severity coloring — Class I (most severe) red, II yellow, III dim,
        # plus inspection-style outcome tokens if/when CSV-seed cross-loads.
        if "I" == cls.replace("Class ", "").strip() or cls == "OAI":
            cls_str = f"[red]{cls}[/red]" if cls else ""
        elif cls.replace("Class ", "").strip() == "II" or cls == "VAI":
            cls_str = f"[yellow]{cls}[/yellow]"
        else:
            cls_str = f"[dim]{cls}[/dim]" if cls else ""

        table.add_row(
            (r.get("inspection_date") or "").strip() or "—",
            (r.get("posted_date") or "").strip() or "—",
            cls_str,
            (r.get("country") or "").strip() or "—",
            (r.get("firm_name") or "").strip()[:40],
            (r.get("fei_number") or "").strip() or "—",
            (r.get("product_area") or "").strip()[:80] or "—",
        )

    console.print(table)
