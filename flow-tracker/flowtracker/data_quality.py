"""Detect Screener line-item reclassification discontinuities.

Background: Screener mirrors company filings as-reported. When companies
change P&L/BS bucketing between years (Schedule III amendments, Ind-AS 116
lease transition, mergers/demergers), Screener captures the new bucketing
without restating prior years. This corrupts every multi-year trend metric
computed off `annual_financials`.

This module walks consecutive year pairs per symbol and flags lines that
jump >threshold while revenue stays flat (the control). Severity tiers:
HIGH = sign flip OR jump >500%; MEDIUM = 200-500%; LOW = 100-200%.

See `plans/screener-data-discontinuity.md` for full background.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# Lines monitored for reclass jumps. Scoped to **bucketing-prone** items:
# expense sub-buckets that get re-grouped (Schedule III, sector mandates) and
# balance-sheet liability buckets that get reshuffled (Ind-AS 116 leases,
# merger accounting). Treasury "investments" included — Screener moves
# between current/non-current frequently.
#
# Deliberately excluded (legitimate volatility, not bucketing):
#   - tax, net_income, profit_before_tax — real earnings swings, deferred tax
#   - cwip, net_block, total_assets, other_assets — capex cycles
#   - cash_and_bank, receivables, inventory — working capital cycles
#   - cfo, cfi, cff, net_cash_flow — capital allocation by design
#   - per-share / count fields (eps, num_shares, dividend_amount, equity_capital, price)
TREND_LINES: tuple[str, ...] = (
    "employee_cost", "other_income", "depreciation", "interest",
    "raw_material_cost", "power_and_fuel", "other_mfr_exp", "selling_and_admin",
    "other_expenses_detail", "total_expenses", "operating_profit",
    "reserves", "borrowings", "other_liabilities", "investments",
)

# Subset where a YoY sign flip is suspicious. Cash-flow lines naturally flip
# (already excluded above) and asset lines can flip via accounting reclass
# without semantic meaning, so we restrict sign-flip flagging to expense
# and liability/equity lines plus other_income.
SIGN_FLIP_LINES: tuple[str, ...] = (
    "employee_cost", "depreciation", "interest",
    "raw_material_cost", "power_and_fuel", "other_mfr_exp", "selling_and_admin",
    "other_expenses_detail", "total_expenses",
    "borrowings", "other_liabilities", "reserves",
    "other_income",
)

# Below this absolute crore value, relative changes and sign flips are treated
# as noise (Screener rounds and small companies have tiny line items).
MIN_MAGNITUDE_CR = 1.0

# Lines smaller than this fraction of revenue (on both sides of the pair) are
# skipped — even if reclassified, the impact on trend math is immaterial.
MIN_LINE_TO_REVENUE = 0.01

# Severity bands keyed off |YoY jump| (absolute fractional change).
# HIGH absorbs sign flips unconditionally — polarity reversal is a stronger
# reclass signal than any magnitude threshold.
JUMP_HIGH = 5.0      # > 500%
JUMP_MEDIUM = 2.0    # 200%-500%
JUMP_LOW = 1.0       # 100%-200%

SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass(frozen=True)
class Flag:
    symbol: str
    prior_fy: str
    curr_fy: str
    line: str
    prior_val: float
    curr_val: float
    jump_pct: float
    revenue_change_pct: float
    flag_type: str  # RECLASS or SIGN_FLIP
    severity: str   # HIGH / MEDIUM / LOW


def _severity(jump_abs: float, sign_flipped: bool) -> str | None:
    if sign_flipped:
        return "HIGH"
    if jump_abs >= JUMP_HIGH:
        return "HIGH"
    if jump_abs >= JUMP_MEDIUM:
        return "MEDIUM"
    if jump_abs >= JUMP_LOW:
        return "LOW"
    return None


def fetch_rows(
    conn: sqlite3.Connection, symbols: list[str] | None = None
) -> dict[str, list[dict]]:
    """Pull annual_financials rows ordered by symbol, fiscal_year_end ASC."""
    cols = ["symbol", "fiscal_year_end", "revenue", *TREND_LINES]
    sql = f"SELECT {', '.join(cols)} FROM annual_financials"
    params: tuple = ()
    if symbols:
        placeholders = ",".join("?" * len(symbols))
        sql += f" WHERE symbol IN ({placeholders})"
        params = tuple(symbols)
    sql += " ORDER BY symbol, fiscal_year_end"
    cur = conn.execute(sql, params)
    rows_by_symbol: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        d = dict(zip(cols, row, strict=True))
        rows_by_symbol.setdefault(d["symbol"], []).append(d)
    return rows_by_symbol


def detect(
    rows_by_symbol: dict[str, list[dict]],
    threshold_revenue: float = 0.30,
    min_severity: str = "LOW",
) -> list[Flag]:
    """Walk each symbol's year pairs and emit Flags above min_severity.

    rows_by_symbol: dict[symbol -> rows ordered ASC by fiscal_year_end].
                    Each row must have keys: revenue, fiscal_year_end, plus
                    TREND_LINES columns (None allowed).
    threshold_revenue: max |revenue change| (fraction) for a line jump to
                      qualify as reclass. Above this, growth could explain it.
    min_severity: lowest severity to emit. LOW emits everything; HIGH only
                  emits sign flips and >500% jumps.
    """
    cutoff = SEVERITY_RANK[min_severity]
    flags: list[Flag] = []
    for symbol, rows in rows_by_symbol.items():
        for prior, curr in zip(rows, rows[1:], strict=False):
            prior_rev = prior.get("revenue")
            curr_rev = curr.get("revenue")
            if prior_rev is None or curr_rev is None or abs(prior_rev) < MIN_MAGNITUDE_CR:
                continue
            rev_change = (curr_rev - prior_rev) / abs(prior_rev)
            # Revenue change is the "control" — only flag if revenue stayed flat
            # enough that the line-item jump can't be explained by genuine growth.
            if abs(rev_change) >= threshold_revenue:
                continue
            for line in TREND_LINES:
                p, c = prior.get(line), curr.get(line)
                if p is None or c is None:
                    continue
                if abs(p) < MIN_MAGNITUDE_CR and abs(c) < MIN_MAGNITUDE_CR:
                    continue
                if max(abs(p), abs(c)) / abs(prior_rev) < MIN_LINE_TO_REVENUE:
                    continue

                jump = (c - p) / abs(p) if abs(p) >= MIN_MAGNITUDE_CR else float("inf")
                sign_flipped = (
                    line in SIGN_FLIP_LINES
                    and p * c < 0
                    and abs(p) >= MIN_MAGNITUDE_CR
                    and abs(c) >= MIN_MAGNITUDE_CR
                )
                severity = _severity(abs(jump), sign_flipped)
                if severity is None or SEVERITY_RANK[severity] < cutoff:
                    continue
                flags.append(Flag(
                    symbol=symbol,
                    prior_fy=prior["fiscal_year_end"],
                    curr_fy=curr["fiscal_year_end"],
                    line=line,
                    prior_val=p,
                    curr_val=c,
                    jump_pct=jump * 100,
                    revenue_change_pct=rev_change * 100,
                    flag_type="SIGN_FLIP" if sign_flipped else "RECLASS",
                    severity=severity,
                ))
    return flags
