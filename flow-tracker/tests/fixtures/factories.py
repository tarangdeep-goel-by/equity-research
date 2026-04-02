"""Model factories and fixture data for tests.

Produces realistic Indian market data for 2 symbols: SBIN (banking) and INFY (IT).
All monetary values in crores unless noted otherwise.
"""

from __future__ import annotations

from datetime import date, timedelta

from flowtracker.models import DailyFlow
from flowtracker.fund_models import (
    AnnualFinancials,
    QuarterlyResult,
    ScreenerRatios,
    ValuationSnapshot,
)
from flowtracker.holding_models import (
    PromoterPledge,
    ShareholdingRecord,
)
from flowtracker.mf_models import MFAUMSummary, MFDailyFlow, MFMonthlyFlow
from flowtracker.mfportfolio_models import MFSchemeHolding
from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.commodity_models import CommodityPrice, GoldETFNav
from flowtracker.macro_models import MacroSnapshot
from flowtracker.deals_models import BulkBlockDeal
from flowtracker.insider_models import InsiderTransaction
from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.filing_models import CorporateFiling
from flowtracker.fmp_models import (
    FMPAnalystGrade,
    FMPDcfValue,
    FMPFinancialGrowth,
    FMPKeyMetrics,
    FMPPriceTarget,
    FMPTechnicalIndicator,
)
from flowtracker.portfolio_models import PortfolioHolding
from flowtracker.alert_models import Alert
from flowtracker.scan_models import IndexConstituent


# ---------------------------------------------------------------------------
# Individual model factories
# ---------------------------------------------------------------------------

def make_daily_flow(
    dt: str = "2026-03-28",
    category: str = "FII",
    buy: float = 12000.0,
    sell: float = 13500.0,
    net: float | None = None,
) -> DailyFlow:
    if net is None:
        net = buy - sell
    return DailyFlow(
        date=date.fromisoformat(dt),
        category=category,
        buy_value=buy,
        sell_value=sell,
        net_value=net,
    )


def make_daily_flows(n: int = 5, start: str = "2026-03-24") -> list[DailyFlow]:
    """N days of FII+DII flows with alternating sentiment."""
    flows = []
    base = date.fromisoformat(start)
    for i in range(n):
        d = base + timedelta(days=i)
        ds = d.isoformat()
        # FII: alternating buy/sell
        fii_net = (-1500.0 + i * 200) if i % 2 == 0 else (800.0 - i * 100)
        flows.append(make_daily_flow(dt=ds, category="FII", buy=12000, sell=12000 - fii_net, net=fii_net))
        # DII: counter-flow
        dii_net = -fii_net * 0.6
        flows.append(make_daily_flow(dt=ds, category="DII", buy=8000, sell=8000 - dii_net, net=dii_net))
    return flows


def make_quarterly_result(
    symbol: str = "SBIN",
    quarter_end: str = "2025-12-31",
    revenue: float = 52000.0,
    net_income: float = 18500.0,
) -> QuarterlyResult:
    return QuarterlyResult(
        symbol=symbol,
        quarter_end=quarter_end,
        revenue=revenue,
        gross_profit=revenue * 0.55,
        operating_income=revenue * 0.42,
        net_income=net_income,
        ebitda=revenue * 0.48,
        eps=net_income / 893,  # SBIN shares ~893 Cr
        eps_diluted=net_income / 893,
        operating_margin=42.0,
        net_margin=net_income / revenue * 100,
        expenses=revenue * 0.58,
        other_income=revenue * 0.05,
        depreciation=revenue * 0.03,
        interest=revenue * 0.02,
        profit_before_tax=net_income * 1.3,
        tax_pct=23.0,
    )


def make_quarterly_results(symbol: str = "SBIN", n: int = 8) -> list[QuarterlyResult]:
    """N quarters with growing revenue trajectory."""
    results = []
    quarters = ["03-31", "06-30", "09-30", "12-31"]
    base_rev = 45000.0 if symbol == "SBIN" else 42000.0
    for i in range(n):
        q_idx = (n - 1 - i) % 4
        year = 2026 - (n - 1 - i) // 4
        qe = f"{year}-{quarters[q_idx]}"
        rev = base_rev + i * 1500
        ni = rev * (0.35 if symbol == "SBIN" else 0.22)
        results.append(make_quarterly_result(symbol=symbol, quarter_end=qe, revenue=rev, net_income=ni))
    return results


