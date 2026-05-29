"""Industry → D&A resolution (P2a fix).

`_resolve_industry_token` previously had no power/energy or FMCG branch, so
NTPC ("Power Generation") and HUL ("Diversified FMCG") collapsed to None and
projections fell to the 2% unresolved_default (NTPC actual D&A ≈ 9.25%). These
tests pin the new energy/FMCG branches + the projections D&A ratios.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.projections import _resolve_da_strategy
from flowtracker.store import FlowStore


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# --- _resolve_industry_token: power/energy + FMCG branches ---


def test_resolve_industry_token_energy_for_power(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda symbol: "Power Generation")
    assert api._resolve_industry_token("NTPC") == "energy"


def test_resolve_industry_token_energy_for_renewable(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda symbol: "Renewable Energy")
    assert api._resolve_industry_token("XYZGREEN") == "energy"


def test_resolve_industry_token_fmcg(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda symbol: "Diversified FMCG")
    assert api._resolve_industry_token("HINDUNILVR") == "fmcg"


def test_resolve_industry_token_passes_through_unknown_nonempty(api, monkeypatch):
    """Belt-and-suspenders: an unrecognized but non-empty industry passes
    through lowercased rather than collapsing to None."""
    monkeypatch.setattr(api, "_get_industry", lambda symbol: "Some Niche Sector")
    assert api._resolve_industry_token("WEIRDCO") == "some niche sector"


def test_resolve_industry_token_none_for_empty(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda symbol: "Unknown")
    assert api._resolve_industry_token("MYSTERY") is None


# --- _resolve_da_strategy: energy 7%, fmcg 1.5% ---


def test_da_strategy_energy_ratio():
    strat = _resolve_da_strategy("energy", latest_rev=1000.0, latest_dep=90.0,
                                 latest_net_block=None)
    assert strat["mode"] == "ratio"
    assert strat["ratio"] == 0.07


def test_da_strategy_fmcg_ratio():
    strat = _resolve_da_strategy("fmcg", latest_rev=1000.0, latest_dep=15.0,
                                 latest_net_block=None)
    assert strat["mode"] == "ratio"
    assert strat["ratio"] == 0.015
