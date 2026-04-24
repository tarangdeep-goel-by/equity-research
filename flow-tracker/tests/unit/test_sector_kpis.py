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


# ---------------------------------------------------------------------------
# Six new sectors added 2026-04-24 per Gemini review (covers ~30% of Nifty 500
# mcap previously falling through to generic extraction)
# ---------------------------------------------------------------------------
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
    ])
    def test_industry_routes_to_expected_sector(self, industry, expected_sector):
        assert get_sector_for_industry(industry) == expected_sector


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
