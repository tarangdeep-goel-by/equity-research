"""Tests for all Pydantic models across the project.

Covers construction, optional fields, extra="ignore" behavior, and computed properties.
"""

from __future__ import annotations

from datetime import date

import pytest

# ---------------------------------------------------------------------------
# flowtracker.models
# ---------------------------------------------------------------------------
from flowtracker.models import (
    DailyFlow,
    DailyFlowPair,
    NSEApiResponse,
    StreakInfo,
)


class TestNSEApiResponse:
    def test_construction(self):
        r = NSEApiResponse(
            category="FII/FPI",
            date="17-Mar-2026",
            buyValue="10000.00",
            sellValue="9000.00",
            netValue="1000.00",
        )
        assert r.category == "FII/FPI"
        assert r.buyValue == "10000.00"

    def test_extra_ignored(self):
        r = NSEApiResponse(
            category="DII",
            date="17-Mar-2026",
            buyValue="100",
            sellValue="200",
            netValue="-100",
            extraField="should be dropped",
        )
        assert not hasattr(r, "extraField")


class TestDailyFlow:
    def test_construction(self):
        f = DailyFlow(
            date=date(2026, 3, 17),
            category="FII",
            buy_value=10000.0,
            sell_value=9000.0,
            net_value=1000.0,
        )
        assert f.date == date(2026, 3, 17)
        assert f.net_value == 1000.0

    def test_negative_net(self):
        f = DailyFlow(
            date=date(2026, 3, 17),
            category="DII",
            buy_value=5000.0,
            sell_value=7000.0,
            net_value=-2000.0,
        )
        assert f.net_value == -2000.0


class TestDailyFlowPair:
    def _make_pair(self, fii_net=1000.0, dii_net=500.0):
        d = date(2026, 3, 17)
        fii = DailyFlow(date=d, category="FII", buy_value=10000, sell_value=9000, net_value=fii_net)
        dii = DailyFlow(date=d, category="DII", buy_value=8000, sell_value=7500, net_value=dii_net)
        return DailyFlowPair(date=d, fii=fii, dii=dii)

    def test_construction(self):
        p = self._make_pair()
        assert p.fii.category == "FII"
        assert p.dii.category == "DII"

    def test_fii_dii_net_diff_positive(self):
        p = self._make_pair(fii_net=1000, dii_net=500)
        assert p.fii_dii_net_diff == pytest.approx(500.0)

    def test_fii_dii_net_diff_negative(self):
        p = self._make_pair(fii_net=-2000, dii_net=3000)
        assert p.fii_dii_net_diff == pytest.approx(-5000.0)

    def test_fii_dii_net_diff_zero(self):
        p = self._make_pair(fii_net=500, dii_net=500)
        assert p.fii_dii_net_diff == pytest.approx(0.0)


class TestStreakInfo:
    def test_construction(self):
        s = StreakInfo(
            category="FII",
            direction="buying",
            days=5,
            cumulative_net=5000.0,
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 14),
        )
        assert s.days == 5
        assert s.direction == "buying"


# ---------------------------------------------------------------------------
# flowtracker.fund_models
# ---------------------------------------------------------------------------
from flowtracker.fund_models import (
    AnnualEPS,
    AnnualFinancials,
    LiveSnapshot,
    QuarterlyResult,
    ScreenerRatios,
    ValuationBand,
    ValuationSnapshot,
)


class TestQuarterlyResult:
    def test_all_fields(self):
        q = QuarterlyResult(
            symbol="SBIN",
            quarter_end="2025-12-31",
            revenue=5000.0,
            net_income=1200.0,
            eps=12.5,
        )
        assert q.symbol == "SBIN"
        assert q.revenue == 5000.0

    def test_all_optionals_none(self):
        q = QuarterlyResult(symbol="SBIN", quarter_end="2025-12-31")
        assert q.revenue is None
        assert q.eps is None
        assert q.tax_pct is None


class TestScreenerRatios:
    def test_all_fields(self):
        r = ScreenerRatios(
            symbol="INFY",
            fiscal_year_end="2025-03-31",
            debtor_days=60.0,
            roce_pct=25.0,
        )
        assert r.roce_pct == 25.0

    def test_all_optionals_none(self):
        r = ScreenerRatios(symbol="INFY", fiscal_year_end="2025-03-31")
        assert r.debtor_days is None
        assert r.working_capital_days is None


