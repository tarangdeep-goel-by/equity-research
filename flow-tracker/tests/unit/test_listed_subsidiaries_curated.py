"""SOTP fix: `listed_subsidiaries` is driven by a curated YAML map
(research/data/listed_subsidiaries.yaml), NOT a promoter-surname heuristic.

Guards:
  (a) ADANIENT is curated as an incubator with NO listed holdings → the result
      surfaces a guidance note and contains none of the promoter-group siblings
      (ADANIPORTS/ADANIPOWER/ADANIGREEN/ADANIENSOL/ATGL).
  (b) A genuinely-curated parent (SBIN) returns its real listed subsidiaries.
  (c) An uncurated symbol returns None.
  (d) The deleted heuristic / AR-extraction functions no longer exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import (
    ResearchDataAPI,
    _load_curated_subsidiaries,
)
from flowtracker.store import FlowStore

ADANI_SIBLINGS = ["ADANIPORTS", "ADANIPOWER", "ADANIGREEN", "ADANIENSOL", "ATGL"]


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# --- (loader) the curated YAML is the source of truth ---


def test_curated_yaml_loads():
    curated = _load_curated_subsidiaries()
    for sym in ("ADANIENT", "NTPC", "SBIN", "LT", "BAJAJFINSV"):
        assert sym in curated, f"{sym} missing from curated map"
    # ADANIENT is the incubator: no listed holdings, but a guidance note.
    assert curated["ADANIENT"].get("subsidiaries") == []
    assert "incubator" in (curated["ADANIENT"].get("note") or "").lower()


def test_curated_yaml_has_no_adani_siblings():
    """No curated entry anywhere may list an Adani promoter-group sibling."""
    curated = _load_curated_subsidiaries()
    for sym, entry in curated.items():
        for row in entry.get("subsidiaries") or []:
            assert row["sub_symbol"] not in ADANI_SIBLINGS, (
                f"{sym} wrongly lists sibling {row['sub_symbol']}"
            )


# --- (a) ADANIENT: incubator note, zero siblings ---


def test_adanient_returns_note_no_siblings(api):
    res = api.get_listed_subsidiaries("ADANIENT")
    assert res is not None
    assert res["subsidiaries"] == []
    assert "note" in res and res["note"]
    blob = str(res)
    for sib in ADANI_SIBLINGS:
        assert sib not in blob, f"sibling {sib} leaked into ADANIENT SOTP"


# --- (b) SBIN: real curated subsidiaries surface (no network via no-shares path) ---


def test_curated_parent_returns_subsidiaries(api, monkeypatch):
    # Force the "can't price" branch so we never hit yfinance in the test.
    monkeypatch.setattr(api, "get_valuation_snapshot", lambda s: {})
    res = api.get_listed_subsidiaries("SBIN")
    assert res is not None
    syms = {r["symbol"] for r in res["subsidiaries"]}
    assert {"SBILIFE", "SBICARD"} <= syms
    for r in res["subsidiaries"]:
        assert r["source"] == "curated_map"
        assert r.get("needs_refresh") is True  # unpriced in the no-shares path


# --- (c) uncurated symbol → None ---


def test_uncurated_symbol_returns_none(api):
    assert api.get_listed_subsidiaries("NOTACONGLO") is None


# --- (d) deleted heuristic / AR functions are gone ---


def test_deleted_functions_absent():
    assert not hasattr(ResearchDataAPI, "get_group_structure")
    assert not hasattr(ResearchDataAPI, "_resolve_entity_ticker")
    assert not hasattr(ResearchDataAPI, "_find_promoter_owned_children")
    assert not hasattr(ResearchDataAPI, "_discover_recent_listings")
    from flowtracker.research import refresh

    assert not hasattr(refresh, "_detect_parent_subsidiary")
