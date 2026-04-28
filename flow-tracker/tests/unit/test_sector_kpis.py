"""Tests for flowtracker/research/sector_kpis.py canonical KPI registry.

Focus areas:
- E2.2 BFSI asset-quality keys (GNPA / NNPA / PCR / CRAR / CET-1 / LCR / CASA)
- E13 sector expansion: pharma / FMCG / telecom new canonical keys
- Fallback path: `get_sector_kpis(symbol, sub_section=<key>)` reading from
  `concall_insights.financial_metrics` when operational_metrics is empty.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from flowtracker.research.sector_kpis import (
    SECTOR_KPI_CONFIG,
    get_kpi_keys_for_industry,
    get_kpis_for_industry,
    get_sector_for_industry,
)


# ---------------------------------------------------------------------------
# E2.2 — BFSI asset-quality keys must be canonical for `banks` sector
# ---------------------------------------------------------------------------
class TestBfsiKpisInCanonicalList:
    """E2.2 — banks sector must expose GNPA / NNPA / PCR / CRAR / CET-1 / LCR / CASA.

    Keys are checked either directly or via alias — both paths are valid as
    downstream consumers resolve aliases via `get_sector_kpis` lookup.
    """

    _REQUIRED = ("gnpa_pct", "nnpa_pct", "pcr_pct", "crar_pct", "cet1_pct", "lcr_pct", "casa_pct")

    def _all_lookup_keys(self, kpis: list[dict]) -> set[str]:
        keys: set[str] = set()
        for kpi in kpis:
            keys.add(kpi["key"])
            keys.update(kpi.get("aliases") or [])
        return keys

    def test_bfsi_kpis_in_canonical_list(self):
        """banks sector must register all required BFSI keys (canonical or alias)."""
        banks = SECTOR_KPI_CONFIG["banks"]["kpis"]
        lookup = self._all_lookup_keys(banks)
        for key in self._REQUIRED:
            assert key in lookup, f"banks sector KPIs missing '{key}' (as canonical or alias)"

    def test_cet1_pct_is_canonical_key(self):
        """CET-1 % is a standalone Basel III ratio — must be canonical, not just an alias."""
        banks = SECTOR_KPI_CONFIG["banks"]["kpis"]
        canonical_keys = {k["key"] for k in banks}
        assert "cet1_pct" in canonical_keys, (
            "cet1_pct must be a top-level canonical KPI key (Basel III CET-1 is distinct from CRAR)"
        )

    def test_private_bank_industry_resolves_bfsi_keys(self):
        """Industry-level lookup for 'Private Sector Bank' exposes all required keys."""
        kpis = get_kpis_for_industry("Private Sector Bank")
        assert kpis is not None
        lookup = self._all_lookup_keys(kpis)
        for key in self._REQUIRED:
            assert key in lookup

    def test_psu_bank_industry_resolves_bfsi_keys(self):
        """PSU banks resolve to the same `banks` sector and same keys."""
        kpis = get_kpis_for_industry("Public Sector Bank")
        assert kpis is not None
        lookup = self._all_lookup_keys(kpis)
        for key in self._REQUIRED:
            assert key in lookup


# ---------------------------------------------------------------------------
# E13 — Pharma new canonical keys
# ---------------------------------------------------------------------------
class TestPharmaKpisInCanonicalList:
    """Pharma must register rd_pct_of_revenue, usfda_facility_status,
    anda_approvals_ltm, key_molecule_pipeline as canonical keys."""

    _REQUIRED = (
        "rd_pct_of_revenue",
        "usfda_facility_status",
        "anda_approvals_ltm",
        "key_molecule_pipeline",
    )

    def test_pharma_kpis_in_canonical_list(self):
        pharma = SECTOR_KPI_CONFIG["pharma"]["kpis"]
        canonical_keys = {k["key"] for k in pharma}
        for required in self._REQUIRED:
            assert required in canonical_keys, f"pharma canonical KPIs missing '{required}'"

    def test_pharma_keys_resolve_via_industry(self):
        keys = get_kpi_keys_for_industry("Pharmaceuticals")
        assert keys is not None
        for required in self._REQUIRED:
            assert required in keys


# ---------------------------------------------------------------------------
# E13 — FMCG new canonical keys
# ---------------------------------------------------------------------------
class TestFmcgKpisInCanonicalList:
    """FMCG must register all these keys as either canonical or alias.

    The short-form canonical duplicates (`uvg_pct`, `price_growth_pct`,
    `rural_growth_pct`, `urban_growth_pct`) were dropped 2026-04-24 and
    moved to aliases of their long-form counterparts. The test checks the
    UNION of canonical + aliases so lookup-side code that still uses short
    forms continues to work (once PR-C wires alias normalization).
    """

    _REQUIRED = (
        "uvg_pct",
        "price_growth_pct",
        "channel_gt_pct",
        "channel_mt_pct",
        "channel_ecom_pct",
        "rural_growth_pct",
        "urban_growth_pct",
    )

    @staticmethod
    def _all_lookup_keys(kpis: list[dict]) -> set[str]:
        keys: set[str] = set()
        for kpi in kpis:
            keys.add(kpi["key"])
            keys.update(kpi.get("aliases") or [])
        return keys

    def test_fmcg_kpis_in_canonical_or_alias(self):
        fmcg = SECTOR_KPI_CONFIG["fmcg"]["kpis"]
        lookup = self._all_lookup_keys(fmcg)
        for required in self._REQUIRED:
            assert required in lookup, f"fmcg missing '{required}' (as canonical or alias)"

    def test_fmcg_keys_resolve_via_industry(self):
        kpis = get_kpis_for_industry("FMCG")
        assert kpis is not None
        lookup = self._all_lookup_keys(kpis)
        for required in self._REQUIRED:
            assert required in lookup


# ---------------------------------------------------------------------------
# E13 — Telecom new canonical keys
# ---------------------------------------------------------------------------
class TestTelecomKpisInCanonicalList:
    """Telecom must register all these keys as either canonical or alias.

    The short-form duplicates (`arpu_inr`, `subscribers_mn`) were dropped
    2026-04-24 and moved to aliases of `arpu_rs` / `total_subscriber_base_mn`.
    """

    _REQUIRED = (
        "arpu_inr",
        "subscribers_mn",
        "africa_cc_growth_pct",
        "africa_fx_devaluation_pct",
    )

    @staticmethod
    def _all_lookup_keys(kpis: list[dict]) -> set[str]:
        keys: set[str] = set()
        for kpi in kpis:
            keys.add(kpi["key"])
            keys.update(kpi.get("aliases") or [])
        return keys

    def test_telecom_kpis_in_canonical_or_alias(self):
        telecom = SECTOR_KPI_CONFIG["telecom"]["kpis"]
        lookup = self._all_lookup_keys(telecom)
        for required in self._REQUIRED:
            assert required in lookup, f"telecom missing '{required}' (as canonical or alias)"

    def test_telecom_keys_resolve_via_industry(self):
        kpis = get_kpis_for_industry("Telecom - Services")
        assert kpis is not None
        lookup = self._all_lookup_keys(kpis)
        for required in self._REQUIRED:
            assert required in lookup


# ---------------------------------------------------------------------------
# E2.2 — BFSI fallback: get_sector_kpis reads financial_metrics when
# operational_metrics is empty for a bank
# ---------------------------------------------------------------------------
class TestBfsiFinancialMetricsFallback:
    """When a bank concall's operational_metrics section is empty but
    financial_metrics.{consolidated,standalone} contains the asset-quality
    keys, `get_sector_kpis(symbol, sub_section='gross_npa_pct')` should
    surface the value via the financial_metrics fallback.
    """

    def _make_api(self, op_quarters, fin_quarters):
        """Build a minimal ResearchDataAPI with mocked concall lookup + industry.

        Uses __new__ to avoid database/context wiring — we only exercise the
        pure-python matching logic around get_concall_insights().
        """
        from flowtracker.research.data_api import ResearchDataAPI

        api = ResearchDataAPI.__new__(ResearchDataAPI)
        api._get_industry = MagicMock(return_value="Public Sector Bank")

        def _fake_insights(symbol, section_filter=None, **kw):  # noqa: ARG001
            if section_filter == "operational_metrics":
                return {"quarters": op_quarters}
            if section_filter == "financial_metrics":
                return {"quarters": fin_quarters}
            return {"quarters": op_quarters}

        api.get_concall_insights = MagicMock(side_effect=_fake_insights)
        # Stub press-release backfill — these tests probe the financial_metrics
        # fallback in isolation. Real vault data would otherwise leak in via
        # the BFSI press_release backfill loop and shift expected values
        # (e.g. SBIN GNPA from "2.1" mock to 1.73 from on-disk press release).
        api.get_press_release_metrics = MagicMock(return_value={})
        return api

    def test_sector_kpis_bfsi_fallback_reads_concall(self):
        """SBIN: empty op_metrics + GNPA only in financial_metrics.consolidated
        → get_sector_kpis(sub_section='gross_npa_pct') returns that value.
        """
        op_quarters = [
            {"fy_quarter": "FY26-Q3", "operational_metrics": {}},
        ]
        fin_quarters = [
            {
                "fy_quarter": "FY26-Q3",
                "financial_metrics": {
                    "consolidated": {
                        "gross_npa_pct": {"value": "2.1", "context": "improved from 2.4 last quarter"},
                    },
                    "standalone": {},
                },
            },
        ]
        api = self._make_api(op_quarters, fin_quarters)
        result = api.get_sector_kpis("SBIN", kpi_key="gross_npa_pct")

        assert "kpi" in result, f"expected drill-down response with 'kpi' key, got: {result}"
        assert result["kpi"]["key"] == "gross_npa_pct"
        values = result["kpi"]["values"]
        assert len(values) == 1
        assert values[0]["value"] == "2.1"
        assert values[0]["quarter"] == "FY26-Q3"
        # Fallback path must be tagged so downstream agents can attribute source.
        assert "financial_metrics" in values[0].get("matched_via", "")

    def test_sector_kpis_bfsi_fallback_reads_via_alias(self):
        """SBIN: empty op_metrics + GNPA stored under alias 'gnpa_pct' in
        financial_metrics.standalone → fallback still resolves it.
        """
        op_quarters = [
            {"fy_quarter": "FY26-Q3", "operational_metrics": {}},
        ]
        fin_quarters = [
            {
                "fy_quarter": "FY26-Q3",
                "financial_metrics": {
                    "consolidated": {},
                    "standalone": {
                        "gnpa_pct": {"value": "1.9"},
                    },
                },
            },
        ]
        api = self._make_api(op_quarters, fin_quarters)
        result = api.get_sector_kpis("SBIN", kpi_key="gross_npa_pct")

        assert "kpi" in result
        assert result["kpi"]["values"][0]["value"] == "1.9"

    def test_operational_metrics_takes_precedence_over_fallback(self):
        """When both op_metrics and fin_metrics have the key, op_metrics wins."""
        op_quarters = [
            {
                "fy_quarter": "FY26-Q3",
                "operational_metrics": {
                    "gross_npa_pct": {"value": "2.1"},
                },
            },
        ]
        fin_quarters = [
            {
                "fy_quarter": "FY26-Q3",
                "financial_metrics": {
                    "consolidated": {"gross_npa_pct": {"value": "99.9"}},
                },
            },
        ]
        api = self._make_api(op_quarters, fin_quarters)
        result = api.get_sector_kpis("SBIN", kpi_key="gross_npa_pct")

        assert "kpi" in result
        assert result["kpi"]["values"][0]["value"] == "2.1"
        # Not tagged as financial_metrics fallback
        matched_via = result["kpi"]["values"][0].get("matched_via", "")
        assert "financial_metrics" not in matched_via


# ---------------------------------------------------------------------------
# Sector mapping sanity — ensure industry strings route to expected sectors.
# ---------------------------------------------------------------------------
class TestSectorMapping:
    def test_private_bank_maps_to_banks(self):
        assert get_sector_for_industry("Private Sector Bank") == "banks"

    def test_pharma_maps_to_pharma(self):
        assert get_sector_for_industry("Pharmaceuticals") == "pharma"

    def test_fmcg_maps_to_fmcg(self):
        assert get_sector_for_industry("FMCG") == "fmcg"

    def test_telecom_maps_to_telecom(self):
        assert get_sector_for_industry("Telecom - Services") == "telecom"

    def test_unknown_industry_returns_none(self):
        assert get_sector_for_industry("Underwater Basket Weaving") is None

    # 2026-04-28 — singular/exact industry names from Screener that were missing
    # from the alias lists for the 6 sectors added 2026-04-24. Each reproduces
    # the exact industry string returned by `_get_industry()` for a benchmark
    # stock in that sector.
    def test_civil_construction_maps_to_capital_goods(self):
        # LT (Larsen & Toubro)
        assert get_sector_for_industry("Civil Construction") == "capital_goods"

    def test_hospital_singular_maps_to_hospitals(self):
        # APOLLOHOSP — Screener returns bare "Hospital", not the plural variants
        assert get_sector_for_industry("Hospital") == "hospitals"

    def test_asset_management_company_singular_maps_to_amc(self):
        # HDFCAMC
        assert get_sector_for_industry("Asset Management Company") == "amc_capital_markets"

    def test_airline_singular_maps_to_logistics(self):
        # INDIGO
        assert get_sector_for_industry("Airline") == "logistics"

    def test_speciality_retail_maps_to_retail(self):
        # TRENT — already worked, locked in to prevent regression
        assert get_sector_for_industry("Speciality Retail") == "retail"

    def test_consumer_electronics_maps_to_durables(self):
        # HAVELLS — already worked, locked in to prevent regression
        assert get_sector_for_industry("Consumer Electronics") == "consumer_durables"


# ---------------------------------------------------------------------------
# Six new sectors added 2026-04-24 per Gemini review (covers ~30% of Nifty 500
# mcap previously falling through to generic extraction)
# ---------------------------------------------------------------------------
class TestAliasNormalization:
    """2026-04-24 — canonicalize_operational_metrics collapses LLM-emitted
    alias keys to canonical form so downstream consumers never see duplicate
    concepts (e.g. gnpa_pct alongside gross_npa_pct).
    """

    def test_alias_map_for_banks_contains_known_aliases(self):
        from flowtracker.research.sector_kpis import get_alias_map_for_industry
        m = get_alias_map_for_industry("Private Sector Bank")
        assert m.get("gnpa_pct") == "gross_npa_pct"
        assert m.get("nnpa_pct") == "net_npa_pct"
        assert m.get("pcr") == "provision_coverage_ratio_pct"

    def test_alias_map_empty_for_unknown_industry(self):
        from flowtracker.research.sector_kpis import get_alias_map_for_industry
        assert get_alias_map_for_industry("Underwater Basket Weaving") == {}

    def test_canonicalize_renames_alias_to_canonical(self):
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        ops = {
            "gnpa_pct": {"value": 1.5},          # alias → gross_npa_pct
            "casa_ratio_pct": {"value": 42.0},   # canonical — untouched
            "random_non_kpi_key": {"value": "keep"},  # pass-through
        }
        result, renamed = canonicalize_operational_metrics(ops, "Private Sector Bank")
        assert "gross_npa_pct" in result, "alias should be renamed to canonical"
        assert "gnpa_pct" not in result, "alias key should no longer appear"
        assert result["gross_npa_pct"] == {"value": 1.5}
        assert result["casa_ratio_pct"] == {"value": 42.0}
        assert result["random_non_kpi_key"] == {"value": "keep"}
        assert renamed == ["gnpa_pct"]

    def test_canonicalize_canonical_wins_on_collision(self):
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        # LLM emits BOTH canonical AND alias — canonical wins, alias dropped
        ops = {
            "gross_npa_pct": {"value": 1.5, "yoy_change": 0.1},   # canonical
            "gnpa_pct": {"value": 99.0, "source": "stale"},        # alias drop
        }
        result, renamed = canonicalize_operational_metrics(ops, "Private Sector Bank")
        assert result["gross_npa_pct"] == {"value": 1.5, "yoy_change": 0.1}
        assert "gnpa_pct" not in result
        assert renamed == [], "no rename — alias was dropped due to canonical collision"

    def test_canonicalize_pass_through_when_no_sector(self):
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        ops = {"gnpa_pct": {"value": 1.5}}
        result, renamed = canonicalize_operational_metrics(ops, "Underwater Basket Weaving")
        assert result == ops
        assert renamed == []

    def test_canonicalize_non_dict_input_pass_through(self):
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        # Defensive — e.g. a malformed extraction returned a list
        result, renamed = canonicalize_operational_metrics(["not", "a", "dict"], "Private Sector Bank")
        assert result == ["not", "a", "dict"]
        assert renamed == []

    def test_canonicalize_fmcg_shortform_alias(self):
        """FMCG dropped short-form canonicals in PR-B — now they're aliases.
        Extractor should still accept `uvg_pct` from the LLM and canonicalize."""
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        ops = {"uvg_pct": {"value": 5.5}}
        result, renamed = canonicalize_operational_metrics(ops, "FMCG")
        assert "underlying_volume_growth_pct" in result
        assert "uvg_pct" not in result
        assert renamed == ["uvg_pct"]


class TestTier2KpiAdditions:
    """Tier-2 KPIs added 2026-04-24 per Gemini review. Regression guards
    so future edits don't silently drop these institutional-grade keys."""

    @pytest.mark.parametrize("sector,required", [
        ("banks", ["cd_ratio_pct", "retail_deposit_growth_pct", "recoveries_and_upgrades_cr", "ridf_shortfall_cr"]),
        ("nbfcs", ["co_lending_aum_cr", "off_book_aum_pct", "bt_out_rate_pct", "stage_2_assets_pct"]),
        ("insurance", ["product_mix_ulip_pct", "product_mix_nonpar_pct", "product_mix_protection_pct", "motor_od_loss_ratio_pct", "motor_tp_loss_ratio_pct"]),
        ("it_services", ["genai_pipeline_usd_mn", "fresher_additions_number", "top_5_client_growth_pct"]),
        ("pharma", ["cdmo_revenue_cr", "biosimilar_market_share_pct", "complex_generics_mix_pct"]),
        ("fmcg", ["qcom_salience_pct", "ebitda_margin_pct"]),
        ("auto", ["ev_2w_mix_pct", "ev_pv_mix_pct", "tractor_volumes_number", "dealer_inventory_weeks"]),
        ("cement", ["regional_dominant_mix_pct", "clinker_capacity_utilization_pct"]),
        ("metals_and_mining", ["coking_coal_cost_usd_per_ton", "e_auction_premium_pct"]),
        ("real_estate", ["inventory_months", "embedded_ebitda_margin_pct", "bd_addition_gdv_cr", "annuity_income_cr"]),
        ("telecom", ["ftth_subs_mn", "enterprise_revenue_growth_pct", "capex_5g_cr"]),
        ("chemicals", ["inventory_days", "ebitda_per_kg_rs"]),
        ("power_and_utilities", ["merchant_sales_mix_pct", "fgd_capex_cr"]),
        ("oil_and_gas", ["inventory_gain_loss_cr", "marketing_under_recovery_cr"]),
    ])
    def test_sector_has_tier2_kpis(self, sector, required):
        canonical = {k["key"] for k in SECTOR_KPI_CONFIG[sector]["kpis"]}
        missing = [k for k in required if k not in canonical]
        assert not missing, f"{sector} missing tier-2 KPIs: {missing}"