def make_annual_financials(symbol: str = "SBIN", n: int = 5) -> list[AnnualFinancials]:
    """N years of annual financials."""
    records = []
    base_rev = 170000.0 if symbol == "SBIN" else 160000.0
    for i in range(n):
        fy = f"{2026 - n + i}-03-31"
        rev = base_rev + i * 8000
        ni = rev * (0.30 if symbol == "SBIN" else 0.20)
        records.append(AnnualFinancials(
            symbol=symbol,
            fiscal_year_end=fy,
            revenue=rev,
            employee_cost=rev * 0.12,
            raw_material_cost=None,
            power_and_fuel=None,
            other_mfr_exp=None,
            selling_and_admin=rev * 0.08,
            other_expenses_detail=rev * 0.15,
            total_expenses=rev * 0.65,
            operating_profit=rev * 0.35,
            other_income=rev * 0.04,
            depreciation=rev * 0.03,
            interest=rev * 0.02,
            profit_before_tax=ni * 1.3,
            tax=ni * 0.3,
            net_income=ni,
            eps=ni / 893,
            dividend_amount=ni * 0.2,
            equity_capital=893.0,
            reserves=ni * 5,
            borrowings=rev * 0.3,
            other_liabilities=rev * 0.2,
            total_assets=rev * 1.5,
            net_block=rev * 0.15,
            cwip=rev * 0.02,
            investments=rev * 0.4,
            other_assets=rev * 0.3,
            receivables=rev * 0.08,
            inventory=None,  # Banks don't have inventory
            cash_and_bank=rev * 0.1,
            num_shares=893.0,
            cfo=ni * 1.2,
            cfi=-ni * 0.5,
            cff=-ni * 0.4,
            net_cash_flow=ni * 0.3,
            price=750.0 + i * 50,
        ))
    return records


def make_screener_ratios(symbol: str = "SBIN", n: int = 5) -> list[ScreenerRatios]:
    records = []
    for i in range(n):
        fy = f"{2022 + i}-03-31"
        records.append(ScreenerRatios(
            symbol=symbol,
            fiscal_year_end=fy,
            debtor_days=25.0 + i,
            inventory_days=None,
            days_payable=30.0 + i,
            cash_conversion_cycle=-5.0 + i,
            working_capital_days=15.0 + i,
            roce_pct=18.0 + i * 0.5,
        ))
    return records


def make_valuation_snapshot(
    symbol: str = "SBIN",
    dt: str = "2026-03-28",
    price: float = 820.0,
    pe: float = 9.5,
) -> ValuationSnapshot:
    return ValuationSnapshot(
        symbol=symbol,
        date=dt,
        price=price,
        market_cap=price * 893,
        enterprise_value=price * 893 * 1.1,
        fifty_two_week_high=price * 1.2,
        fifty_two_week_low=price * 0.7,
        beta=1.1,
        pe_trailing=pe,
        pe_forward=pe * 0.85,
        pb_ratio=1.8,
        ev_ebitda=7.5,
        ev_revenue=2.1,
        ps_ratio=1.5,
        peg_ratio=0.6,
        gross_margin=55.0,
        operating_margin=42.0,
        net_margin=35.0,
        roe=18.5,
        roa=1.2,
        revenue_growth=12.0,
        earnings_growth=15.0,
        earnings_quarterly_growth=18.0,
        dividend_yield=1.5,
        debt_to_equity=0.4,
        current_ratio=1.2,
        total_cash=50000.0,
        total_debt=200000.0,
        book_value_per_share=450.0,
        free_cash_flow=25000.0,
        operating_cash_flow=35000.0,
        revenue_per_share=200.0,
        cash_per_share=56.0,
        avg_volume=15000000,
        float_shares=700000000,
        shares_outstanding=893000000,
    )


def make_valuation_snapshots(symbol: str = "SBIN", n: int = 30) -> list[ValuationSnapshot]:
    base = date.fromisoformat("2026-03-01")
    base_price = 800.0 if symbol == "SBIN" else 1800.0
    base_pe = 9.0 if symbol == "SBIN" else 28.0
    snapshots = []
    for i in range(n):
        d = base + timedelta(days=i)
        price = base_price + (i - 15) * 5  # slight trend
        pe = base_pe + (i - 15) * 0.1
        snapshots.append(make_valuation_snapshot(symbol=symbol, dt=d.isoformat(), price=price, pe=pe))
    return snapshots


