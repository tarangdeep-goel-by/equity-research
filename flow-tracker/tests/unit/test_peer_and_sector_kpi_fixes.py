"""Eval follow-up: peer size-band filter + sector-KPI gaps (2026-05-29).

1. get_screener_peers drops off-size micro-cap peers for large-cap subjects
   (ADANIENT was grouped with ₹11 Cr / ₹407 Cr names via its "Thermal Coal" tag).
2. "Thermal Coal" now maps to a real KPI sector (was None → empty framework).
3. power_and_utilities gained RDA + regulated-RoE KPIs (NTPC eval gap).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.sector_kpis import (
    get_sector_for_industry,
    get_kpi_keys_for_industry,
)
from flowtracker.store import FlowStore


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


def _seed_peers(store, symbol, rows):
    store.upsert_peers(symbol, rows)


# --- 1. peer size-band filter ---


def test_large_cap_drops_microcap_peers(api):
    # Subject ₹3.8L Cr + a real peer ₹50k Cr + two micro-caps + self + median.
    api._store.upsert_peers("ADANIENT", [
        {"peer_symbol": "ADANIENT", "name": "Adani Enterp.", "market_cap": 384222.0, "pe": 121.0},
        {"peer_symbol": "BIGPEER", "name": "Big Peer", "market_cap": 50000.0, "pe": 30.0},
        {"peer_symbol": "540492", "name": "Starlineps", "market_cap": 407.0, "pe": 68.0},
        {"peer_symbol": "ARENTERP", "name": "Rajdarshan", "market_cap": 11.0, "pe": None},
        {"peer_symbol": None, "name": "Median: 3 Co.", "market_cap": 19200.0, "pe": 50.0},
    ])
    out = api.get_screener_peers("ADANIENT")
    names = {p["peer_name"] for p in out}
    assert "Starlineps" not in names and "Rajdarshan" not in names  # micro-caps dropped (<5% of 3.8L)
    assert "Big Peer" in names            # real peer kept
    assert "Adani Enterp." in names       # self kept
    assert "Median: 3 Co." in names       # summary row kept


def test_small_cap_subject_keeps_all_peers(api):
    # Subject is small (₹800 Cr) → no filtering; peer set untouched.
    api._store.upsert_peers("SMALLCO", [
        {"peer_symbol": "SMALLCO", "name": "Small Co", "market_cap": 800.0, "pe": 15.0},
        {"peer_symbol": "TINY1", "name": "Tiny One", "market_cap": 120.0, "pe": 12.0},
        {"peer_symbol": "TINY2", "name": "Tiny Two", "market_cap": 60.0, "pe": 10.0},
    ])
    out = api.get_screener_peers("SMALLCO")
    assert len(out) == 3  # nothing dropped — floor scales with subject


def test_empty_peers_safe(api):
    assert api.get_screener_peers("NOPEERS") == []


# --- 2 & 3. sector-KPI gaps ---


def test_thermal_coal_maps_to_sector():
    assert get_sector_for_industry("Thermal Coal") == "metals_and_mining"
    assert get_sector_for_industry("Coal") == "metals_and_mining"
    keys = get_kpi_keys_for_industry("Thermal Coal")
    assert keys and len(keys) > 0  # framework now non-empty


def test_power_has_rda_and_regulated_roe():
    keys = get_kpi_keys_for_industry("Power Generation")
    assert "regulatory_deferral_account_cr" in keys
    assert "regulated_roe_pct" in keys
