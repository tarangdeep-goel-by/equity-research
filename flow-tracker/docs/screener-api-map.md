# Screener.in API Map

Reference for all Screener.in endpoints used by `ScreenerClient` in `flowtracker/screener_client.py`.

## Authentication

All requests require an authenticated session. The client logs in once during `__init__`:

1. `GET /login/` -- acquire CSRF token from cookies
2. `POST /login/` -- submit `csrfmiddlewaretoken`, `username`, `password` with `Referer` header

Credentials loaded from `~/.config/flowtracker/screener.env` (`SCREENER_EMAIL`, `SCREENER_PASSWORD`).

## Company IDs

Screener uses two different internal IDs per company, both extracted from the `#company-info` HTML element:

| ID | HTML Attribute | Used By |
|----|----------------|---------|
| `company_id` | `data-company-id` | Chart API, Shareholders API, Schedules API |
| `warehouse_id` | `data-warehouse-id` | Peers API, Excel Export |

`_get_both_ids()` extracts both from page HTML. `_get_company_id()` extracts `company_id` via regex on `/api/company/{id}/` pattern. `_get_warehouse_id()` extracts `warehouse_id` via regex on `/user/company/export/{id}/` pattern.

## Endpoints

### 1. Company Page (HTML)

| | |
|---|---|
| **Method** | `fetch_company_page(symbol)` |
| **URL** | `GET /company/{SYMBOL}/consolidated/` (fallback: `/company/{SYMBOL}/`) |
| **Auth** | Session cookies |
| **ID used** | None (symbol in URL path) |
| **Returns** | Full HTML page |

The HTML is parsed by multiple methods:
- `parse_quarterly_from_html()` -- `#quarters` section table
- `parse_ratios_from_html()` -- `#ratios` section table
- `parse_documents_from_html()` -- `#documents` section (concalls, annual reports)
- `parse_growth_rates_from_html()` -- `table.ranges-table` elements (compounded growth rates)
- ID extraction for subsequent API calls

### 2. Excel Export

| | |
|---|---|
| **Method** | `download_excel(symbol)` |
| **URL** | `POST /user/company/export/{warehouse_id}/` |
| **Auth** | Session cookies + CSRF token in POST body |
| **ID used** | `warehouse_id` |
| **Headers** | `Referer: /company/{SYMBOL}/consolidated/` |
| **Returns** | `.xlsx` binary (Excel workbook) |

The Excel file contains a `Data Sheet` with sections: PROFIT & LOSS, QUARTERS, BALANCE SHEET, CASH FLOW, PRICE, DERIVED. Parsed by:
- `parse_quarterly_results()` -- Quarters section (10yr quarterly financials)
- `parse_annual_eps()` -- P&L section (annual EPS for historical P/E)
- `parse_annual_financials()` -- All sections (full annual P&L, BS, CF, price, derived)

### 3. Chart API

| | |
|---|---|
| **Method** | `fetch_chart_data(symbol, html)` / `fetch_chart_data_single(company_id, chart_type, days)` |
| **URL** | `GET /api/company/{company_id}/chart/?q={query}&days={days}&consolidated=true` |
| **Auth** | Session cookies |
| **ID used** | `company_id` |
| **Returns** | JSON `{"datasets": [{"label": str, "values": [[date, value], ...]}]}` |

Six chart queries available:

| chart_type | Query Parameter (`q=`) | Datasets Returned |
|------------|----------------------|-------------------|
| `price` | `Price-DMA50-DMA200-Volume` | Price, DMA50, DMA200, Volume |
| `pe` | `Price+to+Earning-Median+PE-EPS` | P/E ratio, Median PE, EPS |
| `sales_margin` | `GPM-OPM-NPM-Quarter+Sales` | Gross margin, Operating margin, Net margin, Quarterly sales |
| `ev_ebitda` | `EV+Multiple-Median+EV+Multiple-EBITDA` | EV/EBITDA, Median EV/EBITDA, EBITDA |
| `pbv` | `Price+to+book+value-Median+PBV-Book+value` | P/B ratio, Median PBV, Book value |
| `mcap_sales` | `Market+Cap+to+Sales-Median+Market+Cap+to+Sales-Sales` | Mcap/Sales, Median Mcap/Sales, Sales |

