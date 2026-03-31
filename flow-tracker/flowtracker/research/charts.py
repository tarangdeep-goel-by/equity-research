"""Chart rendering for equity research reports.

Generates PNG charts from SQLite data and returns file paths for embedding
in markdown reports as ![chart](path).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter


_REPORTS_DIR = Path.home() / "vault" / "stocks"

# Dark theme matching the HTML report
_DARK_BG = "#1B1B1B"
_SURFACE = "#2A2A2A"
_TEXT = "#F5F0EB"
_ACCENT_1 = "#C4533A"  # terracotta
_ACCENT_2 = "#2B5EA7"  # blue
_GREEN = "#4ecca3"
_RED = "#e94560"
_YELLOW = "#f0a500"
_GRID = "#333333"

plt.rcParams.update({
    "figure.facecolor": _DARK_BG,
    "axes.facecolor": _SURFACE,
    "axes.edgecolor": _GRID,
    "axes.labelcolor": _TEXT,
    "text.color": _TEXT,
    "xtick.color": _TEXT,
    "ytick.color": _TEXT,
    "grid.color": _GRID,
    "grid.alpha": 0.3,
    "font.family": "sans-serif",
    "font.size": 11,
    "legend.facecolor": _SURFACE,
    "legend.edgecolor": _GRID,
})


def _chart_dir(symbol: str) -> Path:
    d = _REPORTS_DIR / symbol.upper() / "charts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _crore_fmt(x, _):
    """Format y-axis values in crores."""
    if abs(x) >= 100:
        return f"₹{x:,.0f}"
    return f"₹{x:,.1f}"


def _pct_fmt(x, _):
    return f"{x:.0f}%"


def _fy_label(yr_str: str) -> str:
    """Convert fiscal year end date to 'FY25' format.

    '2025-03-31' → 'FY25', '2016-03-31' → 'FY16'.
    For dates with month > 3 (rare), fiscal year is year+1.
    Falls back to last 7 chars if not a date string.
    """
    s = str(yr_str)
    if len(s) >= 10 and s[4] == "-":
        try:
            year = int(s[:4])
            month = int(s[5:7])
            fy = year if month <= 3 else year + 1
            return f"FY{fy % 100:02d}"
        except ValueError:
            pass
    return s[-7:]


def render_price_chart(symbol: str, chart_data: list[dict]) -> str:
    """Render price + SMA50 + SMA200 chart from get_chart_data('price') output.

    Args:
        symbol: Stock symbol
        chart_data: List of {metric, values: [{date, value}]} from get_chart_data

    Returns: Absolute file path to the PNG.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    colors = {"Price": _TEXT, "DMA50": _YELLOW, "DMA200": _ACCENT_2}
    labels = {"Price": "Price", "DMA50": "50-day MA", "DMA200": "200-day MA"}

    for series in chart_data:
        metric = series.get("metric", "")
        values = series.get("values", [])
        if not values:
            continue

        dates = [date.fromisoformat(v["date"]) for v in values]
        vals = [v["value"] for v in values]

        ax.plot(dates, vals,
                color=colors.get(metric, _TEXT),
                label=labels.get(metric, metric),
                linewidth=2 if metric == "Price" else 1.2,
                alpha=1.0 if metric == "Price" else 0.7)

    ax.set_title(f"{symbol} — Price & Moving Averages", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Price (₹)")
    ax.yaxis.set_major_formatter(FuncFormatter(_crore_fmt))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    fig.autofmt_xdate(rotation=30)
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, alpha=0.3)

    path = _chart_dir(symbol) / "price_sma.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_pe_chart(symbol: str, chart_data: list[dict]) -> str:
    """Render PE ratio chart from get_chart_data('pe') output."""
    fig, ax = plt.subplots(figsize=(12, 5))

    for series in chart_data:
        metric = series.get("metric", "")
        values = series.get("values", [])
        if not values:
            continue

        dates = [date.fromisoformat(v["date"]) for v in values]
        vals = [v["value"] for v in values]

        color = _ACCENT_1 if "PE" in metric.upper() else _ACCENT_2
        ax.plot(dates, vals, color=color, label=metric, linewidth=1.5)

    ax.set_title(f"{symbol} — P/E Ratio History", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("P/E Ratio (x)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    fig.autofmt_xdate(rotation=30)
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, alpha=0.3)

    path = _chart_dir(symbol) / "pe_history.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_delivery_chart(symbol: str, delivery_data: list[dict]) -> str:
    """Render delivery % trend chart."""
    if not delivery_data:
        return ""

    fig, ax1 = plt.subplots(figsize=(12, 5))

    dates = [date.fromisoformat(d["date"]) for d in delivery_data if d.get("date")]
    delivery_pct = [d.get("delivery_pct", 0) for d in delivery_data if d.get("date")]
    volumes = [d.get("volume", 0) for d in delivery_data if d.get("date")]

    # Delivery % as bars
    bar_colors = [_GREEN if p > 55 else (_YELLOW if p > 40 else _RED) for p in delivery_pct]
    ax1.bar(dates, delivery_pct, color=bar_colors, alpha=0.7, width=0.8, label="Delivery %")
    ax1.axhline(y=45, color=_TEXT, linestyle="--", alpha=0.4, label="Market avg (45%)")
    ax1.set_ylabel("Delivery %")
    ax1.yaxis.set_major_formatter(FuncFormatter(_pct_fmt))
    ax1.set_ylim(0, 100)

    # Volume as secondary axis
    ax2 = ax1.twinx()
    ax2.plot(dates, volumes, color=_ACCENT_2, alpha=0.5, linewidth=1, label="Volume")
    ax2.set_ylabel("Volume", color=_ACCENT_2)
    ax2.tick_params(axis="y", labelcolor=_ACCENT_2)

    ax1.set_title(f"{symbol} — Delivery % & Volume", fontsize=14, fontweight="bold", pad=12)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.autofmt_xdate(rotation=30)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.8)
    ax1.grid(True, alpha=0.3)

    path = _chart_dir(symbol) / "delivery_trend.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_revenue_profit_chart(symbol: str, annual_data: list[dict]) -> str:
    """Render 10-year revenue & profit bar chart from annual financials."""
    if not annual_data:
        return ""

    fig, ax = plt.subplots(figsize=(12, 5))

    # Sort by year
    sorted_data = sorted(annual_data, key=lambda x: x.get("fiscal_year_end", x.get("year", "")))

    years = []
    revenues = []
    profits = []
    for d in sorted_data:
        yr = d.get("fiscal_year_end", d.get("year", ""))
        rev = d.get("revenue", d.get("sales", 0)) or 0
        profit = d.get("net_income", d.get("net_profit", d.get("profit_after_tax", 0))) or 0
        if yr and rev:
            years.append(_fy_label(yr))
            revenues.append(float(rev))
            profits.append(float(profit))

    if not years:
        plt.close(fig)
        return ""

    x = range(len(years))
    width = 0.35

    ax.bar([i - width / 2 for i in x], revenues, width, label="Revenue", color=_ACCENT_2, alpha=0.85)
    ax.bar([i + width / 2 for i in x], profits, width, label="Net Profit", color=_GREEN, alpha=0.85)

    ax.set_title(f"{symbol} — Revenue & Net Profit (₹ Cr)", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("₹ Crores")
    ax.yaxis.set_major_formatter(FuncFormatter(_crore_fmt))
    ax.set_xticks(list(x))
    ax.set_xticklabels(years, rotation=45, ha="right")
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, axis="y", alpha=0.3)

    path = _chart_dir(symbol) / "revenue_profit.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_shareholding_chart(symbol: str, shareholding_data: list[dict]) -> str:
    """Render quarterly shareholding trend (stacked area)."""
    if not shareholding_data:
        return ""

    # Pivot: {quarter: {category: pct}}
    quarters_map: dict[str, dict[str, float]] = {}
    for row in shareholding_data:
        q = row.get("quarter_end", "")
        cat = row.get("category", "")
        pct = row.get("percentage", 0) or 0
        if q and cat:
            quarters_map.setdefault(q, {})[cat] = float(pct)

    if not quarters_map:
        return ""

    quarters = sorted(quarters_map.keys())
    categories = ["Promoters", "FII", "DII", "Public"]
    cat_aliases = {
        "Promoters": ["Promoters", "Promoter"],
        "FII": ["FII", "Foreign Institutions", "FPI"],
        "DII": ["DII", "Domestic Institutions", "MF"],
        "Public": ["Public", "Retail", "Others"],
    }

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = {"Promoters": _ACCENT_1, "FII": _ACCENT_2, "DII": _GREEN, "Public": _YELLOW}

    for cat in categories:
        vals = []
        for q in quarters:
            qdata = quarters_map.get(q, {})
            v = 0
            for alias in cat_aliases.get(cat, [cat]):
                if alias in qdata:
                    v = qdata[alias]
                    break
            vals.append(v)

        if any(v > 0 for v in vals):
            ax.plot(quarters, vals, color=colors.get(cat, _TEXT),
                    label=cat, linewidth=2, marker="o", markersize=4)

    ax.set_title(f"{symbol} — Shareholding Pattern", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Holding %")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct_fmt))
    ax.set_xticklabels(quarters, rotation=45, ha="right")
    ax.legend(loc="upper right", framealpha=0.8)
    ax.grid(True, alpha=0.3)

    path = _chart_dir(symbol) / "shareholding.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_quarterly_chart(symbol: str, quarterly_data: list[dict]) -> str:
    """Render 12-quarter revenue + profit bar chart with YoY growth line."""
    if not quarterly_data:
        return ""

    fig, ax1 = plt.subplots(figsize=(12, 5))

    sorted_data = sorted(quarterly_data, key=lambda x: x.get("quarter_end", ""))[-12:]

    quarters = []
    revenues = []
    profits = []
    for d in sorted_data:
        q = d.get("quarter_end", "")
        rev = d.get("revenue", d.get("sales", 0)) or 0
        profit = d.get("net_income", d.get("net_profit", d.get("profit_after_tax", 0))) or 0
        if q:
            # Format as "Q3 FY26" from quarter_end date like "2025-12-31"
            qs = str(q)
            if len(qs) >= 10 and qs[4] == "-":
                try:
                    qy = int(qs[:4])
                    qm = int(qs[5:7])
                    q_map = {3: ("Q4", qy), 6: ("Q1", qy + 1), 9: ("Q2", qy + 1), 12: ("Q3", qy + 1)}
                    qname, fy = q_map.get(qm, (f"M{qm}", qy))
                    qs = f"{qname} FY{fy % 100:02d}"
                except ValueError:
                    pass
            quarters.append(qs)
            revenues.append(float(rev))
            profits.append(float(profit))

    if not quarters:
        plt.close(fig)
        return ""

    x = range(len(quarters))
    width = 0.35

    ax1.bar([i - width / 2 for i in x], revenues, width, label="Revenue", color=_ACCENT_2, alpha=0.85)
    ax1.bar([i + width / 2 for i in x], profits, width, label="Net Profit", color=_GREEN, alpha=0.85)
    ax1.set_ylabel("₹ Crores")
    ax1.yaxis.set_major_formatter(FuncFormatter(_crore_fmt))
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(quarters, rotation=45, ha="right", fontsize=9)
    ax1.legend(loc="upper left", framealpha=0.8)
    ax1.grid(True, axis="y", alpha=0.3)

    ax1.set_title(f"{symbol} — Quarterly Revenue & Profit (12Q)", fontsize=14, fontweight="bold", pad=12)

    path = _chart_dir(symbol) / "quarterly_earnings.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_margin_trend(symbol: str, annual_data: list[dict]) -> str:
    """Render OPM and NPM trend over 10 years."""
    if not annual_data:
        return ""

    fig, ax = plt.subplots(figsize=(12, 5))
    sorted_data = sorted(annual_data, key=lambda x: x.get("fiscal_year_end", x.get("year", "")))

    years = []
    opms = []
    npms = []
    for d in sorted_data:
        yr = d.get("fiscal_year_end", d.get("year", ""))
        opm = d.get("opm", d.get("operating_profit_margin", None))
        npm = d.get("npm", d.get("net_profit_margin", None))
        rev = d.get("revenue", d.get("sales", 0)) or 0
        op = d.get("operating_profit") or 0
        # Derive operating_profit when missing: PBT + interest + depreciation - other_income
        if not op and rev:
            pbt = d.get("profit_before_tax", 0) or 0
            interest = d.get("interest", 0) or 0
            dep = d.get("depreciation", 0) or 0
            oi = d.get("other_income", 0) or 0
            if pbt:
                op = pbt + interest + dep - oi
        np_ = d.get("net_income", d.get("net_profit", d.get("profit_after_tax", 0))) or 0

        if yr and rev:
            years.append(_fy_label(yr))
            opms.append(float(opm) if opm else (float(op) / float(rev) * 100 if rev else 0))
            npms.append(float(npm) if npm else (float(np_) / float(rev) * 100 if rev else 0))

    if not years:
        plt.close(fig)
        return ""

    ax.plot(years, opms, color=_ACCENT_1, marker="o", markersize=5, linewidth=2, label="Operating Margin %")
    ax.plot(years, npms, color=_GREEN, marker="s", markersize=5, linewidth=2, label="Net Profit Margin %")

    # Annotate latest values
    if opms:
        ax.annotate(f"{opms[-1]:.1f}%", (years[-1], opms[-1]), textcoords="offset points",
                     xytext=(10, 5), fontsize=10, color=_ACCENT_1, fontweight="bold")
    if npms:
        ax.annotate(f"{npms[-1]:.1f}%", (years[-1], npms[-1]), textcoords="offset points",
                     xytext=(10, -10), fontsize=10, color=_GREEN, fontweight="bold")

    ax.set_title(f"{symbol} — Margin Trend", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Margin %")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct_fmt))
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha="right")

    path = _chart_dir(symbol) / "margin_trend.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_roce_trend(symbol: str, ratios_data: list[dict]) -> str:
    """Render ROCE trend from Screener ratios."""
    if not ratios_data:
        return ""

    fig, ax = plt.subplots(figsize=(12, 5))
    sorted_data = sorted(ratios_data, key=lambda x: x.get("fiscal_year_end", x.get("year", "")))

    years = []
    roces = []
    for d in sorted_data:
        yr = d.get("fiscal_year_end", d.get("year", ""))
        roce = d.get("roce_pct", d.get("roce", d.get("return_on_capital_employed", None)))
        if yr and roce is not None:
            years.append(_fy_label(yr))
            roces.append(float(roce))

    if not years:
        plt.close(fig)
        return ""

    # Color bars by quality
    bar_colors = [_GREEN if r > 20 else (_YELLOW if r > 12 else _RED) for r in roces]
    ax.bar(years, roces, color=bar_colors, alpha=0.85, width=0.6)

    # Annotate values
    for i, (yr, r) in enumerate(zip(years, roces)):
        ax.annotate(f"{r:.0f}%", (yr, r), textcoords="offset points",
                     xytext=(0, 5), ha="center", fontsize=9, fontweight="bold")

    ax.axhline(y=15, color=_TEXT, linestyle="--", alpha=0.3, label="15% threshold")
    ax.set_title(f"{symbol} — ROCE Trend (Return on Capital Employed)", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("ROCE %")
    ax.yaxis.set_major_formatter(FuncFormatter(_pct_fmt))
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")

    path = _chart_dir(symbol) / "roce_trend.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_dupont_chart(symbol: str, dupont_data: list[dict] | dict) -> str:
    """Render DuPont decomposition: margin × turnover × leverage → ROE."""
    if not dupont_data:
        return ""

    # Handle dict format: {"source": ..., "years": [...]}
    if isinstance(dupont_data, dict):
        dupont_data = dupont_data.get("years", [])
    if not dupont_data:
        return ""

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1])

    sorted_data = sorted(dupont_data, key=lambda x: x.get("fiscal_year_end", x.get("date", "")))

    years = []
    margins = []
    turnovers = []
    leverages = []
    roes = []
    for d in sorted_data:
        yr = d.get("fiscal_year_end", d.get("date", ""))
        m = d.get("net_profit_margin", d.get("npm", None))
        t = d.get("asset_turnover", None)
        l = d.get("equity_multiplier", None)
        r = d.get("roe_dupont", d.get("roe", None))
        if yr and m is not None:
            years.append(_fy_label(yr))
            # DuPont values may be decimals (0.39 = 39%) — normalize to percentage
            m_val = float(m)
            r_val = float(r) if r else 0
            if m_val < 1:
                m_val *= 100
            if r_val < 1:
                r_val *= 100
            margins.append(m_val)
            turnovers.append(float(t) if t else 0)
            leverages.append(float(l) if l else 0)
            roes.append(r_val)

    if not years:
        plt.close(fig)
        return ""

    # Top: ROE and its drivers
    ax1.plot(years, margins, color=_ACCENT_1, marker="o", linewidth=2, label="Net Margin %")
    ax1.plot(years, roes, color=_TEXT, marker="D", linewidth=2.5, label="ROE %")
    ax1.set_ylabel("Percentage (%)")
    ax1.set_title(f"{symbol} — DuPont Decomposition (ROE = Margin × Turnover × Leverage)",
                   fontsize=14, fontweight="bold", pad=12)
    ax1.legend(loc="upper left", framealpha=0.8)
    ax1.grid(True, alpha=0.3)

    # Bottom: Turnover and Leverage
    ax2.plot(years, turnovers, color=_ACCENT_2, marker="s", linewidth=2, label="Asset Turnover (x)")
    ax2.plot(years, leverages, color=_YELLOW, marker="^", linewidth=2, label="Equity Multiplier (x)")
    ax2.set_ylabel("Ratio (x)")
    ax2.legend(loc="upper left", framealpha=0.8)
    ax2.grid(True, alpha=0.3)

    for a in [ax1, ax2]:
        a.set_xticks(range(len(years)))
        a.set_xticklabels(years, rotation=45, ha="right", fontsize=9)

    path = _chart_dir(symbol) / "dupont.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_cashflow_chart(symbol: str, annual_data: list[dict]) -> str:
    """Render CFO, CapEx, FCF bar chart over 10 years."""
    if not annual_data:
        return ""

    fig, ax = plt.subplots(figsize=(12, 5))
    sorted_data = sorted(annual_data, key=lambda x: x.get("fiscal_year_end", x.get("year", "")))

    years = []
    cfos = []
    fcfs = []
    for d in sorted_data:
        yr = d.get("fiscal_year_end", d.get("year", ""))
        cfo = d.get("cfo", d.get("cash_from_operating", d.get("operating_cash_flow", 0))) or 0
        fcf = d.get("free_cash_flow", 0) or 0
        # Derive FCF from CFO + CFI (investing outflow) when not available directly
        if not fcf and cfo:
            cfi = d.get("cfi", 0) or 0
            fcf = cfo + cfi  # cfi is typically negative (capex + investments)
        if yr:
            years.append(_fy_label(yr))
            cfos.append(float(cfo))
            fcfs.append(float(fcf))

    if not years or all(c == 0 for c in cfos):
        plt.close(fig)
        return ""

    x = range(len(years))
    width = 0.35

    ax.bar([i - width / 2 for i in x], cfos, width, label="Operating Cash Flow", color=_ACCENT_2, alpha=0.85)
    ax.bar([i + width / 2 for i in x], fcfs, width, label="Free Cash Flow", color=_GREEN, alpha=0.85)
    ax.axhline(y=0, color=_TEXT, linewidth=0.5)

    ax.set_title(f"{symbol} — Cash Flow (₹ Cr)", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("₹ Crores")
    ax.yaxis.set_major_formatter(FuncFormatter(_crore_fmt))
    ax.set_xticks(list(x))
    ax.set_xticklabels(years, rotation=45, ha="right")
    ax.legend(loc="upper left", framealpha=0.8)
    ax.grid(True, axis="y", alpha=0.3)

    path = _chart_dir(symbol) / "cashflow.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_fair_value_range(symbol: str, fair_value_data: dict) -> str:
    """Render horizontal bar showing bear/base/bull fair value vs current price."""
    if not fair_value_data:
        return ""

    pe_band = fair_value_data.get("pe_band", {})
    bear = pe_band.get("bear", 0) if isinstance(pe_band, dict) else 0
    base = fair_value_data.get("combined_fair_value", 0)
    if isinstance(base, dict):
        base = base.get("base", 0)
    bull = pe_band.get("bull", 0) if isinstance(pe_band, dict) else 0
    consensus = fair_value_data.get("consensus_target", 0)
    current = fair_value_data.get("current_price", 0)

    # Use consensus as bull if PE band bull is unreasonably high
    if bull > current * 5 and consensus:
        bull = consensus * 1.2

    if not all([bear, current]):
        return ""

    fig, ax = plt.subplots(figsize=(10, 3))

    # Range bar
    ax.barh(0, bull - bear, left=bear, height=0.4, color=_ACCENT_2, alpha=0.3, label="Fair Value Range")
    ax.barh(0, base - bear, left=bear, height=0.4, color=_ACCENT_2, alpha=0.5)

    # Markers
    ax.plot(current, 0, "D", color=_ACCENT_1, markersize=15, zorder=5, label=f"Current: ₹{current:,.0f}")
    ax.plot(bear, 0, "|", color=_RED, markersize=20, markeredgewidth=3, zorder=5)
    ax.plot(base, 0, "|", color=_GREEN, markersize=20, markeredgewidth=3, zorder=5)
    ax.plot(bull, 0, "|", color=_ACCENT_2, markersize=20, markeredgewidth=3, zorder=5)

    # Labels
    ax.annotate(f"Bear\n₹{bear:,.0f}", (bear, -0.35), ha="center", fontsize=10, color=_RED)
    ax.annotate(f"Base\n₹{base:,.0f}", (base, -0.35), ha="center", fontsize=10, color=_GREEN)
    ax.annotate(f"Bull\n₹{bull:,.0f}", (bull, -0.35), ha="center", fontsize=10, color=_ACCENT_2)

    margin = fair_value_data.get("margin_of_safety_pct", 0)
    signal = fair_value_data.get("signal", "")
    ax.set_title(f"{symbol} — Fair Value Range | {signal} | Margin of Safety: {margin:.0f}%",
                  fontsize=13, fontweight="bold", pad=12)
    ax.set_yticks([])
    ax.set_xlabel("Price (₹)")
    ax.legend(loc="upper right", framealpha=0.8)
    ax.grid(True, axis="x", alpha=0.3)

    path = _chart_dir(symbol) / "fair_value_range.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_expense_pie(symbol: str, expense_data: list[dict]) -> str:
    """Render expense breakdown pie chart."""
    if not expense_data:
        return ""

    fig, ax = plt.subplots(figsize=(8, 8))

    labels = []
    values = []
    for d in expense_data:
        name = d.get("name", d.get("item", ""))
        val = d.get("value", d.get("amount", 0)) or 0
        if name and float(val) > 0:
            labels.append(name[:25])  # truncate long names
            values.append(float(val))

    if not labels:
        plt.close(fig)
        return ""

    colors = [_ACCENT_1, _ACCENT_2, _GREEN, _YELLOW, _RED, _TEXT, "#8B5CF6", "#EC4899"]
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.0f%%",
        colors=colors[: len(values)], startangle=90,
        textprops={"color": _TEXT, "fontsize": 10},
    )
    for t in autotexts:
        t.set_fontsize(9)
        t.set_fontweight("bold")

    ax.set_title(f"{symbol} — Expense Breakdown", fontsize=14, fontweight="bold", pad=12)

    path = _chart_dir(symbol) / "expense_pie.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


