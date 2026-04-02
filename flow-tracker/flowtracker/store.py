"""SQLite persistence for FII/DII daily flow data."""

from __future__ import annotations

import os
import sqlite3
import statistics
from datetime import date
from pathlib import Path

from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
from flowtracker.mf_models import MFMonthlyFlow, MFAUMSummary, MFDailyFlow
from flowtracker.holding_models import WatchlistEntry, ShareholdingRecord, ShareholdingChange, PromoterPledge
from flowtracker.commodity_models import CommodityPrice, GoldETFNav, GoldCorrelation
from flowtracker.scan_models import IndexConstituent, ScanSummary
from flowtracker.fund_models import QuarterlyResult, ValuationSnapshot, ValuationBand, AnnualFinancials, ScreenerRatios
from flowtracker.macro_models import MacroSnapshot
from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.deals_models import BulkBlockDeal
from flowtracker.insider_models import InsiderTransaction
from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.mfportfolio_models import MFSchemeHolding, MFHoldingChange
from flowtracker.filing_models import CorporateFiling
from flowtracker.fmp_models import (
    FMPDcfValue, FMPTechnicalIndicator, FMPKeyMetrics,
    FMPFinancialGrowth, FMPAnalystGrade, FMPPriceTarget,
)
from flowtracker.portfolio_models import PortfolioHolding
from flowtracker.alert_models import Alert

import logging

_val_logger = logging.getLogger("flowtracker.validation")

# Ranges designed to catch unit errors (rupees stored as crores).
# A ₹500 Cr company in rupees = 5,000,000,000 — must exceed upper bound.
# Lower bounds catch reverse errors or nonsense values.
_VALIDATION_RULES: dict[str, dict[str, tuple[float, float]]] = {
    "annual_financials": {
        "revenue": (1, 1_500_000),          # ₹1 Cr to ₹15L Cr (Reliance ~9L Cr)
        "net_income": (-50_000, 500_000),   # losses capped, profits ~5L Cr max
        "total_assets": (1, 50_000_000),    # SBI ~60L Cr, but most < 50L
        "num_shares": (100_000, 50_000_000_000),  # at least 1L shares
        "eps": (-500, 5_000),               # per-share rupees
    },
    "valuation_snapshot": {
        "market_cap": (50, 25_000_000),     # ₹50 Cr to ₹25L Cr
        "enterprise_value": (-500_000, 30_000_000),
        "total_cash": (0.01, 10_000_000),   # at least 1L, max 10L Cr
        "total_debt": (0.01, 30_000_000),
        "free_cash_flow": (-200_000, 200_000),
        "operating_cash_flow": (-200_000, 300_000),
        "price": (1, 200_000),              # ₹1 to ₹2L per share
        "pe_trailing": (-500, 2000),
    },
    "quarterly_results": {
        "revenue": (0.1, 400_000),          # quarterly — max ~4L Cr
        "net_income": (-30_000, 200_000),
    },
    "insider_transactions": {
        "value": (0, 10_000),               # max ~₹10K Cr single trade
    },
    "mf_scheme_holdings": {
        "market_value_cr": (0.01, 50_000),  # ₹1L to ₹50K Cr per scheme holding
        "pct_of_nav": (0.001, 25),          # max 25% NAV in one stock
    },
    "fmp_key_metrics": {
        "market_cap": (50, 25_000_000),
        "enterprise_value": (-500_000, 30_000_000),
    },
    "quarterly_balance_sheet": {
        "total_assets": (1, 50_000_000),
        "total_debt": (0.01, 30_000_000),
    },
    "quarterly_cash_flow": {
        "operating_cf": (-200_000, 300_000),
        "free_cf": (-200_000, 200_000),
    },
}


def _validate_row(table: str, row: dict) -> list[str]:
    """Return list of validation warnings. Empty = valid."""
    errors = []
    rules = _VALIDATION_RULES.get(table, {})
    for field, (lo, hi) in rules.items():
        val = row.get(field)
        if val is not None and (val < lo or val > hi):
            errors.append(f"{field}={val} outside [{lo}, {hi}]")
    return errors


_DEFAULT_DB_DIR = Path.home() / ".local" / "share" / "flowtracker"
_DEFAULT_DB_NAME = "flows.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS daily_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    buy_value REAL NOT NULL,
    sell_value REAL NOT NULL,
    net_value REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, category)
);

CREATE TABLE IF NOT EXISTS mf_monthly_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT NOT NULL,
    num_schemes INTEGER,
    funds_mobilized REAL,
    redemption REAL,
    net_flow REAL NOT NULL,
    aum REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month, category, sub_category)
);

CREATE TABLE IF NOT EXISTS mf_aum_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    total_aum REAL NOT NULL,
    equity_aum REAL NOT NULL,
    debt_aum REAL NOT NULL,
    hybrid_aum REAL NOT NULL,
    other_aum REAL NOT NULL,
    equity_net_flow REAL NOT NULL,
    debt_net_flow REAL NOT NULL,
    hybrid_net_flow REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    company_name TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shareholding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    category TEXT NOT NULL,
    percentage REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end, category)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    index_name TEXT NOT NULL,
    company_name TEXT,
    industry TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, index_name)
);

CREATE TABLE IF NOT EXISTS promoter_pledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    pledge_pct REAL NOT NULL DEFAULT 0,
    encumbered_pct REAL NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS commodity_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    unit TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol)
);

CREATE TABLE IF NOT EXISTS gold_etf_nav (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    scheme_code TEXT NOT NULL,
    scheme_name TEXT,
    nav REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, scheme_code)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    symbol TEXT,
    key_info TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quarterly_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    net_income REAL,
    ebitda REAL,
    eps REAL,
    eps_diluted REAL,
    operating_margin REAL,
    net_margin REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS valuation_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    price REAL,
    market_cap REAL,
    enterprise_value REAL,
    fifty_two_week_high REAL,
    fifty_two_week_low REAL,
    beta REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    ev_revenue REAL,
    ps_ratio REAL,
    peg_ratio REAL,
    gross_margin REAL,
    operating_margin REAL,
    net_margin REAL,
    roe REAL,
    roa REAL,
    revenue_growth REAL,
    earnings_growth REAL,
    earnings_quarterly_growth REAL,
    dividend_yield REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    total_cash REAL,
    total_debt REAL,
    book_value_per_share REAL,
    free_cash_flow REAL,
    operating_cash_flow REAL,
    revenue_per_share REAL,
    cash_per_share REAL,
    avg_volume INTEGER,
    float_shares INTEGER,
    shares_outstanding INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS annual_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    fiscal_year_end TEXT NOT NULL,
    revenue REAL,
    employee_cost REAL,
    other_income REAL,
    depreciation REAL,
    interest REAL,
    profit_before_tax REAL,
    tax REAL,
    net_income REAL,
    eps REAL,
    dividend_amount REAL,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_assets REAL,
    net_block REAL,
    cwip REAL,
    investments REAL,
    other_assets REAL,
    receivables REAL,
    inventory REAL,
    cash_and_bank REAL,
    num_shares REAL,
    cfo REAL,
    cfi REAL,
    cff REAL,
    net_cash_flow REAL,
    price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, fiscal_year_end)
);

CREATE TABLE IF NOT EXISTS mf_daily_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    gross_purchase REAL NOT NULL,
    gross_sale REAL NOT NULL,
    net_investment REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, category)
);

CREATE TABLE IF NOT EXISTS macro_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    india_vix REAL,
    usd_inr REAL,
    brent_crude REAL,
    gsec_10y REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);

CREATE TABLE IF NOT EXISTS daily_stock_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    prev_close REAL NOT NULL,
    volume INTEGER NOT NULL,
    turnover REAL NOT NULL,
    delivery_qty INTEGER,
    delivery_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_daily_stock_symbol ON daily_stock_data(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_stock_date ON daily_stock_data(date);

CREATE TABLE IF NOT EXISTS bulk_block_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    deal_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    client_name TEXT,
    buy_sell TEXT,
    quantity INTEGER NOT NULL,
    price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, deal_type, symbol, client_name)
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    person_name TEXT NOT NULL,
    person_category TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    value REAL NOT NULL,
    mode TEXT,
    holding_before_pct REAL,
    holding_after_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol, person_name, transaction_type, quantity)
);

CREATE TABLE IF NOT EXISTS consensus_estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    target_mean REAL,
    target_median REAL,
    target_high REAL,
    target_low REAL,
    num_analysts INTEGER,
    recommendation TEXT,
    recommendation_score REAL,
    forward_pe REAL,
    forward_eps REAL,
    eps_current_year REAL,
    eps_next_year REAL,
    earnings_growth REAL,
    current_price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS earnings_surprises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    eps_actual REAL,
    eps_estimate REAL,
    surprise_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    amc TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    isin TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    market_value_cr REAL NOT NULL,
    pct_of_nav REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month, amc, scheme_name, isin)
);

CREATE INDEX IF NOT EXISTS idx_mf_holdings_isin ON mf_scheme_holdings(isin);
CREATE INDEX IF NOT EXISTS idx_mf_holdings_month ON mf_scheme_holdings(month);

CREATE TABLE IF NOT EXISTS corporate_filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    bse_scrip_code TEXT,
    filing_date TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    headline TEXT NOT NULL,
    attachment_name TEXT NOT NULL,
    pdf_flag INTEGER DEFAULT 0,
    file_size INTEGER,
    news_id TEXT,
    local_path TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(news_id)
);

CREATE INDEX IF NOT EXISTS idx_filings_symbol ON corporate_filings(symbol);
CREATE INDEX IF NOT EXISTS idx_filings_date ON corporate_filings(filing_date);

CREATE TABLE IF NOT EXISTS screener_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    fiscal_year_end TEXT NOT NULL,
    debtor_days REAL,
    inventory_days REAL,
    days_payable REAL,
    cash_conversion_cycle REAL,
    working_capital_days REAL,
    roce_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, fiscal_year_end)
);

CREATE TABLE IF NOT EXISTS screener_ids (
    symbol TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS screener_charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    chart_type TEXT NOT NULL,
    metric TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, chart_type, metric, date)
);

CREATE TABLE IF NOT EXISTS peer_comparison (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    peer_symbol TEXT,
    peer_name TEXT NOT NULL,
    cmp REAL,
    pe REAL,
    market_cap REAL,
    div_yield REAL,
    np_qtr REAL,
    qtr_profit_var REAL,
    sales_qtr REAL,
    qtr_sales_var REAL,
    roce REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, peer_name)
);

CREATE TABLE IF NOT EXISTS shareholder_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    classification TEXT NOT NULL,
    holder_name TEXT NOT NULL,
    quarter TEXT NOT NULL,
    percentage REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, classification, holder_name, quarter)
);

CREATE TABLE IF NOT EXISTS financial_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    section TEXT NOT NULL,
    parent_item TEXT NOT NULL,
    sub_item TEXT NOT NULL,
    period TEXT NOT NULL,
    value REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, section, parent_item, sub_item, period)
);

CREATE TABLE IF NOT EXISTS company_profiles (
    symbol TEXT PRIMARY KEY,
    about_text TEXT,
    key_points_json TEXT,
    screener_url TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    period TEXT NOT NULL,
    url TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, doc_type, period)
);

CREATE TABLE IF NOT EXISTS fmp_dcf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    dcf REAL,
    stock_price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS fmp_technical_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    indicator TEXT NOT NULL,
    value REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date, indicator)
);

CREATE TABLE IF NOT EXISTS fmp_key_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    revenue_per_share REAL,
    net_income_per_share REAL,
    operating_cash_flow_per_share REAL,
    free_cash_flow_per_share REAL,
    cash_per_share REAL,
    book_value_per_share REAL,
    tangible_book_value_per_share REAL,
    shareholders_equity_per_share REAL,
    interest_debt_per_share REAL,
    market_cap REAL,
    enterprise_value REAL,
    pe_ratio REAL,
    price_to_sales_ratio REAL,
    pb_ratio REAL,
    ev_to_sales REAL,
    ev_to_ebitda REAL,
    ev_to_operating_cash_flow REAL,
    ev_to_free_cash_flow REAL,
    earnings_yield REAL,
    free_cash_flow_yield REAL,
    debt_to_equity REAL,
    debt_to_assets REAL,
    dividend_yield REAL,
    payout_ratio REAL,
    roe REAL,
    roa REAL,
    roic REAL,
    net_profit_margin_dupont REAL,
    asset_turnover REAL,
    equity_multiplier REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS fmp_financial_growth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    revenue_growth REAL,
    gross_profit_growth REAL,
    ebitda_growth REAL,
    operating_income_growth REAL,
    net_income_growth REAL,
    eps_growth REAL,
    eps_diluted_growth REAL,
    dividends_per_share_growth REAL,
    operating_cash_flow_growth REAL,
    free_cash_flow_growth REAL,
    asset_growth REAL,
    debt_growth REAL,
    book_value_per_share_growth REAL,
    revenue_growth_3y REAL,
    revenue_growth_5y REAL,
    revenue_growth_10y REAL,
    net_income_growth_3y REAL,
    net_income_growth_5y REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS fmp_analyst_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    grading_company TEXT NOT NULL,
    previous_grade TEXT,
    new_grade TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date, grading_company)
);

CREATE TABLE IF NOT EXISTS fmp_price_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    published_date TEXT NOT NULL,
    analyst_name TEXT,
    analyst_company TEXT,
    price_target REAL,
    price_when_posted REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, published_date, analyst_company)
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_cost REAL NOT NULL,
    buy_date TEXT,
    notes TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    condition_type TEXT NOT NULL,
    threshold REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    last_triggered TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
    current_value REAL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS sector_benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_symbol TEXT NOT NULL,
    metric TEXT NOT NULL,
    subject_value REAL,
    peer_count INTEGER,
    sector_median REAL,
    sector_p25 REAL,
    sector_p75 REAL,
    sector_min REAL,
    sector_max REAL,
    percentile REAL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_symbol, metric)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    action_type TEXT NOT NULL,
    ratio_text TEXT,
    multiplier REAL,
    dividend_amount REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, ex_date, action_type, source)
);

