"""Canonical sector-specific KPI definitions for concall extraction and research tools.

Each sector defines:
- industries: list of NSE/Screener industry names that map to this sector
- kpis: list of {key, label, unit, description} for extraction

The `key` field is the canonical snake_case name used in:
1. Concall extraction prompt (tells the LLM what to look for)
2. Cross-quarter narrative (standardized metric trajectories)
3. get_sector_kpis() tool (surfaces sector KPIs to research agents)
"""

from __future__ import annotations

SECTOR_KPI_CONFIG: dict[str, dict] = {
    "banks": {
        "industries": ["Private Sector Bank", "Public Sector Bank", "Other Bank"],
        "kpis": [
            {"key": "casa_ratio_pct", "label": "CASA Ratio %", "unit": "pct", "description": "Current Account and Savings Account deposits as % of total deposits"},
            {"key": "gross_npa_pct", "label": "Gross NPA %", "unit": "pct", "description": "Gross non-performing assets as % of gross advances"},
            {"key": "net_npa_pct", "label": "Net NPA %", "unit": "pct", "description": "Net non-performing assets as % of net advances"},
            {"key": "net_interest_margin_pct", "label": "NIM %", "unit": "pct", "description": "Net interest income divided by average total assets"},
            {"key": "provision_coverage_ratio_pct", "label": "PCR %", "unit": "pct", "description": "Provision coverage ratio (excl. technical write-offs)"},
            {"key": "fresh_slippages_cr", "label": "Fresh Slippages", "unit": "cr", "description": "New additions to NPAs during the quarter in crores"},
            {"key": "credit_cost_bps", "label": "Credit Cost", "unit": "bps", "description": "Annualized loan loss provisions as % of average advances, in basis points"},
            {"key": "capital_adequacy_ratio_pct", "label": "CRAR %", "unit": "pct", "description": "Total Capital Adequacy Ratio (Basel III)"},
            {"key": "liquidity_coverage_ratio_pct", "label": "LCR %", "unit": "pct", "description": "Liquidity Coverage Ratio"},
            {"key": "cost_to_income_ratio_pct", "label": "Cost to Income %", "unit": "pct", "description": "Operating expenses divided by net total income"},
            {"key": "roau_pct", "label": "ROA %", "unit": "pct", "description": "Annualized net profit divided by average total assets"},
        ],
    },
    "nbfcs": {
        "industries": ["Non Banking Financial Company (NBFC)"],
        "kpis": [
            {"key": "aum_cr", "label": "AUM", "unit": "cr", "description": "Total Assets Under Management in crores"},
            {"key": "disbursements_cr", "label": "Disbursements", "unit": "cr", "description": "Total loans disbursed during the quarter in crores"},
            {"key": "stage_3_assets_pct", "label": "Stage 3 Assets %", "unit": "pct", "description": "Gross Stage 3 assets as % of total AUM (IndAS equivalent of GNPA)"},
            {"key": "collection_efficiency_pct", "label": "Collection Efficiency %", "unit": "pct", "description": "Total collections divided by total billings"},
            {"key": "cost_of_funds_pct", "label": "Cost of Funds %", "unit": "pct", "description": "Average annualized cost of borrowings"},
            {"key": "yield_on_advances_pct", "label": "Yield on Advances %", "unit": "pct", "description": "Annualized interest income as % of average advances"},
            {"key": "net_interest_margin_pct", "label": "NIM %", "unit": "pct", "description": "Net interest margin on average AUM"},
            {"key": "credit_cost_pct", "label": "Credit Cost %", "unit": "pct", "description": "ECL provisions as % of average AUM"},
            {"key": "capital_adequacy_ratio_pct", "label": "CRAR %", "unit": "pct", "description": "Total Capital Adequacy Ratio"},
            {"key": "cost_to_income_ratio_pct", "label": "Cost to Income %", "unit": "pct", "description": "Operating expenses divided by total net income"},
        ],
    },
    "insurance": {
        "industries": ["Life Insurance", "General Insurance"],
        "kpis": [
            {"key": "annualized_premium_equivalent_cr", "label": "APE", "unit": "cr", "description": "(Life) Annualized Premium Equivalent in crores"},
            {"key": "value_of_new_business_cr", "label": "VNB", "unit": "cr", "description": "(Life) Value of New Business in crores"},
            {"key": "vnb_margin_pct", "label": "VNB Margin %", "unit": "pct", "description": "(Life) VNB divided by APE"},
            {"key": "persistency_13th_month_pct", "label": "13th Month Persistency %", "unit": "pct", "description": "(Life) % of policies renewing in 13th month"},
            {"key": "persistency_61st_month_pct", "label": "61st Month Persistency %", "unit": "pct", "description": "(Life) % of policies renewing in 61st month"},
            {"key": "indian_embedded_value_cr", "label": "IEV", "unit": "cr", "description": "(Life) Indian Embedded Value in crores"},
            {"key": "gross_written_premium_cr", "label": "GWP", "unit": "cr", "description": "(General) Gross Written Premium in crores"},
            {"key": "combined_ratio_pct", "label": "Combined Ratio %", "unit": "pct", "description": "(General) Sum of loss ratio and expense ratio"},
            {"key": "loss_ratio_pct", "label": "Loss Ratio %", "unit": "pct", "description": "(General) Net incurred claims / net earned premium"},
            {"key": "solvency_ratio_times", "label": "Solvency Ratio", "unit": "ratio", "description": "Available solvency margin / required solvency margin (min 1.5x)"},
        ],
    },
    "it_services": {
        "industries": ["IT - Software", "IT - Services"],
        "kpis": [
            {"key": "tcv_deal_wins_usd_mn", "label": "TCV / Deal Wins", "unit": "usd_mn", "description": "Total Contract Value of new deal wins in USD Millions"},
            {"key": "constant_currency_revenue_growth_pct", "label": "CC Growth %", "unit": "pct", "description": "Revenue growth adjusted for exchange rate fluctuations"},
            {"key": "ltm_attrition_pct", "label": "LTM Attrition %", "unit": "pct", "description": "Last Twelve Months voluntary attrition rate"},
            {"key": "net_headcount_addition_number", "label": "Net Headcount Addition", "unit": "number", "description": "Net change in total employee headcount"},
            {"key": "utilization_excluding_trainees_pct", "label": "Utilization (ex-trainees) %", "unit": "pct", "description": "% of billable employees on projects, excluding trainees"},
            {"key": "subcontracting_cost_pct", "label": "Subcontracting Cost %", "unit": "pct", "description": "Third-party contractor cost as % of revenue"},
            {"key": "offshore_revenue_mix_pct", "label": "Offshore Mix %", "unit": "pct", "description": "% of effort/revenue delivered from offshore (India)"},
            {"key": "active_clients_number", "label": "Active Clients", "unit": "number", "description": "Total active billing clients"},
            {"key": "ebit_margin_pct", "label": "EBIT Margin %", "unit": "pct", "description": "Operating profit margin before interest and taxes"},
        ],
    },
    "pharma": {
        "industries": ["Pharmaceuticals", "Healthcare"],
        "kpis": [
            {"key": "us_revenue_usd_mn", "label": "US Revenue", "unit": "usd_mn", "description": "Total US market sales in USD Millions"},
            {"key": "india_formulations_revenue_cr", "label": "India Formulations Revenue", "unit": "cr", "description": "Domestic branded generics sales in crores"},
            {"key": "r_and_d_spend_pct", "label": "R&D Spend %", "unit": "pct", "description": "R&D expenditure as % of total sales"},
            {"key": "anda_filed_number", "label": "ANDAs Filed", "unit": "number", "description": "ANDA filings with US FDA this quarter"},
            {"key": "anda_approved_number", "label": "ANDAs Approved", "unit": "number", "description": "ANDA approvals from US FDA this quarter"},
            {"key": "us_price_erosion_pct", "label": "US Price Erosion %", "unit": "pct", "description": "YoY price erosion in US base business"},
            {"key": "api_revenue_cr", "label": "API Revenue", "unit": "cr", "description": "Active Pharmaceutical Ingredients revenue in crores"},
            {"key": "mr_productivity_lakhs_per_month", "label": "MR Productivity", "unit": "lakhs", "description": "Monthly revenue per Medical Representative in India"},
        ],
    },
    "fmcg": {
        "industries": ["FMCG", "Consumer Food"],
        "kpis": [
            {"key": "underlying_volume_growth_pct", "label": "Volume Growth %", "unit": "pct", "description": "YoY growth in actual units sold, stripping out price/mix"},
            {"key": "price_led_growth_pct", "label": "Price/Mix Growth %", "unit": "pct", "description": "Revenue growth from price hikes or premiumization"},
            {"key": "rural_revenue_growth_pct", "label": "Rural Growth %", "unit": "pct", "description": "Revenue/volume growth in rural markets"},
            {"key": "urban_revenue_growth_pct", "label": "Urban Growth %", "unit": "pct", "description": "Revenue/volume growth in urban markets"},
            {"key": "gross_margin_pct", "label": "Gross Margin %", "unit": "pct", "description": "Revenue minus COGS as % of revenue (RM inflation indicator)"},
            {"key": "advertising_and_promotion_spend_pct", "label": "A&P Spend %", "unit": "pct", "description": "Ad and promotion expenses as % of revenue"},
            {"key": "direct_reach_outlets_number", "label": "Direct Reach", "unit": "number", "description": "Retail outlets directly serviced by distributors"},
            {"key": "new_product_contribution_pct", "label": "NPD Contribution %", "unit": "pct", "description": "% of sales from new product launches"},
        ],
    },
    "auto": {
        "industries": ["Automobile", "Auto Components"],
        "kpis": [
            {"key": "wholesale_volumes_number", "label": "Wholesale Volumes", "unit": "number", "description": "Total units dispatched to dealers"},
            {"key": "retail_volumes_number", "label": "Retail Volumes", "unit": "number", "description": "Total units sold to end customers"},
            {"key": "average_selling_price_rs", "label": "ASP", "unit": "rs", "description": "Revenue divided by wholesale volumes"},
            {"key": "dealer_inventory_days", "label": "Dealer Inventory Days", "unit": "days", "description": "Days of stock at dealership level"},
            {"key": "order_backlog_number", "label": "Order Backlog", "unit": "number", "description": "Pending unexecuted customer orders"},
            {"key": "ev_sales_mix_pct", "label": "EV Mix %", "unit": "pct", "description": "Electric Vehicles as % of total volumes"},
            {"key": "export_volumes_number", "label": "Export Volumes", "unit": "number", "description": "Total units exported"},
            {"key": "raw_material_cost_pct", "label": "RM Cost %", "unit": "pct", "description": "Raw material cost as % of sales"},
        ],
    },
    "cement": {
        "industries": ["Cement & Cement Products"],
        "kpis": [
            {"key": "sales_volume_mn_tons", "label": "Sales Volume", "unit": "mn_tons", "description": "Total cement + clinker sales volume in MMT"},
            {"key": "capacity_utilization_pct", "label": "Capacity Utilization %", "unit": "pct", "description": "Production as % of installed capacity"},
            {"key": "ebitda_per_ton_rs", "label": "EBITDA per Ton", "unit": "rs", "description": "EBITDA / sales volume (key cement metric)"},
            {"key": "power_and_fuel_cost_per_ton_rs", "label": "P&F per Ton", "unit": "rs", "description": "Power and fuel costs per ton"},
            {"key": "freight_cost_per_ton_rs", "label": "Freight per Ton", "unit": "rs", "description": "Logistics costs per ton"},
            {"key": "trade_sales_mix_pct", "label": "Trade Mix %", "unit": "pct", "description": "% of sales through dealer/retail (B2C) vs institutional (B2B)"},
            {"key": "premium_product_mix_pct", "label": "Premium Mix %", "unit": "pct", "description": "% of trade sales from premium brands"},
            {"key": "green_energy_share_pct", "label": "Green Power %", "unit": "pct", "description": "% of power from WHRS, Solar, Wind"},
        ],
    },
    "metals_and_mining": {
        "industries": ["Iron & Steel", "Non-Ferrous Metals", "Mining & Mineral products"],
        "kpis": [
            {"key": "production_volume_kt", "label": "Production Volume", "unit": "kt", "description": "Total production in Kilo Tonnes"},
            {"key": "sales_volume_kt", "label": "Sales Volume", "unit": "kt", "description": "Total volume sold in Kilo Tonnes"},
            {"key": "blended_realization_per_ton_rs", "label": "NSR per Ton", "unit": "rs", "description": "Net Sales Realization per tonne"},
            {"key": "cost_of_production_per_ton_rs", "label": "CoP per Ton", "unit": "rs", "description": "Blended cost of production per tonne"},
            {"key": "ebitda_per_ton_rs", "label": "EBITDA per Ton", "unit": "rs", "description": "EBITDA / sales volume"},
            {"key": "value_added_products_mix_pct", "label": "VAP Mix %", "unit": "pct", "description": "% of sales from Value Added Products"},
            {"key": "net_debt_cr", "label": "Net Debt", "unit": "cr", "description": "Total borrowings minus cash in crores"},
        ],
    },
    "real_estate": {
        "industries": ["Realty", "Construction"],
        "kpis": [
            {"key": "pre_sales_value_cr", "label": "Pre-Sales Value", "unit": "cr", "description": "Value of new units booked in crores"},
            {"key": "pre_sales_volume_mn_sqft", "label": "Pre-Sales Volume", "unit": "mn_sqft", "description": "Area of new units booked in Mn Sq Ft"},
            {"key": "collections_cr", "label": "Collections", "unit": "cr", "description": "Cash collected from customers in crores"},
            {"key": "average_realization_per_sqft_rs", "label": "Realization per Sqft", "unit": "rs", "description": "Pre-sales value / pre-sales volume"},
            {"key": "new_launches_mn_sqft", "label": "New Launches", "unit": "mn_sqft", "description": "New project area opened for sale"},
            {"key": "business_development_value_cr", "label": "BD / GDV", "unit": "cr", "description": "Gross Development Value of new land/JDA signed"},
            {"key": "unsold_inventory_mn_sqft", "label": "Unsold Inventory", "unit": "mn_sqft", "description": "Pending inventory available for sale"},
            {"key": "operating_cash_flow_cr", "label": "Operating Cash Flow", "unit": "cr", "description": "Collections minus construction/opex"},
            {"key": "net_debt_cr", "label": "Net Debt", "unit": "cr", "description": "Gross debt minus cash"},
        ],
    },
    "telecom": {
        "industries": ["Telecom - Services"],
        "kpis": [
            {"key": "arpu_rs", "label": "ARPU", "unit": "rs", "description": "Average Revenue Per User per month"},
            {"key": "total_subscriber_base_mn", "label": "Total Subscribers", "unit": "mn", "description": "Active wireless subscriber base in Millions"},
            {"key": "broadband_4g_5g_subscribers_mn", "label": "4G/5G Subscribers", "unit": "mn", "description": "Data subscribers on 4G/5G"},
            {"key": "monthly_churn_rate_pct", "label": "Monthly Churn %", "unit": "pct", "description": "% of subscribers leaving per month"},
            {"key": "data_usage_per_subscriber_gb", "label": "Data Usage per Sub", "unit": "gb", "description": "Monthly data consumption per subscriber in GB"},
            {"key": "minutes_of_usage_mou", "label": "MOU", "unit": "minutes", "description": "Voice Minutes Of Usage per subscriber per month"},
            {"key": "network_capex_cr", "label": "Network Capex", "unit": "cr", "description": "Capex on towers, spectrum, fiber in crores"},
        ],
    },
    "chemicals": {
        "industries": ["Chemicals", "Specialty Chemicals", "Agrochemicals"],
        "kpis": [
            {"key": "volume_growth_pct", "label": "Volume Growth %", "unit": "pct", "description": "YoY growth in tonnage sold"},
            {"key": "price_and_mix_growth_pct", "label": "Price/Mix Growth %", "unit": "pct", "description": "Revenue growth from pricing/product mix"},
            {"key": "capacity_utilization_pct", "label": "Capacity Utilization %", "unit": "pct", "description": "Plant utilization levels"},
            {"key": "export_revenue_mix_pct", "label": "Export Mix %", "unit": "pct", "description": "% of revenues from exports"},
            {"key": "csm_revenue_mix_pct", "label": "CSM Revenue %", "unit": "pct", "description": "Revenue from Custom Synthesis & Manufacturing"},
            {"key": "new_products_commercialized_number", "label": "New Products Commercialized", "unit": "number", "description": "New molecules scaled to commercial production"},
            {"key": "capex_incurred_cr", "label": "Capex Incurred", "unit": "cr", "description": "Capex for capacity expansion in crores"},
        ],
    },
    "power_and_utilities": {
        "industries": ["Power Generation", "Power Distribution", "Gas Distribution"],
        "kpis": [
            {"key": "plant_load_factor_pct", "label": "PLF %", "unit": "pct", "description": "Actual generation as % of max possible"},
            {"key": "plant_availability_factor_pct", "label": "PAF %", "unit": "pct", "description": "Plant availability (determines capacity charge recovery)"},
            {"key": "regulated_equity_cr", "label": "Regulated Equity", "unit": "cr", "description": "Equity base on which regulated RoE is earned"},
            {"key": "receivables_days", "label": "Receivables Days", "unit": "days", "description": "Days sales outstanding from discoms"},
            {"key": "at_and_c_losses_pct", "label": "AT&C Losses %", "unit": "pct", "description": "(Discoms) Aggregate Technical & Commercial losses"},
            {"key": "merchant_sales_realization_rs_per_kwh", "label": "Merchant Realization", "unit": "rs", "description": "Per unit realization on power exchange"},
            {"key": "renewable_capacity_gw", "label": "Renewable Capacity", "unit": "gw", "description": "Installed renewable energy capacity in GW"},
        ],
    },
    "oil_and_gas": {
        "industries": ["Refineries", "Oil Exploration", "Petrochemicals"],
        "kpis": [
            {"key": "gross_refining_margin_usd_per_bbl", "label": "GRM", "unit": "usd_per_bbl", "description": "Gross Refining Margin per barrel of crude"},
            {"key": "refinery_throughput_mmt", "label": "Throughput", "unit": "mmt", "description": "Crude oil processed in Million Metric Tonnes"},
            {"key": "crude_realization_usd_per_bbl", "label": "Upstream Realization", "unit": "usd_per_bbl", "description": "Net realization per barrel of crude sold"},
            {"key": "gas_sales_volume_mmscmd", "label": "Gas Sales Volume", "unit": "mmscmd", "description": "Natural gas sales in MMSCMD"},
            {"key": "marketing_margin_rs_per_liter", "label": "Marketing Margin", "unit": "rs", "description": "(OMCs) Retail margin per liter of petrol/diesel"},
            {"key": "petrochemical_production_kmt", "label": "Petchem Production", "unit": "kmt", "description": "Petrochemical production volume in KMT"},
            {"key": "cgd_sales_volume_mmscmd", "label": "CGD Volume", "unit": "mmscmd", "description": "(City Gas) CNG + PNG sales in MMSCMD"},
        ],
    },
}