def render_composite_radar(symbol: str, score_data: dict) -> str:
    """Render 8-factor composite score as a radar/spider chart."""
    if not score_data or "factors" not in score_data:
        return ""

    import numpy as np

    factors = score_data["factors"]
    if not isinstance(factors, (list, dict)):
        return ""

    if isinstance(factors, dict):
        labels = list(factors.keys())
        values = [float(v) for v in factors.values()]
    else:
        labels = [f.get("name", f"Factor {i}") for i, f in enumerate(factors)]
        values = [float(f.get("score", f.get("value", 50))) for f in factors]

    if not labels:
        return ""

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_closed = values + [values[0]]
    angles_closed = angles + [angles[0]]

    ax.plot(angles_closed, values_closed, color=_ACCENT_2, linewidth=2)
    ax.fill(angles_closed, values_closed, color=_ACCENT_2, alpha=0.25)

    # Reference circle at 50
    ref = [50] * (N + 1)
    ax.plot(angles_closed, ref, color=_TEXT, linewidth=0.5, linestyle="--", alpha=0.3)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], fontsize=8)

    overall = score_data.get("composite_score", score_data.get("overall", sum(values) / len(values)))
    ax.set_title(f"{symbol} — Composite Score: {overall:.0f}/100",
                  fontsize=14, fontweight="bold", pad=20)

    path = _chart_dir(symbol) / "composite_radar.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=_DARK_BG)
    plt.close(fig)
    return str(path)


