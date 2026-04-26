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

# Aggregate-bridging tolerances (Gemini review item #7).
#
# When a per-component flag fires (e.g. other_expenses_detail +290%) we ALSO
# check whether the parent aggregate (total_expenses for P&L, total_assets for
# BS) is conserved across the same year boundary. If the parent grows roughly
# in line with the business, the per-component break is a pure reshuffle from
# a *ratio* perspective — DuPont's cost / revenue computed off the SAME
# total_expenses both years still produces a true cost-to-income walk.
#
# P&L tolerance: total_expenses YoY change is allowed to be within
# ``revenue YoY ± BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH`` (additive band).
# 10pp is wider than the 5pp default the spec floats — chosen because banks
# (HDFCBANK FY26: revenue +3.6%, total_expenses +11.2%, gap 7.6pp post-merger
# from depreciation/amortisation step-ups) and any company in a capex / IT
# investment cycle routinely run cost growth a few points above revenue
# without a real reclass. 10pp catches the HDFCBANK case while still rejecting
# INFY FY26 (other_expenses_detail +3129% — total_expenses also explodes,
# trivially outside any reasonable band).
BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH = 0.10

# BS tolerance: |total_assets YoY change| ≤ 15%. Asset growth above 15% YoY
# in a single year is unusual outside M&A — and M&A IS the reshuffle pattern
# we want to flag, not bridge across. 15% accommodates organic balance-sheet
# growth in fast-growing private banks / NBFCs without admitting merger
# years.
BRIDGE_TOLERANCE_BS_ABS = 0.15

# Map per-component lines → which parent aggregate they roll up into. Used
# by `compute_aggregate_bridge` to decide which aggregate to compare.
PL_PARENT = "total_expenses"
BS_PARENT = "total_assets"

# P&L sub-components whose conservation we measure against `total_expenses`.
# Excludes `total_expenses` itself (it IS the parent) and `operating_profit`
# (a derived aggregate, not a component) and `other_income` (above-the-line
# revenue addition, not a cost bucket).
PL_EXPENSE_COMPONENTS: tuple[str, ...] = (
    "employee_cost", "raw_material_cost", "power_and_fuel", "other_mfr_exp",
    "selling_and_admin", "other_expenses_detail", "depreciation", "interest",
)

# Map flag.line → parent aggregate name. P&L sub-components bridge to
# total_expenses; BS sub-components bridge to total_assets. Lines not in
# this map (e.g. operating_profit, other_income, total_expenses itself,
# total_assets itself) are NOT bridge-able — `compute_aggregate_bridge`
# returns None for them so the legacy behaviour holds.
BRIDGE_PARENT_BY_LINE: dict[str, str] = {
    **{line: PL_PARENT for line in PL_EXPENSE_COMPONENTS},
    "borrowings": BS_PARENT,
    "other_liabilities": BS_PARENT,
    "reserves": BS_PARENT,
    "investments": BS_PARENT,
}


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


# ---------------------------------------------------------------------------
# Aggregate-level bridging (Gemini review item #7)
# ---------------------------------------------------------------------------


def _expense_sum(row: dict) -> float | None:
    """Sum of P&L expense sub-components on a row, treating None as 0.

    Returns None only when ALL sub-components are missing (no signal).
    Used as fallback when the row's stored `total_expenses` is absent.
    """
    parts = [row.get(line) for line in PL_EXPENSE_COMPONENTS]
    if all(p is None for p in parts):
        return None
    return sum((p or 0.0) for p in parts)


def _aggregate_value(row: dict, parent: str) -> float | None:
    """Return the parent aggregate value for `row`. Prefers stored value,
    falls back to summing sub-components for `total_expenses` (BS parent
    `total_assets` is always stored — no fallback)."""
    stored = row.get(parent)
    if stored is not None:
        return stored
    if parent == PL_PARENT:
        return _expense_sum(row)
    return None