class TestValuationSnapshot:
    def test_minimal(self):
        v = ValuationSnapshot(symbol="RELIANCE", date="2026-03-17")
        assert v.price is None
        assert v.avg_volume is None

    def test_with_values(self):
        v = ValuationSnapshot(
            symbol="RELIANCE",
            date="2026-03-17",
            price=2500.0,
            pe_trailing=25.0,
            market_cap=1700000.0,
            avg_volume=5000000,
            shares_outstanding=670000000,
        )
        assert v.price == 2500.0
        assert v.avg_volume == 5000000


class TestLiveSnapshot:
    def test_minimal(self):
        l = LiveSnapshot(symbol="TCS")
        assert l.company_name is None
        assert l.price is None

    def test_with_values(self):
        l = LiveSnapshot(symbol="TCS", price=3800.0, pe_trailing=30.0, roe=0.45)
        assert l.roe == 0.45


class TestAnnualEPS:
    def test_required_fields(self):
        e = AnnualEPS(symbol="SBIN", fiscal_year_end="2025-03-31", eps=55.0)
        assert e.eps == 55.0

    def test_optionals_none(self):
        e = AnnualEPS(symbol="SBIN", fiscal_year_end="2025-03-31", eps=55.0)
        assert e.revenue is None
        assert e.net_income is None

    def test_all_fields(self):
        e = AnnualEPS(
            symbol="SBIN",
            fiscal_year_end="2025-03-31",
            eps=55.0,
            revenue=35000.0,
            net_income=6700.0,
        )
        assert e.revenue == 35000.0


class TestAnnualFinancials:
    """Test AnnualFinancials including all 9 computed properties."""

    def _make(self, **overrides):
        base = {"symbol": "SBIN", "fiscal_year_end": "2025-03-31"}
        base.update(overrides)
        return AnnualFinancials(**base)

    def test_minimal(self):
        f = self._make()
        assert f.revenue is None
        assert f.cfo is None

    def test_all_fields(self):
        f = self._make(
            revenue=35000, net_income=6700, equity_capital=900, reserves=40000,
            borrowings=15000, other_liabilities=20000, total_assets=100000,
            profit_before_tax=9000, interest=3000, cfo=8000, cfi=-4000,
            receivables=5000,
        )
        assert f.revenue == 35000

    # total_equity
    def test_total_equity(self):
        f = self._make(equity_capital=900, reserves=40000)
        assert f.total_equity == pytest.approx(40900.0)

    def test_total_equity_none_when_equity_capital_missing(self):
        f = self._make(reserves=40000)
        assert f.total_equity is None

    def test_total_equity_none_when_reserves_missing(self):
        f = self._make(equity_capital=900)
        assert f.total_equity is None

    # roce
    def test_roce(self):
        f = self._make(
            profit_before_tax=9000, interest=3000,
            total_assets=100000, other_liabilities=20000,
        )
        # EBIT = 9000 + 3000 = 12000; CE = 100000 - 20000 = 80000
        assert f.roce == pytest.approx(12000 / 80000)

    def test_roce_none_when_denom_zero(self):
        f = self._make(
            profit_before_tax=9000, interest=3000,
            total_assets=20000, other_liabilities=20000,
        )
        assert f.roce is None

    def test_roce_none_when_field_missing(self):
        f = self._make(profit_before_tax=9000)
        assert f.roce is None

    # roe
    def test_roe(self):
        f = self._make(net_income=6700, equity_capital=900, reserves=40000)
        assert f.roe == pytest.approx(6700 / 40900)

    def test_roe_none_when_equity_zero(self):
        f = self._make(net_income=6700, equity_capital=0, reserves=0)
        assert f.roe is None

    def test_roe_none_when_net_income_missing(self):
        f = self._make(equity_capital=900, reserves=40000)
        assert f.roe is None

    # debt_to_equity
    def test_debt_to_equity(self):
        f = self._make(borrowings=15000, equity_capital=900, reserves=40000)
        assert f.debt_to_equity == pytest.approx(15000 / 40900)

    def test_debt_to_equity_none_when_equity_zero(self):
        f = self._make(borrowings=15000, equity_capital=0, reserves=0)
        assert f.debt_to_equity is None

    def test_debt_to_equity_none_when_borrowings_missing(self):
        f = self._make(equity_capital=900, reserves=40000)
        assert f.debt_to_equity is None

    # interest_coverage
    def test_interest_coverage(self):
        f = self._make(profit_before_tax=9000, interest=3000)
        # EBIT = 12000 / 3000 = 4.0
        assert f.interest_coverage == pytest.approx(4.0)

    def test_interest_coverage_none_when_interest_zero(self):
        f = self._make(profit_before_tax=9000, interest=0)
        assert f.interest_coverage is None

    def test_interest_coverage_none_when_interest_missing(self):
        f = self._make(profit_before_tax=9000)
        assert f.interest_coverage is None

    # cfo_to_net_income
    def test_cfo_to_net_income(self):
        f = self._make(cfo=8000, net_income=6700)
        assert f.cfo_to_net_income == pytest.approx(8000 / 6700)

    def test_cfo_to_net_income_none_when_ni_zero(self):
        f = self._make(cfo=8000, net_income=0)
        assert f.cfo_to_net_income is None

    def test_cfo_to_net_income_none_when_cfo_missing(self):
        f = self._make(net_income=6700)
        assert f.cfo_to_net_income is None

    # fcf
    def test_fcf(self):
        f = self._make(cfo=8000, cfi=-4000)
        assert f.fcf == pytest.approx(4000.0)

    def test_fcf_none_when_cfo_missing(self):
        f = self._make(cfi=-4000)
        assert f.fcf is None

    def test_fcf_none_when_cfi_missing(self):
        f = self._make(cfo=8000)
        assert f.fcf is None

    # debtor_days
    def test_debtor_days(self):
        f = self._make(receivables=5000, revenue=35000)
        assert f.debtor_days == pytest.approx(5000 / (35000 / 365))

    def test_debtor_days_none_when_revenue_zero(self):
        f = self._make(receivables=5000, revenue=0)
        assert f.debtor_days is None

    def test_debtor_days_none_when_receivables_missing(self):
        f = self._make(revenue=35000)
        assert f.debtor_days is None

    # capex_pct_cfo
    def test_capex_pct_cfo(self):
        f = self._make(cfo=8000, cfi=-4000)
        assert f.capex_pct_cfo == pytest.approx(4000 / 8000)

    def test_capex_pct_cfo_none_when_cfo_zero(self):
        f = self._make(cfo=0, cfi=-4000)
        assert f.capex_pct_cfo is None

    def test_capex_pct_cfo_none_when_cfi_missing(self):
        f = self._make(cfo=8000)
        assert f.capex_pct_cfo is None


