"""Thesis tracker — structured conviction tracking per stock with falsifiable conditions."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)

_VAULT_BASE = Path.home() / "vault" / "stocks"


@dataclass
class ThesisCondition:
    """A single falsifiable condition in a thesis."""
    metric: str         # e.g. "quarterly_results.revenue_growth_yoy"
    operator: str       # ">", "<", ">=", "<=", "=="
    threshold: float
    label: str
    status: str = "pending"  # pending, passing, failing, stale


@dataclass
class ThesisTracker:
    """Full thesis tracker for a stock."""
    symbol: str
    entry_price: float | None = None
    entry_date: str | None = None
    conditions: list[ThesisCondition] = field(default_factory=list)
    file_path: Path | None = None


def load_tracker(symbol: str) -> ThesisTracker | None:
    """Load thesis tracker from ~/vault/stocks/{SYMBOL}/thesis-tracker.md."""
    path = _VAULT_BASE / symbol.upper() / "thesis-tracker.md"
    if not path.exists():
        return None

    text = path.read_text()
    # Parse YAML frontmatter between --- delimiters
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    if not meta or "symbol" not in meta:
        return None

    conditions = []
    for c in meta.get("conditions", []):
        conditions.append(ThesisCondition(
            metric=c["metric"],
            operator=c.get("operator", ">"),
            threshold=float(c["threshold"]),
            label=c.get("label", ""),
            status=c.get("status", "pending"),
        ))

    return ThesisTracker(
        symbol=meta["symbol"],
        entry_price=meta.get("entry_price"),
        entry_date=meta.get("entry_date"),
        conditions=conditions,
        file_path=path,
    )


def evaluate_conditions(tracker: ThesisTracker, store: FlowStore) -> list[ThesisCondition]:
    """Evaluate each condition against latest data. Updates status in-place and returns all conditions."""
    symbol = tracker.symbol

    for cond in tracker.conditions:
        value = _resolve_metric(store, symbol, cond.metric)
        if value is None:
            cond.status = "stale"
            continue

        if _compare(value, cond.operator, cond.threshold):
            cond.status = "passing"
        else:
            cond.status = "failing"

    return tracker.conditions


def _resolve_metric(store: FlowStore, symbol: str, metric: str) -> float | None:
    """Resolve a metric path like 'quarterly_results.revenue_growth_yoy' to a value."""
    try:
        parts = metric.split(".", 1)
        table = parts[0]
        field_name = parts[1] if len(parts) > 1 else None

        if table == "quarterly_results" and field_name:
            # Get latest 2 quarters for YoY comparison
            rows = store._conn.execute(
                "SELECT * FROM quarterly_results WHERE symbol = ? ORDER BY quarter_end DESC LIMIT 8",
                (symbol,),
            ).fetchall()
            if not rows:
                return None

            if field_name == "revenue_growth_yoy" and len(rows) >= 5:
                # Compare Q0 vs Q4 (same quarter last year)
                curr = rows[0]["revenue"]
                prev = rows[4]["revenue"]
                if prev and prev > 0 and curr:
                    return (curr - prev) / prev
                return None
            elif field_name == "net_income_growth_yoy" and len(rows) >= 5:
                curr = rows[0]["net_income"]
                prev = rows[4]["net_income"]
                if prev and prev > 0 and curr:
                    return (curr - prev) / prev
                return None
            elif field_name in ("operating_margin", "net_margin", "eps"):
                return rows[0][field_name]

        elif table == "shareholding" and field_name:
            if "change" in field_name:
                cat = field_name.replace("_pct_change", "").upper()
                rows = store._conn.execute(
                    "SELECT percentage FROM shareholding WHERE symbol = ? AND category = ? "
                    "ORDER BY quarter_end DESC LIMIT 2",
                    (symbol, cat),
                ).fetchall()
                if len(rows) >= 2:
                    return rows[0]["percentage"] - rows[1]["percentage"]
                return None
            else:
                category = field_name.upper()
                row = store._conn.execute(
                    "SELECT percentage FROM shareholding WHERE symbol = ? AND category = ? "
                    "ORDER BY quarter_end DESC LIMIT 1",
                    (symbol, category),
                ).fetchone()
                return row["percentage"] if row else None

        elif table == "annual_financials" and field_name:
            row = store._conn.execute(
                "SELECT * FROM annual_financials WHERE symbol = ? ORDER BY fiscal_year_end DESC LIMIT 1",
                (symbol,),
            ).fetchall()
            if not row:
                return None
            r = row[0]
            if field_name == "roce":
                # ROCE from screener_ratios table
                ratio_row = store._conn.execute(
                    "SELECT roce_pct FROM screener_ratios WHERE symbol = ? ORDER BY fiscal_year_end DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
                return ratio_row["roce_pct"] / 100 if ratio_row and ratio_row["roce_pct"] else None
            elif field_name in dict(r).keys():
                return r[field_name]

        elif table == "valuation_snapshot" and field_name:
            row = store._conn.execute(
                "SELECT * FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row and field_name in dict(row).keys():
                return row[field_name]

        elif table == "fmp_dcf" and field_name == "upside":
            row = store._conn.execute(
                "SELECT dcf, stock_price FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row and row["dcf"] and row["stock_price"] and row["stock_price"] > 0:
                return (row["dcf"] - row["stock_price"]) / row["stock_price"] * 100

    except Exception as e:
        logger.warning("Failed to resolve metric %s for %s: %s", metric, symbol, e)

    return None


def _compare(value: float, operator: str, threshold: float) -> bool:
    """Compare value against threshold with operator."""
    if operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == "==":
        return abs(value - threshold) < 0.001
    return False


def update_tracker_file(tracker: ThesisTracker) -> None:
    """Rewrite the tracker markdown with updated condition statuses."""
    if not tracker.file_path:
        return

    meta: dict = {
        "symbol": tracker.symbol,
    }
    if tracker.entry_price is not None:
        meta["entry_price"] = tracker.entry_price
    if tracker.entry_date:
        meta["entry_date"] = tracker.entry_date

    meta["conditions"] = [
        {
            "metric": c.metric,
            "operator": c.operator,
            "threshold": c.threshold,
            "label": c.label,
            "status": c.status,
        }
        for c in tracker.conditions
    ]

    content = "---\n" + yaml.dump(meta, default_flow_style=False, sort_keys=False) + "---\n"
    tracker.file_path.write_text(content)


def get_all_trackers() -> list[ThesisTracker]:
    """Scan vault for all thesis tracker files."""
    trackers = []
    if not _VAULT_BASE.exists():
        return trackers

    for symbol_dir in sorted(_VAULT_BASE.iterdir()):
        if symbol_dir.is_dir():
            tracker = load_tracker(symbol_dir.name)
            if tracker:
                trackers.append(tracker)

    return trackers
