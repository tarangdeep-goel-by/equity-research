"""Tests for flowtracker.research.autoeval.progress.

Covers:
- Module constants (GRADE_ORDER, TARGET, TARGET_NUMERIC)
- load_results: missing file, empty file, valid TSV, malformed row
- grade_matrix: header/row printing, pass/fail markers, empty rows
- sector_timeline: specified sector, missing sector
- experiment_chart: pass / fail / error symbols, sorting
- main: no results path, full render, --sector flag
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from flowtracker.research.autoeval import progress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


TSV_HEADER = (
    "timestamp\tcycle\tagent\tstock\tsector\tgrade\tgrade_numeric"
    "\treport_len\trun_s\teval_s\tprompt_fixes\tnotes\n"
)


def _make_row(
    *,
    timestamp: str = "2026-04-07T06:44:37Z",
    cycle: str = "1",
    agent: str = "business",
    stock: str = "SBIN",
    sector: str = "bfsi",
    grade: str = "B+",
    grade_numeric: str = "85",
    report_len: str = "30000",
    run_s: str = "0.0",
    eval_s: str = "0.2",
    prompt_fixes: str = "0",
    notes: str = "ok",
) -> str:
    """Build a TSV row matching the real results.tsv schema."""
    return "\t".join([
        timestamp, cycle, agent, stock, sector, grade, grade_numeric,
        report_len, run_s, eval_s, prompt_fixes, notes,
    ]) + "\n"


def _write_results(tmp_path: Path, rows: list[str]) -> Path:
    """Write a fake results.tsv under tmp_path and return its path."""
    tsv_path = tmp_path / "results.tsv"
    tsv_path.write_text(TSV_HEADER + "".join(rows))
    return tsv_path


def _point_progress_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect progress.load_results() to look under tmp_path.

    load_results() computes `Path(__file__).parent / "results.tsv"`, so
    overriding the module's __file__ pins the lookup to tmp_path.
    """
    monkeypatch.setattr(progress, "__file__", str(tmp_path / "progress.py"))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Sanity checks on module-level constants."""

    def test_grade_order_contains_target(self):
        assert progress.TARGET in progress.GRADE_ORDER

    def test_grade_order_has_err_sentinel(self):
        assert "ERR" in progress.GRADE_ORDER

    def test_grade_order_descending(self):
        """A+ should rank before F, F before ERR."""
        assert progress.GRADE_ORDER.index("A+") < progress.GRADE_ORDER.index("F")
        assert progress.GRADE_ORDER.index("F") < progress.GRADE_ORDER.index("ERR")

    def test_target_numeric_is_int(self):
        assert isinstance(progress.TARGET_NUMERIC, int)
        assert progress.TARGET_NUMERIC == 90


# ---------------------------------------------------------------------------
# load_results
# ---------------------------------------------------------------------------


class TestLoadResults:
    """load_results() — CSV ingestion."""

    def test_missing_file_returns_empty_list(self, tmp_path, monkeypatch):
        _point_progress_at(tmp_path, monkeypatch)
        # No results.tsv written.
        assert progress.load_results() == []

    def test_header_only_returns_empty_list(self, tmp_path, monkeypatch):
        _write_results(tmp_path, [])
        _point_progress_at(tmp_path, monkeypatch)
        assert progress.load_results() == []

    def test_valid_tsv_parsed_into_dicts(self, tmp_path, monkeypatch):
        _write_results(tmp_path, [
            _make_row(agent="business", sector="bfsi", grade="A-", grade_numeric="90"),
            _make_row(agent="thesis", sector="it_services", grade="B", grade_numeric="80"),
        ])
        _point_progress_at(tmp_path, monkeypatch)

        rows = progress.load_results()
        assert len(rows) == 2
        assert rows[0]["agent"] == "business"
        assert rows[0]["sector"] == "bfsi"
        assert rows[0]["grade"] == "A-"
        assert rows[1]["agent"] == "thesis"

    def test_row_exposes_all_header_columns(self, tmp_path, monkeypatch):
        _write_results(tmp_path, [_make_row()])
        _point_progress_at(tmp_path, monkeypatch)

        rows = progress.load_results()
        assert set(rows[0].keys()) >= {
            "timestamp", "cycle", "agent", "stock", "sector",
            "grade", "grade_numeric", "prompt_fixes", "notes",
        }


# ---------------------------------------------------------------------------
# grade_matrix
# ---------------------------------------------------------------------------


class TestGradeMatrix:
    """grade_matrix() — sector x agent latest-grade printer."""

    def test_empty_rows_prints_placeholder(self, capsys):
        progress.grade_matrix([])
        out = capsys.readouterr().out
        assert "No results yet." in out

    def test_prints_sector_and_agent_headers(self, capsys):
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-", "grade_numeric": "90"},
            {"sector": "it_services", "agent": "thesis", "grade": "B", "grade_numeric": "80"},
        ]
        progress.grade_matrix(rows)
        out = capsys.readouterr().out
        assert "sector" in out
        assert "bfsi" in out
        assert "it_services" in out
        assert "business" in out
        assert "thesis" in out

    def test_passing_cell_has_no_marker(self, capsys):
        """grade_numeric >= TARGET_NUMERIC → no '*' suffix."""
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-", "grade_numeric": "90"},
        ]
        progress.grade_matrix(rows)
        out = capsys.readouterr().out
        assert "A-" in out
        # The grade cell should not contain the failing '*' marker.
        assert "A-*" not in out

    def test_failing_cell_has_star_marker(self, capsys):
        """grade_numeric < TARGET_NUMERIC → '*' suffix on the grade."""
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "B+", "grade_numeric": "85"},
        ]
        progress.grade_matrix(rows)
        out = capsys.readouterr().out
        assert "B+*" in out

    def test_latest_grade_wins(self, capsys):
        """When the same (sector, agent) appears twice, last row's grade shows."""
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "C", "grade_numeric": "70"},
            {"sector": "bfsi", "agent": "business", "grade": "A-", "grade_numeric": "90"},
        ]
        progress.grade_matrix(rows)
        out = capsys.readouterr().out
        # Latest grade (A-) should show with passing marker (no '*').
        assert "A-" in out

    def test_summary_line_counts_passing(self, capsys):
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-", "grade_numeric": "90"},
            {"sector": "it_services", "agent": "thesis", "grade": "B+", "grade_numeric": "85"},
        ]
        progress.grade_matrix(rows)
        out = capsys.readouterr().out
        assert "1/2 cells passing" in out
        assert progress.TARGET in out


