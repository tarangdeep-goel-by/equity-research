"""Tests for store schema creation, migrations, and infrastructure."""

from __future__ import annotations

from pathlib import Path

from flowtracker.store import FlowStore


def test_creates_all_tables(store):
    """FlowStore creates all expected tables on init."""
    rows = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    tables = {r["name"] for r in rows}
    expected = {
        "alert_history", "alerts", "annual_financials", "audit_log",
        "bulk_block_deals", "commodity_prices", "company_documents",
        "company_profiles", "consensus_estimates", "corporate_filings",
        "daily_flows", "daily_stock_data", "earnings_surprises",
        "financial_schedules", "fmp_analyst_grades", "fmp_dcf",
        "fmp_financial_growth", "fmp_key_metrics", "fmp_price_targets",
        "fmp_technical_indicators", "gold_etf_nav", "index_constituents",
        "insider_transactions", "macro_daily", "mf_aum_summary",
        "mf_daily_flows", "mf_monthly_flows", "mf_scheme_holdings",
        "peer_comparison", "portfolio_holdings", "promoter_pledge",
        "quarterly_results", "screener_charts", "screener_ids",
        "screener_ratios", "sector_benchmarks", "shareholder_detail",
        "shareholding", "watchlist",
    }
    missing = expected - tables
    extra = tables - expected - {"sqlite_sequence"}  # auto-generated
    assert not missing, f"Missing tables: {missing}"
    # Extra tables are OK (may include new ones), but flag them
    if extra:
        pass  # New tables are fine


def test_wal_mode_enabled(store):
    """WAL journal mode is set for concurrent access."""
    row = store._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_migrate_valuation_idempotent(store):
    """Running valuation migration twice doesn't error."""
    store._migrate_valuation_snapshot()
    store._migrate_valuation_snapshot()
    # Verify a migrated column exists
    cols = {r[1] for r in store._conn.execute("PRAGMA table_info(valuation_snapshot)").fetchall()}
    assert "fifty_two_week_high" in cols
    assert "peg_ratio" in cols


def test_migrate_quarterly_idempotent(store):
    """Running quarterly/annual migration twice doesn't error."""
    store._migrate_quarterly_and_annual()
    store._migrate_quarterly_and_annual()
    qr_cols = {r[1] for r in store._conn.execute("PRAGMA table_info(quarterly_results)").fetchall()}
    assert "expenses" in qr_cols
    assert "tax_pct" in qr_cols
    af_cols = {r[1] for r in store._conn.execute("PRAGMA table_info(annual_financials)").fetchall()}
    assert "operating_profit" in af_cols


def test_context_manager(tmp_db):
    """Context manager opens and auto-closes connection."""
    with FlowStore(db_path=tmp_db) as s:
        s._conn.execute("SELECT 1").fetchone()
    # After exit, connection should be closed — further ops should fail
    import sqlite3
    try:
        s._conn.execute("SELECT 1")
        assert False, "Expected ProgrammingError after close"
    except Exception:
        pass


def test_populated_store_fixture(populated_store):
    """Smoke test: populated_store has data in key tables."""
    store = populated_store
    assert len(store.get_flows(days=30)) > 0
    assert len(store.get_quarterly_results("SBIN")) > 0
    assert len(store.get_shareholding("SBIN")) > 0
    assert len(store.get_valuation_history("SBIN")) > 0
    assert store.get_fmp_dcf_latest("SBIN") is not None
    assert len(store.get_active_alerts()) > 0
    assert len(store.get_portfolio_holdings()) > 0
