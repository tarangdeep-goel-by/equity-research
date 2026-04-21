"""Tests for E4 (named FII holders) + E7 (ADR/GDR stub) on get_ownership.

E4: Post-eval v1 carry-over. BHARTIARTL eval found that
get_ownership(section='shareholder_detail') returned only DII holders
because the top-N sort was broken (looked for wide-format quarterly
columns on a narrow-format row schema). Large-cap stocks with 28%+ FII
holding had ZERO named FII entities surfaced.

E7: ADR/GDR outstanding data is missing for US-listed Indian names
(HDFCBANK, INFY, etc.). We stub the API surface + schema here so
agents stop re-failing on missing sections; live extraction is deferred
to a follow-up PR that wires the AR extractor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_with_fii(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI pointed at a fresh store with seeded FII+DII holders.

    Mimics Screener's per-classification dict-of-lists shape accepted by
    store.upsert_shareholder_details.
    """
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    store = FlowStore(db_path=tmp_db)
    store.upsert_shareholder_details(
        "BHARTI_T",
        {
            "foreign_institutions": [
                # 3 FII holders: two >= 1%, one < 1%
                {
                    "name": "Government Of Singapore",
                    "values": {"Sep 2025": "1.80", "Jun 2025": "1.75"},
                    "url": "",
                },
                {
                    "name": "Europacific Growth Fund",
                    "values": {"Sep 2025": "1.20", "Jun 2025": "1.15"},
                    "url": "",
                },
                {
                    "name": "Small Foreign Fund",
                    "values": {"Sep 2025": "0.50", "Jun 2025": "0.48"},
                    "url": "",
                },
            ],
            "domestic_institutions": [
                # 1 DII holder > both FIIs — exercises cross-class ordering
                {
                    "name": "Life Insurance Corporation Of India",
                    "values": {"Sep 2025": "3.85", "Jun 2025": "3.70"},
                    "url": "",
                },
            ],
        },
    )
    store.close()

    api = ResearchDataAPI()
    yield api
    api.close()