class TestFmcgDedup:
    """Short-form duplicate canonical keys (uvg_pct, price_growth_pct,
    rural_growth_pct, urban_growth_pct) were dropped 2026-04-24 — they live
    only as aliases of their long-form counterparts."""

    @pytest.mark.parametrize("dropped_key,canonical_key", [
        ("uvg_pct", "underlying_volume_growth_pct"),
        ("price_growth_pct", "price_led_growth_pct"),
        ("rural_growth_pct", "rural_revenue_growth_pct"),
        ("urban_growth_pct", "urban_revenue_growth_pct"),
    ])
    def test_shortform_not_canonical(self, dropped_key, canonical_key):
        fmcg_canonical = {k["key"] for k in SECTOR_KPI_CONFIG["fmcg"]["kpis"]}
        assert dropped_key not in fmcg_canonical, (
            f"{dropped_key!r} was dropped — use {canonical_key!r} instead"
        )
        aliases_of_canonical = next(
            (k.get("aliases") or []) for k in SECTOR_KPI_CONFIG["fmcg"]["kpis"]
            if k["key"] == canonical_key
        )
        assert dropped_key in aliases_of_canonical, (
            f"{dropped_key!r} must remain reachable as an alias of {canonical_key!r}"
        )


class TestTelecomDedup:
    """arpu_inr / subscribers_mn short-form duplicates dropped 2026-04-24."""

    @pytest.mark.parametrize("dropped_key,canonical_key", [
        ("arpu_inr", "arpu_rs"),
        ("subscribers_mn", "total_subscriber_base_mn"),
    ])
    def test_shortform_not_canonical(self, dropped_key, canonical_key):
        telecom_canonical = {k["key"] for k in SECTOR_KPI_CONFIG["telecom"]["kpis"]}
        assert dropped_key not in telecom_canonical
        aliases = next(
            (k.get("aliases") or []) for k in SECTOR_KPI_CONFIG["telecom"]["kpis"]
            if k["key"] == canonical_key
        )
        assert dropped_key in aliases


