"""Tests for screener_charts cache invalidation on corporate actions.

Issue #20 of remediation-plan-post-review-2026-04-24: cached Screener
price charts in `screener_charts` go stale after a split/bonus lands
(pre-adjustment cliff at ex-date). `invalidate_screener_price_charts`
deletes the stale rows so next consumer triggers a fresh fetch.

Note: the underlying method name is `invalidate_screener_price_charts`
(not `invalidate_screener_charts` as the original spec drafted it). The
narrower name is correct — only chart_type='price' goes stale; PE is
adjustment-invariant (ratio) and survives the action.
"""

from __future__ import annotations

from pathlib import Path

from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_chart(
    store: FlowStore, symbol: str, chart_type: str, metric: str, date: str, value: float,
) -> None:
    """Insert one screener_charts row directly (mirrors fund-fetch path)."""
    store._conn.execute(
        "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
        "VALUES (?, ?, ?, ?, ?)",
        (symbol, chart_type, metric, date, value),
    )
    store._conn.commit()


def _chart_count(store: FlowStore, symbol: str, chart_type: str | None = None) -> int:
    if chart_type is None:
        sql = "SELECT COUNT(*) FROM screener_charts WHERE symbol = ?"
        return store._conn.execute(sql, (symbol,)).fetchone()[0]
    sql = "SELECT COUNT(*) FROM screener_charts WHERE symbol = ? AND chart_type = ?"
    return store._conn.execute(sql, (symbol, chart_type)).fetchone()[0]


def _action(symbol: str, action_type: str, ex_date: str = "2024-06-01") -> dict:
    """Build a minimal corporate_action dict for upsert."""
    return {
        "symbol": symbol,
        "ex_date": ex_date,
        "action_type": action_type,
        "ratio_text": "2:1" if action_type in ("split", "bonus") else "",
        "multiplier": 2.0 if action_type in ("split", "bonus") else None,
        "dividend_amount": 5.0 if action_type == "dividend" else None,
        "source": "bse",
    }


# ---------------------------------------------------------------------------
# Direct invalidation method
# ---------------------------------------------------------------------------

def test_invalidate_screener_charts_deletes_rows(tmp_db: Path) -> None:
    """Three SBIN price rows + two INFY price rows. Invalidate SBIN only."""
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-02-01", 610.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-03-01", 620.0)
    _seed_chart(store, "INFY", "price", "Price", "2024-01-01", 1500.0)
    _seed_chart(store, "INFY", "price", "Price", "2024-02-01", 1520.0)

    deleted = store.invalidate_screener_price_charts("SBIN")

    assert deleted == 3
    assert _chart_count(store, "SBIN") == 0
    assert _chart_count(store, "INFY") == 2


def test_invalidate_screener_charts_zero_when_none(tmp_db: Path) -> None:
    """Invalidating when no rows exist returns 0 and does not error."""
    store = FlowStore(db_path=tmp_db)
    deleted = store.invalidate_screener_price_charts("SBIN")
    assert deleted == 0


def test_invalidate_preserves_pe_chart(tmp_db: Path) -> None:
    """PE chart is adjustment-invariant — must survive invalidation."""
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "pe", "PE", "2024-01-01", 12.5)

    store.invalidate_screener_price_charts("SBIN")

    assert _chart_count(store, "SBIN", "price") == 0
    assert _chart_count(store, "SBIN", "pe") == 1


# ---------------------------------------------------------------------------
# Hook from upsert_corporate_actions
# ---------------------------------------------------------------------------

def test_upsert_corporate_action_split_invalidates_charts(tmp_db: Path) -> None:
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-02-01", 610.0)
    assert _chart_count(store, "SBIN", "price") == 2

    store.upsert_corporate_actions([_action("SBIN", "split")])

    assert _chart_count(store, "SBIN", "price") == 0


def test_upsert_corporate_action_bonus_invalidates_charts(tmp_db: Path) -> None:
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-02-01", 610.0)

    store.upsert_corporate_actions([_action("SBIN", "bonus")])

    assert _chart_count(store, "SBIN", "price") == 0


def test_upsert_corporate_action_dividend_does_NOT_invalidate(tmp_db: Path) -> None:
    """Sprint 0 convention: dividends don't shift the price axis."""
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-02-01", 610.0)

    store.upsert_corporate_actions([_action("SBIN", "dividend")])

    assert _chart_count(store, "SBIN", "price") == 2


def test_upsert_corporate_action_idempotent(tmp_db: Path) -> None:
    """Re-upserting the same action is a safe no-op (no error, no resurrection)."""
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)

    store.upsert_corporate_actions([_action("SBIN", "split")])
    assert _chart_count(store, "SBIN", "price") == 0

    # Second call: no chart rows exist anymore, but invalidation must not raise.
    store.upsert_corporate_actions([_action("SBIN", "split")])
    assert _chart_count(store, "SBIN", "price") == 0


def test_upsert_mixed_actions_invalidates_when_any_triggers(tmp_db: Path) -> None:
    """A batch with [dividend, split] still invalidates — split is what matters."""
    store = FlowStore(db_path=tmp_db)
    _seed_chart(store, "SBIN", "price", "Price", "2024-01-01", 600.0)
    _seed_chart(store, "SBIN", "price", "Price", "2024-02-01", 610.0)

    store.upsert_corporate_actions([
        _action("SBIN", "dividend", ex_date="2024-05-01"),
        _action("SBIN", "split", ex_date="2024-06-01"),
    ])

    assert _chart_count(store, "SBIN", "price") == 0
