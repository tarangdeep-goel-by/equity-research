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


# ---------------------------------------------------------- Aggregate bridging
# Gemini review item #7: when the parent aggregate (total_expenses for P&L,
# total_assets for BS) is conserved within tolerance across a flagged
# boundary, the per-component break is a pure reshuffle. Ratio-level
# consumers (DuPont, F-score, common-size) can bridge the window.

from flowtracker.data_quality import (
    BRIDGE_TOLERANCE_BS_ABS,
    BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH,
    attach_aggregate_bridges,
    compute_aggregate_bridge,
)


def _flag_dict(line: str, prior_fy: str = "2025-03-31",
               curr_fy: str = "2026-03-31", rev_change_pct: float = 5.0,
               severity: str = "MEDIUM") -> dict:
    """Build a flag dict matching what FlowStore.get_data_quality_flags returns."""
    return {
        "symbol": "X", "prior_fy": prior_fy, "curr_fy": curr_fy,
        "line": line, "prior_val": 100.0, "curr_val": 400.0,
        "jump_pct": 300.0, "rev_change_pct": rev_change_pct,
        "flag_type": "RECLASS", "severity": severity,
    }


class TestAggregateBridgeHDFCBANK:
    """Real-number HDFCBANK FY26 fixture from
    plans/screener-data-discontinuity.md."""

    def test_hdfcbank_fy26_other_expenses_bridges(self):
        """other_expenses_detail jumps +290% (43.7K → 170.2K Cr) but
        total_expenses bridges within ~11% (186.9K → 207.8K) — well
        inside the revenue ±10pp tolerance band given revenue +3.6%."""
        prior = {
            "revenue": 336367.43, "total_expenses": 186900.0,
            "employee_cost": 34200.0, "other_expenses_detail": 43674.55,
        }
        curr = {
            "revenue": 348615.15, "total_expenses": 207800.0,
            "employee_cost": 37600.0, "other_expenses_detail": 170225.32,
        }
        flag = _flag_dict("other_expenses_detail", rev_change_pct=3.6)
        bridge = compute_aggregate_bridge(flag, prior, curr)
        assert bridge is not None
        assert bridge["parent"] == "total_expenses"
        assert bridge["conserved"] is True
        assert bridge["tolerance_used"] == BRIDGE_TOLERANCE_PL_OVER_REVENUE_GROWTH
        # parent_yoy ~11.18% — gap vs revenue +3.6% is 7.58pp (≤ 10pp).
        assert 11 < bridge["parent_yoy_pct"] < 12

    def test_hdfcbank_fy24_other_liabilities_bridges_via_bs(self):
        """HDFCBANK FY24 BS: other_liabilities can blow up post-merger
        without total_assets reshuffling materially. Bridge via
        total_assets when |TA YoY| ≤ 15%."""
        prior = {"total_assets": 2530000.0, "other_liabilities": 50000.0}
        curr = {"total_assets": 2780000.0, "other_liabilities": 229000.0}  # ~9.9% TA growth
        flag = _flag_dict("other_liabilities", rev_change_pct=5.0)
        bridge = compute_aggregate_bridge(flag, prior, curr)
        assert bridge is not None
        assert bridge["parent"] == "total_assets"
        assert bridge["conserved"] is True
        assert bridge["tolerance_used"] == BRIDGE_TOLERANCE_BS_ABS

    def test_bs_jump_above_tolerance_not_conserved(self):
        """|total_assets YoY| > 15% (e.g. M&A) → BS not bridge-able."""
        prior = {"total_assets": 1000000.0, "borrowings": 50000.0}
        curr = {"total_assets": 1300000.0, "borrowings": 200000.0}  # +30%
        flag = _flag_dict("borrowings")
        bridge = compute_aggregate_bridge(flag, prior, curr)
        assert bridge is not None
        assert bridge["conserved"] is False


class TestAggregateBridgeINFY:
    """INFY FY26 fixture — cost component blew out AND so did the parent.
    Bridging must NOT mask this — the parent itself is corrupt."""

    def test_infy_fy26_other_expenses_does_not_bridge(self):
        """other_expenses_detail +3129% → if it landed in total_expenses
        without offsetting reductions elsewhere, total_expenses also
        blows out far beyond revenue +9.6%. Bridge fails."""
        prior = {
            "revenue": 162990.0, "total_expenses": 145000.0,
            "other_expenses_detail": 1130.0,
        }
        curr = {
            "revenue": 178650.0, "total_expenses": 175000.0,
            "other_expenses_detail": 36486.0,
        }
        flag = _flag_dict("other_expenses_detail", rev_change_pct=9.6)
        bridge = compute_aggregate_bridge(flag, prior, curr)
        assert bridge is not None
        # parent_yoy ~20.7%, revenue +9.6% → gap 11.1pp > 10pp tolerance.
        assert bridge["conserved"] is False
        assert bridge["parent_yoy_pct"] > 20


