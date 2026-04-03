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
# Core Financials
# ---------------------------------------------------------------------------

class TestGetQuarterlyResults:
    @pytest.mark.asyncio
    async def test_returns_data_for_sbin(self, db_env):
        from flowtracker.research.tools import get_quarterly_results
        result = await get_quarterly_results.handler({"symbol": "SBIN", "quarters": 4})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]

    @pytest.mark.asyncio
    async def test_unknown_symbol_returns_empty(self, db_env):
        from flowtracker.research.tools import get_quarterly_results
        result = await get_quarterly_results.handler({"symbol": "NONEXIST", "quarters": 4})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) == 0


class TestGetAnnualFinancials:
    @pytest.mark.asyncio
    async def test_returns_data(self, db_env):
        from flowtracker.research.tools import get_annual_financials
        result = await get_annual_financials.handler({"symbol": "SBIN", "years": 5})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]
        assert "net_income" in data[0]


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

class TestGetValuationSnapshot:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_valuation_snapshot
        result = await get_valuation_snapshot.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "price" in data or "pe_trailing" in data


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

class TestGetShareholding:
    @pytest.mark.asyncio
    async def test_returns_list(self, db_env):
        from flowtracker.research.tools import get_shareholding
        result = await get_shareholding.handler({"symbol": "SBIN", "quarters": 4})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


class TestGetInsiderTransactions:
    @pytest.mark.asyncio
    async def test_returns_list(self, db_env):
        from flowtracker.research.tools import get_insider_transactions
        result = await get_insider_transactions.handler({"symbol": "SBIN", "days": 365})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Market Signals
# ---------------------------------------------------------------------------

class TestGetDeliveryTrend:
    @pytest.mark.asyncio
    async def test_returns_list(self, db_env):
        from flowtracker.research.tools import get_delivery_trend
        result = await get_delivery_trend.handler({"symbol": "SBIN", "days": 30})
        data = _parse_tool_result(result)
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

class TestGetConsensusEstimate:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_consensus_estimate
        result = await get_consensus_estimate.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "target_mean" in data or "recommendation" in data


# ---------------------------------------------------------------------------
# FMP Tools
# ---------------------------------------------------------------------------

class TestGetDupontDecomposition:
    @pytest.mark.asyncio
    async def test_returns_data(self, db_env):
        from flowtracker.research.tools import get_dupont_decomposition
        result = await get_dupont_decomposition.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        # May be dict with "years" key or a list
        assert isinstance(data, (list, dict))


class TestGetFairValue:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_fair_value
        result = await get_fair_value.handler({"symbol": "SBIN"})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Macro (no symbol required)
# ---------------------------------------------------------------------------

class TestGetMacroSnapshot:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_macro_snapshot
        result = await get_macro_snapshot.handler({})
        data = _parse_tool_result(result)
        assert isinstance(data, dict)


class TestGetFiiDiiStreak:
    @pytest.mark.asyncio
    async def test_returns_dict(self, db_env):
        from flowtracker.research.tools import get_fii_dii_streak
        result = await get_fii_dii_streak.handler({})
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
