"""Tests for ResearchDataAPI (research/data_api.py).

Tests that each API method returns correctly shaped data from the
populated test store, and that unknown symbols return empty results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixture: create a ResearchDataAPI pointed at the populated test DB
# ---------------------------------------------------------------------------

@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI backed by the populated test database."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# ---------------------------------------------------------------------------
# Core Financials
# ---------------------------------------------------------------------------

class TestQuarterlyResults:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert isinstance(data[0], dict)

    def test_has_expected_keys(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("SBIN")
        row = data[0]
        assert "revenue" in row
        assert "net_income" in row
        assert "quarter_end" in row

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("NONEXIST")
        assert isinstance(data, list)
        assert len(data) == 0


class TestAnnualFinancials:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_annual_financials("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_annual_financials("NONEXIST")
        assert len(data) == 0


class TestInsuranceHeadlineRevenue:
    """Headline-revenue swap for life insurers — annual + quarterly.

    Screener's "Revenue" line for insurers includes mark-to-market gains/losses
    on policyholder funds, producing wild year-on-year swings unrelated to
    underwriting. The clean industry-standard top line is Net Premium Earned.
    The data layer adds a `headline_revenue` field that prefers Net Premium
    Earned for insurers and falls back to revenue with a `data_quality_note`
    when net_premium_earned isn't ingested. See
    `ResearchDataAPI._apply_insurance_headline`.
    """

    @staticmethod
    def _set_industry(store, symbol: str, industry: str) -> None:
        """Insert an industry row into company_snapshot (the path
        `_get_industry` reads first)."""
        store._conn.execute(
            "INSERT OR REPLACE INTO company_snapshot (symbol, industry) VALUES (?, ?)",
            (symbol, industry),
        )
        store._conn.commit()

    def test_non_insurer_headline_equals_revenue_no_note(self, api: ResearchDataAPI):
        # SBIN (Banks — non-insurance) → headline_revenue == revenue, no note.
        rows = api.get_annual_financials("SBIN")
        assert len(rows) > 0
        for row in rows:
            assert row.get("headline_revenue") == row.get("revenue")
            assert "data_quality_note" not in row
            assert "notes" not in row

    def test_insurer_with_net_premium_uses_premium_as_headline(
        self, api: ResearchDataAPI, populated_store
    ):
        """When net_premium_earned is populated, headline_revenue switches to it."""
        # Mark SBIN as a life insurer (uses one of the insurance industry strings).
        self._set_industry(populated_store, "SBIN", "Insurance - Life")
        rows = api.get_annual_financials("SBIN")
        assert len(rows) > 0
        # Inject a synthetic net_premium_earned into the returned dicts and
        # re-run the swap to verify the branch (round-trip helper).
        for row in rows:
            row["net_premium_earned"] = (row.get("revenue") or 0) * 0.6
        swapped = api._apply_insurance_headline("SBIN", rows)
        for row in swapped:
            assert row["headline_revenue"] == row["net_premium_earned"]
            assert row["headline_metric"] == "net_premium_earned"
            assert "Net Premium Earned" in row["notes"]
            # Original revenue is preserved.
            assert row.get("revenue") is not None
            assert row["revenue"] != row["headline_revenue"]

    def test_insurer_without_net_premium_falls_back_with_note(
        self, api: ResearchDataAPI, populated_store
    ):
        """When net_premium_earned is null, fallback to revenue + data_quality_note."""
        self._set_industry(populated_store, "SBIN", "Insurance - Life")
        rows = api.get_annual_financials("SBIN")
        assert len(rows) > 0
        for row in rows:
            assert row.get("headline_revenue") == row.get("revenue")
            assert row.get("headline_metric") == "revenue (fallback)"
            assert "data_quality_note" in row
            assert "MTM" in row["data_quality_note"] or "mark-to-market" in row["data_quality_note"]

    def test_quarterly_results_insurer_gets_headline(
        self, api: ResearchDataAPI, populated_store
    ):
        """Quarterly path applies the same swap layer."""
        self._set_industry(populated_store, "SBIN", "Insurance - Life")
        rows = api.get_quarterly_results("SBIN")
        assert len(rows) > 0
        for row in rows:
            # Fallback path (no net_premium_earned in quarterly_results either).
            assert "headline_revenue" in row
            assert "data_quality_note" in row

    def test_screener_industry_string_also_matches(
        self, api: ResearchDataAPI, populated_store
    ):
        """Screener's bare 'Life Insurance' string also triggers the swap."""
        self._set_industry(populated_store, "SBIN", "Life Insurance")
        rows = api.get_annual_financials("SBIN")
        assert len(rows) > 0
        assert "data_quality_note" in rows[0]


