"""Tests for ResearchDataAPI quality-flag surface and DuPont effective_window."""
from __future__ import annotations

import pytest

from flowtracker.data_quality import Flag, longest_unflagged_window
from flowtracker.fund_models import AnnualFinancials
from flowtracker.research.data_api import ResearchDataAPI


# ------------------------------------------------------------------ helpers

def _flag(symbol: str, curr_fy: str, line: str, severity: str = "MEDIUM",
          prior_fy: str = "2024-03-31") -> Flag:
    return Flag(
        symbol=symbol, prior_fy=prior_fy, curr_fy=curr_fy, line=line,
        prior_val=100.0, curr_val=400.0, jump_pct=300.0,
        revenue_change_pct=5.0, flag_type="RECLASS", severity=severity,
    )


def _annual(fy: str, revenue: float = 100000.0, net_income: float = 10000.0,
            total_assets: float = 200000.0, equity: float = 50000.0,
            reserves: float = 0.0, **extras) -> AnnualFinancials:
    fields = dict(
        symbol="X", fiscal_year_end=fy, revenue=revenue, net_income=net_income,
        total_assets=total_assets, equity_capital=equity, reserves=reserves,
    )
    fields.update(extras)
    return AnnualFinancials(**fields)


@pytest.fixture
def api(monkeypatch, tmp_db):
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# --------------------------------------------------------- API surface tests

def test_get_data_quality_flags_returns_stored_rows(api):
    api._store.upsert_data_quality_flags([
        _flag("HDFCBANK", "2026-03-31", "other_expenses_detail", "MEDIUM"),
        _flag("HDFCBANK", "2025-03-31", "borrowings", "LOW"),
    ])
    medium_plus = api.get_data_quality_flags("HDFCBANK")  # default MEDIUM
    assert len(medium_plus) == 1
    assert medium_plus[0]["line"] == "other_expenses_detail"

    everything = api.get_data_quality_flags("HDFCBANK", min_severity="LOW")
    assert len(everything) == 2


def test_get_data_quality_flags_unknown_symbol(api):
    assert api.get_data_quality_flags("NOT_A_REAL_SYMBOL") == []


# ------------------------------------------------- longest_unflagged_window

def test_longest_unflagged_window_no_flags():
    annuals = [_annual("2026-03-31"), _annual("2025-03-31"), _annual("2024-03-31")]
    seg, dropped = longest_unflagged_window(annuals, [])
    assert len(seg) == 3
    assert dropped == []


def test_longest_unflagged_window_flag_at_most_recent_boundary():
    """Flag at FY26 boundary → segment is FY25 + earlier, dropping FY26."""
    annuals = [
        _annual("2026-03-31"), _annual("2025-03-31"),
        _annual("2024-03-31"), _annual("2023-03-31"),
    ]
    flags = [{"prior_fy": "2025-03-31", "curr_fy": "2026-03-31",
              "line": "other_expenses_detail", "severity": "MEDIUM"}]
    seg, dropped = longest_unflagged_window(annuals, flags)
    assert [a.fiscal_year_end for a in seg] == [
        "2025-03-31", "2024-03-31", "2023-03-31",
    ]
    assert len(dropped) == 1


def test_longest_unflagged_window_picks_longer_pre_break_segment():
    """Two flags split history into 1-year + 4-year segments — picks the 4-year."""
    annuals = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2, 1, 0)]
    flags = [
        {"prior_fy": "2025-03-31", "curr_fy": "2026-03-31", "line": "x", "severity": "MEDIUM"},
        {"prior_fy": "2024-03-31", "curr_fy": "2025-03-31", "line": "y", "severity": "HIGH"},
    ]
    seg, dropped = longest_unflagged_window(annuals, flags)
    assert [a.fiscal_year_end for a in seg] == [
        "2024-03-31", "2023-03-31", "2022-03-31", "2021-03-31", "2020-03-31",
    ]
    assert len(dropped) == 2


def test_longest_unflagged_window_works_with_dict_rows():
    """The helper should accept dict rows too (for code paths that don't use Pydantic)."""
    annuals = [{"fiscal_year_end": "2026-03-31"}, {"fiscal_year_end": "2025-03-31"}]
    flags = [{"prior_fy": "2025-03-31", "curr_fy": "2026-03-31", "line": "x", "severity": "MEDIUM"}]
    seg, dropped = longest_unflagged_window(annuals, flags)
    assert len(seg) == 1


# ---------------------------------------------- get_dupont_decomposition

def test_dupont_full_window_when_no_flags(api):
    rows = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    result = api.get_dupont_decomposition("X")
    assert result["source"] == "screener"
    assert len(result["years"]) == 5
    ew = result["effective_window"]
    assert ew["n_years"] == 5
    assert ew["start_fy"] == "2022-03-31"
    assert ew["end_fy"] == "2026-03-31"
    assert ew["narrowed_due_to"] == []


def test_dupont_narrows_when_medium_flag_overlaps(api):
    """MEDIUM flag at FY26 boundary → DuPont uses FY22-FY25 only."""
    rows = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_dupont_decomposition("X")
    years_in_result = [r["fiscal_year_end"] for r in result["years"]]
    assert "2026-03-31" not in years_in_result
    ew = result["effective_window"]
    assert ew["end_fy"] == "2025-03-31"
    assert ew["n_years"] == 4
    assert len(ew["narrowed_due_to"]) == 1
    assert ew["narrowed_due_to"][0]["curr_fy"] == "2026-03-31"


