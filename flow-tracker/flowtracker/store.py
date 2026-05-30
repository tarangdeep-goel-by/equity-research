"""SQLite persistence for FII/DII daily flow data.

Unit standard (P-3B):
    Monetary aggregates: CRORES (₹1 Cr = 10M). Converted at ingestion, never in compute code.
    Per-share values:    RUPEES (price, EPS, BVPS, DPS). Use ×1e7 to convert Cr→Rs per-share.
    Counts:              RAW (shares_outstanding, volume, quantity).
    Percentages:         PERCENTAGE (25.0 = 25%). Margins, returns (ROE/ROA/ROCE), growth, yields.
    Ratios:              AS-IS (PE, PB, D/E, current_ratio, beta).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from flowtracker.models import DailyFlow, DailyFlowPair
from flowtracker.scan_models import ScanSummary
from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.store_domains import Namespace
from flowtracker.store_domains.portfolio import PortfolioMixin
from flowtracker.store_domains.flows import FlowsMixin
from flowtracker.store_domains.macro import MacroMixin
from flowtracker.store_domains.derivatives import DerivativesMixin
from flowtracker.store_domains.market_registry import MarketRegistryMixin
from flowtracker.store_domains.research import ResearchMixin
from flowtracker.store_domains.fundamentals import FundamentalsMixin
from flowtracker.store_domains.holdings import HoldingsMixin
from flowtracker.store_domains.prices import PricesMixin
from flowtracker.store_domains.valuation import ValuationMixin
from flowtracker.store_domains.us_market import UsMarketMixin, US_VALIDATION_UNIVERSE

import logging

# Shared store infrastructure (validation, derived-DII CTE, percentile) lives in
# store_domains/_shared.py so domain mixins can import it without a circular
# dependency on this module (refactor P1.4). Re-exported names below keep
# existing `store._validate_row` / `store._SHAREHOLDING_WITH_DII` references
# (and any external imports) working unchanged.
from flowtracker.store_domains._shared import (  # noqa: F401
    _SHAREHOLDING_WITH_DII,
    _VALIDATION_RULES,
    _val_logger,
    _validate_row,
    _percentile_rank,
)

_logger = logging.getLogger("flowtracker.store")


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
    net_premium_earned REAL,  -- Insurers only (₹ Cr). See _apply_insurance_headline.
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
    net_premium_earned REAL,  -- Insurers only (₹ Cr). See _apply_insurance_headline.
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

CREATE TABLE IF NOT EXISTS standalone_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    fiscal_year_end TEXT NOT NULL,
    revenue REAL,
    net_income REAL,
    total_assets REAL,
    equity_capital REAL,
    reserves REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, fiscal_year_end)
);

-- Reclassification flags for annual_financials. See flowtracker/data_quality.py
-- and plans/screener-data-discontinuity.md for the detector and rationale.
-- Each row marks a YoY break between (prior_fy, curr_fy) on a specific line.
CREATE TABLE IF NOT EXISTS data_quality_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    prior_fy TEXT NOT NULL,
    curr_fy TEXT NOT NULL,
    line TEXT NOT NULL,
    prior_val REAL NOT NULL,
    curr_val REAL NOT NULL,
    jump_pct REAL NOT NULL,
    rev_change_pct REAL NOT NULL,
    flag_type TEXT NOT NULL,   -- RECLASS or SIGN_FLIP
    severity TEXT NOT NULL,    -- HIGH / MEDIUM / LOW
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, curr_fy, line)
);
CREATE INDEX IF NOT EXISTS idx_dqf_symbol ON data_quality_flags(symbol);
CREATE INDEX IF NOT EXISTS idx_dqf_severity ON data_quality_flags(severity);

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
    eur_inr REAL,
    gbp_inr REAL,
    brent_crude REAL,
    gsec_10y REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);

-- US daily macro snapshot (US add-on). ALL-NEW table — India ``macro_daily``
-- is untouched. Treasury yields stored in percent (4.44 = 4.44%). Populated
-- from yfinance (^VIX, DX-Y.NYB, ^IRX/^FVX/^TNX/^TYX, CL=F/BZ=F/GC=F).
CREATE TABLE IF NOT EXISTS us_macro_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    vix REAL,
    dxy REAL,
    ust_3m REAL,
    ust_5y REAL,
    ust_10y REAL,
    ust_30y REAL,
    wti_crude REAL,
    brent_crude REAL,
    gold REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS idx_us_macro_daily_date ON us_macro_daily(date);

-- US monthly macro economic series (US add-on). ALL-NEW table — mirrors the
-- India ``cpi_monthly`` / ``iip_monthly`` pattern but unifies both series in
-- one table keyed by (series, period). ``series`` is 'cpi' or 'iip'. Sourced
-- from FRED (keyless fredgraph.csv): CPI = ``CPIAUCSL`` (CPI-U all items, SA,
-- 1982-84=100), Industrial Production = ``INDPRO`` (index 2017=100). ``period``
-- is 'YYYY-MM-01'; ``yoy_pct`` is computed locally (idx_t / idx_{t-12} - 1)*100.
CREATE TABLE IF NOT EXISTS us_macro_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    series TEXT NOT NULL,
    index_value REAL,
    yoy_pct REAL,
    source TEXT NOT NULL DEFAULT 'FRED',
    source_url TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(series, period)
);
CREATE INDEX IF NOT EXISTS idx_us_macro_monthly_series_period
    ON us_macro_monthly(series, period DESC);

-- Daily index-level valuation snapshots (PE / PB / Dividend Yield) sourced
-- from niftyindices.com. Populated by `flowtrack indexpe fetch|backfill`.
-- Used by the `percentile` command to answer regime questions like
-- "where does today's Nifty Smallcap 250 PE sit vs the 10-year distribution".
CREATE TABLE IF NOT EXISTS index_valuation_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    index_name TEXT NOT NULL,
    pe REAL,
    pb REAL,
    dividend_yield REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, index_name)
);
CREATE INDEX IF NOT EXISTS idx_index_valuation_idx_date
    ON index_valuation_daily(index_name, date);

-- Weekly RBI WSS system credit/deposit aggregates. WSS publishes Friday;
-- Section 4 (SCB Business) is keyed to fortnight-end (15th + last calendar day).
-- We use the WSS publication date as PK because that's the unambiguous
-- release identity; ``as_of_date`` records the fortnight the values cover.
CREATE TABLE IF NOT EXISTS macro_system_credit (
    release_date TEXT PRIMARY KEY,
    as_of_date TEXT,
    aggregate_deposits_cr REAL,
    bank_credit_cr REAL,
    deposit_growth_yoy REAL,
    credit_growth_yoy REAL,
    non_food_credit_growth_yoy REAL,
    cd_ratio REAL,
    m3_growth_yoy REAL,
    source TEXT NOT NULL DEFAULT 'RBI_WSS',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_macro_system_credit_as_of ON macro_system_credit(as_of_date);

-- Daily market-breadth metrics per index. Computed from `daily_stock_data`
-- + `index_constituents` (no external HTTP). Each row is one (date, index)
-- pair. See `breadth_compute.py` for the math.
CREATE TABLE IF NOT EXISTS market_breadth_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    index_name TEXT NOT NULL,
    total INTEGER NOT NULL,
    pct_above_200dma REAL,
    advance INTEGER NOT NULL,
    decline INTEGER NOT NULL,
    unchanged INTEGER NOT NULL,
    new_52w_highs INTEGER NOT NULL,
    new_52w_lows INTEGER NOT NULL,
    ad_ratio REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, index_name)
);
CREATE INDEX IF NOT EXISTS idx_market_breadth_date ON market_breadth_daily(date);
CREATE INDEX IF NOT EXISTS idx_market_breadth_index ON market_breadth_daily(index_name);

CREATE TABLE IF NOT EXISTS index_daily_prices (
    date TEXT NOT NULL,
    index_ticker TEXT NOT NULL,
    close REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, index_ticker)
);
CREATE INDEX IF NOT EXISTS idx_index_daily_prices_ticker ON index_daily_prices(index_ticker);
CREATE INDEX IF NOT EXISTS idx_index_daily_prices_date ON index_daily_prices(date);

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

-- Daily per-scheme NAV history sourced from mfapi.in. The curated
-- universe (~30 equity schemes, see ``flowtracker.mf_nav_client``)
-- covers large/mid/small/flexi/multi/focused/ELSS/value/contra/index/
-- sectoral categories. NAVs are per-unit rupee values; ``scheme_name``
-- is denormalised so a single-table query suffices for display.
CREATE TABLE IF NOT EXISTS mf_scheme_nav_daily (
    scheme_code INTEGER NOT NULL,
    date TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    nav REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (scheme_code, date)
);
CREATE INDEX IF NOT EXISTS idx_mf_nav_date ON mf_scheme_nav_daily(date);

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

-- Historical Analog Agent (Sprint 1): per-(symbol, quarter-end) feature
-- fingerprints used as the retrieval space for finding "similar setups" in
-- the last 10 years. Populated by scripts/materialize_analog_states.py.
CREATE TABLE IF NOT EXISTS historical_states (
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    -- Valuation
    pe_trailing REAL,
    pe_percentile_10y REAL,
    -- Quality
    roce_current REAL,
    roce_3yr_delta REAL,
    revenue_cagr_3yr REAL,
    opm_trend REAL,
    -- Ownership
    promoter_pct REAL,
    fii_pct REAL,
    fii_delta_2q REAL,
    mf_pct REAL,
    mf_delta_2q REAL,
    pledge_pct REAL,
    -- Technical
    price_vs_sma200 REAL,
    delivery_pct_6m REAL,
    rsi_14 REAL,
    -- Categorical
    industry TEXT,
    mcap_bucket TEXT,
    -- Listing age + backfill marker (Part 1.5): listed_days is the gap
    -- between the ticker's earliest bhavcopy row and quarter_end; when
    -- small, any multi-year accounting feature (roce_3yr_delta,
    -- revenue_cagr_3yr) reflects provider backfill into a pre-listing
    -- period, not lived market performance. is_backfilled flags that.
    listed_days INTEGER,
    is_backfilled INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, quarter_end)
);
CREATE INDEX IF NOT EXISTS idx_historical_states_ind ON historical_states(industry, mcap_bucket);
CREATE INDEX IF NOT EXISTS idx_historical_states_qtr ON historical_states(quarter_end);

-- Historical Analog Agent (Sprint 1): forward returns aligned to
-- historical_states rows. Reads daily_stock_data.adj_close (Sprint 0
-- split/bonus adjusted) so cliffs don't pollute analog outcomes.
CREATE TABLE IF NOT EXISTS analog_forward_returns (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    return_3m_pct REAL,
    return_6m_pct REAL,
    return_12m_pct REAL,
    excess_3m_vs_sector REAL,
    excess_12m_vs_sector REAL,
    excess_12m_vs_nifty REAL,
    outcome_label TEXT,  -- recovered | sideways | blew_up | null (no 12m data)
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, as_of_date)
);

-- Historical Analog (PR-13, issue #23): symbols absent from the live universe
-- (delisted, demerged, suspended, parked) so cohort base rates aren't biased
-- toward the current index. Populated by detect_delisted_from_gaps() (≥180d
-- bhavcopy gap) and consumed by materialize_analog_states.py --include-delisted.
CREATE TABLE IF NOT EXISTS delisted_symbols (
    symbol TEXT PRIMARY KEY,
    last_active_date TEXT,
    observations INTEGER,
    reason TEXT,
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Historical Analog (PR-13, issue #23): day-over-day price moves >40% with no
-- matching corporate_actions row (±2 trading days). Manual triage queue —
-- written by scripts/reconcile_price_cliffs.py, consumed by humans.
CREATE TABLE IF NOT EXISTS unresolved_cliffs (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    prev_close REAL,
    close REAL,
    return_pct REAL,
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, trade_date)
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

    -- Forensic Checks (Batch 1)
    forensic_cfo_ebitda_5y REAL,
    forensic_cfo_ebitda_signal TEXT,
    forensic_dep_volatility REAL,
    forensic_dep_signal TEXT,
    forensic_cash_yield_pct REAL,
    forensic_cash_yield_signal TEXT,
    forensic_cwip_3y_avg REAL,
    forensic_cwip_signal TEXT,

    -- Improvement Metrics (Batch 1)
    improvement_greatness_pct REAL,
    improvement_greatness_class TEXT,
    improvement_capex_prod_ratio REAL,

    -- Capital Discipline (Batch 1)
    capital_roce_reinvest_signal TEXT,
    capital_sustainable_growth_3y REAL,
    capital_equity_dilution_pct REAL,
    capital_equity_dilution_signal TEXT,

    -- Incremental ROCE (Batch 2)
    incremental_roce_3y REAL,
    incremental_roce_3y_signal TEXT,
    incremental_roce_5y REAL,

    -- Altman Z-Score (Batch 2)
    altman_zscore REAL,
    altman_zone TEXT,

    -- Working Capital (Batch 2)
    wc_ccc_direction TEXT,
    wc_signal TEXT,

    -- Operating Leverage (Batch 2)
    dol_avg_3y REAL,
    dol_signal TEXT,

    -- FCF Yield (Batch 2)
    fcf_yield_pct REAL,
    fcf_yield_signal TEXT,
    fcf_pat_ratio REAL,

    -- Tax Rate Analysis (Batch 2)
    tax_avg_3y_etr REAL,
    tax_signal TEXT,

    -- Receivables Quality (Batch 2)
    recv_quality_signal TEXT,

    -- WACC Parameters
    wacc REAL,
    ke REAL,
    kd_pretax REAL,
    beta_blume REAL,
    beta_raw REAL,
    beta_r_squared REAL,
    terminal_growth REAL,
    wacc_flags TEXT,

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

CREATE TABLE IF NOT EXISTS listed_subsidiaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_symbol TEXT NOT NULL,
    sub_symbol TEXT NOT NULL,
    sub_name TEXT NOT NULL,
    parent_ownership_pct REAL NOT NULL,
    relationship TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(parent_symbol, sub_symbol)
);

CREATE TABLE IF NOT EXISTS company_snapshot (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    industry TEXT,
    cmp REAL,
    market_cap REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb REAL,
    ev_ebitda REAL,
    peg REAL,
    div_yield REAL,
    operating_margin REAL,
    net_margin REAL,
    roe REAL,
    roa REAL,
    roce REAL,
    roic REAL,
    fcf_yield REAL,
    revenue_growth REAL,
    earnings_growth REAL,
    sales_qtr REAL,
    qtr_sales_var REAL,
    np_qtr REAL,
    qtr_profit_var REAL,
    beta REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    high_52w REAL,
    low_52w REAL,
    promoter_holding REAL,
    promoter_pledge REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    screener_updated_at TEXT,
    yfinance_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS peer_links (
    symbol TEXT NOT NULL,
    peer_symbol TEXT NOT NULL,
    score REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, peer_symbol)
);

-- F&O ingestion (Sprint 2): per-contract EOD snapshot from NSE bhavcopy.
-- Strike uses -1 sentinel and option_type '' sentinel because SQLite PK
-- cannot contain NULLs; futures rows always upsert with those sentinels.
CREATE TABLE IF NOT EXISTS fno_contracts (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    instrument TEXT NOT NULL,           -- FUTSTK / OPTSTK / FUTIDX / OPTIDX
    expiry_date TEXT NOT NULL,
    strike REAL NOT NULL DEFAULT -1,    -- -1 sentinel for futures (no strike)
    option_type TEXT NOT NULL DEFAULT '',  -- CE / PE / '' (for futures)
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    settle_price REAL,
    contracts_traded INTEGER DEFAULT 0,
    turnover_cr REAL DEFAULT 0,
    open_interest INTEGER DEFAULT 0,
    change_in_oi INTEGER DEFAULT 0,
    implied_volatility REAL,
    PRIMARY KEY (trade_date, symbol, instrument, expiry_date, strike, option_type)
);
CREATE INDEX IF NOT EXISTS ix_fno_symbol_date ON fno_contracts(symbol, trade_date);
CREATE INDEX IF NOT EXISTS ix_fno_expiry ON fno_contracts(expiry_date);
CREATE INDEX IF NOT EXISTS ix_fno_instrument ON fno_contracts(instrument);

-- F&O ingestion (Sprint 2): participant-wise long/short OI across instrument
-- categories (FII/DII/Pro/Client × idx_fut/idx_opt_ce/.../stk_opt_pe).
CREATE TABLE IF NOT EXISTS fno_participant_oi (
    trade_date TEXT NOT NULL,
    participant TEXT NOT NULL,          -- FII / DII / Pro / Client
    instrument_category TEXT NOT NULL,  -- idx_fut / idx_opt_ce / idx_opt_pe / stk_fut / stk_opt_ce / stk_opt_pe
    long_oi INTEGER DEFAULT 0,
    short_oi INTEGER DEFAULT 0,
    long_turnover_cr REAL,
    short_turnover_cr REAL,
    PRIMARY KEY (trade_date, participant, instrument_category)
);

-- F&O ingestion (Sprint 2): F&O-eligible symbol universe (quarterly refresh).
CREATE TABLE IF NOT EXISTS fno_universe (
    symbol TEXT PRIMARY KEY,
    eligible_since TEXT NOT NULL,
    last_verified TEXT NOT NULL
);

-- Wave 5 P2 — granular shareholding sub-categories from the BSE/NSE XBRL.
-- Augments the canonical 7-bucket `shareholding` table with the rich detail
-- the XBRL exposes but the flat table flattens away (Retail vs HNI inside
-- Public, FPI Cat-I/II inside FII, CustodianOrDRHolder for ADR/GDR holdings,
-- Employee Benefit Trust / IEPF, etc.). All `*_pct` fields are stored in
-- percent form (12.5 = 12.5%). `dr_underlying_shares` is the raw count of
-- equity shares represented by ADRs/GDRs — pulled from
-- NumberOfSharesUnderlyingOutstandingDepositoryReceipts under
-- CustodianOrDRHolder context.
CREATE TABLE IF NOT EXISTS shareholding_breakdown (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    -- Public sub-breakdown
    retail_pct REAL,
    hni_pct REAL,
    bodies_corporate_pct REAL,
    nri_pct REAL,
    -- FPI sub-breakdown
    fpi_cat1_pct REAL,
    fpi_cat2_pct REAL,
    -- Public institutional sub-breakdown
    banks_pct REAL,
    other_financial_institutions_pct REAL,
    nbfc_pct REAL,
    provident_pension_funds_pct REAL,
    venture_capital_funds_pct REAL,
    sovereign_wealth_domestic_pct REAL,
    sovereign_wealth_foreign_pct REAL,
    -- Other foreign / other domestic
    foreign_companies_pct REAL,
    foreign_nationals_pct REAL,
    foreign_dr_holder_pct REAL,
    other_foreign_pct REAL,
    other_indian_pct REAL,
    -- Misc
    employee_benefit_trust_pct REAL,
    iepf_pct REAL,
    -- ADR/GDR specifics
    dr_underlying_shares INTEGER,
    custodian_total_shares INTEGER,
    -- Bookkeeping
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

-- Wave 5 P2 — ESOP pool size disclosure surfaced from AR Notes to Financial
-- Statements / Directors' Report / Schedule III ESOP disclosure. One row
-- per (symbol, fiscal_year). Total options outstanding is the headline pool
-- size; pct_of_paidup_capital captures dilution potential. `plans_json`
-- stores the per-plan detail (plan name, year introduced, options
-- authorized/granted/vested/exercised/lapsed) for drill-down.
CREATE TABLE IF NOT EXISTS ar_esop_summary (
    symbol TEXT NOT NULL,
    fiscal_year TEXT NOT NULL,            -- "FY25"
    total_plans INTEGER,                  -- # of distinct ESOP/RSU schemes active
    options_outstanding REAL,             -- end-of-FY pool (raw count, not Cr)
    options_outstanding_pct_paidup REAL,  -- pool / paid-up shares × 100
    options_granted_fy REAL,              -- granted during the FY
    options_exercised_fy REAL,            -- exercised during the FY
    options_lapsed_fy REAL,               -- forfeited / lapsed during the FY
    weighted_avg_exercise_price REAL,     -- weighted-avg strike of outstanding
    plans_json TEXT,                      -- JSON array of per-plan dicts
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, fiscal_year)
);

-- Wave 5 Strategy 2 — restated 5/10-year financial highlights extracted
-- from the company's AR. Schedule III mandates restatement of prior years
-- when bucketing changes, so this table is internally consistent and is
-- the canonical trend source preferred over Screener's as-reported series.
-- See plans/screener-data-discontinuity.md and
-- flowtracker/research/five_year_parser.py.
--
-- Monetary values in **crores** (project standard). Per-share in rupees.
-- num_shares in millions. fy_end is canonical "YYYY-03-31" (Indian FY close).
-- source_ar_fy records which AR ("FY25") supplied this row — newer ARs
-- supersede older ones when both contain the same fy_end (PK collision
-- on (symbol, fy_end) → INSERT OR REPLACE writes the newer FY's value).
CREATE TABLE IF NOT EXISTS ar_five_year_summary (
    symbol TEXT NOT NULL,
    fy_end TEXT NOT NULL,                 -- canonical "2025-03-31"
    revenue REAL,
    operating_profit REAL,
    pat REAL,
    eps REAL,
    net_worth REAL,
    total_assets REAL,
    borrowings REAL,
    cfo REAL,
    capex REAL,
    dividend_per_share REAL,
    num_shares REAL,                      -- millions of shares
    source_ar_fy TEXT,                    -- "FY25" — which AR this row came from
    raw_unit TEXT,                        -- "crore" / "million" / "billion" / "lakh"
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, fy_end)
);
CREATE INDEX IF NOT EXISTS idx_ar_five_year_summary_symbol
    ON ar_five_year_summary(symbol);

-- Wave 5 P2 — manual override / seed table for ADR/GDR outstanding when
-- XBRL data is unavailable (older filings) or when an analyst wants to
-- record a specific as-of-date measurement (e.g. depositary bank's monthly
-- position report). Consulted by `get_adr_gdr` BEFORE the XBRL/AR fallback
-- chain. Use cases:
--   1. Seeding a known value before XBRL ingestion is wired (HDFCBANK FY26).
--   2. Recording the latest BNY Mellon / DB Trust position report (monthly
--      cadence) for symbols where the SEBI quarterly XBRL lags.
CREATE TABLE IF NOT EXISTS adr_gdr_outstanding (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,                  -- "2025-03-31"
    listed_on TEXT,                            -- "NYSE", "LSE", "Luxembourg" — comma-separated for dual-listed
    sponsor_bank TEXT,                         -- "BNY Mellon", "Citi", "Deutsche Bank", "JP Morgan"
    adr_ratio TEXT,                            -- "1 ADR = 3 equity shares" (free-text — formats vary)
    units_outstanding REAL,                    -- # of ADR/GDR units (NOT underlying equity shares)
    underlying_shares_outstanding REAL,        -- # of equity shares represented by all ADRs/GDRs
    pct_of_total_equity REAL,                  -- underlying / total equity × 100
    source TEXT NOT NULL,                      -- "XBRL_CustodianOrDRHolder", "BNY_Mellon_position_report",
                                               -- "FY25_AR_notes", "manual_seed"
    notes TEXT,                                -- free-text caveat / data_quality_note
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, as_of_date)
);

-- Directory of Indian-issuer Depositary Receipt programs (ADR/GDR/ADS) with
-- custodian and conversion-ratio metadata. This is the *qualitative* counterpart
-- to ``adr_gdr_outstanding`` (which holds quantitative per-date holdings).
-- Populated by ``flowtracker.adr_client`` from a curated seed JSON because the
-- public depositary-bank directories are JavaScript-rendered and not scrape-friendly.
-- ``nse_symbol`` is intentionally nullable — many DR programs (HDB, IBN, RDY)
-- trade under a different US ticker and the NSE-side mapping is curated by hand.
CREATE TABLE IF NOT EXISTS adr_programs (
    nse_symbol TEXT,                           -- "INFY", "ICICIBANK" or NULL if unmapped
    company_name TEXT NOT NULL,                -- "Infosys Limited"
    us_ticker TEXT,                            -- "INFY", "HDB", "IBN" — may be NULL for unsponsored
    program_type TEXT NOT NULL,                -- "ADR" / "GDR" / "ADS"
    sponsorship TEXT,                          -- "sponsored" / "unsponsored"
    depositary TEXT,                           -- "BNY Mellon" / "Citi" / "Deutsche Bank" / "JPMorgan"
    ratio TEXT,                                -- "1 ADR = 1 ord. share" — free-text, no parsing
    country TEXT NOT NULL DEFAULT 'India',
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (company_name, us_ticker)
);
CREATE INDEX IF NOT EXISTS idx_adr_programs_nse_symbol
    ON adr_programs(nse_symbol);

-- 2026-04-29 (feat/strategy2-ops): live-fetch FDA inspection / drug-enforcement
-- records sourced from openFDA `/drug/enforcement.json`. Distinct from the
-- CSV-seed `FDAInspection` model (NAI/VAI/OAI inspection-outcome taxonomy)
-- which has its own separate persistence path. This table holds the public
-- recall feed which is the closest free proxy for USFDA compliance signal
-- on Indian pharma names (SUNPHARMA, DRREDDY, CIPLA, etc.). PK columns
-- (fei_number, inspection_date) use empty-string sentinels rather than
-- NULL so SQLite uniqueness actually constrains duplicate upserts.
CREATE TABLE IF NOT EXISTS fda_inspections (
    symbol TEXT NOT NULL,
    firm_name TEXT NOT NULL,
    fei_number TEXT NOT NULL DEFAULT '',
    inspection_date TEXT NOT NULL DEFAULT '',
    classification TEXT,
    product_area TEXT,
    country TEXT,
    posted_date TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, fei_number, inspection_date)
);
CREATE INDEX IF NOT EXISTS idx_fda_inspections_symbol
    ON fda_inspections(symbol, inspection_date DESC);

-- 2026-05-26 (feat/surveillance): regulatory surveillance flags fetched from
-- NSE ASM/GSM JSON endpoints and BSE ESM (HTML/JSON, best-effort). One row per
-- (symbol, alert_type, exchange, effective_date) — the same symbol can carry
-- multiple concurrent flags (e.g. NSE long-term ASM Stage I plus NSE short-term
-- ASM Stage II) so the uniqueness key spans all four. ``stage`` and ``reason``
-- are nullable because BSE's feed routinely omits both.
CREATE TABLE IF NOT EXISTS surveillance_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,                -- "ASM" / "ESM" / "GSM"
    stage TEXT,                              -- "Stage I" / "I" / etc.
    exchange TEXT NOT NULL,                  -- "NSE" / "BSE"
    effective_date TEXT NOT NULL,            -- ISO YYYY-MM-DD
    reason TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (symbol, alert_type, exchange, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_surveillance_flags_symbol
    ON surveillance_flags(symbol);

-- 2026-05-26 (feat/ipo-pipeline): IPO + SME pipeline tracker.
-- Three tables follow the calendar/snapshot/event split — issuer_name is
-- the join key across them because NSE assigns a listed symbol only at the
-- listing event, not at the upcoming/current stage. Use cases:
--   * Sandeep flagged Jio Platforms (~₹55,000 cr) as an upcoming
--     ecosystem-repricer event — populates ipo_calendar.
--   * Baid flagged dubious-IPO oversubscription as a bull-top indicator —
--     populates ipo_subscription (look at retail_times / nii_times spikes).
-- UNIQUE(issuer_name, open_date) lets re-fetches idempotently replace stale
-- calendar rows without dupe-explosion when NSE shifts the open date.
CREATE TABLE IF NOT EXISTS ipo_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer_name TEXT NOT NULL,
    symbol TEXT,
    segment TEXT NOT NULL,                  -- "MAIN" | "SME"
    exchange TEXT NOT NULL,                 -- "NSE" | "BSE"
    open_date TEXT,
    close_date TEXT,
    listing_date TEXT,
    price_band_low REAL,
    price_band_high REAL,
    issue_size_cr REAL,
    lot_size INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(issuer_name, open_date)
);
CREATE INDEX IF NOT EXISTS idx_ipo_calendar_open
    ON ipo_calendar(open_date);
CREATE INDEX IF NOT EXISTS idx_ipo_calendar_segment
    ON ipo_calendar(segment, exchange);

CREATE TABLE IF NOT EXISTS ipo_subscription (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer_name TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    qib_times REAL,
    nii_times REAL,
    retail_times REAL,
    employee_times REAL,
    total_times REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(issuer_name, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_ipo_subscription_issuer
    ON ipo_subscription(issuer_name, as_of_date DESC);

CREATE TABLE IF NOT EXISTS ipo_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    listing_date TEXT NOT NULL,
    listing_price REAL,
    listing_day_close REAL,
    listing_pop_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, listing_date)
);
CREATE INDEX IF NOT EXISTS idx_ipo_listings_date
    ON ipo_listings(listing_date DESC);

-- Monthly GST (Goods & Services Tax) collections, sourced from the CBIC
-- monthly press release (mirrored by PIB and the GST Council). One row per
-- calendar collection month; the headline ``gross_collection_cr`` is the
-- fastest real-time proxy for nominal GDP / consumption in India and is
-- consumed by the macro agent for the "GST trend" macro signal. All
-- monetary fields are in ₹ crore (project-wide unit standard). The
-- ``period`` is the COLLECTION month (e.g. ``"2025-04"`` for April 2025),
-- NOT the release month — the April figure is published 1 May.
-- All numeric columns are nullable so a defensive parser can persist
-- partial rows when source layout drifts; downstream queries surface gaps
-- rather than rows being silently dropped.
CREATE TABLE IF NOT EXISTS gst_collections_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,                      -- "YYYY-MM" — collection month, not release month
    gross_collection_cr REAL,
    cgst_cr REAL,
    sgst_cr REAL,
    igst_cr REAL,
    cess_cr REAL,
    domestic_cr REAL,
    imports_cr REAL,
    growth_yoy_pct REAL,                       -- headline YoY% as published by CBIC
    source_url TEXT,                           -- CBIC PDF / PIB / GST Council URL for traceability
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(period)
);
CREATE INDEX IF NOT EXISTS idx_gst_collections_period
    ON gst_collections_monthly(period DESC);

-- CPI (Consumer Price Index) monthly inflation. Published by MoSPI on the 12th
-- of each month for the prior month (e.g. April 2025 CPI released 12 May 2025).
-- ``period`` is the data month ("YYYY-MM"), NOT the release month. ``cpi_index``
-- is the headline All-India CPI (Combined) index level; ``yoy_pct`` is the
-- year-on-year headline inflation. Seeded from FRED's OECD-sourced mirror
-- (`INDCPIALLMINMEI`) which goes back to 1957; live re-fetch is supported via
-- ``cpi fetch --source-url`` (point at MoSPI PDF / FRED CSV).
CREATE TABLE IF NOT EXISTS cpi_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    cpi_index REAL,
    yoy_pct REAL,
    source TEXT NOT NULL DEFAULT 'seed',
    source_url TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(period)
);
CREATE INDEX IF NOT EXISTS idx_cpi_monthly_period
    ON cpi_monthly(period DESC);

-- IIP (Index of Industrial Production) monthly. Published by MoSPI on the 12th
-- of each month for two months prior (one-month publication lag). ``iip_index``
-- is the general (all-sectors) IIP level (base 2011-12=100); ``yoy_pct`` is
-- YoY growth. Seeded from FRED `INDPROINDMISMEI`; live re-fetch via
-- ``iip fetch --source-url``.
CREATE TABLE IF NOT EXISTS iip_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    iip_index REAL,
    yoy_pct REAL,
    source TEXT NOT NULL DEFAULT 'seed',
    source_url TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(period)
);
CREATE INDEX IF NOT EXISTS idx_iip_monthly_period
    ON iip_monthly(period DESC);

-- PMI (Purchasing Managers' Index) Services + Manufacturing monthly.
-- Published by S&P Global on the 1st-3rd of each month for the prior month.
-- ``services_pmi`` and ``manufacturing_pmi`` are both >50 = expansion,
-- <50 = contraction. No clean free API; seeded from public press releases
-- (last ~10 years). Live re-fetch via ``pmi fetch --source-url`` (point at
-- the S&P Global press release for the month).
CREATE TABLE IF NOT EXISTS pmi_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    services_pmi REAL,
    manufacturing_pmi REAL,
    source TEXT NOT NULL DEFAULT 'seed',
    source_url TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(period)
);
CREATE INDEX IF NOT EXISTS idx_pmi_monthly_period
    ON pmi_monthly(period DESC);
CREATE TABLE IF NOT EXISTS symbol_registry (
    symbol             TEXT NOT NULL,
    market             TEXT NOT NULL DEFAULT 'NSE',
    isin               TEXT,
    company_name       TEXT,
    currency           TEXT NOT NULL DEFAULT 'INR',
    fiscal_year_system TEXT NOT NULL DEFAULT 'APR_MAR',
    sector             TEXT,
    gics               TEXT,
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, market)
);
CREATE INDEX IF NOT EXISTS idx_symbol_registry_market ON symbol_registry(market);

-- ===========================================================================
-- US add-on (Phase 3) — ALL-NEW us_* tables. US data lives ONLY here; India
-- tables gain ZERO new rows. Each table carries market (default 'NASDAQ') from
-- day one and a composite UNIQUE that includes market. Monetary values are in
-- USD millions (market magnitude_divisor = 1e6); per-share / price values are
-- raw USD; percentages are in percent form (25.0 = 25%). symbol_registry
-- (PK symbol, market) is the cross-market hub; symbol may be derived from a
-- CIK/CUSIP when no live ticker is mapped (institutional_holdings).
-- ===========================================================================
CREATE TABLE IF NOT EXISTS us_daily_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    adj_close REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, date)
);
CREATE INDEX IF NOT EXISTS idx_us_daily_prices_symbol ON us_daily_prices(symbol, market);
CREATE INDEX IF NOT EXISTS idx_us_daily_prices_date ON us_daily_prices(date);

CREATE TABLE IF NOT EXISTS us_annual_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    fiscal_year INTEGER NOT NULL,            -- calendar year (EDGAR fiscal year)
    revenue REAL,
    net_income REAL,
    total_assets REAL,
    total_equity REAL,
    total_debt REAL,
    total_cash REAL,
    eps REAL,
    operating_cash_flow REAL,
    free_cash_flow REAL,
    shares_outstanding REAL,
    -- Phase 3.5b: wider native US storage (USD millions unless noted).
    fiscal_year_end TEXT,                    -- FY-end date string YYYY-MM-DD
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    interest REAL,
    profit_before_tax REAL,
    tax REAL,
    operating_profit REAL,
    depreciation REAL,
    num_shares REAL,                         -- raw diluted share count (not millions)
    net_block REAL,
    cwip REAL,
    cash_and_bank REAL,
    receivables REAL,
    inventory REAL,
    other_liabilities REAL,
    cfi REAL,                                -- cash flow from investing
    cff REAL,                                -- cash flow from financing
    rnd_expense REAL,                        -- US-specific
    stock_based_comp REAL,                   -- US-specific
    sga REAL,                                -- US-specific
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, fiscal_year)
);
CREATE INDEX IF NOT EXISTS idx_us_annual_financials_symbol ON us_annual_financials(symbol, market);

CREATE TABLE IF NOT EXISTS us_quarterly_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    quarter_end TEXT NOT NULL,               -- ISO date
    fiscal_year INTEGER,
    fiscal_period TEXT,                      -- Q1 / Q2 / Q3 / Q4 / FY
    revenue REAL,
    net_income REAL,
    eps REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, quarter_end)
);
CREATE INDEX IF NOT EXISTS idx_us_quarterly_financials_symbol ON us_quarterly_financials(symbol, market);

CREATE TABLE IF NOT EXISTS us_valuation_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    date TEXT NOT NULL,
    price REAL,
    market_cap REAL,
    enterprise_value REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb REAL,
    dividend_yield REAL,
    beta REAL,
    total_cash REAL,
    total_debt REAL,
    free_cash_flow REAL,
    operating_margin REAL,
    net_margin REAL,
    roe REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, date)
);
CREATE INDEX IF NOT EXISTS idx_us_valuation_snapshot_symbol ON us_valuation_snapshot(symbol, market);

CREATE TABLE IF NOT EXISTS us_consensus_estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    date TEXT NOT NULL,
    target_mean REAL,
    target_median REAL,
    target_high REAL,
    target_low REAL,
    num_analysts INTEGER,
    recommendation TEXT,
    forward_pe REAL,
    forward_eps REAL,
    eps_current_year REAL,
    eps_next_year REAL,
    earnings_growth REAL,
    current_price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, date)
);
CREATE INDEX IF NOT EXISTS idx_us_consensus_estimates_symbol ON us_consensus_estimates(symbol, market);

CREATE TABLE IF NOT EXISTS us_insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    filing_date TEXT,
    transaction_date TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    owner_title TEXT,
    transaction_code TEXT NOT NULL,          -- Form 4 code: P / S / A / etc.
    shares REAL NOT NULL,
    price_per_share REAL,
    value REAL,
    shares_owned_after REAL,
    is_director INTEGER,
    is_officer INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, transaction_date, owner_name, transaction_code, shares)
);
CREATE INDEX IF NOT EXISTS idx_us_insider_transactions_symbol ON us_insider_transactions(symbol, market);

CREATE TABLE IF NOT EXISTS us_institutional_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,                    -- may be the CUSIP string if unmapped
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    cusip TEXT,
    manager_name TEXT,
    manager_cik TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    shares REAL,
    value_usd REAL,
    investment_discretion TEXT,
    put_call TEXT NOT NULL DEFAULT '',       -- '' sentinel for plain long; SQLite UNIQUE rejects NULL
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, market, manager_cik, quarter_end, put_call)
);
CREATE INDEX IF NOT EXISTS idx_us_institutional_holdings_symbol ON us_institutional_holdings(symbol, market);
CREATE INDEX IF NOT EXISTS idx_us_institutional_holdings_cik ON us_institutional_holdings(manager_cik);

-- Denormalized per-company snapshot for US listings — the single source of
-- truth for US peers / benchmarks / valuation-matrix, mirroring the market-
-- relevant subset of the India `company_snapshot` table plus market/currency.
-- India-only fields (promoter_holding/pledge/sales_qtr/qtr_var) are omitted.
-- Built by research/us_snapshot_builder.py from us_valuation_snapshot +
-- yfinance .info + us_annual_financials. Monetary aggregates are USD millions;
-- margins/returns/growth are percent form; ratios (pe/pb/peg/beta/d-e) are raw.
CREATE TABLE IF NOT EXISTS us_company_snapshot (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'NASDAQ',
    currency TEXT NOT NULL DEFAULT 'USD',
    name TEXT,
    industry TEXT,
    cmp REAL,
    market_cap REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb REAL,
    ev_ebitda REAL,
    peg REAL,
    div_yield REAL,
    operating_margin REAL,
    net_margin REAL,
    roe REAL,
    roa REAL,
    roce REAL,
    roic REAL,
    fcf_yield REAL,
    revenue_growth REAL,
    earnings_growth REAL,
    beta REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    high_52w REAL,
    low_52w REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(symbol, market)
);
CREATE INDEX IF NOT EXISTS idx_us_company_snapshot_market ON us_company_snapshot(market);
"""


