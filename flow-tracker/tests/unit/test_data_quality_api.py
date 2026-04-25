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
            reserves: float = 0.0) -> AnnualFinancials:
    return AnnualFinancials(
        symbol="X", fiscal_year_end=fy, revenue=revenue, net_income=net_income,
        total_assets=total_assets, equity_capital=equity, reserves=reserves,
    )


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