class TestValuationBand:
    def test_construction(self):
        b = ValuationBand(
            symbol="SBIN",
            metric="PE",
            min_val=5.0,
            max_val=25.0,
            median_val=12.0,
            current_val=15.0,
            percentile=0.65,
            num_observations=40,
            period_start="2016-03-31",
            period_end="2025-12-31",
        )
        assert b.percentile == 0.65
        assert b.num_observations == 40


# ---------------------------------------------------------------------------
# flowtracker.holding_models
# ---------------------------------------------------------------------------
from flowtracker.holding_models import (
    NSEShareholdingMaster,
    PromoterPledge,
    ShareholdingChange,
    ShareholdingRecord,
    ShareholdingSnapshot,
    WatchlistEntry,
)


class TestWatchlistEntry:
    def test_construction(self):
        w = WatchlistEntry(symbol="SBIN", company_name="State Bank of India", added_at="2026-03-17T10:00:00")
        assert w.company_name == "State Bank of India"

    def test_company_name_none(self):
        w = WatchlistEntry(symbol="SBIN", company_name=None, added_at="2026-03-17T10:00:00")
        assert w.company_name is None


class TestShareholdingRecord:
    def test_construction(self):
        r = ShareholdingRecord(
            symbol="RELIANCE", quarter_end="2025-12-31",
            category="Promoter", percentage=50.30,
        )
        assert r.percentage == 50.30


class TestShareholdingSnapshot:
    def _make_snapshot(self, categories=None):
        if categories is None:
            categories = {"Promoter": 50.0, "FII": 20.0, "DII": 15.0, "Public": 10.0, "MF": 5.0}
        records = [
            ShareholdingRecord(symbol="RELIANCE", quarter_end="2025-12-31", category=c, percentage=p)
            for c, p in categories.items()
        ]
        return ShareholdingSnapshot(symbol="RELIANCE", quarter_end="2025-12-31", records=records)

    def test_promoter_pct(self):
        s = self._make_snapshot()
        assert s.promoter_pct == 50.0

    def test_fii_pct(self):
        s = self._make_snapshot()
        assert s.fii_pct == 20.0

    def test_dii_pct(self):
        s = self._make_snapshot()
        assert s.dii_pct == 15.0

    def test_public_pct(self):
        s = self._make_snapshot()
        assert s.public_pct == 10.0

    def test_mf_pct(self):
        s = self._make_snapshot()
        assert s.mf_pct == 5.0

    def test_missing_category_returns_none(self):
        s = self._make_snapshot(categories={"Promoter": 50.0})
        assert s.fii_pct is None
        assert s.dii_pct is None
        assert s.public_pct is None
        assert s.mf_pct is None

    def test_empty_records(self):
        s = ShareholdingSnapshot(symbol="RELIANCE", quarter_end="2025-12-31", records=[])
        assert s.promoter_pct is None
        assert s.fii_pct is None