# --- Master render function for MCP tool ---

_AVAILABLE_CHARTS = [
    "price", "pe", "delivery", "revenue_profit", "shareholding",
    "quarterly", "margin_trend", "roce_trend", "dupont", "cashflow",
    "fair_value_range", "expense_pie", "composite_radar",
]


def render_chart(symbol: str, chart_type: str, data: list | dict | None = None) -> dict:
    """Render a chart and return the file path.

    chart_type options:
      price           — Price + SMA50 + SMA200 (7yr)
      pe              — P/E ratio history (7yr)
      delivery        — Delivery % + volume (90 days)
      revenue_profit  — 10yr annual revenue & profit bars
      shareholding    — 12-quarter ownership trend
      quarterly       — 12-quarter revenue & profit bars
      margin_trend    — 10yr OPM & NPM lines
      roce_trend      — 10yr ROCE bars (color-coded)
      dupont          — DuPont decomposition (margin × turnover × leverage)
      cashflow        — 10yr CFO & FCF bars
      fair_value_range — Bear/base/bull vs current price
      expense_pie     — Expense breakdown pie
      composite_radar — 8-factor quality score radar

    data: Optional pre-fetched data. If None, fetches from DB.
    """
    from flowtracker.research.data_api import ResearchDataAPI

    symbol = symbol.upper()

    if chart_type not in _AVAILABLE_CHARTS:
        return {"error": f"Unknown chart type: {chart_type}", "available": _AVAILABLE_CHARTS}

    with ResearchDataAPI() as api:
        if chart_type == "price":
            path = render_price_chart(symbol, data or api.get_chart_data(symbol, "price"))
        elif chart_type == "pe":
            path = render_pe_chart(symbol, data or api.get_chart_data(symbol, "pe"))
        elif chart_type == "delivery":
            path = render_delivery_chart(symbol, data or api.get_delivery_trend(symbol, days=90))
        elif chart_type == "revenue_profit":
            path = render_revenue_profit_chart(symbol, data or api.get_annual_financials(symbol, years=10))
        elif chart_type == "shareholding":
            path = render_shareholding_chart(symbol, data or api.get_shareholding(symbol, quarters=12))
        elif chart_type == "quarterly":
            path = render_quarterly_chart(symbol, data or api.get_quarterly_results(symbol, quarters=12))
        elif chart_type == "margin_trend":
            path = render_margin_trend(symbol, data or api.get_annual_financials(symbol, years=10))
        elif chart_type == "roce_trend":
            path = render_roce_trend(symbol, data or api.get_screener_ratios(symbol, years=10))
        elif chart_type == "dupont":
            path = render_dupont_chart(symbol, data or api.get_dupont_decomposition(symbol))
        elif chart_type == "cashflow":
            path = render_cashflow_chart(symbol, data or api.get_annual_financials(symbol, years=10))
        elif chart_type == "fair_value_range":
            path = render_fair_value_range(symbol, data or api.get_fair_value(symbol))
        elif chart_type == "expense_pie":
            path = render_expense_pie(symbol, data or api.get_expense_breakdown(symbol))
        elif chart_type == "composite_radar":
            path = render_composite_radar(symbol, data or api.get_composite_score(symbol))
        else:
            path = ""

    if path:
        return {"path": path, "chart_type": chart_type, "symbol": symbol,
                "embed_markdown": f"![{symbol} {chart_type}]({path})"}
    return {"error": f"No data available for {chart_type} chart"}
