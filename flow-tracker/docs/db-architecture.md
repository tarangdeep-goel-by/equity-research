# Database Architecture Reference

> Generated: 2026-03-31 | 40 tables, 4.5M rows, single SQLite file

## Overview

Single SQLite DB at `~/.local/share/flowtracker/flows.db`. Single `FlowStore` class (~2900 lines, ~117 methods) handles all reads and writes. Data flows one-way: Client → Store → DataAPI → MCP Tools → Agent.

## Table Domains (9 domains, 40 tables)

### Market Flows — FII/DII/MF (5 tables, ~360K rows)
| Table | Rows | Key | Source | Cron |
|-------|------|-----|--------|------|
| daily_flows | 9,838 | date + category | NSE FII/DII API | daily |
| mf_monthly_flows | 4,375 | date + amc + category | AMFI monthly | monthly |
| mf_daily_flows | 28 | date + category | AMFI daily | daily |
| mf_aum_summary | 94 | date + amc | AMFI monthly | monthly |
| mf_scheme_holdings | 344,889 | scheme + symbol + date | AMFI disclosure | monthly |

No `symbol` column — these are market-wide tables.

### Stock Fundamentals (8 tables, ~31K rows)
| Table | Rows | Key | Source |
|-------|------|-----|--------|
| quarterly_results | 13,443 | symbol + quarter_end | Screener.in HTML |
| annual_financials | 2,291 | symbol + fiscal_year_end | Screener.in Excel export |
| screener_ratios | 4,846 | symbol + fiscal_year_end | Screener.in HTML |
| financial_schedules | 139 | symbol + section + item | Screener.in Schedules API |
| screener_charts | 10,316 | symbol + chart_type + date | Screener.in Chart API |
| screener_ids | 3 | symbol | Screener.in HTML (company_id, warehouse_id) |
| company_profiles | 3 | symbol | Screener.in HTML (about text, key points) |
| company_documents | 202 | symbol + doc_type + url | Screener.in HTML (concall/AR links) |

### Ownership & Governance (5 tables, ~399K rows)
| Table | Rows | Key | Source |
|-------|------|-----|--------|
| shareholding | 74,448 | symbol + quarter_end + category | NSE XBRL filings |
| shareholder_detail | 635 | symbol + name + classification | Screener.in Shareholders API |
| promoter_pledge | 10,915 | symbol + quarter_end | NSE XBRL filings |
| insider_transactions | 313,113 | symbol + date + person | NSE SAST API |
| bulk_block_deals | 0 | symbol + date + client | NSE deals API |

### Valuation & Estimates (5 tables, ~4.9K rows)
| Table | Rows | Key | Source |
|-------|------|-----|--------|
| valuation_snapshot | 3,403 | symbol + date | yfinance (50+ fields) |
| consensus_estimates | 1,003 | symbol + date | yfinance analyst consensus |
| earnings_surprises | 408 | symbol + date | yfinance earnings |
| peer_comparison | 24 | symbol + peer_name | Screener.in Peers API |
| sector_benchmarks | 12 | subject_symbol + metric | Computed (median, P25/P75, percentile) |

### FMP — Financial Modeling Prep (6 tables, 0 rows)
| Table | Rows | Key | Source | Status |
|-------|------|-----|--------|--------|
| fmp_dcf | 0 | symbol + date | FMP /discounted-cash-flow | **403 on free tier** |
| fmp_technical_indicators | 0 | symbol + date + indicator | FMP /technical_indicator | **403** |
| fmp_key_metrics | 0 | symbol + date | FMP /key-metrics | **403** |
| fmp_financial_growth | 0 | symbol + date | FMP /financial-growth | **403** |
| fmp_analyst_grades | 0 | symbol + date | FMP /grade | **403** |
| fmp_price_targets | 0 | symbol + date | FMP /price-target | **403** |

All 6 tables are dead weight on free tier. Most endpoints require paid plan ($14/mo starter).

### Market Data (4 tables, ~3.7M rows)
| Table | Rows | Key | Source |
|-------|------|-----|--------|
| daily_stock_data | 3,709,482 | symbol + date | NSE bhavcopy (OHLCV + delivery %) |
| commodity_prices | 16,324 | symbol + date | yfinance (gold/silver) |
| gold_etf_nav | 3,343 | scheme + date | mfapi.in |
| macro_daily | 4,756 | date + indicator | VIX, USD/INR, Brent, 10Y G-sec |

### Corporate Filings (1 table, ~2K rows)
| Table | Rows | Key | Source |
|-------|------|-----|--------|
| corporate_filings | 2,087 | symbol + date + headline | BSE announcements API |

### Portfolio & Alerts (4 tables, ~0 rows)
| Table | Rows | Key | Purpose |
|-------|------|-----|---------|
| portfolio_holdings | 0 | symbol | User portfolio tracking |
| alerts | 1 | symbol + condition | Condition-based alerts |
| alert_history | 0 | alert_id + triggered_at | Alert trigger log |
| watchlist | 0 | symbol | User watchlist |

### System (2 tables)
| Table | Rows | Key | Purpose |
|-------|------|-----|---------|
| index_constituents | 600 | symbol | Nifty 500 symbol ↔ company name mapping |
| audit_log | 9,111 | timestamp | Tracks all fetch operations |

## MCP Tool → Table Mapping

