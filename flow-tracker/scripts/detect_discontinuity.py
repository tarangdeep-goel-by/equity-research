#!/usr/bin/env python3
"""Detect Screener line-item reclassification discontinuities in annual_financials.

Validation-only tool for `plans/screener-data-discontinuity.md` Strategy 1, Step 1.
No DB writes. Reads ~/.local/share/flowtracker/flows.db, walks consecutive year
pairs per symbol, flags lines that jump >threshold while revenue is flat.

Usage:
  uv run python scripts/detect_discontinuity.py
  uv run python scripts/detect_discontinuity.py --symbols HDFCBANK,INFY,SIEMENS
  uv run python scripts/detect_discontinuity.py --min-severity HIGH --summary-only
  uv run python scripts/detect_discontinuity.py --output /tmp/flags.tsv
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "flowtracker" / "flows.db"

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

# Subset where a YoY sign flip is suspicious (cash-flow lines naturally flip,
# so they're excluded from sign-flip flagging though still checked for jumps).
SIGN_FLIP_LINES: tuple[str, ...] = (
    "employee_cost", "depreciation", "interest", "tax",
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


def fetch_rows(conn: sqlite3.Connection, symbols: list[str] | None) -> dict[str, list[dict]]:
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
    threshold_revenue: float,
    min_severity: str,
) -> list[Flag]:
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    cutoff = rank[min_severity]
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
                if severity is None or rank[severity] < cutoff:
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


def write_tsv(flags: list[Flag], out: Path | None) -> None:
    header = (
        "symbol\tprior_fy\tcurr_fy\tline\tprior_val\tcurr_val"
        "\tjump_pct\trev_change_pct\tflag_type\tseverity"
    )
    lines = [header]
    sev_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for f in sorted(flags, key=lambda x: (sev_rank[x.severity], x.symbol, x.curr_fy, x.line)):
        lines.append(
            f"{f.symbol}\t{f.prior_fy}\t{f.curr_fy}\t{f.line}\t"
            f"{f.prior_val:.1f}\t{f.curr_val:.1f}\t{f.jump_pct:+.0f}\t"
            f"{f.revenue_change_pct:+.1f}\t{f.flag_type}\t{f.severity}"
        )
    text = "\n".join(lines) + "\n"
    if out:
        out.write_text(text)
        print(f"Wrote {len(flags)} flags to {out}", file=sys.stderr)
    else:
        print(text)


def print_summary(flags: list[Flag], rows_by_symbol: dict[str, list[dict]]) -> None:
    by_sev = Counter(f.severity for f in flags)
    by_type = Counter(f.flag_type for f in flags)
    by_line = Counter(f.line for f in flags)
    by_symbol = Counter(f.symbol for f in flags)
    print(
        f"\nScanned: {len(rows_by_symbol)} symbols, "
        f"{sum(len(v) for v in rows_by_symbol.values())} rows",
        file=sys.stderr,
    )
    print(
        f"Flags: {len(flags)} total — "
        f"HIGH={by_sev.get('HIGH', 0)} MEDIUM={by_sev.get('MEDIUM', 0)} LOW={by_sev.get('LOW', 0)} "
        f"| RECLASS={by_type.get('RECLASS', 0)} SIGN_FLIP={by_type.get('SIGN_FLIP', 0)}",
        file=sys.stderr,
    )
    print(f"Distinct symbols flagged: {len(by_symbol)}", file=sys.stderr)
    print("Top 8 lines by flag count:", file=sys.stderr)
    for line, count in by_line.most_common(8):
        print(f"  {line:32s} {count}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols. Default: full universe.",
    )
    p.add_argument(
        "--threshold-revenue",
        type=float,
        default=0.30,
        help="Reclass flag only if |revenue change| stays below this fraction (default 0.30 = 30%%).",
    )
    p.add_argument(
        "--min-severity",
        choices=("LOW", "MEDIUM", "HIGH"),
        default="MEDIUM",
        help="Lowest severity to report. HIGH = sign flip or jump >500%%; "
             "MEDIUM = 200-500%%; LOW = 100-200%%. Default MEDIUM.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write TSV here. Default: stdout.",
    )
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip per-row TSV; print summary only.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    conn = sqlite3.connect(args.db)
    try:
        rows = fetch_rows(conn, symbols)
    finally:
        conn.close()
    flags = detect(rows, args.threshold_revenue, args.min_severity)
    if not args.summary_only:
        write_tsv(flags, args.output)
    print_summary(flags, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