class TestPersonalProductsRoutesToFmcg:
    """HUL / Godrej Consumer are FMCG (consumer staples), not retail.
    'Personal Products' must route to fmcg so HUL gets the 13-KPI FMCG set
    instead of falling through to retail."""

    def test_personal_products_maps_to_fmcg(self):
        assert get_sector_for_industry("Personal Products") == "fmcg"


class TestNewSectorsRegistered:
    """capital_goods, hospitals, retail, amc_capital_markets, consumer_durables,
    logistics must all be registered with non-empty KPIs and industries.
    """

    NEW_SECTORS = (
        "capital_goods", "hospitals", "retail",
        "amc_capital_markets", "consumer_durables", "logistics",
    )

    def test_all_new_sectors_present(self):
        for s in self.NEW_SECTORS:
            assert s in SECTOR_KPI_CONFIG, f"sector {s!r} missing from SECTOR_KPI_CONFIG"

    def test_each_new_sector_has_kpis_and_industries(self):
        for s in self.NEW_SECTORS:
            cfg = SECTOR_KPI_CONFIG[s]
            assert cfg["kpis"], f"{s} has no KPIs"
            assert cfg["industries"], f"{s} has no industries listed"
            # Every KPI must have the 4 required fields
            for kpi in cfg["kpis"]:
                for field in ("key", "label", "unit", "description"):
                    assert field in kpi, f"{s}/{kpi.get('key','?')} missing {field!r}"