def make_shareholding(symbol: str = "SBIN", n: int = 4) -> list[ShareholdingRecord]:
    """N quarters of shareholding, categories sum to ~100%."""
    records = []
    quarters = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    base = {"Promoter": 57.5, "FII": 11.2, "DII": 8.5, "MF": 7.8, "Insurance": 5.2, "Public": 9.8}
    for i in range(min(n, len(quarters))):
        for cat, pct in base.items():
            # Slight drift each quarter
            drift = (i - 1) * 0.3 if cat == "MF" else -(i - 1) * 0.1
            records.append(ShareholdingRecord(
                symbol=symbol,
                quarter_end=quarters[i],
                category=cat,
                percentage=round(pct + drift, 2),
            ))
    return records


def make_promoter_pledges(symbol: str = "SBIN", n: int = 4) -> list[PromoterPledge]:
    quarters = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    return [
        PromoterPledge(
            symbol=symbol,
            quarter_end=quarters[i],
            pledge_pct=2.5 - i * 0.5,
            encumbered_pct=3.0 - i * 0.5,
        )
        for i in range(min(n, len(quarters)))
    ]


def make_index_constituents() -> list[IndexConstituent]:
    return [
        IndexConstituent(symbol="SBIN", index_name="NIFTY 50", company_name="State Bank of India", industry="Banks"),
        IndexConstituent(symbol="INFY", index_name="NIFTY 50", company_name="Infosys Ltd", industry="IT - Software"),
        IndexConstituent(symbol="RELIANCE", index_name="NIFTY 50", company_name="Reliance Industries", industry="Refineries"),
    ]


def make_daily_stock_data(symbol: str = "SBIN", n: int = 30) -> list[DailyStockData]:
    base = date.fromisoformat("2026-03-01")
    base_price = 800.0 if symbol == "SBIN" else 1800.0
    records = []
    for i in range(n):
        d = base + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        price = base_price + (i - 15) * 3
        records.append(DailyStockData(
            date=d.isoformat(),
            symbol=symbol,
            open=price - 5,
            high=price + 10,
            low=price - 12,
            close=price,
            prev_close=price - 3,
            volume=15000000 + i * 100000,
            turnover=price * 150,
            delivery_qty=9000000 + i * 50000,
            delivery_pct=60.0 + (i % 10) - 5,
        ))
    return records


def make_commodity_prices(n: int = 10) -> list[CommodityPrice]:
    base = date.fromisoformat("2026-03-20")
    return [
        CommodityPrice(
            date=(base + timedelta(days=i)).isoformat(),
            symbol="GOLD",
            price=2050.0 + i * 5,
            unit="USD/oz",
        )
        for i in range(n)
    ]


def make_gold_etf_navs(n: int = 10) -> list[GoldETFNav]:
    base = date.fromisoformat("2026-03-20")
    return [
        GoldETFNav(
            date=(base + timedelta(days=i)).isoformat(),
            scheme_code="140088",
            scheme_name="Nippon India ETF Gold BeES",
            nav=58.5 + i * 0.2,
        )
        for i in range(n)
    ]


def make_macro_snapshots(n: int = 10) -> list[MacroSnapshot]:
    base = date.fromisoformat("2026-03-20")
    return [
        MacroSnapshot(
            date=(base + timedelta(days=i)).isoformat(),
            india_vix=14.5 + i * 0.3,
            usd_inr=83.5 + i * 0.1,
            brent_crude=82.0 + i * 0.5,
            gsec_10y=7.15 + i * 0.02,
        )
        for i in range(n)
    ]


def make_deals() -> list[BulkBlockDeal]:
    return [
        BulkBlockDeal(date="2026-03-28", deal_type="BLOCK", symbol="SBIN", client_name="Goldman Sachs", buy_sell="BUY", quantity=5000000, price=820.0),
        BulkBlockDeal(date="2026-03-28", deal_type="BULK", symbol="INFY", client_name="Axis MF", buy_sell="SELL", quantity=2000000, price=1850.0),
    ]


def make_insider_transactions(symbol: str = "SBIN") -> list[InsiderTransaction]:
    return [
        InsiderTransaction(date="2026-03-20", symbol=symbol, person_name="Rajesh Kumar", person_category="Promoters", transaction_type="Buy", quantity=100000, value=82000000.0, mode="Market Purchase", holding_before_pct=57.5, holding_after_pct=57.6),
        InsiderTransaction(date="2026-03-15", symbol=symbol, person_name="Amit Shah", person_category="Director", transaction_type="Buy", quantity=50000, value=40000000.0, mode="Market Purchase", holding_before_pct=0.01, holding_after_pct=0.02),
        InsiderTransaction(date="2026-03-10", symbol=symbol, person_name="Priya Singh", person_category="KMP", transaction_type="Sell", quantity=10000, value=8200000.0, mode="Market Purchase", holding_before_pct=0.005, holding_after_pct=0.004),
    ]