def compute_aggregate_bridge(
    flag: dict,
    prior_row: dict | None,
    curr_row: dict | None,
    *,
    sibling_flagged_lines: set[str] | None = None,
) -> dict | None:
    """Decide whether a per-component flag is bridge-able by the parent
    aggregate's YoY conservation.

    Args:
        flag: a flag dict (must have `line`, `rev_change_pct`).
        prior_row, curr_row: the two annual_financials rows the flag spans.
        sibling_flagged_lines: per-symbol set of `parent` lines that are
            ALSO flagged elsewhere (e.g. `total_expenses` itself flagged
            in another row). When the parent aggregate is itself flagged,
            we never bridge — that's a real reshuffle, not a recategorisation.

    Returns:
        dict with keys {parent, parent_yoy_pct, conserved, tolerance_used}
        or None when:
          - flag.line has no defined parent (e.g. operating_profit)
          - either prior_row or curr_row is missing
          - parent aggregate cannot be computed on either side
        These cases preserve legacy behaviour (no bridging applied).
    """
    line = flag.get("line")
    parent = BRIDGE_PARENT_BY_LINE.get(line)
    if parent is None or prior_row is None or curr_row is None:
        return None

    p_val = _aggregate_value(prior_row, parent)
    c_val = _aggregate_value(curr_row, parent)
    if p_val is None or c_val is None or abs(p_val) < MIN_MAGNITUDE_CR:
        return None

    parent_yoy = (c_val - p_val) / abs(p_val)

    # Edge case: parent aggregate is itself flagged in another row → never
    # bridge across what is itself a real structural break.
    if sibling_flagged_lines and parent in sibling_flagged_lines:
        return {
            "parent": parent,
            "parent_yoy_pct": round(parent_yoy * 100, 2),
            "conserved": False,
            "tolerance_used": None,
            "reason": f"parent {parent} also flagged",
        }

    if parent == PL_PARENT:
        # P&L: total_expenses growth must be within revenue growth ± tolerance.
        rev_change_pct = flag.get("rev_change_pct", 0.0) or 0.0
        rev_change = rev_change_pct / 100.0
        gap = parent_yoy - rev_change  # positive = expenses grew faster than revenue
        conserved = abs(gap) <= BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH
        tolerance = BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH
    else:
        # BS: |total_assets YoY| ≤ tolerance (absolute).
        conserved = abs(parent_yoy) <= BRIDGE_TOLERANCE_BS_ABS
        tolerance = BRIDGE_TOLERANCE_BS_ABS

    return {
        "parent": parent,
        "parent_yoy_pct": round(parent_yoy * 100, 2),
        "conserved": bool(conserved),
        "tolerance_used": tolerance,
    }


def attach_aggregate_bridges(
    flag_dicts: list[dict],
    rows_by_fy: dict[str, dict],
) -> list[dict]:
    """Enrich flag dicts with `aggregate_bridge` field in-place-equivalent.

    Args:
        flag_dicts: list of flag dicts as returned by
            `FlowStore.get_data_quality_flags(symbol)`.
        rows_by_fy: annual_financials rows for the same symbol, keyed by
            `fiscal_year_end`. Each row should expose the same column dict
            shape used by the detector (`total_expenses`, `total_assets`,
            and the PL_EXPENSE_COMPONENTS keys).

    Returns:
        new list with each flag carrying `aggregate_bridge: dict | None`.
        Original dicts are not mutated.
    """
    # Sibling parents: which parent aggregates are themselves flagged anywhere.
    parent_lines = {PL_PARENT, BS_PARENT}
    sibling_parents = {
        f["line"] for f in flag_dicts if f.get("line") in parent_lines
    }

    enriched: list[dict] = []
    for f in flag_dicts:
        prior_row = rows_by_fy.get(f.get("prior_fy"))
        curr_row = rows_by_fy.get(f.get("curr_fy"))
        bridge = compute_aggregate_bridge(
            f, prior_row, curr_row, sibling_flagged_lines=sibling_parents,
        )
        new_f = dict(f)
        new_f["aggregate_bridge"] = bridge
        enriched.append(new_f)
    return enriched
