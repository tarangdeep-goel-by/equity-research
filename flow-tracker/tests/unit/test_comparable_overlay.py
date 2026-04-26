"""Tests for the comparable_growth_metrics overlay annotation layer.

Strategy 3 of plans/screener-data-discontinuity.md: when a trend method
narrows its `effective_window` because a MEDIUM+ reclassification flag
falls inside the requested window, attach a `comparable_overlay`
showing management's stated like-for-like / pre-merger comparable /
constant-currency growth for the same period.

Annotation, not replacement — the headline series still comes from
Screener; the overlay is a second opinion the agent can quote
alongside.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


def _write_concall_with_overlay(
    home: Path,
    symbol: str,
    entries_by_quarter: dict[str, list[dict]],
) -> None:
    """Write a synthetic concall_extraction_v2.json under the given fake home.

    entries_by_quarter maps fy_quarter → list of comparable_growth_metrics dicts.
    """
    out_dir = home / "vault" / "stocks" / symbol.upper() / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    quarters = []
    for fq, cgm in entries_by_quarter.items():
        quarters.append(
            {
                "fy_quarter": fq,
                "label": fq,
                "extraction_status": "complete",
                "comparable_growth_metrics": cgm,
            }
        )
    payload = {
        "symbol": symbol.upper(),
        "quarters_analyzed": len(quarters),
        "quarters": quarters,
        "cross_quarter_narrative": {},
    }
    (out_dir / "concall_extraction_v2.json").write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# _load_comparable_overlay
# ---------------------------------------------------------------------------


class TestLoadComparableOverlay:
    """Helper that flattens comparable_growth_metrics across quarters."""

    def test_returns_empty_when_no_concall_file(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = api._load_comparable_overlay("NOEXIST")
        assert result == []

    def test_returns_empty_when_no_comparable_metrics(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {"FY26-Q3": [], "FY26-Q2": []},
        )
        assert api._load_comparable_overlay("TEST") == []

    def test_flattens_across_quarters_with_annotations(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {
                "FY26-Q3": [
                    {
                        "metric": "opex",
                        "value": "8%",
                        "comparable_basis": "like-for-like ex-merger",
                        "period": "FY26 vs FY25",
                        "context": "On a like-for-like basis, opex grew 8% YoY.",
                        "speaker": "CFO",
                    }
                ],
                "FY26-Q2": [
                    {
                        "metric": "revenue",
                        "value": "12%",
                        "comparable_basis": "constant currency",
                        "period": "Q2 YoY",
                        "context": "Core revenue growth was 12% on constant currency.",
                        "speaker": "CEO",
                    }
                ],
            },
        )
        result = api._load_comparable_overlay("TEST")
        assert len(result) == 2
        # Source annotation present on every entry
        for entry in result:
            assert entry["data_source_for_comparable"] == "concall_management_commentary"
            assert "fy_quarter" in entry
        # Quarter labels propagated
        fqs = sorted(e["fy_quarter"] for e in result)
        assert fqs == ["FY26-Q2", "FY26-Q3"]
        # Original fields preserved
        opex = next(e for e in result if e["metric"] == "opex")
        assert opex["value"] == "8%"
        assert opex["comparable_basis"] == "like-for-like ex-merger"

    def test_handles_corrupt_json_gracefully(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        out = tmp_path / "vault" / "stocks" / "TEST" / "fundamentals"
        out.mkdir(parents=True)
        (out / "concall_extraction_v2.json").write_text("not json {{{")
        assert api._load_comparable_overlay("TEST") == []

    def test_skips_non_dict_entries(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        """Defensive: skip non-dict garbage in the comparable_growth_metrics list."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {
                "FY26-Q3": [
                    "garbage string",
                    None,
                    {"metric": "opex", "value": "8%", "comparable_basis": "like-for-like"},
                ],
            },
        )
        result = api._load_comparable_overlay("TEST")
        assert len(result) == 1
        assert result[0]["metric"] == "opex"


# ---------------------------------------------------------------------------
# _attach_comparable_overlay — annotation behavior
# ---------------------------------------------------------------------------


