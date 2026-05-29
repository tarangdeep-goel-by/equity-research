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
from flowtracker.macro_models import MacroSnapshot, MacroSystemCredit
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
                          usd_inr=83.5, eur_inr=92.1, gbp_inr=108.4,
                          brent_crude=82.0, gsec_10y=7.15),
            MacroSnapshot(date=(today - timedelta(days=1)).isoformat(),
                          india_vix=14.2, usd_inr=83.4, eur_inr=92.0,
                          gbp_inr=108.3, brent_crude=81.5, gsec_10y=7.14),
        ]
        count = store.upsert_macro_snapshots(snapshots)
        assert count == 2
        latest = store.get_macro_latest()
        assert latest is not None
        assert latest.date == today.isoformat()
        assert latest.india_vix == pytest.approx(14.5)
        assert latest.eur_inr == pytest.approx(92.1)
        assert latest.gbp_inr == pytest.approx(108.4)

    def test_eur_gbp_round_trip_via_trend(self, store: FlowStore):
        """EUR/INR and GBP/INR persist + round-trip through get_macro_trend."""
        today = date.today()
        snapshots = [
            MacroSnapshot(
                date=(today - timedelta(days=i)).isoformat(),
                india_vix=14.0, usd_inr=83.0,
                eur_inr=92.0 + i * 0.1, gbp_inr=108.0 + i * 0.2,
                brent_crude=80.0, gsec_10y=7.1,
            )
            for i in range(3)
        ]
        store.upsert_macro_snapshots(snapshots)
        trend = store.get_macro_trend(days=10)
        assert len(trend) == 3
        for s in trend:
            assert s.eur_inr is not None
            assert s.gbp_inr is not None

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

    def test_backfill_missing_gsec(self, store: FlowStore):
        """backfill_missing_gsec fills NULL gsec_10y rows within the lookback window."""
        today = date.today()
        # Seed 4 days: today has gsec, prior 3 have gsec=NULL
        snapshots = [
            MacroSnapshot(date=today.isoformat(), india_vix=14.5,
                          usd_inr=83.5, brent_crude=82.0, gsec_10y=6.48),
        ]
        for i in range(1, 4):
            d = (today - timedelta(days=i)).isoformat()
            snapshots.append(MacroSnapshot(
                date=d, india_vix=14.0, usd_inr=83.4,
                brent_crude=81.5, gsec_10y=None,
            ))
        store.upsert_macro_snapshots(snapshots)

        patched = store.backfill_missing_gsec(6.48)
        assert patched == 3  # 3 NULL rows got filled; today already had a value

        # Every row in window now has gsec
        trend = store.get_macro_trend(days=10)
        for s in trend:
            assert s.gsec_10y == 6.48, f"{s.date} still missing"

    def test_backfill_missing_gsec_respects_lookback(self, store: FlowStore):
        """Rows older than max_lookback_days are NOT patched."""
        today = date.today()
        # One row today (NULL), one row 30 days ago (NULL)
        store.upsert_macro_snapshots([
            MacroSnapshot(date=today.isoformat(), india_vix=14.5,
                          usd_inr=83.5, brent_crude=82.0, gsec_10y=None),
            MacroSnapshot(date=(today - timedelta(days=30)).isoformat(),
                          india_vix=14.0, usd_inr=83.0, brent_crude=80.0, gsec_10y=None),
        ])

        patched = store.backfill_missing_gsec(6.48, max_lookback_days=7)
        assert patched == 1  # only today's row within 7-day window

        # Old row still NULL
        row = store._conn.execute(
            "SELECT gsec_10y FROM macro_daily WHERE date = ?",
            ((today - timedelta(days=30)).isoformat(),),
        ).fetchone()
        assert row["gsec_10y"] is None

    def test_backfill_missing_gsec_skips_populated_rows(self, store: FlowStore):
        """Rows already holding a gsec value are not overwritten."""
        today = date.today()
        store.upsert_macro_snapshots([
            MacroSnapshot(date=today.isoformat(), india_vix=14.5,
                          usd_inr=83.5, brent_crude=82.0, gsec_10y=7.00),
        ])
        patched = store.backfill_missing_gsec(6.48)
        assert patched == 0
        latest = store.get_macro_latest()
        assert latest is not None
        assert latest.gsec_10y == 7.00


