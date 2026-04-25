"""Tests for ResearchDataAPI quality-flag surface, DuPont, F-score, and CAGR
narrowing. Updated post-Gemini-review for recency anchor + per-line CAGR
nullification + F-score abstain."""
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


# --------------------------------------------------------- API surface

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


# ----------------------------------------- longest_unflagged_window (recency)

def test_longest_unflagged_window_no_flags():
    annuals = [_annual("2026-03-31"), _annual("2025-03-31"), _annual("2024-03-31")]
    seg, dropped = longest_unflagged_window(annuals, [])
    assert len(seg) == 3
    assert dropped == []


def test_longest_unflagged_window_flag_at_most_recent_year():
    """Flag at FY26 (curr_fy) means break between FY25 and FY26.
    Recency anchor: segment containing T0 (FY26) is just [FY26]."""
    annuals = [
        _annual("2026-03-31"), _annual("2025-03-31"),
        _annual("2024-03-31"), _annual("2023-03-31"),
    ]
    flags = [{"prior_fy": "2025-03-31", "curr_fy": "2026-03-31",
              "line": "other_expenses_detail", "severity": "MEDIUM"}]
    seg, dropped = longest_unflagged_window(annuals, flags)
    assert [a.fiscal_year_end for a in seg] == ["2026-03-31"]
    assert len(dropped) == 1


def test_longest_unflagged_window_recency_picks_short_segment_over_old_long_segment():
    """Gemini review fix: prefer the recent segment even when an older one is
    longer. With a flag at FY26 and another at FY24, segments are
    [FY26] (1yr recent) vs [FY23, FY22, FY21, FY20] (4yr old). Helper must
    return the recent [FY26], not the longer historical era."""
    annuals = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2, 1, 0)]
    flags = [
        {"prior_fy": "2025-03-31", "curr_fy": "2026-03-31", "line": "x", "severity": "MEDIUM"},
        {"prior_fy": "2023-03-31", "curr_fy": "2024-03-31", "line": "y", "severity": "HIGH"},
    ]
    seg, dropped = longest_unflagged_window(annuals, flags)
    # Recent segment = [FY26] only (FY25 is across the FY26 flag)
    assert [a.fiscal_year_end for a in seg] == ["2026-03-31"]
    # Both flags are dropped (one excluded FY25..FY24, other excluded FY23..)
    assert len(dropped) == 2


def test_longest_unflagged_window_flag_two_years_back():
    """Flag at curr_fy=FY24 (prior_fy=FY23) means the break is BETWEEN FY23 and
    FY24 — FY24 is post-break (new era). Recent segment from FY26 walks back
    through the post-break era: [FY26, FY25, FY24]. FY23 is excluded."""
    annuals = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    flags = [{"prior_fy": "2023-03-31", "curr_fy": "2024-03-31", "line": "x", "severity": "MEDIUM"}]
    seg, dropped = longest_unflagged_window(annuals, flags)
    assert [a.fiscal_year_end for a in seg] == [
        "2026-03-31", "2025-03-31", "2024-03-31",
    ]
    assert len(dropped) == 1  # the FY24 flag excluded FY23..earlier


def test_longest_unflagged_window_works_with_dict_rows():
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


def test_dupont_narrows_to_recent_year_only_when_flag_at_top(api):
    """MEDIUM flag at FY26 → recency-anchor returns just [FY26]. Single-year
    DuPont is computable without prior-year averaging — better than analyzing
    a stale historical era."""
    rows = [_annual(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_dupont_decomposition("X")
    years_in_result = [r["fiscal_year_end"] for r in result["years"]]
    # Only FY26 is in the recent segment; older years are dropped.
    assert years_in_result == ["2026-03-31"]
    ew = result["effective_window"]
    assert ew["start_fy"] == "2026-03-31"
    assert ew["end_fy"] == "2026-03-31"
    assert ew["n_years"] == 1
    assert len(ew["narrowed_due_to"]) == 1


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
    base = dict(
        revenue=100000.0, net_income=10000.0, total_assets=200000.0,
        equity_capital=50000.0, reserves=0.0,
        cfo=12000.0, borrowings=30000.0, eps=10.0, num_shares=1000.0,
        operating_profit=15000.0, raw_material_cost=40000.0,
        interest=2000.0,
    )
    base.update(extras)
    return _annual(fy, **base)


def test_fscore_abstains_when_latest_pair_flagged(api):
    """Gemini fix #3: F-score must NOT silently shift back to (T-1, T-2) when
    (T, T-1) crosses a flag. Stale F-score is worse than no F-score."""
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_piotroski_score("X")
    assert "error" in result
    assert result.get("reason") == "stale_due_to_reclass"
    assert "fallback_hint" in result
    assert result["effective_window"]["n_years"] == 1


def test_fscore_uses_latest_when_no_flags(api):
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4)]
    api._store.upsert_annual_financials(rows)
    result = api.get_piotroski_score("X")
    ew = result["effective_window"]
    assert ew["end_fy"] == "2026-03-31"
    assert ew["start_fy"] == "2025-03-31"