def test_dupont_low_flag_does_not_narrow(api):
    """LOW flags are advisory only — DuPont uses the full window."""
    rows = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "LOW",
              prior_fy="2025-03-31"),
    ])
    result = api.get_dupont_decomposition("X")
    assert result["effective_window"]["n_years"] == 5
    assert result["effective_window"]["narrowed_due_to"] == []


# --------------------------------------------------- get_piotroski_score

def _annual_for_fscore(fy: str, **extras) -> AnnualFinancials:
    """F-score needs richer fields than DuPont — populate the criteria inputs."""
    base = dict(
        revenue=100000.0, net_income=10000.0, total_assets=200000.0,
        equity_capital=50000.0, reserves=0.0,
        cfo=12000.0, borrowings=30000.0, eps=10.0, num_shares=1000.0,
        operating_profit=15000.0, raw_material_cost=40000.0,
        interest=2000.0,
    )
    base.update(extras)
    return _annual(fy, **base)


def test_fscore_shifts_back_when_latest_pair_flagged(api):
    """F-score should use (FY25, FY24) when FY26 has a MEDIUM flag."""
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_piotroski_score("X")
    assert "score" in result, result
    ew = result["effective_window"]
    # The (start, end) pair used should be FY24, FY25 — not FY25, FY26
    assert ew["end_fy"] == "2025-03-31"
    assert ew["start_fy"] == "2024-03-31"
    assert len(ew["narrowed_due_to"]) == 1


def test_fscore_uses_latest_when_no_flags(api):
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4)]
    api._store.upsert_annual_financials(rows)
    result = api.get_piotroski_score("X")
    ew = result["effective_window"]
    assert ew["end_fy"] == "2026-03-31"
    assert ew["start_fy"] == "2025-03-31"


def test_fscore_abstains_when_no_unflagged_pair(api):
    """If every consecutive pair spans a flag, F-score should error cleanly."""
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4)]
    api._store.upsert_annual_financials(rows)
    # Flag every boundary so no pair is unflagged
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "x", "HIGH", prior_fy="2025-03-31"),
        _flag("X", "2025-03-31", "x", "HIGH", prior_fy="2024-03-31"),
    ])
    result = api.get_piotroski_score("X")
    assert "error" in result
    assert "abstained" in result["error"].lower()
    assert result["effective_window"]["n_years"] == 1


# --------------------------------------------------- get_growth_cagr_table

def test_cagr_suppresses_horizons_spanning_flag(api):
    """Flag at FY26 boundary → 1y/3y/5y/10y horizons starting at FY25 or earlier
    and ending at FY26 are all suppressed."""
    # 11 years for full 10y horizon coverage
    rows = [_annual(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_growth_cagr_table("X")
    assert "1y" not in result["cagrs"]["revenue"] or result["cagrs"]["revenue"].get("1y") is None
    ew = result["effective_window"]
    assert "1y" in ew["suppressed_horizons"]
    assert "3y" in ew["suppressed_horizons"]


def test_cagr_unaffected_when_no_flags(api):
    """No flags → all horizons compute and effective_window has no suppression."""
    rows = [_annual(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
    api._store.upsert_annual_financials(rows)
    result = api.get_growth_cagr_table("X")
    assert result["effective_window"]["suppressed_horizons"] == []
    # latest revenue still surfaces
    assert result["cagrs"]["revenue"]["latest"] == 100000.0


# --------------------------------------------------- get_common_size_pl

def test_common_size_narrows_when_flag_overlaps(api):
    """Common-size with a MEDIUM flag at FY26 → segment ends FY25."""
    rows = [_annual(f"202{i}-03-31",
                    operating_profit=15000.0, raw_material_cost=40000.0,
                    interest=2000.0, depreciation=3000.0,
                    employee_cost=10000.0, other_expenses_detail=20000.0,
                    profit_before_tax=12000.0)
            for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_common_size_pl("X")
    fys = [r["fiscal_year"] for r in result["years"]]
    assert "2026-03-31" not in fys
    ew = result["effective_window"]
    assert ew["end_fy"] == "2025-03-31"
    assert ew["n_years"] == 4
    assert len(ew["narrowed_due_to"]) == 1


# --------------------------------------------------- prompt rule integrity

def test_shared_preamble_mentions_flags():
    """SHARED_PREAMBLE_V2 must instruct agents to call get_data_quality_flags
    before chaining multi-year ratios — defends the prompt-level contract."""
    from flowtracker.research.prompts import SHARED_PREAMBLE_V2
    assert "get_data_quality_flags" in SHARED_PREAMBLE_V2
    assert "Reclassification" in SHARED_PREAMBLE_V2 or "reclassification" in SHARED_PREAMBLE_V2
    # Must reference at least one of the gated trend methods so agents know it applies
    assert any(m in SHARED_PREAMBLE_V2 for m in
               ["DuPont", "F-score", "F-Score", "CAGR", "margin walk", "common-size"])
