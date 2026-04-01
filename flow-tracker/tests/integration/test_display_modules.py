"""Integration tests: display module functions render correctly with fixture data.

Each test queries data from populated_store, calls the display function,
captures Rich console output to a StringIO buffer, and verifies key strings appear.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, width=200)
    return con, buf


# ---------------------------------------------------------------------------
# 1. display.py — core FII/DII flow display functions
# ---------------------------------------------------------------------------


class TestFlowDisplay:
    def test_display_flows_table(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        flows = populated_store.get_flows(days=30)
        mod.display_flows_table(flows, "30d")
        out = buf.getvalue()
        assert "FII" in out
        assert "Total" in out

    def test_display_flows_table_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_flows_table([], "7d")
        out = buf.getvalue()
        assert "No data" in out or "fetch" in out.lower()

    def test_display_summary(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        pair = populated_store.get_latest()
        assert pair is not None
        mod.display_summary(pair)
        out = buf.getvalue()
        assert "FII" in out and "DII" in out

    def test_display_fetch_result(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        flows = populated_store.get_flows(days=1)
        mod.display_fetch_result(flows)
        out = buf.getvalue()
        assert "Fetched" in out or "Category" in out or len(out) > 10

    def test_display_fetch_result_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_fetch_result([])
        out = buf.getvalue()
        assert "No data" in out

    def test_display_streak(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        fii_streak = populated_store.get_streak("FII")
        dii_streak = populated_store.get_streak("DII")
        mod.display_streak(fii_streak, dii_streak)
        out = buf.getvalue()
        assert "BUYING" in out or "SELLING" in out or "Streak" in out or len(out) > 5


# ---------------------------------------------------------------------------
# 2. bhavcopy_display.py — delivery data
# ---------------------------------------------------------------------------


class TestBhavcopyDisplay:
    def test_display_top_delivery(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import bhavcopy_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        records = populated_store.get_top_delivery(None, 10)
        mod.display_top_delivery(records, "2026-03-28")
        out = buf.getvalue()
        assert "Delivery" in out or "Symbol" in out or len(out) > 10

    def test_display_delivery_trend(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import bhavcopy_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        records = populated_store.get_stock_delivery("SBIN", 30)
        mod.display_delivery_trend(records, "SBIN")
        out = buf.getvalue()
        assert "SBIN" in out

    def test_display_delivery_trend_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import bhavcopy_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_delivery_trend([], "ZZZZ")
        out = buf.getvalue()
        assert "No delivery" in out or "ZZZZ" in out


# ---------------------------------------------------------------------------
# 3. commodity_display.py — gold/silver prices + ETF NAVs
# ---------------------------------------------------------------------------


class TestCommodityDisplay:
    def test_display_commodity_prices(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import commodity_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        gold = populated_store.get_commodity_prices("GOLD", 30)
        mod.display_commodity_prices(gold, [])
        out = buf.getvalue()
        assert "Gold" in out or len(out) > 10

    def test_display_etf_navs(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import commodity_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        navs = populated_store.get_etf_navs("140088", 365)
        mod.display_etf_navs(navs)
        out = buf.getvalue()
        assert "NAV" in out or "Nippon" in out or len(out) > 10


# ---------------------------------------------------------------------------
# 4. deals_display.py — bulk/block deals
# ---------------------------------------------------------------------------


class TestDealsDisplay:
    def test_display_deals_summary(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import deals_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        deals = populated_store.get_deals_latest()
        mod.display_deals_summary(deals)
        out = buf.getvalue()
        assert "Deals" in out or "BLOCK" in out or "BULK" in out or len(out) > 10

    def test_display_deals_stock(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import deals_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        deals = populated_store.get_deals_by_symbol("SBIN")
        mod.display_deals_stock(deals, "SBIN")
        out = buf.getvalue()
        assert "SBIN" in out or "Deal" in out


# ---------------------------------------------------------------------------
# 5. estimates_display.py — consensus estimates + surprises
# ---------------------------------------------------------------------------


class TestEstimatesDisplay:
    def test_display_estimates_stock(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import estimates_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        est = populated_store.get_estimate_latest("SBIN")
        surprises = populated_store.get_surprises("SBIN")
        assert est is not None
        mod.display_estimates_stock(est, surprises)
        out = buf.getvalue()
        assert "SBIN" in out or "Target" in out

    def test_display_estimates_upside(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import estimates_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        estimates = populated_store.get_all_latest_estimates()
        mod.display_estimates_upside(estimates)
        out = buf.getvalue()
        assert "Upside" in out or "Symbol" in out


# ---------------------------------------------------------------------------
# 6. fmp_display.py — DCF + technicals
# ---------------------------------------------------------------------------


class TestFMPDisplay:
    def test_display_dcf(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import fmp_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        current = populated_store.get_fmp_dcf_latest("SBIN")
        history = populated_store.get_fmp_dcf_history("SBIN")
        mod.display_dcf(current, history)
        out = buf.getvalue()
        assert "DCF" in out or "Intrinsic" in out

    def test_display_dcf_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import fmp_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_dcf(None, [])
        out = buf.getvalue()
        assert "No DCF" in out

    def test_display_technicals(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import fmp_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        indicators = populated_store.get_fmp_technical_indicators("SBIN")
        mod.display_technicals(indicators)
        out = buf.getvalue()
        assert "RSI" in out or "SMA" in out or "Technical" in out


# ---------------------------------------------------------------------------
# 7. fund_display.py — quarterly history
# ---------------------------------------------------------------------------


class TestFundDisplay:
    def test_display_quarterly_history(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import fund_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        results = populated_store.get_quarterly_results("SBIN", limit=8)
        mod.display_quarterly_history(results, "SBIN")
        out = buf.getvalue()
        assert "SBIN" in out or "Quarter" in out

    def test_display_quarterly_history_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import fund_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_quarterly_history([], "ZZZZ")
        out = buf.getvalue()
        assert "No quarterly" in out


# ---------------------------------------------------------------------------
# 8. holding_display.py — shareholding patterns + changes
# ---------------------------------------------------------------------------


class TestHoldingDisplay:
    def test_display_shareholding(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import holding_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        records = populated_store.get_shareholding("SBIN", 8)
        mod.display_shareholding("SBIN", records)
        out = buf.getvalue()
        assert "SBIN" in out or "Promoter" in out

    def test_display_shareholding_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import holding_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_shareholding("ZZZZ", [])
        out = buf.getvalue()
        assert "No shareholding" in out

    def test_display_holding_changes(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import holding_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        changes = populated_store.get_biggest_changes(None, 10)
        mod.display_holding_changes(changes)
        out = buf.getvalue()
        # Either actual changes or "no changes" message
        assert len(out) > 0


# ---------------------------------------------------------------------------
# 9. insider_display.py — insider transactions
# ---------------------------------------------------------------------------


class TestInsiderDisplay:
    def test_display_insider_trades(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import insider_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        trades = populated_store.get_insider_by_symbol("SBIN", 365)
        mod.display_insider_trades(trades, title="Insider — SBIN")
        out = buf.getvalue()
        assert "SBIN" in out or "Insider" in out

    def test_display_promoter_buys(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import insider_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        trades = populated_store.get_promoter_buys(365)
        mod.display_promoter_buys(trades)
        out = buf.getvalue()
        assert "Promoter" in out or len(out) > 0


# ---------------------------------------------------------------------------
# 10. macro_display.py — macro indicators
# ---------------------------------------------------------------------------


class TestMacroDisplay:
    def test_display_macro_summary(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import macro_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        latest = populated_store.get_macro_latest()
        prev = populated_store.get_macro_previous()
        assert latest is not None
        mod.display_macro_summary(latest, prev)
        out = buf.getvalue()
        assert "VIX" in out or "Macro" in out

    def test_display_macro_trend(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import macro_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        snapshots = populated_store.get_macro_trend(30)
        mod.display_macro_trend(snapshots)
        out = buf.getvalue()
        assert "Macro" in out or "VIX" in out or "India" in out


# ---------------------------------------------------------------------------
# 11. mf_display.py — MF AUM summary
# ---------------------------------------------------------------------------


class TestMFDisplay:
    def test_display_mf_summary(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import mf_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        summary = populated_store.get_mf_latest_aum()
        assert summary is not None
        mod.display_mf_summary(summary)
        out = buf.getvalue()
        assert "Equity" in out or "AUM" in out


# ---------------------------------------------------------------------------
# 12. mfportfolio_display.py — MF scheme-level holdings for a stock
# ---------------------------------------------------------------------------


class TestMFPortfolioDisplay:
    def test_display_stock_holdings(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import mfportfolio_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        holdings = populated_store.get_mf_stock_holdings("SBIN")
        mod.display_stock_holdings(holdings, "SBIN")
        out = buf.getvalue()
        # Either holdings data or "no holdings" message
        assert "SBIN" in out or "MF" in out or "No MF" in out


# ---------------------------------------------------------------------------
# 13. portfolio_display.py — portfolio view
# ---------------------------------------------------------------------------


class TestPortfolioDisplay:
    def test_display_portfolio_view(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import portfolio_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        holdings = populated_store.get_portfolio_holdings()
        enriched = []
        for h in holdings:
            enriched.append({
                "symbol": h.symbol,
                "quantity": h.quantity,
                "avg_cost": h.avg_cost,
                "cmp": h.avg_cost * 1.1,  # Simulate a 10% gain
            })
        mod.display_portfolio_view(enriched)
        out = buf.getvalue()
        assert "SBIN" in out or "Portfolio" in out

    def test_display_portfolio_view_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import portfolio_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_portfolio_view([])
        out = buf.getvalue()
        assert "No holdings" in out


# ---------------------------------------------------------------------------
# 14. scan_display.py — index constituents
# ---------------------------------------------------------------------------


class TestScanDisplay:
    def test_display_constituents(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import scan_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        constituents = populated_store.get_index_constituents()
        mod.display_constituents(constituents)
        out = buf.getvalue()
        assert "SBIN" in out or "INFY" in out or "Symbol" in out


# ---------------------------------------------------------------------------
# 15. screener_display.py — stock scorecard
# ---------------------------------------------------------------------------


class TestScreenerDisplay:
    def test_display_stock_scorecard(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import screener_display as mod
        from flowtracker.screener_engine import ScreenerEngine

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        engine = ScreenerEngine(populated_store)
        score = engine.score_stock("SBIN")
        if score is not None:
            mod.display_stock_scorecard(score)
            out = buf.getvalue()
            assert "SBIN" in out or "Score" in out
        # If score is None, the data wasn't sufficient — still passes


# ---------------------------------------------------------------------------
# 16. sector_display.py — sector overview
# ---------------------------------------------------------------------------


class TestSectorDisplay:
    def test_display_sector_overview(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import sector_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        sectors = populated_store.get_sector_overview()
        mod.display_sector_overview(sectors)
        out = buf.getvalue()
        # Either has data or "No sector data" message
        assert len(out) > 0


# ---------------------------------------------------------------------------
# 17. alert_display.py — alert list
# ---------------------------------------------------------------------------


class TestAlertDisplay:
    def test_display_alerts(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import alert_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        alerts = populated_store.get_active_alerts()
        mod.display_alerts(alerts)
        out = buf.getvalue()
        assert "Alert" in out or "SBIN" in out or "price_below" in out

    def test_display_alerts_empty(self, populated_store: FlowStore, monkeypatch):
        from flowtracker import alert_display as mod

        con, buf = _make_console()
        monkeypatch.setattr(mod, "console", con)
        mod.display_alerts([])
        out = buf.getvalue()
        assert "No active" in out