def make_consensus_estimate(symbol: str = "SBIN") -> ConsensusEstimate:
    return ConsensusEstimate(
        symbol=symbol,
        date="2026-03-28",
        target_mean=950.0,
        target_median=940.0,
        target_high=1100.0,
        target_low=780.0,
        num_analysts=28,
        recommendation="buy",
        recommendation_score=2.1,
        forward_pe=8.2,
        forward_eps=100.0,
        eps_current_year=92.0,
        eps_next_year=105.0,
        earnings_growth=15.0,
        current_price=820.0,
    )


def make_earnings_surprises(symbol: str = "SBIN", n: int = 4) -> list[EarningsSurprise]:
    quarters = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    surprises = [8.5, 12.3, -2.1, 15.0]
    return [
        EarningsSurprise(
            symbol=symbol,
            quarter_end=quarters[i],
            eps_actual=20.0 + i * 2,
            eps_estimate=20.0 + i * 2 - surprises[i] * 0.2,
            surprise_pct=surprises[i],
        )
        for i in range(min(n, len(quarters)))
    ]


def make_mf_monthly_flows(n: int = 3) -> list[MFMonthlyFlow]:
    months = ["2026-01", "2026-02", "2026-03"]
    flows = []
    for i in range(min(n, len(months))):
        flows.append(MFMonthlyFlow(month=months[i], category="Equity", sub_category="Large Cap Fund", num_schemes=35, funds_mobilized=15000.0, redemption=12000.0, net_flow=3000.0, aum=250000.0 + i * 5000))
        flows.append(MFMonthlyFlow(month=months[i], category="Equity", sub_category="Multi Cap Fund", num_schemes=25, funds_mobilized=8000.0, redemption=6000.0, net_flow=2000.0, aum=180000.0 + i * 3000))
    return flows


def make_mf_aum_summary(n: int = 3) -> list[MFAUMSummary]:
    months = ["2026-01", "2026-02", "2026-03"]
    return [
        MFAUMSummary(
            month=months[i],
            total_aum=4500000.0 + i * 50000,
            equity_aum=2500000.0 + i * 30000,
            debt_aum=1200000.0 + i * 10000,
            hybrid_aum=500000.0 + i * 5000,
            other_aum=300000.0 + i * 5000,
            equity_net_flow=25000.0 + i * 2000,
            debt_net_flow=-5000.0 + i * 1000,
            hybrid_net_flow=3000.0 + i * 500,
        )
        for i in range(min(n, len(months)))
    ]


def make_mf_daily_flows(n: int = 5) -> list[MFDailyFlow]:
    base = date.fromisoformat("2026-03-24")
    flows = []
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        flows.append(MFDailyFlow(date=d, category="Equity", gross_purchase=5000.0, gross_sale=4200.0, net_investment=800.0))
        flows.append(MFDailyFlow(date=d, category="Debt", gross_purchase=3000.0, gross_sale=3500.0, net_investment=-500.0))
    return flows


def make_mf_scheme_holdings() -> list[MFSchemeHolding]:
    return [
        MFSchemeHolding(month="2026-02", amc="SBI", scheme_name="SBI Bluechip Fund", isin="INE062A01020", stock_name="State Bank of India", quantity=5000000, market_value_cr=410.0, pct_of_nav=5.2),
        MFSchemeHolding(month="2026-02", amc="ICICI", scheme_name="ICICI Pru Bluechip Fund", isin="INE062A01020", stock_name="State Bank of India", quantity=3000000, market_value_cr=246.0, pct_of_nav=3.8),
        MFSchemeHolding(month="2026-02", amc="SBI", scheme_name="SBI Focused Equity Fund", isin="INE009A01021", stock_name="Infosys Ltd", quantity=2000000, market_value_cr=370.0, pct_of_nav=4.5),
        # Previous month for change detection
        MFSchemeHolding(month="2026-01", amc="SBI", scheme_name="SBI Bluechip Fund", isin="INE062A01020", stock_name="State Bank of India", quantity=4500000, market_value_cr=360.0, pct_of_nav=4.8),
    ]


