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

    def test_persisted_net_premium_earned_drives_headline(
        self, api: ResearchDataAPI, populated_store
    ):
        """End-to-end: persist net_premium_earned via upsert, read via API,
        confirm the swap layer picks it up — no client-side injection.

        This is the wiring test that proves the column is actually plumbed:
        Pydantic model -> upsert SQL -> SELECT -> get_annual_financials ->
        _apply_insurance_headline.
        """
        from flowtracker.fund_models import AnnualFinancials, QuarterlyResult

        self._set_industry(populated_store, "SBIN", "Life Insurance")
        # Write a row with net_premium_earned populated. Use a fresh
        # fiscal_year_end so we don't collide with the populated_store row.
        af = AnnualFinancials(
            symbol="SBIN",
            fiscal_year_end="2099-03-31",
            revenue=10_000.0,           # MTM-mixed top line (wild)
            net_premium_earned=6_500.0, # clean underwriting top line
            net_income=1_200.0,
        )
        populated_store.upsert_annual_financials([af])

        rows = api.get_annual_financials("SBIN", years=20)
        target = next((r for r in rows if r["fiscal_year_end"] == "2099-03-31"), None)
        assert target is not None, "test row was not retrieved"
        assert target["net_premium_earned"] == 6_500.0
        assert target["headline_revenue"] == 6_500.0
        assert target["headline_metric"] == "net_premium_earned"
        assert "Net Premium Earned" in target["notes"]
        # Original revenue preserved (additive transform).
        assert target["revenue"] == 10_000.0
        # The fallback note should NOT be present when we have real data.
        assert "data_quality_note" not in target

    def test_persisted_quarterly_net_premium_earned_drives_headline(
        self, api: ResearchDataAPI, populated_store
    ):
        """Same wiring test for quarterly_results."""
        from flowtracker.fund_models import QuarterlyResult

        self._set_industry(populated_store, "SBIN", "Life Insurance")
        qr = QuarterlyResult(
            symbol="SBIN",
            quarter_end="2099-12-31",
            revenue=2_500.0,
            net_premium_earned=1_700.0,
            net_income=300.0,
        )
        populated_store.upsert_quarterly_results([qr])

        rows = api.get_quarterly_results("SBIN", quarters=20)
        target = next((r for r in rows if r["quarter_end"] == "2099-12-31"), None)
        assert target is not None
        assert target["net_premium_earned"] == 1_700.0
        assert target["headline_revenue"] == 1_700.0
        assert target["headline_metric"] == "net_premium_earned"
        assert "data_quality_note" not in target


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


# ---------------------------------------------------------------------------
# Strategy 2 — ar_five_year_summary consumer wiring
# ---------------------------------------------------------------------------
# get_five_year_summary is the public surface; the four trend methods
# (DuPont, F-score, CAGR, common-size) consume it. These tests exercise the
# wiring against a fresh tmp_db so the AR rows are deterministic.

from flowtracker.data_quality import Flag  # noqa: E402
from flowtracker.fund_models import AnnualFinancials  # noqa: E402
from flowtracker.research.five_year_parser import FiveYearHighlight  # noqa: E402


def _ar_row(fy_end: str, *, revenue: float, pat: float, total_assets: float,
            net_worth: float, cfo: float = 1500.0, capex: float = 800.0,
            operating_profit: float = 1800.0, borrowings: float = 5000.0,
            eps: float = 12.0, num_shares: float = 1000.0,
            source_ar_fy: str = "FY25") -> FiveYearHighlight:
    """Synthetic AR row for Strategy 2 wiring tests."""
    return FiveYearHighlight(
        fy_end=fy_end, revenue=revenue, operating_profit=operating_profit,
        pat=pat, eps=eps, net_worth=net_worth, total_assets=total_assets,
        borrowings=borrowings, cfo=cfo, capex=capex,
        dividend_per_share=2.5, num_shares=num_shares,
        source_ar_fy=source_ar_fy, raw_unit="crore",
    )


def _annual_full(fy: str, *, revenue: float = 100000.0, net_income: float = 10000.0,
                 total_assets: float = 200000.0, equity: float = 50000.0,
                 cfo: float = 12000.0, borrowings: float = 30000.0,
                 operating_profit: float = 15000.0, eps: float = 10.0,
                 num_shares: float = 1000.0,
                 raw_material_cost: float = 40000.0,
                 interest: float = 2000.0,
                 depreciation: float = 3000.0,
                 **extras) -> AnnualFinancials:
    fields = dict(
        symbol="X", fiscal_year_end=fy, revenue=revenue, net_income=net_income,
        total_assets=total_assets, equity_capital=equity, reserves=0.0,
        cfo=cfo, borrowings=borrowings, operating_profit=operating_profit,
        eps=eps, num_shares=num_shares,
        raw_material_cost=raw_material_cost, interest=interest,
        depreciation=depreciation,
    )
    fields.update(extras)
    return AnnualFinancials(**fields)


