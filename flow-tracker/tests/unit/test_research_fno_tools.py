"""Unit tests for the F&O Positioning MCP tool wrappers (Sprint 3).

Each test mocks the corresponding `ResearchDataAPI` method, awaits the tool
handler with an args dict, and asserts that the wrapper returned the
expected JSON envelope. Mirrors the established pattern in
`tests/unit/test_research_tools.py` (FakeAPI + patch_api).

The companion subagent owns the `data_api.py` implementations; these
tests pin the wire contract so a method-name drift breaks loudly.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Autouse: reset the dedup ContextVar between tests so cache state cannot
# leak across the suite.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tool_dedup_cache():
    from flowtracker.research import tools as t

    t._tool_result_cache.set({})
    yield
    t._tool_result_cache.set({})


# ---------------------------------------------------------------------------
# Helpers (mirrors test_research_tools.py)
# ---------------------------------------------------------------------------


def _parse(result: dict) -> Any:
    """Extract + JSON-decode the text payload from an MCP tool result."""
    assert "content" in result
    content = result["content"]
    assert isinstance(content, list) and len(content) > 0
    assert content[0]["type"] == "text"
    return json.loads(content[0]["text"])


class FakeAPI:
    """In-memory fake for ResearchDataAPI.

    Records every method call. Each method consults `overrides` (keyed by
    method name) to determine the return value; falls back to a sentinel
    dict so accidental calls are loud rather than silent.
    """

    def __init__(self, overrides: dict[str, Any] | None = None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.overrides = overrides or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __getattr__(self, name):
        def _method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name in self.overrides:
                val = self.overrides[name]
                return val(*args, **kwargs) if callable(val) else val
            return {"_unmocked": name}
        return _method


@contextmanager
def patch_api(fake: FakeAPI):
    class _Factory:
        def __call__(self, *a, **kw):
            return fake

    with patch("flowtracker.research.tools.ResearchDataAPI", _Factory()):
        yield fake


# ---------------------------------------------------------------------------
# get_fno_positioning
# ---------------------------------------------------------------------------


class TestGetFnoPositioning:
    @pytest.mark.asyncio
    async def test_happy_path_returns_snapshot(self):
        from flowtracker.research.tools import get_fno_positioning

        payload = {
            "fno_eligible": True,
            "symbol": "RELIANCE",
            "as_of_date": "2026-04-23",
            "futures": {
                "current_oi": 12_345_000,
                "oi_percentile_90d": 78.4,
                "oi_trend": "rising",
                "basis_pct": 0.32,
                "oi_change_5d_pct": 8.1,
            },
            "options": {
                "pcr_oi": 0.92,
                "pcr_label": "neutral",
                "max_pain_strike": 2900.0,
                "atm_iv": 22.7,
            },
            "fii_derivatives": {
                "index_fut_net_long_pct": 41.2,
                "trend": "shorting",
            },
        }
        fake = FakeAPI(overrides={"get_fno_positioning": payload})
        with patch_api(fake):
            result = await get_fno_positioning.handler({"symbol": "RELIANCE"})
        data = _parse(result)
        assert data == payload
        assert fake.calls[0] == ("get_fno_positioning", ("RELIANCE",), {})

    @pytest.mark.asyncio
    async def test_non_fno_symbol_returns_eligibility_envelope(self):
        from flowtracker.research.tools import get_fno_positioning

        fake = FakeAPI(overrides={"get_fno_positioning": None})
        with patch_api(fake):
            result = await get_fno_positioning.handler({"symbol": "OBSCURECO"})
        data = _parse(result)
        assert data == {
            "fno_eligible": False,
            "reason": "symbol not in NSE F&O eligibility list",
        }
        assert fake.calls[0] == ("get_fno_positioning", ("OBSCURECO",), {})


# ---------------------------------------------------------------------------
# get_oi_history
# ---------------------------------------------------------------------------


class TestGetOiHistory:
    @pytest.mark.asyncio
    async def test_happy_path_default_days(self):
        from flowtracker.research.tools import get_oi_history

        rows = [
            {"date": "2026-04-23", "oi": 12_345_000, "close": 2890.5, "volume": 9_876_000},
            {"date": "2026-04-22", "oi": 12_100_000, "close": 2875.0, "volume": 8_700_000},
        ]
        fake = FakeAPI(overrides={"get_oi_history": rows})
        with patch_api(fake):
            result = await get_oi_history.handler({"symbol": "RELIANCE"})
        data = _parse(result)
        assert data == rows
        # Default days = 90
        assert fake.calls[0] == ("get_oi_history", ("RELIANCE", 90), {})

    @pytest.mark.asyncio
    async def test_custom_days_passed_through(self):
        from flowtracker.research.tools import get_oi_history

        fake = FakeAPI(overrides={"get_oi_history": []})
        with patch_api(fake):
            await get_oi_history.handler({"symbol": "TCS", "days": 30})
        assert fake.calls[0] == ("get_oi_history", ("TCS", 30), {})

    @pytest.mark.asyncio
    async def test_empty_list_for_non_fno_symbol(self):
        from flowtracker.research.tools import get_oi_history

        fake = FakeAPI(overrides={"get_oi_history": []})
        with patch_api(fake):
            result = await get_oi_history.handler({"symbol": "OBSCURECO"})
        data = _parse(result)
        assert data == []


# ---------------------------------------------------------------------------
# get_option_chain_concentration
# ---------------------------------------------------------------------------


class TestGetOptionChainConcentration:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        from flowtracker.research.tools import get_option_chain_concentration

        payload = {
            "symbol": "RELIANCE",
            "expiry": "2026-04-30",
            "max_call_oi_strike": 3000.0,
            "max_put_oi_strike": 2800.0,
            "max_pain_strike": 2900.0,
            "total_call_oi": 5_400_000,
            "total_put_oi": 4_900_000,
        }
        fake = FakeAPI(overrides={"get_option_chain_concentration": payload})
        with patch_api(fake):
            result = await get_option_chain_concentration.handler({"symbol": "RELIANCE"})
        data = _parse(result)
        assert data == payload
        assert fake.calls[0] == ("get_option_chain_concentration", ("RELIANCE",), {})

    @pytest.mark.asyncio
    async def test_returns_null_for_non_fno_symbol(self):
        from flowtracker.research.tools import get_option_chain_concentration

        fake = FakeAPI(overrides={"get_option_chain_concentration": None})
        with patch_api(fake):
            result = await get_option_chain_concentration.handler({"symbol": "OBSCURECO"})
        data = _parse(result)
        assert data is None


# ---------------------------------------------------------------------------
# get_fii_derivative_flow
# ---------------------------------------------------------------------------


class TestGetFiiDerivativeFlow:
    @pytest.mark.asyncio
    async def test_happy_path_default_days(self):
        from flowtracker.research.tools import get_fii_derivative_flow

        rows = [
            {
                "date": "2026-04-23",
                "index_fut_long_oi": 250_000,
                "index_fut_short_oi": 320_000,
                "index_fut_net_long_pct": 43.9,
                "index_opt_ce_oi": 800_000,
                "index_opt_pe_oi": 750_000,
                "stock_fut_long_oi": 1_100_000,
                "stock_fut_short_oi": 950_000,
                "stock_fut_net_long_pct": 53.7,
            }
        ]
        fake = FakeAPI(overrides={"get_fii_derivative_flow": rows})
        with patch_api(fake):
            result = await get_fii_derivative_flow.handler({})
        data = _parse(result)
        assert data == rows
        # Default days = 30, no symbol arg
        assert fake.calls[0] == ("get_fii_derivative_flow", (30,), {})

    @pytest.mark.asyncio
    async def test_custom_days_passed_through(self):
        from flowtracker.research.tools import get_fii_derivative_flow

        fake = FakeAPI(overrides={"get_fii_derivative_flow": []})
        with patch_api(fake):
            await get_fii_derivative_flow.handler({"days": 60})
        assert fake.calls[0] == ("get_fii_derivative_flow", (60,), {})


# ---------------------------------------------------------------------------
# get_futures_basis
# ---------------------------------------------------------------------------


class TestGetFuturesBasis:
    @pytest.mark.asyncio
    async def test_happy_path_default_days(self):
        from flowtracker.research.tools import get_futures_basis

        rows = [
            {"date": "2026-04-23", "spot": 2890.5, "futures": 2899.7, "basis_pct": 0.318},
            {"date": "2026-04-22", "spot": 2875.0, "futures": 2880.6, "basis_pct": 0.195},
        ]
        fake = FakeAPI(overrides={"get_futures_basis": rows})
        with patch_api(fake):
            result = await get_futures_basis.handler({"symbol": "RELIANCE"})
        data = _parse(result)
        assert data == rows
        # Default days = 30
        assert fake.calls[0] == ("get_futures_basis", ("RELIANCE", 30), {})

    @pytest.mark.asyncio
    async def test_custom_days(self):
        from flowtracker.research.tools import get_futures_basis

        fake = FakeAPI(overrides={"get_futures_basis": []})
        with patch_api(fake):
            await get_futures_basis.handler({"symbol": "TCS", "days": 90})
        assert fake.calls[0] == ("get_futures_basis", ("TCS", 90), {})

    @pytest.mark.asyncio
    async def test_empty_list_for_non_fno_symbol(self):
        from flowtracker.research.tools import get_futures_basis

        fake = FakeAPI(overrides={"get_futures_basis": []})
        with patch_api(fake):
            result = await get_futures_basis.handler({"symbol": "OBSCURECO"})
        data = _parse(result)
        assert data == []


# ---------------------------------------------------------------------------
# Tools-list registry
# ---------------------------------------------------------------------------


class TestFnoPositioningRegistry:
    def test_registry_includes_five_owned_tools_plus_shared_context(self):
        from flowtracker.research.tools import (
            FNO_POSITIONING_AGENT_TOOLS_V2,
            get_company_context,
            get_fii_derivative_flow,
            get_fno_positioning,
            get_futures_basis,
            get_market_context,
            get_oi_history,
            get_option_chain_concentration,
            get_ownership,
        )

        assert get_fno_positioning in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_oi_history in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_option_chain_concentration in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_fii_derivative_flow in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_futures_basis in FNO_POSITIONING_AGENT_TOOLS_V2
        # Shared cross-reference tools
        assert get_company_context in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_ownership in FNO_POSITIONING_AGENT_TOOLS_V2
        assert get_market_context in FNO_POSITIONING_AGENT_TOOLS_V2
        assert len(FNO_POSITIONING_AGENT_TOOLS_V2) == 8
