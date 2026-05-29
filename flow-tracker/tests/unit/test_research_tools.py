"""Unit tests for flowtracker.research.tools — MCP tool wrappers.

These tests focus on NEWLY ADDED MCP tool wrappers (paginated tools,
TOC mode, BFSI variants, compliance gate tools, and all individual
pass-through wrappers). They complement
`tests/integration/test_mcp_tools_extended.py` which covers V2 macro
tools against a populated test DB.

Strategy:
- Most tests mock `flowtracker.research.tools.ResearchDataAPI` so a single
  fake backs every `ResearchDataAPI()` context-manager call. This exercises
  the wrapper's argument plumbing, default values, section routing and
  serialization without needing a populated database.
- A small number of happy-path tests use `populated_store` to verify the
  dedup cache and freshness metadata paths.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Autouse: reset the module-level dedup cache between tests so the
# ContextVar state cannot leak into sibling tests (including integration
# tests that exercise the same tool+args pairs).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tool_dedup_cache():
    from flowtracker.research import tools as t

    t._tool_result_cache.set({})
    yield
    t._tool_result_cache.set({})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(result: dict) -> Any:
    """Extract + JSON-decode the text payload from an MCP tool result."""
    assert "content" in result
    content = result["content"]
    assert isinstance(content, list) and len(content) > 0
    assert content[0]["type"] == "text"
    text = content[0]["text"]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text  # some tools return plain strings (business_profile)


class FakeAPI:
    """In-memory fake for ResearchDataAPI — every method records its call
    and returns a dict-shaped payload derived from its name.

    Use `patch_api(fake)` as a context manager to install the fake for the
    duration of a single handler invocation. The fake implements the
    context-manager protocol so the `with ResearchDataAPI() as api:` line
    works.
    """

    def __init__(self, overrides: dict[str, Any] | None = None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.overrides = overrides or {}

    # Context-manager plumbing
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __getattr__(self, name):
        # Stable generic behaviour for any get_* method the wrapper might call.
        def _method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name in self.overrides:
                val = self.overrides[name]
                return val(*args, **kwargs) if callable(val) else val
            # Default returns per name heuristic
            if name.endswith("_toc"):
                return {"sections": [], "symbol": args[0] if args else "?"}
            if name in {"get_data_freshness"}:
                return {"fresh": True}
            # Most data_api methods return dict or list; default to a dict
            return {"_fake": name, "args": list(args), "kwargs": kwargs}

        return _method

    # Special internal method used by get_quality_scores 'all'
    def _is_bfsi(self, symbol):
        self.calls.append(("_is_bfsi", (symbol,), {}))
        return self.overrides.get("_is_bfsi", False)


@contextmanager
def patch_api(fake: FakeAPI):
    """Patch `ResearchDataAPI` inside tools module with `fake`."""

    class _Factory:
        def __call__(self, *a, **kw):
            return fake

    with patch("flowtracker.research.tools.ResearchDataAPI", _Factory()):
        yield fake


# ---------------------------------------------------------------------------
# Module-level helpers: _parse_section + _cache_key
# ---------------------------------------------------------------------------


class TestParseSection:
    """`_parse_section` normalizes JSON-string lists emitted by agents."""

    def test_passes_through_list(self):
        from flowtracker.research.tools import _parse_section

        assert _parse_section(["a", "b"]) == ["a", "b"]

    def test_parses_json_array_string(self):
        from flowtracker.research.tools import _parse_section

        assert _parse_section('["snapshot","band"]') == ["snapshot", "band"]

    def test_passes_plain_string_unchanged(self):
        from flowtracker.research.tools import _parse_section

        assert _parse_section("snapshot") == "snapshot"

    def test_malformed_json_returns_as_is(self):
        from flowtracker.research.tools import _parse_section

        # Starts with "[" but is not valid JSON — fallback returns the string
        result = _parse_section("[not json")
        assert result == "[not json"


class TestCacheKey:
    """`_cache_key` produces a stable 16-char hash of (tool_name, args)."""

    def test_stable_hash(self):
        from flowtracker.research.tools import _cache_key

        k1 = _cache_key("foo", {"symbol": "SBIN", "q": 4})
        k2 = _cache_key("foo", {"q": 4, "symbol": "SBIN"})
        assert k1 == k2
        assert len(k1) == 16

    def test_different_args_different_key(self):
        from flowtracker.research.tools import _cache_key

        assert _cache_key("foo", {"symbol": "A"}) != _cache_key("foo", {"symbol": "B"})


# ---------------------------------------------------------------------------
# Screener APIs (Phase 2)
# ---------------------------------------------------------------------------


class TestScreenerPhaseTools:
    @pytest.mark.asyncio
    async def test_chart_data(self):
        from flowtracker.research.tools import get_chart_data

        fake = FakeAPI()
        with patch_api(fake):
            await get_chart_data.handler({"symbol": "SBIN", "chart_type": "pe"})
        # _market_of is the US-guard bookkeeping call; assert on the real dispatch.
        non_meta = [c for c in fake.calls if c[0] != "_market_of"]
        assert non_meta[0] == ("get_chart_data", ("SBIN", "pe"), {})

    @pytest.mark.asyncio
    async def test_yahoo_peers_uppercases_symbol(self):
        """get_yahoo_peers uppercases the input symbol before dispatch."""
        from flowtracker.research.tools import get_yahoo_peers

        fake = FakeAPI()
        with patch_api(fake):
            await get_yahoo_peers.handler({"symbol": "sbin"})
        non_meta = [c for c in fake.calls if c[0] != "_market_of"]
        assert non_meta[0] == ("get_yahoo_peer_comparison", ("SBIN",), {})

# ---------------------------------------------------------------------------
# Filings / company info
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Business profile vault tools (file system)
# ---------------------------------------------------------------------------


class TestBusinessProfileTools:
    @pytest.mark.asyncio
    async def test_save_business_profile_persists_to_vault(
        self, monkeypatch, tmp_path: Path
    ):
        from flowtracker.research.tools import save_business_profile

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        save_result = await save_business_profile.handler(
            {"symbol": "SBIN", "content": "# SBIN\n\nIndia's largest bank."}
        )
        save_text = save_result["content"][0]["text"]
        assert "Saved business profile" in save_text

        # Verify the profile was written to the vault path on disk.
        profile_path = tmp_path / "vault" / "stocks" / "SBIN" / "profile.md"
        assert profile_path.exists()
        assert "India's largest bank" in profile_path.read_text()


# ---------------------------------------------------------------------------
# FMP / quality scores — individual wrappers
# ---------------------------------------------------------------------------


class TestFmpAndQualityTools:
    @pytest.mark.asyncio
    async def test_fair_value(self):
        from flowtracker.research.tools import get_fair_value

        fake = FakeAPI()
        with patch_api(fake):
            await get_fair_value.handler({"symbol": "SBIN"})
        assert fake.calls[0][0] == "get_fair_value"

# ---------------------------------------------------------------------------
# Sector tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Deep quality / forensics tools
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Sector KPIs & Concall — paginated / TOC-mode tools
# ---------------------------------------------------------------------------


class TestSectorKpisAndConcallTools:
    """These are paginated (sub_section) wrappers: no sub_section returns
    the TOC; with sub_section returns the drilled-in data."""

    @pytest.mark.asyncio
    async def test_concall_insights_toc_mode(self):
        from flowtracker.research.tools import get_concall_insights

        fake = FakeAPI()
        with patch_api(fake):
            await get_concall_insights.handler({"symbol": "SBIN"})
        non_meta = [c for c in fake.calls if c[0] != "_market_of"]
        assert non_meta[0][0] == "get_concall_insights"
        assert non_meta[0][2] == {
            "section_filter": None,
            "quarter": None,
            "qa_topics": None,
        }

    @pytest.mark.asyncio
    async def test_concall_insights_drill(self):
        from flowtracker.research.tools import get_concall_insights

        fake = FakeAPI()
        with patch_api(fake):
            await get_concall_insights.handler(
                {"symbol": "SBIN", "sub_section": "operational_metrics"}
            )
        non_meta = [c for c in fake.calls if c[0] != "_market_of"]
        assert non_meta[0][2] == {
            "section_filter": "operational_metrics",
            "quarter": None,
            "qa_topics": None,
        }

    @pytest.mark.asyncio
    async def test_concall_insights_with_quarter_and_topics(self):
        from flowtracker.research.tools import get_concall_insights

        fake = FakeAPI()
        with patch_api(fake):
            await get_concall_insights.handler({
                "symbol": "SBIN",
                "quarter": "FY26-Q3",
                "qa_topics": ["margins", "guidance"],
            })
        non_meta = [c for c in fake.calls if c[0] != "_market_of"]
        assert non_meta[0][2] == {
            "section_filter": None,
            "quarter": "FY26-Q3",
            "qa_topics": ["margins", "guidance"],
        }


# ---------------------------------------------------------------------------
# Analytical profile + screener tools
# ---------------------------------------------------------------------------


class TestAnalyticalProfileAndScreenerTools:
    @pytest.mark.asyncio
    async def test_analytical_profile_happy(self):
        from flowtracker.research.tools import get_analytical_profile

        fake = FakeAPI(
            overrides={
                "get_analytical_profile": {"composite": 75, "f_score": 7},
                "get_data_freshness": {"ok": True},
            }
        )
        with patch_api(fake):
            result = await get_analytical_profile.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data["composite"] == 75
        # Freshness metadata is injected on non-error payloads
        assert "_meta" in data
        assert data["_meta"]["data_freshness"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_analytical_profile_error_skips_freshness(self):
        from flowtracker.research.tools import get_analytical_profile

        fake = FakeAPI(overrides={"get_analytical_profile": {"error": "no data"}})
        with patch_api(fake):
            result = await get_analytical_profile.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data == {"error": "no data"}  # no _meta injected on error

    @pytest.mark.asyncio
    async def test_screen_stocks(self):
        from flowtracker.research.tools import screen_stocks

        fake = FakeAPI(
            overrides={"screen_stocks": [{"symbol": "SBIN", "f_score": 8}]}
        )
        with patch_api(fake):
            result = await screen_stocks.handler({"filters": {"f_score_min": 7}})
        data = _parse(result)
        assert data == [{"symbol": "SBIN", "f_score": 8}]
        assert fake.calls[0] == ("screen_stocks", ({"f_score_min": 7},), {})


# ---------------------------------------------------------------------------
# V2 macro tool — get_fundamentals (TOC mode + section routing)
# ---------------------------------------------------------------------------


class TestGetFundamentalsV2:
    """get_fundamentals added the TOC/wave pattern: no section → TOC payload;
    explicit section(s) → drill in. Tests here exercise the routing layer."""

    @pytest.mark.asyncio
    async def test_no_section_returns_toc(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI(
            overrides={"get_fundamentals_toc": {"sections": ["a", "b"], "symbol": "SBIN"}}
        )
        with patch_api(fake):
            result = await get_fundamentals.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data["sections"] == ["a", "b"]
        assert any(c[0] == "get_fundamentals_toc" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_section_toc_keyword_returns_toc(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI(
            overrides={"get_fundamentals_toc": {"sections": [], "symbol": "SBIN"}}
        )
        with patch_api(fake):
            await get_fundamentals.handler({"symbol": "SBIN", "section": "toc"})
        assert any(c[0] == "get_fundamentals_toc" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_single_section_quarterly_results(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI()
        with patch_api(fake):
            await get_fundamentals.handler(
                {"symbol": "SBIN", "section": "quarterly_results", "quarters": 4}
            )
        assert any(
            c[0] == "get_quarterly_results" and c[1] == ("SBIN", 4) for c in fake.calls
        )

    @pytest.mark.asyncio
    async def test_list_sections_routes_each(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_fundamentals.handler(
                {
                    "symbol": "SBIN",
                    "section": ["quarterly_results", "annual_financials", "ratios"],
                }
            )
        data = _parse(result)
        assert set(data.keys()) >= {"quarterly_results", "annual_financials", "ratios"}

    @pytest.mark.asyncio
    async def test_all_section_returns_warning_and_full_payload(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_fundamentals.handler(
                {"symbol": "SBIN", "section": "all"}
            )
        data = _parse(result)
        assert "_warning" in data
        # All 14 sections present
        for key in (
            "quarterly_results",
            "annual_financials",
            "ratios",
            "quarterly_balance_sheet",
            "quarterly_cash_flow",
            "expense_breakdown",
            "growth_rates",
            "capital_allocation",
            "rate_sensitivity",
            "cagr_table",
            "cost_structure",
            "balance_sheet_detail",
            "cash_flow_quality",
            "working_capital",
        ):
            assert key in data

    @pytest.mark.asyncio
    async def test_unknown_section_error_envelope(self):
        from flowtracker.research.tools import get_fundamentals

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_fundamentals.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data
        assert "bogus" in data["error"]

    @pytest.mark.asyncio
    async def test_section_routes_all_branches(self):
        """Exercise every branch of _get_fundamentals_section."""
        from flowtracker.research.tools import get_fundamentals

        sections = [
            "quarterly_results",
            "annual_financials",
            "ratios",
            "quarterly_balance_sheet",
            "quarterly_cash_flow",
            "expense_breakdown",
            "growth_rates",
            "capital_allocation",
            "rate_sensitivity",
            "cagr_table",
            "cost_structure",
            "balance_sheet_detail",
            "cash_flow_quality",
            "working_capital",
        ]
        for s in sections:
            fake = FakeAPI()
            with patch_api(fake):
                await get_fundamentals.handler({"symbol": "SBIN", "section": s})
            # At least one api call should have been dispatched (excluding freshness)
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1


# ---------------------------------------------------------------------------
# V2 macro tool — get_quality_scores (BFSI routing)
# ---------------------------------------------------------------------------


class TestGetQualityScoresV2:
    @pytest.mark.asyncio
    async def test_section_all_non_bfsi(self):
        from flowtracker.research.tools import get_quality_scores

        fake = FakeAPI(overrides={"_is_bfsi": False})
        with patch_api(fake):
            result = await get_quality_scores.handler(
                {"symbol": "SBIN", "section": "all"}
            )
        data = _parse(result)
        # Non-BFSI path: bfsi is skipped but others are computed
        assert data["bfsi"] == {"skipped": "not applicable for non-BFSI"}
        assert isinstance(data["earnings_quality"], dict)

    @pytest.mark.asyncio
    async def test_section_all_bfsi_skips_non_applicable(self):
        from flowtracker.research.tools import get_quality_scores

        fake = FakeAPI(overrides={"_is_bfsi": True})
        with patch_api(fake):
            result = await get_quality_scores.handler(
                {"symbol": "HDFCBANK", "section": "all"}
            )
        data = _parse(result)
        # BFSI path: earnings_quality/beneish/capex_cycle skipped
        assert data["earnings_quality"] == {"skipped": "not applicable for BFSI"}
        assert data["beneish"] == {"skipped": "not applicable for BFSI"}
        assert data["capex_cycle"] == {"skipped": "not applicable for BFSI"}
        # BFSI-specific tool actually called
        assert isinstance(data["bfsi"], dict)

    @pytest.mark.asyncio
    async def test_single_section_piotroski(self):
        from flowtracker.research.tools import get_quality_scores

        fake = FakeAPI()
        with patch_api(fake):
            await get_quality_scores.handler(
                {"symbol": "SBIN", "section": "piotroski"}
            )
        assert any(c[0] == "get_piotroski_score" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_quality_scores

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_quality_scores.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_list_sections_routes_each(self):
        from flowtracker.research.tools import get_quality_scores

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_quality_scores.handler(
                {
                    "symbol": "SBIN",
                    "section": ["piotroski", "dupont", "altman_zscore"],
                }
            )
        data = _parse(result)
        assert {"piotroski", "dupont", "altman_zscore"}.issubset(data.keys())

    @pytest.mark.asyncio
    async def test_all_individual_sections_routable(self):
        """Exercise every branch of _get_quality_scores_section."""
        from flowtracker.research.tools import get_quality_scores

        sections = [
            "earnings_quality",
            "piotroski",
            "beneish",
            "dupont",
            "common_size",
            "capex_cycle",
            "bfsi",
            "subsidiary",
            "insurance",
            "metals",
            "realestate",
            "telecom",
            "power",
            "sector_health",
            "risk_flags",
            "forensic_checks",
            "improvement_metrics",
            "capital_discipline",
            "incremental_roce",
            "altman_zscore",
            "working_capital",
            "operating_leverage",
            "fcf_yield",
            "tax_rate_analysis",
            "receivables_quality",
        ]
        for s in sections:
            fake = FakeAPI()
            with patch_api(fake):
                result = await get_quality_scores.handler(
                    {"symbol": "SBIN", "section": s}
                )
            data = _parse(result)
            # Error only if bogus — all listed are valid
            assert not (isinstance(data, dict) and data.get("error", "").startswith("Unknown"))


# ---------------------------------------------------------------------------
# V2 macro tool — get_ownership (TOC mode + routing)
# ---------------------------------------------------------------------------


class TestGetOwnershipV2:
    @pytest.mark.asyncio
    async def test_no_section_returns_toc(self):
        from flowtracker.research.tools import get_ownership

        fake = FakeAPI(
            overrides={
                "get_ownership_toc": {"snapshot": {}, "symbol": "SBIN"},
            }
        )
        with patch_api(fake):
            result = await get_ownership.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data["symbol"] == "SBIN"
        assert any(c[0] == "get_ownership_toc" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_section_all_includes_warning(self):
        from flowtracker.research.tools import get_ownership

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_ownership.handler(
                {"symbol": "SBIN", "section": "all"}
            )
        data = _parse(result)
        assert "_warning" in data
        for key in (
            "shareholding",
            "changes",
            "insider",
            "bulk_block",
            "mf_holdings",
            "mf_changes",
            "shareholder_detail",
            "promoter_pledge",
            "mf_conviction",
        ):
            assert key in data

    @pytest.mark.asyncio
    async def test_single_section_insider(self):
        from flowtracker.research.tools import get_ownership

        fake = FakeAPI()
        with patch_api(fake):
            await get_ownership.handler(
                {"symbol": "SBIN", "section": "insider", "days": 365}
            )
        # Default 1825 replaced with 365
        assert any(
            c[0] == "get_insider_transactions" and c[1] == ("SBIN", 365)
            for c in fake.calls
        )

    @pytest.mark.asyncio
    async def test_all_individual_sections_routable(self):
        from flowtracker.research.tools import get_ownership

        for s in [
            "shareholding",
            "changes",
            "insider",
            "bulk_block",
            "mf_holdings",
            "mf_changes",
            "shareholder_detail",
            "promoter_pledge",
            "mf_conviction",
        ]:
            fake = FakeAPI()
            with patch_api(fake):
                await get_ownership.handler({"symbol": "SBIN", "section": s})
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section_error(self):
        from flowtracker.research.tools import get_ownership

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_ownership.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_json_string_section_list(self):
        """Agents sometimes send a JSON-encoded array string."""
        from flowtracker.research.tools import get_ownership

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_ownership.handler(
                {"symbol": "SBIN", "section": '["shareholding","changes"]'}
            )
        data = _parse(result)
        assert set(data.keys()) >= {"shareholding", "changes"}


# ---------------------------------------------------------------------------
# V2 macro tools — get_valuation / get_fair_value_analysis / get_peer_sector /
# get_estimates / get_market_context / get_company_context / get_events_actions
# ---------------------------------------------------------------------------


class TestValuationMacroV2:
    @pytest.mark.asyncio
    async def test_single_section_wacc(self):
        from flowtracker.research.tools import get_valuation

        fake = FakeAPI()
        with patch_api(fake):
            await get_valuation.handler({"symbol": "SBIN", "section": "wacc"})
        assert any(c[0] == "get_wacc_params" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_sotp_with_no_subsidiaries_returns_info(self):
        """When api.get_listed_subsidiaries returns None, tool returns a
        default {'info': ...} payload rather than raising."""
        from flowtracker.research.tools import get_valuation

        fake = FakeAPI(overrides={"get_listed_subsidiaries": None})
        with patch_api(fake):
            result = await get_valuation.handler(
                {"symbol": "SBIN", "section": "sotp"}
            )
        data = _parse(result)
        assert "info" in data

    @pytest.mark.asyncio
    async def test_section_list_valuation(self):
        from flowtracker.research.tools import get_valuation

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_valuation.handler(
                {"symbol": "SBIN", "section": ["snapshot", "band"]}
            )
        data = _parse(result)
        assert "snapshot" in data and "band" in data

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_valuation

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_valuation.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data


class TestFairValueAnalysisV2:
    @pytest.mark.asyncio
    async def test_all_individual_sections(self):
        from flowtracker.research.tools import get_fair_value_analysis

        for s in ("combined", "dcf", "dcf_history", "reverse_dcf", "projections"):
            fake = FakeAPI()
            with patch_api(fake):
                await get_fair_value_analysis.handler(
                    {"symbol": "SBIN", "section": s}
                )
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_section_list(self):
        from flowtracker.research.tools import get_fair_value_analysis

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_fair_value_analysis.handler(
                {"symbol": "SBIN", "section": ["dcf", "reverse_dcf"]}
            )
        data = _parse(result)
        assert "dcf" in data and "reverse_dcf" in data

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_fair_value_analysis

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_fair_value_analysis.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data


class TestPeerSectorV2:
    @pytest.mark.asyncio
    async def test_no_section_returns_toc(self):
        from flowtracker.research.tools import get_peer_sector

        fake = FakeAPI(
            overrides={"get_peer_sector_toc": {"sections": [], "symbol": "SBIN"}}
        )
        with patch_api(fake):
            await get_peer_sector.handler({"symbol": "SBIN"})
        assert any(c[0] == "get_peer_sector_toc" for c in fake.calls)

    @pytest.mark.asyncio
    async def test_all_section_warning(self):
        from flowtracker.research.tools import get_peer_sector

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_peer_sector.handler(
                {"symbol": "SBIN", "section": "all"}
            )
        data = _parse(result)
        assert "_warning" in data

    @pytest.mark.asyncio
    async def test_all_individual_sections(self):
        from flowtracker.research.tools import get_peer_sector

        for s in (
            "peer_table",
            "peer_metrics",
            "peer_growth",
            "valuation_matrix",
            "benchmarks",
            "sector_overview",
            "sector_flows",
            "sector_valuations",
            "yahoo_peers",
        ):
            fake = FakeAPI()
            with patch_api(fake):
                await get_peer_sector.handler({"symbol": "SBIN", "section": s})
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_peer_sector

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_peer_sector.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data


class TestEstimatesV2:
    @pytest.mark.asyncio
    async def test_all_individual_sections(self):
        from flowtracker.research.tools import get_estimates

        for s in (
            "consensus",
            "surprises",
            "revisions",
            "momentum",
            "revenue",
            "growth",
            "analyst_grades",
            "price_targets",
        ):
            fake = FakeAPI()
            with patch_api(fake):
                await get_estimates.handler({"symbol": "SBIN", "section": s})
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_estimates

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_estimates.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data


class TestMarketContextV2:
    @pytest.mark.asyncio
    async def test_all_individual_sections(self):
        from flowtracker.research.tools import get_market_context

        for s in (
            "delivery",
            "macro",
            "fii_dii_streak",
            "fii_dii_flows",
            "technicals",
            "price_performance",
            "delivery_analysis",
            "commodities",
            "institutional_consensus",
        ):
            fake = FakeAPI()
            with patch_api(fake):
                await get_market_context.handler({"symbol": "SBIN", "section": s})
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_market_context

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_market_context.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.xfail(
        reason=(
            "F&O derivatives data (PCR, OI, rollover, fo_enabled) is mandated "
            "by the technical agent prompt (prompts.py:998) but the underlying "
            "infrastructure does not exist: no DB table, no client (FMP/NSE/"
            "Screener), no cron populates it, and get_technical_indicators() "
            "only returns RSI/SMA/MACD/ADX. Shipping this requires a new NSE "
            "derivatives client + table + cron + fo_enabled symbol list "
            "(~200 stocks). Tracked as plan-v2 B6 tenet gap — eval flagged "
            "HDFCBANK/GODREJPROP/ETERNAL/NTPC technical reports."
        ),
        strict=True,
    )
    @pytest.mark.asyncio
    async def test_technicals_includes_fo_fields_for_liquid_stock(self):
        """Contract test: for an F&O-enabled Nifty 50 stock, get_market_context(
        section='technicals') must expose PCR, OI, rollover, and fo_enabled=True.

        Uses the real ResearchDataAPI against the local DB (not FakeAPI), so it
        fails as long as the derivatives data is not actually ingested. Flip to
        non-xfail once the ingestion pipeline lands.
        """
        from flowtracker.research.tools import get_market_context

        result = await get_market_context.handler(
            {"symbol": "HDFCBANK", "section": "technicals"}
        )
        data = _parse(result)
        # technicals section returns a list[dict] or a dict; normalize to dict
        record = data[0] if isinstance(data, list) and data else data
        assert isinstance(record, dict), f"expected dict, got {type(record)}"
        assert record.get("fo_enabled") is True, "HDFCBANK is F&O-enabled"
        assert record.get("pcr") is not None, "PCR (Put-Call Ratio) must be present"
        assert record.get("open_interest") is not None, "Open Interest must be present"
        assert record.get("rollover_pct") is not None, "Rollover % must be present"


class TestCompanyContextV2:
    @pytest.mark.asyncio
    async def test_all_individual_sections(self, monkeypatch, tmp_path):
        from flowtracker.research.tools import get_company_context

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        for s in (
            "info",
            "profile",
            "documents",
            "business_profile",
            "concall_insights",
            "sector_kpis",
            "filings",
        ):
            fake = FakeAPI()
            with patch_api(fake):
                await get_company_context.handler(
                    {"symbol": "SBIN", "section": s}
                )
            # business_profile returns from filesystem, does not call api
            if s != "business_profile":
                non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
                assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_company_context

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_company_context.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_section_list(self, monkeypatch, tmp_path):
        from flowtracker.research.tools import get_company_context

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        fake = FakeAPI()
        with patch_api(fake):
            result = await get_company_context.handler(
                {"symbol": "SBIN", "section": ["info", "profile"]}
            )
        data = _parse(result)
        assert "info" in data and "profile" in data


class TestEventsActionsV2:
    @pytest.mark.asyncio
    async def test_all_individual_sections(self):
        from flowtracker.research.tools import get_events_actions

        for s in (
            "events",
            "dividends",
            "corporate_actions",
            "adjusted_eps",
            "catalysts",
            "material_events",
            "dividend_policy",
        ):
            fake = FakeAPI()
            with patch_api(fake):
                await get_events_actions.handler(
                    {"symbol": "SBIN", "section": s}
                )
            non_meta = [c for c in fake.calls if c[0] != "get_data_freshness"]
            assert len(non_meta) >= 1

    @pytest.mark.asyncio
    async def test_unknown_section(self):
        from flowtracker.research.tools import get_events_actions

        fake = FakeAPI()
        with patch_api(fake):
            result = await get_events_actions.handler(
                {"symbol": "SBIN", "section": "bogus"}
            )
        data = _parse(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# Stock news
# ---------------------------------------------------------------------------


class TestStockNewsTool:
    @pytest.mark.asyncio
    async def test_stock_news_happy(self):
        from flowtracker.research.tools import get_stock_news

        fake = FakeAPI(
            overrides={
                "get_stock_news": [
                    {"title": "T", "source": "S", "date": "2026-04-01"}
                ]
            }
        )
        with patch_api(fake):
            result = await get_stock_news.handler({"symbol": "SBIN", "days": 30})
        data = _parse(result)
        assert isinstance(data, list) and data[0]["title"] == "T"

    @pytest.mark.asyncio
    async def test_stock_news_default_days(self):
        from flowtracker.research.tools import get_stock_news

        fake = FakeAPI(overrides={"get_stock_news": []})
        with patch_api(fake):
            await get_stock_news.handler({"symbol": "SBIN"})
        assert fake.calls[0][1] == ("SBIN", 90)


# ---------------------------------------------------------------------------
# render_chart / get_composite_score — non-data-api wrappers
# ---------------------------------------------------------------------------


class TestRenderChartTool:
    @pytest.mark.asyncio
    async def test_render_chart_dispatches(self):
        from flowtracker.research import tools as t

        with patch.object(
            t,
            "__name__",
            t.__name__,  # sanity
        ):
            pass

        # Patch the charts.render_chart symbol consumed inside the handler
        with patch(
            "flowtracker.research.charts.render_chart",
            return_value={"path": "/tmp/c.png", "embed_markdown": "![c](/tmp/c.png)"},
        ) as m:
            result = await t.render_chart.handler(
                {"symbol": "SBIN", "chart_type": "price"}
            )
        m.assert_called_once_with("SBIN", "price")
        data = _parse(result)
        assert data["path"] == "/tmp/c.png"


class TestCompositeScoreTool:
    @pytest.mark.asyncio
    async def test_composite_score_none_returns_message(self):
        from flowtracker.research.tools import get_composite_score

        fake_store = MagicMock()
        fake_store.__enter__ = MagicMock(return_value=fake_store)
        fake_store.__exit__ = MagicMock(return_value=False)

        fake_engine = MagicMock()
        fake_engine.score_stock = MagicMock(return_value=None)

        with patch("flowtracker.store.FlowStore", return_value=fake_store), patch(
            "flowtracker.screener_engine.ScreenerEngine", return_value=fake_engine
        ):
            result = await get_composite_score.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data == "No scoring data available"

    @pytest.mark.asyncio
    async def test_composite_score_returns_factor_dict(self):
        from flowtracker.research.tools import get_composite_score

        fake_factor = MagicMock(
            factor="ownership", score=75, raw_value=0.7, detail="good"
        )
        fake_score = MagicMock(
            symbol="SBIN", composite_score=82, factors=[fake_factor]
        )

        fake_store = MagicMock()
        fake_store.__enter__ = MagicMock(return_value=fake_store)
        fake_store.__exit__ = MagicMock(return_value=False)

        fake_engine = MagicMock()
        fake_engine.score_stock = MagicMock(return_value=fake_score)

        with patch("flowtracker.store.FlowStore", return_value=fake_store), patch(
            "flowtracker.screener_engine.ScreenerEngine", return_value=fake_engine
        ):
            result = await get_composite_score.handler({"symbol": "SBIN"})
        data = _parse(result)
        assert data["symbol"] == "SBIN"
        assert data["composite_score"] == 82
        assert data["factors"][0]["factor"] == "ownership"


# ---------------------------------------------------------------------------
# calculate tool — all named operations + expr fallback + error paths
# ---------------------------------------------------------------------------


class TestCalculateTool:
    @pytest.mark.asyncio
    async def test_shares_to_value_cr(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "shares_to_value_cr", "a": "100000000", "b": "500"}
        )
        data = _parse(result)
        # 1e8 × 500 / 1e7 = 5000 Cr
        assert data["value_cr"] == 5000.0
        # `unit` field was deliberately removed in prior commit
        # ("strip rupee symbol + unit labels from calculate output")
        assert "calculation" in data

    @pytest.mark.asyncio
    async def test_per_share_to_total_cr(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "per_share_to_total_cr", "a": "10", "b": "100000000"}
        )
        data = _parse(result)
        assert data["total_cr"] == 100.0

    @pytest.mark.asyncio
    async def test_total_cr_to_per_share(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "total_cr_to_per_share", "a": "100", "b": "100000000"}
        )
        data = _parse(result)
        assert data["per_share"] == 10.0

    @pytest.mark.asyncio
    async def test_total_cr_to_per_share_div_zero(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "total_cr_to_per_share", "a": "100", "b": "0"}
        )
        data = _parse(result)
        assert data["per_share"] == 0

    @pytest.mark.asyncio
    async def test_pe_from_price_eps(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pe_from_price_eps", "a": "100", "b": "5"}
        )
        data = _parse(result)
        assert data["pe"] == 20.0

    @pytest.mark.asyncio
    async def test_pe_from_price_eps_zero(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pe_from_price_eps", "a": "100", "b": "0"}
        )
        data = _parse(result)
        assert data["pe"] == 0

    @pytest.mark.asyncio
    async def test_eps_from_pat_shares(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "eps_from_pat_shares", "a": "1000", "b": "100000000"}
        )
        data = _parse(result)
        assert data["eps"] == 100.0

    @pytest.mark.asyncio
    async def test_fair_value(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "fair_value", "a": "20", "b": "50"}
        )
        data = _parse(result)
        assert data["fair_value"] == 1000.0

    @pytest.mark.asyncio
    async def test_growth_rate(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "growth_rate", "a": "100", "b": "120"}
        )
        data = _parse(result)
        assert data["growth_pct"] == 20.0

    @pytest.mark.asyncio
    async def test_growth_rate_zero(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "growth_rate", "a": "0", "b": "120"}
        )
        data = _parse(result)
        assert data["growth_pct"] == 0

    @pytest.mark.asyncio
    async def test_cagr_hint(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "cagr", "a": "100", "b": "200"}
        )
        data = _parse(result)
        assert "note" in data

    @pytest.mark.asyncio
    async def test_mcap_cr(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "mcap_cr", "a": "100", "b": "100000000"}
        )
        data = _parse(result)
        assert data["mcap_cr"] == 1000.0

    @pytest.mark.asyncio
    async def test_margin_of_safety(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "margin_of_safety", "a": "1000", "b": "800"}
        )
        data = _parse(result)
        assert data["mos_pct"] == 20.0

    @pytest.mark.asyncio
    async def test_margin_of_safety_div_zero(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "margin_of_safety", "a": "0", "b": "800"}
        )
        data = _parse(result)
        assert data["mos_pct"] == 0

    @pytest.mark.asyncio
    async def test_annualize_quarterly_ignores_b(self):
        """annualize_quarterly needs only 'a'; unparseable 'b' is OK."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "annualize_quarterly", "a": "100", "b": "0"}
        )
        data = _parse(result)
        assert data["annualized"] == 400.0

    @pytest.mark.asyncio
    async def test_pct_of(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pct_of", "a": "25", "b": "100"}
        )
        data = _parse(result)
        assert data["pct"] == 25.0

    @pytest.mark.asyncio
    async def test_ratio(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "ratio", "a": "50", "b": "100"}
        )
        data = _parse(result)
        assert data["ratio"] == 0.5

    @pytest.mark.asyncio
    async def test_ratio_div_zero(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "ratio", "a": "50", "b": "0"}
        )
        data = _parse(result)
        assert data["ratio"] == 0

    @pytest.mark.asyncio
    async def test_expr_happy(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "expr", "a": "(74 - 47.67) / 2", "b": "0"}
        )
        data = _parse(result)
        assert data["result"] == pytest.approx(13.165)
        assert "expression" in data

    @pytest.mark.asyncio
    async def test_expr_rejects_invalid_chars(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "expr", "a": "__import__('os')", "b": "0"}
        )
        data = _parse(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_unknown_operation(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "bogus_op", "a": "1", "b": "2"}
        )
        data = _parse(result)
        assert "error" in data
        # Phase 1-B: the enum guard rejects unknown ops up front with a
        # standardized did-you-mean envelope (replaces the old in-chain
        # "Unknown operation" message).
        assert data["error"].startswith("Invalid operation")
        assert "valid_values" in data and "suggestion" in data

    @pytest.mark.asyncio
    async def test_timestamp_discipline_no_args_is_clean(self):
        """Back-compat: no inputs_as_of/mcap_as_of → no warning, no hint."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pct_of", "a": "10", "b": "100"}
        )
        data = _parse(result)
        assert data["pct"] == 10.0
        assert "timestamp_discipline" not in data

    @pytest.mark.asyncio
    async def test_timestamp_discipline_matching_quarters_no_warning(self):
        """inputs_as_of == mcap_as_of (both current) → clean result."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler({
            "operation": "pct_of", "a": "10", "b": "100",
            "inputs_as_of": "2026-Q1", "mcap_as_of": "2026-Q1",
        })
        data = _parse(result)
        assert data["pct"] == 10.0
        assert "timestamp_discipline" not in data

    @pytest.mark.asyncio
    async def test_timestamp_discipline_mismatch_emits_warning(self):
        """Historical %pt multiplied by current mcap → warning must fire."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler({
            "operation": "pct_of", "a": "10", "b": "100",
            "inputs_as_of": "2023-Q4", "mcap_as_of": "2026-Q1",
        })
        data = _parse(result)
        assert "timestamp_discipline" in data
        assert "HISTORICAL_MCAP_MISMATCH" in data["timestamp_discipline"]
        assert "2023-Q4" in data["timestamp_discipline"]
        assert "2026-Q1" in data["timestamp_discipline"]
        assert "20-50%" in data["timestamp_discipline"]

    @pytest.mark.asyncio
    async def test_timestamp_discipline_mismatch_on_expr(self):
        """Mismatch warning also fires for operation='expr' (common flow path)."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler({
            "operation": "expr", "a": "10 * 1000000 / 100", "b": "0",
            "inputs_as_of": "2023-Q4", "mcap_as_of": "2026-Q1",
        })
        data = _parse(result)
        assert data["result"] == pytest.approx(100000.0)
        assert "timestamp_discipline" in data
        assert "HISTORICAL_MCAP_MISMATCH" in data["timestamp_discipline"]

    @pytest.mark.asyncio
    async def test_non_numeric_args_return_parse_error(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pe_from_price_eps", "a": "not-a-number", "b": "5"}
        )
        data = _parse(result)
        assert "error" in data
        assert "not a valid numeric string" in data["error"]

    @pytest.mark.asyncio
    async def test_exception_path_returns_error(self):
        """If the op body raises an unexpected exception, the tool wraps it."""
        from flowtracker.research.tools import calculate

        # Trigger an error by breaking the op table — use expr eval with a
        # valid charset but divide-by-zero inside eval
        result = await calculate.handler(
            {"operation": "expr", "a": "1/0", "b": "0"}
        )
        data = _parse(result)
        assert "error" in data

    # --- Defensive unit checks: share counts must be raw integer counts ---

    @pytest.mark.asyncio
    async def test_total_cr_to_per_share_rejects_lakhs_input(self):
        """BANKBARODA bug: agent passed 51,713.62 (lakhs of shares) instead of raw count.

        The tool must reject implausibly-low share counts loud enough that
        the agent reads the error and self-corrects.
        """
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "total_cr_to_per_share", "a": "100000", "b": "51713.62"}
        )
        data = _parse(result)
        assert "error" in data
        assert "UNIT_ERROR" in data["error"]
        assert "total_cr_to_per_share" in data["error"]
        assert "RAW share count" in data["error"]
        # Must reference the actually-passed value so the agent sees what went wrong
        assert "51713" in data["error"]

    @pytest.mark.asyncio
    async def test_total_cr_to_per_share_happy_path_nestleind(self):
        """Realistic NESTLEIND inputs → ~₹381 per share."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "total_cr_to_per_share", "a": "36780", "b": "964157160"}
        )
        data = _parse(result)
        assert "error" not in data
        # ₹36,780 Cr / 964M shares = ₹381.49 per share
        assert data["per_share"] == pytest.approx(381.49, rel=0.01)

    @pytest.mark.asyncio
    async def test_per_share_to_total_cr_rejects_low_shares(self):
        """`per_share_to_total_cr` shares is on `b` — must also reject lakhs."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "per_share_to_total_cr", "a": "10", "b": "9641"}
        )
        data = _parse(result)
        assert "error" in data
        assert "UNIT_ERROR" in data["error"]

    @pytest.mark.asyncio
    async def test_shares_to_value_cr_rejects_low_shares_on_a(self):
        """`shares_to_value_cr` has shares on `a` — defensive check fires on `a`."""
        from flowtracker.research.tools import calculate

        # 96 crore shares (passed as if it were raw count) — clearly wrong
        result = await calculate.handler(
            {"operation": "shares_to_value_cr", "a": "96", "b": "2400"}
        )
        data = _parse(result)
        assert "error" in data
        assert "UNIT_ERROR" in data["error"]
        assert "'a'=96" in data["error"]

    @pytest.mark.asyncio
    async def test_eps_from_pat_shares_rejects_low_shares(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "eps_from_pat_shares", "a": "1000", "b": "100"}
        )
        data = _parse(result)
        assert "error" in data
        assert "UNIT_ERROR" in data["error"]

    @pytest.mark.asyncio
    async def test_mcap_cr_rejects_low_shares(self):
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "mcap_cr", "a": "2400", "b": "96"}
        )
        data = _parse(result)
        assert "error" in data
        assert "UNIT_ERROR" in data["error"]

    @pytest.mark.asyncio
    async def test_unit_check_does_not_fire_for_zero_shares(self):
        """b=0 must still go through divide-by-zero handling, not unit-error path."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "total_cr_to_per_share", "a": "100", "b": "0"}
        )
        data = _parse(result)
        # No unit error — divide-by-zero path returns per_share=0 cleanly
        assert "error" not in data
        assert data["per_share"] == 0

    @pytest.mark.asyncio
    async def test_unit_check_does_not_fire_for_unrelated_ops(self):
        """`pct_of`, `ratio`, `growth_rate` etc. don't take shares — small `b` is fine."""
        from flowtracker.research.tools import calculate

        result = await calculate.handler(
            {"operation": "pct_of", "a": "25", "b": "100"}
        )
        data = _parse(result)
        assert "error" not in data
        assert data["pct"] == 25.0