class TestNewSectorRouting:
    """Industries added in the 6 new sectors must route correctly."""

    @pytest.mark.parametrize("industry,expected_sector", [
        # capital_goods
        ("Industrial Machinery", "capital_goods"),
        ("Heavy Electrical Equipment", "capital_goods"),
        ("Aerospace & Defense", "capital_goods"),
        # hospitals
        ("Healthcare Services", "hospitals"),
        ("Hospitals & Healthcare Services", "hospitals"),
        ("Diagnostic Services", "hospitals"),
        # retail
        ("Retailing", "retail"),
        ("Speciality Retail", "retail"),
        ("Restaurants", "retail"),
        # amc_capital_markets
        ("Asset Management", "amc_capital_markets"),
        ("Financial - Capital Markets", "amc_capital_markets"),
        ("Exchanges & Data", "amc_capital_markets"),
        # consumer_durables
        ("Consumer Durables", "consumer_durables"),
        ("Household Appliances", "consumer_durables"),
        ("Wires & Cables", "consumer_durables"),
        # logistics
        ("Logistics", "logistics"),
        ("Airlines", "logistics"),
        ("Marine Ports & Services", "logistics"),
        # platform (added 2026-04-25 — ETERNAL/Zomato, NYKAA, IndiaMart, Naukri,
        # Swiggy, FirstCry, Paytm). Must NOT regress 'Restaurants' (Jubilant
        # Foodworks etc. — franchisee QSR, stays in retail) or other sectors.
        ("Internet Retail", "platform"),
        ("Internet & Catalogue Retail", "platform"),
        ("E-Retail/ E-Commerce", "platform"),
        ("Internet Content & Information", "platform"),
        ("Financial Technology (Fintech)", "platform"),
    ])
    def test_industry_routes_to_expected_sector(self, industry, expected_sector):
        assert get_sector_for_industry(industry) == expected_sector


