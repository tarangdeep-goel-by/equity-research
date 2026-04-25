"""Detect Screener line-item reclassification discontinuities.

Background: Screener mirrors company filings as-reported. When companies
change P&L/BS bucketing between years (Schedule III amendments, Ind-AS 116
lease transition, mergers/demergers), Screener captures the new bucketing
without restating prior years. This corrupts every multi-year trend metric
computed off `annual_financials`.

This module walks consecutive year pairs per symbol and flags lines that
jump >threshold while the appropriate control stays flat. Severity tiers:
HIGH = sign flip OR jump >500%; MEDIUM = 200-500%; LOW = 100-200%.

Detector splits lines into two groups (Gemini review fix):
  - P&L lines  : compare to revenue (control); skip when revenue jumped >30%
                 (a 50% revenue rise can plausibly drive a 50% expense rise).
  - BS lines   : compare to total_assets (better denominator for banks/financials);
                 NO revenue control (M&A reshuffles BS even when revenue jumps).

See `plans/screener-data-discontinuity.md` for full background.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# P&L expense / income lines monitored for reclass jumps. Bucketing-prone:
# expense sub-buckets that get re-grouped (Schedule III, sector mandates).
PL_LINES: tuple[str, ...] = (
    "employee_cost", "other_income", "depreciation", "interest",
    "raw_material_cost", "power_and_fuel", "other_mfr_exp", "selling_and_admin",
    "other_expenses_detail", "total_expenses", "operating_profit",
)

# Balance sheet liability/equity lines + treasury investments. Reshuffled by
# Ind-AS 116 lease accounting, merger consolidation, current/non-current
# reclassification. Materiality denominated in total_assets, not revenue.
BS_LINES: tuple[str, ...] = (
    "reserves", "borrowings", "other_liabilities", "investments",
)

TREND_LINES: tuple[str, ...] = PL_LINES + BS_LINES

# Lines where a YoY polarity reversal is suspicious. Excluded after Gemini
# review:
#   - reserves: legitimately flips when accumulated deficit exceeds capital.
#   - other_income: flips when one-off gains are followed by MTM losses.
SIGN_FLIP_LINES: tuple[str, ...] = (
    "employee_cost", "depreciation", "interest",
    "raw_material_cost", "power_and_fuel", "other_mfr_exp", "selling_and_admin",
    "other_expenses_detail", "total_expenses",
    "borrowings", "other_liabilities",
)

# Below this absolute crore value, relative changes and sign flips are treated
# as noise (Screener rounds and small companies have tiny line items).
MIN_MAGNITUDE_CR = 1.0

# Lines smaller than this fraction of their denominator (revenue for P&L,
# total_assets for BS) on both sides of the pair are skipped — even if
# reclassified, the impact on trend math is immaterial.
MIN_LINE_TO_DENOMINATOR = 0.01

# Severity bands keyed off |YoY jump| (absolute fractional change).
# HIGH absorbs sign flips unconditionally — polarity reversal is a stronger
# reclass signal than any magnitude threshold.
JUMP_HIGH = 5.0      # > 500%
JUMP_MEDIUM = 2.0    # 200%-500%
JUMP_LOW = 1.0       # 100%-200%

SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def longest_unflagged_window(
    annuals_desc: list, flags: list[dict]
) -> tuple[list, list[dict]]:
    """Return the contiguous segment **anchored at the most recent year** that
    contains no flag boundary, plus the flags that excluded other rows.

    annuals_desc: list of objects/dicts with `.fiscal_year_end` or ['fiscal_year_end'].
                  Must be ordered DESC by fiscal_year_end (newest first).
    flags: list of flag dicts. A flag with curr_fy=X means the bucketing
           changed between (X-1) and X, so X cannot be aggregated with the
           year before it.

    Recency anchor (Gemini review fix): we always return the segment containing
    annuals_desc[0] (the newest year), even when an older segment is longer.
    Returning a stale 5-year segment from before a merger looks current to a
    downstream agent but represents an obsolete era.

    If the recent segment is too short for a tool's needs (e.g. F-score wants
    2 years and the recent segment is just 1), the tool should abstain rather
    than fall back to a detached historical segment.
    """
    if not annuals_desc:
        return [], []

    def _fy(obj) -> str:
        return obj["fiscal_year_end"] if isinstance(obj, dict) else obj.fiscal_year_end

    flagged_curr_fys = {f["curr_fy"] for f in flags}
    if not flagged_curr_fys:
        return list(annuals_desc), []

    # Walk DESC from index 0; stop when crossing a flag boundary.
    # annuals_desc[i-1] is the newer year of consecutive pair (i-1, i).
    # A flag with curr_fy = annuals_desc[i-1].fy marks a break before this row.
    recent: list = [annuals_desc[0]]
    for i in range(1, len(annuals_desc)):
        if _fy(annuals_desc[i - 1]) in flagged_curr_fys:
            break
        recent.append(annuals_desc[i])

    recent_fys = {_fy(a) for a in recent}
    # A flag's effect is to terminate the segment by excluding its prior_fy.
    # If the flag's prior_fy is not in the recent segment, that flag caused
    # part of the history to be cut off — surface it.
    dropped = [f for f in flags if f["prior_fy"] not in recent_fys]
    return recent, dropped


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
    """Pull annual_financials rows ordered by symbol, fiscal_year_end ASC.

    total_assets is fetched as the BS-side materiality denominator.
    """
    cols = ["symbol", "fiscal_year_end", "revenue", "total_assets", *TREND_LINES]
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


def _check_line(
    line: str,
    p: float | None,
    c: float | None,
    denom_prior: float,
) -> tuple[float, bool] | None:
    """Apply materiality + jump computation. Returns (jump, sign_flipped) or None
    if line should be skipped (immaterial / null / both-sides-tiny / bad denom).
    """
    if p is None or c is None:
        return None
    if abs(p) < MIN_MAGNITUDE_CR and abs(c) < MIN_MAGNITUDE_CR:
        return None
    if abs(denom_prior) < MIN_MAGNITUDE_CR:
        return None
    if max(abs(p), abs(c)) / abs(denom_prior) < MIN_LINE_TO_DENOMINATOR:
        return None

    jump = (c - p) / abs(p) if abs(p) >= MIN_MAGNITUDE_CR else float("inf")
    sign_flipped = (
        line in SIGN_FLIP_LINES
        and p * c < 0
        and abs(p) >= MIN_MAGNITUDE_CR
        and abs(c) >= MIN_MAGNITUDE_CR
    )
    return jump, sign_flipped


def detect(
    rows_by_symbol: dict[str, list[dict]],
    threshold_revenue: float = 0.30,
    min_severity: str = "LOW",
) -> list[Flag]:
    """Walk each symbol's year pairs and emit Flags above min_severity.

    rows_by_symbol: dict[symbol -> rows ordered ASC by fiscal_year_end].
                    Each row must have keys: revenue, total_assets,
                    fiscal_year_end, plus PL_LINES + BS_LINES columns.
    threshold_revenue: max |revenue change| (fraction) for a P&L line jump
                      to qualify as reclass. Above this, growth could explain
                      the line move. Does NOT apply to BS items (M&A drives
                      both revenue jump AND BS reshuffle, so revenue control
                      would suppress real reclasses).
    min_severity: lowest severity to emit. LOW emits everything; HIGH only
                  emits sign flips and >500% jumps.
    """
    cutoff = SEVERITY_RANK[min_severity]
    flags: list[Flag] = []
    for symbol, rows in rows_by_symbol.items():
        for prior, curr in zip(rows, rows[1:], strict=False):
            prior_rev = prior.get("revenue")
            curr_rev = curr.get("revenue")
            prior_ta = prior.get("total_assets")
            if prior_rev is None or curr_rev is None or abs(prior_rev) < MIN_MAGNITUDE_CR:
                continue
            rev_change = (curr_rev - prior_rev) / abs(prior_rev)

            # Revenue control vetoes P&L flags (only) when revenue swung > threshold.
            pl_revenue_gate_open = abs(rev_change) < threshold_revenue

            for line in TREND_LINES:
                p, c = prior.get(line), curr.get(line)
                # Per-group denominator + per-group revenue gate.
                if line in PL_LINES:
                    if not pl_revenue_gate_open:
                        continue
                    denom = prior_rev
                else:
                    # BS items: prefer total_assets; fall back to revenue if TA missing.
                    denom = (
                        prior_ta
                        if (prior_ta is not None and abs(prior_ta) >= MIN_MAGNITUDE_CR)
                        else prior_rev
                    )

                check = _check_line(line, p, c, denom)
                if check is None:
                    continue
                jump, sign_flipped = check
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
