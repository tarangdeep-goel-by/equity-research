"""Tests for FlowStore market data methods.

Tables: daily_stock_data, commodity_prices, gold_etf_nav,
        macro_daily, bulk_block_deals, insider_transactions
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.store import FlowStore
from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.commodity_models import CommodityPrice
from flowtracker.macro_models import MacroSnapshot
from flowtracker.deals_models import BulkBlockDeal
from flowtracker.insider_models import InsiderTransaction
from tests.fixtures.factories import (
    make_daily_stock_data,
    make_commodity_prices,
    make_gold_etf_navs,
    make_macro_snapshots,
    make_deals,
    make_insider_transactions,
)


# ---------------------------------------------------------------------------
# daily_stock_data
# ---------------------------------------------------------------------------


class TestDailyStockData:
    def test_upsert_and_get_top_delivery(self, store: FlowStore):
        today = date.today()
        records = [
            DailyStockData(date=today.isoformat(), symbol="SBIN", open=800, high=810,
                           low=790, close=805, prev_close=800, volume=10000000,
                           turnover=80500, delivery_qty=7000000, delivery_pct=70.0),
            DailyStockData(date=today.isoformat(), symbol="INFY", open=1800, high=1820,
                           low=1790, close=1810, prev_close=1800, volume=5000000,
                           turnover=90500, delivery_qty=2000000, delivery_pct=40.0),
        ]
        count = store.upsert_daily_stock_data(records)
        assert count == 2
        top = store.get_top_delivery(date_str=today.isoformat(), limit=10)
        assert len(top) == 2
        # Highest delivery_pct first
        assert top[0].delivery_pct >= top[1].delivery_pct
        assert top[0].symbol == "SBIN"

    def test_get_stock_delivery(self, store: FlowStore):
        today = date.today()
        records = []
        for i in range(3):
            d = (today - timedelta(days=i)).isoformat()
            records.append(DailyStockData(
                date=d, symbol="SBIN", open=800, high=810, low=790,
                close=805, prev_close=800, volume=10000000, turnover=80000,
                delivery_qty=7000000, delivery_pct=70.0 + i,
            ))
        store.upsert_daily_stock_data(records)
        result = store.get_stock_delivery("SBIN", days=7)
        assert len(result) == 3

    def test_get_top_delivery_empty(self, store: FlowStore):
        assert store.get_top_delivery() == []

    def test_get_top_delivery_default_date(self, store: FlowStore):
        """get_top_delivery with no date_str uses MAX(date)."""
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        store.upsert_daily_stock_data([
            DailyStockData(date=yesterday, symbol="SBIN", open=800, high=810,
                           low=790, close=805, prev_close=800, volume=10000000,
                           turnover=80000, delivery_qty=7000000, delivery_pct=65.0),
            DailyStockData(date=today.isoformat(), symbol="INFY", open=1800, high=1820,
                           low=1790, close=1810, prev_close=1800, volume=5000000,
                           turnover=90000, delivery_qty=3000000, delivery_pct=60.0),
        ])
        top = store.get_top_delivery()
        # Should only return today's data (the most recent date)
        assert len(top) == 1
        assert top[0].symbol == "INFY"


# ---------------------------------------------------------------------------
# commodity_prices
# ---------------------------------------------------------------------------


class TestCommodityPrices:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        today = date.today()
        prices = [
            CommodityPrice(date=today.isoformat(), symbol="GOLD",
                           price=2100.0, unit="USD/oz"),
            CommodityPrice(date=(today - timedelta(days=1)).isoformat(),
                           symbol="GOLD", price=2095.0, unit="USD/oz"),
        ]
        count = store.upsert_commodity_prices(prices)
        assert count == 2
        got = store.get_commodity_prices("GOLD", days=7)
        assert len(got) == 2
        # Most recent first
        assert got[0].date >= got[1].date

    def test_nan_prices_skipped(self, store: FlowStore):
        import math
        prices = [
            CommodityPrice(date="2026-03-28", symbol="GOLD",
                           price=float('nan'), unit="USD/oz"),
        ]
        count = store.upsert_commodity_prices(prices)
        assert count == 0

    def test_get_empty(self, store: FlowStore):
        assert store.get_commodity_prices("GOLD") == []


# ---------------------------------------------------------------------------
# gold_etf_nav
# ---------------------------------------------------------------------------


class TestGoldETFNav:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        today = date.today()
        from flowtracker.commodity_models import GoldETFNav
        navs = [
            GoldETFNav(date=today.isoformat(), scheme_code="140088",
                       scheme_name="Nippon Gold BeES", nav=59.0),
            GoldETFNav(date=(today - timedelta(days=1)).isoformat(),
                       scheme_code="140088", scheme_name="Nippon Gold BeES", nav=58.8),
        ]
        count = store.upsert_etf_navs(navs)
        assert count == 2
        got = store.get_etf_navs("140088", days=7)
        assert len(got) == 2
        assert got[0].nav >= got[1].nav  # most recent first


# ---------------------------------------------------------------------------
# macro_daily
# ---------------------------------------------------------------------------


class TestMacroDaily:
    def test_upsert_and_get_latest(self, store: FlowStore):
        today = date.today()
        snapshots = [
            MacroSnapshot(date=today.isoformat(), india_vix=14.5,
                          usd_inr=83.5, brent_crude=82.0, gsec_10y=7.15),
            MacroSnapshot(date=(today - timedelta(days=1)).isoformat(),
                          india_vix=14.2, usd_inr=83.4, brent_crude=81.5, gsec_10y=7.14),
        ]
        count = store.upsert_macro_snapshots(snapshots)
        assert count == 2
        latest = store.get_macro_latest()
        assert latest is not None
        assert latest.date == today.isoformat()
        assert latest.india_vix == pytest.approx(14.5)

    def test_get_macro_previous(self, store: FlowStore):
        today = date.today()
        store.upsert_macro_snapshots([
            MacroSnapshot(date=today.isoformat(), india_vix=14.5,
                          usd_inr=83.5, brent_crude=82.0, gsec_10y=7.15),
            MacroSnapshot(date=(today - timedelta(days=1)).isoformat(),
                          india_vix=14.2, usd_inr=83.4, brent_crude=81.5, gsec_10y=7.14),
        ])
        prev = store.get_macro_previous()
        assert prev is not None
        assert prev.date == (today - timedelta(days=1)).isoformat()

    def test_get_macro_trend(self, store: FlowStore):
        today = date.today()
        snapshots = []
        for i in range(5):
            d = (today - timedelta(days=4 - i)).isoformat()
            snapshots.append(MacroSnapshot(
                date=d, india_vix=14.0 + i * 0.1,
                usd_inr=83.0, brent_crude=80.0, gsec_10y=7.1,
            ))
        store.upsert_macro_snapshots(snapshots)
        trend = store.get_macro_trend(days=10)
        assert len(trend) == 5
        # Most recent first
        assert trend[0].date >= trend[-1].date

    def test_get_latest_empty(self, store: FlowStore):
        assert store.get_macro_latest() is None

    def test_get_previous_empty(self, store: FlowStore):
        assert store.get_macro_previous() is None


# ---------------------------------------------------------------------------
# bulk_block_deals
# ---------------------------------------------------------------------------


class TestDeals:
    def test_upsert_and_get_latest(self, store: FlowStore):
        deals = make_deals()
        count = store.upsert_deals(deals)
        assert count == 2
        latest = store.get_deals_latest()
        assert len(latest) == 2

    def test_get_deals_by_symbol(self, store: FlowStore):
        store.upsert_deals(make_deals())
        got = store.get_deals_by_symbol("SBIN")
        assert len(got) == 1
        assert got[0].symbol == "SBIN"
        assert got[0].deal_type == "BLOCK"

    def test_get_deals_top(self, store: FlowStore):
        today = date.today()
        deals = [
            BulkBlockDeal(date=today.isoformat(), deal_type="BLOCK", symbol="SBIN",
                          client_name="GS", buy_sell="BUY", quantity=5000000, price=820.0),
            BulkBlockDeal(date=today.isoformat(), deal_type="BULK", symbol="INFY",
                          client_name="MS", buy_sell="SELL", quantity=100000, price=1800.0),
        ]
        store.upsert_deals(deals)
        top = store.get_deals_top(days=7, limit=10)
        assert len(top) == 2
        # Biggest value first (5M * 820 > 100K * 1800)
        assert top[0].symbol == "SBIN"

    def test_get_deals_empty(self, store: FlowStore):
        assert store.get_deals_latest() == []


# ---------------------------------------------------------------------------
# insider_transactions
# ---------------------------------------------------------------------------


class TestInsiderTransactions:
    def test_upsert_and_get_by_symbol(self, store: FlowStore):
        trades = make_insider_transactions("SBIN")
        count = store.upsert_insider_transactions(trades)
        assert count == 3
        got = store.get_insider_by_symbol("SBIN", days=365)
        assert len(got) == 3
        # Most recent first
        assert got[0].date >= got[-1].date

    def test_get_promoter_buys(self, store: FlowStore):
        today = date.today()
        trades = [
            InsiderTransaction(date=today.isoformat(), symbol="SBIN",
                               person_name="Rajesh", person_category="Promoters",
                               transaction_type="Buy", quantity=100000,
                               value=82000000.0, mode="Market Purchase"),
            InsiderTransaction(date=today.isoformat(), symbol="SBIN",
                               person_name="Amit", person_category="Director",
                               transaction_type="Buy", quantity=50000,
                               value=40000000.0, mode="Market Purchase"),
            InsiderTransaction(date=today.isoformat(), symbol="SBIN",
                               person_name="Priya", person_category="Promoters",
                               transaction_type="Sell", quantity=10000,
                               value=8200000.0, mode="Market Purchase"),
        ]
        store.upsert_insider_transactions(trades)
        buys = store.get_promoter_buys(days=7)
        assert len(buys) == 1  # only promoter BUY
        assert buys[0].person_name == "Rajesh"
        assert buys[0].transaction_type == "Buy"

    def test_get_insider_empty(self, store: FlowStore):
        assert store.get_insider_by_symbol("SBIN") == []

    def test_get_promoter_buys_empty(self, store: FlowStore):
        assert store.get_promoter_buys() == []