CREATE TABLE IF NOT EXISTS estimate_revisions (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    period TEXT NOT NULL,
    eps_current REAL,
    eps_7d_ago REAL,
    eps_30d_ago REAL,
    eps_60d_ago REAL,
    eps_90d_ago REAL,
    revisions_up_7d INTEGER,
    revisions_up_30d INTEGER,
    revisions_down_7d INTEGER,
    revisions_down_30d INTEGER,
    momentum_score REAL,
    momentum_signal TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date, period)
);

CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    total_assets REAL,
    total_debt REAL,
    long_term_debt REAL,
    stockholders_equity REAL,
    cash_and_equivalents REAL,
    net_debt REAL,
    investments REAL,
    net_ppe REAL,
    shares_outstanding REAL,
    total_liabilities REAL,
    minority_interest REAL,
    source TEXT DEFAULT 'yfinance',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    operating_cash_flow REAL,
    free_cash_flow REAL,
    capital_expenditure REAL,
    investing_cash_flow REAL,
    financing_cash_flow REAL,
    change_in_working_capital REAL,
    depreciation REAL,
    dividends_paid REAL,
    net_income REAL,
    source TEXT DEFAULT 'yfinance',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS analytical_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    computed_date TEXT NOT NULL,

    -- Composite Score
    composite_score REAL,
    composite_factors TEXT,

    -- Piotroski F-Score
    f_score INTEGER,
    f_score_max INTEGER,
    f_score_signal TEXT,
    f_score_criteria TEXT,

    -- Beneish M-Score
    m_score REAL,
    m_score_signal TEXT,
    m_score_variables TEXT,

    -- Earnings Quality
    eq_signal TEXT,
    eq_cfo_pat_3y REAL,
    eq_cfo_pat_5y REAL,
    eq_accruals_3y REAL,

    -- Reverse DCF
    rdcf_implied_growth REAL,
    rdcf_implied_margin REAL,
    rdcf_model TEXT,
    rdcf_base_cf REAL,
    rdcf_market_cap REAL,
    rdcf_3y_cagr REAL,
    rdcf_5y_cagr REAL,
    rdcf_assessment TEXT,
    rdcf_sensitivity TEXT,

    -- Capex Cycle
    capex_phase TEXT,
    capex_cwip_to_nb REAL,
    capex_intensity REAL,
    capex_asset_turnover REAL,

    -- Common Size P&L (latest year)
    cs_biggest_cost TEXT,
    cs_fastest_growing_cost TEXT,
    cs_raw_material_pct REAL,
    cs_employee_pct REAL,
    cs_depreciation_pct REAL,
    cs_interest_pct REAL,
    cs_net_margin_pct REAL,
    cs_ebit_pct REAL,
    cs_denominator TEXT,

    -- BFSI Metrics (latest year)
    bfsi_nim_pct REAL,
    bfsi_roa_pct REAL,
    bfsi_cost_to_income_pct REAL,
    bfsi_equity_multiplier REAL,
    bfsi_book_value_per_share REAL,
    bfsi_pb_ratio REAL,

    -- Price Performance
    perf_1m_stock REAL,
    perf_3m_stock REAL,
    perf_6m_stock REAL,
    perf_1y_stock REAL,
    perf_1m_excess REAL,
    perf_3m_excess REAL,
    perf_6m_excess REAL,
    perf_1y_excess REAL,
    perf_outperformer INTEGER,
    perf_sector_index TEXT,

    -- Metadata
    industry TEXT,
    is_bfsi INTEGER,
    is_insurance INTEGER,
    errors TEXT,
    compute_duration_ms INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(symbol, computed_date)
);

