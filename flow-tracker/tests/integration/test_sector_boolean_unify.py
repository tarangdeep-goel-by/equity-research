"""Coarse sector booleans on ResearchDataAPI derive from the canonical sector
resolver (one source of truth).

`_is_bfsi`, `_is_metals`, `_is_conglomerate`, `_is_insurance` each OR the
canonical resolver family (`sector_kpis.industry_in_family`) against their
legacy `_*_INDUSTRIES` frozenset. The change is strictly *additive*: every
industry that was True before stays True, and we additionally pick up
industries that resolve to a family sector via the canonical resolver but are
absent from the legacy frozenset.
"""

from __future__ import annotations

import pytest

from flowtracker.research import data_api as _dapi
from flowtracker.research import sector_kpis
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


@pytest.fixture
def api(tmp_path):
    db = tmp_path / "t.db"
    store = FlowStore(db_path=db)
    store.__enter__()
    api = ResearchDataAPI(store)
    yield api
    store.__exit__(None, None, None)


def _seed_industry(api, symbol, industry):
    """Insert a company_snapshot row so _get_industry(symbol) returns `industry`."""
    api._store._conn.execute(
        "INSERT OR REPLACE INTO company_snapshot (symbol, industry) VALUES (?, ?)",
        (symbol, industry),
    )
    api._store._conn.commit()


# --- BFSI ---------------------------------------------------------------


def test_bfsi_additive_from_resolver(api):
    """'Asset Management Company' resolves to amc_capital_markets (a BFSI-family
    sector) but is NOT in the legacy _BFSI_INDUSTRIES frozenset → now True."""
    industry = "Asset Management Company"
    assert industry not in _dapi._BFSI_INDUSTRIES  # was False under legacy
    assert sector_kpis.get_sector_for_industry(industry) in sector_kpis.BFSI_SECTORS
    _seed_industry(api, "HDFCAMC", industry)
    assert api._is_bfsi("HDFCAMC") is True


def test_bfsi_legacy_still_true(api):
    _seed_industry(api, "HDFCBANK", "Private Sector Bank")
    assert api._is_bfsi("HDFCBANK") is True


def test_bfsi_unrelated_false(api):
    _seed_industry(api, "SUNPHARMA", "Pharmaceuticals")
    assert api._is_bfsi("SUNPHARMA") is False


# --- Metals -------------------------------------------------------------


def test_metals_additive_from_resolver(api):
    """'Mining & Mineral products' resolves to metals_and_mining but is NOT in
    the legacy _METALS_INDUSTRIES frozenset → now True."""
    industry = "Mining & Mineral products"
    assert industry not in _dapi._METALS_INDUSTRIES
    assert (
        sector_kpis.get_sector_for_industry(industry) in sector_kpis.METALS_SECTORS
    )
    _seed_industry(api, "NMDC", industry)
    assert api._is_metals("NMDC") is True


def test_metals_legacy_still_true(api):
    _seed_industry(api, "TATASTEEL", "Iron & Steel")
    assert api._is_metals("TATASTEEL") is True


def test_metals_unrelated_false(api):
    _seed_industry(api, "SUNPHARMA", "Pharmaceuticals")
    assert api._is_metals("SUNPHARMA") is False


# --- Conglomerate -------------------------------------------------------


def test_conglomerate_additive_from_resolver(api):
    """'Trading' resolves to the conglomerate sector but is NOT in the legacy
    _CONGLOMERATE_INDUSTRIES frozenset → now True."""
    industry = "Trading"
    assert industry not in _dapi._CONGLOMERATE_INDUSTRIES
    assert (
        sector_kpis.get_sector_for_industry(industry)
        in sector_kpis.CONGLOMERATE_SECTORS
    )
    _seed_industry(api, "SOMETRADER", industry)
    assert api._is_conglomerate("SOMETRADER") is True


def test_conglomerate_legacy_industry_still_true(api):
    _seed_industry(api, "SOMECONGLO", "Conglomerates")
    assert api._is_conglomerate("SOMECONGLO") is True


def test_conglomerate_name_keyword_still_works(api):
    # industry not a conglomerate, but the company name keyword triggers it.
    _seed_industry(api, "RELIANCE", "Refineries")
    api._store._conn.execute(
        "UPDATE company_snapshot SET name = ? WHERE symbol = ?",
        ("Reliance Industries Ltd", "RELIANCE"),
    )
    api._store._conn.commit()
    assert api._is_conglomerate("RELIANCE") is True


def test_conglomerate_unrelated_false(api):
    _seed_industry(api, "SUNPHARMA", "Pharmaceuticals")
    assert api._is_conglomerate("SUNPHARMA") is False


# --- Insurance ----------------------------------------------------------


def test_insurance_legacy_still_true(api):
    _seed_industry(api, "HDFCLIFE", "Life Insurance")
    assert api._is_insurance("HDFCLIFE") is True
    _seed_industry(api, "ICICIGI", "General Insurance")
    assert api._is_insurance("ICICIGI") is True


def test_insurance_resolver_family_true(api):
    # both legacy frozenset and resolver agree for the canonical insurance label
    industry = "Life Insurance"
    assert (
        sector_kpis.get_sector_for_industry(industry)
        in sector_kpis.INSURANCE_SECTORS
    )


def test_insurance_unrelated_false(api):
    _seed_industry(api, "SUNPHARMA", "Pharmaceuticals")
    assert api._is_insurance("SUNPHARMA") is False
