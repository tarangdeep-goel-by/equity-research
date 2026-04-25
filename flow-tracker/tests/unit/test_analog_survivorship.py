"""PR-13 tests — survivorship-aware universe + cliff reconciliation.

Covers issues #3 (survivorship bias) and #23 (parked-symbol opacity) from
plans/remediation-plan-post-review-2026-04-24.md.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from flowtracker.store import FlowStore

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _insert_daily(
    store: FlowStore, symbol: str, dates_and_prices: list[tuple[str, float]],
    *, adj_close_override: dict[str, float] | None = None,
) -> None:
    for trade_date, close in dates_and_prices:
        store._conn.execute(
            "INSERT OR REPLACE INTO daily_stock_data "
            "(date, symbol, open, high, low, close, prev_close, volume, "
            " turnover, delivery_qty, delivery_pct, adj_close, adj_factor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, symbol.upper(), close, close, close, close, close,
             1000, 1000.0 * close, 500, 50.0,
             (adj_close_override or {}).get(trade_date), 1.0),
        )
    store._conn.commit()


def _insert_index(store: FlowStore, symbols: list[str]) -> None:
    for s in symbols:
        store._conn.execute(
            "INSERT OR REPLACE INTO index_constituents "
            "(symbol, index_name, company_name, industry) VALUES (?, ?, ?, ?)",
            (s, "NIFTY 50", f"{s} Ltd", "TestIndustry"),
        )
    store._conn.commit()


def _long_history(n_rows: int, end: date) -> list[tuple[str, float]]:
    return [((end - timedelta(days=i)).isoformat(), 100.0 + i * 0.01)
            for i in range(n_rows)]


def _build_cliff_series(today: date, cliff_close: float) -> list[tuple[str, float]]:
    """5 stable @100, 1 cliff day, 4 stable @cliff_close — used by 4 cliff tests."""
    series = [((today - timedelta(days=10 - i)).isoformat(), 100.0) for i in range(5)]
    series.append(((today - timedelta(days=5)).isoformat(), cliff_close))
    series += [((today - timedelta(days=4 - i)).isoformat(), cliff_close)
               for i in range(4)]
    return series


# Schema --------------------------------------------------------------

def test_delisted_symbols_table_exists(store: FlowStore) -> None:
    cols = {r["name"] for r in store._conn.execute("PRAGMA table_info(delisted_symbols)")}
    assert {"symbol", "last_active_date", "observations", "reason"} <= cols


def test_unresolved_cliffs_table_exists(store: FlowStore) -> None:
    cols = {r["name"] for r in store._conn.execute("PRAGMA table_info(unresolved_cliffs)")}
    assert {"symbol", "trade_date", "prev_close", "close", "return_pct"} <= cols


# Round-trip ----------------------------------------------------------

def test_upsert_and_get_delisted_symbols(store: FlowStore) -> None:
    rows = [
        {"symbol": "FOO", "last_active_date": "2020-01-15",
         "observations": 1234, "reason": "gap_180d"},
        {"symbol": "BAR", "last_active_date": "2018-06-30",
         "observations": 5678, "reason": "manually_parked"},
        {"symbol": "BAZ", "last_active_date": None,
         "observations": None, "reason": "unknown"},
    ]
    assert store.upsert_delisted_symbols(rows) == 3
    fetched = {r["symbol"]: r for r in store.get_delisted_symbols()}
    assert set(fetched) == {"FOO", "BAR", "BAZ"}
    assert fetched["FOO"]["reason"] == "gap_180d"
    assert fetched["BAR"]["observations"] == 5678


# Gap detection -------------------------------------------------------

def test_detect_delisted_from_gaps_finds_old_symbols(store: FlowStore) -> None:
    today = date.today()
    _insert_daily(store, "ACTIVE",
                  [((today - timedelta(days=i)).isoformat(), 100.0) for i in range(5)])
    _insert_daily(store, "DELISTED",
                  [((today - timedelta(days=200 + i)).isoformat(), 50.0) for i in range(5)])
    _insert_daily(store, "RECENTGAP",
                  [((today - timedelta(days=100 + i)).isoformat(), 75.0) for i in range(5)])
    found = store.detect_delisted_from_gaps(180)
    syms = {r["symbol"] for r in found}
    assert "DELISTED" in syms
    assert "ACTIVE" not in syms
    assert "RECENTGAP" not in syms
    delisted = next(r for r in found if r["symbol"] == "DELISTED")
    assert delisted["reason"] == "gap_180d"
    assert delisted["observations"] == 5


# Universe semantics --------------------------------------------------

def test_target_symbols_include_delisted_unions(store: FlowStore) -> None:
    from scripts.materialize_analog_states import target_symbols
    today = date.today()
    indexed = ["IDX1", "IDX2", "IDX3", "IDX4", "IDX5"]
    _insert_index(store, indexed)
    for sym in ("OLD1", "OLD2", "OLD3"):
        _insert_daily(store, sym, _long_history(3000, today))
    assert set(target_symbols(store, include_delisted=False)) == set(indexed)
    extended = target_symbols(store, include_delisted=True)
    assert set(extended) == set(indexed) | {"OLD1", "OLD2", "OLD3"}
    assert len(extended) == 8


def test_target_symbols_recent_ipo_stays_in_cohort(store: FlowStore) -> None:
    """Indexed symbol with <3000 rows must NOT be dropped by the union."""
    from scripts.materialize_analog_states import target_symbols
    today = date.today()
    _insert_index(store, ["NEWIPO"])
    _insert_daily(store, "NEWIPO", _long_history(500, today))
    assert "NEWIPO" in target_symbols(store, include_delisted=True)


# Cliff reconciliation -----------------------------------------------

def test_reconcile_price_cliffs_flags_unexplained_drop(store: FlowStore) -> None:
    from scripts.reconcile_price_cliffs import reconcile
    _insert_daily(store, "FALLER", _build_cliff_series(date.today(), 40.0))
    unresolved = reconcile(store, only_symbol="FALLER", threshold_pct=40.0)
    assert len(unresolved) == 1
    assert unresolved[0]["symbol"] == "FALLER"
    assert unresolved[0]["return_pct"] < -50
    assert len(store.get_unresolved_cliffs("FALLER")) == 1


def test_reconcile_price_cliffs_skips_explained_drop(store: FlowStore) -> None:
    from scripts.reconcile_price_cliffs import reconcile
    today = date.today()
    cliff_date = (today - timedelta(days=5)).isoformat()
    _insert_daily(store, "SPLITTER", _build_cliff_series(today, 40.0))
    store.upsert_corporate_actions(
        [{"symbol": "SPLITTER", "ex_date": cliff_date, "action_type": "split",
          "ratio_text": "5:2", "multiplier": 2.5, "source": "test"}],
        recompute_adj_close=False,
    )
    assert reconcile(store, only_symbol="SPLITTER", threshold_pct=40.0) == []


def test_reconcile_price_cliffs_uses_adj_close_when_present(store: FlowStore) -> None:
    """adj_close steady → no cliff, even though raw close drops 60%."""
    from scripts.reconcile_price_cliffs import reconcile
    today = date.today()
    raw_series = _build_cliff_series(today, 40.0)
    adj_overrides = {d: 100.0 for d, _ in raw_series}
    _insert_daily(store, "ADJUSTED", raw_series, adj_close_override=adj_overrides)
    assert reconcile(store, only_symbol="ADJUSTED", threshold_pct=40.0) == []


def test_reconcile_price_cliffs_corp_action_within_two_days(store: FlowStore) -> None:
    from scripts.reconcile_price_cliffs import reconcile
    today = date.today()
    _insert_daily(store, "OFFBYONE", _build_cliff_series(today, 40.0))
    one_day_off = (today - timedelta(days=6)).isoformat()
    store.upsert_corporate_actions(
        [{"symbol": "OFFBYONE", "ex_date": one_day_off, "action_type": "split",
          "ratio_text": "5:2", "multiplier": 2.5, "source": "test"}],
        recompute_adj_close=False,
    )
    assert reconcile(store, only_symbol="OFFBYONE", threshold_pct=40.0) == []


# CLI smoke -----------------------------------------------------------

def test_cli_smoke_reconcile_script() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "reconcile_price_cliffs.py"), "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "reconcile" in result.stdout.lower() or "cliff" in result.stdout.lower()