class TestShareholdingChange:
    def test_construction(self):
        c = ShareholdingChange(
            symbol="SBIN", category="FII",
            prev_quarter_end="2025-09-30", curr_quarter_end="2025-12-31",
            prev_pct=10.0, curr_pct=12.0, change_pct=2.0,
        )
        assert c.change_pct == 2.0


class TestNSEShareholdingMaster:
    def test_construction(self):
        m = NSEShareholdingMaster(
            symbol="SBIN", company_name="State Bank of India",
            quarter_end="2025-12-31", xbrl_url="https://example.com/xbrl",
        )
        assert m.xbrl_url.startswith("https://")

    def test_extra_ignored(self):
        m = NSEShareholdingMaster(
            symbol="SBIN", company_name="SBI",
            quarter_end="2025-12-31", xbrl_url="url",
            randomField="dropped",
        )
        assert not hasattr(m, "randomField")


class TestPromoterPledge:
    def test_construction(self):
        p = PromoterPledge(
            symbol="RELIANCE", quarter_end="2025-12-31",
            pledge_pct=1.5, encumbered_pct=2.0,
        )
        assert p.pledge_pct == 1.5


# ---------------------------------------------------------------------------
# flowtracker.mf_models
# ---------------------------------------------------------------------------
from flowtracker.mf_models import AMFIReportRow, MFAUMSummary, MFDailyFlow, MFMonthlyFlow


class TestAMFIReportRow:
    def test_all_fields(self):
        r = AMFIReportRow(
            category="Equity", sub_category="Large Cap Fund",
            num_schemes=35, funds_mobilized=5000.0,
            redemption=4000.0, net_flow=1000.0, aum=150000.0,
        )
        assert r.net_flow == 1000.0

    def test_optionals_none(self):
        r = AMFIReportRow(
            category="Equity", sub_category="Large Cap",
            num_schemes=None, funds_mobilized=None,
            redemption=None, net_flow=500.0, aum=None,
        )
        assert r.aum is None


class TestMFMonthlyFlow:
    def test_construction(self):
        f = MFMonthlyFlow(
            month="2026-02", category="Equity",
            sub_category="Large Cap", num_schemes=35,
            funds_mobilized=5000, redemption=4000,
            net_flow=1000, aum=150000,
        )
        assert f.month == "2026-02"


class TestMFAUMSummary:
    def test_construction(self):
        s = MFAUMSummary(
            month="2026-02", total_aum=500000, equity_aum=200000,
            debt_aum=150000, hybrid_aum=80000, other_aum=70000,
            equity_net_flow=5000, debt_net_flow=-2000, hybrid_net_flow=1000,
        )
        assert s.total_aum == 500000


class TestMFDailyFlow:
    def test_construction(self):
        f = MFDailyFlow(
            date="2026-03-19", category="Equity",
            gross_purchase=5000, gross_sale=4000, net_investment=1000,
        )
        assert f.net_investment == 1000


# ---------------------------------------------------------------------------
# flowtracker.bhavcopy_models
# ---------------------------------------------------------------------------
from flowtracker.bhavcopy_models import DailyStockData


class TestDailyStockData:
    def test_all_fields(self):
        d = DailyStockData(
            date="2026-03-17", symbol="SBIN",
            open=900.0, high=920.0, low=895.0, close=915.0,
            prev_close=905.0, volume=5000000, turnover=4575.0,
            delivery_qty=3000000, delivery_pct=60.0,
        )
        assert d.close == 915.0
        assert d.delivery_pct == 60.0

    def test_optionals_none(self):
        d = DailyStockData(
            date="2026-03-17", symbol="SBIN",
            open=900, high=920, low=895, close=915,
            prev_close=905, volume=5000000, turnover=4575,
        )
        assert d.delivery_qty is None
        assert d.delivery_pct is None


# ---------------------------------------------------------------------------
# flowtracker.commodity_models
# ---------------------------------------------------------------------------
from flowtracker.commodity_models import CommodityPrice, GoldCorrelation, GoldETFNav


class TestCommodityPrice:
    def test_construction(self):
        c = CommodityPrice(date="2026-03-17", symbol="GOLD", price=3050.0, unit="USD/oz")
        assert c.unit == "USD/oz"


class TestGoldETFNav:
    def test_construction(self):
        g = GoldETFNav(date="2026-03-17", scheme_code="140088", scheme_name="Gold BeES", nav=5500.0)
        assert g.nav == 5500.0

    def test_scheme_name_none(self):
        g = GoldETFNav(date="2026-03-17", scheme_code="140088", scheme_name=None, nav=5500.0)
        assert g.scheme_name is None