# ---------------------------------------------------------------------------
# Dedup cache — same call twice returns stub on 2nd invocation
# ---------------------------------------------------------------------------


class TestDedupCache:
    @pytest.mark.asyncio
    async def test_same_args_returns_stub_second_call(self, monkeypatch):
        """Two identical calls in the same ContextVar scope dedupe the 2nd."""
        from flowtracker.research import tools as t

        # Reset the context var for this test run
        t._tool_result_cache.set({})

        fake = FakeAPI(overrides={"get_macro_indicators": {"cpi": 5.0}})
        with patch_api(fake):
            first = await t.get_macro_indicators.handler({})
            second = await t.get_macro_indicators.handler({})

        first_text = first["content"][0]["text"]
        second_text = second["content"][0]["text"]
        assert "Identical to previous call" in second_text
        assert first_text != second_text


# ---------------------------------------------------------------------------
# Tool registry exports
# ---------------------------------------------------------------------------


class TestToolRegistries:
    """Sanity-check the module-level registries are populated."""

    def test_v2_registry_has_core_tools(self):
        from flowtracker.research.tools import (
            RESEARCH_TOOLS,
            get_fundamentals,
            get_ownership,
            get_quality_scores,
        )

        assert get_fundamentals in RESEARCH_TOOLS
        assert get_ownership in RESEARCH_TOOLS
        assert get_quality_scores in RESEARCH_TOOLS

    def test_specialist_registries_nonempty(self):
        from flowtracker.research.tools import (
            BUSINESS_AGENT_TOOLS,
            FINANCIAL_AGENT_TOOLS,
            NEWS_AGENT_TOOLS,
            OWNERSHIP_AGENT_TOOLS,
            RISK_AGENT_TOOLS,
            SECTOR_AGENT_TOOLS,
            TECHNICAL_AGENT_TOOLS,
            VALUATION_AGENT_TOOLS,
        )

        for reg in (
            BUSINESS_AGENT_TOOLS,
            FINANCIAL_AGENT_TOOLS,
            OWNERSHIP_AGENT_TOOLS,
            VALUATION_AGENT_TOOLS,
            RISK_AGENT_TOOLS,
            TECHNICAL_AGENT_TOOLS,
            SECTOR_AGENT_TOOLS,
            NEWS_AGENT_TOOLS,
        ):
            assert len(reg) > 0


