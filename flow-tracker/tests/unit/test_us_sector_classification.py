"""US sector/industry classification (the GICS-resolver keystone).

US symbols now persist the GRANULAR yfinance ``industry`` on symbol_registry, and
``_us_industry_from_registry`` prefers it. That string already lives in the India
industry→sector sets, so ``_get_industry`` / ``_is_bfsi`` / ``get_sector_for_industry``
resolve correctly for US — instead of the coarse GICS map ('Financials' → 'Banks',
which matched nothing). India classification is untouched.
"""

import pytest

from flowtracker.store import FlowStore
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.sector_kpis import get_sector_for_industry

US = "NASDAQ"

# (symbol, granular yfinance industry, expected sector key)
CASES = [
    ("JPM", "Banks - Diversified", "banks"),
    ("ALL", "Insurance - Property & Casualty", "insurance"),
    ("O", "REIT - Retail", "real_estate"),
    ("PLD", "REIT - Industrial", "real_estate"),
    ("PFE", "Drug Manufacturers - General", "pharma"),
    ("NVDA", "Semiconductors", "it_services"),
    ("MSFT", "Software - Infrastructure", "it_services"),
    ("XOM", "Oil & Gas Integrated", "oil_and_gas"),
    ("UNH", "Healthcare Plans", "insurance"),
]


@pytest.fixture
def api(tmp_path, monkeypatch):
    db = tmp_path / "cls.db"
    monkeypatch.setenv("FLOWTRACKER_DB", str(db))
    with FlowStore(db_path=db) as store:
        for sym, industry, _ in CASES:
            store.upsert_symbol_registry(
                sym, US, company_name=f"{sym} Inc.",
                sector="(coarse GICS)", gics="(coarse GICS)", industry=industry,
            )
        # A US symbol with only a coarse sector and NO granular industry,
        # to exercise the _US_GICS_TO_INDUSTRY fallback.
        store.upsert_symbol_registry("COARSE", US, sector="Technology", gics="Technology")
    a = ResearchDataAPI()
    try:
        yield a
    finally:
        a.close()


def test_industry_column_round_trips(tmp_path, monkeypatch):
    db = tmp_path / "rt.db"
    monkeypatch.setenv("FLOWTRACKER_DB", str(db))
    with FlowStore(db_path=db) as store:
        store.upsert_symbol_registry("JPM", US, industry="Banks - Diversified")
        entry = store.get_symbol_registry_entry("JPM", US)
    assert entry is not None
    assert entry["industry"] == "Banks - Diversified"


@pytest.mark.parametrize("sym,industry,sector", CASES, ids=[c[0] for c in CASES])
def test_us_industry_resolves_to_sector(api, sym, industry, sector):
    # Granular industry flows through _get_industry…
    assert api._get_industry(sym) == industry
    # …and resolves to the correct sector key.
    assert get_sector_for_industry(industry) == sector


def test_us_bank_gates_bfsi(api):
    assert api._is_bfsi("JPM") is True
    assert api._is_insurance("JPM") is False


def test_us_insurer_gates_insurance(api):
    assert api._is_insurance("ALL") is True
    assert api._is_bfsi("ALL") is False


def test_us_reit_gates_realestate(api):
    assert api._is_realestate("O") is True
    assert api._is_realestate("PLD") is True


def test_coarse_fallback_when_no_granular_industry(api):
    # No granular industry on file → coarse GICS map 'Technology' → 'IT - Software'.
    assert api._get_industry("COARSE") == "IT - Software"