class TestGoldCorrelation:
    def test_construction(self):
        c = GoldCorrelation(
            date="2026-03-17", fii_net=-2000.0,
            gold_close=3050.0, gold_change_pct=0.5, gold_inr=92000.0,
        )
        assert c.gold_inr == 92000.0

    def test_gold_inr_none(self):
        c = GoldCorrelation(
            date="2026-03-17", fii_net=-2000.0,
            gold_close=3050.0, gold_change_pct=0.5, gold_inr=None,
        )
        assert c.gold_inr is None


# ---------------------------------------------------------------------------
# flowtracker.macro_models
# ---------------------------------------------------------------------------
from flowtracker.macro_models import MacroSnapshot as MacroMacroSnapshot


class TestMacroSnapshot:
    def test_minimal(self):
        m = MacroMacroSnapshot(date="2026-03-17")
        assert m.india_vix is None
        assert m.usd_inr is None

    def test_all_fields(self):
        m = MacroMacroSnapshot(
            date="2026-03-17", india_vix=14.5, usd_inr=83.5,
            brent_crude=80.0, gsec_10y=7.1,
        )
        assert m.india_vix == 14.5


# ---------------------------------------------------------------------------
# flowtracker.deals_models
# ---------------------------------------------------------------------------
from flowtracker.deals_models import BulkBlockDeal


class TestBulkBlockDeal:
    def test_all_required(self):
        d = BulkBlockDeal(
            date="2026-03-17", deal_type="BULK", symbol="SBIN", quantity=500000,
        )
        assert d.quantity == 500000
        assert d.client_name is None

    def test_all_fields(self):
        d = BulkBlockDeal(
            date="2026-03-17", deal_type="BLOCK", symbol="SBIN",
            client_name="HDFC MF", buy_sell="BUY", quantity=500000, price=920.0,
        )
        assert d.client_name == "HDFC MF"


# ---------------------------------------------------------------------------
# flowtracker.insider_models
# ---------------------------------------------------------------------------
from flowtracker.insider_models import InsiderTransaction


class TestInsiderTransaction:
    def test_all_required(self):
        t = InsiderTransaction(
            date="2026-03-17", symbol="SBIN", person_name="John Doe",
            person_category="Promoters", transaction_type="Buy",
            quantity=10000, value=9200000.0,
        )
        assert t.mode is None

    def test_all_fields(self):
        t = InsiderTransaction(
            date="2026-03-17", symbol="SBIN", person_name="John Doe",
            person_category="Promoters", transaction_type="Buy",
            quantity=10000, value=9200000.0,
            mode="Market Purchase", holding_before_pct=50.0, holding_after_pct=50.1,
        )
        assert t.holding_after_pct == 50.1


# ---------------------------------------------------------------------------
# flowtracker.estimates_models
# ---------------------------------------------------------------------------
from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise


class TestConsensusEstimate:
    def test_minimal(self):
        c = ConsensusEstimate(symbol="SBIN", date="2026-03-17")
        assert c.target_mean is None
        assert c.earnings_growth is None

    def test_all_fields(self):
        c = ConsensusEstimate(
            symbol="SBIN", date="2026-03-17",
            target_mean=1050.0, target_median=1030.0,
            target_high=1200.0, target_low=850.0,
            num_analysts=25, recommendation="buy",
            recommendation_score=2.0, forward_pe=10.0,
            forward_eps=95.0, eps_current_year=90.0,
            eps_next_year=100.0, earnings_growth=0.15,
            current_price=920.0,
        )
        assert c.num_analysts == 25


class TestEarningsSurprise:
    def test_minimal(self):
        e = EarningsSurprise(symbol="SBIN", quarter_end="2025-12-31")
        assert e.eps_actual is None

    def test_all_fields(self):
        e = EarningsSurprise(
            symbol="SBIN", quarter_end="2025-12-31",
            eps_actual=14.5, eps_estimate=13.0, surprise_pct=11.5,
        )
        assert e.surprise_pct == 11.5


# ---------------------------------------------------------------------------
# flowtracker.mfportfolio_models
# ---------------------------------------------------------------------------
from flowtracker.mfportfolio_models import MFHoldingChange, MFSchemeHolding


class TestMFSchemeHolding:
    def test_construction(self):
        h = MFSchemeHolding(
            month="2026-02", amc="SBI", scheme_name="SBI Blue Chip",
            isin="INE123456789", stock_name="RELIANCE",
            quantity=50000, market_value_lakhs=1250.0, pct_of_nav=5.5,
        )
        assert h.pct_of_nav == 5.5


