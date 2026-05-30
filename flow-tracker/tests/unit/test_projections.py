"""Tests for research/projections.py — sector-aware D&A routing (Plan v2 §7 E12)."""

from __future__ import annotations

import pytest

from flowtracker.research.projections import build_projections, _resolve_da_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthetic_annual(n: int = 5, start_year: int = 2025, industry_flag: str = "generic") -> list[dict]:
    """Build a minimal annual-financials payload that satisfies build_projections.

    Uses monotonic growth so rev_3yr_cagr is stable and non-zero.
    """
    rows: list[dict] = []
    base_rev = 10_000.0
    base_ni = 1_500.0
    for i in range(n):
        yr = start_year - i
        rev = base_rev * (0.90 ** i)  # newest (i=0) is largest
        ni = base_ni * (0.88 ** i)
        rows.append(
            {
                "symbol": "TESTX",
                "fiscal_year_end": f"{yr}-03-31",
                "revenue": rev,
                "net_income": ni,
                "operating_profit": rev * 0.20,
                "depreciation": rev * 0.03,
                "interest": rev * 0.01,
                "tax": ni * 0.25,
                "eps": 15.0,
                "num_shares": 10.0,
                "net_block": rev * 0.5,  # for real_estate route
            }
        )
    return rows


# ---------------------------------------------------------------------------
# _resolve_da_strategy unit tests
# ---------------------------------------------------------------------------


