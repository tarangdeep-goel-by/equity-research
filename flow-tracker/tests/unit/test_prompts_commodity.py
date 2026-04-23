"""VEDL regression guards (PR-10) — commodity-framework discipline.

Post-eval v2 retry found VEDL valuation regressed to F(53) because the agent
applied DCF/static-PE on a commodity stock instead of routing to the
commodity/cyclical framework. Discipline lives in
`research/sector_skills/metals/_shared.md` (+ `metals/valuation.md`). These
tests pin signal phrases so accidental deletion / reword flips them red.
"""
from __future__ import annotations

from pathlib import Path

import flowtracker.research.prompts as prompts_module

METALS_SKILLS_DIR = Path(prompts_module.__file__).parent / "sector_skills" / "metals"


def _load(name: str) -> str:
    path = METALS_SKILLS_DIR / name
    assert path.exists(), f"expected metals skill file: {path}"
    return path.read_text()


def test_commodity_sector_has_commodity_framework_tenet():
    """Metals sector prompt must flag commodity/cyclical nature AND name an
    anti-generic-valuation framework cue. Accepts a union of phrases so minor
    rewording doesn't break the test — but the combined set must cover
    (a) cyclical framing and (b) framework-discipline.
    """
    combined = (_load("_shared.md") + "\n" + _load("valuation.md")).lower()

    cyclical_cues = [
        "commodity", "cyclical", "mid-cycle", "through-cycle",
        "cycle peak", "cycle trough", "price-taker", "replacement cost",
    ]
    assert any(c in combined for c in cyclical_cues), (
        f"metals prompt lost cyclical/commodity framing — expected any of {cyclical_cues}"
    )

    framework_cues = [
        "ev/ebitda", "ev/ton", "ev per ton", "replacement cost",
        "through-cycle ebitda", "pe at cycle peak", "dcf without cycle-normalization",
    ]
    assert any(c in combined for c in framework_cues), (
        f"metals prompt lost commodity-framework discipline — expected any of {framework_cues}"
    )


def test_commodity_framework_warns_against_generic_pe_or_dcf():
    """Metals skill must explicitly name PE and DCF as failure modes for
    commodity stocks — root cause of VEDL regression.
    """
    valuation = _load("valuation.md").lower()

    pe_warning_cues = [
        "pe at cycle peak", "pe at cycle trough", "pe is inverted",
        "pe therefore mis-signals", "do not cite pe in isolation", "defaulting to pe",
    ]
    assert any(c in valuation for c in pe_warning_cues), (
        f"metals valuation.md lost PE-failure-mode warning — expected any of {pe_warning_cues}"
    )

    dcf_discipline_cues = [
        "dcf without cycle-normalization", "through-cycle ebitda", "reverse-dcf on through-cycle",
    ]
    assert any(c in valuation for c in dcf_discipline_cues), (
        f"metals valuation.md lost DCF / through-cycle discipline — expected any of {dcf_discipline_cues}"
    )