class TestMFHoldingChange:
    def test_construction(self):
        c = MFHoldingChange(
            stock_name="RELIANCE", isin="INE123456789",
            amc="SBI", scheme_name="SBI Blue Chip",
            prev_month="2026-01", curr_month="2026-02",
            prev_qty=40000, curr_qty=50000, qty_change=10000,
            prev_value=1000.0, curr_value=1250.0, change_type="INCREASE",
        )
        assert c.change_type == "INCREASE"


# ---------------------------------------------------------------------------
# flowtracker.filing_models
# ---------------------------------------------------------------------------
from flowtracker.filing_models import CorporateFiling


class TestCorporateFiling:
    def test_all_required(self):
        f = CorporateFiling(
            symbol="SBIN", bse_scrip_code="500112",
            filing_date="2026-03-17", category="Result",
            subcategory="Earnings Call Transcript",
            headline="Q3 FY26 Earnings Call",
            attachment_name="transcript.pdf", pdf_flag=0,
        )
        assert f.file_size is None
        assert f.local_path is None

    def test_all_fields(self):
        f = CorporateFiling(
            symbol="SBIN", bse_scrip_code="500112",
            filing_date="2026-03-17", category="Result",
            subcategory="Earnings Call Transcript",
            headline="Q3 FY26 Earnings Call",
            attachment_name="transcript.pdf", pdf_flag=1,
            file_size=2048, news_id="abc123", local_path="/tmp/transcript.pdf",
        )
        assert f.pdf_flag == 1
        assert f.file_size == 2048


# ---------------------------------------------------------------------------
# flowtracker.fmp_models
# ---------------------------------------------------------------------------
from flowtracker.fmp_models import (
    FMPAnalystGrade,
    FMPDcfValue,
    FMPFinancialGrowth,
    FMPKeyMetrics,
    FMPPriceTarget,
    FMPTechnicalIndicator,
)


class TestFMPDcfValue:
    def test_construction(self):
        d = FMPDcfValue(symbol="SBIN", date="2026-03-17", dcf=1100.0, stock_price=920.0)
        assert d.dcf == 1100.0

    def test_optionals_none(self):
        d = FMPDcfValue(symbol="SBIN", date="2026-03-17")
        assert d.dcf is None
        assert d.stock_price is None


class TestFMPTechnicalIndicator:
    def test_construction(self):
        t = FMPTechnicalIndicator(
            symbol="SBIN", date="2026-03-17", indicator="rsi", value=65.0,
        )
        assert t.indicator == "rsi"

    def test_value_none(self):
        t = FMPTechnicalIndicator(symbol="SBIN", date="2026-03-17", indicator="macd")
        assert t.value is None


class TestFMPKeyMetrics:
    def test_minimal(self):
        m = FMPKeyMetrics(symbol="SBIN", date="2026-03-17")
        assert m.pe_ratio is None
        assert m.roe is None
        assert m.equity_multiplier is None

    def test_with_values(self):
        m = FMPKeyMetrics(
            symbol="SBIN", date="2026-03-17",
            pe_ratio=10.0, roe=0.15, roic=0.12,
            net_profit_margin_dupont=0.2, asset_turnover=0.05,
            equity_multiplier=15.0,
        )
        assert m.equity_multiplier == 15.0


class TestFMPFinancialGrowth:
    def test_minimal(self):
        g = FMPFinancialGrowth(symbol="SBIN", date="2026-03-17")
        assert g.revenue_growth is None
        assert g.revenue_growth_10y is None

    def test_with_values(self):
        g = FMPFinancialGrowth(
            symbol="SBIN", date="2026-03-17",
            revenue_growth=0.12, net_income_growth=0.18,
            eps_growth=0.15, revenue_growth_5y=0.10,
        )
        assert g.eps_growth == 0.15


class TestFMPAnalystGrade:
    def test_construction(self):
        g = FMPAnalystGrade(
            symbol="SBIN", date="2026-03-17",
            grading_company="Morgan Stanley",
            previous_grade="Equal-Weight", new_grade="Overweight",
        )
        assert g.new_grade == "Overweight"

    def test_optionals_none(self):
        g = FMPAnalystGrade(
            symbol="SBIN", date="2026-03-17", grading_company="GS",
        )
        assert g.previous_grade is None
        assert g.new_grade is None


class TestFMPPriceTarget:
    def test_construction(self):
        p = FMPPriceTarget(
            symbol="SBIN", published_date="2026-03-17",
            analyst_name="Analyst A", analyst_company="GS",
            price_target=1100.0, price_when_posted=920.0,
        )
        assert p.price_target == 1100.0

    def test_optionals_none(self):
        p = FMPPriceTarget(symbol="SBIN", published_date="2026-03-17")
        assert p.analyst_name is None
        assert p.price_target is None