class TestPlatformKPIs:
    """Platform sector (ETERNAL/Zomato, NYKAA, IndiaMart, Swiggy, Paytm) added
    2026-04-25 — covers consumer-internet, quick-commerce, food delivery,
    online marketplaces, and fintech platforms.
    """

    _CANONICAL_REQUIRED = (
        # Top-line operating
        "gov_cr", "gmv_cr", "take_rate_pct",
        # Profitability waterfall
        "contribution_margin_pct", "adj_ebitda_margin_pct", "unit_economics_per_order_inr",
        # Engagement
        "mtu_mn", "aov_inr", "frequency_per_user_per_month",
        # Quick-commerce specific
        "dark_store_count", "qc_gov_cr", "qc_aov_inr", "qc_orders_per_dark_store_per_day",
        # Food-delivery specific
        "food_delivery_gov_cr", "food_delivery_aov_inr", "food_delivery_take_rate_pct",
        # Supply-side / capacity
        "delivery_partners_active_thousand", "monthly_active_restaurants_thousand",
        "geographic_footprint_cities",
    )

    def test_platform_registered_with_kpis_and_industries(self):
        assert "platform" in SECTOR_KPI_CONFIG
        cfg = SECTOR_KPI_CONFIG["platform"]
        assert cfg["industries"], "platform must list at least one industry"
        assert cfg["kpis"], "platform must register at least one KPI"

    def test_canonical_kpis_present(self):
        canonical = {k["key"] for k in SECTOR_KPI_CONFIG["platform"]["kpis"]}
        missing = [k for k in self._CANONICAL_REQUIRED if k not in canonical]
        assert not missing, f"platform missing canonical KPIs: {missing}"

    def test_eternal_industry_routes_to_platform(self):
        """ETERNAL (Zomato/Blinkit parent) is tagged 'Internet Retail' in the
        company_snapshot table — must route to platform sector."""
        assert get_sector_for_industry("Internet Retail") == "platform"

    def test_indiamart_naukri_industry_routes_to_platform(self):
        """B2B and classifieds platforms — 'Internet & Catalogue Retail'."""
        assert get_sector_for_industry("Internet & Catalogue Retail") == "platform"

    def test_swiggy_firstcry_industry_routes_to_platform(self):
        """SWIGGY, FIRSTCRY are tagged 'E-Retail/ E-Commerce' in DB."""
        assert get_sector_for_industry("E-Retail/ E-Commerce") == "platform"

    def test_paytm_industry_routes_to_platform(self):
        """PAYTM tagged 'Financial Technology (Fintech)' — fintech marketplace."""
        assert get_sector_for_industry("Financial Technology (Fintech)") == "platform"

    def test_restaurants_does_not_regress_to_platform(self):
        """JUBLFOOD, DEVYANI, SAPPHIRE — franchisee QSR, NOT marketplace
        platforms — must stay in retail (regression guard)."""
        assert get_sector_for_industry("Restaurants") == "retail"

    def test_platform_kpis_resolve_via_industry(self):
        keys = get_kpi_keys_for_industry("Internet Retail")
        assert keys is not None
        for required in self._CANONICAL_REQUIRED:
            assert required in keys, f"platform via industry lookup missing {required!r}"

    def test_platform_aliases_normalize_to_canonical(self):
        """LLM extractor drift (gmv → gmv_cr, take_rate → take_rate_pct etc.)
        must canonicalize via the alias map."""
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics

        ops = {
            "gmv": {"value": 12500.0},                 # alias → gmv_cr
            "take_rate": {"value": 4.5},               # alias → take_rate_pct
            "monthly_transacting_users_mn": {"value": 22.7},  # alias → mtu_mn
        }
        result, renamed = canonicalize_operational_metrics(ops, "Internet Retail")
        assert "gmv_cr" in result
        assert "take_rate_pct" in result
        assert "mtu_mn" in result
        assert sorted(renamed) == sorted(["gmv", "take_rate", "monthly_transacting_users_mn"])