def test_fscore_uses_recent_pair_when_older_year_flagged(api):
    """Flag at FY24 only → F-score uses (FY26, FY25), the recent post-break pair."""
    rows = [_annual_for_fscore(f"202{i}-03-31") for i in (6, 5, 4, 3, 2)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2024-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2023-03-31"),
    ])
    result = api.get_piotroski_score("X")
    assert "score" in result, result
    ew = result["effective_window"]
    assert ew["end_fy"] == "2026-03-31"
    assert ew["start_fy"] == "2025-03-31"


# --------------------------------------------------- get_growth_cagr_table

def test_cagr_revenue_ni_eps_unaffected_by_unrelated_reclass(api):
    """Gemini fix #2: a flag on other_expenses_detail (NOT in revenue/ni/eps
    dependency set) must NOT nullify revenue/ni/eps CAGRs. Only ebitda + fcf
    have op_profit + depreciation as dependencies."""
    rows = [_annual(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "other_expenses_detail", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_growth_cagr_table("X")
    # Revenue/ni/eps CAGRs survive — other_expenses_detail not in any of their deps.
    assert result["cagrs"]["revenue"].get("1y") is not None
    assert result["cagrs"]["net_income"].get("3y") is not None
    # No suppressed cells from this flag.
    assert result["effective_window"]["suppressed_cells"] == []
    assert result["effective_window"]["narrowed_due_to"] == []


def test_cagr_ebitda_suppressed_when_depreciation_flagged(api):
    """Depreciation IS in ebitda's dependency set → ebitda 1y/3y/5y CAGRs that
    span the flag should be suppressed."""
    rows = [_annual(f"20{i:02d}-03-31",
                    operating_profit=20000.0, depreciation=3000.0)
            for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
    api._store.upsert_annual_financials(rows)
    api._store.upsert_data_quality_flags([
        _flag("X", "2026-03-31", "depreciation", "MEDIUM",
              prior_fy="2025-03-31"),
    ])
    result = api.get_growth_cagr_table("X")
    suppressed = result["effective_window"]["suppressed_cells"]
    suppressed_metrics = {s["metric"] for s in suppressed}
    # ebitda affected; revenue/ni/eps untouched
    assert "ebitda" in suppressed_metrics
    assert "revenue" not in suppressed_metrics
    assert "net_income" not in suppressed_metrics
    # ebitda's spanning horizons should not have computed values.
    eb = result["cagrs"]["ebitda"]
    assert eb.get("1y") is None or "1y" not in eb


def test_cagr_unaffected_when_no_flags(api):
    rows = [_annual(f"20{i:02d}-03-31") for i in (26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16)]
    api._store.upsert_annual_financials(rows)
    result = api.get_growth_cagr_table("X")
    assert result["effective_window"]["suppressed_cells"] == []
    assert result["cagrs"]["revenue"]["latest"] == 100000.0


# --------------------------------------------------- get_common_size_pl

def test_common_size_narrows_to_recent_segment(api):
    """Common-size with a MEDIUM flag at FY26 → recent segment is [FY26] only."""
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
    # Recency anchor: segment containing T0 (FY26) is just [FY26].
    assert fys == ["2026-03-31"]
    ew = result["effective_window"]
    assert ew["n_years"] == 1
    assert ew["start_fy"] == "2026-03-31"
    assert ew["end_fy"] == "2026-03-31"
    assert len(ew["narrowed_due_to"]) == 1


# --------------------------------------------------- prompt rule integrity

def test_shared_preamble_mentions_flags():
    from flowtracker.research.prompts import SHARED_PREAMBLE_V2
    assert "get_data_quality_flags" in SHARED_PREAMBLE_V2
    assert "Reclassification" in SHARED_PREAMBLE_V2
    assert any(m in SHARED_PREAMBLE_V2 for m in
               ["DuPont", "F-score", "F-Score", "CAGR", "margin walk", "common-size"])


def test_shared_preamble_orders_concall_before_window():
    """Gemini fix #5: management's comparable basis must be checked BEFORE
    falling back to the unbroken sub-window."""
    from flowtracker.research.prompts import SHARED_PREAMBLE_V2
    rule_start = SHARED_PREAMBLE_V2.find("## Reclassification Breaks")
    rule = SHARED_PREAMBLE_V2[rule_start:]
    concall_idx = rule.find("comparable_growth_metrics")
    fallback_idx = rule.find("unbroken sub-window")
    assert 0 < concall_idx < fallback_idx, (
        f"Expected comparable_growth_metrics step (idx {concall_idx}) to come "
        f"BEFORE unbroken-window fallback (idx {fallback_idx})"
    )
