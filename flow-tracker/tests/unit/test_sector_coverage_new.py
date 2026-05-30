"""New-sector coverage guards (2026-05-30 backfill gap).

The yfinance industry backfill surfaced ~70 industries with no sector skill.
Tier-1 remapped aliases to existing skills; six new Tier-2 skills were authored
(textiles, building_materials, packaging, media, hospitality, logistics). These
tests pin the industry→skill resolution and the presence of the new skill files
so a map edit or a deleted skill dir flips red.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.prompts import _industry_to_sector_skill

SKILLS_DIR = Path(__file__).resolve().parents[2] / "flowtracker" / "research" / "sector_skills"

# (yfinance industry string, expected sector skill dir)
TIER1_REMAPS = [
    ("Software - Application", "it_services"),
    ("Information Technology Services", "it_services"),
    ("Specialty Industrial Machinery", "capital_goods"),
    ("Metal Fabrication", "capital_goods"),
    ("Tools & Accessories", "capital_goods"),
    ("Agricultural Inputs", "chemicals"),
    ("Confectioners", "fmcg"),
    ("Farm Products", "fmcg"),
    ("Utilities - Regulated Electric", "regulated_power"),
]

NEW_SECTOR_INDUSTRIES = [
    ("Textile Manufacturing", "textiles"),
    ("Apparel Manufacturing", "textiles"),
    ("Footwear & Accessories", "textiles"),
    ("Luxury Goods", "textiles"),
    ("Building Materials", "building_materials"),
    ("Building Products & Equipment", "building_materials"),
    ("Packaging & Containers", "packaging"),
    ("Paper & Paper Products", "packaging"),
    ("Entertainment", "media"),
    ("Broadcasting", "media"),
    ("Publishing", "media"),
    ("Advertising Agencies", "media"),
    ("Lodging", "hospitality"),
    ("Restaurants", "hospitality"),
    ("Travel Services", "hospitality"),
    ("Integrated Freight & Logistics", "logistics"),
    ("Marine Shipping", "logistics"),
    ("Railroads", "logistics"),
    ("Trucking", "logistics"),
]

NEW_SECTORS = ["textiles", "building_materials", "packaging", "media", "hospitality", "logistics"]
SKILL_FILES = ["_shared.md", "sector.md", "valuation.md", "financials.md", "risk.md"]


@pytest.mark.parametrize("industry,expected", TIER1_REMAPS + NEW_SECTOR_INDUSTRIES)
def test_industry_resolves_to_expected_skill(industry, expected):
    assert _industry_to_sector_skill(industry) == expected


@pytest.mark.parametrize("sector", NEW_SECTORS)
@pytest.mark.parametrize("fname", SKILL_FILES)
def test_new_sector_skill_files_exist_and_nonempty(sector, fname):
    path = SKILLS_DIR / sector / fname
    assert path.exists(), f"missing skill file: {path}"
    assert len(path.read_text().strip()) > 500, f"skill file too thin: {path}"


@pytest.mark.parametrize("sector", NEW_SECTORS)
def test_new_sector_shared_has_valuation_framework(sector):
    """Each new _shared.md must name a primary valuation multiple (sector skills
    exist primarily to anchor the right framework)."""
    shared = (SKILLS_DIR / sector / "_shared.md").read_text().lower()
    assert "ev/ebitda" in shared or "p/e" in shared or "pe " in shared