class TestNewSectorCanonicalKpis:
    """Spot-check the flagship KPIs per new sector — if any of these are missing
    a buy-side PM will complain. These aren't an exhaustive list; they're the
    must-have ones per the Gemini review."""

    @pytest.mark.parametrize("sector,required", [
        ("capital_goods", ["order_inflow_cr", "order_book_cr", "book_to_bill_ratio"]),
        ("hospitals", ["arpob_rs", "occupancy_pct", "alos_days", "same_hospital_revenue_growth_pct"]),
        ("retail", ["sssg_pct", "store_additions_net_number", "revenue_per_sqft_rs"]),
        ("amc_capital_markets", ["total_aum_cr", "equity_aum_mix_pct", "sip_flows_cr", "yield_on_aum_bps"]),
        ("consumer_durables", ["channel_inventory_days", "category_market_share_pct", "commodity_cost_impact_bps"]),
        ("logistics", ["plf_passenger_load_factor_pct", "rask_rs", "cask_rs", "yield_per_kg_rs"]),
    ])
    def test_sector_has_flagship_kpis(self, sector, required):
        canonical = {k["key"] for k in SECTOR_KPI_CONFIG[sector]["kpis"]}
        missing = [k for k in required if k not in canonical]
        assert not missing, f"{sector} missing flagship KPIs: {missing}"