def make_filings(symbol: str = "SBIN") -> list[CorporateFiling]:
    return [
        CorporateFiling(symbol=symbol, bse_scrip_code="500112", filing_date="2026-03-15", category="Result", subcategory="Financial Results", headline="Q3 FY26 Results", attachment_name="Q3_results.pdf", pdf_flag=0, file_size=250000, news_id="20260315001"),
        CorporateFiling(symbol=symbol, bse_scrip_code="500112", filing_date="2026-03-10", category="Company Update", subcategory="Investor Presentation", headline="Investor Day 2026", attachment_name="investor_deck.pdf", pdf_flag=0, file_size=500000, news_id="20260310001"),
    ]


def make_fmp_dcf(symbol: str = "SBIN") -> list[FMPDcfValue]:
    return [
        FMPDcfValue(symbol=symbol, date="2026-03-28", dcf=950.0, stock_price=820.0),
        FMPDcfValue(symbol=symbol, date="2025-03-28", dcf=850.0, stock_price=720.0),
    ]


def make_fmp_technicals(symbol: str = "SBIN") -> list[FMPTechnicalIndicator]:
    return [
        FMPTechnicalIndicator(symbol=symbol, date="2026-03-28", indicator="rsi", value=55.0),
        FMPTechnicalIndicator(symbol=symbol, date="2026-03-28", indicator="sma_50", value=810.0),
        FMPTechnicalIndicator(symbol=symbol, date="2026-03-28", indicator="sma_200", value=780.0),
        FMPTechnicalIndicator(symbol=symbol, date="2026-03-28", indicator="macd", value=12.5),
        FMPTechnicalIndicator(symbol=symbol, date="2026-03-28", indicator="adx", value=22.0),
    ]


def make_fmp_key_metrics(symbol: str = "SBIN") -> list[FMPKeyMetrics]:
    return [FMPKeyMetrics(
        symbol=symbol,
        date="2026-03-28",
        revenue_per_share=200.0,
        net_income_per_share=70.0,
        operating_cash_flow_per_share=85.0,
        free_cash_flow_per_share=60.0,
        cash_per_share=56.0,
        book_value_per_share=450.0,
        tangible_book_value_per_share=420.0,
        shareholders_equity_per_share=440.0,
        interest_debt_per_share=220.0,
        market_cap=732000.0,
        enterprise_value=805000.0,
        pe_ratio=9.5,
        price_to_sales_ratio=1.5,
        pb_ratio=1.8,
        ev_to_sales=2.1,
        ev_to_ebitda=7.5,
        ev_to_operating_cash_flow=9.5,
        ev_to_free_cash_flow=13.4,
        earnings_yield=10.5,
        free_cash_flow_yield=7.3,
        debt_to_equity=0.4,
        debt_to_assets=0.25,
        dividend_yield=1.5,
        payout_ratio=20.0,
        roe=18.5,
        roa=1.2,
        roic=14.0,
        net_profit_margin_dupont=35.0,
        asset_turnover=0.05,
        equity_multiplier=10.5,
    )]


def make_fmp_growth(symbol: str = "SBIN") -> list[FMPFinancialGrowth]:
    return [FMPFinancialGrowth(
        symbol=symbol,
        date="2026-03-28",
        revenue_growth=12.0,
        gross_profit_growth=14.0,
        ebitda_growth=15.0,
        operating_income_growth=16.0,
        net_income_growth=18.0,
        eps_growth=17.5,
        eps_diluted_growth=17.5,
        dividends_per_share_growth=10.0,
        operating_cash_flow_growth=20.0,
        free_cash_flow_growth=22.0,
        asset_growth=8.0,
        debt_growth=5.0,
        book_value_per_share_growth=12.0,
        revenue_growth_3y=35.0,
        revenue_growth_5y=65.0,
        revenue_growth_10y=None,
        net_income_growth_3y=50.0,
        net_income_growth_5y=80.0,
    )]


def make_fmp_grades(symbol: str = "SBIN") -> list[FMPAnalystGrade]:
    return [
        FMPAnalystGrade(symbol=symbol, date="2026-03-15", grading_company="Morgan Stanley", previous_grade="Equal-Weight", new_grade="Overweight"),
        FMPAnalystGrade(symbol=symbol, date="2026-02-20", grading_company="Goldman Sachs", previous_grade="Buy", new_grade="Conviction Buy"),
    ]


