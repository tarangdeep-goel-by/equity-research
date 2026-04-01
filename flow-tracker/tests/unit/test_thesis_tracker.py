"""Tests for the thesis tracker (research/thesis_tracker.py).

Tests YAML loading/parsing, condition evaluation against store data,
comparison operators, and file update/rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flowtracker.research.thesis_tracker import (
    ThesisCondition,
    ThesisTracker,
    _compare,
    _resolve_metric,
    evaluate_conditions,
    load_tracker,
    update_tracker_file,
)
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_YAML = """\
---
symbol: SBIN
entry_price: 750.0
entry_date: "2025-06-15"
conditions:
  - metric: quarterly_results.revenue
    operator: ">"
    threshold: 40000
    label: "Revenue above 40K Cr"
    status: pending
  - metric: valuation_snapshot.pe_trailing
    operator: "<"
    threshold: 5.0
    label: "PE below 5"
    status: pending
---
Thesis body here.
"""

_MINIMAL_YAML = """\
---
symbol: TESTCO
conditions: []
---
"""

_NO_FRONTMATTER = "Just plain text, no YAML."

_INVALID_YAML = """\
---
symbol: SBIN
conditions:
  - metric: valuation_snapshot.pe_trailing
    operator: [invalid
---
"""


def _write_tracker(tmp_path: Path, symbol: str, content: str) -> Path:
    """Write a thesis-tracker.md file and return its path."""
    d = tmp_path / symbol.upper()
    d.mkdir(parents=True, exist_ok=True)
    p = d / "thesis-tracker.md"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# _compare — pure operator tests
# ---------------------------------------------------------------------------

class TestCompare:
    def test_greater_than(self):
        assert _compare(10.0, ">", 5.0) is True
        assert _compare(5.0, ">", 10.0) is False

    def test_less_than(self):
        assert _compare(3.0, "<", 5.0) is True
        assert _compare(5.0, "<", 3.0) is False

    def test_greater_equal(self):
        assert _compare(5.0, ">=", 5.0) is True
        assert _compare(5.1, ">=", 5.0) is True
        assert _compare(4.9, ">=", 5.0) is False

    def test_less_equal(self):
        assert _compare(5.0, "<=", 5.0) is True
        assert _compare(4.9, "<=", 5.0) is True
        assert _compare(5.1, "<=", 5.0) is False

    def test_equal(self):
        assert _compare(5.0, "==", 5.0) is True
        assert _compare(5.0005, "==", 5.0) is True  # within 0.001 tolerance
        assert _compare(5.01, "==", 5.0) is False

    def test_unknown_operator(self):
        assert _compare(5.0, "!=", 5.0) is False


# ---------------------------------------------------------------------------
# load_tracker — file parsing
# ---------------------------------------------------------------------------

class TestLoadTracker:
    def test_load_valid_tracker(self, tmp_path: Path, monkeypatch):
        _write_tracker(tmp_path, "SBIN", _SAMPLE_YAML)
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)

        tracker = load_tracker("SBIN")
        assert tracker is not None
        assert tracker.symbol == "SBIN"
        assert tracker.entry_price == 750.0
        assert tracker.entry_date == "2025-06-15"
        assert len(tracker.conditions) == 2
        assert tracker.conditions[0].metric == "quarterly_results.revenue"
        assert tracker.conditions[0].operator == ">"
        assert tracker.conditions[0].threshold == 40000.0

    def test_load_minimal_tracker(self, tmp_path: Path, monkeypatch):
        _write_tracker(tmp_path, "TESTCO", _MINIMAL_YAML)
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)

        tracker = load_tracker("TESTCO")
        assert tracker is not None
        assert tracker.symbol == "TESTCO"
        assert tracker.conditions == []

    def test_load_missing_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)
        assert load_tracker("NONEXIST") is None

    def test_load_no_frontmatter(self, tmp_path: Path, monkeypatch):
        _write_tracker(tmp_path, "BADFMT", _NO_FRONTMATTER)
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)
        assert load_tracker("BADFMT") is None

    def test_load_invalid_yaml(self, tmp_path: Path, monkeypatch):
        _write_tracker(tmp_path, "BADYAML", _INVALID_YAML)
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)
        assert load_tracker("BADYAML") is None

    def test_load_case_insensitive_symbol(self, tmp_path: Path, monkeypatch):
        _write_tracker(tmp_path, "SBIN", _SAMPLE_YAML)
        monkeypatch.setattr("flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path)
        # load_tracker uppercases the symbol
        tracker = load_tracker("sbin")
        assert tracker is not None
        assert tracker.symbol == "SBIN"


# ---------------------------------------------------------------------------
# _resolve_metric — reads store
# ---------------------------------------------------------------------------

class TestResolveMetric:
    def test_valuation_pe_trailing(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "SBIN", "valuation_snapshot.pe_trailing")
        assert val is not None
        assert 5 < val < 15  # SBIN PE fixture range

    def test_valuation_price(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "SBIN", "valuation_snapshot.price")
        assert val is not None
        assert 700 < val < 900

    def test_shareholding_category(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "SBIN", "shareholding.fii")
        assert val is not None
        assert 8 < val < 15  # ~11.2%

    def test_quarterly_results_field(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "SBIN", "quarterly_results.operating_margin")
        assert val is not None

    def test_nonexistent_symbol(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "NONEXIST", "valuation_snapshot.price")
        assert val is None

    def test_unknown_table(self, populated_store: FlowStore):
        val = _resolve_metric(populated_store, "SBIN", "nonexistent_table.field")
        assert val is None


# ---------------------------------------------------------------------------
# evaluate_conditions
# ---------------------------------------------------------------------------

class TestEvaluateConditions:
    def test_passing_condition(self, populated_store: FlowStore):
        """PE ~9.5, threshold < 15 → should pass."""
        tracker = ThesisTracker(
            symbol="SBIN",
            conditions=[
                ThesisCondition(
                    metric="valuation_snapshot.pe_trailing",
                    operator="<",
                    threshold=15.0,
                    label="PE below 15",
                ),
            ],
        )
        results = evaluate_conditions(tracker, populated_store)
        assert len(results) == 1
        assert results[0].status == "passing"

    def test_failing_condition(self, populated_store: FlowStore):
        """PE ~9.5, threshold < 5 → should fail."""
        tracker = ThesisTracker(
            symbol="SBIN",
            conditions=[
                ThesisCondition(
                    metric="valuation_snapshot.pe_trailing",
                    operator="<",
                    threshold=5.0,
                    label="PE below 5",
                ),
            ],
        )
        results = evaluate_conditions(tracker, populated_store)
        assert len(results) == 1
        assert results[0].status == "failing"

    def test_stale_when_no_data(self, populated_store: FlowStore):
        """Metric resolves to None → stale."""
        tracker = ThesisTracker(
            symbol="NONEXIST",
            conditions=[
                ThesisCondition(
                    metric="valuation_snapshot.price",
                    operator=">",
                    threshold=100.0,
                    label="Has a price",
                ),
            ],
        )
        results = evaluate_conditions(tracker, populated_store)
        assert len(results) == 1
        assert results[0].status == "stale"

    def test_multiple_conditions_mixed(self, populated_store: FlowStore):
        """Mix of passing, failing conditions."""
        tracker = ThesisTracker(
            symbol="SBIN",
            conditions=[
                ThesisCondition(
                    metric="valuation_snapshot.pe_trailing",
                    operator="<",
                    threshold=15.0,
                    label="PE below 15",
                ),
                ThesisCondition(
                    metric="valuation_snapshot.pe_trailing",
                    operator="<",
                    threshold=5.0,
                    label="PE below 5",
                ),
            ],
        )
        results = evaluate_conditions(tracker, populated_store)
        statuses = {r.label: r.status for r in results}
        assert statuses["PE below 15"] == "passing"
        assert statuses["PE below 5"] == "failing"


# ---------------------------------------------------------------------------
# update_tracker_file
# ---------------------------------------------------------------------------

class TestUpdateTrackerFile:
    def test_writes_updated_yaml(self, tmp_path: Path):
        path = tmp_path / "SBIN" / "thesis-tracker.md"
        path.parent.mkdir(parents=True)
        path.write_text(_SAMPLE_YAML)

        tracker = ThesisTracker(
            symbol="SBIN",
            entry_price=750.0,
            entry_date="2025-06-15",
            conditions=[
                ThesisCondition(
                    metric="quarterly_results.revenue",
                    operator=">",
                    threshold=40000,
                    label="Revenue above 40K Cr",
                    status="passing",
                ),
                ThesisCondition(
                    metric="valuation_snapshot.pe_trailing",
                    operator="<",
                    threshold=5.0,
                    label="PE below 5",
                    status="failing",
                ),
            ],
            file_path=path,
        )

        update_tracker_file(tracker)

        # Read back and verify
        text = path.read_text()
        assert text.startswith("---\n")
        parts = text.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert meta["symbol"] == "SBIN"
        assert meta["entry_price"] == 750.0
        assert len(meta["conditions"]) == 2
        assert meta["conditions"][0]["status"] == "passing"
        assert meta["conditions"][1]["status"] == "failing"

    def test_no_file_path_does_nothing(self):
        tracker = ThesisTracker(symbol="SBIN", file_path=None)
        # Should not raise
        update_tracker_file(tracker)