def _flag(symbol: str, curr_fy: str, line: str, severity: str = "MEDIUM",
          prior_fy: str | None = None) -> Flag:
    """Build a Flag matching the data_quality_api helper."""
    return Flag(
        symbol=symbol, prior_fy=prior_fy or "2024-03-31", curr_fy=curr_fy,
        line=line, prior_val=100.0, curr_val=400.0, jump_pct=300.0,
        revenue_change_pct=5.0, flag_type="RECLASS", severity=severity,
    )


@pytest.fixture
def s2_api(tmp_db, monkeypatch) -> ResearchDataAPI:
    """Fresh tmp_db ResearchDataAPI for Strategy 2 wiring tests."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# ---- get_five_year_summary surface --------------------------------------

class TestGetFiveYearSummarySurface:
    def test_returns_rows_when_persisted(self, s2_api: ResearchDataAPI):
        rows = [
            _ar_row("2026-03-31", revenue=20000.0, pat=4000.0,
                    total_assets=200000.0, net_worth=80000.0),
            _ar_row("2025-03-31", revenue=18000.0, pat=3500.0,
                    total_assets=180000.0, net_worth=72000.0),
        ]
        s2_api._store.upsert_five_year_summary("HDFCBANK", rows)
        out = s2_api.get_five_year_summary("HDFCBANK")
        assert isinstance(out, list)
        assert len(out) == 2
        # Sorted DESC by fy_end
        assert out[0]["fy_end"] == "2026-03-31"
        assert out[1]["fy_end"] == "2025-03-31"
        # Pass-through of all columns
        assert out[0]["revenue"] == 20000.0
        assert out[0]["pat"] == 4000.0
        assert out[0]["source_ar_fy"] == "FY25"
        assert out[0]["raw_unit"] == "crore"

    def test_returns_empty_for_unknown_symbol(self, s2_api: ResearchDataAPI):
        assert s2_api.get_five_year_summary("NOT_A_REAL_STOCK") == []


# ---- DuPont — Strategy 2 ------------------------------------------------

class TestDupontStrategy2:
    def _seed_ar(self, api, symbol: str, fys: list[str]) -> None:
        # Build a clean restated 5-year AR series.
        rows = [
            _ar_row(fy, revenue=20000.0 + i * 1000, pat=4000.0 + i * 200,
                    total_assets=200000.0 + i * 5000,
                    net_worth=80000.0 + i * 2000)
            for i, fy in enumerate(fys)
        ]
        api._store.upsert_five_year_summary(symbol, rows)

    def test_full_window_uses_ar_when_screener_narrowed(self, s2_api):
        """Screener has a MEDIUM flag at FY26 → without AR, DuPont narrows
        to [FY26]. With AR fully covering FY26-FY24 AND aggregate-bridging
        (Gemini #7) restoring the older Screener years to the segment,
        the result is hybrid: AR for FY26/FY25/FY24 + Screener-bridged for
        FY23/FY22. Bridging is invisible to the AR-covered years.

        The test fixture's expense components on the flagged boundary are
        all None, so `total_expenses` falls back to a sum of zeros — both
        sides land at 0 cr, and `compute_aggregate_bridge` returns None
        (parent missing on either side). Build the pair so the parent IS
        bridge-able by populating total_expenses directly.
        """
        # Screener has 5 years; expenses populated so the parent aggregate
        # exists on both sides of the flagged boundary.
        annuals = [_annual_full(f"202{i}-03-31",
                                total_expenses=80000.0,
                                other_expenses_detail=20000.0)
                   for i in (6, 5, 4, 3, 2)]
        # Make FY26 total_expenses YoY +10% (within tolerance vs revenue +0%)
        annuals[0].total_expenses = 88000.0
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        # AR has 3 most-recent years
        self._seed_ar(s2_api, "X", ["2026-03-31", "2025-03-31", "2024-03-31"])

        result = s2_api.get_dupont_decomposition("X")
        # AR + bridged Screener → mixed.
        assert result["data_source"] == "mixed"
        assert result["source"] == "mixed"
        years_in_result = [r["fiscal_year_end"] for r in result["years"]]
        # AR-covered years still present.
        assert "2026-03-31" in years_in_result
        assert "2025-03-31" in years_in_result
        assert "2024-03-31" in years_in_result
        # Older Screener years now recovered via bridging.
        assert "2023-03-31" in years_in_result
        assert "2022-03-31" in years_in_result
        ew = result["effective_window"]
        # Bridged path → narrowed_due_to is empty, bridged_years populated.
        assert ew["narrowed_due_to"] == []
        assert "2026-03-31" in ew["bridged_years"]
        # AR-covered rows tagged ar_five_year_summary; Screener-bridged
        # rows tagged screener_annual_bridged.
        sources = {y["fiscal_year_end"]: y["source"] for y in result["years"]}
        assert sources["2026-03-31"] == "ar_five_year_summary"
        assert sources["2024-03-31"] == "ar_five_year_summary"
        # FY23 / FY22 fall back to Screener — not in bridged_years (the
        # boundary flag is at FY26), so they're plain screener_annual.
        assert sources["2023-03-31"] == "screener_annual"
        assert result.get("bridged_via_aggregate") is True

    def test_screener_path_when_no_ar_rows(self, s2_api):
        """Without AR rows the legacy Screener path runs unchanged."""
        annuals = [_annual_full(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_dupont_decomposition("X")
        assert result["data_source"] == "screener_annual"
        assert result["source"] == "screener"
        assert len(result["years"]) == 5

    def test_hybrid_when_ar_covers_only_recent_years(self, s2_api):
        """AR has 3 most-recent years, Screener has 5 years and is narrowed
        to 1 year (FY26). Hybrid: AR for the 3 AR years, Screener fills
        the rest of the (narrowed) window. Since AR fully covers
        Screener's narrowed segment ([FY26] alone is in AR), this collapses
        to pure-AR — confirms Strategy 2 dominance over a narrowed
        Screener segment.

        We blow out total_expenses on the FY26 boundary so aggregate
        bridging (Gemini #7) does NOT apply — the parent isn't conserved,
        so Screener stays narrowed and AR fully covers it.
        """
        annuals = [_annual_full(f"202{i}-03-31",
                                total_expenses=80000.0)
                   for i in (6, 5, 4, 3, 2)]
        # FY26 total_expenses doubles → not bridge-able.
        annuals[0].total_expenses = 160000.0
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        # AR covers FY26 only — minimal coverage
        self._seed_ar(s2_api, "X", ["2026-03-31"])
        result = s2_api.get_dupont_decomposition("X")
        # Single AR year covers Screener's narrowed [FY26] → pure AR path.
        assert result["data_source"] == "ar_five_year_summary"
        assert result["effective_window"]["narrowed_due_to"] == []


# ---- F-Score — Strategy 2 -----------------------------------------------

class TestPiotroskiStrategy2:
    def test_uses_ar_pair_when_screener_pair_flagged(self, s2_api):
        """Screener (T, T-1) flagged → without AR, F-score abstains. With
        AR T and T-1 both populated, F-score computes from AR and
        annotates data_source='ar_five_year_summary'."""
        annuals = [_annual_full(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        rows = [
            _ar_row("2026-03-31", revenue=20000.0, pat=4000.0,
                    total_assets=200000.0, net_worth=80000.0,
                    cfo=5000.0, borrowings=30000.0,
                    operating_profit=6000.0, num_shares=1000.0),
            _ar_row("2025-03-31", revenue=18000.0, pat=3500.0,
                    total_assets=180000.0, net_worth=72000.0,
                    cfo=4500.0, borrowings=32000.0,
                    operating_profit=5500.0, num_shares=1000.0),
        ]
        s2_api._store.upsert_five_year_summary("X", rows)
        result = s2_api.get_piotroski_score("X")
        # No abstain — AR-restated pair is internally consistent.
        assert "error" not in result, f"unexpected abstain: {result}"
        assert result["data_source"] == "ar_five_year_summary"
        assert "score" in result
        assert isinstance(result["score"], int)
        ew = result["effective_window"]
        assert ew["narrowed_due_to"] == []

    def test_falls_back_to_screener_path_when_ar_missing(self, s2_api):
        """No AR rows → legacy Screener path runs."""
        annuals = [_annual_full(f"202{i}-03-31") for i in (6, 5, 4)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_piotroski_score("X")
        assert result.get("data_source") == "screener_annual"
        assert "score" in result

    def test_abstains_when_ar_lacks_required_fields(self, s2_api):
        """AR rows present but missing borrowings → fall through to legacy
        Screener path, which abstains because of the flag.

        Blow out total_expenses on the FY26 boundary so aggregate bridging
        (Gemini #7) does NOT salvage the Screener pair — only the legacy
        abstain path remains.
        """
        annuals = [_annual_full(f"202{i}-03-31",
                                total_expenses=80000.0)
                   for i in (6, 5, 4, 3, 2)]
        annuals[0].total_expenses = 200000.0  # +150% vs revenue 0% — not bridge-able
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        # AR rows missing `borrowings`
        rows = [
            FiveYearHighlight(
                fy_end="2026-03-31", revenue=20000.0, pat=4000.0,
                total_assets=200000.0, net_worth=80000.0,
                cfo=5000.0, operating_profit=6000.0,
                source_ar_fy="FY26", raw_unit="crore",
                # borrowings intentionally None
            ),
            FiveYearHighlight(
                fy_end="2025-03-31", revenue=18000.0, pat=3500.0,
                total_assets=180000.0, net_worth=72000.0,
                cfo=4500.0, operating_profit=5500.0,
                source_ar_fy="FY26", raw_unit="crore",
            ),
        ]
        s2_api._store.upsert_five_year_summary("X", rows)
        result = s2_api.get_piotroski_score("X")
        # Falls through to Screener, which abstains on the flag.
        assert result.get("reason") == "stale_due_to_reclass"
        assert result.get("data_source") == "screener_annual"


# ---- CAGR — Strategy 2 --------------------------------------------------

class TestCagrTableStrategy2:
    def test_revenue_ni_eps_from_ar_when_endpoints_available(self, s2_api):
        """AR has FY26 and FY24 rows → 1y / 3y revenue, NI, EPS CAGRs come
        from the restated series. data_source becomes 'ar_five_year_summary'
        when every populated cell came from AR."""
        annuals = [_annual_full(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
        s2_api._store.upsert_annual_financials(annuals)
        # AR covers the most recent 5 years — supplies endpoints for 1y / 3y / 5y.
        rows = [
            _ar_row(fy, revenue=20000.0 + i * 1000, pat=4000.0 + i * 200,
                    total_assets=200000.0 + i * 5000,
                    net_worth=80000.0 + i * 2000,
                    eps=12.0 + i, cfo=5000.0 + i * 100, capex=2000.0 + i * 50)
            for i, fy in enumerate([
                "2026-03-31", "2025-03-31", "2024-03-31", "2023-03-31", "2022-03-31",
            ])
        ]
        s2_api._store.upsert_five_year_summary("X", rows)
        result = s2_api.get_growth_cagr_table("X")
        # data_source — at least one cell from AR
        assert result["data_source"] in ("ar_five_year_summary", "mixed")
        # Per-cell source tracking
        spc = result["source_per_cell"]
        # Revenue 1y / 3y / 5y endpoints all in AR → AR-sourced
        assert spc.get("revenue.1y") == "ar_five_year_summary"
        assert spc.get("revenue.3y") == "ar_five_year_summary"
        # 10y endpoint (FY16) not in AR → Screener-sourced
        assert spc.get("revenue.10y") == "screener_annual"
        assert result["data_source"] == "mixed"

    def test_falls_back_to_screener_when_no_ar(self, s2_api):
        """No AR rows → legacy Screener path; data_source='screener_annual'."""
        annuals = [_annual_full(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_growth_cagr_table("X")
        assert result["data_source"] == "screener_annual"

    def test_ar_cells_not_suppressed_by_screener_flags(self, s2_api):
        """AR-sourced cells must NOT be suppressed by Screener reclass flags
        — that's the whole point of Strategy 2: AR is restated."""
        annuals = [_annual_full(f"20{i:02d}-03-31",
                                operating_profit=20000.0, depreciation=3000.0)
                   for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
        s2_api._store.upsert_annual_financials(annuals)
        # Flag depreciation at FY26 — would normally suppress EBITDA + FCF
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "depreciation", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        # AR provides revenue / pat / cfo / capex (FCF) for endpoints
        rows = [
            _ar_row(fy, revenue=20000.0 + i * 1000, pat=4000.0 + i * 200,
                    total_assets=200000.0 + i * 5000,
                    net_worth=80000.0 + i * 2000,
                    cfo=5000.0 + i * 100, capex=2000.0 + i * 50)
            for i, fy in enumerate([
                "2026-03-31", "2025-03-31", "2024-03-31",
            ])
        ]
        s2_api._store.upsert_five_year_summary("X", rows)
        result = s2_api.get_growth_cagr_table("X")
        # FCF 1y from AR — not suppressed even though depreciation flagged.
        assert result["source_per_cell"].get("fcf.1y") == "ar_five_year_summary"
        assert result["cagrs"]["fcf"].get("1y") is not None


# ---- Common-size — Strategy 2 -------------------------------------------

class TestCommonSizeStrategy2:
    def test_data_source_screener_when_no_ar(self, s2_api):
        """Without AR rows, common-size annotates data_source='screener_annual'."""
        rows = [_annual_full(f"202{i}-03-31",
                             profit_before_tax=12000.0,
                             employee_cost=10000.0)
                for i in (6, 5, 4, 3, 2)]
        for r in rows:
            r.profit_before_tax = 12000.0
        s2_api._store.upsert_annual_financials(rows)
        result = s2_api.get_common_size_pl("X")
        assert result["data_source"] == "screener_annual"
        assert result["ar_confirmed_years"] == []

    def test_mixed_when_ar_confirms_narrowed_segment(self, s2_api):
        """Screener narrowed to [FY26] AND AR has FY26 → mixed annotation.

        Set total_expenses jump high enough to fall outside the bridging
        tolerance so the legacy narrow-then-AR-confirm path runs (Gemini #7
        bridging would otherwise restore the full window and route to
        `screener_annual_bridged`).
        """
        rows = [_annual_full(f"202{i}-03-31",
                             profit_before_tax=12000.0,
                             employee_cost=10000.0,
                             total_expenses=80000.0)
                for i in (6, 5, 4, 3, 2)]
        # FY26 total_expenses doubles — way outside bridging tolerance.
        rows[0].total_expenses = 200000.0
        s2_api._store.upsert_annual_financials(rows)
        s2_api._store.upsert_data_quality_flags([
            _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
                  prior_fy="2025-03-31"),
        ])
        s2_api._store.upsert_five_year_summary("X", [
            _ar_row("2026-03-31", revenue=20000.0, pat=4000.0,
                    total_assets=200000.0, net_worth=80000.0),
        ])
        result = s2_api.get_common_size_pl("X")
        assert result["data_source"] == "mixed"
        assert "2026-03-31" in result["ar_confirmed_years"]


# ---- Annotation contract: every response carries data_source -------------

# Allowed data_source values now include `screener_annual_bridged`
# (Gemini review item #7 — aggregate bridging).
_ALLOWED_DATA_SOURCES = (
    "ar_five_year_summary", "screener_annual", "screener_annual_bridged", "mixed",
)


class TestDataSourceAnnotationContract:
    def test_dupont_carries_data_source(self, s2_api):
        annuals = [_annual_full(f"202{i}-03-31") for i in (6, 5, 4)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_dupont_decomposition("X")
        assert result["data_source"] in _ALLOWED_DATA_SOURCES

    def test_piotroski_carries_data_source(self, s2_api):
        annuals = [_annual_full(f"202{i}-03-31") for i in (6, 5, 4)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_piotroski_score("X")
        # Either a successful score with data_source, or an abstain dict
        # with data_source — both must include the field.
        assert result.get("data_source") in _ALLOWED_DATA_SOURCES

    def test_cagr_carries_data_source(self, s2_api):
        annuals = [_annual_full(f"20{i:02d}-03-31") for i in (26, 25, 24, 23)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_growth_cagr_table("X")
        assert result["data_source"] in _ALLOWED_DATA_SOURCES

    def test_common_size_carries_data_source(self, s2_api):
        annuals = [_annual_full(f"202{i}-03-31",
                                profit_before_tax=12000.0,
                                employee_cost=10000.0)
                   for i in (6, 5, 4)]
        s2_api._store.upsert_annual_financials(annuals)
        result = s2_api.get_common_size_pl("X")
        assert result["data_source"] in _ALLOWED_DATA_SOURCES


# ---------------------------------------------------------------------------
# Aggregate-bridging consumer wiring (Gemini review item #7)
# ---------------------------------------------------------------------------
# Strategy 1 narrows the window when a per-component flag (e.g.
# other_expenses_detail) fires, even though the parent aggregate
# (total_expenses) is conserved within tolerance. Bridging restores the
# full window for ratio-level consumers (DuPont, F-score, common-size, CAGR).


def _annual_bridged(fy: str, *, total_expenses: float,
                    revenue: float = 100000.0, **kw) -> AnnualFinancials:
    """AnnualFinancials with explicit total_expenses for bridging tests."""
    return _annual_full(fy, revenue=revenue, total_expenses=total_expenses, **kw)


class TestDupontBridging:
    """DuPont: when all dropped flags have aggregate_bridge.conserved=true,
    use the full window with `data_source='screener_annual_bridged'` and
    `bridged_via_aggregate=true`."""

    def test_hdfcbank_style_bridges_full_window(self, s2_api):
        """Mirrors HDFCBANK FY26: revenue +3.6%, total_expenses +11.2%
        (within 10pp tolerance band) → bridge restores window."""
        # Revenue 100K → 103.6K (+3.6%); total_expenses 80K → 88.96K (+11.2%).
        annuals = [
            _annual_bridged("2022-03-31", revenue=90000.0, total_expenses=72000.0),
            _annual_bridged("2023-03-31", revenue=94500.0, total_expenses=75600.0),
            _annual_bridged("2024-03-31", revenue=99225.0, total_expenses=79380.0),
            _annual_bridged("2025-03-31", revenue=100000.0, total_expenses=80000.0),
            _annual_bridged("2026-03-31", revenue=103600.0, total_expenses=88960.0),
        ]
        s2_api._store.upsert_annual_financials(annuals)
        # Flag at FY26 with revenue change matching the actual 3.6%.
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 400.0, 300.0, 3.6, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_dupont_decomposition("X")
        assert result["data_source"] == "screener_annual_bridged"
        assert result.get("bridged_via_aggregate") is True
        # Full 5-year window restored.
        assert len(result["years"]) == 5
        ew = result["effective_window"]
        assert ew["narrowed_due_to"] == []
        assert "2026-03-31" in ew["bridged_years"]
        # The bridged year is tagged screener_annual_bridged at the row level.
        sources = {y["fiscal_year_end"]: y["source"] for y in result["years"]}
        assert sources["2026-03-31"] == "screener_annual_bridged"
        # Older years tagged plain screener_annual.
        assert sources["2024-03-31"] == "screener_annual"

    def test_infy_style_does_not_bridge(self, s2_api):
        """INFY FY26 mirror: revenue +9.6% but total_expenses +20.7% — gap
        11pp > 10pp tolerance → bridge fails, narrowing preserved."""
        annuals = [
            _annual_bridged(f"202{i}-03-31",
                            revenue=100000.0, total_expenses=80000.0)
            for i in (2, 3, 4, 5, 6)
        ]
        annuals[-1].revenue = 109600.0  # +9.6%
        annuals[-1].total_expenses = 96560.0  # +20.7%
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 3000.0, 2900.0, 9.6, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_dupont_decomposition("X")
        # Not bridged → standard narrowing.
        assert result["data_source"] == "screener_annual"
        assert result.get("bridged_via_aggregate") is False
        ew = result["effective_window"]
        assert ew["narrowed_due_to"] != []  # narrowing still occurred

    def test_strategy2_dominates_bridging(self, s2_api):
        """When AR has the bridged year, AR wins — bridge annotation is
        per-row but data_source is 'mixed' or 'ar_five_year_summary',
        not 'screener_annual_bridged'."""
        annuals = [
            _annual_bridged(f"202{i}-03-31",
                            revenue=100000.0, total_expenses=80000.0)
            for i in (2, 3, 4, 5, 6)
        ]
        annuals[-1].total_expenses = 88000.0  # bridge-able
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 400.0, 300.0, 3.6, "RECLASS", "MEDIUM"),
        ])
        # AR covers ALL 5 years → AR wins, no bridging mention at top level.
        rows = [
            FiveYearHighlight(
                fy_end=f"202{i}-03-31", revenue=20000.0 + j * 1000,
                pat=4000.0 + j * 200, total_assets=200000.0 + j * 5000,
                net_worth=80000.0 + j * 2000, source_ar_fy="FY26",
                raw_unit="crore",
            )
            for j, i in enumerate([6, 5, 4, 3, 2])
        ]
        s2_api._store.upsert_five_year_summary("X", rows)
        result = s2_api.get_dupont_decomposition("X")
        # AR fully covers segment → pure AR.
        assert result["data_source"] == "ar_five_year_summary"
        # AR-primary path — no bridge annotation at the top level.
        assert "bridged_years" not in result["effective_window"]


class TestPiotroskiBridging:
    """F-score: when (T, T-1) pair flag is bridge-conserved AND no AR pair
    available, compute the score with bridged annotation instead of
    abstaining."""

    def test_bridges_when_pair_aggregate_conserved(self, s2_api):
        annuals = [
            _annual_bridged("2025-03-31", revenue=100000.0, total_expenses=80000.0,
                            net_income=10000.0, total_assets=200000.0,
                            cfo=12000.0, borrowings=30000.0,
                            operating_profit=15000.0,
                            equity_capital=50000.0, num_shares=100000000,
                            depreciation=3000.0, raw_material_cost=40000.0,
                            interest=2000.0),
            _annual_bridged("2026-03-31", revenue=103600.0, total_expenses=88960.0,
                            net_income=11000.0, total_assets=210000.0,
                            cfo=13000.0, borrowings=29000.0,
                            operating_profit=15500.0,
                            equity_capital=50000.0, num_shares=100000000,
                            depreciation=3100.0, raw_material_cost=41000.0,
                            interest=2100.0),
        ]
        # Need 5 years for the helper to find segment[0]; pad with prior years.
        more = [_annual_bridged(f"202{i}-03-31", revenue=90000.0, total_expenses=72000.0,
                                net_income=9000.0, total_assets=190000.0,
                                cfo=11000.0, borrowings=31000.0,
                                operating_profit=14000.0,
                                equity_capital=50000.0, num_shares=100000000,
                                depreciation=3000.0, raw_material_cost=39000.0,
                                interest=2000.0)
                for i in (2, 3, 4)]
        s2_api._store.upsert_annual_financials(more + annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 400.0, 300.0, 3.6, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_piotroski_score("X")
        # Did NOT abstain — bridged.
        assert "error" not in result
        assert result["data_source"] == "screener_annual_bridged"
        assert result.get("bridged_via_aggregate") is True
        ew = result["effective_window"]
        assert ew["narrowed_due_to"] == []
        assert "2026-03-31" in ew["bridged_years"]
        assert "score" in result

    def test_does_not_bridge_when_aggregate_blew_out(self, s2_api):
        """INFY-style: aggregate not conserved → still abstains."""
        annuals = [
            _annual_bridged("2025-03-31", revenue=100000.0, total_expenses=80000.0,
                            net_income=10000.0, total_assets=200000.0,
                            cfo=12000.0, borrowings=30000.0,
                            operating_profit=15000.0, num_shares=100000000),
            _annual_bridged("2026-03-31", revenue=109600.0, total_expenses=96560.0,
                            net_income=11000.0, total_assets=210000.0,
                            cfo=13000.0, borrowings=29000.0,
                            operating_profit=15500.0, num_shares=100000000),
        ]
        more = [_annual_bridged(f"202{i}-03-31", revenue=90000.0, total_expenses=72000.0,
                                net_income=9000.0, total_assets=190000.0,
                                cfo=11000.0, borrowings=31000.0,
                                operating_profit=14000.0, num_shares=100000000)
                for i in (2, 3, 4)]
        s2_api._store.upsert_annual_financials(more + annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 3000.0, 2900.0, 9.6, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_piotroski_score("X")
        assert result.get("reason") == "stale_due_to_reclass"
        assert result.get("data_source") == "screener_annual"


class TestCommonSizeBridging:
    def test_bridges_when_conserved(self, s2_api):
        """All flags bridge-conserved → full window restored, data_source
        becomes screener_annual_bridged."""
        annuals = [
            _annual_bridged(f"202{i}-03-31",
                            revenue=100000.0, total_expenses=80000.0,
                            employee_cost=20000.0,
                            other_expenses_detail=10000.0,
                            profit_before_tax=12000.0,
                            interest=2000.0)
            for i in (2, 3, 4, 5, 6)
        ]
        annuals[-1].total_expenses = 88000.0  # +10% bridge-able
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 400.0, 300.0, 3.6, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_common_size_pl("X")
        assert result["data_source"] == "screener_annual_bridged"
        assert result.get("bridged_via_aggregate") is True
        assert len(result["years"]) == 5

    def test_bs_flag_does_not_bridge_common_size(self, s2_api):
        """Common-size is a P&L ratio — only total_expenses parent counts.
        A BS-only flag (borrowings) gets an aggregate_bridge against
        total_assets, but common-size requires `parent='total_expenses'`,
        so it does NOT bridge — falls back to legacy narrowing."""
        annuals = [
            _annual_bridged(f"202{i}-03-31",
                            revenue=100000.0, total_expenses=80000.0,
                            employee_cost=20000.0,
                            other_expenses_detail=10000.0,
                            profit_before_tax=12000.0,
                            interest=2000.0,
                            total_assets=200000.0,
                            borrowings=30000.0)
            for i in (2, 3, 4, 5, 6)
        ]
        annuals[-1].total_assets = 215000.0  # +7.5% TA — within BS tolerance
        annuals[-1].borrowings = 100000.0  # huge borrowings jump
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "borrowings",
                 30000.0, 100000.0, 233.0, 0.0, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_common_size_pl("X")
        # The borrowings flag IS bridge-conserved (BS via total_assets), but
        # common-size only bridges P&L parent → falls back to narrowing.
        assert result["data_source"] in ("screener_annual", "mixed")
        assert result.get("bridged_via_aggregate") is False


class TestCagrBridging:
    def test_per_cell_survives_when_dependency_flag_bridges(self, s2_api):
        """EBITDA depends on depreciation — when depreciation flag is
        bridge-conserved, the EBITDA cell survives with
        `screener_annual_bridged` source."""
        annuals = [
            _annual_full(f"20{i:02d}-03-31",
                         operating_profit=20000.0, depreciation=3000.0,
                         total_expenses=80000.0, revenue=100000.0)
            for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)
        ]
        # FY26 depreciation flag — bridgeable: total_expenses +5% within band.
        annuals[0].total_expenses = 84000.0
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "depreciation",
                 3000.0, 5000.0, 66.7, 0.0, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_growth_cagr_table("X")
        # EBITDA 1y depends on depreciation; flag bridged → cell present.
        ebitda_row = result["cagrs"].get("ebitda", {})
        assert ebitda_row.get("1y") is not None
        spc = result["source_per_cell"]
        assert spc.get("ebitda.1y") == "screener_annual_bridged"
        ew = result["effective_window"]
        assert {"metric": "ebitda", "horizon": "1y"} in ew["bridged_cells"]
        assert result.get("bridged_via_aggregate") is True

    def test_per_cell_suppressed_when_dependency_flag_not_bridge_conserved(self, s2_api):
        annuals = [
            _annual_full(f"20{i:02d}-03-31",
                         operating_profit=20000.0, depreciation=3000.0,
                         total_expenses=80000.0, revenue=100000.0)
            for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)
        ]
        # Total_expenses doubles → not bridgeable.
        annuals[0].total_expenses = 160000.0
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "depreciation",
                 3000.0, 5000.0, 66.7, 0.0, "RECLASS", "MEDIUM"),
        ])
        result = s2_api.get_growth_cagr_table("X")
        # EBITDA 1y suppressed (legacy behaviour).
        ebitda_row = result["cagrs"].get("ebitda", {})
        assert ebitda_row.get("1y") is None
        spc = result["source_per_cell"]
        assert "ebitda.1y" not in spc
        ew = result["effective_window"]
        assert {"metric": "ebitda", "horizon": "1y"} in ew["suppressed_cells"]