class TestAttachComparableOverlay:
    """Overlay attaches only when (a) effective_window narrowed AND (b) overlay non-empty."""

    def test_no_overlay_when_window_not_narrowed(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {"FY26-Q3": [{"metric": "opex", "value": "8%", "comparable_basis": "lfl"}]},
        )
        payload = {
            "source": "screener",
            "years": [{"fiscal_year_end": "2026-03-31"}],
            "effective_window": {"narrowed_due_to": []},
        }
        result = api._attach_comparable_overlay(payload, "TEST")
        assert "comparable_overlay" not in result

    def test_no_overlay_when_window_missing(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {"FY26-Q3": [{"metric": "opex", "value": "8%", "comparable_basis": "lfl"}]},
        )
        payload = {"source": "screener", "years": []}
        result = api._attach_comparable_overlay(payload, "TEST")
        assert "comparable_overlay" not in result

    def test_no_overlay_when_concall_has_no_metrics(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(tmp_path, "TEST", {"FY26-Q3": []})
        payload = {
            "effective_window": {
                "narrowed_due_to": [
                    {"prior_fy": "2025-03-31", "curr_fy": "2026-03-31",
                     "line": "other_expenses_detail", "severity": "MEDIUM"}
                ]
            }
        }
        result = api._attach_comparable_overlay(payload, "TEST")
        assert "comparable_overlay" not in result

    def test_overlay_attached_when_window_narrowed_and_overlay_present(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {
                "FY26-Q3": [
                    {
                        "metric": "opex",
                        "value": "8%",
                        "comparable_basis": "like-for-like ex-merger",
                        "period": "FY26 vs FY25",
                        "context": "On a like-for-like basis, opex grew 8% YoY.",
                        "speaker": "CFO",
                    }
                ]
            },
        )
        payload = {
            "source": "screener",
            "effective_window": {
                "narrowed_due_to": [
                    {"prior_fy": "2025-03-31", "curr_fy": "2026-03-31",
                     "line": "other_expenses_detail", "severity": "MEDIUM"}
                ]
            },
        }
        result = api._attach_comparable_overlay(payload, "TEST")
        assert "comparable_overlay" in result
        overlay = result["comparable_overlay"]
        assert overlay["source"] == "concall_management_commentary"
        assert "purpose" in overlay
        # Annotation language clear about it not replacing primary
        assert "second opinion" in overlay["purpose"].lower()
        assert "do not replace" in overlay["purpose"].lower() or "do not" in overlay["purpose"].lower()
        assert len(overlay["entries"]) == 1
        entry = overlay["entries"][0]
        assert entry["metric"] == "opex"
        assert entry["fy_quarter"] == "FY26-Q3"
        assert entry["data_source_for_comparable"] == "concall_management_commentary"

    def test_overlay_does_not_replace_primary_series(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        """The headline `years` / `cagrs` / etc. payload survives untouched."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {"FY26-Q3": [{"metric": "opex", "value": "8%", "comparable_basis": "lfl"}]},
        )
        payload = {
            "source": "screener",
            "years": [{"fiscal_year_end": "2026-03-31", "roe_dupont": 0.18}],
            "effective_window": {
                "narrowed_due_to": [
                    {"prior_fy": "2025-03-31", "curr_fy": "2026-03-31",
                     "line": "other_expenses_detail", "severity": "MEDIUM"}
                ]
            },
        }
        result = api._attach_comparable_overlay(payload, "TEST")
        # Primary series untouched
        assert result["source"] == "screener"
        assert result["years"][0]["roe_dupont"] == 0.18
        # Overlay added alongside
        assert "comparable_overlay" in result


# ---------------------------------------------------------------------------
# Integration: trend methods call the overlay attacher
# ---------------------------------------------------------------------------


def _seed_annual_with_reclass_break(store: FlowStore, symbol: str) -> None:
    """Seed annual_financials so a reclass jump on `other_expenses_detail`
    triggers the data_quality detector. Five years; the FY26 row jumps
    `other_expenses_detail` by >100% with revenue stable, mimicking a
    Schedule III re-bucketing."""
    rows = [
        # most-recent first ordering not enforced; we insert chronologically
        {
            "fiscal_year_end": "2022-03-31", "revenue": 1000.0, "operating_profit": 200.0,
            "depreciation": 30.0, "interest": 20.0, "tax": 50.0, "net_income": 100.0,
            "eps": 10.0, "cfo": 110.0, "total_assets": 2000.0,
            "equity_capital": 100.0, "reserves": 800.0, "borrowings": 500.0,
            "raw_material_cost": 500.0, "employee_cost": 100.0,
            "other_expenses_detail": 70.0, "num_shares": 10.0,
        },
        {
            "fiscal_year_end": "2023-03-31", "revenue": 1100.0, "operating_profit": 220.0,
            "depreciation": 30.0, "interest": 20.0, "tax": 60.0, "net_income": 110.0,
            "eps": 11.0, "cfo": 120.0, "total_assets": 2200.0,
            "equity_capital": 100.0, "reserves": 900.0, "borrowings": 520.0,
            "raw_material_cost": 540.0, "employee_cost": 110.0,
            "other_expenses_detail": 75.0, "num_shares": 10.0,
        },
        {
            "fiscal_year_end": "2024-03-31", "revenue": 1200.0, "operating_profit": 240.0,
            "depreciation": 30.0, "interest": 20.0, "tax": 65.0, "net_income": 120.0,
            "eps": 12.0, "cfo": 130.0, "total_assets": 2400.0,
            "equity_capital": 100.0, "reserves": 1000.0, "borrowings": 540.0,
            "raw_material_cost": 580.0, "employee_cost": 120.0,
            "other_expenses_detail": 80.0, "num_shares": 10.0,
        },
        {
            "fiscal_year_end": "2025-03-31", "revenue": 1300.0, "operating_profit": 260.0,
            "depreciation": 30.0, "interest": 20.0, "tax": 70.0, "net_income": 130.0,
            "eps": 13.0, "cfo": 140.0, "total_assets": 2600.0,
            "equity_capital": 100.0, "reserves": 1100.0, "borrowings": 560.0,
            "raw_material_cost": 620.0, "employee_cost": 130.0,
            "other_expenses_detail": 85.0, "num_shares": 10.0,
        },
        {
            # Reclass break on FY26: other_expenses_detail jumps 4× while revenue stable.
            "fiscal_year_end": "2026-03-31", "revenue": 1380.0, "operating_profit": 270.0,
            "depreciation": 30.0, "interest": 20.0, "tax": 75.0, "net_income": 140.0,
            "eps": 14.0, "cfo": 145.0, "total_assets": 2750.0,
            "equity_capital": 100.0, "reserves": 1200.0, "borrowings": 580.0,
            "raw_material_cost": 650.0, "employee_cost": 140.0,
            "other_expenses_detail": 340.0, "num_shares": 10.0,  # 85 → 340 = +300%
        },
    ]
    for r in rows:
        store._conn.execute(
            "INSERT INTO annual_financials (symbol, fiscal_year_end, revenue, "
            "operating_profit, depreciation, interest, tax, net_income, eps, cfo, "
            "total_assets, equity_capital, reserves, borrowings, raw_material_cost, "
            "employee_cost, other_expenses_detail, num_shares) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol, r["fiscal_year_end"], r["revenue"], r["operating_profit"],
                r["depreciation"], r["interest"], r["tax"], r["net_income"], r["eps"],
                r["cfo"], r["total_assets"], r["equity_capital"], r["reserves"],
                r["borrowings"], r["raw_material_cost"], r["employee_cost"],
                r["other_expenses_detail"], r["num_shares"],
            ),
        )
    store._conn.commit()


class TestTrendMethodAnnotation:
    """End-to-end: trend method called on a symbol with both a reclass flag
    and a concall comparable overlay → comparable_overlay annotates the result."""

    @staticmethod
    def _populate_quality_flags(store: FlowStore, symbol: str) -> None:
        """Run the detector on the seeded annual rows and persist the flags."""
        from flowtracker.data_quality import detect, fetch_rows
        rows_by = fetch_rows(store._conn, symbols=[symbol])
        flags = detect(rows_by, min_severity="MEDIUM")
        if flags:
            store.upsert_data_quality_flags(flags)

    def test_dupont_attaches_overlay_when_reclass_narrows(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _seed_annual_with_reclass_break(api._store, "TEST")
        self._populate_quality_flags(api._store, "TEST")

        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {
                "FY26-Q4": [
                    {
                        "metric": "opex",
                        "value": "8%",
                        "comparable_basis": "ex-Schedule-III re-bucketing",
                        "period": "FY26 vs FY25",
                        "context": "On a like-for-like basis, opex grew 8% YoY (vs reported 300%).",
                        "speaker": "CFO",
                    }
                ]
            },
        )

        # Sanity: the seeded row really did produce a MEDIUM+ flag.
        flags = api._store.get_data_quality_flags("TEST", min_severity="MEDIUM")
        assert flags, "expected at least one MEDIUM+ flag for the seeded reclass"

        result = api.get_dupont_decomposition("TEST")
        # Reclass detected → narrowed_due_to populated → overlay attached
        assert "effective_window" in result
        narrowed = result["effective_window"].get("narrowed_due_to")
        assert narrowed, "expected the FY26 reclass to narrow the dupont window"
        assert "comparable_overlay" in result
        assert result["comparable_overlay"]["source"] == "concall_management_commentary"
        assert len(result["comparable_overlay"]["entries"]) == 1
        assert result["comparable_overlay"]["entries"][0]["fy_quarter"] == "FY26-Q4"

    def test_common_size_pl_attaches_overlay_when_reclass_narrows(
        self, api: ResearchDataAPI, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _seed_annual_with_reclass_break(api._store, "TEST")
        self._populate_quality_flags(api._store, "TEST")

        _write_concall_with_overlay(
            tmp_path,
            "TEST",
            {
                "FY26-Q4": [
                    {
                        "metric": "operating_margin",
                        "value": "stable",
                        "comparable_basis": "like-for-like",
                        "period": "FY26",
                        "context": "Underlying margin held flat ex re-bucketing.",
                        "speaker": "CFO",
                    }
                ]
            },
        )

        result = api.get_common_size_pl("TEST")
        narrowed = result.get("effective_window", {}).get("narrowed_due_to")
        assert narrowed, "expected the FY26 reclass to narrow the common-size window"
        assert "comparable_overlay" in result
        assert result["comparable_overlay"]["entries"][0]["metric"] == "operating_margin"