# --- Lookup helpers ---

# Flat mapping: industry name → sector key
_INDUSTRY_TO_SECTOR: dict[str, str] = {}
for _sector, _cfg in SECTOR_KPI_CONFIG.items():
    for _ind in _cfg["industries"]:
        _INDUSTRY_TO_SECTOR[_ind] = _sector


def get_sector_for_industry(industry: str) -> str | None:
    """Map an NSE/Screener industry name to a sector key."""
    return _INDUSTRY_TO_SECTOR.get(industry)


def get_kpis_for_industry(industry: str) -> list[dict] | None:
    """Get canonical KPI definitions for a given industry."""
    sector = get_sector_for_industry(industry)
    if sector is None:
        return None
    return SECTOR_KPI_CONFIG[sector]["kpis"]


def get_kpi_keys_for_industry(industry: str) -> list[str] | None:
    """Get just the canonical KPI key names for a given industry."""
    kpis = get_kpis_for_industry(industry)
    if kpis is None:
        return None
    return [k["key"] for k in kpis]


def build_extraction_hint(industry: str) -> str:
    """Build the sector-specific extraction hint for the concall extraction prompt."""
    kpis = get_kpis_for_industry(industry)
    if not kpis:
        return ""
    sector = get_sector_for_industry(industry)
    lines = [f"This company is in the **{sector}** sector. Extract these CANONICAL operational KPIs using EXACTLY these field names:"]
    for kpi in kpis:
        lines.append(f'  - `{kpi["key"]}` — {kpi["label"]}: {kpi["description"]} (unit: {kpi["unit"]})')
    lines.append("")
    lines.append("If a KPI is mentioned in the concall, extract it with {value, yoy_change, qoq_change, context}.")
    lines.append("If a KPI is NOT mentioned, set its value to null — do NOT omit the key.")
    return "\n".join(lines)