class TestGetDataQualityFlagsAttachesBridge:
    """The API-level get_data_quality_flags MUST enrich each flag with
    aggregate_bridge — that's the single contract change that lets
    consumers downstream make the bridge decision."""

    def test_flags_carry_bridge_field(self, s2_api):
        annuals = [
            _annual_bridged(f"202{i}-03-31",
                            revenue=100000.0, total_expenses=80000.0)
            for i in (5, 6)
        ]
        annuals[-1].total_expenses = 88000.0
        s2_api._store.upsert_annual_financials(annuals)
        s2_api._store.upsert_data_quality_flags([
            Flag("X", "2025-03-31", "2026-03-31", "other_expenses_detail",
                 100.0, 400.0, 300.0, 3.6, "RECLASS", "MEDIUM"),
        ])
        flags = s2_api.get_data_quality_flags("X", min_severity="MEDIUM")
        assert len(flags) == 1
        f = flags[0]
        assert "aggregate_bridge" in f
        assert f["aggregate_bridge"] is not None
        assert f["aggregate_bridge"]["parent"] == "total_expenses"
        assert f["aggregate_bridge"]["conserved"] is True

    def test_empty_flag_list_returns_empty(self, s2_api):
        # No flags persisted; method must return [] not crash on empty rows.
        flags = s2_api.get_data_quality_flags("NOSUCH", min_severity="MEDIUM")
        assert flags == []
