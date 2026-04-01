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
