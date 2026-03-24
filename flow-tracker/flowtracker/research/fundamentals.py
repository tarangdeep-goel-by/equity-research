"""Render fundamentals HTML report from collected data."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_VAULT_BASE = Path.home() / "vault" / "stocks"
_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def render_fundamentals_report(
    symbol: str,
    data: dict,
    concall_data: dict | None = None,
) -> Path:
    """Render a fundamentals HTML report and save to vault + reports/.

    Args:
        symbol: Stock symbol (e.g., 'INDIAMART')
        data: Dict from data_collector.collect_fundamentals_data()
        concall_data: Optional dict with concall-extracted content (HTML fragments).
            Keys: operational_kpis, themes, analyst_qa, guidance, scorecard, risks, thesis, quarters_covered

    Returns:
        Path to the generated HTML file in the vault.
    """
    symbol = symbol.upper()
    today = date.today().isoformat()

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
    )
    template = env.get_template("fundamentals.html.j2")

    # Build template context
    ctx = {
        "symbol": symbol,
        "report_date": today,
        "v": data.get("valuation_latest", {}),
        "concall_data": concall_data,
        **data,
    }

    html = template.render(**ctx)

    # Write to vault
    vault_dir = _VAULT_BASE / symbol / "fundamentals"
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / f"{today}.html"
    vault_path.write_text(html)

    # Copy to reports/
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports_path = _REPORTS_DIR / f"{symbol.lower()}-fundamentals.html"
    shutil.copy2(vault_path, reports_path)

    return vault_path