class TestAggregateBridgeEdgeCases:
    def test_returns_none_when_parent_unknown(self):
        """Lines with no parent (e.g. operating_profit, other_income) →
        bridge returns None. Legacy behaviour holds."""
        flag = _flag_dict("operating_profit")
        prior = {"revenue": 100.0, "total_expenses": 80.0}
        curr = {"revenue": 110.0, "total_expenses": 90.0}
        assert compute_aggregate_bridge(flag, prior, curr) is None

    def test_returns_none_when_rows_missing(self):
        flag = _flag_dict("employee_cost")
        assert compute_aggregate_bridge(flag, None, None) is None
        assert compute_aggregate_bridge(flag, {"total_expenses": 100.0}, None) is None

    def test_returns_none_when_parent_unavailable_either_side(self):
        """Both rows lacking total_expenses AND all sub-components → no
        parent computable → bridge returns None."""
        flag = _flag_dict("employee_cost")
        prior = {"revenue": 100.0}
        curr = {"revenue": 110.0}
        assert compute_aggregate_bridge(flag, prior, curr) is None

    def test_falls_back_to_sum_when_total_expenses_missing(self):
        """When total_expenses is None on one side, sum of sub-components
        substitutes — parent is still computable."""
        flag = _flag_dict("employee_cost", rev_change_pct=5.0)
        prior = {
            "revenue": 100.0, "total_expenses": None,
            "employee_cost": 30.0, "raw_material_cost": 40.0, "depreciation": 5.0,
        }
        curr = {
            "revenue": 105.0, "total_expenses": 80.0,  # 80 vs 75 prior = +6.7%
            "employee_cost": 33.0, "raw_material_cost": 42.0, "depreciation": 5.0,
        }
        bridge = compute_aggregate_bridge(flag, prior, curr)
        assert bridge is not None
        # gap = 6.67% - 5% = 1.67% < 10% → conserved.
        assert bridge["conserved"] is True

    def test_parent_itself_flagged_short_circuits(self):
        """If `total_expenses` is itself flagged, never bridge across —
        that's a real reshuffle, not a recategorisation."""
        flag = _flag_dict("employee_cost")
        prior = {"revenue": 100.0, "total_expenses": 80.0, "employee_cost": 20.0}
        curr = {"revenue": 105.0, "total_expenses": 84.0, "employee_cost": 25.0}
        bridge = compute_aggregate_bridge(
            flag, prior, curr,
            sibling_flagged_lines={"total_expenses"},
        )
        assert bridge is not None
        assert bridge["conserved"] is False
        assert "parent" in bridge.get("reason", "")


class TestAttachAggregateBridges:
    def test_enriches_each_flag_with_bridge_field(self):
        flags = [
            _flag_dict("other_expenses_detail", rev_change_pct=3.6),
            _flag_dict("borrowings", curr_fy="2024-03-31",
                       prior_fy="2023-03-31"),
        ]
        rows_by_fy = {
            "2025-03-31": {
                "revenue": 336367.43, "total_expenses": 186900.0,
                "employee_cost": 34200.0, "other_expenses_detail": 43674.55,
            },
            "2026-03-31": {
                "revenue": 348615.15, "total_expenses": 207800.0,
                "employee_cost": 37600.0, "other_expenses_detail": 170225.32,
            },
            "2023-03-31": {"total_assets": 2300000.0, "borrowings": 100000.0},
            "2024-03-31": {"total_assets": 2530000.0, "borrowings": 250000.0},
        }
        enriched = attach_aggregate_bridges(flags, rows_by_fy)
        assert len(enriched) == 2
        for f in enriched:
            assert "aggregate_bridge" in f
            assert f["aggregate_bridge"] is not None
            assert f["aggregate_bridge"]["conserved"] is True

    def test_does_not_mutate_input(self):
        flags = [_flag_dict("employee_cost")]
        attach_aggregate_bridges(flags, {})
        assert "aggregate_bridge" not in flags[0]

    def test_sibling_parent_detection_disables_bridge(self):
        """If `total_expenses` is itself in the flag list, no P&L flag
        bridges across (any year)."""
        flags = [
            _flag_dict("total_expenses", curr_fy="2026-03-31"),
            _flag_dict("employee_cost", curr_fy="2026-03-31"),
        ]
        rows_by_fy = {
            "2025-03-31": {"revenue": 100.0, "total_expenses": 80.0,
                           "employee_cost": 30.0},
            "2026-03-31": {"revenue": 105.0, "total_expenses": 84.0,
                           "employee_cost": 35.0},
        }
        enriched = attach_aggregate_bridges(flags, rows_by_fy)
        # Both flags get an aggregate_bridge, but employee_cost's bridge
        # is conserved=False because total_expenses is sibling-flagged.
        ec_flag = next(f for f in enriched if f["line"] == "employee_cost")
        assert ec_flag["aggregate_bridge"]["conserved"] is False