# --- Multi-market dimension (WS1) --------------------------------------------
# Tables keyed to a single equity symbol that gain a stored `market` column.
# Country-macro / industry-aggregate tables and config/cache/audit tables are
# intentionally EXCLUDED (they are not per-symbol equity data). `symbol_registry`
# itself is excluded (it already carries market in its PK).
_MARKET_COLUMN_TABLES: tuple[str, ...] = (
    "shareholding",
    "index_constituents",
    "promoter_pledge",
    "commodity_prices",
    "quarterly_results",
    "valuation_snapshot",
    "annual_financials",
    "standalone_financials",
    "data_quality_flags",
    "daily_stock_data",
    "bulk_block_deals",
    "insider_transactions",
    "consensus_estimates",
    "earnings_surprises",
    "screener_ratios",
    "screener_charts",
    "peer_comparison",
    "shareholder_detail",
    "financial_schedules",
    "company_profiles",
    "company_documents",
    "fmp_dcf",
    "fmp_technical_indicators",
    "fmp_key_metrics",
    "fmp_financial_growth",
    "fmp_analyst_grades",
    "fmp_price_targets",
    "portfolio_holdings",
    "alerts",
    "sector_benchmarks",
    "corporate_actions",
    "historical_states",
    "analog_forward_returns",
    "estimate_revisions",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
    "analytical_snapshot",
    "listed_subsidiaries",
    "company_snapshot",
    "peer_links",
    "ar_esop_summary",
    "ar_five_year_summary",
    "adr_gdr_outstanding",
    "adr_programs",
    "fda_inspections",
    "surveillance_flags",
    "shareholding_breakdown",
    "screener_ids",
    "watchlist",
    "delisted_symbols",
    "unresolved_cliffs",
    "fno_universe",
    "fno_contracts",
    "ipo_listings",
)