# ---------------------------------------------------------------------------
# Wave 4-5 P2 — Pharma sector pack (USFDA / GTN / R&D detail)
# ---------------------------------------------------------------------------
class TestPharmaWave45KPIs:
    """USFDA + GTN + R&D detail keys flagged as missing by SUNPHARMA / DRREDDY /
    CIPLA pharma autoeval. Must register as canonical (not just alias) keys.
    """

    _REQUIRED_NEW = (
        "usfda_observations_count",
        "usfda_warning_letters_active",
        "anda_filings_pending",
        "anda_approvals_ytd",
        "gross_to_net_pct",
        "us_revenue_pct",
        "india_branded_pct",
        "gross_margin_pct",
        "ebitda_margin_pct",
    )

    def test_new_pharma_kpis_are_canonical(self):
        pharma = SECTOR_KPI_CONFIG["pharma"]["kpis"]
        canonical_keys = {k["key"] for k in pharma}
        for key in self._REQUIRED_NEW:
            assert key in canonical_keys, f"pharma canonical KPIs missing '{key}'"

    def test_new_pharma_kpis_resolve_via_industry(self):
        keys = get_kpi_keys_for_industry("Pharmaceuticals")
        assert keys is not None
        for key in self._REQUIRED_NEW:
            assert key in keys

    def test_existing_pharma_kpis_still_present(self):
        """Adding new KPIs must not have removed any existing canonical key.

        Regression guard against careless edits to the pharma section.
        """
        keys = set(get_kpi_keys_for_industry("Pharmaceuticals") or [])
        # Pre-existing keys that the autoeval already trusted to be present.
        for legacy in (
            "us_revenue_usd_mn",
            "india_formulations_revenue_cr",
            "r_and_d_spend_pct",
            "anda_filed_number",
            "anda_approved_number",
            "us_price_erosion_pct",
            "rd_pct_of_revenue",
            "usfda_facility_status",
            "anda_approvals_ltm",
            "key_molecule_pipeline",
            "cdmo_revenue_cr",
            "biosimilar_market_share_pct",
            "complex_generics_mix_pct",
        ):
            assert legacy in keys, f"pharma lost legacy KPI '{legacy}'"

    def test_gross_to_net_alias_collapses(self):
        """`gtn_pct` (LLM-emitted alias) must canonicalize to `gross_to_net_pct`."""
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        ops_in = {"gtn_pct": {"value": 32.0, "context": "GTN was 32% in Q3"}}
        out, renamed = canonicalize_operational_metrics(ops_in, "Pharmaceuticals")
        assert "gross_to_net_pct" in out
        assert "gtn_pct" not in out
        assert "gtn_pct" in renamed

    def test_form_483_alias_collapses(self):
        """`form_483_count` (alias) must canonicalize to `usfda_observations_count`."""
        from flowtracker.research.sector_kpis import canonicalize_operational_metrics
        ops_in = {"form_483_count": {"value": 9, "context": "Halol audit Apr 2026"}}
        out, renamed = canonicalize_operational_metrics(ops_in, "Pharmaceuticals")
        assert "usfda_observations_count" in out
        assert "form_483_count" not in out
        assert "form_483_count" in renamed