Default `days=10000` (~27 years of history).

### 4. Shareholders (Investors) API

| | |
|---|---|
| **Method** | `fetch_shareholders(company_id)` / `fetch_shareholder_details(html)` |
| **URL** | `GET /api/3/{company_id}/investors/{classification}/{period}/` |
| **Auth** | Session cookies |
| **ID used** | `company_id` |
| **Returns** | JSON dict `{investor_name: {quarter: pct, ..., setAttributes: {data-person-url: ...}}}` |

Classifications and periods:

| Classification | Period | Key in result |
|---------------|--------|---------------|
| `promoters` | `quarterly` | `promoters` |
| `foreign_institutions` | `quarterly` | `fii` / `foreign_institutions` |
| `domestic_institutions` | `quarterly` | `dii` / `domestic_institutions` |
| `public` | `quarterly` | `public` |
| `foreign_institutions` | `yearly` | `fii_yearly` |
| `domestic_institutions` | `yearly` | `dii_yearly` |

Note: `fetch_shareholders()` fetches all 4 classifications (quarterly only) with 1s delay between calls. `fetch_shareholder_details()` fetches FII + DII in both quarterly and yearly views.

### 5. Peers API

| | |
|---|---|
| **Method** | `fetch_peers(warehouse_id)` |
| **URL** | `GET /api/company/{warehouse_id}/peers/` |
| **Auth** | Session cookies |
| **ID used** | `warehouse_id` |
| **Returns** | HTML table (parsed with BeautifulSoup into list of peer dicts) |

Returns peer comparison with columns like: Name, CMP, P/E, Mar Cap, Div Yld, NP Qtr, Qtr Profit Var, Sales Qtr, Qtr Sales Var, ROCE.

### 6. Schedules API

| | |
|---|---|
| **Method** | `fetch_schedules(company_id, section, parent)` / `fetch_all_schedules(company_id)` |
| **URL** | `GET /api/company/{company_id}/schedules/?parent={parent}&section={section}&consolidated=` |
| **Auth** | Session cookies |
| **ID used** | `company_id` |
| **Returns** | JSON dict with sub-item breakdowns |

Available section/parent combinations:

| Section | Parent Line Items |
|---------|------------------|
| `quarters` | Sales, Expenses, Other Income, Net Profit |
| `profit-loss` | Sales, Expenses, Other Income, Net Profit |
| `balance-sheet` | Borrowings, Other Liabilities, Fixed Assets, Other Assets |
| `cash-flow` | Cash from Operating Activity, Cash from Investing Activity, Cash from Financing Activity |

`fetch_all_schedules()` iterates all combinations with 1s delay between calls.

### 7. Search API

| | |
|---|---|
| **Method** | `search(query)` |
| **URL** | `GET /api/company/search/?q={query}` |
| **Auth** | Session cookies |
| **ID used** | None |
| **Returns** | JSON list `[{id, name, url}, ...]` |

## Rate Limiting

No formal rate limit documented. The client adds `time.sleep(1)` between:
- Shareholder API calls (4 classifications)
- Schedule API calls (up to 15 section/parent combos)

## Summary Table

| # | Endpoint | HTTP | ID Type | Response |
|---|----------|------|---------|----------|
| 1 | `/company/{SYMBOL}/consolidated/` | GET | symbol | HTML |
| 2 | `/user/company/export/{warehouse_id}/` | POST | warehouse_id | Excel (.xlsx) |
| 3 | `/api/company/{company_id}/chart/` | GET | company_id | JSON |
| 4 | `/api/3/{company_id}/investors/{class}/{period}/` | GET | company_id | JSON |
| 5 | `/api/company/{warehouse_id}/peers/` | GET | warehouse_id | HTML table |
| 6 | `/api/company/{company_id}/schedules/` | GET | company_id | JSON |
| 7 | `/api/company/search/` | GET | none | JSON |
| - | `/login/` | GET+POST | none | Session cookies |