# Monetary SUBSET of _MARKET_COLUMN_TABLES — tables holding native-currency
# amounts (price / market_cap / value / cash / debt / revenue / income / etc.).
# Tables that hold only ratios, percentages, day-counts, scores, or share counts
# are excluded (currency is meaningless for them).
_CURRENCY_COLUMN_TABLES: tuple[str, ...] = (
    "commodity_prices",
    "quarterly_results",
    "valuation_snapshot",
    "annual_financials",
    "standalone_financials",
    "daily_stock_data",
    "bulk_block_deals",
    "insider_transactions",
    "consensus_estimates",
    "earnings_surprises",
    "screener_charts",
    "peer_comparison",
    "financial_schedules",
    "fmp_dcf",
    "fmp_key_metrics",
    "fmp_price_targets",
    "portfolio_holdings",
    "sector_benchmarks",
    "corporate_actions",
    "estimate_revisions",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
    "analytical_snapshot",
    "company_snapshot",
    "ar_esop_summary",
    "ar_five_year_summary",
    "fno_contracts",
    "ipo_listings",
)


class FlowStore(PortfolioMixin, FlowsMixin, MacroMixin, DerivativesMixin, MarketRegistryMixin, ResearchMixin, FundamentalsMixin, HoldingsMixin, PricesMixin, ValuationMixin, UsMarketMixin):
    """SQLite store for daily FII/DII flows.

    Domain methods are progressively being split into mixins under
    ``flowtracker/store_domains/`` (refactor P1.4); FlowStore composes them and
    owns the shared connection/schema/validation infrastructure.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("FLOWTRACKER_DB")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_valuation_snapshot()
        self._migrate_quarterly_and_annual()
        self._migrate_analytical_snapshot()
        self._migrate_company_snapshot()
        self._migrate_daily_stock_data()
        self._migrate_historical_states()
        self._migrate_fno_tables()
        self._migrate_survivorship_tables()
        self._migrate_macro_daily()
        self._migrate_market_columns()
        self._migrate_symbol_registry()
        self._migrate_us_registry()
        self._migrate_us_annual_financials()
        self._migrate_us_consensus_estimates()
        self._migrate_us_macro_daily()

        # Additive domain namespaces (refactor P1.4): store.portfolio.<method>()
        # works alongside the flat store.<method>() API.
        self.portfolio = Namespace(self, PortfolioMixin)
        self.flows = Namespace(self, FlowsMixin)
        self.macro = Namespace(self, MacroMixin)
        self.derivatives = Namespace(self, DerivativesMixin)
        self.market_registry = Namespace(self, MarketRegistryMixin)
        self.research = Namespace(self, ResearchMixin)
        self.fundamentals = Namespace(self, FundamentalsMixin)
        self.holdings = Namespace(self, HoldingsMixin)
        self.prices = Namespace(self, PricesMixin)
        self.valuation = Namespace(self, ValuationMixin)
        self.us = Namespace(self, UsMarketMixin)

    def _migrate_analytical_snapshot(self) -> None:
        """Add new columns to analytical_snapshot if they don't exist."""
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(analytical_snapshot)").fetchall()
        }
        new_cols = [
            # WACC (original migration)
            ("wacc", "REAL"), ("ke", "REAL"), ("kd_pretax", "REAL"),
            ("beta_blume", "REAL"), ("beta_raw", "REAL"),
            ("beta_r_squared", "REAL"), ("terminal_growth", "REAL"),
            ("wacc_flags", "TEXT"),
            # Forensic Checks (Batch 1)
            ("forensic_cfo_ebitda_5y", "REAL"), ("forensic_cfo_ebitda_signal", "TEXT"),
            ("forensic_dep_volatility", "REAL"), ("forensic_dep_signal", "TEXT"),
            ("forensic_cash_yield_pct", "REAL"), ("forensic_cash_yield_signal", "TEXT"),
            ("forensic_cwip_3y_avg", "REAL"), ("forensic_cwip_signal", "TEXT"),
            # Improvement Metrics (Batch 1)
            ("improvement_greatness_pct", "REAL"), ("improvement_greatness_class", "TEXT"),
            ("improvement_capex_prod_ratio", "REAL"),
            # Capital Discipline (Batch 1)
            ("capital_roce_reinvest_signal", "TEXT"), ("capital_sustainable_growth_3y", "REAL"),
            ("capital_equity_dilution_pct", "REAL"), ("capital_equity_dilution_signal", "TEXT"),
            # Incremental ROCE (Batch 2)
            ("incremental_roce_3y", "REAL"), ("incremental_roce_3y_signal", "TEXT"),
            ("incremental_roce_5y", "REAL"),
            # Altman Z-Score (Batch 2)
            ("altman_zscore", "REAL"), ("altman_zone", "TEXT"),
            # Working Capital (Batch 2)
            ("wc_ccc_direction", "TEXT"), ("wc_signal", "TEXT"),
            # Operating Leverage (Batch 2)
            ("dol_avg_3y", "REAL"), ("dol_signal", "TEXT"),
            # FCF Yield (Batch 2)
            ("fcf_yield_pct", "REAL"), ("fcf_yield_signal", "TEXT"), ("fcf_pat_ratio", "REAL"),
            # Tax Rate (Batch 2)
            ("tax_avg_3y_etr", "REAL"), ("tax_signal", "TEXT"),
            # Receivables Quality (Batch 2)
            ("recv_quality_signal", "TEXT"),
        ]
        for col, typ in new_cols:
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE analytical_snapshot ADD COLUMN {col} {typ}"
                )

    def _migrate_company_snapshot(self) -> None:
        """Add sector column to company_snapshot (yfinance-sourced)."""
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(company_snapshot)").fetchall()
        }
        for col_name, col_type in [("sector", "TEXT")]:
            if col_name not in existing:
                self._conn.execute(f"ALTER TABLE company_snapshot ADD COLUMN {col_name} {col_type}")
        self._conn.commit()

    def _migrate_historical_states(self) -> None:
        """Add evolved columns to historical_states.

        - Part 1.5: ``listed_days``, ``is_backfilled``.
        - PR-12 (issue #4): ``industry_as_of_date`` + ``industry_source`` so
          consumers can tell whether the ``industry`` field reflects a true
          historical classification (``"historical"``) or a current-fallback
          proxy (``"current_fallback"``). Re-classified tickers (e.g. SBIN)
          previously had cohorts compared against today's industry rather
          than the industry at the row's quarter — the source flag exposes
          that drift instead of pretending it isn't there.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(historical_states)").fetchall()
        }
        for col_name, col_type in [
            ("listed_days", "INTEGER"),
            ("is_backfilled", "INTEGER NOT NULL DEFAULT 0"),
            ("industry_as_of_date", "TEXT"),
            ("industry_source", "TEXT"),
        ]:
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE historical_states ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

    def _migrate_daily_stock_data(self) -> None:
        """Add adj_close + adj_factor columns for split/bonus-adjusted prices.

        adj_close: close price back-adjusted for all splits and bonuses that
            occurred AFTER the row's date. Canonical adjusted-price surface.
        adj_factor: cumulative multiplier applied to derive adj_close from close
            (adj_close = close / adj_factor).
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(daily_stock_data)").fetchall()
        }
        for col_name, col_type in [("adj_close", "REAL"), ("adj_factor", "REAL")]:
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE daily_stock_data ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

    def _migrate_macro_daily(self) -> None:
        """Extend macro_daily with extra FX pairs and yield-curve tenors.

        - ``eur_inr`` / ``gbp_inr`` (PR #143) — additional cross-currency pairs.
        - ``gsec_1y`` / ``gsec_5y`` / ``gsec_30y`` (feat/macro-expansion) —
          three additional G-sec tenors so the yield-curve module can compute
          slopes (1y-10y, 10y-30y) and inversion regimes. ``gsec_10y`` is
          unchanged.

        Idempotent — guarded by PRAGMA table_info.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(macro_daily)").fetchall()
        }
        for col_name, col_type in [
            ("eur_inr", "REAL"),
            ("gbp_inr", "REAL"),
            ("gsec_1y", "REAL"),
            ("gsec_5y", "REAL"),
            ("gsec_30y", "REAL"),
        ]:
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE macro_daily ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

    def _migrate_market_columns(self) -> None:
        """Add `market` (+ `currency` for monetary tables) to equity tables.

        Data-safe: ALTER ADD COLUMN is metadata-only in SQLite; the constant
        NOT NULL DEFAULT means existing rows materialize 'NSE'/'INR' for free —
        zero full-table writes (critical on the 4.5M-row daily_stock_data).
        Idempotent: PRAGMA table_info guards every column add.
        """
        cur = self._conn.cursor()
        for table in _MARKET_COLUMN_TABLES:
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            if not cols:
                continue
            if "market" not in cols:
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN market TEXT NOT NULL DEFAULT 'NSE'"
                )
        for table in _CURRENCY_COLUMN_TABLES:
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            if not cols:
                continue
            if "currency" not in cols:
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"
                )
        self._conn.commit()

    def _migrate_symbol_registry(self) -> None:
        """Seed symbol_registry from existing symbol-bearing tables (Tier A).

        Additive INSERT OR IGNORE; (symbol, market) PK makes it idempotent —
        re-runs never duplicate and never touch existing scraped rows.
        """
        self._conn.executescript(
            """
            INSERT OR IGNORE INTO symbol_registry (symbol, market, company_name, sector)
            SELECT u.symbol, 'NSE', MAX(u.company_name), MAX(u.sector)
            FROM (
                SELECT symbol, NULL AS company_name, NULL AS sector FROM company_profiles
                UNION ALL SELECT symbol, company_name, industry FROM index_constituents
                UNION ALL SELECT symbol, NULL, NULL FROM screener_ids
                UNION ALL SELECT symbol, name, industry FROM company_snapshot
                UNION ALL SELECT symbol, company_name, NULL FROM watchlist
            ) AS u
            WHERE u.symbol IS NOT NULL AND u.symbol <> ''
            GROUP BY u.symbol;
            """
        )
        self._conn.commit()

    def _migrate_us_registry(self) -> None:
        """Add symbol_registry.cik (US add-on, Phase 3). Metadata-only ALTER.

        EDGAR keys filers by CIK; we store it on the cross-market registry so a
        US symbol row can carry its SEC identifier. Idempotent — guarded by
        PRAGMA table_info. India rows simply leave cik NULL.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(symbol_registry)").fetchall()
        }
        if "cik" not in existing:
            self._conn.execute("ALTER TABLE symbol_registry ADD COLUMN cik TEXT")
        # industry: the GRANULAR yfinance industry label (e.g. 'Banks - Diversified',
        # 'REIT - Retail', 'Semiconductors') captured for US symbols so sector
        # classification routes through the same industry→sector sets as India,
        # instead of the coarse GICS-sector map ('Financials'→'Banks'). India rows
        # leave it NULL (they resolve industry via company_snapshot/index_constituents).
        if "industry" not in existing:
            self._conn.execute("ALTER TABLE symbol_registry ADD COLUMN industry TEXT")
        self._conn.commit()

    def _migrate_us_annual_financials(self) -> None:
        """Add the Phase 3.5b wide columns to us_annual_financials (US add-on).

        Idempotent — guarded by PRAGMA table_info; each missing column is added
        via ALTER TABLE. US-only table, so India reads/writes are untouched.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(us_annual_financials)").fetchall()
        }
        new_cols = {
            "fiscal_year_end": "TEXT",
            "equity_capital": "REAL",
            "reserves": "REAL",
            "borrowings": "REAL",
            "interest": "REAL",
            "profit_before_tax": "REAL",
            "tax": "REAL",
            "operating_profit": "REAL",
            "depreciation": "REAL",
            "num_shares": "REAL",
            "net_block": "REAL",
            "cwip": "REAL",
            "cash_and_bank": "REAL",
            "receivables": "REAL",
            "inventory": "REAL",
            "other_liabilities": "REAL",
            "cfi": "REAL",
            "cff": "REAL",
            "rnd_expense": "REAL",
            "stock_based_comp": "REAL",
            "sga": "REAL",
        }
        for col_name, col_type in new_cols.items():
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE us_annual_financials ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

    def _migrate_us_consensus_estimates(self) -> None:
        """Add analyst target high/low to us_consensus_estimates (US add-on).

        Idempotent — guarded by PRAGMA table_info. US-only table, so India
        reads/writes are untouched. Enables the fair_value bear/base/bull range
        to use the consensus low/mean/high directly.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(us_consensus_estimates)").fetchall()
        }
        for col_name in ("target_high", "target_low"):
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE us_consensus_estimates ADD COLUMN {col_name} REAL"
                )
        self._conn.commit()

    def _migrate_us_macro_daily(self) -> None:
        """Ensure us_macro_daily has the full column set (US add-on).

        The CREATE TABLE IF NOT EXISTS in _SCHEMA handles brand-new DBs; this
        idempotent PRAGMA-guarded ALTER exists for parity with the other
        _migrate_us_* methods and to backfill columns onto any pre-existing
        partial table. US-only table — India macro_daily is untouched.
        """
        existing = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(us_macro_daily)").fetchall()
        }
        if not existing:
            return  # table not yet created (shouldn't happen post-_SCHEMA); no-op
        new_cols = {
            "vix": "REAL", "dxy": "REAL", "ust_3m": "REAL", "ust_5y": "REAL",
            "ust_10y": "REAL", "ust_30y": "REAL", "wti_crude": "REAL",
            "brent_crude": "REAL", "gold": "REAL",
        }
        for col_name, col_type in new_cols.items():
            if col_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE us_macro_daily ADD COLUMN {col_name} {col_type}"
                )
        self._conn.commit()

    def seed_us_validation_universe(self) -> int:
        """Seed the US validation tickers into symbol_registry (manual helper).

        NOT auto-run in __init__ — call explicitly from tests / setup scripts.
        Upserts each (symbol, market, cik, sector) via upsert_symbol_registry,
        which derives currency='USD' and fiscal_year_system='CALENDAR' from the
        market config. Idempotent on (symbol, market). Returns the row count.
        """
        for symbol, market, cik, sector in US_VALIDATION_UNIVERSE:
            self.upsert_symbol_registry(symbol, market, sector=sector, cik=cik)
        return len(US_VALIDATION_UNIVERSE)

    def _migrate_survivorship_tables(self) -> None:
        """PR-13: idempotent PRAGMA guard for delisted_symbols + unresolved_cliffs."""
        for table, expected in (
            ("delisted_symbols",
             {"symbol", "last_active_date", "observations", "reason", "detected_at"}),
            ("unresolved_cliffs",
             {"symbol", "trade_date", "prev_close", "close", "return_pct", "detected_at"}),
        ):
            cols = {row[1] for row in
                    self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if cols:
                missing = expected - cols
                assert not missing, f"{table} missing {missing}"
        self._conn.commit()

    def _migrate_fno_tables(self) -> None:
        """Reserved for future F&O schema additions (Sprint 2).

        Currently a no-op — initial fno_contracts / fno_participant_oi /
        fno_universe tables are created via CREATE TABLE IF NOT EXISTS in
        _SCHEMA. This stub exists so future column additions (e.g. IV
        surface fields, Greeks, participant sub-categories) can be added
        idempotently without touching the __init__ block.
        """
        return

    def _migrate_quarterly_and_annual(self) -> None:
        """Add new columns to quarterly_results and annual_financials if they don't exist."""
        existing_qr = {
            row[1] for row in
            self._conn.execute("PRAGMA table_info(quarterly_results)").fetchall()
        }
        new_qr_cols = [
            ("expenses", "REAL"), ("other_income", "REAL"), ("depreciation", "REAL"),
            ("interest", "REAL"), ("profit_before_tax", "REAL"), ("tax_pct", "REAL"),
            # Insurance-only: Net Premium Earned (Schedule III "premium income net
            # of reinsurance ceded"). Stays NULL for non-insurers and for insurers
            # whose source feed doesn't expose the row. See
            # ResearchDataAPI._apply_insurance_headline for the read-side swap.
            ("net_premium_earned", "REAL"),
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
            # Insurance-only: Net Premium Earned (₹ Cr). See note above.
            ("net_premium_earned", "REAL"),
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

    # -- Phase 4: Watchlist & Shareholding --

    # -- Phase 5: Index Scanner --

    # -- Commodity Prices --

    # -- Index Daily Prices --

    # -- Promoter Pledge --

    # --- Wave 5 P2: granular shareholding breakdown ---

    _BREAKDOWN_PCT_FIELDS: tuple[str, ...] = (
        "retail_pct", "hni_pct", "bodies_corporate_pct", "nri_pct",
        "fpi_cat1_pct", "fpi_cat2_pct",
        "banks_pct", "other_financial_institutions_pct", "nbfc_pct",
        "provident_pension_funds_pct", "venture_capital_funds_pct",
        "sovereign_wealth_domestic_pct", "sovereign_wealth_foreign_pct",
        "foreign_companies_pct", "foreign_nationals_pct",
        "foreign_dr_holder_pct", "other_foreign_pct", "other_indian_pct",
        "employee_benefit_trust_pct", "iepf_pct",
    )

    _BREAKDOWN_INT_FIELDS: tuple[str, ...] = (
        "dr_underlying_shares", "custodian_total_shares",
    )

    # --- Wave 5 P2: AR ESOP summary ---

    # --- Wave 5 Strategy 2: AR five-year financial highlights ---

    # --- Wave 5 P2: ADR/GDR outstanding override / seed ---

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

    # -- Fundamentals: Valuation Snapshots --

    # -- Fundamentals: Annual Financials --

    # -- Macro Indicators --

    def backfill_missing_gsec(self, value: float, max_lookback_days: int = 7) -> int:
        """Fill NULL gsec_10y rows for the last N days with the given value.

        CCIL only publishes today's 10Y yield, and prior-day rows inserted
        before the first successful scrape keep NULL gsec_10y forever. This
        helper patches recent NULLs with the latest scraped value — a
        reasonable approximation since 10Y yields move <5bps/day.

        Returns the number of rows updated.
        """
        cursor = self._conn.execute(
            "UPDATE macro_daily SET gsec_10y = ? "
            "WHERE date >= date('now', ? || ' days') "
            "AND gsec_10y IS NULL",
            (value, f"-{max_lookback_days}"),
        )
        self._conn.commit()
        return cursor.rowcount

    def backfill_missing_gsec_curve(
        self,
        curve: dict[str, float | None],
        max_lookback_days: int = 7,
    ) -> int:
        """Patch NULL gsec_{1y,5y,10y,30y} rows over the last N days.

        ``curve`` keys are ``"1y"``, ``"5y"``, ``"10y"``, ``"30y"``; any
        missing/None entry is skipped (we don't overwrite a real NULL with
        another NULL). Returns the total number of column-updates issued
        across all tenors (so the caller has something concrete to log).
        """
        tenor_to_col = {
            "1y": "gsec_1y",
            "5y": "gsec_5y",
            "10y": "gsec_10y",
            "30y": "gsec_30y",
        }
        total = 0
        for key, col in tenor_to_col.items():
            value = curve.get(key)
            if value is None:
                continue
            cursor = self._conn.execute(
                f"UPDATE macro_daily SET {col} = ? "
                f"WHERE date >= date('now', ? || ' days') "
                f"AND {col} IS NULL",
                (value, f"-{max_lookback_days}"),
            )
            total += cursor.rowcount
        self._conn.commit()
        return total

    # -- Index-level Valuation (PE / PB / Dividend Yield) --

    # -- MF Scheme Daily NAVs (mfapi.in) --

    # -- RBI WSS System Credit (weekly) --

    # -- Market Breadth --

    # -- Bhavcopy + Delivery --

    # -- Bulk/Block Deals --

    # -- Insider/SAST Transactions --

    # -- Consensus Estimates --

    # -- Sector Aggregation --

    # -- MF Scheme Holdings --

    # -- Corporate Filings --

    def update_filing_path(self, news_id: str, local_path: str) -> None:
        """Update the local file path for a downloaded filing."""
        self._conn.execute(
            "UPDATE corporate_filings SET local_path = ? WHERE news_id = ?",
            (local_path, news_id),
        )
        self._conn.commit()

    # -- Chart data --

    # -- Peer comparison --

    # -- Company snapshot --

    # -- Peer links --

    # -- Shareholder details --

    # -- Financial schedules --

    # -- FMP Data --

    # Portfolio + alerts methods now live in store_domains/portfolio.py
    # (PortfolioMixin), composed into FlowStore via inheritance (refactor P1.4).

    # ── sector benchmarks ──────────────────────────────────────────

    # -- Corporate Actions --

    # -- Survivorship-bias instrumentation (PR-13, issues #3 + #23) --

    # ── Analytical Snapshot ─────────────────────────────────────────

    # ---------------------------------------------------------------------------
    # F&O ingestion (Sprint 2)
    # ---------------------------------------------------------------------------

    # ------------------------------------------------------------------
    # ADR/GDR program directory
    # ------------------------------------------------------------------

    # -- FDA inspections (live-fetch from openFDA, 2026-04-29 strategy2-ops) --

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


def _row_to_breadth(row: sqlite3.Row) -> BreadthSnapshot:
    """Convert a market_breadth_daily row to a BreadthSnapshot."""
    return BreadthSnapshot(
        date=row["date"],
        index_name=row["index_name"],
        total=row["total"],
        pct_above_200dma=row["pct_above_200dma"],
        advance=row["advance"],
        decline=row["decline"],
        unchanged=row["unchanged"],
        new_52w_highs=row["new_52w_highs"],
        new_52w_lows=row["new_52w_lows"],
        ad_ratio=row["ad_ratio"],
    )
