"""Integration tests for MCP tool functions in flowtracker/research/tools.py.

Each tool is an SdkMcpTool instance wrapping an async handler. We call
tool.handler(args) directly with a populated test database, and verify
the response shape: {"content": [{"type": "text", "text": <json_str>}]}.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixture: point FLOWTRACKER_DB at the populated test database
# ---------------------------------------------------------------------------

@pytest.fixture
def db_env(tmp_db: Path, populated_store: FlowStore, monkeypatch):
    """Set FLOWTRACKER_DB env var so ResearchDataAPI finds the test database."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    return tmp_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tool_result(result: dict) -> list | dict:
    """Extract and parse JSON from MCP tool response."""
    assert "content" in result, f"Missing 'content' key in result: {result}"
    content = result["content"]
    assert isinstance(content, list) and len(content) > 0
    assert content[0]["type"] == "text"
    return json.loads(content[0]["text"])


# ---------------------------------------------------------------------------
# FMP Tools
# ---------------------------------------------------------------------------

class TestGetFairValue:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_fair_value
        result = await get_fair_value.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Macro Tools (V2 consolidated)
# ---------------------------------------------------------------------------


class TestGetFundamentals:
    @pytest.mark.asyncio
    async def test_section_quarterly_results(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        result = await get_fundamentals.handler({"symbol": "SBIN", "section": "quarterly_results", "quarters": 4})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        result = await get_fundamentals.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "quarterly_results" in data
        assert "annual_financials" in data

    @pytest.mark.asyncio
    async def test_unknown_section(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        result = await get_fundamentals.handler({"symbol": "SBIN", "section": "bogus"})
        data = _parse_tool_result(result)
        assert "error" in data


class TestGetQualityScores:
    @pytest.mark.asyncio
    async def test_section_piotroski(self, db_env):
        from flowtracker.research.tools import get_quality_scores
        result = await get_quality_scores.handler({"symbol": "SBIN", "section": "piotroski"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all_returns_all_keys(self, db_env):
        """Test 'all' section returns expected keys.

        Note: SBIN in test DB has industry='Banks' which doesn't match
        _BFSI_INDUSTRIES (expects 'Public Sector Bank'), so both SBIN
        and INFY follow the non-BFSI path in the test fixture.
        """
        from flowtracker.research.tools import get_quality_scores
        result = await get_quality_scores.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        # All quality sections present
        for key in ("piotroski", "dupont", "common_size", "earnings_quality", "beneish", "capex_cycle", "bfsi"):
            assert key in data


class TestGetOwnership:
    @pytest.mark.asyncio
    async def test_section_shareholding(self, db_env):
        from flowtracker.research.tools import get_ownership
        result = await get_ownership.handler({"symbol": "SBIN", "section": "shareholding", "quarters": 4})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_ownership
        result = await get_ownership.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("shareholding", "changes", "insider", "bulk_block", "mf_holdings", "mf_changes", "shareholder_detail", "promoter_pledge"):
            assert key in data


class TestGetValuationMacro:
    @pytest.mark.asyncio
    async def test_section_snapshot(self, db_env):
        from flowtracker.research.tools import get_valuation
        result = await get_valuation.handler({"symbol": "SBIN", "section": "snapshot"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_valuation
        result = await get_valuation.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("snapshot", "band", "pe_history", "key_metrics"):
            assert key in data


class TestGetFairValueAnalysis:
    @pytest.mark.asyncio
    async def test_section_combined(self, db_env):
        from flowtracker.research.tools import get_fair_value_analysis
        result = await get_fair_value_analysis.handler({"symbol": "SBIN", "section": "combined"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_fair_value_analysis
        result = await get_fair_value_analysis.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("combined", "dcf", "dcf_history", "reverse_dcf", "projections"):
            assert key in data


class TestGetPeerSector:
    @pytest.mark.asyncio
    async def test_section_peer_table(self, db_env):
        from flowtracker.research.tools import get_peer_sector
        result = await get_peer_sector.handler({"symbol": "SBIN", "section": "peer_table"})
        data = _parse_tool_result(result)
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_peer_sector
        result = await get_peer_sector.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("peer_table", "peer_metrics", "sector_overview"):
            assert key in data


class TestGetEstimatesMacro:
    @pytest.mark.asyncio
    async def test_section_consensus(self, db_env):
        from flowtracker.research.tools import get_estimates
        result = await get_estimates.handler({"symbol": "SBIN", "section": "consensus"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_estimates
        result = await get_estimates.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("consensus", "surprises", "revisions", "momentum"):
            assert key in data


class TestGetMarketContext:
    @pytest.mark.asyncio
    async def test_section_macro(self, db_env):
        from flowtracker.research.tools import get_market_context
        result = await get_market_context.handler({"symbol": "SBIN", "section": "macro"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_market_context
        result = await get_market_context.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("delivery", "macro", "fii_dii_streak"):
            assert key in data


class TestGetCompanyContext:
    @pytest.mark.asyncio
    async def test_section_info(self, db_env):
        from flowtracker.research.tools import get_company_context
        result = await get_company_context.handler({"symbol": "SBIN", "section": "info"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_company_context
        result = await get_company_context.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("info", "profile", "documents"):
            assert key in data


class TestGetEventsActions:
    @pytest.mark.asyncio
    async def test_section_events(self, db_env):
        from flowtracker.research.tools import get_events_actions
        result = await get_events_actions.handler({"symbol": "SBIN", "section": "events"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_section_all(self, db_env):
        from flowtracker.research.tools import get_events_actions
        result = await get_events_actions.handler({"symbol": "SBIN", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        for key in ("events", "dividends", "corporate_actions", "adjusted_eps", "catalysts"):
            assert key in data


# ---------------------------------------------------------------------------
# Phase 3 — uniform TOC default (3a) + standardized _meta sidecar (3b)
# ---------------------------------------------------------------------------


def _reset_dedup_cache():
    """Clear the _with_dedup ContextVar so a fresh payload is never replaced by
    the '[Identical to previous call...]' stub from an earlier test in-process."""
    from flowtracker.research.tools import _tool_result_cache
    _tool_result_cache.set({})


class TestTocDefaultsAndMeta:
    """Phase 3a: the seven dispatchers that used to default to the heavy 'all'
    payload now return a compact enum-constant TOC when called with no section,
    while section='all' STILL returns the full multi-section payload.
    Phase 3b: every return path carries a `_meta` sidecar with a `status` key.
    """

    # --- 3a: no-section default is a TOC, not the full 'all' payload ---

    @pytest.mark.asyncio
    async def test_quality_scores_no_section_returns_toc(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import (
            _QUALITY_SCORES_SECTIONS,
            get_quality_scores,
        )
        result = await get_quality_scores.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        # TOC shape — has the _toc enum listing, NOT the full 'all' payload.
        assert "_toc" in data
        assert set(data["_toc"]) == set(_QUALITY_SCORES_SECTIONS)
        # Must NOT have routed any data section (e.g. piotroski/dupont).
        assert "piotroski" not in data
        assert "dupont" not in data
        # 3b: _meta sidecar present with a status key on the TOC path.
        assert "_meta" in data
        assert "status" in data["_meta"]

    @pytest.mark.asyncio
    async def test_valuation_no_section_returns_toc(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import _VALUATION_SECTIONS, get_valuation
        result = await get_valuation.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" in data
        assert set(data["_toc"]) == set(_VALUATION_SECTIONS)
        assert "snapshot" not in data  # not the full payload
        assert "band" not in data
        assert "_meta" in data and "status" in data["_meta"]

    @pytest.mark.asyncio
    async def test_estimates_no_section_returns_toc(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import _ESTIMATES_SECTIONS, get_estimates
        result = await get_estimates.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" in data
        assert set(data["_toc"]) == set(_ESTIMATES_SECTIONS)
        assert "consensus" not in data
        assert "_meta" in data and "status" in data["_meta"]

    @pytest.mark.asyncio
    async def test_events_actions_no_section_returns_toc(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import (
            _EVENTS_ACTIONS_SECTIONS,
            get_events_actions,
        )
        result = await get_events_actions.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" in data
        assert set(data["_toc"]) == set(_EVENTS_ACTIONS_SECTIONS)
        assert "events" not in data
        assert "_meta" in data and "status" in data["_meta"]

    # --- 3a: section='all' STILL returns the full multi-section payload ---

    @pytest.mark.asyncio
    async def test_valuation_all_still_full_payload(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import get_valuation
        result = await get_valuation.handler({"symbol": "INFY", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" not in data
        for key in ("snapshot", "band", "pe_history", "key_metrics"):
            assert key in data

    @pytest.mark.asyncio
    async def test_estimates_all_still_full_payload(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import get_estimates
        result = await get_estimates.handler({"symbol": "INFY", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" not in data
        for key in ("consensus", "surprises", "revisions", "momentum"):
            assert key in data

    @pytest.mark.asyncio
    async def test_quality_scores_all_still_full_payload(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import get_quality_scores
        result = await get_quality_scores.handler({"symbol": "INFY", "section": "all"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_toc" not in data
        for key in ("piotroski", "dupont", "common_size"):
            assert key in data

    # --- 3b: _meta on a per-section success path (dict payload) ---

    @pytest.mark.asyncio
    async def test_meta_on_success_dict_path(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import get_valuation
        # snapshot returns a dict — _meta should ride alongside it.
        result = await get_valuation.handler({"symbol": "SBIN", "section": "snapshot"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "_meta" in data
        meta = data["_meta"]
        assert "status" in meta and "count" in meta and "as_of_date" in meta
        assert meta["status"] in ("ok", "empty", "partial", "error")

    # --- 3b: _meta with status='error' on the invalid-section error path ---

    @pytest.mark.asyncio
    async def test_meta_status_error_on_invalid_section(self, db_env):
        _reset_dedup_cache()
        from flowtracker.research.tools import get_valuation
        result = await get_valuation.handler({"symbol": "SBIN", "section": "bogus_xyz"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "error" in data
        # Error envelope carries a did-you-mean suggestion AND a _meta status.
        assert "suggestion" in data
        assert "_meta" in data
        assert data["_meta"]["status"] == "error"


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

class TestGetStockNews:
    @pytest.mark.asyncio
    async def test_returns_valid_response_shape(self, db_env):
        from unittest.mock import patch

        from flowtracker.research.tools import get_stock_news

        mock_data = [
            {
                "title": "Test News",
                "source": "Test",
                "date": "2026-03-01",
                "url": "https://example.com",
                "summary": None,
                "provider": "google_rss",
            }
        ]
        with patch(
            "flowtracker.research.data_api.ResearchDataAPI.get_stock_news",
            return_value=mock_data,
        ):
            result = await get_stock_news.handler({"symbol": "INFY", "days": 30})

        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test News"
        assert data[0]["provider"] == "google_rss"

    @pytest.mark.asyncio
    async def test_empty_news_returns_empty_list(self, db_env):
        from unittest.mock import patch

        from flowtracker.research.tools import get_stock_news

        with patch(
            "flowtracker.research.data_api.ResearchDataAPI.get_stock_news",
            return_value=[],
        ):
            result = await get_stock_news.handler({"symbol": "NONEXIST", "days": 30})

        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) == 0


# ---------------------------------------------------------------------------
# Macro numeric series + sector-index wiring (feat/agent-data-wiring)
# ---------------------------------------------------------------------------


class TestGetMacroIndicators:
    @pytest.mark.asyncio
    async def test_returns_cpi_iip_pmi_yield_sections(self, db_env, populated_store):
        from flowtracker.cpi_models import CPIMonth
        from flowtracker.iip_models import IIPMonth
        from flowtracker.pmi_models import PMIMonth
        from flowtracker.research.tools import get_macro_indicators

        populated_store.upsert_cpi_monthly([
            CPIMonth(period="2025-04", cpi_index=194.5, yoy_pct=3.16),
            CPIMonth(period="2025-03", cpi_index=193.8, yoy_pct=3.34),
        ])
        populated_store.upsert_iip_monthly([
            IIPMonth(period="2025-04", iip_index=152.5, yoy_pct=2.7),
        ])
        populated_store.upsert_pmi_monthly([
            PMIMonth(period="2025-04", services_pmi=58.7, manufacturing_pmi=58.2),
        ])

        result = await get_macro_indicators.handler({"months": 6})
        data = _parse_tool_result(result)
        assert set(data.keys()) >= {"cpi", "iip", "pmi", "yield_curve"}
        assert data["cpi"]["latest"]["yoy_pct"] == 3.16
        assert len(data["cpi"]["trend"]) == 2
        assert data["pmi"]["latest"]["services_pmi"] == 58.7


class TestSectorIndexValuation:
    @pytest.mark.asyncio
    async def test_returns_percentile_band(self, db_env, populated_store):
        from datetime import date, timedelta

        from flowtracker.indexpe_models import IndexValuation
        from flowtracker.research.tools import get_peer_sector

        # Seed both the likely-resolved sector index (NIFTY BANK for SBIN) and
        # the broad fallback (NIFTY 500) so the test is robust to how the
        # symbol's industry resolves.
        base = date(2024, 1, 1)
        rows = []
        for name in ("NIFTY BANK", "NIFTY 500"):
            for i in range(40):
                rows.append(IndexValuation(
                    date=(base + timedelta(days=i)).isoformat(),
                    index_name=name, pe=12.0 + i * 0.1, pb=1.8 + i * 0.01,
                    dividend_yield=1.1,
                ))
        populated_store.upsert_index_valuations(rows)

        result = await get_peer_sector.handler(
            {"symbol": "SBIN", "section": "sector_index_valuation"}
        )
        data = _parse_tool_result(result)
        assert data["index_name"] in ("NIFTY BANK", "NIFTY 500")
        assert data["current"]["pe"] is not None
        assert "pe_percentile" in data


class TestSectorPerformance:
    @pytest.mark.asyncio
    async def test_ranks_indices(self, db_env, populated_store):
        from datetime import date, timedelta

        from flowtracker.research.tools import get_peer_sector

        base = date.today() - timedelta(days=300)
        recs = []
        for tkr, p0 in (("^NSEI", 22000.0), ("^CNXIT", 35000.0)):
            for i in range(300):
                recs.append({
                    "date": (base + timedelta(days=i)).isoformat(),
                    "index_ticker": tkr, "close": p0 * (1 + i * 0.001),
                })
        populated_store.upsert_index_daily_prices(recs)

        result = await get_peer_sector.handler(
            {"symbol": "SBIN", "section": "sector_performance"}
        )
        data = _parse_tool_result(result)
        assert data.get("indices"), data
        first = data["indices"][0]
        assert {"index", "ticker", "return_1y_pct"} <= set(first.keys())


class TestGoldETFNavInCommoditySnapshot:
    @pytest.mark.asyncio
    async def test_gold_etf_nav_present(self, db_env):
        from flowtracker.research.tools import get_market_context

        result = await get_market_context.handler(
            {"symbol": "SBIN", "section": "commodities"}
        )
        data = _parse_tool_result(result)
        # populated_store seeds Gold BeES scheme 140088 (10 days).
        assert "gold_etf_nav" in data
        assert data["gold_etf_nav"]["nav"] is not None


class TestPricePerformanceHorizons:
    @pytest.mark.asyncio
    async def test_includes_long_horizons(self, db_env, populated_store, monkeypatch):
        from datetime import date, timedelta

        from flowtracker.bhavcopy_models import DailyStockData
        from flowtracker.research.tools import get_market_context

        # ~6.5 years of weekly bars for a fresh symbol → 3Y/5Y/Since-Listing.
        base = date.today() - timedelta(days=int(365.25 * 6.5))
        recs = []
        d, px = base, 100.0
        while d <= date.today():
            recs.append(DailyStockData(
                date=d.isoformat(), symbol="LONGCO",
                open=px, high=px + 2, low=px - 2, close=px, prev_close=px - 1,
                volume=100000, turnover=px * 1000,
                delivery_qty=50000, delivery_pct=55.0,
            ))
            d += timedelta(days=7)
            px += 1.0
        populated_store.upsert_daily_stock_data(recs)

        # Avoid network: force the yfinance benchmark fetch onto its except path.
        import yfinance

        def _boom(*args, **kwargs):
            raise RuntimeError("no network in tests")

        monkeypatch.setattr(yfinance, "Ticker", _boom)

        result = await get_market_context.handler(
            {"symbol": "LONGCO", "section": "price_performance"}
        )
        data = _parse_tool_result(result)
        labels = {p["period"] for p in data["periods"]}
        assert {"1Y", "3Y", "5Y", "Since Listing"} <= labels


class TestValuationAgentCanReachCashFlow:
    def test_get_fundamentals_in_valuation_allowlist(self):
        from flowtracker.research.tools import (
            VALUATION_AGENT_TOOLS,
            get_fundamentals,
        )

        # Regression: the valuation prompt (step 4) calls get_fundamentals for
        # cash_flow_quality/capital_allocation; it must be in the allow-list.
        assert get_fundamentals in VALUATION_AGENT_TOOLS


# ---------------------------------------------------------------------------
# Phase 1-A: section-enum schema + did-you-mean validation on dispatchers.
#
# An invalid `section`/`doc_type` must return an `{error, suggestion}` payload
# that the Phase 0 wrapper (`_wrap_handler_is_error`) flags `is_error=True`,
# while a valid section still routes normally. We also assert one built schema
# actually carries an `enum` on `section`.
# ---------------------------------------------------------------------------

class TestSectionEnumValidation:
    @pytest.mark.asyncio
    async def test_annual_report_toc_is_rejected(self, db_env):
        # 'toc' is a notorious wrong guess for get_annual_report (not a section).
        from flowtracker.research.tools import get_annual_report
        result = await get_annual_report.handler({"symbol": "SBIN", "section": "toc"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_annual_report_valid_section_routes(self, db_env):
        from flowtracker.research.tools import get_annual_report
        result = await get_annual_report.handler({"symbol": "SBIN", "section": "auditor_report"})
        data = _parse_tool_result(result)
        # A valid section must NOT be rejected as an invalid-enum value (no
        # did-you-mean validation envelope). It MAY still return a data-absence
        # error ("No AR extractions found…") when the vault has no AR for this
        # symbol — that is correct Phase-0 behavior (is_error=True is right), and
        # CI has no vault data, so we don't assert is_error here.
        assert not (isinstance(data, dict) and "valid_values" in data)
        assert not (isinstance(data, dict) and str(data.get("error", "")).startswith("Invalid section"))

    @pytest.mark.asyncio
    async def test_fundamentals_invalid_section_is_rejected(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        result = await get_fundamentals.handler({"symbol": "SBIN", "section": "nonsense"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert "valid_values" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_fundamentals_valid_section_still_routes(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        # quarters=3 keeps this arg-tuple distinct from the quarters=4 call in
        # TestGetFundamentals so the session-level _with_dedup cache (a ContextVar
        # shared across handler calls in this process) does not return a stub.
        result = await get_fundamentals.handler(
            {"symbol": "SBIN", "section": "quarterly_results", "quarters": 3}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]

    @pytest.mark.asyncio
    async def test_fundamentals_invalid_section_in_list_is_rejected(self, db_env):
        from flowtracker.research.tools import get_fundamentals
        result = await get_fundamentals.handler(
            {"symbol": "SBIN", "section": ["quarterly_results", "bogus"]}
        )
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_ownership_invalid_section_is_rejected(self, db_env):
        from flowtracker.research.tools import get_ownership
        result = await get_ownership.handler({"symbol": "SBIN", "section": "shareholdings"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        # 'shareholdings' is close to 'shareholding' → fuzzy match offered.
        assert "Did you mean" in data["suggestion"]
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_macro_anchor_invalid_doc_type_is_rejected(self, db_env):
        from flowtracker.research.tools import get_macro_anchor
        result = await get_macro_anchor.handler({"doc_type": "budget"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_company_context_bad_sub_section_is_rejected(self, db_env):
        from flowtracker.research.tools import get_company_context
        result = await get_company_context.handler(
            {"symbol": "SBIN", "section": "annual_report", "sub_section": "not_a_section"}
        )
        data = _parse_tool_result(result)
        assert data["error"].startswith("Invalid sub_section")
        assert "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_company_context_sector_kpis_sub_section_not_validated(self, db_env):
        # sector_kpis sub_section is a free-text canonical KPI key — must NOT be
        # rejected as an invalid enum value.
        from flowtracker.research.tools import get_company_context
        result = await get_company_context.handler(
            {"symbol": "SBIN", "section": "sector_kpis", "sub_section": "any_free_text_key"}
        )
        data = _parse_tool_result(result)
        assert not (isinstance(data, dict) and str(data.get("error", "")).startswith("Invalid sub_section"))

    def test_built_schema_section_has_enum(self):
        from flowtracker.research.tools import get_fundamentals
        schema = get_fundamentals.input_schema
        assert schema["type"] == "object"
        assert schema["required"] == ["symbol"]
        section_schema = schema["properties"]["section"]
        # anyOf form: first branch is a plain string enum.
        enum = section_schema["anyOf"][0]["enum"]
        assert "quarterly_results" in enum
        assert "toc" in enum  # sentinel handler supports

    def test_built_schema_macro_anchor_doc_type_enum(self):
        from flowtracker.research.tools import get_macro_anchor
        schema = get_macro_anchor.input_schema
        assert schema["required"] == ["doc_type"]
        assert "enum" in schema["properties"]["doc_type"]
        # `section` is free-text heading match — must NOT be an enum.
        assert "enum" not in schema["properties"]["section"]


# ---------------------------------------------------------------------------
# Macro anchor tools — market routing (US Fed vs India)
# ---------------------------------------------------------------------------

class TestMacroAnchorMarketRouting:
    @pytest.mark.asyncio
    async def test_india_run_routes_to_india_anchors(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        captured = {}

        def fake_get(doc_type, section, market="NSE"):
            captured["doc_type"] = doc_type
            captured["market"] = market
            return {"status": "ok", "doc_type": doc_type}

        monkeypatch.setattr(t, "get_anchor_content", fake_get)
        tok = _run_market.set(None)  # India default
        try:
            result = await t.get_macro_anchor.handler({"doc_type": "economic_survey"})
        finally:
            _run_market.reset(tok)
        data = _parse_tool_result(result)
        assert data["status"] == "ok"
        assert captured["market"] == "NSE"
        assert captured["doc_type"] == "economic_survey"

    @pytest.mark.asyncio
    async def test_us_run_routes_to_fed_anchors(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        captured = {}

        def fake_get(doc_type, section, market="NSE"):
            captured["market"] = market
            return {"status": "ok", "doc_type": doc_type}

        monkeypatch.setattr(t, "get_anchor_content", fake_get)
        tok = _run_market.set("NASDAQ")
        try:
            result = await t.get_macro_anchor.handler({"doc_type": "fomc_statement"})
        finally:
            _run_market.reset(tok)
        data = _parse_tool_result(result)
        assert data["status"] == "ok"
        assert captured["market"] == "US"

    @pytest.mark.asyncio
    async def test_us_run_rejects_india_doc_type(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        tok = _run_market.set("NYSE")
        try:
            # economic_survey is an India doc_type — invalid under a US run.
            result = await t.get_macro_anchor.handler({"doc_type": "economic_survey"})
        finally:
            _run_market.reset(tok)
        data = _parse_tool_result(result)
        assert "error" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_india_run_rejects_us_doc_type(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        tok = _run_market.set(None)
        try:
            result = await t.get_macro_anchor.handler({"doc_type": "fomc_statement"})
        finally:
            _run_market.reset(tok)
        data = _parse_tool_result(result)
        assert "error" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_us_catalog_lists_fed_anchors(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        captured = {}

        def fake_list(market="NSE"):
            captured["market"] = market
            return {"anchors": {"fomc_statement": {"title": "FOMC", "status": "complete"}}}

        monkeypatch.setattr(t, "list_current_anchors", fake_list)
        tok = _run_market.set("NASDAQ")
        try:
            result = await t.get_macro_catalog.handler({})
        finally:
            _run_market.reset(tok)
        data = _parse_tool_result(result)
        assert captured["market"] == "US"
        assert data["anchors"][0]["doc_type"] == "fomc_statement"

    @pytest.mark.asyncio
    async def test_india_catalog_lists_india_anchors(self, db_env, monkeypatch):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        captured = {}

        def fake_list(market="NSE"):
            captured["market"] = market
            return {"anchors": {}}

        monkeypatch.setattr(t, "list_current_anchors", fake_list)
        tok = _run_market.set(None)
        try:
            await t.get_macro_catalog.handler({})
        finally:
            _run_market.reset(tok)
        assert captured["market"] == "NSE"


# ---------------------------------------------------------------------------
# Phase 1-B: standalone vocab tools — enum schema + did-you-mean validation on
# render_chart / get_chart_data / calculate / get_data_quality_flags /
# get_shareholder_detail / get_company_documents / get_sector_benchmarks /
# get_valuation_band. Same envelope contract as Phase 1-A (error+suggestion+
# is_error on a miss; valid value still routes). Args are varied per call to
# dodge the session-level _with_dedup ContextVar cache.
# ---------------------------------------------------------------------------

class TestStandaloneVocabValidation:
    @pytest.mark.asyncio
    async def test_render_chart_pbv_is_rejected(self, db_env):
        # 'pbv' is a get_chart_data type, NOT a render_chart type — must reject.
        from flowtracker.research.tools import render_chart
        result = await render_chart.handler({"symbol": "SBIN", "chart_type": "pbv"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert "valid_values" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_render_chart_valid_type_routes(self, db_env, monkeypatch):
        # A valid chart_type must NOT hit the enum guard. Stub the renderer so we
        # don't depend on matplotlib output / data presence.
        import flowtracker.research.charts as charts_mod
        from flowtracker.research import tools as tools_mod
        monkeypatch.setattr(
            charts_mod, "render_chart",
            lambda symbol, chart_type, *a, **k: {"path": "/tmp/x.png", "embed_markdown": "![](x)"},
        )
        result = await tools_mod.render_chart.handler({"symbol": "INFY", "chart_type": "price"})
        data = _parse_tool_result(result)
        assert not (isinstance(data, dict) and str(data.get("error", "")).startswith("Invalid chart_type"))
        assert result.get("is_error") is not True

    @pytest.mark.asyncio
    async def test_get_chart_data_invalid_type_is_rejected(self, db_env):
        from flowtracker.research.tools import get_chart_data
        result = await get_chart_data.handler({"symbol": "SBIN", "chart_type": "dupont"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_calculate_margin_is_rejected(self, db_env):
        # 'margin' is not a named op — must reject with a did-you-mean.
        from flowtracker.research.tools import calculate
        result = await calculate.handler({"operation": "margin", "a": "1", "b": "2"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_calculate_valid_operation_still_works(self, db_env):
        from flowtracker.research.tools import calculate
        # Vary args from any earlier calculate call to dodge the dedup cache.
        result = await calculate.handler({"operation": "ratio", "a": "10", "b": "4"})
        data = _parse_tool_result(result)
        assert data.get("ratio") == 2.5
        assert result.get("is_error") is not True

    @pytest.mark.asyncio
    async def test_calculate_expr_still_works(self, db_env):
        from flowtracker.research.tools import calculate
        result = await calculate.handler({"operation": "expr", "a": "(74 - 47.67) / 2", "b": "0"})
        data = _parse_tool_result(result)
        assert "result" in data
        assert result.get("is_error") is not True

    @pytest.mark.asyncio
    async def test_data_quality_flags_invalid_severity_is_rejected(self, db_env):
        from flowtracker.research.tools import get_data_quality_flags
        result = await get_data_quality_flags.handler({"symbol": "SBIN", "min_severity": "CRITICAL"})
        data = _parse_tool_result(result)
        assert "error" in data and "suggestion" in data
        assert result.get("is_error") is True

    @pytest.mark.asyncio
    async def test_data_quality_flags_default_severity_routes(self, db_env):
        # No min_severity passed → default MEDIUM, must NOT be rejected.
        from flowtracker.research.tools import get_data_quality_flags
        result = await get_data_quality_flags.handler({"symbol": "INFY"})
        data = _parse_tool_result(result)
        assert not (isinstance(data, dict) and str(data.get("error", "")).startswith("Invalid min_severity"))

    def test_built_schema_render_chart_has_enum(self):
        from flowtracker.research.tools import render_chart
        schema = render_chart.input_schema
        assert schema["type"] == "object"
        assert schema["required"] == ["symbol", "chart_type"]
        ct = schema["properties"]["chart_type"]
        assert "enum" in ct
        assert "price" in ct["enum"]
        assert "pbv" not in ct["enum"]  # pbv is a get_chart_data type, not here

    def test_built_schema_calculate_operation_has_enum(self):
        from flowtracker.research.tools import calculate
        schema = calculate.input_schema
        assert schema["required"] == ["operation"]
        op = schema["properties"]["operation"]
        assert "enum" in op
        assert "expr" in op["enum"]
        assert "ratio" in op["enum"]

    def test_built_schema_chart_data_type_has_enum(self):
        from flowtracker.research.tools import get_chart_data
        schema = get_chart_data.input_schema
        assert schema["required"] == ["symbol", "chart_type"]
        ct = schema["properties"]["chart_type"]
        assert "enum" in ct
        assert "pbv" in ct["enum"]
        assert "dupont" not in ct["enum"]  # dupont is a render_chart type