# ---------------------------------------------------------------------------
# sector_timeline
# ---------------------------------------------------------------------------


class TestSectorTimeline:
    """sector_timeline() — per-sector experiment history."""

    def test_unknown_sector_prints_not_found(self, capsys):
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-",
             "grade_numeric": "90", "cycle": "1", "prompt_fixes": "0", "notes": ""},
        ]
        progress.sector_timeline(rows, "platform")
        out = capsys.readouterr().out
        assert "No results for sector 'platform'" in out

    def test_known_sector_renders_rows(self, capsys):
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-",
             "grade_numeric": "90", "cycle": "1", "prompt_fixes": "2",
             "notes": "prompt tightened"},
            {"sector": "bfsi", "agent": "thesis", "grade": "B+",
             "grade_numeric": "85", "cycle": "2", "prompt_fixes": "1",
             "notes": "needs work"},
            {"sector": "it_services", "agent": "business", "grade": "A",
             "grade_numeric": "92", "cycle": "1", "prompt_fixes": "0", "notes": ""},
        ]
        progress.sector_timeline(rows, "bfsi")
        out = capsys.readouterr().out

        assert "Timeline: bfsi" in out
        assert "cycle" in out
        assert "prompt_fixes" in out
        # Both bfsi rows present.
        assert "business" in out
        assert "thesis" in out
        # Non-matching sector excluded.
        assert "it_services" not in out

    def test_notes_truncated_to_50_chars(self, capsys):
        long_note = "x" * 200
        rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-",
             "grade_numeric": "90", "cycle": "1", "prompt_fixes": "0",
             "notes": long_note},
        ]
        progress.sector_timeline(rows, "bfsi")
        out = capsys.readouterr().out
        # Only the first 50 characters should appear as one contiguous run.
        assert "x" * 50 in out
        assert "x" * 51 not in out

    def test_missing_optional_fields_fall_back_to_question_mark(self, capsys):
        """Rows missing cycle/agent/etc use '?' placeholder via .get default."""
        rows = [{"sector": "bfsi"}]  # agent, grade, etc. absent
        progress.sector_timeline(rows, "bfsi")
        out = capsys.readouterr().out
        assert "?" in out


# ---------------------------------------------------------------------------
# experiment_chart
# ---------------------------------------------------------------------------