# ---------------------------------------------------------------------------
# classify_completeness + _count_rows (C-2c)
# ---------------------------------------------------------------------------


class TestClassifyCompleteness:
    """Helper used by agent.py/evals to grade tool-use discipline."""

    def test_none_is_empty(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness(None) == ("empty", 0)

    def test_empty_dict_is_empty(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({}) == ("empty", 0)

    def test_empty_list_is_empty(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness([]) == ("empty", 0)

    def test_empty_string_is_empty(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness("") == ("empty", 0)

    def test_whitespace_string_is_empty(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness("   \n  \t ") == ("empty", 0)

    def test_populated_list_is_full(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness([1, 2, 3]) == ("full", 3)
        assert classify_completeness([{"a": 1}]) == ("full", 1)

    def test_error_dict(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"error": "boom"}) == ("error", None)
        assert classify_completeness({"error": "boom", "rows": [1, 2]}) == (
            "error",
            None,
        )

    def test_error_false_not_error(self):
        # Falsy error key should NOT trigger error classification
        from flowtracker.research.tools import classify_completeness

        result = classify_completeness({"error": None, "rows": [1]})
        assert result[0] == "full"
        assert result[1] == 1

    def test_truncated_underscore_flag(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"_truncated": True, "rows": [1, 2, 3]}) == (
            "truncated",
            3,
        )

    def test_truncated_no_underscore_flag(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"truncated": True, "items": [1, 2]}) == (
            "truncated",
            2,
        )

    def test_truncated_no_rows(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"_truncated": True, "note": "too big"}) == (
            "truncated",
            None,
        )

    def test_degraded_quality_is_partial(self):
        from flowtracker.research.tools import classify_completeness

        payload = {"_meta": {"degraded_quality": True}, "rows": [1, 2, 3, 4]}
        assert classify_completeness(payload) == ("partial", 4)

    def test_degraded_quality_no_rows(self):
        from flowtracker.research.tools import classify_completeness

        payload = {"_meta": {"degraded_quality": True}, "summary": "fallback used"}
        assert classify_completeness(payload) == ("partial", None)

    def test_dict_with_rows_list_counts(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"rows": [1, 2, 3, 4, 5]}) == ("full", 5)

    def test_dict_with_items_list_counts(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"items": [{"a": 1}, {"b": 2}]}) == ("full", 2)

    def test_dict_with_data_list_counts(self):
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness({"data": [1]}) == ("full", 1)

    def test_dict_without_row_keys_no_count(self):
        from flowtracker.research.tools import classify_completeness

        # Dict with scalar values only → full, but no row count derivable
        assert classify_completeness({"name": "ACME", "pe": 42.5}) == ("full", None)

    def test_plain_string_payload_is_full(self):
        # Non-empty strings (e.g. business_profile markdown) classify as full.
        from flowtracker.research.tools import classify_completeness

        assert classify_completeness("some report text") == ("full", None)

    def test_row_key_precedence(self):
        # When multiple row keys exist, "rows" wins (first in our precedence list).
        from flowtracker.research.tools import classify_completeness

        payload = {"rows": [1, 2], "items": [1, 2, 3, 4], "data": [1]}
        assert classify_completeness(payload) == ("full", 2)

    def test_count_rows_helper_direct(self):
        from flowtracker.research.tools import _count_rows

        assert _count_rows([1, 2, 3]) == 3
        assert _count_rows({"rows": [1]}) == 1
        assert _count_rows({"items": [1, 2]}) == 2
        assert _count_rows({"data": [1, 2, 3]}) == 3
        assert _count_rows({"name": "x"}) is None
        assert _count_rows(42) is None
        assert _count_rows("hello") is None