# ---------------------------------------------------------------------------
# macro_system_credit (RBI WSS)
# ---------------------------------------------------------------------------


class TestMacroSystemCredit:
    def test_upsert_and_get_latest_round_trip(self, store: FlowStore):
        record = MacroSystemCredit(
            release_date="2026-04-24",
            as_of_date="2026-04-15",
            aggregate_deposits_cr=25648470.0,
            bank_credit_cr=20921084.0,
            deposit_growth_yoy=12.2,
            credit_growth_yoy=15.0,
            non_food_credit_growth_yoy=15.1,
            cd_ratio=81.57,
            m3_growth_yoy=11.9,
            source="RBI_WSS",
        )
        rowcount = store.upsert_system_credit(record)
        assert rowcount == 1

        latest = store.get_latest_system_credit()
        assert latest is not None
        assert latest.release_date == "2026-04-24"
        assert latest.as_of_date == "2026-04-15"
        assert latest.credit_growth_yoy == pytest.approx(15.0)
        assert latest.deposit_growth_yoy == pytest.approx(12.2)
        assert latest.cd_ratio == pytest.approx(81.57)
        assert latest.m3_growth_yoy == pytest.approx(11.9)
        assert latest.source == "RBI_WSS"

    def test_upsert_replaces_same_release(self, store: FlowStore):
        """Re-upserting the same release_date overwrites prior values."""
        record1 = MacroSystemCredit(
            release_date="2026-04-24", credit_growth_yoy=14.0,
        )
        store.upsert_system_credit(record1)
        record2 = MacroSystemCredit(
            release_date="2026-04-24", credit_growth_yoy=15.5,
        )
        store.upsert_system_credit(record2)

        latest = store.get_latest_system_credit()
        assert latest.credit_growth_yoy == 15.5

    def test_get_latest_returns_most_recent_release(self, store: FlowStore):
        store.upsert_system_credit(MacroSystemCredit(
            release_date="2026-04-17", credit_growth_yoy=16.1,
        ))
        store.upsert_system_credit(MacroSystemCredit(
            release_date="2026-04-24", credit_growth_yoy=15.0,
        ))
        latest = store.get_latest_system_credit()
        assert latest.release_date == "2026-04-24"
        assert latest.credit_growth_yoy == 15.0

    def test_get_trend_orders_newest_first(self, store: FlowStore):
        for d, g in [
            ("2026-04-03", 16.5), ("2026-04-10", 16.3),
            ("2026-04-17", 16.1), ("2026-04-24", 15.0),
        ]:
            store.upsert_system_credit(MacroSystemCredit(
                release_date=d, credit_growth_yoy=g,
            ))
        trend = store.get_system_credit_trend(weeks=10)
        assert len(trend) == 4
        assert trend[0].release_date == "2026-04-24"
        assert trend[-1].release_date == "2026-04-03"

    def test_get_trend_respects_weeks_limit(self, store: FlowStore):
        for d in ["2026-04-03", "2026-04-10", "2026-04-17", "2026-04-24"]:
            store.upsert_system_credit(MacroSystemCredit(release_date=d))
        trend = store.get_system_credit_trend(weeks=2)
        assert len(trend) == 2
        assert trend[0].release_date == "2026-04-24"

    def test_get_latest_empty(self, store: FlowStore):
        assert store.get_latest_system_credit() is None


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

    def test_upsert_drops_future_dated_rows(self, store: FlowStore):
        """Future-dated rows are rejected at ingestion (issue #175)."""
        today = date.today()
        future = (today + timedelta(days=180)).isoformat()
        trades = [
            InsiderTransaction(date=today.isoformat(), symbol="SBIN",
                               person_name="Rajesh", person_category="Promoters",
                               transaction_type="Buy", quantity=100000,
                               value=82000000.0, mode="Market Purchase"),
            InsiderTransaction(date=future, symbol="CAMPUS",
                               person_name="Future Guy", person_category="Promoters",
                               transaction_type="Buy", quantity=50000,
                               value=40000000.0, mode="Market Purchase"),
        ]
        count = store.upsert_insider_transactions(trades)
        assert count == 1  # only the valid (today) row persisted
        assert store.get_insider_by_symbol("CAMPUS", days=3650) == []
        assert len(store.get_insider_by_symbol("SBIN", days=365)) == 1

    def test_get_insider_empty(self, store: FlowStore):
        assert store.get_insider_by_symbol("SBIN") == []

    def test_get_promoter_buys_empty(self, store: FlowStore):
        assert store.get_promoter_buys() == []


