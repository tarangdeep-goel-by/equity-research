"""Rich display formatters for composite screening engine."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowtracker.screener_models import StockScore

console = Console()

_FACTOR_LABELS = {
    "ownership": "Ownership",
    "insider": "Insider",
    "valuation": "Valuation",
    "earnings": "Earnings",
    "quality": "Quality",
    "delivery": "Delivery",
    "estimates": "Estimates",
    "risk": "Risk",
}

_INDUSTRY_MAX = 18


def _truncate_industry(industry: str | None) -> str:
    """Truncate industry name to _INDUSTRY_MAX chars with ellipsis."""
    if not industry:
        return "—"
    if len(industry) <= _INDUSTRY_MAX:
        return industry
    return industry[: _INDUSTRY_MAX - 1] + "\u2026"


def display_screen_results(scores: list[StockScore], limit: int = 30) -> None:
    """Show ranked stock screening results."""
    if not scores:
        console.print("[yellow]No stocks scored. Run data fetches first.[/]")
        return

    table = Table(
        title="Composite Stock Screen",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", width=4)
    table.add_column("Symbol", width=12)
    table.add_column("Industry", width=_INDUSTRY_MAX + 2)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Own", justify="right", width=5)
    table.add_column("Ins", justify="right", width=5)
    table.add_column("Val", justify="right", width=5)
    table.add_column("Ear", justify="right", width=5)
    table.add_column("Qua", justify="right", width=5)
    table.add_column("Del", justify="right", width=5)
    table.add_column("Est", justify="right", width=5)
    table.add_column("Risk", justify="right", width=5)

    for s in scores[:limit]:
        factors = {f.factor: f.score for f in s.factors}

        # Color composite score
        sc = s.composite_score
        if sc >= 70:
            score_str = f"[bold green]{sc:.0f}[/]"
        elif sc >= 50:
            score_str = f"[yellow]{sc:.0f}[/]"
        else:
            score_str = f"[red]{sc:.0f}[/]"

        table.add_row(
            str(s.rank),
            s.symbol,
            _truncate_industry(s.industry),
            score_str,
            _factor_cell(factors.get("ownership", -1)),
            _factor_cell(factors.get("insider", -1)),
            _factor_cell(factors.get("valuation", -1)),
            _factor_cell(factors.get("earnings", -1)),
            _factor_cell(factors.get("quality", -1)),
            _factor_cell(factors.get("delivery", -1)),
            _factor_cell(factors.get("estimates", -1)),
            _factor_cell(factors.get("risk", -1)),
        )

    console.print(table)
    console.print(f"[dim]Showing top {min(limit, len(scores))} of {len(scores)} stocks[/]")


def display_screen_summary(scores: list[StockScore]) -> None:
    """Show summary statistics for screening results."""
    if not scores:
        return

    composites = [s.composite_score for s in scores]
    avg = mean(composites)
    med = median(composites)

    # Top represented industry
    industries = [s.industry for s in scores if s.industry]
    top_industry = "—"
    if industries:
        counter = Counter(industries)
        top_industry, top_count = counter.most_common(1)[0]
        top_industry = f"{top_industry} ({top_count})"

    console.print(
        f"\n[bold]Summary:[/] {len(scores)} stocks scored  |  "
        f"Mean: [cyan]{avg:.1f}[/]  |  Median: [cyan]{med:.1f}[/]  |  "
        f"Top industry: [cyan]{top_industry}[/]"
    )


def display_stock_scorecard(score: StockScore) -> None:
    """Show detailed scorecard for a single stock."""
    lines = [
        f"[bold]{score.symbol}[/] — {score.company_name or 'Unknown'}",
        f"Industry: {score.industry or '—'}",
        "",
    ]

    # Composite
    sc = score.composite_score
    if sc >= 70:
        color = "bold green"
    elif sc >= 50:
        color = "yellow"
    else:
        color = "red"
    lines.append(f"Composite Score: [{color}]{sc:.0f}/100[/{color}]")
    lines.append("")

    # Factor breakdown
    lines.append("[bold]Factor Breakdown:[/]")
    for f in score.factors:
        label = _FACTOR_LABELS.get(f.factor, f.factor.title())
        if f.score < 0:
            lines.append(f"  {label:12s}  [dim]— (no data)[/]")
        else:
            bar = _score_bar(f.score)
            lines.append(f"  {label:12s}  {bar} {f.score:.0f}  {f.detail}")

    console.print(Panel(
        "\n".join(lines),
        title=f"Stock Scorecard — {score.symbol}",
        border_style="cyan",
    ))


def _factor_cell(score: float) -> str:
    """Format a factor score as a colored cell."""
    if score < 0:
        return "[dim]—[/]"
    if score > 70:
        return f"[green]{score:.0f}[/]"
    elif score >= 40:
        return f"[yellow]{score:.0f}[/]"
    else:
        return f"[red]{score:.0f}[/]"


def _score_bar(score: float) -> str:
    """Create a visual score bar."""
    filled = int(score / 10)
    empty = 10 - filled
    if score >= 70:
        color = "green"
    elif score >= 50:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"