### Business Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_company_info | index_constituents |
| get_company_profile | company_profiles |
| get_company_documents | company_documents |
| get_business_profile | vault JSON (not DB) |
| get_concall_insights | vault JSON (not DB) |
| get_quarterly_results | quarterly_results |
| get_annual_financials | annual_financials |
| get_screener_ratios | screener_ratios |
| get_valuation_snapshot | valuation_snapshot |
| get_peer_comparison | peer_comparison |
| get_expense_breakdown | financial_schedules |
| get_consensus_estimate | consensus_estimates |
| get_earnings_surprises | earnings_surprises |

### Financial Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_quarterly_results | quarterly_results |
| get_annual_financials | annual_financials |
| get_screener_ratios | screener_ratios |
| get_expense_breakdown | financial_schedules |
| get_financial_growth_rates | fmp_financial_growth (empty on free tier) |
| get_dupont_decomposition | annual_financials (primary), fmp_key_metrics (fallback) |
| get_key_metrics_history | fmp_key_metrics (empty on free tier) |
| get_chart_data | screener_charts |
| get_earnings_surprises | earnings_surprises |
| get_concall_insights | vault JSON |

### Ownership Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_shareholding | shareholding |
| get_shareholding_changes | shareholding (self-join for QoQ) |
| get_insider_transactions | insider_transactions |
| get_bulk_block_deals | bulk_block_deals |
| get_mf_holdings | mf_scheme_holdings |
| get_mf_holding_changes | mf_scheme_holdings |
| get_shareholder_detail | shareholder_detail |
| get_promoter_pledge | promoter_pledge |
| get_delivery_trend | daily_stock_data |
| get_fii_dii_flows | daily_flows |
| get_fii_dii_streak | daily_flows |

### Valuation Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_valuation_snapshot | valuation_snapshot |
| get_valuation_band | valuation_snapshot (statistical) |
| get_pe_history | screener_charts |
| get_fair_value | valuation_snapshot + fmp_dcf + consensus_estimates (combined) |
| get_dcf_valuation | fmp_dcf (empty on free tier) |
| get_dcf_history | fmp_dcf (empty) |
| get_price_targets | fmp_price_targets (empty) |
| get_analyst_grades | fmp_analyst_grades (empty) |
| get_peer_comparison | peer_comparison |
| get_chart_data | screener_charts |
| get_consensus_estimate | consensus_estimates |
| get_concall_insights | vault JSON |

### Risk Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_composite_score | Cross-domain: valuation_snapshot, shareholding, insider_transactions, earnings_surprises, screener_ratios, daily_stock_data, consensus_estimates, promoter_pledge |
| get_macro_snapshot | macro_daily |
| get_recent_filings | corporate_filings |
| get_concall_insights | vault JSON |
| *(plus overlaps with Financial and Ownership tools)* | |

### Technical Agent Tools
| Tool | Tables Read |
|------|-------------|
| get_technical_indicators | fmp_technical_indicators (empty on free tier) |
| get_chart_data | screener_charts |
| get_delivery_trend | daily_stock_data |
| get_valuation_snapshot | valuation_snapshot |
| get_bulk_block_deals | bulk_block_deals |
| get_fii_dii_flows | daily_flows |
| get_fii_dii_streak | daily_flows |

### Cross-agent Tools (available to multiple agents)
| Tool | Tables Read | Used By |
|------|-------------|---------|
| get_peer_metrics | fmp_key_metrics + peer_comparison | Business, Financial, Valuation, Risk |
| get_peer_growth | fmp_financial_growth + peer_comparison | Business, Financial, Valuation, Risk |
| get_sector_benchmarks | sector_benchmarks | All agents |
| render_chart | Various (depends on chart_type) | All agents |

## Caching Strategy

| Layer | Freshness | Strategy |
|-------|-----------|----------|
| Full refresh (refresh_for_research) | 6 hours | Skip if 2/3 key tables fresh |
| Business refresh (refresh_for_business) | 6 hours | Skip if company_profiles fresh |
| Peer yfinance (peer_refresh) | 7 days | Per-peer check on valuation_snapshot |
| Peer FMP (peer_refresh) | Indefinite | Any record = cached (quarterly data) |
| Concall extraction | 30 days | Check file mtime |
| Sector benchmarks | Per-run | Recomputed each peer refresh |

## Known Technical Debt

1. **God class**: FlowStore is 2900 lines, 117 methods, all domains mixed. Should split by domain.
2. **FMP dead tables**: 6 tables, 0 rows. Free tier doesn't support .NS stocks. Remove or gate behind config.
3. **No schema versioning**: Column additions via _migrate_* methods with no tracking.
4. **Mixed granularity**: Market-wide tables (no symbol) and per-stock tables in same DB.
5. **No indexes beyond UNIQUE**: Large tables (daily_stock_data: 3.7M, insider_transactions: 313K) may need indexes for query performance.
6. **Implicit tool→table mapping**: Documented above but not enforced in code.

## Future Considerations

- Split FlowStore into domain stores (FlowStore, FundamentalStore, OwnershipStore, etc.)
- Add proper migration framework (alembic-lite or manual version table)
- Consider WAL mode for concurrent reads during parallel agent runs (may already be default)
- Add composite indexes on (symbol, date) for large tables
- Web UI would need read-only API layer on top of DataAPI