# ---------------------------------------------------------------------------
# flowtracker.portfolio_models
# ---------------------------------------------------------------------------
from flowtracker.portfolio_models import PortfolioHolding


class TestPortfolioHolding:
    def test_required_fields(self):
        h = PortfolioHolding(symbol="SBIN", quantity=50, avg_cost=920.0)
        assert h.buy_date is None
        assert h.notes is None

    def test_all_fields(self):
        h = PortfolioHolding(
            symbol="SBIN", quantity=50, avg_cost=920.0,
            buy_date="2026-01-15", notes="PSU bank bet", added_at="2026-01-15T10:00:00",
        )
        assert h.notes == "PSU bank bet"


# ---------------------------------------------------------------------------
# flowtracker.alert_models
# ---------------------------------------------------------------------------
from flowtracker.alert_models import Alert, TriggeredAlert


class TestAlert:
    def test_defaults(self):
        a = Alert(symbol="SBIN", condition_type="price_below", threshold=750.0)
        assert a.id is None
        assert a.active is True
        assert a.last_triggered is None

    def test_all_fields(self):
        a = Alert(
            id=42, symbol="SBIN", condition_type="pe_above", threshold=15.0,
            active=False, last_triggered="2026-03-17", created_at="2026-01-01",
            notes="Valuation alert",
        )
        assert a.id == 42
        assert a.active is False


class TestTriggeredAlert:
    def test_defaults(self):
        a = Alert(symbol="SBIN", condition_type="price_below", threshold=750.0)
        t = TriggeredAlert(alert=a)
        assert t.current_value is None
        assert t.message == ""

    def test_with_values(self):
        a = Alert(symbol="SBIN", condition_type="price_below", threshold=750.0)
        t = TriggeredAlert(alert=a, current_value=720.0, message="Price dropped below 750")
        assert t.current_value == 720.0
        assert "750" in t.message


# ---------------------------------------------------------------------------
# flowtracker.scan_models
# ---------------------------------------------------------------------------
from flowtracker.scan_models import BatchFetchResult, IndexConstituent, ScanSummary


class TestIndexConstituent:
    def test_construction(self):
        c = IndexConstituent(
            symbol="SBIN", index_name="NIFTY 50",
            company_name="State Bank of India", industry="Banks",
        )
        assert c.index_name == "NIFTY 50"

    def test_optionals_none(self):
        c = IndexConstituent(
            symbol="SBIN", index_name="NIFTY 50",
            company_name=None, industry=None,
        )
        assert c.company_name is None


class TestBatchFetchResult:
    def test_construction(self):
        r = BatchFetchResult(total=250, fetched=240, skipped=5, failed=5, errors=["ERR: timeout"])
        assert r.failed == 5
        assert len(r.errors) == 1

    def test_empty_errors(self):
        r = BatchFetchResult(total=50, fetched=50, skipped=0, failed=0, errors=[])
        assert r.errors == []


class TestScanSummary:
    def test_construction(self):
        s = ScanSummary(
            total_symbols=250, symbols_with_data=240,
            latest_quarter="2025-12-31", missing_symbols=["ABC", "DEF"],
        )
        assert s.symbols_with_data == 240

    def test_latest_quarter_none(self):
        s = ScanSummary(
            total_symbols=250, symbols_with_data=0,
            latest_quarter=None, missing_symbols=[],
        )
        assert s.latest_quarter is None


# ---------------------------------------------------------------------------
# flowtracker.screener_models
# ---------------------------------------------------------------------------
from flowtracker.screener_models import FactorScore, StockScore


class TestFactorScore:
    def test_construction(self):
        f = FactorScore(factor="ownership", score=85.0, raw_value=12.5, detail="FII increased 2%")
        assert f.score == 85.0

    def test_raw_value_none(self):
        f = FactorScore(factor="quality", score=70.0, raw_value=None)
        assert f.raw_value is None
        assert f.detail == ""


class TestStockScore:
    def test_construction(self):
        factors = [FactorScore(factor="ownership", score=85.0, raw_value=12.5)]
        s = StockScore(
            symbol="SBIN", company_name="State Bank of India",
            industry="Banks", composite_score=82.0, factors=factors, rank=1,
        )
        assert s.rank == 1
        assert len(s.factors) == 1

    def test_defaults(self):
        s = StockScore(symbol="SBIN", composite_score=75.0, factors=[])
        assert s.company_name is None
        assert s.rank == 0