class TestScreenerRatios:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_screener_ratios("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "roce_pct" in data[0]


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

class TestValuationSnapshot:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_valuation_snapshot("SBIN")
        assert isinstance(data, dict)
        assert "price" in data
        assert "pe_trailing" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_valuation_snapshot("NONEXIST")
        assert data == {}


class TestReconcileSharesOutstanding:
    """Source-selection rule for share count: prefer Screener, warn on >5% disagreement."""

    def test_both_agree_returns_screener(self):
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        # Both sources agree within tolerance → use screener
        result = _reconcile_shares_outstanding(
            yfinance_shares=1_000_000_000,
            screener_shares=1_010_000_000,  # 1% spread
            symbol="TESTSYM",
        )
        assert result == 1_010_000_000

    def test_both_disagree_uses_screener_and_warns(self, caplog):
        import logging
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        # NESTLEIND-style 2x bug
        with caplog.at_level(logging.WARNING, logger="flowtracker.research.data_api"):
            result = _reconcile_shares_outstanding(
                yfinance_shares=1_928_000_000,
                screener_shares=964_000_000,
                symbol="NESTLEIND",
            )
        assert result == 964_000_000  # screener wins
        assert any(
            "share-count mismatch" in rec.message and "NESTLEIND" in rec.message
            and "using screener" in rec.message
            for rec in caplog.records
        )

    def test_only_screener_populated(self):
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        result = _reconcile_shares_outstanding(
            yfinance_shares=None,
            screener_shares=500_000_000,
            symbol="TESTSYM",
        )
        assert result == 500_000_000

    def test_only_yfinance_populated(self):
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        result = _reconcile_shares_outstanding(
            yfinance_shares=750_000_000,
            screener_shares=None,
            symbol="TESTSYM",
        )
        assert result == 750_000_000

    def test_both_zero_returns_none(self):
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        result = _reconcile_shares_outstanding(
            yfinance_shares=0,
            screener_shares=0,
            symbol="TESTSYM",
        )
        assert result is None or result == 0

    def test_both_none_returns_none(self):
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        result = _reconcile_shares_outstanding(
            yfinance_shares=None,
            screener_shares=None,
            symbol="TESTSYM",
        )
        assert result is None

    def test_within_5pct_no_warning(self, caplog):
        import logging
        from flowtracker.research.data_api import _reconcile_shares_outstanding
        with caplog.at_level(logging.WARNING, logger="flowtracker.research.data_api"):
            _reconcile_shares_outstanding(
                yfinance_shares=1_000_000_000,
                screener_shares=1_040_000_000,  # 4% spread, within tol
                symbol="TESTSYM",
            )
        # No warning should fire
        assert not any("share-count mismatch" in rec.message for rec in caplog.records)


class TestValuationSnapshotShareReconciliation:
    """get_valuation_snapshot must reconcile yfinance vs Screener share counts."""

    def test_yfinance_2x_bug_corrected_via_screener(self, tmp_db, monkeypatch, caplog):
        """When valuation_snapshot.shares_outstanding is 2x annual_financials.num_shares,
        the read layer should override with Screener and recompute mcap."""
        import logging
        from flowtracker.fund_models import ValuationSnapshot, AnnualFinancials
        from flowtracker.store import FlowStore
        from flowtracker.research.data_api import ResearchDataAPI

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with FlowStore(tmp_db) as store:
            # yfinance: 1928M shares, mcap = price × 1928M / 1e7 = 2x correct
            store.upsert_valuation_snapshot(ValuationSnapshot(
                symbol="NESTLEIND",
                date="2026-04-25",
                price=1421.3,
                market_cap=274071.34,  # buggy yfinance mcap
                shares_outstanding=1_928_314_320,
                float_shares=702_388_491,
                pe_trailing=70.0,
                book_value_per_share=22.99,
            ))
            # Screener: correct 964M shares
            store.upsert_annual_financials([AnnualFinancials(
                symbol="NESTLEIND",
                fiscal_year_end="2025-03-31",
                num_shares=964_157_160.0,
                revenue=20000.0,
                net_income=3000.0,
            )])

        api = ResearchDataAPI()
        try:
            with caplog.at_level(logging.WARNING, logger="flowtracker.research.data_api"):
                snap = api.get_valuation_snapshot("NESTLEIND")
        finally:
            api.close()

        assert snap["shares_outstanding"] == 964_157_160
        assert snap["shares_outstanding_lakh"] == round(964_157_160 / 1e5, 2)
        # mcap recomputed from corrected share count
        assert abs(snap["market_cap"] - (1421.3 * 964_157_160 / 1e7)) < 1.0
        # warning was logged
        assert any(
            "share-count mismatch" in r.message and "NESTLEIND" in r.message
            for r in caplog.records
        )


class TestValuationBand:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_valuation_band("SBIN")
        assert isinstance(data, dict)
        # May be empty if not enough data for percentile band
        # Just verify it doesn't crash


class TestPeHistory:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_pe_history("SBIN", days=90)
        assert isinstance(data, list)
        if data:
            assert "pe" in data[0]
            assert "price" in data[0]
            assert "date" in data[0]


# ---------------------------------------------------------------------------
# Ownership & Institutional
# ---------------------------------------------------------------------------

class TestShareholding:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_shareholding("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "category" in data[0]
        assert "percentage" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_shareholding("NONEXIST")
        assert len(data) == 0


class TestShareholdingChanges:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_shareholding_changes("SBIN")
        assert isinstance(data, list)
        if data:
            assert "category" in data[0]
            assert "change_pct" in data[0]


class TestInsiderTransactions:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_insider_transactions("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "person_name" in data[0]
        assert "transaction_type" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_insider_transactions("NONEXIST")
        assert len(data) == 0


class TestBulkBlockDeals:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_bulk_block_deals("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Market Signals
# ---------------------------------------------------------------------------

class TestDeliveryTrend:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_delivery_trend("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "delivery_pct" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_delivery_trend("NONEXIST")
        assert len(data) == 0


class TestPromoterPledge:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_promoter_pledge("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "pledge_pct" in data[0]


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

class TestConsensusEstimate:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_consensus_estimate("SBIN")
        assert isinstance(data, dict)
        assert "target_mean" in data
        assert "recommendation" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_consensus_estimate("NONEXIST")
        assert data == {}


class TestEarningsSurprises:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_earnings_surprises("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "surprise_pct" in data[0]


# ---------------------------------------------------------------------------
# Macro Context
# ---------------------------------------------------------------------------

class TestMacroSnapshot:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_macro_snapshot()
        assert isinstance(data, dict)
        assert "india_vix" in data
        assert "usd_inr" in data

    def test_carries_forward_partial_today_row(self, tmp_db, monkeypatch):
        """Today's row has only usd_inr; vix/brent/gsec must carry forward
        from yesterday's complete row, while top-level ``date`` stays today.
        """
        from flowtracker.macro_models import MacroSnapshot

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        store.upsert_macro_snapshots([
            MacroSnapshot(
                date="2026-04-24",
                india_vix=19.71,
                usd_inr=94.11,
                brent_crude=99.78,
                gsec_10y=6.40,
            ),
            MacroSnapshot(
                date="2026-04-25",
                india_vix=None,
                usd_inr=94.22,
                brent_crude=None,
                gsec_10y=None,
            ),
        ])
        store.close()

        api = ResearchDataAPI()
        try:
            data = api.get_macro_snapshot()
        finally:
            api.close()

        # Top-level date is today's date (latest row).
        assert data["date"] == "2026-04-25"
        # usd_inr from today's row.
        assert data["usd_inr"] == 94.22
        # Other fields carried forward from 2026-04-24.
        assert data["india_vix"] == 19.71
        assert data["brent_crude"] == 99.78
        assert data["gsec_10y"] == 6.40
        # ``<field>_as_of`` records the source date when it differs.
        assert data["india_vix_as_of"] == "2026-04-24"
        assert data["brent_crude_as_of"] == "2026-04-24"
        assert data["gsec_10y_as_of"] == "2026-04-24"
        # No as_of marker for today-sourced field.
        assert "usd_inr_as_of" not in data

    def test_embeds_system_credit_when_present(self, tmp_db, monkeypatch):
        """get_macro_snapshot embeds latest RBI WSS aggregate under 'system_credit'."""
        from flowtracker.macro_models import MacroSnapshot, MacroSystemCredit

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        store.upsert_macro_snapshots([
            MacroSnapshot(date="2026-04-25", india_vix=14.0, usd_inr=85.0,
                          brent_crude=72.0, gsec_10y=6.5),
        ])
        store.upsert_system_credit(MacroSystemCredit(
            release_date="2026-04-24",
            as_of_date="2026-04-15",
            aggregate_deposits_cr=25648470.0,
            bank_credit_cr=20921084.0,
            deposit_growth_yoy=12.2,
            credit_growth_yoy=15.0,
            cd_ratio=81.57,
            m3_growth_yoy=11.9,
        ))
        store.close()

        api = ResearchDataAPI()
        try:
            data = api.get_macro_snapshot()
        finally:
            api.close()

        assert "system_credit" in data
        sc = data["system_credit"]
        assert sc["release_date"] == "2026-04-24"
        assert sc["credit_growth_yoy"] == 15.0
        assert sc["deposit_growth_yoy"] == 12.2
        assert sc["cd_ratio"] == 81.57

    def test_omits_system_credit_when_no_wss_rows(self, tmp_db, monkeypatch):
        """system_credit key is omitted when no WSS rows exist (don't mislead with empty dict)."""
        from flowtracker.macro_models import MacroSnapshot

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        store.upsert_macro_snapshots([
            MacroSnapshot(date="2026-04-25", india_vix=14.0, usd_inr=85.0,
                          brent_crude=72.0, gsec_10y=6.5),
        ])
        store.close()

        api = ResearchDataAPI()
        try:
            data = api.get_macro_snapshot()
        finally:
            api.close()

        assert "system_credit" not in data


class TestSystemCreditSnapshot:
    def test_returns_empty_when_no_rows(self, api: ResearchDataAPI):
        # The shared `api` fixture doesn't seed system_credit.
        sc = api.get_system_credit_snapshot()
        assert sc == {}

    def test_returns_dict_when_present(self, tmp_db, monkeypatch):
        from flowtracker.macro_models import MacroSystemCredit

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        store.upsert_system_credit(MacroSystemCredit(
            release_date="2026-04-24", credit_growth_yoy=15.0,
            deposit_growth_yoy=12.2, cd_ratio=81.57,
        ))
        store.close()

        api = ResearchDataAPI()
        try:
            sc = api.get_system_credit_snapshot()
        finally:
            api.close()

        assert sc["release_date"] == "2026-04-24"
        assert sc["credit_growth_yoy"] == 15.0
        assert sc["source"] == "RBI_WSS"


class TestCommoditySnapshot:
    def test_includes_brent(self, api: ResearchDataAPI):
        """Brent crude (from macro_daily.brent_crude) must be exposed
        alongside gold/silver with the same delta shape.
        """
        data = api.get_commodity_snapshot()
        assert isinstance(data, dict)
        assert "brent" in data
        brent = data["brent"]
        assert "price" in brent
        assert "date" in brent
        assert "change_1m_pct" in brent
        assert "change_3m_pct" in brent
        assert "change_1y_pct" in brent
        assert isinstance(brent["price"], (int, float))

    def test_includes_industrial_metals(self, tmp_db, monkeypatch):
        """Aluminium and copper (LME proxies via yfinance) must be exposed
        alongside gold/silver/brent with unit and delta shape.
        """
        from flowtracker.commodity_models import CommodityPrice

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        store.upsert_commodity_prices([
            CommodityPrice(date="2026-04-23", symbol="ALUMINIUM", price=3600.0, unit="USD/MT"),
            CommodityPrice(date="2026-04-24", symbol="ALUMINIUM", price=3610.0, unit="USD/MT"),
            CommodityPrice(date="2026-04-23", symbol="COPPER", price=6.00, unit="USD/lb"),
            CommodityPrice(date="2026-04-24", symbol="COPPER", price=6.05, unit="USD/lb"),
        ])
        store.close()

        api = ResearchDataAPI()
        try:
            data = api.get_commodity_snapshot()
        finally:
            api.close()

        assert "aluminium" in data
        alu = data["aluminium"]
        assert alu["price"] == 3610.0
        assert alu["unit"] == "USD/MT"
        assert alu["date"] == "2026-04-24"
        assert "change_1m_pct" in alu

        assert "copper" in data
        cu = data["copper"]
        assert cu["price"] == 6.05
        assert cu["unit"] == "USD/lb"


class TestFiiDiiStreak:
    def test_returns_dict_with_fii_dii_keys(self, api: ResearchDataAPI):
        data = api.get_fii_dii_streak()
        assert isinstance(data, dict)
        assert "fii" in data
        assert "dii" in data


class TestFiiDiiFlows:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_fii_dii_flows(days=30)
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# FMP Data
# ---------------------------------------------------------------------------

class TestDcfValuation:
    def test_returns_dict_with_margin(self, api: ResearchDataAPI):
        data = api.get_dcf_valuation("SBIN")
        assert isinstance(data, dict)
        assert "dcf" in data
        assert "stock_price" in data
        assert "margin_of_safety_pct" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        """Plan v2 §7 E15: empty DCF returns explicit reason code, not {}.
        Unknown symbol has no annual financials → insufficient_history.
        """
        data = api.get_dcf_valuation("NONEXIST")
        assert isinstance(data, dict)
        assert data.get("fv_cr") is None
        assert data.get("reason_empty") == "insufficient_history"


class TestTechnicalIndicators:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_technical_indicators("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "indicator" in data[0]


class TestFnoMetrics:
    """get_fno_metrics aggregates fno_contracts into PCR + rollover + OI legs."""

    def _seed(self, store, symbol: str, trade_date: str = "2026-04-24") -> None:
        from flowtracker.fno_models import FnoContract
        from datetime import date

        td = date.fromisoformat(trade_date)
        cur_exp = date.fromisoformat("2026-04-30")
        nxt_exp = date.fromisoformat("2026-05-28")

        rows: list[FnoContract] = [
            # Two future expiries: current 100 OI, next 50 OI → rollover = 50/(100+50) = 33.3%
            FnoContract(
                trade_date=td, symbol=symbol, instrument="FUTSTK",
                expiry_date=cur_exp, open_interest=100, change_in_oi=10,
            ),
            FnoContract(
                trade_date=td, symbol=symbol, instrument="FUTSTK",
                expiry_date=nxt_exp, open_interest=50, change_in_oi=5,
            ),
            # Calls 200, Puts 100 → PCR = 0.5
            FnoContract(
                trade_date=td, symbol=symbol, instrument="OPTSTK",
                expiry_date=cur_exp, strike=500.0, option_type="CE",
                open_interest=200, change_in_oi=-20,
            ),
            FnoContract(
                trade_date=td, symbol=symbol, instrument="OPTSTK",
                expiry_date=cur_exp, strike=500.0, option_type="PE",
                open_interest=100, change_in_oi=15,
            ),
        ]
        store.upsert_fno_contracts(rows)

    def test_returns_none_when_no_fno_data(self, api: ResearchDataAPI):
        assert api.get_fno_metrics("UNKNOWNSYM") is None

    def test_pcr_and_rollover_aggregation(self, api: ResearchDataAPI):
        self._seed(api._store, "FNOTEST")
        m = api.get_fno_metrics("FNOTEST")
        assert m is not None
        assert m["futures_oi"] == 150
        assert m["call_oi"] == 200
        assert m["put_oi"] == 100
        assert m["pcr"] == 0.5
        # Rollover %: next/(curr+next) = 50/150 = 33.3%
        assert m["rollover_pct"] == 33.3

    def test_technical_indicators_includes_fno_when_present(
        self, api: ResearchDataAPI,
    ):
        self._seed(api._store, "SBIN")
        rows = api.get_technical_indicators("SBIN")
        assert rows
        assert "fno" in rows[0]
        assert rows[0]["fno"]["pcr"] == 0.5


class TestDupontDecomposition:
    def test_screener_path(self, api: ResearchDataAPI):
        """Should use Screener annual_financials data (source='screener')."""
        data = api.get_dupont_decomposition("SBIN")
        assert isinstance(data, dict)
        assert data.get("source") == "screener"
        assert "years" in data
        assert len(data["years"]) > 0
        year = data["years"][0]
        assert "net_profit_margin" in year
        assert "asset_turnover" in year
        assert "equity_multiplier" in year
        assert "roe_dupont" in year

    def test_unknown_symbol_returns_empty(self, api: ResearchDataAPI):
        data = api.get_dupont_decomposition("NONEXIST")
        assert data == {}


# ---------------------------------------------------------------------------
# Fair Value
# ---------------------------------------------------------------------------

class TestFairValue:
    def test_returns_dict_with_symbol(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        assert isinstance(data, dict)
        assert data["symbol"] == "SBIN"

    def test_has_dcf_component(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        # Fixture has DCF=950, estimates with target_mean=950
        assert "dcf" in data or "consensus_target" in data

    def test_has_signal(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        assert "signal" in data
        assert data["signal"] in ("DEEP VALUE", "UNDERVALUED", "FAIR VALUE", "EXPENSIVE", "INSUFFICIENT DATA")

    def test_unknown_symbol_no_crash(self, api: ResearchDataAPI):
        data = api.get_fair_value("NONEXIST")
        assert isinstance(data, dict)
        assert data["symbol"] == "NONEXIST"


# ---------------------------------------------------------------------------
# _clean applied
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Forensic Checks
# ---------------------------------------------------------------------------

class TestForensicChecks:
    def test_returns_data_for_sbin(self, api: ResearchDataAPI):
        """SBIN not tagged as BFSI in test fixture (no industry data) — returns data."""
        data = api.get_forensic_checks("SBIN")
        assert isinstance(data, dict)
        assert "years" in data

    def test_non_bfsi_returns_structure(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert isinstance(data, dict)
        assert "years" in data
        assert "cfo_ebitda_5y_avg" in data
        assert "cfo_ebitda_signal" in data
        assert "depreciation_volatility" in data
        assert "depreciation_signal" in data
        assert data["depreciation_signal"] in ("stable", "moderate", "volatile")
        assert data["cfo_ebitda_signal"] in ("clean", "moderate", "warning")

    def test_per_year_metrics(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        year = data["years"][0]
        assert "fiscal_year_end" in year
        assert "cfo_ebitda" in year
        assert "depreciation_rate" in year
        assert "cwip_ratio" in year

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("NONEXIST")
        assert "error" in data

    def test_cash_yield_signal(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert data.get("cash_yield_signal") in ("normal", "suspicious", "low")

    def test_cwip_signal(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert data.get("cwip_signal") in ("normal", "elevated", "parking_risk")


# ---------------------------------------------------------------------------
# Improvement Metrics
# ---------------------------------------------------------------------------

class TestImprovementMetrics:
    def test_returns_structure(self, api: ResearchDataAPI):
        data = api.get_improvement_metrics("INFY")
        assert isinstance(data, dict)
        assert "data_years" in data
        assert data["data_years"] == 5

    def test_bfsi_not_skipped(self, api: ResearchDataAPI):
        """Improvement metrics apply to all sectors including BFSI."""
        data = api.get_improvement_metrics("SBIN")
        assert "skipped" not in data
        assert "data_years" in data

    def test_insufficient_data_no_trajectories(self, api: ResearchDataAPI):
        """With only 5 years, trajectories require 6+ so should be absent."""
        data = api.get_improvement_metrics("INFY")
        # 5 years fixture → trajectories may be empty
        if data["data_years"] < 6:
            assert data.get("trajectories") is None or data.get("trajectories") == {}

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_improvement_metrics("NONEXIST")
        assert "error" in data

    def test_with_10_years(self, api: ResearchDataAPI, populated_store: "FlowStore"):
        """With 10 years of data, trajectories and greatness should be populated."""
        from tests.fixtures.factories import make_annual_financials, make_screener_ratios
        # Insert 10 years for INFY
        populated_store.upsert_annual_financials(make_annual_financials("INFY", n=10))
        populated_store.upsert_screener_ratios(make_screener_ratios("INFY", n=10))
        data = api.get_improvement_metrics("INFY")
        assert data["data_years"] == 10
        assert data.get("trajectories") is not None
        # ROE is computed from annuals directly — should always have 6+ values
        assert "roe" in data["trajectories"]
        assert "improvement" in data["trajectories"]["roe"]
        assert "consistency" in data["trajectories"]["roe"]
        # ROCE may not have 6 matching FYs due to fixture alignment — check if present
        if "roce" in data["trajectories"]:
            assert "improvement" in data["trajectories"]["roce"]
        # Greatness
        assert data.get("greatness") is not None
        assert data["greatness"]["classification"] in ("great", "good", "mediocre")
        assert 0 <= data["greatness"]["score_pct"] <= 100
        # Capex productivity
        assert data.get("capex_productivity") is not None
        assert "gross_block_cagr_pct" in data["capex_productivity"]
        assert "sales_cagr_pct" in data["capex_productivity"]


# ---------------------------------------------------------------------------
# Capital Discipline
# ---------------------------------------------------------------------------

class TestCapitalDiscipline:
    def test_returns_data_for_sbin(self, api: ResearchDataAPI):
        """SBIN not tagged as BFSI in test fixture (no industry data) — returns data."""
        data = api.get_capital_discipline("SBIN")
        assert isinstance(data, dict)
        assert "roce_reinvestment" in data

    def test_non_bfsi_returns_structure(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        assert isinstance(data, dict)
        assert "roce_reinvestment" in data
        assert "equity_dilution" in data

    def test_roce_reinvestment_years(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        rr = data["roce_reinvestment"]
        assert "years" in rr
        assert "latest_signal" in rr
        assert rr["latest_signal"] in ("compounder", "cash_cow", "growth_trap", "challenged")
        year = rr["years"][0]
        assert "fiscal_year_end" in year

    def test_equity_dilution(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        ed = data["equity_dilution"]
        assert "shares_latest_cr" in ed
        assert "signal" in ed
        assert ed["signal"] in ("dilutive", "moderate", "stable", "buyback")

    def test_rm_cost_empty_when_no_data(self, api: ResearchDataAPI):
        """Fixture has raw_material_cost=None → rm_cost_cycle should be absent."""
        data = api.get_capital_discipline("INFY")
        # rm_cost_cycle should be None or absent since raw_material_cost is None in fixture
        assert data.get("rm_cost_cycle") is None

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("NONEXIST")
        assert "error" in data

    def test_serializable(self, api: ResearchDataAPI):
        import json
        for method in ("get_forensic_checks", "get_improvement_metrics", "get_capital_discipline"):
            data = getattr(api, method)("INFY")
            json.dumps(data)  # Should not raise


# ---------------------------------------------------------------------------
# Batch 2: Incremental ROCE, Z-Score, WC, DOL, FCF Yield, Tax, Receivables
# ---------------------------------------------------------------------------

class TestIncrementalRoce:
    def test_returns_structure(self, api: ResearchDataAPI):
        data = api.get_incremental_roce("INFY")
        assert isinstance(data, dict)
        assert "incremental_roce_3y" in data or "error" in data

    def test_has_caveat(self, api: ResearchDataAPI):
        data = api.get_incremental_roce("INFY")
        if "caveat" in data:
            assert "Capital employed" in data["caveat"]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_incremental_roce("NONEXIST")
        assert "error" in data


class TestAltmanZscore:
    def test_returns_zscore(self, api: ResearchDataAPI):
        data = api.get_altman_zscore("INFY")
        assert isinstance(data, dict)
        assert "latest_z_score" in data or "error" in data

    def test_zone_classification(self, api: ResearchDataAPI):
        data = api.get_altman_zscore("INFY")
        if "latest_zone" in data:
            assert data["latest_zone"] in ("safe", "gray", "distress")

    def test_years_list(self, api: ResearchDataAPI):
        data = api.get_altman_zscore("INFY")
        if "years" in data:
            assert isinstance(data["years"], list)
            year = data["years"][0]
            assert "z_score" in year
            assert "zone" in year

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_altman_zscore("NONEXIST")
        assert "error" in data


class TestWorkingCapitalDeterioration:
    def test_returns_structure(self, api: ResearchDataAPI):
        data = api.get_working_capital_deterioration("INFY")
        assert isinstance(data, dict)

    def test_has_ccc_trend(self, api: ResearchDataAPI):
        data = api.get_working_capital_deterioration("INFY")
        if "ccc_trend" in data:
            assert "direction" in data["ccc_trend"]
            assert data["ccc_trend"]["direction"] in ("improving", "stable", "deteriorating")

    def test_flags_list(self, api: ResearchDataAPI):
        data = api.get_working_capital_deterioration("INFY")
        if "flags" in data:
            assert isinstance(data["flags"], list)

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_working_capital_deterioration("NONEXIST")
        assert "error" in data


class TestOperatingLeverage:
    def test_works_for_all_sectors(self, api: ResearchDataAPI):
        """DOL should work for both SBIN and INFY (no BFSI skip)."""
        for sym in ("SBIN", "INFY"):
            data = api.get_operating_leverage(sym)
            assert isinstance(data, dict)
            assert "years" in data or "error" in data

    def test_dol_clipped(self, api: ResearchDataAPI):
        data = api.get_operating_leverage("INFY")
        if "years" in data:
            for y in data["years"]:
                if "dol" in y:
                    assert -10 <= y["dol"] <= 10

    def test_signal_values(self, api: ResearchDataAPI):
        data = api.get_operating_leverage("INFY")
        if "signal" in data:
            assert data["signal"] in ("high_leverage", "moderate", "low")

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_operating_leverage("NONEXIST")
        assert "error" in data


class TestFcfYield:
    def test_returns_yield(self, api: ResearchDataAPI):
        data = api.get_fcf_yield("INFY")
        assert isinstance(data, dict)

    def test_signal_values(self, api: ResearchDataAPI):
        data = api.get_fcf_yield("INFY")
        if "signal" in data:
            assert data["signal"] in ("deep_value", "attractive", "growth_priced", "hope_trade")

    def test_risk_free_ref(self, api: ResearchDataAPI):
        data = api.get_fcf_yield("INFY")
        if "risk_free_ref_pct" in data:
            assert data["risk_free_ref_pct"] == 7.0

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_fcf_yield("NONEXIST")
        assert "error" in data or data == {}


class TestTaxRateAnalysis:
    def test_returns_etr_trend(self, api: ResearchDataAPI):
        data = api.get_tax_rate_analysis("INFY")
        assert isinstance(data, dict)
        assert "years" in data or "error" in data

    def test_statutory_ref(self, api: ResearchDataAPI):
        data = api.get_tax_rate_analysis("INFY")
        if "statutory_rate_ref" in data:
            assert data["statutory_rate_ref"] == 25.17

    def test_works_for_bfsi(self, api: ResearchDataAPI):
        """Tax rate analysis should NOT be skipped for BFSI."""
        data = api.get_tax_rate_analysis("SBIN")
        assert "skipped" not in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_tax_rate_analysis("NONEXIST")
        assert "error" in data


class TestReceivablesQuality:
    def test_returns_structure(self, api: ResearchDataAPI):
        data = api.get_receivables_quality("INFY")
        assert isinstance(data, dict)

    def test_signal_values(self, api: ResearchDataAPI):
        data = api.get_receivables_quality("INFY")
        if "signal" in data:
            assert data["signal"] in ("clean", "warning", "concern")

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_receivables_quality("NONEXIST")
        assert "error" in data

    def test_batch2_serializable(self, api: ResearchDataAPI):
        """All Batch 2 methods should be JSON-serializable."""
        import json
        for method in ("get_incremental_roce", "get_altman_zscore", "get_working_capital_deterioration",
                       "get_operating_leverage", "get_fcf_yield", "get_tax_rate_analysis", "get_receivables_quality"):
            data = getattr(api, method)("INFY")
            json.dumps(data)  # Should not raise


# ---------------------------------------------------------------------------
# _clean applied
# ---------------------------------------------------------------------------

class TestClean:
    def test_no_none_values_in_quarterly(self, api: ResearchDataAPI):
        """_clean should convert None to JSON-friendly values (or strip them)."""
        data = api.get_quarterly_results("SBIN")
        # _clean passes through json.dumps/loads which converts None → null → None
        # But the key thing is it handles numpy/Decimal types
        assert isinstance(data, list)

    def test_serializable(self, api: ResearchDataAPI):
        """All API outputs should be JSON-serializable."""
        import json
        data = api.get_quarterly_results("SBIN")
        json.dumps(data)  # Should not raise

        data = api.get_fair_value("SBIN")
        json.dumps(data)


# ---------------------------------------------------------------------------
# EBITDA field router — E1 regression fix
# ---------------------------------------------------------------------------

class TestEbitdaRouterE1:
    """Regression tests for the E1 bug in plans/post-eval-fix-plan.md:
    get_quality_scores(metals|telecom) was returning depreciation as EBITDA
    when Screener-sourced annual data had operating_profit=None.

    Before fix: ebitda = (op or 0) + (dep or 0)  →  0 + dep = dep
    After fix:  falls back to bottom-up NI + tax + interest + dep
    """

    def test_helper_uses_operating_profit_when_available(self):
        """Happy path: op is present, ebitda = op + dep."""
        row = {
            "operating_profit": 30_000.0,
            "depreciation": 11_000.0,
            "net_income": 15_000.0,
            "tax": 5_000.0,
            "interest": 8_000.0,
        }
        ebitda = ResearchDataAPI._compute_ebitda_from_row(row)
        assert ebitda == 41_000.0
        assert ebitda != row["depreciation"]

    def test_helper_bottom_up_fallback_when_op_missing(self):
        """E1 bug fix: when op is None (Screener metals/telecom case),
        use NI + tax + interest + dep — not 0 + dep."""
        row = {
            "operating_profit": None,  # the bug trigger
            "depreciation": 11_096.0,  # real VEDL FY2025 value
            "net_income": 15_000.0,
            "tax": 5_000.0,
            "interest": 8_000.0,
            "revenue": 152_968.0,
        }
        ebitda = ResearchDataAPI._compute_ebitda_from_row(row)
        # EBITDA = 15000 + 5000 + 8000 + 11096 = 39096 — NOT 11096
        assert ebitda == 39_096.0
        assert ebitda != row["depreciation"], (
            "E1 regression: EBITDA must not equal depreciation"
        )

    def test_helper_handles_all_none_gracefully(self):
        """Empty row shouldn't crash — returns 0 (no useful signal)."""
        assert ResearchDataAPI._compute_ebitda_from_row({}) == 0

    def test_metals_metrics_ebitda_not_depreciation(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Integration: VEDL-like row with operating_profit=None must yield
        EBITDA != depreciation through the get_metals_metrics path."""
        from flowtracker.fund_models import AnnualFinancials

        SYMBOL = "METALX"
        # Mark as metals via company_snapshot (yfinance-owned columns)
        populated_store.upsert_snapshot_yfinance(
            SYMBOL,
            {"sector": "Basic Materials", "industry": "Steel"},
        )
        # Seed annual financials with operating_profit=None (Screener case)
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2024 + i}-03-31",
                revenue=150_000.0 + i * 5_000,
                operating_profit=None,  # the bug trigger
                depreciation=11_000.0 + i * 500,
                net_income=12_000.0 + i * 800,
                tax=4_000.0 + i * 200,
                interest=6_000.0 + i * 300,
                borrowings=90_000.0,
                cash_and_bank=5_000.0,
            )
            for i in range(3)
        ]
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            result = api.get_metals_metrics(SYMBOL)
        finally:
            api.close()

        assert "years" in result, f"Expected metals metrics, got: {result}"
        assert len(result["years"]) >= 1
        latest = result["years"][0]
        # The fiscal_year comes back as a date string from the row
        assert "ebitda" in latest
        # Find matching annual row for this fiscal year
        fy = latest["fiscal_year"]
        matching = next(r for r in rows if r.fiscal_year_end == fy)
        assert latest["ebitda"] != matching.depreciation, (
            f"E1 regression: EBITDA ({latest['ebitda']}) must not equal "
            f"depreciation ({matching.depreciation}) for metals"
        )
        # Expected bottom-up EBITDA = NI + tax + interest + dep
        expected = (
            matching.net_income + matching.tax + matching.interest + matching.depreciation
        )
        assert latest["ebitda"] == expected

    def test_telecom_metrics_ebitda_not_depreciation(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Integration: BHARTIARTL-like row with operating_profit=None must
        yield EBITDA != depreciation through get_telecom_metrics path."""
        from flowtracker.fund_models import AnnualFinancials

        SYMBOL = "TELCOX"
        populated_store.upsert_snapshot_yfinance(
            SYMBOL,
            {"sector": "Communication Services", "industry": "Telecom Services"},
        )
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2024 + i}-03-31",
                revenue=170_000.0 + i * 10_000,
                operating_profit=None,  # the bug trigger
                depreciation=45_000.0 + i * 2_000,
                net_income=20_000.0 + i * 1_500,
                tax=7_000.0 + i * 300,
                interest=12_000.0 + i * 500,
                borrowings=200_000.0,
                cash_and_bank=4_000.0,
                cfo=60_000.0,
                cfi=-55_000.0,
            )
            for i in range(3)
        ]
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            result = api.get_telecom_metrics(SYMBOL)
        finally:
            api.close()

        assert "years" in result, f"Expected telecom metrics, got: {result}"
        latest = result["years"][0]
        fy = latest["fiscal_year"]
        matching = next(r for r in rows if r.fiscal_year_end == fy)
        assert latest["ebitda"] != matching.depreciation, (
            f"E1 regression: EBITDA ({latest['ebitda']}) must not equal "
            f"depreciation ({matching.depreciation}) for telecom"
        )
        expected = (
            matching.net_income + matching.tax + matching.interest + matching.depreciation
        )
        assert latest["ebitda"] == expected


# ---------------------------------------------------------------------------
# E11 — PE / EPS basis fields on get_valuation_snapshot + get_fair_value
# ---------------------------------------------------------------------------


class TestValuationBasisFieldsE11:
    """Plan v2 §7 E11: every valuation surface must tag pe_basis and eps_basis.

    When PE and EPS come from different bases (standalone vs consolidated),
    the fair-value auto-blend must downrank the PE component to 0 and emit
    a warning field so agents can show the user *why* the blend shape shifted.
    """

    def test_snapshot_tags_basis_fields(self, api: ResearchDataAPI):
        data = api.get_valuation_snapshot("SBIN")
        assert "pe_basis" in data
        assert "eps_basis" in data
        assert data["pe_basis"] in ("standalone", "consolidated", "unknown")
        assert data["eps_basis"] in ("standalone", "consolidated", "unknown")

    def test_fair_value_matched_basis_no_warning(self, api: ResearchDataAPI):
        """When PE and EPS come from the same basis, no mismatch warning is emitted."""
        data = api.get_fair_value("SBIN")
        # SBIN seeded path: only yfinance valuation_snapshot exists (no screener_charts
        # for PE seeded by default), so both PE and EPS resolve to consolidated.
        # Mismatch warning must NOT be present.
        assert "_warning_basis_mismatch" not in data
        assert data.get("pe_basis") == "consolidated"
        # eps_basis reflects whichever source exists (standalone if annual EPS
        # is seeded via Screener factory; consolidated if consensus is seeded).
        assert data.get("eps_basis") in ("standalone", "consolidated")

    def test_fair_value_mismatch_triggers_warning_and_pe_downrank(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Seed screener_charts PE (standalone) + yfinance consensus forward_eps
        (consolidated). Expect mismatch warning + PE component dropped from blend.
        """
        from flowtracker.estimates_models import ConsensusEstimate
        from flowtracker.fund_models import ValuationSnapshot

        SYMBOL = "MISMATCHX"
        # 1. Standalone PE chart series from Screener — unique dates required by UNIQUE index
        from datetime import date, timedelta
        conn = populated_store._conn
        base_date = date(2024, 1, 15)
        for i in range(60):
            d = (base_date + timedelta(days=i * 5)).isoformat()
            conn.execute(
                "INSERT INTO screener_charts (symbol, chart_type, metric, date, value, fetched_at) "
                "VALUES (?, 'pe', 'Price to Earning', ?, ?, datetime('now'))",
                (SYMBOL, d, 18.0 + (i % 5) * 0.5),
            )
        conn.commit()
        # 2. yfinance consensus forward_eps (consolidated)
        populated_store.upsert_consensus_estimates(
            [
                ConsensusEstimate(
                    symbol=SYMBOL,
                    date="2026-04-20",
                    target_mean=850.0,
                    target_high=950.0,
                    target_low=750.0,
                    recommendation="BUY",
                    num_analysts=15,
                    forward_pe=22.0,
                    forward_eps=45.0,
                    current_price=800.0,
                )
            ]
        )
        # 3. Minimal valuation_snapshot so current_price is populated but
        # pe_trailing=None → PE basis resolves to 'standalone' via Screener chart path.
        populated_store.upsert_valuation_snapshot(
            ValuationSnapshot(
                symbol=SYMBOL,
                date="2026-04-20",
                price=800.0,
                pe_trailing=None,
            )
        )

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_fair_value(SYMBOL)
        finally:
            api.close()

        # Basis fields present
        assert data.get("pe_basis") == "standalone"
        assert data.get("eps_basis") == "consolidated"
        # Warning emitted
        assert "_warning_basis_mismatch" in data
        assert "downranked" in data["_warning_basis_mismatch"].lower()
        # If auto-blend ran, pe_band weight must be 0
        if "blend_weights" in data:
            assert data["blend_weights"]["pe_band"] == 0


# ---------------------------------------------------------------------------
# E15 — DCF reason codes when empty
# ---------------------------------------------------------------------------


class TestDcfReasonCodesE15:
    """Plan v2 §7 E15: get_dcf_valuation must classify *why* DCF is empty."""

    def test_reason_insufficient_history_when_no_annual(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Symbol with no annual financials at all → insufficient_history."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation("NOANNUAL")
        finally:
            api.close()
        assert data.get("reason_empty") == "insufficient_history"
        assert data.get("fv_cr") is None
        assert "notes" in data

    def test_reason_negative_fcf(self, tmp_db, populated_store, monkeypatch):
        """Latest FCF negative → negative_fcf."""
        from flowtracker.fund_models import AnnualFinancials
        SYMBOL = "NEGFCFX"
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2025 - i}-03-31",
                revenue=100_000.0,
                net_income=5_000.0,
                # Latest year (i=0): cfi swamps cfo → negative FCF
                cfo=5_000.0 if i > 0 else 1_000.0,
                cfi=-3_000.0 if i > 0 else -20_000.0,
            )
            for i in range(5)
        ]
        populated_store.upsert_annual_financials(rows)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()
        assert data.get("reason_empty") == "negative_fcf"

    def test_reason_insufficient_history_when_under_3y_positive(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Fewer than 3 positive-FCF years → insufficient_history."""
        from flowtracker.fund_models import AnnualFinancials
        SYMBOL = "THINFCFX"
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2025 - i}-03-31",
                revenue=100_000.0,
                net_income=5_000.0,
                cfo=2_000.0,
                cfi=-5_000.0,  # FCF negative across all years
            )
            for i in range(5)
        ]
        populated_store.upsert_annual_financials(rows)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()
        # All FCFs negative → 0 positive → insufficient_history takes precedence
        assert data.get("reason_empty") == "insufficient_history"

    def test_dcf_section_always_returned_with_reason(
        self, tmp_db, populated_store, monkeypatch
    ):
        """DCF key must never be hidden when empty — agents need to see the reason."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation("NONEXIST")
        finally:
            api.close()
        assert "reason_empty" in data
        assert "fv_cr" in data


# ---------------------------------------------------------------------------
# Wave 2 — In-house DCF fallback when FMP DCF is missing
# ---------------------------------------------------------------------------


class TestIntrinsicDcfFallbackWave2:
    """Wave 2 fix: when FMP DCF is missing but FCF history is healthy,
    compute an in-house DCF instead of returning null.

    Targets eval-plan P1 — INFY/HINDUNILVR (and other mega-caps) returning
    null DCF despite a decade of clean cash flow.
    """

    @staticmethod
    def _stable_cashcow_rows(symbol: str, base_fcf: float = 10_000.0):
        """5 years of stable, modestly growing FCF — mimics a cash-cow mega-cap."""
        from flowtracker.fund_models import AnnualFinancials
        rows = []
        # latest first: 14k, 13k, 12k, 11k, 10k → ~9% CAGR
        for i in range(5):
            year = 2025 - i
            cfo = base_fcf * (1 + (4 - i) * 0.10)
            rows.append(AnnualFinancials(
                symbol=symbol,
                fiscal_year_end=f"{year}-03-31",
                revenue=100_000.0,
                net_income=15_000.0,
                cfo=cfo + 2_000.0,  # so cfo+cfi = cfo (net of -2k capex)
                cfi=-2_000.0,
                borrowings=5_000.0,
                num_shares=1_000_000_000.0,
                profit_before_tax=20_000.0,
                tax=5_000.0,
                interest=500.0,
            ))
        return rows

    def test_intrinsic_dcf_fires_when_fmp_missing_with_clean_fcf(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Mega-cap-shaped FCF history → non-null DCF + data_quality_note."""
        SYMBOL = "MEGAFCF"
        rows = self._stable_cashcow_rows(SYMBOL)
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()

        # No FMP DCF row, but FCF clean → in-house path
        assert data.get("source") == "in_house_fallback"
        assert data.get("fv_cr") is not None
        assert data.get("fv_cr") > 0
        assert data.get("wacc") is not None
        assert data.get("terminal_growth") is not None
        # Required disclosure
        assert "data_quality_note" in data
        assert "fallback" in data["data_quality_note"].lower()

    def test_intrinsic_dcf_skipped_when_fcf_negative(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Latest FCF negative → still returns reason_empty=negative_fcf, no fallback."""
        from flowtracker.fund_models import AnnualFinancials
        SYMBOL = "NEGFCFW2"
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2025 - i}-03-31",
                revenue=100_000.0,
                net_income=5_000.0,
                cfo=5_000.0 if i > 0 else 1_000.0,
                cfi=-3_000.0 if i > 0 else -20_000.0,
            )
            for i in range(5)
        ]
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()

        assert data.get("reason_empty") == "negative_fcf"
        assert data.get("fv_cr") is None
        assert data.get("source") != "in_house_fallback"

    def test_intrinsic_dcf_skipped_when_fcf_history_thin(
        self, tmp_db, populated_store, monkeypatch
    ):
        """<3 positive FCF years → reason_empty=insufficient_history, no fallback."""
        from flowtracker.fund_models import AnnualFinancials
        SYMBOL = "THINW2"
        rows = [
            AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{2025 - i}-03-31",
                revenue=100_000.0,
                cfo=2_000.0,
                cfi=-5_000.0,
            )
            for i in range(5)
        ]
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()

        assert data.get("reason_empty") == "insufficient_history"
        assert data.get("source") != "in_house_fallback"

    def test_intrinsic_dcf_clamps_growth_above_terminal_plus_6pp(
        self, tmp_db, populated_store, monkeypatch
    ):
        """Hyper-growth FCF (but ≤30% CAGR so reason='unknown') → growth clamped + noted."""
        from flowtracker.fund_models import AnnualFinancials
        SYMBOL = "FASTGROW"
        # 25% CAGR over 4yr — passes the 30% gate, but well above terminal+6pp
        rows = []
        fcf = 10_000.0
        for i in range(5):
            year = 2025 - i
            # latest = highest, oldest = lowest
            actual_fcf = fcf * (1.25 ** (4 - i))
            rows.append(AnnualFinancials(
                symbol=SYMBOL,
                fiscal_year_end=f"{year}-03-31",
                revenue=100_000.0,
                cfo=actual_fcf + 1_000.0,
                cfi=-1_000.0,
                borrowings=0.0,
                num_shares=1_000_000_000.0,
            ))
        populated_store.upsert_annual_financials(rows)

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        try:
            data = api.get_dcf_valuation(SYMBOL)
        finally:
            api.close()

        # If WACC inputs were available, fallback fires with growth clamp note
        if data.get("source") == "in_house_fallback":
            assert "clamp" in data["data_quality_note"].lower()
            assert data["growth_used"] <= data["terminal_growth"] + 0.06 + 1e-6


# ---------------------------------------------------------------------------
# E16 — sector-index null fallback
# ---------------------------------------------------------------------------


class TestSectorIndexFallbackE16:
    """Plan v2 §7 E16: sector_index must never be null — always at least Nifty 500."""

    def test_sector_index_fallback_for_banks_regional(self, api: ResearchDataAPI):
        """'Banks - Regional' (yfinance sub-sector) → ^NSEBANK."""
        assert api._resolve_sector_index("Banks - Regional") == "^NSEBANK"

    def test_sector_index_fallback_for_nbfc_token(self, api: ResearchDataAPI):
        assert api._resolve_sector_index("nbfc") == "^NSEBANK"

    def test_sector_index_reit_maps_to_realty(self, api: ResearchDataAPI):
        assert api._resolve_sector_index("reit") == "NIFTY_REALTY.NS"

    def test_sector_index_null_defaults_to_nifty500(self, api: ResearchDataAPI):
        """Unmapped sector → NIFTY 500 (^CRSLDX), not None."""
        assert api._resolve_sector_index(None) == "^CRSLDX"
        assert api._resolve_sector_index("") == "^CRSLDX"
        assert api._resolve_sector_index("Some Unknown Sector") == "^CRSLDX"

    def test_sector_index_existing_map_still_wins(self, api: ResearchDataAPI):
        """Back-compat: entries already in _SECTOR_INDEX still resolve correctly."""
        assert api._resolve_sector_index("Private Sector Bank") == "^NSEBANK"
        assert api._resolve_sector_index("IT - Software") == "^CNXIT"


# ---------------------------------------------------------------------------
# E10 — SOTP subsidiary freshness check (bhavcopy-backed)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="E10 bhavcopy-backed subsidiary-freshness integration test deferred")
class TestSotpSubsidiaryFreshnessE10:
    def test_recently_listed_subsidiary_flagged(self):
        pass