# ---------------------------------------------------------------------------
# WS1 — multi-market dimension: market/currency columns + symbol_registry
# ---------------------------------------------------------------------------

from flowtracker.store import _MARKET_COLUMN_TABLES, _CURRENCY_COLUMN_TABLES
from flowtracker.scan_models import IndexConstituent


class TestMarketColumns:
    @pytest.mark.parametrize(
        "table", ["valuation_snapshot", "shareholding", "daily_stock_data"]
    )
    def test_market_column_exists(self, store: FlowStore, table: str):
        cols = {r[1] for r in store._conn.execute(
            f"PRAGMA table_info({table})").fetchall()}
        assert "market" in cols

    def test_all_market_tables_have_market_column(self, store: FlowStore):
        for table in _MARKET_COLUMN_TABLES:
            cols = {r[1] for r in store._conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            assert cols, f"{table} does not exist"
            assert "market" in cols, f"{table} missing market column"

    def test_all_currency_tables_have_currency_column(self, store: FlowStore):
        for table in _CURRENCY_COLUMN_TABLES:
            cols = {r[1] for r in store._conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            assert "currency" in cols, f"{table} missing currency column"

    def test_market_defaults_to_nse(self, store: FlowStore):
        store._conn.execute(
            "INSERT INTO valuation_snapshot (symbol, date, price) VALUES "
            "('SBIN', '2024-01-01', 800)"
        )
        store._conn.commit()
        row = store._conn.execute(
            "SELECT market, currency FROM valuation_snapshot WHERE symbol='SBIN'"
        ).fetchone()
        assert row["market"] == "NSE"
        assert row["currency"] == "INR"

    def test_currency_default_on_daily_stock_data(self, store: FlowStore):
        store._conn.execute(
            "INSERT INTO daily_stock_data "
            "(date, symbol, open, high, low, close, prev_close, volume, turnover) "
            "VALUES ('2024-01-01', 'SBIN', 1, 1, 1, 100, 99, 10, 1000)"
        )
        store._conn.commit()
        row = store._conn.execute(
            "SELECT market, currency FROM daily_stock_data WHERE symbol='SBIN'"
        ).fetchone()
        assert row["market"] == "NSE"
        assert row["currency"] == "INR"

    def test_non_currency_table_has_no_currency_column(self, store: FlowStore):
        cols = {r[1] for r in store._conn.execute(
            "PRAGMA table_info(shareholding)").fetchall()}
        assert "currency" not in cols

    def test_migration_is_idempotent(self, store: FlowStore):
        # Re-running the column migration must not raise (PRAGMA guard).
        store._migrate_market_columns()
        store._migrate_market_columns()
        cols = {r[1] for r in store._conn.execute(
            "PRAGMA table_info(valuation_snapshot)").fetchall()}
        # market added exactly once
        assert sum(1 for c in cols if c == "market") == 1


class TestSymbolRegistry:
    def test_upsert_and_get_roundtrip(self, store: FlowStore):
        store.upsert_symbol_registry("reliance", company_name="Reliance Industries",
                                     sector="Energy")
        entry = store.get_symbol_registry_entry("RELIANCE")
        assert entry is not None
        assert entry["symbol"] == "RELIANCE"
        assert entry["market"] == "NSE"
        assert entry["company_name"] == "Reliance Industries"
        assert entry["sector"] == "Energy"
        # derived from market config
        assert entry["currency"] == "INR"
        assert entry["fiscal_year_system"] == "APR_MAR"

    def test_get_missing_returns_none(self, store: FlowStore):
        assert store.get_symbol_registry_entry("NOPE") is None

    def test_coalesce_preserves_existing_company_name(self, store: FlowStore):
        store.upsert_symbol_registry("SBIN", company_name="State Bank of India",
                                     sector="Banks")
        # later partial upsert with None must not wipe existing fields
        store.upsert_symbol_registry("SBIN", isin="INE062A01020")
        entry = store.get_symbol_registry_entry("SBIN")
        assert entry["company_name"] == "State Bank of India"
        assert entry["sector"] == "Banks"
        assert entry["isin"] == "INE062A01020"

    def test_us_market_derives_usd_calendar(self, store: FlowStore):
        store.upsert_symbol_registry("AAPL", market="NASDAQ", company_name="Apple")
        entry = store.get_symbol_registry_entry("AAPL", market="NASDAQ")
        assert entry["currency"] == "USD"
        assert entry["fiscal_year_system"] == "CALENDAR"

    def test_same_symbol_different_markets_coexist(self, store: FlowStore):
        store.upsert_symbol_registry("INFY", market="NSE", company_name="Infosys NSE")
        store.upsert_symbol_registry("INFY", market="NASDAQ", company_name="Infosys ADR")
        nse = store.get_symbol_registry_entry("INFY", market="NSE")
        nasdaq = store.get_symbol_registry_entry("INFY", market="NASDAQ")
        assert nse["company_name"] == "Infosys NSE"
        assert nse["currency"] == "INR"
        assert nasdaq["company_name"] == "Infosys ADR"
        assert nasdaq["currency"] == "USD"
        all_nasdaq = store.get_symbol_registry(market="NASDAQ")
        assert [e["symbol"] for e in all_nasdaq] == ["INFY"]
        assert len(store.get_symbol_registry()) == 2

    def test_seed_backfill_from_source_tables(self, store: FlowStore):
        store.add_to_watchlist("SBIN", "State Bank")
        store.upsert_index_constituents([
            IndexConstituent(symbol="INFY", index_name="NIFTY",
                             company_name="Infosys", industry="IT"),
        ])
        store._migrate_symbol_registry()
        symbols = {e["symbol"] for e in store.get_symbol_registry()}
        assert {"SBIN", "INFY"} <= symbols
        infy = store.get_symbol_registry_entry("INFY")
        assert infy["company_name"] == "Infosys"
        assert infy["sector"] == "IT"  # industry mapped into sector

    def test_seed_backfill_is_idempotent(self, store: FlowStore):
        store.add_to_watchlist("SBIN", "State Bank")
        store.upsert_index_constituents([
            IndexConstituent(symbol="INFY", index_name="NIFTY",
                             company_name="Infosys", industry="IT"),
        ])
        store._migrate_symbol_registry()
        first = len(store.get_symbol_registry())
        store._migrate_symbol_registry()  # second run must not duplicate
        second = len(store.get_symbol_registry())
        assert first == second
        # exactly one row per (symbol, market)
        dupes = store._conn.execute(
            "SELECT symbol, market, COUNT(*) c FROM symbol_registry "
            "GROUP BY symbol, market HAVING c > 1"
        ).fetchall()
        assert dupes == []