def make_fmp_targets(symbol: str = "SBIN") -> list[FMPPriceTarget]:
    return [
        FMPPriceTarget(symbol=symbol, published_date="2026-03-15", analyst_name="Rahul Jain", analyst_company="Morgan Stanley", price_target=1000.0, price_when_posted=820.0),
        FMPPriceTarget(symbol=symbol, published_date="2026-02-20", analyst_name="Kiran Mehta", analyst_company="Goldman Sachs", price_target=950.0, price_when_posted=790.0),
    ]


def make_portfolio_holdings() -> list[PortfolioHolding]:
    return [
        PortfolioHolding(symbol="SBIN", quantity=100, avg_cost=750.0, buy_date="2025-06-15", notes="Core holding"),
        PortfolioHolding(symbol="INFY", quantity=50, avg_cost=1650.0, buy_date="2025-09-20", notes="IT exposure"),
    ]


def make_alerts() -> list[Alert]:
    return [
        Alert(symbol="SBIN", condition_type="price_below", threshold=700.0, notes="Buy more below 700"),
        Alert(symbol="SBIN", condition_type="pe_above", threshold=15.0, notes="Expensive above 15x"),
        Alert(symbol="SBIN", condition_type="pledge_above", threshold=10.0, notes="Pledge risk"),
        Alert(symbol="INFY", condition_type="rsi_below", threshold=30.0, notes="Oversold signal"),
    ]


# ---------------------------------------------------------------------------
# populate_all — inserts coherent fixture data across all key tables
# ---------------------------------------------------------------------------

def populate_all(store) -> None:
    """Populate a FlowStore with realistic fixture data for SBIN and INFY."""
    # Flows
    store.upsert_flows(make_daily_flows(n=5))
    store.upsert_mf_flows(make_mf_monthly_flows())
    for s in make_mf_aum_summary():
        store.upsert_mf_aum(s)
    store.upsert_mf_daily_flows(make_mf_daily_flows())

    # Index constituents
    store.upsert_index_constituents(make_index_constituents())

    # Shareholding + pledges (both symbols)
    for sym in ("SBIN", "INFY"):
        store.upsert_shareholding(make_shareholding(sym))
        store.upsert_promoter_pledges(make_promoter_pledges(sym))

    # Fundamentals
    for sym in ("SBIN", "INFY"):
        store.upsert_quarterly_results(make_quarterly_results(sym))
        store.upsert_annual_financials(make_annual_financials(sym))
        store.upsert_screener_ratios(make_screener_ratios(sym))

    # Valuation snapshots
    for sym in ("SBIN", "INFY"):
        store.upsert_valuation_snapshots(make_valuation_snapshots(sym))

    # Daily stock data
    for sym in ("SBIN", "INFY"):
        store.upsert_daily_stock_data(make_daily_stock_data(sym))

    # Commodities + macro
    store.upsert_commodity_prices(make_commodity_prices())
    store.upsert_etf_navs(make_gold_etf_navs())
    store.upsert_macro_snapshots(make_macro_snapshots())

    # Deals + insider
    store.upsert_deals(make_deals())
    for sym in ("SBIN", "INFY"):
        store.upsert_insider_transactions(make_insider_transactions(sym))

    # Estimates
    for sym in ("SBIN", "INFY"):
        store.upsert_consensus_estimates([make_consensus_estimate(sym)])
        store.upsert_earnings_surprises(make_earnings_surprises(sym))

    # MF scheme holdings
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    # Filings
    for sym in ("SBIN", "INFY"):
        store.upsert_filings(make_filings(sym))

    # FMP data
    for sym in ("SBIN", "INFY"):
        store.upsert_fmp_dcf(make_fmp_dcf(sym))
        store.upsert_fmp_technical_indicators(make_fmp_technicals(sym))
        store.upsert_fmp_key_metrics(make_fmp_key_metrics(sym))
        store.upsert_fmp_financial_growth(make_fmp_growth(sym))
        store.upsert_fmp_analyst_grades(make_fmp_grades(sym))
        store.upsert_fmp_price_targets(make_fmp_targets(sym))

    # Portfolio + alerts
    for h in make_portfolio_holdings():
        store.upsert_portfolio_holding(h)
    for a in make_alerts():
        store.upsert_alert(a)

    # Watchlist (subset)
    store.add_to_watchlist("SBIN", "State Bank of India")
    store.add_to_watchlist("INFY", "Infosys Ltd")