class TestExperimentChart:
    """experiment_chart() — compact pass/fail/error timeline per sector."""

    def test_legend_printed(self, capsys):
        progress.experiment_chart([])
        out = capsys.readouterr().out
        assert "Experiment History" in out
        assert "#" in out and "." in out and "x" in out

    def test_pass_symbol_hash(self, capsys):
        rows = [
            {"sector": "bfsi", "grade_numeric": "95"},
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        # bfsi row should render with '#'
        assert "bfsi" in out
        bfsi_line = [ln for ln in out.splitlines() if "bfsi" in ln][0]
        assert "#" in bfsi_line

    def test_fail_symbol_dot(self, capsys):
        rows = [
            {"sector": "bfsi", "grade_numeric": "70"},
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        bfsi_line = [ln for ln in out.splitlines() if "bfsi" in ln][0]
        assert "." in bfsi_line

    def test_error_symbol_x(self, capsys):
        """grade_numeric == 0 → 'x'."""
        rows = [
            {"sector": "bfsi", "grade_numeric": "0"},
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        bfsi_line = [ln for ln in out.splitlines() if "bfsi" in ln][0]
        assert "x" in bfsi_line

    def test_invalid_numeric_treated_as_error(self, capsys):
        """Non-int grade_numeric → 'x' (via ValueError path)."""
        rows = [
            {"sector": "bfsi", "grade_numeric": "bogus"},
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        bfsi_line = [ln for ln in out.splitlines() if "bfsi" in ln][0]
        assert "x" in bfsi_line

    def test_sectors_sorted_alphabetically(self, capsys):
        rows = [
            {"sector": "platform", "grade_numeric": "95"},
            {"sector": "bfsi", "grade_numeric": "95"},
            {"sector": "it_services", "grade_numeric": "95"},
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        # Find order of first appearance of each sector name.
        bfsi_pos = out.index("bfsi")
        it_pos = out.index("it_services")
        platform_pos = out.index("platform")
        assert bfsi_pos < it_pos < platform_pos

    def test_multiple_runs_aggregate_into_timeline(self, capsys):
        rows = [
            {"sector": "bfsi", "grade_numeric": "95"},  # #
            {"sector": "bfsi", "grade_numeric": "70"},  # .
            {"sector": "bfsi", "grade_numeric": "0"},   # x
        ]
        progress.experiment_chart(rows)
        out = capsys.readouterr().out
        bfsi_line = [ln for ln in out.splitlines() if "bfsi" in ln][0]
        assert "#.x" in bfsi_line


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """main() — argparse entry point."""

    def test_no_results_prints_hint(self, tmp_path, monkeypatch, capsys):
        _point_progress_at(tmp_path, monkeypatch)
        monkeypatch.setattr(sys, "argv", ["progress.py"])
        progress.main()
        out = capsys.readouterr().out
        assert "No results.tsv found" in out

    def test_renders_full_summary(self, monkeypatch, capsys):
        fake_rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-",
             "grade_numeric": "90", "cycle": "1", "prompt_fixes": "0", "notes": ""},
        ]
        monkeypatch.setattr(progress, "load_results", lambda: fake_rows)
        monkeypatch.setattr(sys, "argv", ["progress.py"])

        progress.main()
        out = capsys.readouterr().out
        # grade_matrix output.
        assert "bfsi" in out
        assert "business" in out
        # experiment_chart output.
        assert "Experiment History" in out
        # No sector timeline requested → no "Timeline:" header.
        assert "Timeline:" not in out

    def test_sector_flag_triggers_timeline(self, monkeypatch, capsys):
        fake_rows = [
            {"sector": "bfsi", "agent": "business", "grade": "A-",
             "grade_numeric": "90", "cycle": "1", "prompt_fixes": "0", "notes": ""},
        ]
        monkeypatch.setattr(progress, "load_results", lambda: fake_rows)
        monkeypatch.setattr(sys, "argv", ["progress.py", "--sector", "bfsi"])

        progress.main()
        out = capsys.readouterr().out
        assert "Timeline: bfsi" in out


# ---------------------------------------------------------------------------
# Macro block
# ---------------------------------------------------------------------------


MACRO_TSV_HEADER = (
    "timestamp\tnote\tas_of_date\tgrade\tgrade_numeric"
    "\tprompt_fixes\tissues\tsummary\n"
)


def _make_macro_row(
    *,
    timestamp: str = "2026-04-22T10:00:00Z",
    note: str = "baseline",
    as_of_date: str = "2025-11-01",
    grade: str = "A-",
    grade_numeric: str = "90",
    prompt_fixes: str = "0",
    issues: str = "1",
    summary: str = "Solid regime read",
) -> str:
    return "\t".join([
        timestamp, note, as_of_date, grade, grade_numeric,
        prompt_fixes, issues, summary,
    ]) + "\n"


def _write_macro_results(tmp_path: Path, rows: list[str]) -> Path:
    tsv_path = tmp_path / "results_macro.tsv"
    tsv_path.write_text(MACRO_TSV_HEADER + "".join(rows))
    return tsv_path


class TestMacroBlock:
    """macro_block() and load_macro_results() — Part 3 PR-A2 additions."""

    def test_load_macro_results_missing_returns_empty(self, tmp_path, monkeypatch):
        _point_progress_at(tmp_path, monkeypatch)
        assert progress.load_macro_results() == []

    def test_load_macro_results_parses_tsv(self, tmp_path, monkeypatch):
        _write_macro_results(tmp_path, [
            _make_macro_row(as_of_date="2025-11-01", grade="A-", grade_numeric="90"),
            _make_macro_row(as_of_date="2025-12-15", grade="A", grade_numeric="93"),
        ])
        _point_progress_at(tmp_path, monkeypatch)
        rows = progress.load_macro_results()
        assert len(rows) == 2
        assert rows[0]["as_of_date"] == "2025-11-01"
        assert rows[1]["grade"] == "A"

    def test_macro_block_empty_renders_nothing(self, capsys):
        progress.macro_block([])
        out = capsys.readouterr().out
        assert out == ""
        assert "Macro autoeval" not in out

    def test_macro_block_renders_rows_and_passing_count(self, capsys):
        rows = [
            {"as_of_date": "2025-11-01", "grade": "A-", "grade_numeric": "90"},
            {"as_of_date": "2025-12-15", "grade": "A", "grade_numeric": "93"},
            {"as_of_date": "2026-02-01", "grade": "B+", "grade_numeric": "85"},
        ]
        progress.macro_block(rows)
        out = capsys.readouterr().out
        assert "Macro autoeval" in out
        assert "2025-11-01" in out
        assert "2025-12-15" in out
        assert "PASS" in out
        assert "FAIL" in out
        assert "passing: 2/3" in out

    def test_macro_block_sorted_oldest_to_newest(self, capsys):
        """Rows render sorted by as_of_date so newest is at the bottom."""
        rows = [
            {"as_of_date": "2026-02-01", "grade": "A", "grade_numeric": "93"},
            {"as_of_date": "2025-11-01", "grade": "A-", "grade_numeric": "90"},
            {"as_of_date": "2025-12-15", "grade": "A", "grade_numeric": "92"},
        ]
        progress.macro_block(rows)
        out = capsys.readouterr().out
        nov_pos = out.index("2025-11-01")
        dec_pos = out.index("2025-12-15")
        feb_pos = out.index("2026-02-01")
        assert nov_pos < dec_pos < feb_pos

    def test_macro_block_respects_limit(self, capsys):
        rows = [
            {"as_of_date": f"2025-11-{i:02d}", "grade": "A", "grade_numeric": "93"}
            for i in range(1, 16)
        ]
        progress.macro_block(rows, limit=3)
        out = capsys.readouterr().out
        assert "last 3 dates" in out
        # Only the 3 most recent (2025-11-13/14/15) should appear
        assert "2025-11-15" in out
        assert "2025-11-01" not in out

    def test_macro_block_invalid_numeric_treated_as_fail(self, capsys):
        rows = [{"as_of_date": "2025-11-01", "grade": "ERR",
                 "grade_numeric": "bogus"}]
        progress.macro_block(rows)
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_main_skips_macro_block_when_tsv_absent(self, tmp_path, monkeypatch, capsys):
        """When results_macro.tsv is missing, main() emits no Macro section."""
        _write_results(tmp_path, [_make_row()])
        _point_progress_at(tmp_path, monkeypatch)
        monkeypatch.setattr(sys, "argv", ["progress.py"])
        progress.main()
        out = capsys.readouterr().out
        assert "Macro autoeval" not in out

    def test_main_renders_macro_block_when_tsv_present(self, tmp_path, monkeypatch, capsys):
        """When results_macro.tsv exists, main() appends the Macro block."""
        _write_results(tmp_path, [_make_row()])
        _write_macro_results(tmp_path, [
            _make_macro_row(as_of_date="2025-11-01", grade="A-", grade_numeric="90"),
        ])
        _point_progress_at(tmp_path, monkeypatch)
        monkeypatch.setattr(sys, "argv", ["progress.py"])
        progress.main()
        out = capsys.readouterr().out
        assert "Macro autoeval" in out
        assert "2025-11-01" in out
