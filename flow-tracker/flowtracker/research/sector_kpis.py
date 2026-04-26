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
        "industries": ["Private Sector Bank", "Public Sector Bank", "Other Bank", "Banks - Regional", "Banks - Diversified", "Banks"],
        "kpis": [
            {"key": "casa_ratio_pct", "label": "CASA Ratio %", "unit": "pct", "description": "Current Account and Savings Account deposits as % of total deposits", "aliases": ["casa_pct", "casa"]},
            {"key": "gross_npa_pct", "label": "Gross NPA %", "unit": "pct", "description": "Gross non-performing assets as % of gross advances", "aliases": ["gnpa_pct", "gnpa", "gross_npa", "gross_npa_ratio"]},
            {"key": "net_npa_pct", "label": "Net NPA %", "unit": "pct", "description": "Net non-performing assets as % of net advances", "aliases": ["nnpa_pct", "nnpa", "net_npa", "net_npa_ratio"]},
            {"key": "net_interest_margin_pct", "label": "NIM %", "unit": "pct", "description": "Net interest income divided by average total assets", "aliases": ["nim_pct", "nim", "domestic_nim_pct", "global_nim_pct", "consolidated_nim_pct"]},
            {"key": "provision_coverage_ratio_pct", "label": "PCR %", "unit": "pct", "description": "Provision coverage ratio (excl. technical write-offs)", "aliases": ["pcr_pct", "pcr", "provision_coverage"]},
            {"key": "fresh_slippages_cr", "label": "Fresh Slippages", "unit": "cr", "description": "New additions to NPAs during the quarter in crores", "aliases": ["slippages_cr", "slippage_ratio_pct", "fresh_slippage_cr", "slippages"]},
            {"key": "credit_cost_bps", "label": "Credit Cost", "unit": "bps", "description": "Annualized loan loss provisions as % of average advances, in basis points", "aliases": ["credit_cost_pct", "credit_cost_pp", "credit_cost", "credit_cost_ratio"]},
            {"key": "capital_adequacy_ratio_pct", "label": "CRAR %", "unit": "pct", "description": "Total Capital Adequacy Ratio (Basel III)", "aliases": ["crar_pct", "crar", "car_pct", "car", "capital_adequacy"]},
            {"key": "cet1_pct", "label": "CET-1 %", "unit": "pct", "description": "Common Equity Tier 1 capital ratio (Basel III)", "aliases": ["cet_1_pct", "cet1", "cet_1", "common_equity_tier_1_pct", "common_equity_tier1_pct"]},
            {"key": "liquidity_coverage_ratio_pct", "label": "LCR %", "unit": "pct", "description": "Liquidity Coverage Ratio", "aliases": ["lcr_pct", "lcr"]},
            {"key": "cost_to_income_ratio_pct", "label": "Cost to Income %", "unit": "pct", "description": "Operating expenses divided by net total income", "aliases": ["c_to_i_pct", "cost_income_ratio", "c_i_ratio"]},
            {"key": "roau_pct", "label": "ROA %", "unit": "pct", "description": "Annualized net profit divided by average total assets", "aliases": ["roa_pct", "roa", "return_on_assets_pct"]},
            # Tier-2 additions 2026-04-24 per Gemini review — deposit-war + RBI scrutiny focus
            {"key": "cd_ratio_pct", "label": "Credit-to-Deposit Ratio %", "unit": "pct", "description": "Total advances divided by total deposits — RBI is hammering private banks on elevated C/D", "aliases": ["credit_deposit_ratio_pct", "c_d_ratio_pct"]},
            {"key": "retail_deposit_growth_pct", "label": "Retail Deposit Growth %", "unit": "pct", "description": "YoY growth in granular low-cost retail deposits (the scarcity resource in the current cycle)"},
            {"key": "recoveries_and_upgrades_cr", "label": "Recoveries & Upgrades", "unit": "cr", "description": "Gross recoveries + upgrades from NPAs in crores — needed to compute net slippages"},
            {"key": "ridf_shortfall_cr", "label": "RIDF/PSL Shortfall", "unit": "cr", "description": "Priority Sector Lending shortfall parked in RIDF bonds (yield drag for private banks)"},
        ],
    },
    "nbfcs": {
        "industries": ["Non Banking Financial Company (NBFC)", "Credit Services", "Financial - Capital Markets", "Financial - Credit Services"],
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
            # Tier-2 additions 2026-04-24 per Gemini review — IndAS + capital-light growth signals
            {"key": "co_lending_aum_cr", "label": "Co-Lending AUM", "unit": "cr", "description": "Co-lending / direct-assignment AUM in crores — how NBFCs manage capital efficiency"},
            {"key": "off_book_aum_pct", "label": "Off-Book AUM %", "unit": "pct", "description": "Securitized / direct-assignment off-book AUM as % of total AUM"},
            {"key": "bt_out_rate_pct", "label": "BT-Out Rate %", "unit": "pct", "description": "Balance-Transfer-Out attrition rate (housing/credit card). Elevated BT-out = pricing pressure"},
            {"key": "stage_2_assets_pct", "label": "Stage 2 Assets %", "unit": "pct", "description": "SMA-1/SMA-2 Stage 2 assets as % of AUM — early-warning leading indicator over Stage 3"},
        ],
    },
    "insurance": {
        "industries": ["Life Insurance", "General Insurance", "Insurance - Life", "Insurance - Diversified", "Insurance - Property & Casualty"],
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
            # Tier-2 additions 2026-04-24 per Gemini review — product mix drives VNB margin
            {"key": "product_mix_ulip_pct", "label": "ULIP Mix %", "unit": "pct", "description": "(Life) Unit-Linked Insurance Plans as % of APE"},
            {"key": "product_mix_nonpar_pct", "label": "Non-Par Mix %", "unit": "pct", "description": "(Life) Non-Par savings as % of APE (highest-margin segment)"},
            {"key": "product_mix_protection_pct", "label": "Protection Mix %", "unit": "pct", "description": "(Life) Pure-protection plans as % of APE"},
            {"key": "motor_od_loss_ratio_pct", "label": "Motor OD Loss Ratio %", "unit": "pct", "description": "(General) Own-Damage claims / OD earned premium"},
            {"key": "motor_tp_loss_ratio_pct", "label": "Motor TP Loss Ratio %", "unit": "pct", "description": "(General) Third-Party claims / TP earned premium"},
        ],
    },
    "it_services": {
        "industries": ["IT - Software", "IT - Services", "Information Technology Services", "Software - Application", "Software - Infrastructure"],
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
            # Tier-2 additions 2026-04-24 per Gemini review — GenAI + pyramid + concentration
            {"key": "genai_pipeline_usd_mn", "label": "GenAI Pipeline", "unit": "usd_mn", "description": "Disclosed GenAI deal pipeline or TCV in USD Millions — PoC→production conversion is the current theme"},
            {"key": "fresher_additions_number", "label": "Fresher Additions", "unit": "number", "description": "Gross campus/fresher hires this quarter — leading indicator of demand visibility vs lagging headcount"},
            {"key": "top_5_client_growth_pct", "label": "Top-5 Client Growth %", "unit": "pct", "description": "Revenue growth from top-5 clients — concentration risk + BFSI discretionary-spend sensitivity"},
        ],
    },
    "pharma": {
        "industries": ["Pharmaceuticals", "Healthcare", "Drug Manufacturers - Specialty & Generic", "Drug Manufacturers - General", "Biotechnology"],
        "kpis": [
            {"key": "us_revenue_usd_mn", "label": "US Revenue", "unit": "usd_mn", "description": "Total US market sales in USD Millions", "aliases": ["us_sales_usd_mn", "us_revenue", "us_sales"]},
            {"key": "india_formulations_revenue_cr", "label": "India Formulations Revenue", "unit": "cr", "description": "Domestic branded generics sales in crores", "aliases": ["india_formulations_cr", "india_branded_generics_cr", "domestic_formulations_cr"]},
            {"key": "r_and_d_spend_pct", "label": "R&D Spend %", "unit": "pct", "description": "R&D expenditure as % of total sales", "aliases": ["rd_spend_pct", "rnd_spend_pct", "research_development_pct", "r_and_d_pct", "rd_pct"]},
            {"key": "anda_filed_number", "label": "ANDAs Filed", "unit": "number", "description": "ANDA filings with US FDA this quarter", "aliases": ["anda_filings_number", "anda_filed", "andas_filed"]},
            {"key": "anda_approved_number", "label": "ANDAs Approved", "unit": "number", "description": "ANDA approvals from US FDA this quarter", "aliases": ["anda_approvals_number", "anda_approved", "andas_approved"]},
            {"key": "us_price_erosion_pct", "label": "US Price Erosion %", "unit": "pct", "description": "YoY price erosion in US base business", "aliases": ["price_erosion_pct", "us_erosion_pct"]},
            {"key": "api_revenue_cr", "label": "API Revenue", "unit": "cr", "description": "Active Pharmaceutical Ingredients revenue in crores"},
            {"key": "mr_productivity_lakhs_per_month", "label": "MR Productivity", "unit": "lakhs", "description": "Monthly revenue per Medical Representative in India"},
            # E13 additions — richer pharma granularity
            {"key": "rd_pct_of_revenue", "label": "R&D % of Revenue", "unit": "pct", "description": "R&D expenditure as % of total revenue (granular variant of r_and_d_spend_pct)", "aliases": ["rd_as_pct_of_revenue", "rd_revenue_pct", "r_and_d_as_pct_of_revenue"]},
            {"key": "usfda_facility_status", "label": "USFDA Facility Status", "unit": "string", "description": "Current USFDA inspection status for manufacturing facilities. Expected values: 'active_no_observations' | '483s_open' | 'warning_letter' | 'unknown'", "aliases": ["us_fda_status", "fda_status", "usfda_status"]},
            {"key": "anda_approvals_ltm", "label": "ANDA Approvals (LTM)", "unit": "number", "description": "Trailing twelve month count of ANDA approvals from US FDA", "aliases": ["anda_approvals_ttm", "anda_approvals_trailing"]},
            {"key": "key_molecule_pipeline", "label": "Key Molecule Pipeline", "unit": "list", "description": "List of strategic molecules in pipeline with optional launch dates (expect list of strings or {name, launch_date} objects)", "aliases": ["molecule_pipeline", "pipeline_molecules", "key_pipeline"]},
            # Tier-2 additions 2026-04-24 per Gemini review — pure formulations is dead money; CDMO + biosimilars drive multiples
            {"key": "cdmo_revenue_cr", "label": "CDMO Revenue", "unit": "cr", "description": "Contract Development & Manufacturing revenue in crores (Divi's, Syngene, Suven) — premium-multiple segment"},
            {"key": "biosimilar_market_share_pct", "label": "Biosimilar Market Share %", "unit": "pct", "description": "Market share in key biosimilar molecule (US/EU) — critical for Biocon, Dr. Reddy's"},
            {"key": "complex_generics_mix_pct", "label": "Complex Generics Mix %", "unit": "pct", "description": "Complex generics / specialty / injectables as % of revenue (vs plain vanilla generics)"},
            # Wave 4-5 P2 additions 2026-04-25 — pharma autoeval flagged USFDA compliance + GTN + R&D detail gaps
            {"key": "usfda_observations_count", "label": "USFDA Observations Count", "unit": "number", "description": "Form 483 observation count from the most recent USFDA inspection across plants. Track most-recent inspection's observation count, summed across multi-day inspections", "aliases": ["form_483_count", "fda_483_count", "fda_observations_count"]},
            {"key": "usfda_warning_letters_active", "label": "Active USFDA Warning Letters", "unit": "number", "description": "Count of active (un-cleared) USFDA warning letters across manufacturing facilities — a single warning letter can disable an entire plant's US business", "aliases": ["fda_warning_letters_active", "warning_letters_active"]},
            {"key": "anda_filings_pending", "label": "ANDA Filings Pending", "unit": "number", "description": "Count of ANDA filings with USFDA awaiting approval (cumulative pending filings, not quarterly)", "aliases": ["anda_pending_count", "anda_filings_pending_approval"]},
            {"key": "anda_approvals_ytd", "label": "ANDA Approvals YTD", "unit": "number", "description": "ANDA approvals received from USFDA year-to-date (calendar or fiscal as disclosed)", "aliases": ["anda_approvals_ytd_number"]},
            {"key": "gross_to_net_pct", "label": "US Gross-to-Net (GTN) %", "unit": "pct", "description": "US generics gross-to-net deduction as % of gross sales — captures channel rebates, chargebacks, returns. Spike = price erosion / pricing pressure", "aliases": ["gtn_pct", "us_gtn_pct", "gross_to_net_deduction_pct"]},
            {"key": "us_revenue_pct", "label": "US Revenue %", "unit": "pct", "description": "US generics + branded sales as % of total revenue (geographic mix)", "aliases": ["us_sales_mix_pct", "us_revenue_share_pct"]},
            {"key": "india_branded_pct", "label": "India Branded Formulations %", "unit": "pct", "description": "India branded formulations / IPM revenue as % of total revenue", "aliases": ["india_formulations_mix_pct", "ipm_revenue_pct", "domestic_branded_pct"]},
            {"key": "gross_margin_pct", "label": "Gross Margin %", "unit": "pct", "description": "Revenue minus COGS as % of revenue — pharma gross margin tracks API cost + product mix"},
            {"key": "ebitda_margin_pct", "label": "EBITDA Margin %", "unit": "pct", "description": "Operating EBITDA margin — pharma EBITDA margin is the headline profitability metric for the sector"},
        ],
    },
    "fmcg": {
        # Personal Products mapped here (HUL, Godrej Consumer etc.) per 2026-04-24
        # correction — was falling through to no-sector previously.
        "industries": ["FMCG", "Consumer Food", "Household & Personal Products", "Packaged Foods", "Beverages - Non-Alcoholic", "Personal Products"],
        "kpis": [
            {"key": "underlying_volume_growth_pct", "label": "Volume Growth %", "unit": "pct", "description": "YoY growth in actual units sold, stripping out price/mix", "aliases": ["uvg_pct", "uvg", "volume_growth_pct"]},
            {"key": "price_led_growth_pct", "label": "Price/Mix Growth %", "unit": "pct", "description": "Revenue growth from price hikes or premiumization", "aliases": ["price_growth_pct", "price_mix_growth_pct"]},
            {"key": "rural_revenue_growth_pct", "label": "Rural Growth %", "unit": "pct", "description": "Revenue/volume growth in rural markets", "aliases": ["rural_growth_pct", "rural_pct"]},
            {"key": "urban_revenue_growth_pct", "label": "Urban Growth %", "unit": "pct", "description": "Revenue/volume growth in urban markets", "aliases": ["urban_growth_pct", "urban_pct"]},
            {"key": "gross_margin_pct", "label": "Gross Margin %", "unit": "pct", "description": "Revenue minus COGS as % of revenue (RM inflation indicator)"},
            {"key": "advertising_and_promotion_spend_pct", "label": "A&P Spend %", "unit": "pct", "description": "Ad and promotion expenses as % of revenue"},
            {"key": "direct_reach_outlets_number", "label": "Direct Reach", "unit": "number", "description": "Retail outlets directly serviced by distributors"},
            {"key": "new_product_contribution_pct", "label": "NPD Contribution %", "unit": "pct", "description": "% of sales from new product launches"},
            {"key": "channel_gt_pct", "label": "General Trade %", "unit": "pct", "description": "General Trade share of sales (kirana / traditional distribution)", "aliases": ["gt_pct", "general_trade_pct", "gt_share_pct"]},
            {"key": "channel_mt_pct", "label": "Modern Trade %", "unit": "pct", "description": "Modern Trade share of sales (supermarkets / hypermarkets)", "aliases": ["mt_pct", "modern_trade_pct", "mt_share_pct"]},
            {"key": "channel_ecom_pct", "label": "E-Commerce %", "unit": "pct", "description": "E-commerce / online share of sales", "aliases": ["ecom_pct", "ecommerce_pct", "online_pct", "d2c_pct"]},
            # Tier-2 additions 2026-04-24 per Gemini review — Q-com salience + bottom-line margin
            # Also: dropped short-form duplicate keys uvg_pct / price_growth_pct /
            # rural_growth_pct / urban_growth_pct (moved into aliases of their
            # long-form canonical counterparts). Schema now has a single canonical
            # key per concept — prevents DB normalization headaches downstream.
            {"key": "qcom_salience_pct", "label": "Q-Com Salience %", "unit": "pct", "description": "Quick-commerce (Blinkit/Zepto/Instamart/BB Now) revenue as % of total — the #1 topic on every FMCG concall", "aliases": ["quick_commerce_salience_pct", "qcom_mix_pct", "q_commerce_pct"]},
            {"key": "ebitda_margin_pct", "label": "EBITDA Margin %", "unit": "pct", "description": "Operating EBITDA margin post A&P — the actual bottom-line driver (gross margin alone misses A&P flex)"},
        ],
    },
    "auto": {
        "industries": ["Automobile", "Auto Components", "Auto - Manufacturers", "Auto Manufacturers", "Auto Parts", "Auto & Truck Dealerships"],
        "kpis": [
            {"key": "wholesale_volumes_number", "label": "Wholesale Volumes", "unit": "number", "description": "Total units dispatched to dealers"},
            {"key": "retail_volumes_number", "label": "Retail Volumes", "unit": "number", "description": "Total units sold to end customers"},
            {"key": "average_selling_price_rs", "label": "ASP", "unit": "rs", "description": "Revenue divided by wholesale volumes"},
            {"key": "dealer_inventory_days", "label": "Dealer Inventory Days", "unit": "days", "description": "Days of stock at dealership level"},
            {"key": "order_backlog_number", "label": "Order Backlog", "unit": "number", "description": "Pending unexecuted customer orders"},
            {"key": "ev_sales_mix_pct", "label": "EV Mix %", "unit": "pct", "description": "Electric Vehicles as % of total volumes"},
            {"key": "export_volumes_number", "label": "Export Volumes", "unit": "number", "description": "Total units exported"},
            {"key": "raw_material_cost_pct", "label": "RM Cost %", "unit": "pct", "description": "Raw material cost as % of sales"},
            # Tier-2 additions 2026-04-24 per Gemini review — segment-specific EV + tractors + weeks not days
            {"key": "ev_2w_mix_pct", "label": "EV 2W Mix %", "unit": "pct", "description": "Electric 2-wheelers as % of 2W volumes (Bajaj, TVS, Hero, Ola) — blended EV mix is useless across segments"},
            {"key": "ev_pv_mix_pct", "label": "EV PV Mix %", "unit": "pct", "description": "Electric passenger vehicles as % of PV volumes (Tata Motors, M&M, Hyundai)"},
            {"key": "tractor_volumes_number", "label": "Tractor Volumes", "unit": "number", "description": "Tractor units sold (Escorts, M&M) — decoupled from PV/CV cycles, driven by monsoon + MSP"},
            {"key": "dealer_inventory_weeks", "label": "Dealer Inventory Weeks", "unit": "weeks", "description": "Dealer inventory in weeks (Indian OEMs guide in weeks, not days; FADA reports in days) — convert if needed", "aliases": ["channel_inventory_weeks"]},
        ],
    },
    "cement": {
        "industries": ["Cement & Cement Products", "Building Materials"],
        "kpis": [
            {"key": "sales_volume_mn_tons", "label": "Sales Volume", "unit": "mn_tons", "description": "Total cement + clinker sales volume in MMT"},
            {"key": "capacity_utilization_pct", "label": "Capacity Utilization %", "unit": "pct", "description": "Production as % of installed capacity"},
            {"key": "ebitda_per_ton_rs", "label": "EBITDA per Ton", "unit": "rs", "description": "EBITDA / sales volume (key cement metric)"},
            {"key": "power_and_fuel_cost_per_ton_rs", "label": "P&F per Ton", "unit": "rs", "description": "Power and fuel costs per ton"},
            {"key": "freight_cost_per_ton_rs", "label": "Freight per Ton", "unit": "rs", "description": "Logistics costs per ton"},
            {"key": "trade_sales_mix_pct", "label": "Trade Mix %", "unit": "pct", "description": "% of sales through dealer/retail (B2C) vs institutional (B2B)"},
            {"key": "premium_product_mix_pct", "label": "Premium Mix %", "unit": "pct", "description": "% of trade sales from premium brands"},
            {"key": "green_energy_share_pct", "label": "Green Power %", "unit": "pct", "description": "% of power from WHRS, Solar, Wind"},
            # Tier-2 additions 2026-04-24 per Gemini review — regional pricing + clinker bottleneck
            {"key": "regional_dominant_mix_pct", "label": "Dominant Region Mix %", "unit": "pct", "description": "Largest-region volume share (N/S/E/W/Central) — Indian cement pricing is regional, so sensitivity to that region's pricing cycle is key"},
            {"key": "clinker_capacity_utilization_pct", "label": "Clinker Capacity Utilization %", "unit": "pct", "description": "Clinker production as % of installed clinker capacity — clinker is the true bottleneck; grinding is easily added"},
        ],
    },
    "metals_and_mining": {
        "industries": ["Iron & Steel", "Non-Ferrous Metals", "Mining & Mineral products", "Steel", "Copper", "Aluminum", "Other Industrial Metals & Mining"],
        "kpis": [
            {"key": "production_volume_kt", "label": "Production Volume", "unit": "kt", "description": "Total production in Kilo Tonnes"},
            {"key": "sales_volume_kt", "label": "Sales Volume", "unit": "kt", "description": "Total volume sold in Kilo Tonnes"},
            {"key": "blended_realization_per_ton_rs", "label": "NSR per Ton", "unit": "rs", "description": "Net Sales Realization per tonne"},
            {"key": "cost_of_production_per_ton_rs", "label": "CoP per Ton", "unit": "rs", "description": "Blended cost of production per tonne"},
            {"key": "ebitda_per_ton_rs", "label": "EBITDA per Ton", "unit": "rs", "description": "EBITDA / sales volume"},
            {"key": "value_added_products_mix_pct", "label": "VAP Mix %", "unit": "pct", "description": "% of sales from Value Added Products"},
            {"key": "net_debt_cr", "label": "Net Debt", "unit": "cr", "description": "Total borrowings minus cash in crores"},
            # Tier-2 additions 2026-04-24 per Gemini review — steel margin driver + Coal India e-auction
            {"key": "coking_coal_cost_usd_per_ton", "label": "Coking Coal Cost", "unit": "usd_per_ton", "description": "Landed coking coal cost per ton — single biggest variable for Tata Steel / JSW Steel margins"},
            {"key": "e_auction_premium_pct", "label": "E-Auction Premium %", "unit": "pct", "description": "(Coal India) E-auction realization premium over FSA — drives the earnings beats"},
        ],
    },
    "real_estate": {
        "industries": ["Realty", "Construction", "Real Estate - Development", "Real Estate Services"],
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
            # Tier-2 additions 2026-04-24 per Gemini review — margin on unsold + BD replenishment + annuity
            {"key": "inventory_months", "label": "Inventory Months", "unit": "months", "description": "Unsold inventory divided by TTM pre-sales run-rate — the canonical cycle indicator for Indian RE"},
            {"key": "embedded_ebitda_margin_pct", "label": "Embedded EBITDA Margin %", "unit": "pct", "description": "EBITDA margin embedded in the pre-sales / unsold book — real story beyond headline pre-sales"},
            {"key": "bd_addition_gdv_cr", "label": "BD Addition GDV", "unit": "cr", "description": "Business Development (land / JDA) additions' Gross Development Value — land bank replenishment is what the multiple trades on"},
            {"key": "annuity_income_cr", "label": "Annuity Income", "unit": "cr", "description": "Rental / lease income from operational commercial assets (DLF, Macrotech, Phoenix) — separate from trading revenue"},
        ],
    },
    "telecom": {
        "industries": ["Telecom - Services", "Telecom Services", "Communication Services"],
        "kpis": [
            {"key": "arpu_rs", "label": "ARPU (Rs)", "unit": "rs", "description": "Average Revenue Per User per month (INR)", "aliases": ["arpu", "arpu_inr"]},
            {"key": "total_subscriber_base_mn", "label": "Total Subscribers", "unit": "mn", "description": "Active wireless subscriber base in Millions", "aliases": ["subscribers_mn", "total_subscribers_mn", "subscriber_base_mn"]},
            {"key": "broadband_4g_5g_subscribers_mn", "label": "4G/5G Subscribers", "unit": "mn", "description": "Data subscribers on 4G/5G"},
            {"key": "monthly_churn_rate_pct", "label": "Monthly Churn %", "unit": "pct", "description": "% of subscribers leaving per month"},
            {"key": "data_usage_per_subscriber_gb", "label": "Data Usage per Sub", "unit": "gb", "description": "Monthly data consumption per subscriber in GB"},
            {"key": "minutes_of_usage_mou", "label": "MOU", "unit": "minutes", "description": "Voice Minutes Of Usage per subscriber per month"},
            {"key": "network_capex_cr", "label": "Network Capex", "unit": "cr", "description": "Capex on towers, spectrum, fiber in crores"},
            # E13 additions — Africa subsidiary (Bharti Airtel / Africa Telecom)
            # Note: short-form duplicates `arpu_inr` / `subscribers_mn` dropped
            # 2026-04-24; they lived on as aliases of `arpu_rs` / `total_subscriber_base_mn`.
            {"key": "africa_cc_growth_pct", "label": "Africa CC Growth %", "unit": "pct", "description": "Constant-currency revenue growth % for Africa subsidiary (YoY)", "aliases": ["africa_constant_currency_growth_pct", "africa_cc_revenue_growth_pct"]},
            {"key": "africa_fx_devaluation_pct", "label": "Africa FX Devaluation %", "unit": "pct", "description": "Local-currency devaluation % impacting Africa reported revenue (negative = headwind)", "aliases": ["africa_fx_impact_pct", "africa_currency_devaluation_pct"]},
            # Tier-2 additions 2026-04-24 per Gemini review — FTTH + B2B + 5G capex split
            {"key": "ftth_subs_mn", "label": "FTTH Subscribers", "unit": "mn", "description": "Home broadband / FTTH / wireline subscribers in millions (JioFiber, Airtel Xstream) — the ARPU-accretive growth segment", "aliases": ["fttx_subs_mn", "wireline_subs_mn", "home_broadband_subs_mn"]},
            {"key": "enterprise_revenue_growth_pct", "label": "Enterprise Revenue Growth %", "unit": "pct", "description": "YoY growth in enterprise / B2B / digital services revenue — the hidden cash cow"},
            {"key": "capex_5g_cr", "label": "5G Capex", "unit": "cr", "description": "5G-specific network capex in crores (separated from general network_capex_cr to track end of investment cycle)"},
        ],
    },
    "chemicals": {
        "industries": ["Chemicals", "Specialty Chemicals", "Agrochemicals", "Chemicals - Specialty"],
        "kpis": [
            {"key": "volume_growth_pct", "label": "Volume Growth %", "unit": "pct", "description": "YoY growth in tonnage sold"},
            {"key": "price_and_mix_growth_pct", "label": "Price/Mix Growth %", "unit": "pct", "description": "Revenue growth from pricing/product mix"},
            {"key": "capacity_utilization_pct", "label": "Capacity Utilization %", "unit": "pct", "description": "Plant utilization levels"},
            {"key": "export_revenue_mix_pct", "label": "Export Mix %", "unit": "pct", "description": "% of revenues from exports"},
            {"key": "csm_revenue_mix_pct", "label": "CSM Revenue %", "unit": "pct", "description": "Revenue from Custom Synthesis & Manufacturing"},
            {"key": "new_products_commercialized_number", "label": "New Products Commercialized", "unit": "number", "description": "New molecules scaled to commercial production"},
            {"key": "capex_incurred_cr", "label": "Capex Incurred", "unit": "cr", "description": "Capex for capacity expansion in crores"},
            # Tier-2 additions 2026-04-24 per Gemini review — destocking cycle + fluorine specialty
            {"key": "inventory_days", "label": "Inventory Days", "unit": "days", "description": "Days of inventory on hand — agrochem destocking is the only thing moving this sector currently"},
            {"key": "ebitda_per_kg_rs", "label": "EBITDA per Kg", "unit": "rs", "description": "EBITDA per kg of product sold — essential for refrigerant / fluorine specialty players (SRF, Navin Fluorine)"},
        ],
    },
    "power_and_utilities": {
        "industries": ["Power Generation", "Power Distribution", "Gas Distribution", "Utilities - Regulated Electric", "Utilities - Independent Power Producers", "Utilities - Diversified"],
        "kpis": [
            {"key": "plant_load_factor_pct", "label": "PLF %", "unit": "pct", "description": "Actual generation as % of max possible"},
            {"key": "plant_availability_factor_pct", "label": "PAF %", "unit": "pct", "description": "Plant availability (determines capacity charge recovery)"},
            {"key": "regulated_equity_cr", "label": "Regulated Equity", "unit": "cr", "description": "Equity base on which regulated RoE is earned"},
            {"key": "receivables_days", "label": "Receivables Days", "unit": "days", "description": "Days sales outstanding from discoms"},
            {"key": "at_and_c_losses_pct", "label": "AT&C Losses %", "unit": "pct", "description": "(Discoms) Aggregate Technical & Commercial losses"},
            {"key": "merchant_sales_realization_rs_per_kwh", "label": "Merchant Realization", "unit": "rs", "description": "Per unit realization on power exchange"},
            {"key": "renewable_capacity_gw", "label": "Renewable Capacity", "unit": "gw", "description": "Installed renewable energy capacity in GW"},
            # Tier-2 additions 2026-04-24 per Gemini review — merchant pricing + FGD mandate
            {"key": "merchant_sales_mix_pct", "label": "Merchant Sales Mix %", "unit": "pct", "description": "Merchant / exchange sales (IEX) as % of total volume — IEX rates hitting Rs 10/unit; un-tied capacity is where operating leverage sits (Tata Power, JSW Energy)"},
            {"key": "fgd_capex_cr", "label": "FGD Capex", "unit": "cr", "description": "Flue Gas Desulfurization capex in crores (regulatory mandate for thermal plants) — material capex drag until completion"},
        ],
    },
    "oil_and_gas": {
        "industries": ["Refineries", "Oil Exploration", "Petrochemicals", "Refineries & Marketing", "Oil & Gas Refining & Marketing", "Oil & Gas Integrated", "Oil & Gas E&P"],
        "kpis": [
            {"key": "gross_refining_margin_usd_per_bbl", "label": "GRM", "unit": "usd_per_bbl", "description": "Gross Refining Margin per barrel of crude"},
            {"key": "refinery_throughput_mmt", "label": "Throughput", "unit": "mmt", "description": "Crude oil processed in Million Metric Tonnes"},
            {"key": "crude_realization_usd_per_bbl", "label": "Upstream Realization", "unit": "usd_per_bbl", "description": "Net realization per barrel of crude sold"},
            {"key": "gas_sales_volume_mmscmd", "label": "Gas Sales Volume", "unit": "mmscmd", "description": "Natural gas sales in MMSCMD"},
            {"key": "marketing_margin_rs_per_liter", "label": "Marketing Margin", "unit": "rs", "description": "(OMCs) Retail margin per liter of petrol/diesel"},
            {"key": "petrochemical_production_kmt", "label": "Petchem Production", "unit": "kmt", "description": "Petrochemical production volume in KMT"},
            {"key": "cgd_sales_volume_mmscmd", "label": "CGD Volume", "unit": "mmscmd", "description": "(City Gas) CNG + PNG sales in MMSCMD"},
            # Tier-2 additions 2026-04-24 per Gemini review — OMC inventory swing + govt under-recoveries
            {"key": "inventory_gain_loss_cr", "label": "Inventory Gain/Loss", "unit": "cr", "description": "Crude inventory revaluation P&L impact in crores — drives most headline EBITDA beats/misses for IOCL, BPCL, HPCL"},
            {"key": "marketing_under_recovery_cr", "label": "Marketing Under-Recovery", "unit": "cr", "description": "Under-recovery on retail petrol/diesel sales in crores — material when govt freezes fuel prices (pre-elections)"},
        ],
    },
    # --- Added 2026-04-24 per Gemini review — covers ~30% of Nifty 500 mcap
    # previously falling through to generic extraction.
    "capital_goods": {
        "industries": [
            "Industrial Machinery", "Engineering", "Construction Engineering",
            "Heavy Electrical Equipment", "Electrical Equipment",
            "Defence", "Aerospace & Defense",
            "Diversified", "Other Industrial Goods",
        ],
        "kpis": [
            {"key": "order_inflow_cr", "label": "Order Inflow", "unit": "cr", "description": "Gross order wins received during the quarter in crores"},
            {"key": "order_book_cr", "label": "Order Book", "unit": "cr", "description": "Total unexecuted orders as of quarter-end in crores"},
            {"key": "book_to_bill_ratio", "label": "Book to Bill", "unit": "ratio", "description": "Order book divided by trailing twelve-month revenue (cycle indicator)"},
            {"key": "execution_runrate_cr", "label": "Execution Run-Rate", "unit": "cr", "description": "Quarterly revenue from order-book execution in crores"},
            {"key": "ebitda_margin_core_pct", "label": "Core EBITDA Margin %", "unit": "pct", "description": "Core EBITDA margin excluding one-offs, land sales, services"},
            {"key": "working_capital_pct_sales", "label": "Working Capital % Sales", "unit": "pct", "description": "Net working capital as % of annualized revenue"},
            {"key": "export_order_share_pct", "label": "Export Order Share %", "unit": "pct", "description": "Export/international orders as % of order book"},
            {"key": "defence_order_share_pct", "label": "Defence Order Share %", "unit": "pct", "description": "Defence segment orders as % of order book (HAL, BEL, L&T)"},
        ],
    },
    "hospitals": {
        "industries": [
            "Healthcare Services", "Hospitals & Healthcare Services",
            "Healthcare Facilities", "Medical Care Facilities",
            "Diagnostic Services",
        ],
        "kpis": [
            {"key": "arpob_rs", "label": "ARPOB", "unit": "rs", "description": "Average Revenue Per Occupied Bed per day — the golden metric for Indian hospitals"},
            {"key": "occupancy_pct", "label": "Occupancy %", "unit": "pct", "description": "Inpatient bed occupancy as % of operational beds"},
            {"key": "alos_days", "label": "ALOS", "unit": "days", "description": "Average Length Of Stay per inpatient admission"},
            {"key": "new_bed_additions_number", "label": "New Bed Additions", "unit": "number", "description": "Net new operational beds commissioned during the quarter"},
            {"key": "operational_bed_count_number", "label": "Operational Beds", "unit": "number", "description": "Total operational bed count across network"},
            {"key": "payor_mix_cash_pct", "label": "Cash Payor Mix %", "unit": "pct", "description": "Revenue from self-pay (cash) patients as % of total; balance is TPA/insurance/govt"},
            {"key": "international_patient_revenue_pct", "label": "International Revenue %", "unit": "pct", "description": "Medical tourism / international patient revenue as % of total"},
            {"key": "same_hospital_revenue_growth_pct", "label": "SHRG %", "unit": "pct", "description": "Same-Hospital Revenue Growth excluding new unit additions (like-for-like)"},
        ],
    },
    "retail": {
        # Note: "Personal Products" is NOT here — HUL/Godrej Consumer are FMCG
        # (consumer staples), not retail. Nykaa-type beauty retail is covered by
        # "Beauty & Personal Care" which is kept below.
        "industries": [
            "Retailing", "Department Stores", "Speciality Retail", "Specialty Retail",
            "Restaurants & Cafes", "Restaurants",
            "Textiles - Apparel", "Apparel Retail",
            "Consumer Staples Distribution & Retail",
            "Beauty & Personal Care",
        ],
        "kpis": [
            {"key": "sssg_pct", "label": "SSSG %", "unit": "pct", "description": "Same-Store Sales Growth YoY — the headline retail metric"},
            {"key": "store_additions_net_number", "label": "Net Store Additions", "unit": "number", "description": "Net new stores opened during the quarter (opens minus closures)"},
            {"key": "total_store_count_number", "label": "Total Stores", "unit": "number", "description": "Total operational store count at quarter-end"},
            {"key": "revenue_per_sqft_rs", "label": "Revenue per Sqft", "unit": "rs", "description": "Annualized revenue per square foot of trading area (productivity metric)"},
            {"key": "gross_margin_pct", "label": "Gross Margin %", "unit": "pct", "description": "Retail gross margin (revenue − cost of goods / revenue)"},
            {"key": "private_label_mix_pct", "label": "Private Label Mix %", "unit": "pct", "description": "Private/own-brand label share of revenue"},
            {"key": "online_revenue_mix_pct", "label": "Online Mix %", "unit": "pct", "description": "E-commerce / app / omnichannel revenue as % of total"},
            {"key": "average_ticket_size_rs", "label": "Avg Ticket Size", "unit": "rs", "description": "Average transaction value per bill"},
        ],
    },
    "amc_capital_markets": {
        "industries": [
            "Asset Management", "Asset Management Companies",
            "Financial - Capital Markets", "Capital Markets",
            "Exchanges & Data", "Stock Exchanges",
            "Financial - Data & Stock Exchanges",
            "Financial Services - Other", "Other Capital Markets",
        ],
        "kpis": [
            {"key": "total_aum_cr", "label": "Total AUM", "unit": "cr", "description": "Total Assets Under Management at quarter-end in crores"},
            {"key": "equity_aum_mix_pct", "label": "Equity AUM Mix %", "unit": "pct", "description": "Equity schemes as % of total AUM (drives yield)"},
            {"key": "sip_flows_cr", "label": "SIP Flows", "unit": "cr", "description": "Monthly SIP inflows in crores (avg of last 3 months if disclosed)"},
            {"key": "sip_folio_count_lakhs", "label": "SIP Folios", "unit": "lakhs", "description": "Total active SIP folios in lakhs"},
            {"key": "yield_on_aum_bps", "label": "Yield on AUM", "unit": "bps", "description": "Annualized revenue as basis points of average AUM"},
            {"key": "market_share_revenue_pct", "label": "Market Share (Revenue) %", "unit": "pct", "description": "Market share by revenue (AMCs) or volumes (brokers/exchanges)"},
            {"key": "market_share_derivatives_pct", "label": "Derivatives Share %", "unit": "pct", "description": "Market share in F&O volumes (Angel, BSE)"},
            {"key": "active_clients_mn", "label": "Active Clients", "unit": "mn", "description": "NSE-active clients (brokers) or unique investors (AMCs) in millions"},
            {"key": "adto_cr", "label": "ADTO", "unit": "cr", "description": "Average Daily Turnover in crores (brokers/exchanges)"},
            {"key": "demat_accounts_mn", "label": "Demat Accounts", "unit": "mn", "description": "Total demat accounts (CDSL/NSDL) in millions"},
        ],
    },
    "consumer_durables": {
        "industries": [
            "Consumer Durables", "Household Appliances",
            "Consumer Electronics", "Industrial Electronics",
            "Cable", "Cables", "Wires & Cables",
            "Electronic Components", "Electronics Manufacturing Services",
        ],
        "kpis": [
            {"key": "volume_growth_pct", "label": "Volume Growth %", "unit": "pct", "description": "YoY volume growth in units sold (primary vs secondary if disclosed)"},
            {"key": "channel_inventory_days", "label": "Channel Inventory Days", "unit": "days", "description": "Days of inventory at distributor/dealer/retail channel"},
            {"key": "category_market_share_pct", "label": "Category Market Share %", "unit": "pct", "description": "Market share in primary category (Room AC, ceiling fan, wires, etc.)"},
            {"key": "inhouse_mfg_mix_pct", "label": "In-house Manufacturing %", "unit": "pct", "description": "% of product revenue from in-house manufacturing (vs outsourced / traded)"},
            {"key": "b2b_revenue_mix_pct", "label": "B2B Mix %", "unit": "pct", "description": "B2B / institutional / project revenue as % of total (Havells, Polycab cables)"},
            {"key": "commodity_cost_impact_bps", "label": "Commodity Impact", "unit": "bps", "description": "Copper/aluminum/steel/plastic cost impact on gross margin, in bps"},
            {"key": "ebitda_margin_pct", "label": "EBITDA Margin %", "unit": "pct", "description": "Operating EBITDA margin"},
            {"key": "capex_cr", "label": "Capex", "unit": "cr", "description": "Quarterly capex for capacity / backward integration in crores"},
            {"key": "new_product_contribution_pct", "label": "NPD Contribution %", "unit": "pct", "description": "New product introductions (last 3 years) as % of revenue"},
        ],
    },
    # --- Added 2026-04-25 — covers new-age consumer platforms (Zomato/Eternal,
    # Nykaa, Swiggy, FirstCry, IndiaMart, Naukri, Paytm) previously falling
    # through to generic extraction. Note: 'Restaurants' (Jubilant Foodworks,
    # Devyani, Sapphire) stays in retail — those are franchisee-operated brick-
    # and-mortar QSR chains, not marketplace platforms.
    "platform": {
        "industries": [
            # Consumer-internet / quick-commerce / food delivery
            "Internet Retail",                  # ETERNAL (Zomato), NYKAA
            "Internet & Catalogue Retail",      # INDIAMART, NAUKRI
            "E-Retail/ E-Commerce",             # SWIGGY, FIRSTCRY
            "Internet Content & Information",   # standard yfinance label
            "Internet Content",
            "E-Commerce",
            # Fintech marketplaces (lending + payments + brokerage platforms)
            "Financial Technology (Fintech)",   # PAYTM
            "Fintech",
            # Online travel / transport
            "Travel Services",                  # MAKEMYTRIP-equivalents
        ],
        "kpis": [
            # Top-line operating — GMV/GOV is the true scale; revenue is the cut
            {"key": "gov_cr", "label": "GOV (Gross Order Value)", "unit": "cr", "description": "Gross Order Value — total transactional value flowing through the platform in crores", "aliases": ["gross_order_value_cr", "gov", "gross_order_value"]},
            {"key": "gmv_cr", "label": "GMV (Gross Merchandise Value)", "unit": "cr", "description": "Gross Merchandise Value of transactions on the platform in crores", "aliases": ["gross_merchandise_value_cr", "gmv", "gross_merchandise_value"]},
            {"key": "take_rate_pct", "label": "Take Rate %", "unit": "pct", "description": "Platform revenue as % of GOV/GMV — monetization power", "aliases": ["take_rate", "monetization_rate_pct", "commission_rate_pct"]},
            # Profitability waterfall
            {"key": "contribution_margin_pct", "label": "Contribution Margin %", "unit": "pct", "description": "Contribution margin (revenue − variable costs) as % of revenue/GOV — unit economics test", "aliases": ["contribution_margin", "cm_pct", "contribution_pct"]},
            {"key": "adj_ebitda_margin_pct", "label": "Adj EBITDA Margin %", "unit": "pct", "description": "Adjusted EBITDA margin (post ESOP add-back) as % of revenue", "aliases": ["adjusted_ebitda_margin_pct", "adj_ebitda_pct"]},
            {"key": "unit_economics_per_order_inr", "label": "Unit Economics / Order", "unit": "rs", "description": "Contribution profit per order in rupees (positive = unit economics work)", "aliases": ["contribution_per_order_inr", "ce_per_order", "unit_economics_per_order"]},
            # Engagement
            {"key": "mtu_mn", "label": "Monthly Transacting Users", "unit": "mn", "description": "Monthly Transacting Users in millions — paying user base", "aliases": ["monthly_transacting_users_mn", "mtu", "mau_transacting_mn"]},
            {"key": "aov_inr", "label": "Average Order Value", "unit": "rs", "description": "Average basket size per order in rupees", "aliases": ["average_order_value_inr", "aov", "basket_size_inr"]},
            {"key": "frequency_per_user_per_month", "label": "Order Frequency / User / Month", "unit": "number", "description": "Orders per active user per month — stickiness / engagement metric", "aliases": ["order_frequency_per_user", "frequency_per_mtu", "monthly_order_frequency"]},
            # Quick-commerce specific (Blinkit, BBNow, Zepto, Instamart)
            {"key": "dark_store_count", "label": "Dark Store Count", "unit": "number", "description": "Total operational quick-commerce dark stores at quarter-end", "aliases": ["dark_stores_number", "dark_stores", "qc_dark_store_count"]},
            {"key": "qc_gov_cr", "label": "Quick-Commerce GOV", "unit": "cr", "description": "Quick-commerce vertical GOV in crores (Blinkit, BBNow, Instamart segment)", "aliases": ["quick_commerce_gov_cr", "qc_gmv_cr", "blinkit_gov_cr"]},
            {"key": "qc_aov_inr", "label": "Quick-Commerce AOV", "unit": "rs", "description": "Quick-commerce segment AOV in rupees", "aliases": ["quick_commerce_aov_inr", "blinkit_aov_inr"]},
            {"key": "qc_orders_per_dark_store_per_day", "label": "QC Orders / Dark Store / Day", "unit": "number", "description": "Daily orders per dark store — utilization / throughput metric", "aliases": ["orders_per_dark_store_per_day", "qc_throughput_per_store_per_day"]},
            # Food-delivery specific (Eternal core, Swiggy)
            {"key": "food_delivery_gov_cr", "label": "Food Delivery GOV", "unit": "cr", "description": "Food-delivery vertical GOV in crores", "aliases": ["fd_gov_cr", "food_gov_cr", "food_delivery_gmv_cr"]},
            {"key": "food_delivery_aov_inr", "label": "Food Delivery AOV", "unit": "rs", "description": "Food-delivery AOV in rupees", "aliases": ["fd_aov_inr", "food_aov_inr"]},
            {"key": "food_delivery_take_rate_pct", "label": "Food Delivery Take Rate %", "unit": "pct", "description": "Food-delivery revenue as % of food-delivery GOV", "aliases": ["fd_take_rate_pct", "food_take_rate_pct"]},
            # Supply-side / capacity
            {"key": "delivery_partners_active_thousand", "label": "Active Delivery Partners ('000)", "unit": "thousand", "description": "Active delivery partners (riders) in thousands", "aliases": ["delivery_partners_thousand", "active_riders_thousand", "rider_base_thousand"]},
            {"key": "monthly_active_restaurants_thousand", "label": "Monthly Active Restaurants ('000)", "unit": "thousand", "description": "Monthly active restaurant partners in thousands", "aliases": ["mar_thousand", "active_restaurants_thousand"]},
            {"key": "geographic_footprint_cities", "label": "Cities Covered", "unit": "number", "description": "Number of cities with active operational presence", "aliases": ["cities_present_number", "city_count_number", "cities_served"]},
        ],
    },
    "logistics": {
        "industries": [
            "Logistics", "Transportation", "Logistics Services",
            "Road Transport", "Trucking", "Freight Road",
            "Shipping", "Marine", "Marine Ports & Services",
            "Airlines", "Passenger Airlines",
            "Airports", "Ports",
            "Warehousing", "Rail Transport",
            "Courier Services", "Integrated Shipping & Logistics",
        ],
        "kpis": [
            {"key": "plf_passenger_load_factor_pct", "label": "PLF %", "unit": "pct", "description": "(Airlines) Passenger Load Factor — revenue passenger km / available seat km"},
            {"key": "rask_rs", "label": "RASK", "unit": "rs", "description": "(Airlines) Revenue per Available Seat Kilometer in rupees"},
            {"key": "cask_rs", "label": "CASK", "unit": "rs", "description": "(Airlines) Cost per Available Seat Kilometer in rupees"},
            {"key": "asks_mn", "label": "ASKs", "unit": "mn", "description": "(Airlines) Available Seat Kilometers in millions (capacity)"},
            {"key": "yield_per_passenger_rs", "label": "Yield per Passenger", "unit": "rs", "description": "(Airlines) Average ticket yield per passenger"},
            {"key": "fleet_size_number", "label": "Fleet Size", "unit": "number", "description": "Operational aircraft / trucks / vessels / containers at quarter-end"},
            {"key": "express_parcel_volumes_mn", "label": "Parcel Volumes", "unit": "mn", "description": "(Logistics) Express parcel shipments in millions"},
            {"key": "yield_per_kg_rs", "label": "Yield per Kg", "unit": "rs", "description": "(Logistics) Revenue realization per kg shipped"},
            {"key": "origin_destination_pincodes_number", "label": "Pincode Coverage", "unit": "number", "description": "(Logistics) Unique origin + destination pincodes served"},
            {"key": "fuel_cost_pct", "label": "Fuel Cost %", "unit": "pct", "description": "Fuel (ATF / diesel / bunker) as % of operating revenue"},
            {"key": "ebitda_margin_pct", "label": "EBITDA Margin %", "unit": "pct", "description": "Operating EBITDA margin (pre-depreciation + aircraft lease for airlines)"},
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


# ---------------------------------------------------------------------------
# Alias normalization (added 2026-04-24 per Gemini review)
# ---------------------------------------------------------------------------
# Each KPI may declare an `aliases` list. The extractor prompt asks the LLM
# to emit the canonical `key`, but models drift: they'll emit "gnpa_pct" when
# they should emit "gross_npa_pct", or "arpu_inr" for "arpu_rs". Prior to
# this wiring, such responses would cause the validation loop to add a null
# entry for the canonical key AND leave the alias-keyed entry alongside —
# producing duplicate-concept rows downstream.
#
# `canonicalize_operational_metrics` collapses alias keys to their canonical
# form. If the LLM emits BOTH the canonical key and an alias (e.g. drift mid-
# response), the canonical wins; the alias payload is dropped with a log
# warning so ops can see it happened.


def get_alias_map_for_industry(industry: str) -> dict[str, str]:
    """Return {alias_key -> canonical_key} for the industry's sector.

    Cross-sector collisions are not possible within a single call because
    this map is scoped to one industry/sector. Returns {} if no sector
    matches the industry (generic/unknown cases).
    """
    kpis = get_kpis_for_industry(industry)
    if not kpis:
        return {}
    mapping: dict[str, str] = {}
    for kpi in kpis:
        canonical = kpi["key"]
        for alias in kpi.get("aliases") or ():
            # Self-alias is a no-op; skip collisions against another kpi's key
            if alias == canonical:
                continue
            mapping[alias] = canonical
    return mapping


def canonicalize_operational_metrics(
    ops: dict,
    industry: str,
    *,
    logger=None,
) -> tuple[dict, list[str]]:
    """Collapse alias-keyed entries in `ops` to their canonical key form.

    Returns (canonicalized_dict, list_of_aliases_that_were_renamed).
    The returned list is for logging/metrics; callers can ignore it.

    Rules:
    - If `ops` contains only an alias (e.g. `"gnpa_pct": {...}`), it's
      renamed to the canonical (`gross_npa_pct`).
    - If `ops` contains BOTH the canonical AND an alias for the same
      concept, the canonical wins; the alias entry is dropped and the
      collision logged.
    - Unrelated keys (not aliases, not canonical) pass through untouched.
    - If the industry doesn't map to a sector, `ops` is returned unchanged.
    """
    if not isinstance(ops, dict):
        return ops, []
    alias_map = get_alias_map_for_industry(industry)
    if not alias_map:
        return ops, []

    renamed: list[str] = []
    out: dict = {}
    seen_canonical: set[str] = set()

    # First pass — preserve all canonical entries exactly as-is.
    for k, v in ops.items():
        if k not in alias_map:
            out[k] = v
            seen_canonical.add(k)

    # Second pass — rewrite alias entries to their canonical name.
    for k, v in ops.items():
        if k in alias_map:
            canonical = alias_map[k]
            if canonical in seen_canonical:
                # Collision: canonical already present. Drop the alias payload.
                if logger is not None:
                    logger.warning(
                        "canonicalize: dropping alias %r because canonical %r already present",
                        k, canonical,
                    )
                continue
            out[canonical] = v
            renamed.append(k)
            seen_canonical.add(canonical)

    return out, renamed
