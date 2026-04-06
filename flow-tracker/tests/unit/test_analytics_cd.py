"""Tests for Phase C+D analytical methods."""
from __future__ import annotations

import pytest

from flowtracker.store import FlowStore
from flowtracker.research.data_api import ResearchDataAPI


def _populate_mf(store, symbol="TESTCO"):
    """Insert MF scheme holdings for 2 months."""
    for month, schemes in [
        ("2026-01", [("HDFC Equity", "HDFC", 100, 50.0, 1.2), ("ICICI Value", "ICICI", 80, 40.0, 0.8)]),
        ("2026-02", [("HDFC Equity", "HDFC", 120, 60.0, 1.4), ("ICICI Value", "ICICI", 80, 40.0, 0.8), ("Axis Growth", "AXIS", 50, 25.0, 0.5)]),
    ]:
        for scheme, amc, qty, val, nav_pct in schemes:
            store._conn.execute(
                "INSERT INTO mf_scheme_holdings (month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (month, amc, scheme, "INE001", f"{symbol} LTD", qty, val, nav_pct),
            )
    store._conn.commit()


def _populate_delivery(store, symbol="TESTCO"):
    """Insert daily stock data with delivery."""
    from datetime import date, timedelta

    base = date(2026, 1, 1)
    for i in range(60):
        d = base + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        # Delivery trending up
        dp = 40 + i * 0.3
        store._conn.execute(
            "INSERT INTO daily_stock_data (date, symbol, open, high, low, close, prev_close, volume, turnover, delivery_qty, delivery_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (d.isoformat(), symbol, 100, 105, 95, 102, 100, 100000 + i * 1000, 10000000, int(100000 * dp / 100), dp),
        )
    store._conn.commit()


def _populate_commodities(store):
    """Insert commodity prices."""
    from datetime import date, timedelta

    base = date(2025, 4, 1)
    for i in range(300):
        d = base + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        store._conn.execute(
            "INSERT OR IGNORE INTO commodity_prices (date, symbol, price, unit) VALUES (?, ?, ?, ?)",
            (d.isoformat(), "GOLD", 2000 + i * 0.5, "USD/oz"),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO commodity_prices (date, symbol, price, unit) VALUES (?, ?, ?, ?)",
            (d.isoformat(), "GOLD_INR", 60000 + i * 20, "INR/10g"),
        )
    store._conn.commit()


def _populate_dividends(store, symbol="TESTCO"):
    """Insert corporate actions (dividends)."""
    for yr, div in [(2022, 5.0), (2023, 6.0), (2024, 7.0), (2025, 8.0)]:
        store._conn.execute(
            "INSERT INTO corporate_actions (symbol, ex_date, action_type, dividend_amount, ratio_text, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, f"{yr}-08-15", "dividend", div, str(div), "test"),
        )
    store._conn.commit()


class TestMFConviction:
    def test_returns_scheme_count(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_mf(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_mf_conviction("TESTCO")
        assert result["available"] is True
        assert result["schemes_holding"] == 3  # Feb: HDFC, ICICI, Axis
        assert result["amcs_holding"] == 3

    def test_detects_adding_trend(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_mf(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_mf_conviction("TESTCO")
        assert result["scheme_trend"] == "adding"
        assert result["scheme_change"] == 1  # 3 - 2

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_mf_conviction("NONE")
        assert result.get("available") is False


class TestDeliveryAnalysis:
    def test_returns_trend(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_delivery(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_delivery_analysis("TESTCO", days=90)
        assert result["available"] is True
        assert result["trend"] in ("rising", "falling", "stable")
        assert "avg_delivery_pct" in result

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_delivery_analysis("NONE")
        assert result.get("available") is False


class TestCommoditySnapshot:
    def test_returns_gold_prices(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_commodities(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_commodity_snapshot()
        assert "gold" in result
        assert "price" in result["gold"]
        assert "change_1m_pct" in result["gold"]

    def test_empty_returns_unavailable(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_commodity_snapshot()
        assert result.get("available") is False


class TestDividendPolicy:
    def test_returns_policy(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_dividends(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_dividend_policy("TESTCO")
        assert result["available"] is True
        assert result["years_of_history"] == 4
        assert len(result["annual_policy"]) == 4

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_dividend_policy("NONE")
        assert result.get("available") is False


class TestInstitutionalConsensus:
    def test_returns_composite(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_mf(store)
        _populate_delivery(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_institutional_consensus("TESTCO")
        assert "composite" in result
        assert "composite_score" in result

    def test_empty_returns_neutral(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_institutional_consensus("NONE")
        assert result.get("composite") == "neutral"


class TestToolRouting:
    def test_mf_conviction_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_mf(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.tools import _get_ownership_section

        with ResearchDataAPI() as api:
            result = _get_ownership_section(api, "TESTCO", "mf_conviction", {})
        assert result.get("available") is True

    def test_delivery_analysis_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_delivery(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.tools import _get_market_context_section

        with ResearchDataAPI() as api:
            result = _get_market_context_section(api, "TESTCO", "delivery_analysis", {})
        assert result.get("available") is True

    def test_commodity_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_commodities(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.tools import _get_market_context_section

        with ResearchDataAPI() as api:
            result = _get_market_context_section(api, "TESTCO", "commodities", {})
        assert "gold" in result

    def test_dividend_policy_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_dividends(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.tools import _get_events_actions_section

        with ResearchDataAPI() as api:
            result = _get_events_actions_section(api, "TESTCO", "dividend_policy", {})
        assert result.get("available") is True

    def test_institutional_consensus_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_mf(store)
        _populate_delivery(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.tools import _get_market_context_section

        with ResearchDataAPI() as api:
            result = _get_market_context_section(api, "TESTCO", "institutional_consensus", {})
        assert "composite" in result
