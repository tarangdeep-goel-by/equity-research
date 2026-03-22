"""Rich display formatters for sector aggregation views."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def display_sector_overview(sectors: list[dict]) -> None:
    """Show sector-level ownership shifts overview.

    Each dict: {industry, num_stocks, avg_fii_change, avg_mf_change, avg_dii_change,
                avg_promoter_change, total_fii_change, total_mf_change}
    """
    if not sectors:
        console.print("[yellow]No sector data. Run 'flowtrack scan fetch' first.[/]")
        return

    table = Table(
        title="Sector Ownership Shifts + Market Signals (Latest Quarter)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Sector", width=26)
    table.add_column("#", justify="right", width=3)
    table.add_column("FII Chg", justify="right", width=8)
    table.add_column("MF Chg", justify="right", width=8)
    table.add_column("DII Chg", justify="right", width=8)
    table.add_column("Del%", justify="right", width=5)
    table.add_column("30d Chg", justify="right", width=7)
    table.add_column("Signal", width=12)

    for s in sectors:
        fii_chg = s.get("avg_fii_change", 0) or 0
        mf_chg = s.get("avg_mf_change", 0) or 0
        dii_chg = s.get("avg_dii_change", 0) or 0
        avg_del = s.get("avg_delivery_pct") or 0
        avg_price = s.get("avg_price_change_pct") or 0

        signal = _sector_signal(fii_chg, mf_chg, dii_chg, avg_del)

        # Delivery % coloring
        if avg_del >= 50:
            del_str = f"[green]{avg_del:.0f}[/green]"
        elif avg_del >= 35:
            del_str = f"{avg_del:.0f}"
        else:
            del_str = f"[dim]{avg_del:.0f}[/dim]" if avg_del else "—"

        # Price change coloring
        price_str = _colored_pct(avg_price) if avg_price else "—"

        table.add_row(
            s["industry"][:26],
            str(s["num_stocks"]),
            _colored_pct(fii_chg),
            _colored_pct(mf_chg),
            _colored_pct(dii_chg),
            del_str,
            price_str,
            signal,
        )

    console.print(table)


def display_sector_detail(industry: str, stocks: list[dict]) -> None:
    """Show detailed stock-level view for a sector.

    Each dict: {symbol, fii_change, mf_change, dii_change, promoter_change,
                curr_fii, curr_mf, price, pe_trailing}
    """
    if not stocks:
        console.print(f"[yellow]No data for sector '{industry}'.[/]")
        return

    table = Table(
        title=f"Sector Detail — {industry}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Symbol", width=12)
    table.add_column("FII%", justify="right", width=5)
    table.add_column("FII Chg", justify="right", width=8)
    table.add_column("MF%", justify="right", width=5)
    table.add_column("MF Chg", justify="right", width=8)
    table.add_column("Del%", justify="right", width=5)
    table.add_column("30d%", justify="right", width=7)
    table.add_column("P/E", justify="right", width=6)
    table.add_column("Signal", width=12)

    for s in stocks:
        fii_chg = s.get("fii_change", 0) or 0
        mf_chg = s.get("mf_change", 0) or 0
        avg_del = s.get("avg_delivery_pct") or 0
        avg_price = s.get("avg_price_change_pct") or 0

        signal = _stock_signal(fii_chg, mf_chg)

        # Delivery coloring
        if avg_del >= 50:
            del_str = f"[green]{avg_del:.0f}[/green]"
        elif avg_del >= 35:
            del_str = f"{avg_del:.0f}"
        else:
            del_str = f"[dim]{avg_del:.0f}[/dim]" if avg_del else "—"

        table.add_row(
            s["symbol"],
            f"{s.get('curr_fii', 0) or 0:.1f}",
            _colored_pct(fii_chg),
            f"{s.get('curr_mf', 0) or 0:.1f}",
            _colored_pct(mf_chg),
            del_str,
            _colored_pct(avg_price) if avg_price else "—",
            f"{s['pe_trailing']:.1f}" if s.get("pe_trailing") else "—",
            signal,
        )

    console.print(table)


def _colored_pct(val: float) -> str:
    """Format a percentage change with color."""
    if val > 0:
        return f"[green]+{val:.2f}%[/green]"
    elif val < 0:
        return f"[red]{val:.2f}%[/red]"
    return f"{val:.2f}%"


def _sector_signal(fii_chg: float, mf_chg: float, dii_chg: float, avg_del: float = 0) -> str:
    """Determine sector-level signal from ownership + delivery signals."""
    if fii_chg > 0.5 and mf_chg > 0.5:
        if avg_del >= 50:
            return "[bold green]STRONG BUY[/]"
        return "[bold green]ACCUMULATE[/]"
    elif fii_chg < -0.5 and mf_chg > 0.5:
        return "[yellow]HANDOFF[/]"
    elif fii_chg < -0.5 and mf_chg < -0.5:
        return "[bold red]EXIT[/]"
    elif mf_chg > 1.0:
        if avg_del >= 50:
            return "[bold green]MF+DELIV[/]"
        return "[green]MF INFLOW[/]"
    elif fii_chg > 1.0:
        return "[green]FII INFLOW[/]"
    elif fii_chg < -1.0:
        return "[red]FII EXIT[/]"
    elif avg_del >= 55:
        return "[cyan]HIGH DELIV[/]"
    return "—"


def _stock_signal(fii_chg: float, mf_chg: float) -> str:
    """Determine stock-level signal."""
    if fii_chg < -0.5 and mf_chg > 0.5:
        return "[yellow]HANDOFF[/]"
    elif fii_chg > 0.5 and mf_chg > 0.5:
        return "[bold green]ACCUMULATE[/]"
    elif fii_chg < -1.0:
        return "[red]FII EXIT[/]"
    elif mf_chg > 1.0:
        return "[green]MF BUY[/]"
    return "—"
