"""Unit tests for the discontinuity detector library."""
from __future__ import annotations

from flowtracker.data_quality import (
    JUMP_HIGH,
    JUMP_LOW,
    JUMP_MEDIUM,
    MIN_LINE_TO_REVENUE,
    Flag,
    detect,
)


def _row(fy: str, revenue: float, **lines) -> dict:
    """Build a synthetic annual_financials row. Unset lines default to None."""
    base = {
        "fiscal_year_end": fy, "revenue": revenue,
        "employee_cost": None, "other_income": None, "depreciation": None,
        "interest": None, "raw_material_cost": None, "power_and_fuel": None,
        "other_mfr_exp": None, "selling_and_admin": None,
        "other_expenses_detail": None, "total_expenses": None,
        "operating_profit": None, "reserves": None, "borrowings": None,
        "other_liabilities": None, "investments": None,
    }
    base.update(lines)
    return base


def test_hdfcbank_fy26_other_expenses_caught_at_medium():
    """The headline HDFCBANK FY26 reclass: 290% jump on other_expenses_detail
    while revenue grew 3.6% — should land at MEDIUM (200-500% band)."""
    rows = {"HDFCBANK": [
        _row("2025-03-31", 336367.43, other_expenses_detail=43674.55),
        _row("2026-03-31", 348615.15, other_expenses_detail=170225.32),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert len(flags) == 1
    f = flags[0]
    assert f.symbol == "HDFCBANK"
    assert f.line == "other_expenses_detail"
    assert f.severity == "MEDIUM"
    assert f.flag_type == "RECLASS"
    assert 280 < f.jump_pct < 300


def test_infy_fy26_caught_at_high():
    """+3129% jump should land HIGH (>500%)."""
    rows = {"INFY": [
        _row("2025-03-31", 162990.0, other_expenses_detail=1130.0),
        _row("2026-03-31", 178650.0, other_expenses_detail=36486.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert any(f.severity == "HIGH" and f.line == "other_expenses_detail" for f in flags)


def test_sign_flip_is_high_unconditionally():
    """Both sides material, polarity reverses — HIGH regardless of jump magnitude."""
    rows = {"X": [
        _row("2024-03-31", 1000.0, other_expenses_detail=50.0),
        _row("2025-03-31", 1000.0, other_expenses_detail=-60.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    sf = [f for f in flags if f.flag_type == "SIGN_FLIP"]
    assert len(sf) == 1
    assert sf[0].severity == "HIGH"


def test_revenue_growth_above_threshold_blocks_flag():
    """If revenue grew >30% the line jump may be real growth, not reclass."""
    rows = {"X": [
        _row("2024-03-31", 100.0, other_expenses_detail=10.0),
        _row("2025-03-31", 200.0, other_expenses_detail=50.0),  # +400% but rev +100%
    ]}
    assert detect(rows, threshold_revenue=0.30, min_severity="LOW") == []


def test_immaterial_line_skipped():
    """Line < 1% of revenue on both sides is skipped even with huge jump."""
    rev = 100000.0
    floor = rev * MIN_LINE_TO_REVENUE  # 1000
    rows = {"X": [
        _row("2024-03-31", rev, employee_cost=floor * 0.5),       # 500
        _row("2025-03-31", rev, employee_cost=floor * 0.5 * 10),  # 5000 — but still < floor
    ]}
    # Both values < 1% of revenue (500 and 5000 vs 100000 → 0.5% and 5%).
    # max(500, 5000)=5000 = 5% > 1% → should NOT be skipped. Verify it fires.
    flags = detect(rows, min_severity="LOW")
    assert len(flags) >= 1

    # Now both genuinely below 1%
    rows2 = {"Y": [
        _row("2024-03-31", rev, employee_cost=200.0),   # 0.2%
        _row("2025-03-31", rev, employee_cost=900.0),   # 0.9%
    ]}
    assert detect(rows2, min_severity="LOW") == []


def test_severity_thresholds():
    """LOW = 100-200%, MEDIUM = 200-500%, HIGH = >500%."""
    rev = 1000.0
    base = 100.0
    cases = [
        (base * (1 + JUMP_LOW * 0.5), None),      # +50% — below LOW
        (base * (1 + JUMP_LOW + 0.1), "LOW"),     # ~+110%
        (base * (1 + JUMP_MEDIUM + 0.1), "MEDIUM"),
        (base * (1 + JUMP_HIGH + 0.1), "HIGH"),
    ]
    for curr, expected in cases:
        rows = {"X": [
            _row("2024-03-31", rev, employee_cost=base),
            _row("2025-03-31", rev, employee_cost=curr),
        ]}
        flags = detect(rows, min_severity="LOW")
        if expected is None:
            assert flags == []
        else:
            assert len(flags) == 1
            assert flags[0].severity == expected


def test_min_severity_filter():
    """min_severity='HIGH' excludes MEDIUM and LOW flags."""
    rows = {"X": [
        _row("2024-03-31", 1000.0, employee_cost=100.0),
        _row("2025-03-31", 1000.0, employee_cost=350.0),  # +250% MEDIUM
    ]}
    assert len(detect(rows, min_severity="LOW")) == 1
    assert len(detect(rows, min_severity="MEDIUM")) == 1
    assert detect(rows, min_severity="HIGH") == []


def test_single_year_history_not_flagged():
    """Symbols with one row produce no flags (no pair to compare)."""
    rows = {"X": [_row("2025-03-31", 1000.0, employee_cost=100.0)]}
    assert detect(rows, min_severity="LOW") == []


def test_null_values_skipped():
    """If either side of a line is None, the line is skipped (not all flags)."""
    rows = {"X": [
        _row("2024-03-31", 1000.0, employee_cost=None, borrowings=100.0),
        _row("2025-03-31", 1000.0, employee_cost=500.0, borrowings=400.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert all(f.line != "employee_cost" for f in flags)
    assert any(f.line == "borrowings" for f in flags)


def test_flag_dataclass_shape():
    """Flag exposes the fields downstream callers expect."""
    f = Flag("X", "2024-03-31", "2025-03-31", "borrowings",
             100.0, 500.0, 400.0, 5.0, "RECLASS", "MEDIUM")
    assert f.symbol == "X"
    assert f.severity == "MEDIUM"
    assert f.flag_type == "RECLASS"