class TestDaRatioRouting:
    def test_da_ratio_platform(self):
        """platform → 1% ratio with asset-light caveat."""
        strat = _resolve_da_strategy(
            industry="platform", latest_rev=10_000, latest_dep=50, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.01
        assert strat["source"] == "platform_default"
        assert any("platform" in c.lower() for c in strat["caveats"])

    def test_da_ratio_it_services(self):
        strat = _resolve_da_strategy(
            industry="it_services", latest_rev=10_000, latest_dep=50, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.01
        assert strat["source"] == "it_services_default"

    def test_da_ratio_manufacturing_default(self):
        strat = _resolve_da_strategy(
            industry="manufacturing", latest_rev=10_000, latest_dep=500, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.05

    def test_da_ratio_bfsi_uses_line_item(self):
        """BFSI must route to line-item projection mode, NOT % of revenue."""
        strat = _resolve_da_strategy(
            industry="bfsi", latest_rev=100_000, latest_dep=800, latest_net_block=None
        )
        assert strat["mode"] == "line_item"
        assert strat["base_value"] == 800
        assert strat["growth_rate"] == 0.05
        assert strat["source"] == "bfsi_line_item"

    def test_da_ratio_real_estate_from_net_block(self):
        strat = _resolve_da_strategy(
            industry="real_estate", latest_rev=10_000, latest_dep=200, latest_net_block=30_000
        )
        assert strat["mode"] == "ratio"
        # implied_dep = 30_000 / 30 = 1000, ratio = 1000/10_000 = 0.1
        assert strat["ratio"] == pytest.approx(0.1)
        assert strat["source"] == "real_estate_net_block"

    def test_da_ratio_real_estate_fallback_2pct(self):
        strat = _resolve_da_strategy(
            industry="real_estate", latest_rev=10_000, latest_dep=200, latest_net_block=None
        )
        assert strat["ratio"] == 0.02
        assert strat["source"] == "real_estate_fallback"

    @pytest.mark.parametrize(
        "token",
        [
            "energy",
            "power",
            "Power Generation",
            "Power Generation & Distribution",
            "Renewable Energy",
            "Electric Utilities",
            "Green Energy",
            "Power Transmission",
        ],
    )
    def test_da_ratio_energy_power_resolves_to_7pct(self, token):
        """Energy/power/renewable tokens → 7% ratio (NOT the 2% unresolved default)."""
        strat = _resolve_da_strategy(
            industry=token, latest_rev=10_000, latest_dep=600, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.07
        assert strat["source"] == "energy_power_default"
        assert strat["ratio"] != 0.02  # explicitly not the unresolved default
        assert any("power" in c.lower() or "renewable" in c.lower() for c in strat["caveats"])

    def test_da_ratio_genuinely_unknown_token_still_2pct(self):
        """A genuinely-unknown industry token must still fall through to 2% default."""
        strat = _resolve_da_strategy(
            industry="widgets", latest_rev=10_000, latest_dep=300, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.02
        assert strat["source"] == "unresolved_default"

    def test_da_ratio_unresolved_industry_uses_midpoint_with_caveat(self):
        """Unknown industry → 2% midpoint + explicit 'unresolved' caveat."""
        strat = _resolve_da_strategy(
            industry=None, latest_rev=10_000, latest_dep=300, latest_net_block=None
        )
        assert strat["mode"] == "ratio"
        assert strat["ratio"] == 0.02
        assert strat["source"] == "unresolved_default"
        assert len(strat["caveats"]) >= 1
        assert "unresolved" in strat["caveats"][0].lower()


# ---------------------------------------------------------------------------
# build_projections integration tests (E12 meta + routing)
# ---------------------------------------------------------------------------


class TestProjectionsAssumptionsMeta:
    def test_projection_assumptions_meta_emitted(self):
        """_projection_assumptions must be present with the three required keys."""
        rows = _synthetic_annual()
        result = build_projections(rows, industry="manufacturing")
        assert "_projection_assumptions" in result
        meta = result["_projection_assumptions"]
        assert "da_ratio_used" in meta
        assert "da_ratio_source" in meta
        assert "caveats" in meta
        assert meta["da_ratio_source"] == "manufacturing_default"

    def test_platform_da_flows_through_to_projections(self):
        """platform industry → 1% D&A applied to projected revenue."""
        rows = _synthetic_annual()
        result = build_projections(rows, industry="platform")
        meta = result["_projection_assumptions"]
        assert meta["da_ratio_used"] == 0.01
        assert meta["da_ratio_source"] == "platform_default"
        # And check that projected depreciation ≈ 1% of projected revenue
        base_y1 = result["projections"]["base"][0]
        assert base_y1["depreciation"] == pytest.approx(base_y1["revenue"] * 0.01, rel=1e-4)

    def test_bfsi_line_item_mode_in_projections(self):
        """BFSI → depreciation grows at 5%/yr from latest line item, not from revenue."""
        rows = _synthetic_annual()
        latest_dep = rows[0]["depreciation"]
        result = build_projections(rows, industry="bfsi")
        meta = result["_projection_assumptions"]
        assert meta["da_mode"] == "line_item"
        # da_ratio_used is None for line-item mode
        assert meta["da_ratio_used"] is None
        # Year-1 depreciation ≈ latest * 1.05, Year-2 ≈ latest * 1.05^2, Year-3 ≈ latest * 1.05^3
        base = result["projections"]["base"]
        assert base[0]["depreciation"] == pytest.approx(latest_dep * 1.05, rel=1e-3)
        assert base[2]["depreciation"] == pytest.approx(latest_dep * 1.05 ** 3, rel=1e-3)

    def test_unresolved_industry_emits_caveat_flag(self):
        rows = _synthetic_annual()
        result = build_projections(rows, industry=None)
        meta = result["_projection_assumptions"]
        assert meta["da_ratio_source"] == "unresolved_default"
        assert len(meta["caveats"]) >= 1
        assert "unresolved" in meta["caveats"][0].lower()

    def test_backwards_compat_no_industry_kwarg(self):
        """Existing callers that don't pass industry must still get valid output."""
        rows = _synthetic_annual()
        result = build_projections(rows)
        assert "projections" in result
        assert "bear" in result["projections"]
        # And the new meta block is emitted even with default industry=None
        assert "_projection_assumptions" in result


# ---------------------------------------------------------------------------
# Bug 1: US unit-free EPS ratio (gated on is_us). India factor path unchanged.
# ---------------------------------------------------------------------------


def _us_annual(n: int = 5, start_year: int = 2024) -> list[dict]:
    """US-like annuals: net_income in USD millions, num_shares a raw count
    (~15e9), eps in USD (~6). The India ni_to_eps_factor heuristic mis-scales
    these (~10x); the unit-free ratio is correct.
    """
    rows: list[dict] = []
    base_rev = 390_000.0   # USD millions
    base_ni = 95_000.0     # USD millions
    base_eps = 6.0         # USD per share
    for i in range(n):
        yr = start_year - i
        rev = base_rev * (0.95 ** i)
        ni = base_ni * (0.95 ** i)
        rows.append({
            "symbol": "AAPL",
            "fiscal_year_end": f"{yr}-09-28",
            "revenue": rev,
            "net_income": ni,
            "operating_profit": rev * 0.30,
            "depreciation": rev * 0.03,
            "interest": 0.0,
            "tax": ni * 0.15,
            "eps": base_eps * (0.95 ** i),
            "num_shares": 15_000_000_000.0,
        })
    return rows


class TestUsEpsRatio:
    def test_us_projected_eps_is_sane_not_10x(self):
        rows = _us_annual()
        result = build_projections(rows, is_us=True, industry="it_services")
        base = result["projections"]["base"]
        # Latest EPS ~6; projected base-case EPS should stay in a single-digit
        # USD band (~$6-12), NOT inflated to ~$60-90 by a crores factor.
        for p in base:
            assert 3.0 < p["eps"] < 20.0, f"US EPS out of sane band: {p['eps']}"
        # last_actual_eps surfaces the reported USD EPS, not a rescaled value.
        assert result["last_actual_eps"] == pytest.approx(6.0, rel=0.01)

    def test_india_path_byte_identical_when_is_us_false(self):
        """The default (is_us=False) India ni_to_eps_factor path must be
        unchanged — same output with and without the new kwarg defaulted."""
        rows = _synthetic_annual()
        default_out = build_projections(rows, industry="manufacturing")
        explicit_india = build_projections(rows, industry="manufacturing", is_us=False)
        assert default_out == explicit_india

    def test_us_ratio_changes_eps_vs_india_factor(self):
        """Same US data: is_us=True (ratio) yields a far smaller EPS than the
        India factor path would — proving the gate actually fixes the scale."""
        rows = _us_annual()
        us = build_projections(rows, is_us=True, industry="it_services")
        india = build_projections(rows, is_us=False, industry="it_services")
        us_eps = us["projections"]["base"][0]["eps"]
        india_eps = india["projections"]["base"][0]["eps"]
        # India path divides millions by a 15e9 raw share count → tiny/zero EPS;
        # the key assertion is they DIFFER and the US value is the sane one.
        assert us_eps != india_eps
        assert 3.0 < us_eps < 20.0