# ---------------------------------------------------------------------------
# _wrap_handler_is_error (Phase 0-A) — flag is_error on the envelope when the
# payload classifies as an error, without mutating the content text.
# ---------------------------------------------------------------------------


def _make_is_error_tool(name: str, payload):
    """Build a tiny SdkMcpTool whose handler returns a JSON-encoded payload."""
    from claude_agent_sdk import SdkMcpTool

    async def handler(args):
        return {"content": [{"type": "text", "text": json.dumps(payload)}]}

    return SdkMcpTool(name=name, description="", input_schema={}, handler=handler)


class TestWrapHandlerIsError:
    """Envelope-level is_error flagging via classify_completeness."""

    @pytest.mark.asyncio
    async def test_error_payload_sets_is_error(self):
        from flowtracker.research.tools import _wrap_handler_is_error

        tool = _wrap_handler_is_error(_make_is_error_tool("boom", {"error": "kaboom"}))
        result = await tool.handler({})
        assert result["is_error"] is True
        # Content text is untouched (dedup hash preserved).
        assert json.loads(result["content"][0]["text"]) == {"error": "kaboom"}

    @pytest.mark.asyncio
    async def test_normal_payload_not_flagged(self):
        from flowtracker.research.tools import _wrap_handler_is_error

        tool = _wrap_handler_is_error(_make_is_error_tool("ok", {"rows": [1, 2, 3]}))
        result = await tool.handler({})
        assert result.get("is_error") is not True
        assert "is_error" not in result

    @pytest.mark.asyncio
    async def test_non_json_text_left_unflagged(self):
        from claude_agent_sdk import SdkMcpTool
        from flowtracker.research.tools import _wrap_handler_is_error

        async def handler(args):
            return {"content": [{"type": "text", "text": "[dedup stub]"}]}

        tool = _wrap_handler_is_error(
            SdkMcpTool(name="stub", description="", input_schema={}, handler=handler)
        )
        result = await tool.handler({})
        assert "is_error" not in result

    def test_wrapping_is_idempotent(self):
        from flowtracker.research.tools import _wrap_handler_is_error

        tool = _wrap_handler_is_error(_make_is_error_tool("once", {"rows": [1]}))
        wrapped_handler = tool.handler
        _wrap_handler_is_error(tool)  # second pass must not re-wrap
        assert tool.handler is wrapped_handler

    def test_all_registered_tools_are_wrapped(self):
        from flowtracker.research import tools as t

        seen = {}
        for reg in t._ALL_TOOL_REGISTRIES:
            for tool in reg:
                seen[id(tool)] = tool
        unwrapped = [
            tool.name
            for tool in seen.values()
            if not getattr(tool.handler, "_is_error_wrapped", False)
        ]
        assert unwrapped == []