@pytest.fixture
def api_empty(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    """Empty-store API for non-ADR / non-FII path tests."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    # Create the store so schema exists
    store = FlowStore(db_path=tmp_db)
    store.close()
    api = ResearchDataAPI()
    yield api
    api.close()


# ---------------------------------------------------------------------------
# E4 — Named FII holders surface through shareholder_detail
# ---------------------------------------------------------------------------


def test_named_fii_holders_in_shareholder_detail(api_with_fii):
    """≥1% FII holders must appear; <1% holders excluded."""
    rows = api_with_fii.get_shareholder_detail("BHARTI_T")

    # Must be pivoted: one entry per holder (not per holder × quarter).
    names = [r.get("name") or r.get("holder_name") for r in rows]
    assert "Government Of Singapore" in names, (
        f"FII holder at 1.8% latest should be surfaced; got names={names}"
    )
    assert "Europacific Growth Fund" in names, (
        f"FII holder at 1.2% latest should be surfaced; got names={names}"
    )
    # Below threshold — excluded.
    assert "Small Foreign Fund" not in names, (
        "Sub-1% FII holder must be filtered out of shareholder_detail"
    )


def test_shareholder_detail_labels_fii_classification(api_with_fii):
    """Each returned holder carries an FII / DII / Promoter / Public label.

    Agents need to decompose a 28% FII stake — the raw screener class
    'foreign_institutions' is awkward in reports; normalize to 'FII'.
    """
    rows = api_with_fii.get_shareholder_detail("BHARTI_T")
    gos = next(
        r for r in rows
        if (r.get("name") or r.get("holder_name")) == "Government Of Singapore"
    )
    # Either a new 'holder_type' field or a normalized 'classification'.
    holder_type = gos.get("holder_type") or gos.get("classification")
    assert holder_type in ("FII", "foreign_institutions"), (
        f"Expected FII/foreign_institutions marker, got {holder_type!r}"
    )
    # The pivoted row must expose latest_pct for downstream sort/display.
    assert isinstance(gos.get("latest_pct"), (int, float))
    assert gos["latest_pct"] == pytest.approx(1.80, abs=0.01)


def test_shareholder_detail_reserves_fii_slots(tmp_db, monkeypatch):
    """When a DII-heavy name has 20+ >=1% DII holders AND small FII holders,
    the top-N cap must still surface some FII entries so agents can
    decompose the aggregate FII stake (the BHARTIARTL pattern).
    """
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    store = FlowStore(db_path=tmp_db)
    # 25 DII holders at 2.0-3.0%
    dii = [
        {
            "name": f"DII Fund {i:02d}",
            "values": {"Sep 2025": str(3.0 - 0.02 * i)},
            "url": "",
        }
        for i in range(25)
    ]
    # 3 FII holders at ~1.0-1.3% — would all be evicted by a pure global
    # top-20 sort (DII fund #20 at 2.60% is higher).
    fii = [
        {"name": "Govt Of Singapore", "values": {"Sep 2025": "1.30"}, "url": ""},
        {"name": "Europacific Growth Fund", "values": {"Sep 2025": "1.15"}, "url": ""},
        {"name": "Govt Pension Fund Global", "values": {"Sep 2025": "1.05"}, "url": ""},
    ]
    store.upsert_shareholder_details(
        "FIIHEAVY",
        {"domestic_institutions": dii, "foreign_institutions": fii},
    )
    store.close()

    api = ResearchDataAPI()
    try:
        rows = api.get_shareholder_detail("FIIHEAVY", top_n=20)
        fii_rows = [r for r in rows if r.get("holder_type") == "FII"]
        assert len(fii_rows) >= 3, (
            f"Expected all 3 FII holders reserved in top-20; got {len(fii_rows)}: "
            f"{[r['name'] for r in fii_rows]}"
        )
        # Global sort must still hold on the returned slice.
        pcts = [r.get("latest_pct") for r in rows]
        assert pcts == sorted(pcts, reverse=True)
    finally:
        api.close()


def test_shareholder_detail_sorted_by_latest_pct(api_with_fii):
    """Global sort by latest_pct desc (LIC 3.85 > GoS 1.80 > Europacific 1.20)."""
    rows = api_with_fii.get_shareholder_detail("BHARTI_T")
    latest_pcts = [r.get("latest_pct") for r in rows if r.get("latest_pct") is not None]
    assert latest_pcts == sorted(latest_pcts, reverse=True), (
        f"shareholder_detail must be sorted by latest_pct desc; got {latest_pcts}"
    )


# ---------------------------------------------------------------------------
# E7 — ADR/GDR sub-section
# ---------------------------------------------------------------------------


def test_adr_gdr_sub_section_structure(api_empty):
    """Known-ADR symbol (HDFCBANK) returns the declared schema.

    Since live AR extraction isn't wired, the values can be None but the
    shape must be stable so downstream agents can rely on keys existing.
    """
    data = api_empty.get_adr_gdr("HDFCBANK")
    assert isinstance(data, dict)
    # Required keys per plan-v2 §7 E7.
    for key in ("listed_on", "outstanding_units_mn", "pct_of_total_equity",
                "as_of_date", "source"):
        assert key in data, f"ADR/GDR payload missing required key {key!r}"
    # HDFCBANK is known to have an NYSE ADR listing.
    assert isinstance(data["listed_on"], list)
    assert any("NYSE" in str(x).upper() for x in data["listed_on"])
    # Stub marker — explicit so callers know the numeric fields aren't live.
    meta = data.get("_meta", {})
    assert meta.get("stub") is True, (
        f"Known-ADR stub must flag _meta.stub=True; got {meta!r}"
    )


def test_adr_gdr_empty_for_non_adr_symbol(api_empty):
    """Symbol with no ADR (RELIANCE) returns empty list + stub metadata."""
    data = api_empty.get_adr_gdr("RELIANCE")
    assert isinstance(data, dict)
    assert data.get("listed_on") == []
    meta = data.get("_meta", {})
    assert meta.get("stub") is True


def test_adr_gdr_routed_through_get_ownership(api_empty):
    """get_ownership(section='adr_gdr') proxies to the ADR/GDR extractor."""
    # Router-level: confirms the tool exposes adr_gdr as a first-class
    # section so agents can drill without a separate tool call.
    from flowtracker.research.tools import _get_ownership_section

    data = _get_ownership_section(api_empty, "HDFCBANK", "adr_gdr", {})
    assert isinstance(data, dict)
    assert "listed_on" in data
