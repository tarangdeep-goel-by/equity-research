"""Unit tests for the discontinuity detector library."""
from __future__ import annotations

from flowtracker.data_quality import (
    BS_LINES,
    JUMP_HIGH,
    JUMP_LOW,
    JUMP_MEDIUM,
    MIN_LINE_TO_DENOMINATOR,
    PL_LINES,
    Flag,
    detect,
)


def _row(fy: str, revenue: float, total_assets: float | None = None, **lines) -> dict:
    """Build a synthetic annual_financials row. Unset lines default to None."""
    base = {
        "fiscal_year_end": fy, "revenue": revenue,
        "total_assets": total_assets if total_assets is not None else revenue * 2,
        "employee_cost": None, "other_income": None, "depreciation": None,
        "interest": None, "raw_material_cost": None, "power_and_fuel": None,
        "other_mfr_exp": None, "selling_and_admin": None,
        "other_expenses_detail": None, "total_expenses": None,
        "operating_profit": None, "reserves": None, "borrowings": None,
        "other_liabilities": None, "investments": None,
    }
    base.update(lines)
    return base


# ---------------------------------------------------------- Headline cases

def test_hdfcbank_fy26_other_expenses_caught_at_medium():
    """+290% jump on other_expenses_detail with revenue +3.6% — MEDIUM band."""
    rows = {"HDFCBANK": [
        _row("2025-03-31", 336367.43, other_expenses_detail=43674.55),
        _row("2026-03-31", 348615.15, other_expenses_detail=170225.32),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert len(flags) == 1
    f = flags[0]
    assert f.line == "other_expenses_detail"
    assert f.severity == "MEDIUM"
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
    rows = {"X": [
        _row("2024-03-31", 1000.0, other_expenses_detail=50.0),
        _row("2025-03-31", 1000.0, other_expenses_detail=-60.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    sf = [f for f in flags if f.flag_type == "SIGN_FLIP"]
    assert len(sf) == 1
    assert sf[0].severity == "HIGH"


# ---------------------------------------------------------- P&L revenue control

def test_pl_revenue_control_blocks_flag():
    """P&L line jump suppressed when revenue swung > threshold (real growth)."""
    rows = {"X": [
        _row("2024-03-31", 100.0, employee_cost=10.0),
        _row("2025-03-31", 200.0, employee_cost=50.0),  # +400% but rev +100%
    ]}
    assert detect(rows, threshold_revenue=0.30, min_severity="LOW") == []


def test_bs_revenue_control_does_NOT_block(monkeypatch):
    """BS line jumps must NOT be suppressed by revenue swings — M&A drives both
    revenue jump and BS reshuffle, so revenue gate would mask real reclasses.
    Gemini review fix #4."""
    rows = {"X": [
        # Revenue doubles AND borrowings 5x — should still flag the BS jump.
        _row("2024-03-31", 100.0, total_assets=500.0, borrowings=20.0),
        _row("2025-03-31", 200.0, total_assets=600.0, borrowings=120.0),
    ]}
    flags = detect(rows, threshold_revenue=0.30, min_severity="LOW")
    assert any(f.line == "borrowings" for f in flags)


def test_bs_uses_total_assets_for_materiality():
    """BS items measured vs total_assets, not revenue. Bank-like ratios where
    borrowings >> revenue must still pass materiality.
    Gemini review fix #4 — denominator mismatch.

    Both sides under 1% of total_assets must skip even with huge jumps.
    """
    rows = {"X": [
        # Revenue 100 Cr, total_assets 100,000 Cr. Borrowings 50 / 500 Cr —
        # both <1% of total_assets, so skipped despite 900% jump.
        _row("2024-03-31", 100.0, total_assets=100000.0, borrowings=50.0),
        _row("2025-03-31", 100.0, total_assets=100000.0, borrowings=500.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert all(f.line != "borrowings" for f in flags)

    # If we used revenue (100 Cr) as denominator, borrowings would be 50%/500% —
    # easily passing materiality. Confirm BS items are NOT using revenue.
    # Sanity: a meaningful BS jump (5% of total_assets) does fire.
    rows2 = {"Y": [
        _row("2024-03-31", 100.0, total_assets=100000.0, borrowings=2000.0),
        _row("2025-03-31", 100.0, total_assets=100000.0, borrowings=10000.0),
    ]}
    flags2 = detect(rows2, min_severity="LOW")
    assert any(f.line == "borrowings" for f in flags2)


# ---------------------------------------------------------- Materiality / noise

def test_immaterial_line_skipped():
    """Line < 1% of denominator on both sides is skipped even with huge jump."""
    rev = 100000.0
    rows = {"Y": [
        _row("2024-03-31", rev, employee_cost=200.0),   # 0.2% of revenue
        _row("2025-03-31", rev, employee_cost=900.0),   # 0.9%
    ]}
    assert detect(rows, min_severity="LOW") == []


def test_severity_thresholds():
    rev = 1000.0
    base = 100.0
    cases = [
        (base * (1 + JUMP_LOW * 0.5), None),
        (base * (1 + JUMP_LOW + 0.1), "LOW"),
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
    rows = {"X": [
        _row("2024-03-31", 1000.0, employee_cost=100.0),
        _row("2025-03-31", 1000.0, employee_cost=350.0),  # +250% MEDIUM
    ]}
    assert len(detect(rows, min_severity="LOW")) == 1
    assert len(detect(rows, min_severity="MEDIUM")) == 1
    assert detect(rows, min_severity="HIGH") == []


def test_single_year_history_not_flagged():
    rows = {"X": [_row("2025-03-31", 1000.0, employee_cost=100.0)]}
    assert detect(rows, min_severity="LOW") == []


def test_null_values_skipped():
    rows = {"X": [
        _row("2024-03-31", 1000.0, employee_cost=None, borrowings=100.0),
        _row("2025-03-31", 1000.0, employee_cost=500.0, borrowings=400.0),
    ]}
    flags = detect(rows, min_severity="LOW")
    assert all(f.line != "employee_cost" for f in flags)
    assert any(f.line == "borrowings" for f in flags)


# ---------------------------------------------------------- Sign-flip cleanup

def test_reserves_no_longer_in_sign_flip_set():
    """reserves can legitimately flip due to accumulated deficit. Gemini fix.
    Magnitude should still flag if it crosses a threshold, but not as SIGN_FLIP."""
    from flowtracker.data_quality import SIGN_FLIP_LINES
    assert "reserves" not in SIGN_FLIP_LINES


def test_other_income_no_longer_in_sign_flip_set():
    """other_income flips on MTM swings — not always a reclass. Gemini fix."""
    from flowtracker.data_quality import SIGN_FLIP_LINES
    assert "other_income" not in SIGN_FLIP_LINES


# ---------------------------------------------------------- Group membership

def test_pl_bs_disjoint_partition():
    """TREND_LINES = PL_LINES + BS_LINES, no overlap."""
    assert set(PL_LINES) & set(BS_LINES) == set()
    # Sanity: a few key lines land in the right group
    assert "depreciation" in PL_LINES
    assert "borrowings" in BS_LINES
    assert "investments" in BS_LINES
    assert "other_expenses_detail" in PL_LINES


def test_flag_dataclass_shape():
    f = Flag("X", "2024-03-31", "2025-03-31", "borrowings",
             100.0, 500.0, 400.0, 5.0, "RECLASS", "MEDIUM")
    assert f.symbol == "X"
    assert f.severity == "MEDIUM"
    assert f.flag_type == "RECLASS"