CREATE INDEX IF NOT EXISTS idx_analytical_snapshot_symbol ON analytical_snapshot(symbol);
CREATE INDEX IF NOT EXISTS idx_analytical_snapshot_date ON analytical_snapshot(computed_date);
"""


class FlowStore:
    """SQLite store for daily FII/DII flows."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("FLOWTRACKER_DB")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_valuation_snapshot()
        self._migrate_quarterly_and_annual()

    def _migrate_quarterly_and_annual(self) -> None:
        """Add new columns to quarterly_results and annual_financials if they don't exist."""
        existing_qr = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(quarterly_results)").fetchall()
        }
        new_qr_cols = [
            ("expenses", "REAL"), ("other_income", "REAL"), ("depreciation", "REAL"),
            ("interest", "REAL"), ("profit_before_tax", "REAL"), ("tax_pct", "REAL"),
        ]
        for col_name, col_type in new_qr_cols:
            if col_name not in existing_qr:
                self._conn.execute(f"ALTER TABLE quarterly_results ADD COLUMN {col_name} {col_type}")

        existing_af = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(annual_financials)").fetchall()
        }
        new_af_cols = [
            ("raw_material_cost", "REAL"), ("power_and_fuel", "REAL"),
            ("other_mfr_exp", "REAL"), ("selling_and_admin", "REAL"),
            ("other_expenses_detail", "REAL"), ("total_expenses", "REAL"),
            ("operating_profit", "REAL"),
        ]
        for col_name, col_type in new_af_cols:
            if col_name not in existing_af:
                self._conn.execute(f"ALTER TABLE annual_financials ADD COLUMN {col_name} {col_type}")

        self._conn.commit()

    def _migrate_valuation_snapshot(self) -> None:
        """Add new columns to valuation_snapshot if they don't exist."""
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(valuation_snapshot)").fetchall()
        }
        new_cols = [
            ("fifty_two_week_high", "REAL"), ("fifty_two_week_low", "REAL"),
            ("beta", "REAL"), ("ev_revenue", "REAL"), ("ps_ratio", "REAL"),
            ("peg_ratio", "REAL"), ("gross_margin", "REAL"),
            ("operating_margin", "REAL"), ("net_margin", "REAL"),
            ("revenue_growth", "REAL"), ("earnings_growth", "REAL"),
            ("earnings_quarterly_growth", "REAL"), ("total_cash", "REAL"),
            ("total_debt", "REAL"), ("book_value_per_share", "REAL"),
            ("operating_cash_flow", "REAL"), ("revenue_per_share", "REAL"),
            ("cash_per_share", "REAL"), ("avg_volume", "INTEGER"),
            ("float_shares", "INTEGER"), ("shares_outstanding", "INTEGER"),
        ]
        for col, typ in new_cols:
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE valuation_snapshot ADD COLUMN {col} {typ}"
                )

    def upsert_flows(self, flows: list[DailyFlow]) -> int:
        """Insert or replace flows. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            existing = self._conn.execute(
                "SELECT net_value FROM daily_flows WHERE date = ? AND category = ?",
                (f.date.isoformat(), f.category),
            ).fetchone()
            if existing and existing["net_value"] != f.net_value:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("daily_flows", f.category, f.date.isoformat(),
                     "net_value", str(existing["net_value"]), str(f.net_value)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO daily_flows (date, category, buy_value, sell_value, net_value) "
                "VALUES (?, ?, ?, ?, ?)",
                (f.date.isoformat(), f.category, f.buy_value, f.sell_value, f.net_value),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_latest(self) -> DailyFlowPair | None:
        """Get the most recent day's FII + DII pair."""
        row = self._conn.execute(
            "SELECT DISTINCT date FROM daily_flows ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None

        latest_date = row["date"]
        rows = self._conn.execute(
            "SELECT * FROM daily_flows WHERE date = ? ORDER BY category",
            (latest_date,),
        ).fetchall()

        return _rows_to_pair(rows)

    def get_flows(self, days: int) -> list[DailyFlow]:
        """Get flows for the last N calendar days, ordered by date DESC."""
        rows = self._conn.execute(
            "SELECT * FROM daily_flows "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC, category",
            (f"-{days}",),
        ).fetchall()

        return [_row_to_flow(r) for r in rows]

    def get_streak(self, category: str) -> StreakInfo | None:
        """Get current buying/selling streak for a category.

        Counts consecutive days with same-sign net_value, starting from most recent.
        """
        rows = self._conn.execute(
            "SELECT date, net_value FROM daily_flows "
            "WHERE category = ? ORDER BY date DESC",
            (category,),
        ).fetchall()

        if not rows:
            return None

        first_net = rows[0]["net_value"]
        if first_net == 0:
            return None

        is_buying = first_net > 0
        direction = "buying" if is_buying else "selling"
        cumulative = 0.0
        streak_days = 0
        end_date = date.fromisoformat(rows[0]["date"])
        start_date = end_date

        for row in rows:
            net = row["net_value"]
            if (is_buying and net > 0) or (not is_buying and net < 0):
                streak_days += 1
                cumulative += net
                start_date = date.fromisoformat(row["date"])
            else:
                break

        return StreakInfo(
            category=category,
            direction=direction,
            days=streak_days,
            cumulative_net=cumulative,
            start_date=start_date,
            end_date=end_date,
        )

    # -- Phase 3: Mutual Fund flows & AUM --

    def upsert_mf_flows(self, flows: list[MFMonthlyFlow]) -> int:
        """Insert or replace MF monthly flow records."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_monthly_flows "
                "(month, category, sub_category, num_schemes, funds_mobilized, redemption, net_flow, aum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f.month, f.category, f.sub_category, f.num_schemes, f.funds_mobilized, f.redemption, f.net_flow, f.aum),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_mf_aum(self, summary: MFAUMSummary) -> int:
        """Insert or replace MF AUM summary for a month."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO mf_aum_summary "
            "(month, total_aum, equity_aum, debt_aum, hybrid_aum, other_aum, "
            "equity_net_flow, debt_net_flow, hybrid_net_flow) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (summary.month, summary.total_aum, summary.equity_aum, summary.debt_aum,
             summary.hybrid_aum, summary.other_aum, summary.equity_net_flow,
             summary.debt_net_flow, summary.hybrid_net_flow),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_mf_flows(self, months: int = 12, category: str | None = None) -> list[MFMonthlyFlow]:
        """Get MF flows for the last N months, optionally filtered by category."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM mf_monthly_flows "
                "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') AND category = ? "
                "ORDER BY month DESC, sub_category",
                (f"-{months}", category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM mf_monthly_flows "
                "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') "
                "ORDER BY month DESC, category, sub_category",
                (f"-{months}",),
            ).fetchall()
        return [MFMonthlyFlow(
            month=r["month"], category=r["category"], sub_category=r["sub_category"],
            num_schemes=r["num_schemes"], funds_mobilized=r["funds_mobilized"],
            redemption=r["redemption"], net_flow=r["net_flow"], aum=r["aum"],
        ) for r in rows]

    def get_mf_aum_trend(self, months: int = 12) -> list[MFAUMSummary]:
        """Get MF AUM summaries for the last N months."""
        rows = self._conn.execute(
            "SELECT * FROM mf_aum_summary "
            "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') "
            "ORDER BY month DESC",
            (f"-{months}",),
        ).fetchall()
        return [MFAUMSummary(
            month=r["month"], total_aum=r["total_aum"], equity_aum=r["equity_aum"],
            debt_aum=r["debt_aum"], hybrid_aum=r["hybrid_aum"], other_aum=r["other_aum"],
            equity_net_flow=r["equity_net_flow"], debt_net_flow=r["debt_net_flow"],
            hybrid_net_flow=r["hybrid_net_flow"],
        ) for r in rows]

    def get_mf_latest_aum(self) -> MFAUMSummary | None:
        """Get the most recent MF AUM summary."""
        row = self._conn.execute(
            "SELECT * FROM mf_aum_summary ORDER BY month DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MFAUMSummary(
            month=row["month"], total_aum=row["total_aum"], equity_aum=row["equity_aum"],
            debt_aum=row["debt_aum"], hybrid_aum=row["hybrid_aum"], other_aum=row["other_aum"],
            equity_net_flow=row["equity_net_flow"], debt_net_flow=row["debt_net_flow"],
            hybrid_net_flow=row["hybrid_net_flow"],
        )

    # -- MF Daily Flows (SEBI) --

    def upsert_mf_daily_flows(self, flows: list[MFDailyFlow]) -> int:
        """Insert or replace daily MF flow records from SEBI."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_daily_flows "
                "(date, category, gross_purchase, gross_sale, net_investment) "
                "VALUES (?, ?, ?, ?, ?)",
                (f.date, f.category, f.gross_purchase, f.gross_sale, f.net_investment),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_daily_latest(self) -> list[MFDailyFlow]:
        """Get the most recent day's MF flows (both equity and debt)."""
        rows = self._conn.execute(
            "SELECT * FROM mf_daily_flows "
            "WHERE date = (SELECT MAX(date) FROM mf_daily_flows) "
            "ORDER BY category"
        ).fetchall()
        return [MFDailyFlow(
            date=r["date"], category=r["category"],
            gross_purchase=r["gross_purchase"], gross_sale=r["gross_sale"],
            net_investment=r["net_investment"],
        ) for r in rows]

    def get_mf_daily_summary(self, days: int = 30) -> list[dict]:
        """Get daily MF equity net investment for trend display."""
        rows = self._conn.execute(
            "SELECT date, "
            "SUM(CASE WHEN category = 'Equity' THEN net_investment ELSE 0 END) as equity_net, "
            "SUM(CASE WHEN category = 'Debt' THEN net_investment ELSE 0 END) as debt_net "
            "FROM mf_daily_flows "
            "WHERE date >= date('now', ? || ' days') "
            "GROUP BY date ORDER BY date DESC",
            (f"-{days}",),
        ).fetchall()
        return [{"date": r["date"], "equity_net": r["equity_net"], "debt_net": r["debt_net"]} for r in rows]

    # -- Phase 4: Watchlist & Shareholding --

    def add_to_watchlist(self, symbol: str, company_name: str | None = None) -> None:
        """Add a symbol to the watchlist."""
        self._conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, company_name) VALUES (?, ?)",
            (symbol.upper(), company_name),
        )
        self._conn.commit()

    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove a symbol from the watchlist."""
        self._conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        self._conn.commit()

    def get_watchlist(self) -> list[WatchlistEntry]:
        """Get all watchlist entries."""
        rows = self._conn.execute("SELECT * FROM watchlist ORDER BY symbol").fetchall()
        return [WatchlistEntry(
            symbol=r["symbol"], company_name=r["company_name"], added_at=r["added_at"],
        ) for r in rows]

    def upsert_shareholding(self, records: list[ShareholdingRecord]) -> int:
        """Insert or replace shareholding records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            # Check for existing value before replace
            existing = self._conn.execute(
                "SELECT percentage FROM shareholding WHERE symbol = ? AND quarter_end = ? AND category = ?",
                (r.symbol, r.quarter_end, r.category),
            ).fetchone()
            if existing and existing["percentage"] != r.percentage:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("shareholding", r.symbol, f"{r.quarter_end}|{r.category}",
                     "percentage", str(existing["percentage"]), str(r.percentage)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO shareholding (symbol, quarter_end, category, percentage) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.category, r.percentage),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_shareholding(self, symbol: str, limit: int = 8) -> list[ShareholdingRecord]:
        """Get shareholding records for a symbol, most recent quarters first."""
        rows = self._conn.execute(
            "SELECT * FROM shareholding WHERE symbol = ? "
            "ORDER BY quarter_end DESC, category LIMIT ?",
            (symbol.upper(), limit * 6),  # 6 categories per quarter
        ).fetchall()
        return [ShareholdingRecord(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            category=r["category"], percentage=r["percentage"],
        ) for r in rows]

    def get_shareholding_changes(self, symbol: str) -> list[ShareholdingChange]:
        """Get quarter-over-quarter shareholding changes for a symbol."""
        rows = self._conn.execute(
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.symbol = ? "
            "AND s1.quarter_end = (SELECT MAX(quarter_end) FROM shareholding WHERE symbol = ?) "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC",
            (symbol.upper(), symbol.upper()),
        ).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_biggest_changes(self, category: str | None = None, limit: int = 10) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all watchlist stocks."""
        cat_filter = "AND s1.category = ?" if category else ""
        params: list = []

        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN watchlist w ON s1.symbol = w.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            f") {cat_filter} "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC LIMIT ?"
        )
        if category:
            params = [category, limit]
        else:
            params = [limit]

        rows = self._conn.execute(query, params).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    # -- Phase 5: Index Scanner --

    def upsert_index_constituents(self, constituents: list[IndexConstituent]) -> int:
        """Insert or replace index constituents."""
        cursor = self._conn.cursor()
        count = 0
        for c in constituents:
            cursor.execute(
                "INSERT OR REPLACE INTO index_constituents (symbol, index_name, company_name, industry) "
                "VALUES (?, ?, ?, ?)",
                (c.symbol, c.index_name, c.company_name, c.industry),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_index_constituents(self, index_name: str | None = None) -> list[IndexConstituent]:
        """Get index constituents, optionally filtered by index name."""
        if index_name:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents WHERE index_name = ? ORDER BY symbol",
                (index_name,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents ORDER BY index_name, symbol"
            ).fetchall()
        return [IndexConstituent(
            symbol=r["symbol"], index_name=r["index_name"],
            company_name=r["company_name"], industry=r["industry"],
        ) for r in rows]

    def get_all_scanner_symbols(self) -> list[str]:
        """Get distinct symbols from index_constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT symbol FROM index_constituents ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]

    def get_scanner_deviations(
        self, category: str | None = None, limit: int = 20, min_change: float = 0.0,
    ) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all index constituents."""
        cat_filter = "AND s1.category = ?" if category else ""
        min_filter = f"AND ABS(s1.percentage - s2.percentage) >= {min_change}" if min_change > 0 else ""
        params: list = []

        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN index_constituents ic ON s1.symbol = ic.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            f") {cat_filter} {min_filter} "
            "GROUP BY s1.symbol, s1.category "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC LIMIT ?"
        )
        if category:
            params = [category, limit]
        else:
            params = [limit]

        rows = self._conn.execute(query, params).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_handoff_signals(self, limit: int = 20) -> list[tuple[ShareholdingChange, ShareholdingChange]]:
        """Find stocks where FII decreased AND MF increased (handoff pattern).

        Returns list of (fii_change, mf_change) tuples.
        """
        # Get all latest QoQ changes for scanner stocks
        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN index_constituents ic ON s1.symbol = ic.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            ") "
            "AND s1.category IN ('FII', 'MF') "
            "GROUP BY s1.symbol, s1.category "
            "ORDER BY s1.symbol"
        )
        rows = self._conn.execute(query).fetchall()

        # Group by symbol, find FII-down + MF-up pairs
        by_symbol: dict[str, dict[str, ShareholdingChange]] = {}
        for r in rows:
            change = ShareholdingChange(
                symbol=r["symbol"], category=r["category"],
                prev_quarter_end=r["prev_qtr"], curr_quarter_end=r["curr_qtr"],
                prev_pct=r["prev_pct"], curr_pct=r["curr_pct"],
                change_pct=r["curr_pct"] - r["prev_pct"],
            )
            by_symbol.setdefault(r["symbol"], {})[r["category"]] = change

        handoffs: list[tuple[ShareholdingChange, ShareholdingChange]] = []
        for symbol, cats in by_symbol.items():
            fii = cats.get("FII")
            mf = cats.get("MF")
            if fii and mf and fii.change_pct < 0 and mf.change_pct > 0:
                handoffs.append((fii, mf))

        # Sort by FII selling magnitude
        handoffs.sort(key=lambda x: x[0].change_pct)
        return handoffs[:limit]

    # -- Commodity Prices --

    def upsert_commodity_prices(self, prices: list[CommodityPrice]) -> int:
        """Insert or replace commodity price records."""
        import math
        cursor = self._conn.cursor()
        count = 0
        for p in prices:
            if math.isnan(p.price):
                continue
            cursor.execute(
                "INSERT OR REPLACE INTO commodity_prices (date, symbol, price, unit) "
                "VALUES (?, ?, ?, ?)",
                (p.date, p.symbol, p.price, p.unit),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_etf_navs(self, navs: list[GoldETFNav]) -> int:
        """Insert or replace gold ETF NAV records."""
        cursor = self._conn.cursor()
        count = 0
        for n in navs:
            cursor.execute(
                "INSERT OR REPLACE INTO gold_etf_nav (date, scheme_code, scheme_name, nav) "
                "VALUES (?, ?, ?, ?)",
                (n.date, n.scheme_code, n.scheme_name, n.nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_commodity_prices(self, symbol: str, days: int = 30) -> list[CommodityPrice]:
        """Get commodity prices for a symbol, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM commodity_prices WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [CommodityPrice(
            date=r["date"], symbol=r["symbol"], price=r["price"], unit=r["unit"],
        ) for r in rows]

    def get_etf_navs(self, scheme_code: str, days: int = 365) -> list[GoldETFNav]:
        """Get ETF NAVs for a scheme, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM gold_etf_nav WHERE scheme_code = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (scheme_code, f"-{days}"),
        ).fetchall()
        return [GoldETFNav(
            date=r["date"], scheme_code=r["scheme_code"],
            scheme_name=r["scheme_name"], nav=r["nav"],
        ) for r in rows]

    def get_gold_fii_correlation(self, days: int = 30) -> list[GoldCorrelation]:
        """Get FII daily net flows aligned with gold price changes."""
        rows = self._conn.execute(
            "SELECT df.date, df.net_value AS fii_net, "
            "cp_gold.price AS gold_close, cp_inr.price AS gold_inr "
            "FROM daily_flows df "
            "LEFT JOIN commodity_prices cp_gold ON df.date = cp_gold.date AND cp_gold.symbol = 'GOLD' "
            "LEFT JOIN commodity_prices cp_inr ON df.date = cp_inr.date AND cp_inr.symbol = 'GOLD_INR' "
            "WHERE df.category = 'FII' AND cp_gold.price IS NOT NULL "
            "AND df.date >= date('now', ? || ' days') "
            "ORDER BY df.date DESC",
            (f"-{days}",),
        ).fetchall()

        results: list[GoldCorrelation] = []
        for i, r in enumerate(rows):
            # Calculate day-over-day gold change %
            if i + 1 < len(rows) and rows[i + 1]["gold_close"]:
                prev_gold = rows[i + 1]["gold_close"]
                change_pct = round((r["gold_close"] - prev_gold) / prev_gold * 100, 2) if prev_gold else 0.0
            else:
                change_pct = 0.0

            results.append(GoldCorrelation(
                date=r["date"],
                fii_net=r["fii_net"],
                gold_close=r["gold_close"],
                gold_change_pct=change_pct,
                gold_inr=r["gold_inr"],
            ))
        return results

    # -- Promoter Pledge --

    def upsert_promoter_pledges(self, pledges: list[PromoterPledge]) -> int:
        """Insert or replace promoter pledge records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for p in pledges:
            existing = self._conn.execute(
                "SELECT pledge_pct, encumbered_pct FROM promoter_pledge WHERE symbol = ? AND quarter_end = ?",
                (p.symbol, p.quarter_end),
            ).fetchone()
            if existing and (existing["pledge_pct"] != p.pledge_pct or existing["encumbered_pct"] != p.encumbered_pct):
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("promoter_pledge", p.symbol, p.quarter_end,
                     "pledge_pct", str(existing["pledge_pct"]), str(p.pledge_pct)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO promoter_pledge (symbol, quarter_end, pledge_pct, encumbered_pct) "
                "VALUES (?, ?, ?, ?)",
                (p.symbol, p.quarter_end, p.pledge_pct, p.encumbered_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_promoter_pledge(self, symbol: str, limit: int = 8) -> list[PromoterPledge]:
        """Get promoter pledge history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM promoter_pledge WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def get_high_pledge_stocks(self, min_pledge_pct: float = 1.0, limit: int = 20) -> list[PromoterPledge]:
        """Get stocks with high promoter pledging from latest quarter, joined with scanner stocks."""
        rows = self._conn.execute(
            "SELECT pp.* FROM promoter_pledge pp "
            "INNER JOIN index_constituents ic ON pp.symbol = ic.symbol "
            "WHERE pp.quarter_end = ("
            "  SELECT MAX(pp2.quarter_end) FROM promoter_pledge pp2 WHERE pp2.symbol = pp.symbol"
            ") AND pp.pledge_pct >= ? "
            "ORDER BY pp.pledge_pct DESC LIMIT ?",
            (min_pledge_pct, limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def get_scan_summary(self) -> ScanSummary:
        """Get aggregate stats for the scanner."""
        all_symbols = self.get_all_scanner_symbols()
        total = len(all_symbols)

        # Find latest quarter in shareholding for scanner symbols
        row = self._conn.execute(
            "SELECT MAX(quarter_end) as latest FROM shareholding s "
            "INNER JOIN index_constituents ic ON s.symbol = ic.symbol"
        ).fetchone()
        latest_quarter = row["latest"] if row and row["latest"] else None

        # Symbols that have any shareholding data
        rows = self._conn.execute(
            "SELECT DISTINCT s.symbol FROM shareholding s "
            "INNER JOIN index_constituents ic ON s.symbol = ic.symbol"
        ).fetchall()
        symbols_with_data = {r["symbol"] for r in rows}

        missing = sorted(set(all_symbols) - symbols_with_data)

        return ScanSummary(
            total_symbols=total,
            symbols_with_data=len(symbols_with_data),
            latest_quarter=latest_quarter,
            missing_symbols=missing,
        )

    # -- Fundamentals: Quarterly Results --

    def upsert_quarterly_results(self, results: list[QuarterlyResult]) -> int:
        """Insert or replace quarterly results. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in results:
            existing = self._conn.execute(
                "SELECT revenue FROM quarterly_results WHERE symbol = ? AND quarter_end = ?",
                (r.symbol, r.quarter_end),
            ).fetchone()
            warnings = _validate_row("quarterly_results", r.model_dump())
            if warnings:
                _val_logger.warning("quarterly_results %s/%s: %s", r.symbol, r.quarter_end, "; ".join(warnings))
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("quarterly_results", r.symbol, r.quarter_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO quarterly_results "
                "(symbol, quarter_end, revenue, gross_profit, operating_income, net_income, "
                "ebitda, eps, eps_diluted, operating_margin, net_margin, "
                "expenses, other_income, depreciation, interest, profit_before_tax, tax_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.revenue, r.gross_profit, r.operating_income,
                 r.net_income, r.ebitda, r.eps, r.eps_diluted, r.operating_margin, r.net_margin,
                 r.expenses, r.other_income, r.depreciation, r.interest, r.profit_before_tax, r.tax_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_quarterly_results(self, symbol: str, limit: int = 12) -> list[QuarterlyResult]:
        """Get stored quarterly results, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_results WHERE symbol = ? "
            "ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [QuarterlyResult(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            revenue=r["revenue"], gross_profit=r["gross_profit"],
            operating_income=r["operating_income"], net_income=r["net_income"],
            ebitda=r["ebitda"], eps=r["eps"], eps_diluted=r["eps_diluted"],
            operating_margin=r["operating_margin"], net_margin=r["net_margin"],
            expenses=r["expenses"], other_income=r["other_income"],
            depreciation=r["depreciation"], interest=r["interest"],
            profit_before_tax=r["profit_before_tax"], tax_pct=r["tax_pct"],
        ) for r in rows]

    # -- Fundamentals: Valuation Snapshots --

    def upsert_valuation_snapshot(self, snapshot: ValuationSnapshot) -> int:
        """Insert or replace a valuation snapshot. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        existing = self._conn.execute(
            "SELECT pe_trailing FROM valuation_snapshot WHERE symbol = ? AND date = ?",
            (snapshot.symbol, snapshot.date),
        ).fetchone()
        warnings = _validate_row("valuation_snapshot", snapshot.model_dump())
        if warnings:
            _val_logger.warning("valuation_snapshot %s/%s: %s", snapshot.symbol, snapshot.date, "; ".join(warnings))
        if existing and existing["pe_trailing"] != snapshot.pe_trailing:
            cursor.execute(
                "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("valuation_snapshot", snapshot.symbol, snapshot.date,
                 "pe_trailing", str(existing["pe_trailing"]), str(snapshot.pe_trailing)),
            )
        cursor.execute(
            "INSERT OR REPLACE INTO valuation_snapshot "
            "(symbol, date, price, market_cap, enterprise_value, "
            "fifty_two_week_high, fifty_two_week_low, beta, "
            "pe_trailing, pe_forward, pb_ratio, ev_ebitda, ev_revenue, ps_ratio, peg_ratio, "
            "gross_margin, operating_margin, net_margin, roe, roa, "
            "revenue_growth, earnings_growth, earnings_quarterly_growth, "
            "dividend_yield, debt_to_equity, current_ratio, total_cash, total_debt, "
            "book_value_per_share, free_cash_flow, operating_cash_flow, "
            "revenue_per_share, cash_per_share, avg_volume, float_shares, shares_outstanding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot.symbol, snapshot.date, snapshot.price, snapshot.market_cap,
             snapshot.enterprise_value, snapshot.fifty_two_week_high, snapshot.fifty_two_week_low,
             snapshot.beta, snapshot.pe_trailing, snapshot.pe_forward, snapshot.pb_ratio,
             snapshot.ev_ebitda, snapshot.ev_revenue, snapshot.ps_ratio, snapshot.peg_ratio,
             snapshot.gross_margin, snapshot.operating_margin, snapshot.net_margin,
             snapshot.roe, snapshot.roa, snapshot.revenue_growth, snapshot.earnings_growth,
             snapshot.earnings_quarterly_growth, snapshot.dividend_yield,
             snapshot.debt_to_equity, snapshot.current_ratio, snapshot.total_cash,
             snapshot.total_debt, snapshot.book_value_per_share, snapshot.free_cash_flow,
             snapshot.operating_cash_flow, snapshot.revenue_per_share, snapshot.cash_per_share,
             snapshot.avg_volume, snapshot.float_shares, snapshot.shares_outstanding),
        )
        self._conn.commit()
        return cursor.rowcount

    def upsert_valuation_snapshots(self, snapshots: list[ValuationSnapshot]) -> int:
        """Batch insert valuation snapshots."""
        count = 0
        for s in snapshots:
            count += self.upsert_valuation_snapshot(s)
        return count

    def get_valuation_history(self, symbol: str, days: int = 365) -> list[ValuationSnapshot]:
        """Get valuation snapshots for the last N days, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM valuation_snapshot "
            "WHERE symbol = ? AND date >= date('now', ? || ' days') "
            "ORDER BY date ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()
        def _snap(r) -> ValuationSnapshot:
            d = dict(r)
            return ValuationSnapshot(
                symbol=d["symbol"], date=d["date"], price=d["price"],
                market_cap=d.get("market_cap"), enterprise_value=d.get("enterprise_value"),
                fifty_two_week_high=d.get("fifty_two_week_high"),
                fifty_two_week_low=d.get("fifty_two_week_low"),
                beta=d.get("beta"),
                pe_trailing=d.get("pe_trailing"), pe_forward=d.get("pe_forward"),
                pb_ratio=d.get("pb_ratio"), ev_ebitda=d.get("ev_ebitda"),
                ev_revenue=d.get("ev_revenue"), ps_ratio=d.get("ps_ratio"),
                peg_ratio=d.get("peg_ratio"),
                gross_margin=d.get("gross_margin"), operating_margin=d.get("operating_margin"),
                net_margin=d.get("net_margin"), roe=d.get("roe"), roa=d.get("roa"),
                revenue_growth=d.get("revenue_growth"), earnings_growth=d.get("earnings_growth"),
                earnings_quarterly_growth=d.get("earnings_quarterly_growth"),
                dividend_yield=d.get("dividend_yield"),
                debt_to_equity=d.get("debt_to_equity"), current_ratio=d.get("current_ratio"),
                total_cash=d.get("total_cash"), total_debt=d.get("total_debt"),
                book_value_per_share=d.get("book_value_per_share"),
                free_cash_flow=d.get("free_cash_flow"),
                operating_cash_flow=d.get("operating_cash_flow"),
                revenue_per_share=d.get("revenue_per_share"), cash_per_share=d.get("cash_per_share"),
                avg_volume=d.get("avg_volume"), float_shares=d.get("float_shares"),
                shares_outstanding=d.get("shares_outstanding"),
            )
        return [_snap(r) for r in rows]

    def get_valuation_band(self, symbol: str, metric: str, days: int = 1095) -> ValuationBand | None:
        """Compute min/max/median/percentile for a valuation metric over N days.

        metric must be a column name in valuation_snapshot (e.g., 'pe_trailing', 'ev_ebitda', 'pb_ratio').
        """
        # Validate metric name to prevent SQL injection
        valid_metrics = {
            "pe_trailing", "pe_forward", "pb_ratio", "ev_ebitda", "ev_revenue",
            "ps_ratio", "peg_ratio", "dividend_yield", "beta",
            "gross_margin", "operating_margin", "net_margin", "roe", "roa",
        }
        if metric not in valid_metrics:
            return None

        rows = self._conn.execute(
            f"SELECT {metric}, date FROM valuation_snapshot "
            f"WHERE symbol = ? AND date >= date('now', ? || ' days') AND {metric} IS NOT NULL "
            f"ORDER BY {metric} ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()

        if not rows:
            return None

        values = [r[metric] for r in rows]
        n = len(values)
        min_val = values[0]
        max_val = values[-1]
        median_val = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2

        # Get current value (most recent)
        latest = self._conn.execute(
            f"SELECT {metric} FROM valuation_snapshot "
            f"WHERE symbol = ? AND {metric} IS NOT NULL "
            f"ORDER BY date DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if latest is None:
            return None
        current_val = latest[metric]

        # Compute percentile
        below = sum(1 for v in values if v < current_val)
        percentile = (below / n) * 100

        dates = [r["date"] for r in rows]
        return ValuationBand(
            symbol=symbol.upper(),
            metric=metric,
            min_val=min_val,
            max_val=max_val,
            median_val=median_val,
            current_val=current_val,
            percentile=percentile,
            num_observations=n,
            period_start=min(dates),
            period_end=max(dates),
        )

    # -- Fundamentals: Annual Financials --

    def upsert_annual_financials(self, records: list) -> int:
        """Insert or replace annual financials. Audit-logged."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            existing = self._conn.execute(
                "SELECT revenue FROM annual_financials WHERE symbol = ? AND fiscal_year_end = ?",
                (r.symbol, r.fiscal_year_end),
            ).fetchone()
            warnings = _validate_row("annual_financials", r.model_dump())
            if warnings:
                _val_logger.warning("annual_financials %s/%s: %s", r.symbol, r.fiscal_year_end, "; ".join(warnings))
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("annual_financials", r.symbol, r.fiscal_year_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO annual_financials "
                "(symbol, fiscal_year_end, revenue, employee_cost, other_income, depreciation, "
                "interest, profit_before_tax, tax, net_income, eps, dividend_amount, "
                "equity_capital, reserves, borrowings, other_liabilities, total_assets, "
                "net_block, cwip, investments, other_assets, receivables, inventory, "
                "cash_and_bank, num_shares, cfo, cfi, cff, net_cash_flow, price, "
                "raw_material_cost, power_and_fuel, other_mfr_exp, selling_and_admin, "
                "other_expenses_detail, total_expenses, operating_profit) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.fiscal_year_end, r.revenue, r.employee_cost, r.other_income,
                 r.depreciation, r.interest, r.profit_before_tax, r.tax, r.net_income,
                 r.eps, r.dividend_amount, r.equity_capital, r.reserves, r.borrowings,
                 r.other_liabilities, r.total_assets, r.net_block, r.cwip, r.investments,
                 r.other_assets, r.receivables, r.inventory, r.cash_and_bank, r.num_shares,
                 r.cfo, r.cfi, r.cff, r.net_cash_flow, r.price,
                 r.raw_material_cost, r.power_and_fuel, r.other_mfr_exp, r.selling_and_admin,
                 r.other_expenses_detail, r.total_expenses, r.operating_profit),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_annual_financials(self, symbol: str, limit: int = 10) -> list:
        """Get stored annual financials, most recent first."""
        from flowtracker.fund_models import AnnualFinancials
        rows = self._conn.execute(
            "SELECT * FROM annual_financials WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [AnnualFinancials(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            revenue=r["revenue"], employee_cost=r["employee_cost"],
            other_income=r["other_income"], depreciation=r["depreciation"],
            interest=r["interest"], profit_before_tax=r["profit_before_tax"],
            tax=r["tax"], net_income=r["net_income"], eps=r["eps"],
            dividend_amount=r["dividend_amount"], equity_capital=r["equity_capital"],
            reserves=r["reserves"], borrowings=r["borrowings"],
            other_liabilities=r["other_liabilities"], total_assets=r["total_assets"],
            net_block=r["net_block"], cwip=r["cwip"], investments=r["investments"],
            other_assets=r["other_assets"], receivables=r["receivables"],
            inventory=r["inventory"], cash_and_bank=r["cash_and_bank"],
            num_shares=r["num_shares"], cfo=r["cfo"], cfi=r["cfi"],
            cff=r["cff"], net_cash_flow=r["net_cash_flow"], price=r["price"],
            raw_material_cost=r["raw_material_cost"], power_and_fuel=r["power_and_fuel"],
            other_mfr_exp=r["other_mfr_exp"], selling_and_admin=r["selling_and_admin"],
            other_expenses_detail=r["other_expenses_detail"], total_expenses=r["total_expenses"],
            operating_profit=r["operating_profit"],
        ) for r in rows]

    # -- Screener Ratios --

    def upsert_screener_ratios(self, ratios: list[ScreenerRatios]) -> int:
        """Insert or replace screener ratios."""
        cursor = self._conn.cursor()
        count = 0
        for r in ratios:
            cursor.execute(
                "INSERT OR REPLACE INTO screener_ratios "
                "(symbol, fiscal_year_end, debtor_days, inventory_days, days_payable, "
                "cash_conversion_cycle, working_capital_days, roce_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.fiscal_year_end, r.debtor_days, r.inventory_days,
                 r.days_payable, r.cash_conversion_cycle, r.working_capital_days, r.roce_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_screener_ratios(self, symbol: str, limit: int = 10) -> list[ScreenerRatios]:
        """Get stored screener ratios, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM screener_ratios WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [ScreenerRatios(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            debtor_days=r["debtor_days"], inventory_days=r["inventory_days"],
            days_payable=r["days_payable"], cash_conversion_cycle=r["cash_conversion_cycle"],
            working_capital_days=r["working_capital_days"], roce_pct=r["roce_pct"],
        ) for r in rows]

    # -- Macro Indicators --

    def upsert_macro_snapshots(self, snapshots: list[MacroSnapshot]) -> int:
        """Insert or replace macro daily snapshots."""
        cursor = self._conn.cursor()
        count = 0
        for s in snapshots:
            cursor.execute(
                "INSERT OR REPLACE INTO macro_daily "
                "(date, india_vix, usd_inr, brent_crude, gsec_10y) "
                "VALUES (?, ?, ?, ?, ?)",
                (s.date, s.india_vix, s.usd_inr, s.brent_crude, s.gsec_10y),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_macro_latest(self) -> MacroSnapshot | None:
        """Get the most recent macro snapshot."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MacroSnapshot(
            date=row["date"], india_vix=row["india_vix"],
            usd_inr=row["usd_inr"], brent_crude=row["brent_crude"],
            gsec_10y=row["gsec_10y"],
        )

    def get_macro_previous(self) -> MacroSnapshot | None:
        """Get the second most recent macro snapshot (for delta display)."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1 OFFSET 1"
        ).fetchone()
        if not row:
            return None
        return MacroSnapshot(
            date=row["date"], india_vix=row["india_vix"],
            usd_inr=row["usd_inr"], brent_crude=row["brent_crude"],
            gsec_10y=row["gsec_10y"],
        )

    def get_macro_trend(self, days: int = 30) -> list[MacroSnapshot]:
        """Get macro snapshots for the last N days, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM macro_daily "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC",
            (f"-{days}",),
        ).fetchall()
        return [MacroSnapshot(
            date=r["date"], india_vix=r["india_vix"],
            usd_inr=r["usd_inr"], brent_crude=r["brent_crude"],
            gsec_10y=r["gsec_10y"],
        ) for r in rows]

    # -- Bhavcopy + Delivery --

    def upsert_daily_stock_data(self, records: list[DailyStockData]) -> int:
        """Insert or replace daily stock data records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO daily_stock_data "
                "(date, symbol, open, high, low, close, prev_close, volume, "
                "turnover, delivery_qty, delivery_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.date, r.symbol, r.open, r.high, r.low, r.close, r.prev_close,
                 r.volume, r.turnover, r.delivery_qty, r.delivery_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_top_delivery(self, date_str: str | None = None, limit: int = 20) -> list[DailyStockData]:
        """Get stocks with highest delivery % for a date (default: latest)."""
        if date_str is None:
            row = self._conn.execute("SELECT MAX(date) as d FROM daily_stock_data").fetchone()
            if not row or not row["d"]:
                return []
            date_str = row["d"]
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE date = ? AND delivery_pct IS NOT NULL "
            "ORDER BY delivery_pct DESC LIMIT ?",
            (date_str, limit),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    def get_stock_delivery(self, symbol: str, days: int = 30) -> list[DailyStockData]:
        """Get delivery trend for a specific stock."""
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    # -- Bulk/Block Deals --

    def upsert_deals(self, deals: list[BulkBlockDeal]) -> int:
        """Insert or replace bulk/block deal records."""
        cursor = self._conn.cursor()
        count = 0
        for d in deals:
            cursor.execute(
                "INSERT OR REPLACE INTO bulk_block_deals "
                "(date, deal_type, symbol, client_name, buy_sell, quantity, price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (d.date, d.deal_type, d.symbol, d.client_name, d.buy_sell,
                 d.quantity, d.price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_deals_latest(self) -> list[BulkBlockDeal]:
        """Get deals for the most recent day."""
        row = self._conn.execute("SELECT MAX(date) as d FROM bulk_block_deals").fetchone()
        if not row or not row["d"]:
            return []
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE date = ? ORDER BY deal_type, symbol",
            (row["d"],),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_by_symbol(self, symbol: str) -> list[BulkBlockDeal]:
        """Get all deals for a specific symbol."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE symbol = ? ORDER BY date DESC",
            (symbol,),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_top(self, days: int = 30, limit: int = 20) -> list[BulkBlockDeal]:
        """Get biggest deals by value in the last N days."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals "
            "WHERE date >= date('now', ? || ' days') AND price IS NOT NULL "
            "ORDER BY (quantity * price) DESC LIMIT ?",
            (f"-{days}", limit),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    # -- Insider/SAST Transactions --

    def upsert_insider_transactions(self, trades: list[InsiderTransaction]) -> int:
        """Insert or replace insider transaction records."""
        cursor = self._conn.cursor()
        count = 0
        for t in trades:
            warnings = _validate_row("insider_transactions", t.model_dump())
            if warnings:
                _val_logger.warning("insider_transactions %s/%s: %s", t.symbol, t.date, "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO insider_transactions "
                "(date, symbol, person_name, person_category, transaction_type, "
                "quantity, value, mode, holding_before_pct, holding_after_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t.date, t.symbol, t.person_name, t.person_category,
                 t.transaction_type, t.quantity, t.value, t.mode,
                 t.holding_before_pct, t.holding_after_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_insider_by_symbol(self, symbol: str, days: int = 365) -> list[InsiderTransaction]:
        """Get insider transactions for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    def get_promoter_buys(self, days: int = 30) -> list[InsiderTransaction]:
        """Get promoter buying transactions."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions "
            "WHERE person_category LIKE '%Promoter%' "
            "AND transaction_type = 'Buy' "
            "AND date >= date('now', ? || ' days') "
            "ORDER BY value DESC",
            (f"-{days}",),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    # -- Consensus Estimates --

    def upsert_consensus_estimates(self, estimates: list[ConsensusEstimate]) -> int:
        """Insert or replace consensus estimate records."""
        cursor = self._conn.cursor()
        count = 0
        for e in estimates:
            cursor.execute(
                "INSERT OR REPLACE INTO consensus_estimates "
                "(symbol, date, target_mean, target_median, target_high, target_low, "
                "num_analysts, recommendation, recommendation_score, forward_pe, "
                "forward_eps, eps_current_year, eps_next_year, earnings_growth, current_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e.symbol, e.date, e.target_mean, e.target_median, e.target_high,
                 e.target_low, e.num_analysts, e.recommendation, e.recommendation_score,
                 e.forward_pe, e.forward_eps, e.eps_current_year, e.eps_next_year,
                 e.earnings_growth, e.current_price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_earnings_surprises(self, surprises: list[EarningsSurprise]) -> int:
        """Insert or replace earnings surprise records."""
        cursor = self._conn.cursor()
        count = 0
        for s in surprises:
            cursor.execute(
                "INSERT OR REPLACE INTO earnings_surprises "
                "(symbol, quarter_end, eps_actual, eps_estimate, surprise_pct) "
                "VALUES (?, ?, ?, ?, ?)",
                (s.symbol, s.quarter_end, s.eps_actual, s.eps_estimate, s.surprise_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_estimate_latest(self, symbol: str) -> ConsensusEstimate | None:
        """Get the most recent estimate for a symbol."""
        row = self._conn.execute(
            "SELECT * FROM consensus_estimates WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return ConsensusEstimate(
            symbol=row["symbol"], date=row["date"],
            target_mean=row["target_mean"], target_median=row["target_median"],
            target_high=row["target_high"], target_low=row["target_low"],
            num_analysts=row["num_analysts"], recommendation=row["recommendation"],
            recommendation_score=row["recommendation_score"],
            forward_pe=row["forward_pe"], forward_eps=row["forward_eps"],
            eps_current_year=row["eps_current_year"], eps_next_year=row["eps_next_year"],
            earnings_growth=row["earnings_growth"], current_price=row["current_price"],
        )

    def get_all_latest_estimates(self) -> list[ConsensusEstimate]:
        """Get latest estimate for each symbol, ranked by upside."""
        rows = self._conn.execute(
            "SELECT ce.* FROM consensus_estimates ce "
            "INNER JOIN (SELECT symbol, MAX(date) as max_date FROM consensus_estimates "
            "GROUP BY symbol) latest "
            "ON ce.symbol = latest.symbol AND ce.date = latest.max_date "
            "ORDER BY CASE WHEN ce.target_mean IS NOT NULL AND ce.current_price IS NOT NULL "
            "AND ce.current_price > 0 "
            "THEN (ce.target_mean - ce.current_price) / ce.current_price ELSE -999 END DESC"
        ).fetchall()
        return [ConsensusEstimate(
            symbol=r["symbol"], date=r["date"],
            target_mean=r["target_mean"], target_median=r["target_median"],
            target_high=r["target_high"], target_low=r["target_low"],
            num_analysts=r["num_analysts"], recommendation=r["recommendation"],
            recommendation_score=r["recommendation_score"],
            forward_pe=r["forward_pe"], forward_eps=r["forward_eps"],
            eps_current_year=r["eps_current_year"], eps_next_year=r["eps_next_year"],
            earnings_growth=r["earnings_growth"], current_price=r["current_price"],
        ) for r in rows]

    def get_surprises(self, symbol: str) -> list[EarningsSurprise]:
        """Get earnings surprises for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises WHERE symbol = ? ORDER BY quarter_end DESC",
            (symbol,),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    def get_recent_surprises(self, days: int = 90) -> list[EarningsSurprise]:
        """Get recent earnings surprises across all stocks."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises "
            "WHERE quarter_end >= date('now', ? || ' days') "
            "ORDER BY ABS(COALESCE(surprise_pct, 0)) DESC",
            (f"-{days}",),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    # -- Sector Aggregation --

    def get_sector_overview(self) -> list[dict]:
        """Get sector-level ownership shifts + delivery + price signals.

        Returns list of dicts with industry, num_stocks, avg changes per category,
        avg delivery %, avg price change %.
        """
        rows = self._conn.execute("""
            SELECT
                ic.industry,
                COUNT(DISTINCT ic.symbol) as num_stocks,
                AVG(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as avg_fii_change,
                AVG(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as avg_mf_change,
                AVG(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as avg_dii_change,
                AVG(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as avg_promoter_change,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                SELECT ic2.industry,
                    AVG(d.delivery_pct) as avg_delivery_pct,
                    AVG((d.close - d.prev_close) / NULLIF(d.prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data d
                INNER JOIN index_constituents ic2 ON d.symbol = ic2.symbol
                WHERE d.date >= date('now', '-30 days')
                    AND d.delivery_pct IS NOT NULL
                GROUP BY ic2.industry
            ) del_stats ON ic.industry = del_stats.industry
            WHERE ic.industry IS NOT NULL
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.industry
            HAVING num_stocks >= 3
            ORDER BY avg_mf_change DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_sector_detail(self, industry: str) -> list[dict]:
        """Get stock-level ownership + delivery + price data for a sector."""
        rows = self._conn.execute("""
            SELECT
                ic.symbol,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage END) as curr_fii,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage END) as curr_mf,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as fii_change,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as mf_change,
                MAX(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as dii_change,
                MAX(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as promoter_change,
                vs.pe_trailing,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                SELECT symbol, pe_trailing FROM valuation_snapshot
                WHERE (symbol, date) IN (
                    SELECT symbol, MAX(date) FROM valuation_snapshot GROUP BY symbol
                )
            ) vs ON ic.symbol = vs.symbol
            LEFT JOIN (
                SELECT symbol,
                    AVG(delivery_pct) as avg_delivery_pct,
                    AVG((close - prev_close) / NULLIF(prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data
                WHERE date >= date('now', '-30 days') AND delivery_pct IS NOT NULL
                GROUP BY symbol
            ) del_stats ON ic.symbol = del_stats.symbol
            WHERE ic.industry = ?
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.symbol
            ORDER BY mf_change DESC
        """, (industry,)).fetchall()
        return [dict(r) for r in rows]

    def get_sector_list(self) -> list[str]:
        """Get distinct industry names from index constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT industry FROM index_constituents "
            "WHERE industry IS NOT NULL ORDER BY industry"
        ).fetchall()
        return [r["industry"] for r in rows]

    def get_sector_valuation_summary(self, industry: str) -> dict:
        """Get aggregate valuation metrics for a sector/industry.

        Joins index_constituents → valuation_snapshot (latest per stock)
        → screener_ratios (latest ROCE per stock).
        Returns stock count, total mcap, median PE/PB/ROCE, PE range, top 5 by mcap.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol, ic.company_name,
                vs.market_cap, vs.pe_trailing, vs.pb_ratio,
                sr.roce_pct
            FROM index_constituents ic
            LEFT JOIN valuation_snapshot vs ON ic.symbol = vs.symbol
                AND vs.date = (
                    SELECT MAX(v2.date) FROM valuation_snapshot v2
                    WHERE v2.symbol = ic.symbol
                )
            LEFT JOIN screener_ratios sr ON ic.symbol = sr.symbol
                AND sr.fiscal_year_end = (
                    SELECT MAX(sr2.fiscal_year_end) FROM screener_ratios sr2
                    WHERE sr2.symbol = ic.symbol
                )
            WHERE ic.industry = ?
        """, (industry,)).fetchall()

        if not rows:
            return {
                "industry": industry, "stock_count": 0, "total_mcap_cr": 0.0,
                "median_pe": None, "median_pb": None, "median_roce": None,
                "pe_range": {"min": None, "max": None},
                "top_by_mcap": [],
            }

        def _median(vals: list[float]) -> float | None:
            if not vals:
                return None
            s = sorted(vals)
            n = len(s)
            if n % 2 == 1:
                return round(s[n // 2], 2)
            return round((s[n // 2 - 1] + s[n // 2]) / 2, 2)

        pe_vals = [r["pe_trailing"] for r in rows if r["pe_trailing"] and r["pe_trailing"] > 0]
        pb_vals = [r["pb_ratio"] for r in rows if r["pb_ratio"] and r["pb_ratio"] > 0]
        roce_vals = [r["roce_pct"] for r in rows if r["roce_pct"] is not None]
        mcaps = [(r["symbol"], r["company_name"], r["market_cap"] or 0, r["pe_trailing"]) for r in rows]
        mcaps.sort(key=lambda x: x[2], reverse=True)

        return {
            "industry": industry,
            "stock_count": len(rows),
            "total_mcap_cr": round(sum(r["market_cap"] or 0 for r in rows), 2),
            "median_pe": _median(pe_vals),
            "median_pb": _median(pb_vals),
            "median_roce": _median(roce_vals),
            "pe_range": {
                "min": round(min(pe_vals), 2) if pe_vals else None,
                "max": round(max(pe_vals), 2) if pe_vals else None,
            },
            "top_by_mcap": [
                {"symbol": s, "company_name": cn, "mcap_cr": round(mc, 2), "pe": round(pe, 2) if pe else None}
                for s, cn, mc, pe in mcaps[:5]
            ],
        }

    def get_sector_mf_flows(self, industry: str) -> dict:
        """Get MF ownership change summary for a sector/industry.

        Joins index_constituents → shareholding (latest vs previous quarter,
        category='MF'). Returns counts of stocks where MF% increased/decreased,
        avg change, and top additions/reductions.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol,
                s1.percentage AS curr_pct,
                s2.percentage AS prev_pct,
                s1.percentage - s2.percentage AS mf_change
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
                AND s1.category = 'MF'
                AND s1.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = ic.symbol AND s3.category = 'MF'
                )
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s2.category = 'MF'
                AND s2.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol AND s4.category = 'MF'
                    AND s4.quarter_end < s1.quarter_end
                )
            WHERE ic.industry = ?
        """, (industry,)).fetchall()

        if not rows:
            return {
                "industry": industry, "total_stocks": 0,
                "mf_increased": 0, "mf_decreased": 0, "avg_mf_change_pct": 0.0,
                "top_additions": [], "top_reductions": [],
            }

        changes = [{"symbol": r["symbol"], "mf_change_pct": round(r["mf_change"], 2)} for r in rows]
        increased = [c for c in changes if c["mf_change_pct"] > 0]
        decreased = [c for c in changes if c["mf_change_pct"] < 0]
        avg_change = round(sum(c["mf_change_pct"] for c in changes) / len(changes), 2)

        top_additions = sorted(increased, key=lambda x: x["mf_change_pct"], reverse=True)[:5]
        top_reductions = sorted(decreased, key=lambda x: x["mf_change_pct"])[:5]

        return {
            "industry": industry,
            "total_stocks": len(changes),
            "mf_increased": len(increased),
            "mf_decreased": len(decreased),
            "avg_mf_change_pct": avg_change,
            "top_additions": top_additions,
            "top_reductions": top_reductions,
        }

    def get_sector_stocks_ranked(self, industry: str) -> list[dict]:
        """Get all stocks in a sector ranked by market cap, with key metrics.

        Joins index_constituents → valuation_snapshot (latest) →
        shareholding (latest FII/MF %) → screener_ratios (latest ROCE).
        Returns list of dicts sorted by mcap descending.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol, ic.company_name,
                vs.market_cap, vs.pe_trailing,
                sr.roce_pct,
                fii.percentage AS fii_pct,
                mf.percentage AS mf_pct,
                vs.earnings_growth AS price_change_1yr_pct
            FROM index_constituents ic
            LEFT JOIN valuation_snapshot vs ON ic.symbol = vs.symbol
                AND vs.date = (
                    SELECT MAX(v2.date) FROM valuation_snapshot v2
                    WHERE v2.symbol = ic.symbol
                )
            LEFT JOIN screener_ratios sr ON ic.symbol = sr.symbol
                AND sr.fiscal_year_end = (
                    SELECT MAX(sr2.fiscal_year_end) FROM screener_ratios sr2
                    WHERE sr2.symbol = ic.symbol
                )
            LEFT JOIN shareholding fii ON ic.symbol = fii.symbol
                AND fii.category = 'FII'
                AND fii.quarter_end = (
                    SELECT MAX(f2.quarter_end) FROM shareholding f2
                    WHERE f2.symbol = ic.symbol AND f2.category = 'FII'
                )
            LEFT JOIN shareholding mf ON ic.symbol = mf.symbol
                AND mf.category = 'MF'
                AND mf.quarter_end = (
                    SELECT MAX(m2.quarter_end) FROM shareholding m2
                    WHERE m2.symbol = ic.symbol AND m2.category = 'MF'
                )
            WHERE ic.industry = ?
            ORDER BY vs.market_cap DESC
        """, (industry,)).fetchall()

        return [{
            "symbol": r["symbol"],
            "company_name": r["company_name"],
            "mcap_cr": round(r["market_cap"], 2) if r["market_cap"] else None,
            "pe": round(r["pe_trailing"], 2) if r["pe_trailing"] else None,
            "roce_pct": round(r["roce_pct"], 2) if r["roce_pct"] else None,
            "fii_pct": round(r["fii_pct"], 2) if r["fii_pct"] else None,
            "mf_pct": round(r["mf_pct"], 2) if r["mf_pct"] else None,
            "price_change_1yr_pct": round(r["price_change_1yr_pct"], 2) if r["price_change_1yr_pct"] else None,
        } for r in rows]

    # -- MF Scheme Holdings --

    def upsert_mf_scheme_holdings(self, holdings: list[MFSchemeHolding]) -> int:
        """Insert or replace MF scheme holding records."""
        cursor = self._conn.cursor()
        count = 0
        for h in holdings:
            warnings = _validate_row("mf_scheme_holdings", h.model_dump())
            if warnings:
                _val_logger.warning("mf_scheme_holdings %s/%s/%s: %s", h.amc, h.month, h.stock_name[:20], "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO mf_scheme_holdings "
                "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (h.month, h.amc, h.scheme_name, h.isin, h.stock_name,
                 h.quantity, h.market_value_cr, h.pct_of_nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_stock_holdings(self, search: str) -> list[MFSchemeHolding]:
        """Get MF holdings for a stock by name or ISIN."""
        rows = self._conn.execute(
            "SELECT * FROM mf_scheme_holdings "
            "WHERE (UPPER(stock_name) LIKE ? OR isin = ?) "
            "AND month = (SELECT MAX(month) FROM mf_scheme_holdings) "
            "ORDER BY market_value_cr DESC",
            (f"%{search}%", search),
        ).fetchall()
        return [MFSchemeHolding(
            month=r["month"], amc=r["amc"], scheme_name=r["scheme_name"],
            isin=r["isin"], stock_name=r["stock_name"], quantity=r["quantity"],
            market_value_cr=r["market_value_cr"], pct_of_nav=r["pct_of_nav"],
        ) for r in rows]

    def get_mf_holding_changes(
        self, month: str | None = None, change_type: str = "buy", limit: int = 30,
    ) -> list[MFHoldingChange]:
        """Get month-over-month MF holding changes.

        change_type: "buy" for new+increased, "sell" for exits+decreased
        """
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        # Find previous month
        year, mon = int(month[:4]), int(month[5:7])
        if mon == 1:
            prev_month = f"{year - 1}-12"
        else:
            prev_month = f"{year}-{mon - 1:02d}"

        if change_type == "buy":
            # New positions (in curr but not in prev) + increased positions
            rows = self._conn.execute("""
                SELECT c.stock_name, c.isin, c.amc, c.scheme_name,
                    ? as prev_month, ? as curr_month,
                    COALESCE(p.quantity, 0) as prev_qty, c.quantity as curr_qty,
                    c.quantity - COALESCE(p.quantity, 0) as qty_change,
                    COALESCE(p.market_value_cr, 0) as prev_value,
                    c.market_value_cr as curr_value,
                    CASE WHEN p.isin IS NULL THEN 'NEW' ELSE 'INCREASE' END as change_type
                FROM mf_scheme_holdings c
                LEFT JOIN mf_scheme_holdings p ON c.isin = p.isin
                    AND c.amc = p.amc AND c.scheme_name = p.scheme_name
                    AND p.month = ?
                WHERE c.month = ?
                    AND (p.isin IS NULL OR c.quantity > p.quantity)
                ORDER BY c.market_value_cr - COALESCE(p.market_value_cr, 0) DESC
                LIMIT ?
            """, (prev_month, month, prev_month, month, limit)).fetchall()
        else:
            # Exits (in prev but not in curr) + decreased positions
            rows = self._conn.execute("""
                SELECT p.stock_name, p.isin, p.amc, p.scheme_name,
                    ? as prev_month, ? as curr_month,
                    p.quantity as prev_qty, COALESCE(c.quantity, 0) as curr_qty,
                    COALESCE(c.quantity, 0) - p.quantity as qty_change,
                    p.market_value_cr as prev_value,
                    COALESCE(c.market_value_cr, 0) as curr_value,
                    CASE WHEN c.isin IS NULL THEN 'EXIT' ELSE 'DECREASE' END as change_type
                FROM mf_scheme_holdings p
                LEFT JOIN mf_scheme_holdings c ON p.isin = c.isin
                    AND p.amc = c.amc AND p.scheme_name = c.scheme_name
                    AND c.month = ?
                WHERE p.month = ?
                    AND (c.isin IS NULL OR c.quantity < p.quantity)
                ORDER BY p.market_value_cr - COALESCE(c.market_value_cr, 0) DESC
                LIMIT ?
            """, (prev_month, month, month, prev_month, limit)).fetchall()

        return [MFHoldingChange(
            stock_name=r["stock_name"], isin=r["isin"], amc=r["amc"],
            scheme_name=r["scheme_name"], prev_month=r["prev_month"],
            curr_month=r["curr_month"], prev_qty=r["prev_qty"],
            curr_qty=r["curr_qty"], qty_change=r["qty_change"],
            prev_value=r["prev_value"], curr_value=r["curr_value"],
            change_type=r["change_type"],
        ) for r in rows]

    def get_mf_portfolio_summary(self, month: str | None = None) -> list[dict]:
        """Get AMC-level portfolio summary for a month."""
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        rows = self._conn.execute(
            "SELECT amc, COUNT(DISTINCT scheme_name) as num_schemes, "
            "COUNT(DISTINCT isin) as num_stocks, "
            "SUM(market_value_cr) as total_value_cr "
            "FROM mf_scheme_holdings WHERE month = ? "
            "GROUP BY amc ORDER BY total_value_cr DESC",
            (month,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Corporate Filings --

    def upsert_filings(self, filings: list[CorporateFiling]) -> int:
        """Insert or replace corporate filing records."""
        cursor = self._conn.cursor()
        count = 0
        for f in filings:
            if not f.news_id:
                continue
            cursor.execute(
                "INSERT OR REPLACE INTO corporate_filings "
                "(symbol, bse_scrip_code, filing_date, category, subcategory, "
                "headline, attachment_name, pdf_flag, file_size, news_id, local_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f.symbol, f.bse_scrip_code, f.filing_date, f.category,
                 f.subcategory, f.headline, f.attachment_name, f.pdf_flag,
                 f.file_size, f.news_id, f.local_path),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def update_filing_path(self, news_id: str, local_path: str) -> None:
        """Update the local file path for a downloaded filing."""
        self._conn.execute(
            "UPDATE corporate_filings SET local_path = ? WHERE news_id = ?",
            (local_path, news_id),
        )
        self._conn.commit()

    def get_filings(
        self, symbol: str, category: str | None = None, limit: int = 50,
    ) -> list[CorporateFiling]:
        """Get stored filings for a symbol."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM corporate_filings WHERE symbol = ? "
                "AND (category LIKE ? OR subcategory LIKE ?) "
                "ORDER BY filing_date DESC LIMIT ?",
                (symbol, f"%{category}%", f"%{category}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM corporate_filings WHERE symbol = ? "
                "ORDER BY filing_date DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [CorporateFiling(
            symbol=r["symbol"], bse_scrip_code=r["bse_scrip_code"],
            filing_date=r["filing_date"], category=r["category"],
            subcategory=r["subcategory"] or "", headline=r["headline"],
            attachment_name=r["attachment_name"], pdf_flag=r["pdf_flag"],
            file_size=r["file_size"], news_id=r["news_id"],
            local_path=r["local_path"],
        ) for r in rows]

    # -- Screener IDs cache --

    def upsert_screener_ids(self, symbol: str, company_id: str, warehouse_id: str) -> None:
        """Cache Screener.in company_id and warehouse_id for a symbol."""
        self._conn.execute(
            "INSERT INTO screener_ids (symbol, company_id, warehouse_id, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(symbol) DO UPDATE SET company_id=excluded.company_id, "
            "warehouse_id=excluded.warehouse_id, updated_at=excluded.updated_at",
            (symbol, company_id, warehouse_id),
        )
        self._conn.commit()

    def get_screener_ids(self, symbol: str) -> tuple[str, str] | None:
        """Get cached (company_id, warehouse_id) or None."""
        row = self._conn.execute(
            "SELECT company_id, warehouse_id FROM screener_ids WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        return (row["company_id"], row["warehouse_id"]) if row else None

    # -- Chart data --

    def upsert_chart_data(self, symbol: str, chart_type: str, datasets: list[dict]) -> int:
        """Store chart API datasets. Each dataset has metric, label, values."""
        count = 0
        for ds in datasets:
            metric = ds.get("metric", "")
            for date_val, value in ds.get("values", []):
                self._conn.execute(
                    "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol, chart_type, metric, date) DO UPDATE SET value=excluded.value",
                    (symbol, chart_type, metric, str(date_val), value),
                )
                count += 1
        self._conn.commit()
        return count

    def get_chart_data(self, symbol: str, chart_type: str) -> list[dict]:
        """Get stored chart data grouped by metric."""
        rows = self._conn.execute(
            "SELECT metric, date, value FROM screener_charts "
            "WHERE symbol = ? AND chart_type = ? ORDER BY metric, date",
            (symbol, chart_type),
        ).fetchall()
        from collections import defaultdict

        grouped: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            grouped[r["metric"]].append({"date": r["date"], "value": r["value"]})
        return [{"metric": m, "values": v} for m, v in grouped.items()]

    # -- Peer comparison --

    def upsert_peers(self, symbol: str, peers: list[dict]) -> int:
        """Store peer comparison data."""
        count = 0
        for p in peers:
            name = p.get("name", p.get("sno", ""))
            if not name:
                continue
            self._conn.execute(
                "INSERT INTO peer_comparison "
                "(symbol, peer_name, peer_symbol, cmp, pe, market_cap, div_yield, "
                "np_qtr, qtr_profit_var, sales_qtr, qtr_sales_var, roce) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol, peer_name) DO UPDATE SET "
                "peer_symbol=excluded.peer_symbol, "
                "cmp=excluded.cmp, pe=excluded.pe, market_cap=excluded.market_cap, "
                "div_yield=excluded.div_yield, np_qtr=excluded.np_qtr, "
                "qtr_profit_var=excluded.qtr_profit_var, sales_qtr=excluded.sales_qtr, "
                "qtr_sales_var=excluded.qtr_sales_var, roce=excluded.roce, "
                "fetched_at=datetime('now')",
                (
                    symbol,
                    name,
                    p.get("peer_symbol"),
                    p.get("cmp") or p.get("cmp_rs") or p.get("cmprs"),
                    p.get("pe") or p.get("p_e"),
                    p.get("market_cap") or p.get("market_cap_cr") or p.get("mar_caprscr"),
                    p.get("div_yield") or p.get("div_yld_pct") or p.get("div_yldpct"),
                    p.get("np_qtr") or p.get("np_qtr_cr") or p.get("np_qtrrscr"),
                    p.get("qtr_profit_var") or p.get("qtr_profit_var_pct") or p.get("qtr_profit_varpct"),
                    p.get("sales_qtr") or p.get("sales_qtr_cr") or p.get("sales_qtrrscr"),
                    p.get("qtr_sales_var") or p.get("qtr_sales_var_pct") or p.get("qtr_sales_varpct"),
                    p.get("roce") or p.get("roce_pct") or p.get("rocepct"),
                ),
            )
            count += 1
        self._conn.commit()
        return count

    def get_peers(self, symbol: str) -> list[dict]:
        """Get stored peer comparison data."""
        rows = self._conn.execute(
            "SELECT * FROM peer_comparison WHERE symbol = ? ORDER BY market_cap DESC",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Shareholder details --

    def upsert_shareholder_details(self, symbol: str, data: dict[str, list[dict]]) -> int:
        """Store individual shareholder data from Screener API."""
        count = 0
        for classification, holders in data.items():
            for holder in holders:
                name = holder.get("name", "")
                for quarter, pct in holder.get("values", {}).items():
                    if pct is None:
                        continue
                    try:
                        pct_val = float(pct)
                    except (ValueError, TypeError):
                        continue
                    self._conn.execute(
                        "INSERT INTO shareholder_detail "
                        "(symbol, classification, holder_name, quarter, percentage) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(symbol, classification, holder_name, quarter) "
                        "DO UPDATE SET percentage=excluded.percentage, fetched_at=datetime('now')",
                        (symbol, classification, name, quarter, pct_val),
                    )
                    count += 1
        self._conn.commit()
        return count

    def get_shareholder_details(
        self, symbol: str, classification: str | None = None
    ) -> list[dict]:
        """Get stored shareholder details, optionally filtered by classification."""
        if classification:
            rows = self._conn.execute(
                "SELECT * FROM shareholder_detail "
                "WHERE symbol = ? AND classification = ? "
                "ORDER BY quarter DESC, percentage DESC",
                (symbol, classification),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM shareholder_detail WHERE symbol = ? "
                "ORDER BY classification, quarter DESC, percentage DESC",
                (symbol,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Financial schedules --

    def upsert_schedules(self, symbol: str, section: str, parent: str, data: dict) -> int:
        """Store schedule (sub-item breakdown) data."""
        count = 0
        for sub_item, periods in data.items():
            if not isinstance(periods, dict):
                continue
            for period, value in periods.items():
                if value is None:
                    continue
                try:
                    val = float(str(value).replace(",", "").replace("%", ""))
                except (ValueError, TypeError):
                    continue
                self._conn.execute(
                    "INSERT INTO financial_schedules "
                    "(symbol, section, parent_item, sub_item, period, value) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol, section, parent_item, sub_item, period) "
                    "DO UPDATE SET value=excluded.value, fetched_at=datetime('now')",
                    (symbol, section, parent, sub_item, period, val),
                )
                count += 1
        self._conn.commit()
        return count

    def get_schedules(self, symbol: str, section: str | None = None) -> list[dict]:
        """Get stored schedule data, optionally filtered by section."""
        if section:
            rows = self._conn.execute(
                "SELECT * FROM financial_schedules "
                "WHERE symbol = ? AND section = ? "
                "ORDER BY parent_item, sub_item, period",
                (symbol, section),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM financial_schedules WHERE symbol = ? "
                "ORDER BY section, parent_item, sub_item, period",
                (symbol,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Company Profiles ---

    def upsert_company_profile(self, symbol: str, data: dict) -> None:
        """Insert or update company profile (about text, key points)."""
        import json as _json
        self._conn.execute(
            "INSERT INTO company_profiles (symbol, about_text, key_points_json, screener_url, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(symbol) DO UPDATE SET "
            "about_text=excluded.about_text, key_points_json=excluded.key_points_json, "
            "screener_url=excluded.screener_url, updated_at=datetime('now')",
            (
                symbol.upper(),
                data.get("about_text", ""),
                _json.dumps(data.get("key_points", []), ensure_ascii=False),
                data.get("screener_url", ""),
            ),
        )
        self._conn.commit()

    def get_company_profile(self, symbol: str) -> dict | None:
        """Get company profile. Returns dict with about_text, key_points, screener_url."""
        import json as _json
        row = self._conn.execute(
            "SELECT * FROM company_profiles WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["key_points"] = _json.loads(d.pop("key_points_json", "[]") or "[]")
        return d

    # --- Company Documents ---

    def upsert_documents(self, symbol: str, docs_dict: dict) -> int:
        """Store concall/annual report URLs from Screener documents section.

        docs_dict: output of ScreenerClient.parse_documents_from_html
        """
        count = 0
        symbol = symbol.upper()
        for concall in docs_dict.get("concalls", []):
            period = concall.get("quarter", "")
            for doc_type, key in [
                ("concall_transcript", "transcript_url"),
                ("concall_ppt", "ppt_url"),
                ("concall_recording", "recording_url"),
            ]:
                url = concall.get(key, "")
                if url and period:
                    self._conn.execute(
                        "INSERT INTO company_documents (symbol, doc_type, period, url, updated_at) "
                        "VALUES (?, ?, ?, ?, datetime('now')) "
                        "ON CONFLICT(symbol, doc_type, period) DO UPDATE SET "
                        "url=excluded.url, updated_at=datetime('now')",
                        (symbol, doc_type, period, url),
                    )
                    count += 1

        for ar in docs_dict.get("annual_reports", []):
            period = ar.get("year", "")
            url = ar.get("url", "")
            if url and period:
                self._conn.execute(
                    "INSERT INTO company_documents (symbol, doc_type, period, url, updated_at) "
                    "VALUES (?, ?, ?, ?, datetime('now')) "
                    "ON CONFLICT(symbol, doc_type, period) DO UPDATE SET "
                    "url=excluded.url, updated_at=datetime('now')",
                    (symbol, "annual_report", period, url),
                )
                count += 1

        self._conn.commit()
        return count

    def get_documents(self, symbol: str, doc_type: str | None = None) -> list[dict]:
        """Get stored company documents, optionally filtered by type."""
        if doc_type:
            rows = self._conn.execute(
                "SELECT * FROM company_documents WHERE symbol = ? AND doc_type = ? "
                "ORDER BY period DESC",
                (symbol.upper(), doc_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM company_documents WHERE symbol = ? ORDER BY doc_type, period DESC",
                (symbol.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- FMP Data --

    def upsert_fmp_dcf(self, records: list[FMPDcfValue]) -> int:
        """Insert or replace FMP DCF records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_dcf "
                "(symbol, date, dcf, stock_price) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.date, r.dcf, r.stock_price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_technical_indicators(self, records: list[FMPTechnicalIndicator]) -> int:
        """Insert or replace FMP technical indicator records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_technical_indicators "
                "(symbol, date, indicator, value) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.date, r.indicator, r.value),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_key_metrics(self, records: list[FMPKeyMetrics]) -> int:
        """Insert or replace FMP key metrics records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            warnings = _validate_row("fmp_key_metrics", r.model_dump())
            if warnings:
                _val_logger.warning("fmp_key_metrics %s/%s: %s", r.symbol, r.date, "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_key_metrics "
                "(symbol, date, revenue_per_share, net_income_per_share, "
                "operating_cash_flow_per_share, free_cash_flow_per_share, "
                "cash_per_share, book_value_per_share, tangible_book_value_per_share, "
                "shareholders_equity_per_share, interest_debt_per_share, "
                "market_cap, enterprise_value, pe_ratio, price_to_sales_ratio, "
                "pb_ratio, ev_to_sales, ev_to_ebitda, ev_to_operating_cash_flow, "
                "ev_to_free_cash_flow, earnings_yield, free_cash_flow_yield, "
                "debt_to_equity, debt_to_assets, dividend_yield, payout_ratio, "
                "roe, roa, roic, net_profit_margin_dupont, asset_turnover, "
                "equity_multiplier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.revenue_per_share, r.net_income_per_share,
                 r.operating_cash_flow_per_share, r.free_cash_flow_per_share,
                 r.cash_per_share, r.book_value_per_share, r.tangible_book_value_per_share,
                 r.shareholders_equity_per_share, r.interest_debt_per_share,
                 r.market_cap, r.enterprise_value, r.pe_ratio, r.price_to_sales_ratio,
                 r.pb_ratio, r.ev_to_sales, r.ev_to_ebitda, r.ev_to_operating_cash_flow,
                 r.ev_to_free_cash_flow, r.earnings_yield, r.free_cash_flow_yield,
                 r.debt_to_equity, r.debt_to_assets, r.dividend_yield, r.payout_ratio,
                 r.roe, r.roa, r.roic, r.net_profit_margin_dupont, r.asset_turnover,
                 r.equity_multiplier),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_financial_growth(self, records: list[FMPFinancialGrowth]) -> int:
        """Insert or replace FMP financial growth records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_financial_growth "
                "(symbol, date, revenue_growth, gross_profit_growth, ebitda_growth, "
                "operating_income_growth, net_income_growth, eps_growth, "
                "eps_diluted_growth, dividends_per_share_growth, "
                "operating_cash_flow_growth, free_cash_flow_growth, "
                "asset_growth, debt_growth, book_value_per_share_growth, "
                "revenue_growth_3y, revenue_growth_5y, revenue_growth_10y, "
                "net_income_growth_3y, net_income_growth_5y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.revenue_growth, r.gross_profit_growth,
                 r.ebitda_growth, r.operating_income_growth, r.net_income_growth,
                 r.eps_growth, r.eps_diluted_growth, r.dividends_per_share_growth,
                 r.operating_cash_flow_growth, r.free_cash_flow_growth,
                 r.asset_growth, r.debt_growth, r.book_value_per_share_growth,
                 r.revenue_growth_3y, r.revenue_growth_5y, r.revenue_growth_10y,
                 r.net_income_growth_3y, r.net_income_growth_5y),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_analyst_grades(self, records: list[FMPAnalystGrade]) -> int:
        """Insert or replace FMP analyst grade records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_analyst_grades "
                "(symbol, date, grading_company, previous_grade, new_grade) "
                "VALUES (?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.grading_company, r.previous_grade, r.new_grade),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_price_targets(self, records: list[FMPPriceTarget]) -> int:
        """Insert or replace FMP price target records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_price_targets "
                "(symbol, published_date, analyst_name, analyst_company, "
                "price_target, price_when_posted) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (r.symbol, r.published_date, r.analyst_name, r.analyst_company,
                 r.price_target, r.price_when_posted),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_fmp_dcf_latest(self, symbol: str) -> FMPDcfValue | None:
        """Get the most recent DCF value for a symbol."""
        row = self._conn.execute(
            "SELECT * FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return FMPDcfValue(
            symbol=row["symbol"], date=row["date"],
            dcf=row["dcf"], stock_price=row["stock_price"],
        )

    def get_fmp_dcf_history(self, symbol: str, limit: int = 10) -> list[FMPDcfValue]:
        """Get DCF history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPDcfValue(
            symbol=r["symbol"], date=r["date"],
            dcf=r["dcf"], stock_price=r["stock_price"],
        ) for r in rows]

    def get_fmp_technical_indicators(self, symbol: str) -> list[FMPTechnicalIndicator]:
        """Get latest value per indicator for a symbol."""
        rows = self._conn.execute(
            "SELECT t1.* FROM fmp_technical_indicators t1 "
            "INNER JOIN (SELECT symbol, indicator, MAX(date) as max_date "
            "FROM fmp_technical_indicators WHERE symbol = ? "
            "GROUP BY symbol, indicator) t2 "
            "ON t1.symbol = t2.symbol AND t1.indicator = t2.indicator "
            "AND t1.date = t2.max_date",
            (symbol,),
        ).fetchall()
        return [FMPTechnicalIndicator(
            symbol=r["symbol"], date=r["date"],
            indicator=r["indicator"], value=r["value"],
        ) for r in rows]

    def get_fmp_key_metrics(self, symbol: str, limit: int = 10) -> list[FMPKeyMetrics]:
        """Get key metrics history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_key_metrics WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPKeyMetrics(
            symbol=r["symbol"], date=r["date"],
            revenue_per_share=r["revenue_per_share"],
            net_income_per_share=r["net_income_per_share"],
            operating_cash_flow_per_share=r["operating_cash_flow_per_share"],
            free_cash_flow_per_share=r["free_cash_flow_per_share"],
            cash_per_share=r["cash_per_share"],
            book_value_per_share=r["book_value_per_share"],
            tangible_book_value_per_share=r["tangible_book_value_per_share"],
            shareholders_equity_per_share=r["shareholders_equity_per_share"],
            interest_debt_per_share=r["interest_debt_per_share"],
            market_cap=r["market_cap"], enterprise_value=r["enterprise_value"],
            pe_ratio=r["pe_ratio"], price_to_sales_ratio=r["price_to_sales_ratio"],
            pb_ratio=r["pb_ratio"], ev_to_sales=r["ev_to_sales"],
            ev_to_ebitda=r["ev_to_ebitda"],
            ev_to_operating_cash_flow=r["ev_to_operating_cash_flow"],
            ev_to_free_cash_flow=r["ev_to_free_cash_flow"],
            earnings_yield=r["earnings_yield"],
            free_cash_flow_yield=r["free_cash_flow_yield"],
            debt_to_equity=r["debt_to_equity"], debt_to_assets=r["debt_to_assets"],
            dividend_yield=r["dividend_yield"], payout_ratio=r["payout_ratio"],
            roe=r["roe"], roa=r["roa"], roic=r["roic"],
            net_profit_margin_dupont=r["net_profit_margin_dupont"],
            asset_turnover=r["asset_turnover"],
            equity_multiplier=r["equity_multiplier"],
        ) for r in rows]

    def get_fmp_financial_growth(self, symbol: str, limit: int = 10) -> list[FMPFinancialGrowth]:
        """Get financial growth history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_financial_growth WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPFinancialGrowth(
            symbol=r["symbol"], date=r["date"],
            revenue_growth=r["revenue_growth"],
            gross_profit_growth=r["gross_profit_growth"],
            ebitda_growth=r["ebitda_growth"],
            operating_income_growth=r["operating_income_growth"],
            net_income_growth=r["net_income_growth"],
            eps_growth=r["eps_growth"],
            eps_diluted_growth=r["eps_diluted_growth"],
            dividends_per_share_growth=r["dividends_per_share_growth"],
            operating_cash_flow_growth=r["operating_cash_flow_growth"],
            free_cash_flow_growth=r["free_cash_flow_growth"],
            asset_growth=r["asset_growth"], debt_growth=r["debt_growth"],
            book_value_per_share_growth=r["book_value_per_share_growth"],
            revenue_growth_3y=r["revenue_growth_3y"],
            revenue_growth_5y=r["revenue_growth_5y"],
            revenue_growth_10y=r["revenue_growth_10y"],
            net_income_growth_3y=r["net_income_growth_3y"],
            net_income_growth_5y=r["net_income_growth_5y"],
        ) for r in rows]

    def get_fmp_analyst_grades(self, symbol: str, limit: int = 20) -> list[FMPAnalystGrade]:
        """Get analyst grades for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_analyst_grades WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPAnalystGrade(
            symbol=r["symbol"], date=r["date"],
            grading_company=r["grading_company"],
            previous_grade=r["previous_grade"],
            new_grade=r["new_grade"],
        ) for r in rows]

    def get_fmp_price_targets(self, symbol: str, limit: int = 20) -> list[FMPPriceTarget]:
        """Get price targets for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_price_targets WHERE symbol = ? "
            "ORDER BY published_date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPPriceTarget(
            symbol=r["symbol"], published_date=r["published_date"],
            analyst_name=r["analyst_name"], analyst_company=r["analyst_company"],
            price_target=r["price_target"], price_when_posted=r["price_when_posted"],
        ) for r in rows]

    # -- Portfolio --

    def upsert_portfolio_holding(self, holding: PortfolioHolding) -> int:
        """Insert or replace a portfolio holding."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO portfolio_holdings "
            "(symbol, quantity, avg_cost, buy_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (holding.symbol, holding.quantity, holding.avg_cost,
             holding.buy_date, holding.notes),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_portfolio_holdings(self) -> list[PortfolioHolding]:
        """Get all portfolio holdings."""
        rows = self._conn.execute(
            "SELECT * FROM portfolio_holdings ORDER BY symbol"
        ).fetchall()
        return [PortfolioHolding(
            symbol=r["symbol"], quantity=r["quantity"],
            avg_cost=r["avg_cost"], buy_date=r["buy_date"],
            notes=r["notes"], added_at=r["added_at"],
        ) for r in rows]

    def remove_portfolio_holding(self, symbol: str) -> bool:
        """Remove a holding. Returns True if deleted."""
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM portfolio_holdings WHERE symbol = ?", (symbol,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Alerts --

    def upsert_alert(self, alert: Alert) -> int:
        """Insert a new alert. Returns the alert ID."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO alerts (symbol, condition_type, threshold, notes) "
            "VALUES (?, ?, ?, ?)",
            (alert.symbol, alert.condition_type, alert.threshold, alert.notes),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts."""
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE active = 1 ORDER BY symbol, condition_type"
        ).fetchall()
        return [Alert(
            id=r["id"], symbol=r["symbol"], condition_type=r["condition_type"],
            threshold=r["threshold"], active=bool(r["active"]),
            last_triggered=r["last_triggered"], created_at=r["created_at"],
            notes=r["notes"],
        ) for r in rows]

    def deactivate_alert(self, alert_id: int) -> bool:
        """Deactivate an alert. Returns True if found."""
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE alerts SET active = 0 WHERE id = ?", (alert_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def log_alert_trigger(self, alert_id: int, value: float | None, message: str) -> None:
        """Log an alert trigger and update last_triggered."""
        self._conn.execute(
            "INSERT INTO alert_history (alert_id, current_value, message) VALUES (?, ?, ?)",
            (alert_id, value, message),
        )
        self._conn.execute(
            "UPDATE alerts SET last_triggered = datetime('now') WHERE id = ?",
            (alert_id,),
        )
        self._conn.commit()

    def get_alert_history(self, limit: int = 20) -> list[dict]:
        """Get recent alert trigger history."""
        rows = self._conn.execute(
            "SELECT ah.*, a.symbol, a.condition_type, a.threshold "
            "FROM alert_history ah JOIN alerts a ON ah.alert_id = a.id "
            "ORDER BY ah.triggered_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── sector benchmarks ──────────────────────────────────────────

    def upsert_sector_benchmark(
        self,
        symbol: str,
        metric: str,
        subject_value: float | None,
        peer_values: list[float],
    ) -> None:
        """Insert or replace a sector benchmark row for symbol+metric."""
        peer_count = len(peer_values)
        if peer_count == 0:
            sector_median = sector_p25 = sector_p75 = sector_min = sector_max = None
            percentile = None
        else:
            sorted_vals = sorted(peer_values)
            sector_median = statistics.median(sorted_vals)
            quantiles = statistics.quantiles(sorted_vals, n=4) if peer_count >= 2 else [sorted_vals[0]] * 3
            sector_p25 = quantiles[0]
            sector_p75 = quantiles[-1]
            sector_min = sorted_vals[0]
            sector_max = sorted_vals[-1]
            if subject_value is not None:
                percentile = sum(1 for v in peer_values if v <= subject_value) / peer_count * 100
            else:
                percentile = None

        self._conn.execute(
            "INSERT OR REPLACE INTO sector_benchmarks "
            "(subject_symbol, metric, subject_value, peer_count, "
            "sector_median, sector_p25, sector_p75, sector_min, sector_max, "
            "percentile, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (symbol, metric, subject_value, peer_count,
             sector_median, sector_p25, sector_p75, sector_min, sector_max,
             percentile),
        )
        self._conn.commit()

    def get_sector_benchmark(self, symbol: str, metric: str) -> dict | None:
        """Get a single sector benchmark row."""
        row = self._conn.execute(
            "SELECT * FROM sector_benchmarks WHERE subject_symbol = ? AND metric = ?",
            (symbol, metric),
        ).fetchone()
        return dict(row) if row else None

    def get_all_sector_benchmarks(self, symbol: str) -> list[dict]:
        """Get all sector benchmark rows for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM sector_benchmarks WHERE subject_symbol = ? ORDER BY metric",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_sector_benchmarks(self, symbol: str) -> None:
        """Delete all sector benchmark rows for a symbol."""
        self._conn.execute(
            "DELETE FROM sector_benchmarks WHERE subject_symbol = ?",
            (symbol,),
        )
        self._conn.commit()

    # -- Corporate Actions --

    def upsert_corporate_actions(self, actions: list[dict]) -> int:
        """Store corporate actions."""
        count = 0
        for a in actions:
            self._conn.execute(
                "INSERT OR REPLACE INTO corporate_actions "
                "(symbol, ex_date, action_type, ratio_text, multiplier, dividend_amount, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a["symbol"], a["ex_date"], a["action_type"], a.get("ratio_text"),
                 a.get("multiplier"), a.get("dividend_amount"), a["source"]),
            )
            count += 1
        self._conn.commit()
        return count

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        """Get all corporate actions for a symbol, ordered by date desc."""
        rows = self._conn.execute(
            "SELECT * FROM corporate_actions WHERE symbol = ? ORDER BY ex_date DESC",
            (symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_split_bonus_actions(self, symbol: str) -> list[dict]:
        """Get only split and bonus actions (for adjustment factor computation).

        Deduplicates: if BSE has a bonus on a date, yfinance split on the same
        date is skipped (yfinance can't distinguish bonus from split).
        """
        rows = self._conn.execute(
            "SELECT * FROM corporate_actions WHERE symbol = ? "
            "AND action_type IN ('split', 'bonus') AND multiplier IS NOT NULL "
            "ORDER BY ex_date ASC, source ASC",
            (symbol.upper(),),
        ).fetchall()
        # Deduplicate: BSE source wins per date
        seen_dates: dict[str, str] = {}  # date -> source that claimed it
        result: list[dict] = []
        for r in rows:
            d = dict(r)
            ex = d["ex_date"]
            src = d["source"]
            if ex in seen_dates:
                # Skip yfinance if BSE already covers this date
                if src == "yfinance":
                    continue
                # If BSE arrives after yfinance, replace (shouldn't happen with ASC sort, but safe)
                if seen_dates[ex] == "yfinance" and src == "bse":
                    result = [x for x in result if x["ex_date"] != ex]
            seen_dates[ex] = src
            result.append(d)
        return result

    def upsert_estimate_revisions(self, data: dict) -> int:
        """Upsert estimate revision data (all periods for one symbol)."""
        symbol = data["symbol"]
        today = data.get("date") or __import__("datetime").date.today().isoformat()
        count = 0
        for period, trend in data.get("eps_trend", {}).items():
            rev = data.get("eps_revisions", {}).get(period, {})
            self._conn.execute(
                """INSERT INTO estimate_revisions
                   (symbol, date, period, eps_current, eps_7d_ago, eps_30d_ago, eps_60d_ago, eps_90d_ago,
                    revisions_up_7d, revisions_up_30d, revisions_down_7d, revisions_down_30d,
                    momentum_score, momentum_signal)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, date, period) DO UPDATE SET
                    eps_current=excluded.eps_current, eps_7d_ago=excluded.eps_7d_ago,
                    eps_30d_ago=excluded.eps_30d_ago, eps_60d_ago=excluded.eps_60d_ago,
                    eps_90d_ago=excluded.eps_90d_ago,
                    revisions_up_7d=excluded.revisions_up_7d, revisions_up_30d=excluded.revisions_up_30d,
                    revisions_down_7d=excluded.revisions_down_7d, revisions_down_30d=excluded.revisions_down_30d,
                    momentum_score=excluded.momentum_score, momentum_signal=excluded.momentum_signal,
                    fetched_at=datetime('now')""",
                (symbol, today, period,
                 trend.get("current"), trend.get("7d_ago"), trend.get("30d_ago"),
                 trend.get("60d_ago"), trend.get("90d_ago"),
                 rev.get("up_7d"), rev.get("up_30d"), rev.get("down_7d"), rev.get("down_30d"),
                 data.get("momentum_score"), data.get("momentum_signal")),
            )
            count += 1
        self._conn.commit()
        return count

    def get_estimate_revisions(self, symbol: str) -> list[dict]:
        """Get latest estimate revision data for all periods."""
        rows = self._conn.execute(
            """SELECT * FROM estimate_revisions
               WHERE symbol = ? AND date = (
                   SELECT MAX(date) FROM estimate_revisions WHERE symbol = ?
               ) ORDER BY period""",
            (symbol.upper(), symbol.upper()),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_quarterly_balance_sheet(self, symbol: str, rows: list[dict]) -> int:
        """Upsert quarterly balance sheet data."""
        count = 0
        for row in rows:
            warnings = _validate_row("quarterly_balance_sheet", row)
            if warnings:
                _val_logger.warning("quarterly_balance_sheet %s/%s: %s", symbol, row.get("quarter_end"), "; ".join(warnings))
            self._conn.execute(
                """INSERT INTO quarterly_balance_sheet
                   (symbol, quarter_end, total_assets, total_debt, long_term_debt,
                    stockholders_equity, cash_and_equivalents, net_debt, investments,
                    net_ppe, shares_outstanding, total_liabilities, minority_interest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, quarter_end) DO UPDATE SET
                    total_assets=excluded.total_assets, total_debt=excluded.total_debt,
                    long_term_debt=excluded.long_term_debt, stockholders_equity=excluded.stockholders_equity,
                    cash_and_equivalents=excluded.cash_and_equivalents, net_debt=excluded.net_debt,
                    investments=excluded.investments, net_ppe=excluded.net_ppe,
                    shares_outstanding=excluded.shares_outstanding, total_liabilities=excluded.total_liabilities,
                    minority_interest=excluded.minority_interest, fetched_at=datetime('now')""",
                (symbol.upper(), row["quarter_end"],
                 row.get("total_assets"), row.get("total_debt"), row.get("long_term_debt"),
                 row.get("stockholders_equity"), row.get("cash_and_equivalents"),
                 row.get("net_debt"), row.get("investments"), row.get("net_ppe"),
                 row.get("shares_outstanding"), row.get("total_liabilities"),
                 row.get("minority_interest")),
            )
            count += 1
        self._conn.commit()
        return count

    def upsert_quarterly_cash_flow(self, symbol: str, rows: list[dict]) -> int:
        """Upsert quarterly cash flow data."""
        count = 0
        for row in rows:
            warnings = _validate_row("quarterly_cash_flow", row)
            if warnings:
                _val_logger.warning("quarterly_cash_flow %s/%s: %s", symbol, row.get("quarter_end"), "; ".join(warnings))
            self._conn.execute(
                """INSERT INTO quarterly_cash_flow
                   (symbol, quarter_end, operating_cash_flow, free_cash_flow, capital_expenditure,
                    investing_cash_flow, financing_cash_flow, change_in_working_capital,
                    depreciation, dividends_paid, net_income)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, quarter_end) DO UPDATE SET
                    operating_cash_flow=excluded.operating_cash_flow, free_cash_flow=excluded.free_cash_flow,
                    capital_expenditure=excluded.capital_expenditure, investing_cash_flow=excluded.investing_cash_flow,
                    financing_cash_flow=excluded.financing_cash_flow, change_in_working_capital=excluded.change_in_working_capital,
                    depreciation=excluded.depreciation, dividends_paid=excluded.dividends_paid,
                    net_income=excluded.net_income, fetched_at=datetime('now')""",
                (symbol.upper(), row["quarter_end"],
                 row.get("operating_cash_flow"), row.get("free_cash_flow"),
                 row.get("capital_expenditure"), row.get("investing_cash_flow"),
                 row.get("financing_cash_flow"), row.get("change_in_working_capital"),
                 row.get("depreciation"), row.get("dividends_paid"), row.get("net_income")),
            )
            count += 1
        self._conn.commit()
        return count

    def get_quarterly_balance_sheet(self, symbol: str, limit: int = 8) -> list[dict]:
        """Get quarterly balance sheet data, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_balance_sheet WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_quarterly_cash_flow(self, symbol: str, limit: int = 8) -> list[dict]:
        """Get quarterly cash flow data, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_cash_flow WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Analytical Snapshot ─────────────────────────────────────────

    def upsert_analytical_snapshot(self, row: dict) -> None:
        """Upsert a single analytical snapshot row."""
        cols = [c[1] for c in self._conn.execute(
            "PRAGMA table_info(analytical_snapshot)"
        ).fetchall() if c[1] != "id"]
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO analytical_snapshot ({col_names}) VALUES ({placeholders})"
        self._conn.execute(sql, [row.get(c) for c in cols])
        self._conn.commit()

    def get_analytical_snapshot(self, symbol: str) -> dict | None:
        """Get latest analytical snapshot for a stock."""
        row = self._conn.execute(
            "SELECT * FROM analytical_snapshot WHERE symbol = ? "
            "ORDER BY computed_date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        return dict(row) if row else None

    def get_analytical_snapshots_all(self, computed_date: str | None = None) -> list[dict]:
        """Get latest snapshots for all stocks. For screening and batch operations."""
        if computed_date:
            rows = self._conn.execute(
                "SELECT * FROM analytical_snapshot WHERE computed_date = ?",
                (computed_date,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT a.* FROM analytical_snapshot a
                   INNER JOIN (
                       SELECT symbol, MAX(computed_date) as max_date
                       FROM analytical_snapshot GROUP BY symbol
                   ) b ON a.symbol = b.symbol AND a.computed_date = b.max_date"""
            ).fetchall()
        return [dict(r) for r in rows]

    def screen_by_analytics(self, filters: dict) -> list[dict]:
        """Screen stocks by analytical metrics.

        Filter keys: _min suffix (>=), _max suffix (<=), no suffix (exact match).
        Example: {"f_score_min": 7, "eq_signal": "high_quality"}
        """
        allowed = {c[1] for c in self._conn.execute(
            "PRAGMA table_info(analytical_snapshot)"
        ).fetchall()}

        conditions = []
        params = []
        for key, value in filters.items():
            if key.endswith("_min"):
                col = key[:-4]
                if col not in allowed:
                    continue
                conditions.append(f"{col} >= ?")
                params.append(value)
            elif key.endswith("_max"):
                col = key[:-4]
                if col not in allowed:
                    continue
                conditions.append(f"{col} <= ?")
                params.append(value)
            else:
                if key not in allowed:
                    continue
                conditions.append(f"{key} = ?")
                params.append(value)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""SELECT a.* FROM analytical_snapshot a
                  INNER JOIN (
                      SELECT symbol, MAX(computed_date) as max_date
                      FROM analytical_snapshot GROUP BY symbol
                  ) b ON a.symbol = b.symbol AND a.computed_date = b.max_date
                  WHERE {where}
                  ORDER BY a.composite_score DESC"""
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> FlowStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _row_to_flow(row: sqlite3.Row) -> DailyFlow:
    """Convert a database row to a DailyFlow model."""
    return DailyFlow(
        date=date.fromisoformat(row["date"]),
        category=row["category"],
        buy_value=row["buy_value"],
        sell_value=row["sell_value"],
        net_value=row["net_value"],
    )


def _rows_to_pair(rows: list[sqlite3.Row]) -> DailyFlowPair | None:
    """Convert rows for a single date into a DailyFlowPair."""
    fii = dii = None
    for row in rows:
        flow = _row_to_flow(row)
        if flow.category == "FII":
            fii = flow
        elif flow.category == "DII":
            dii = flow

    if fii is None or dii is None:
        return None

    return DailyFlowPair(date=fii.date, fii=fii, dii=dii)