# ---------------------------------------------------------------------------
# flowtracker.research.briefing models
# ---------------------------------------------------------------------------
from flowtracker.research.briefing import (
    AgentCost,
    BriefingEnvelope,
    ToolEvidence,
    VerificationResult,
)


class TestToolEvidence:
    def test_construction(self):
        e = ToolEvidence(tool="get_price_history", args={"symbol": "SBIN"}, result_summary="OK")
        assert e.tool == "get_price_history"

    def test_defaults(self):
        e = ToolEvidence(tool="get_price_history")
        assert e.args == {}
        assert e.result_summary == ""
        assert e.result_hash == ""
        assert e.is_error is False

    def test_extra_ignored(self):
        e = ToolEvidence(tool="test", unknown_field="dropped")
        assert not hasattr(e, "unknown_field")


class TestAgentCost:
    def test_defaults(self):
        c = AgentCost()
        assert c.input_tokens == 0
        assert c.total_cost_usd == 0.0
        assert c.model == ""

    def test_with_values(self):
        c = AgentCost(input_tokens=5000, output_tokens=2000, total_cost_usd=0.05, model="claude-sonnet-4-20250514")
        assert c.total_cost_usd == 0.05

    def test_extra_ignored(self):
        c = AgentCost(extra_field="dropped")
        assert not hasattr(c, "extra_field")


class TestBriefingEnvelope:
    def test_construction(self):
        env = BriefingEnvelope(agent="business", symbol="SBIN", report="# Business\nGreat bank.")
        assert env.agent == "business"
        assert env.report.startswith("# Business")

    def test_defaults(self):
        env = BriefingEnvelope(agent="business", symbol="SBIN")
        assert env.report == ""
        assert env.briefing == {}
        assert env.evidence == []
        assert env.cost.total_cost_usd == 0.0
        assert env.generated_at  # should be auto-populated

    def test_extra_ignored(self):
        env = BriefingEnvelope(agent="business", symbol="SBIN", unknown="dropped")
        assert not hasattr(env, "unknown")

    def test_with_evidence(self):
        ev = ToolEvidence(tool="test_tool")
        env = BriefingEnvelope(agent="business", symbol="SBIN", evidence=[ev])
        assert len(env.evidence) == 1


class TestVerificationResult:
    def test_defaults(self):
        v = VerificationResult(agent_verified="business", symbol="SBIN")
        assert v.verdict == "pass"
        assert v.spot_checks_performed == 0
        assert v.issues == []
        assert v.corrections == []

    def test_with_issues(self):
        v = VerificationResult(
            agent_verified="financials", symbol="SBIN",
            verdict="pass_with_notes", spot_checks_performed=5,
            issues=[{"field": "revenue", "expected": 35000, "actual": 34500}],
            corrections=["Revenue was off by 1.4%"],
            overall_data_quality="good",
        )
        assert v.verdict == "pass_with_notes"
        assert len(v.issues) == 1

    def test_extra_ignored(self):
        v = VerificationResult(agent_verified="business", symbol="SBIN", extra="dropped")
        assert not hasattr(v, "extra")


# ---------------------------------------------------------------------------
# flowtracker.research.models
# ---------------------------------------------------------------------------
from flowtracker.research.models import (
    DeliveryRecord,
    FIIDIIStreak,
)
from flowtracker.research.models import MacroSnapshot as ResearchMacroSnapshot


class TestResearchMacroSnapshot:
    def test_defaults(self):
        m = ResearchMacroSnapshot()
        assert m.vix is None
        assert m.vix_date is None

    def test_all_fields(self):
        m = ResearchMacroSnapshot(
            vix=14.5, usd_inr=83.5, brent_crude=80.0, gsec_10y=7.1, vix_date="2026-03-17",
        )
        assert m.vix == 14.5


class TestFIIDIIStreak:
    def test_defaults(self):
        s = FIIDIIStreak()
        assert s.fii_streak_days == 0
        assert s.fii_streak_direction == ""
        assert s.dii_streak_total == 0

    def test_with_values(self):
        s = FIIDIIStreak(
            fii_streak_days=10, fii_streak_direction="selling", fii_streak_total=-15000,
            dii_streak_days=8, dii_streak_direction="buying", dii_streak_total=12000,
        )
        assert s.fii_streak_days == 10


class TestDeliveryRecord:
    def test_minimal(self):
        d = DeliveryRecord(date="2026-03-17")
        assert d.close is None
        assert d.delivery_pct is None

    def test_all_fields(self):
        d = DeliveryRecord(
            date="2026-03-17", close=915.0,
            volume=5000000, delivery_qty=3000000, delivery_pct=60.0,
        )
        assert d.delivery_pct == 60.0
