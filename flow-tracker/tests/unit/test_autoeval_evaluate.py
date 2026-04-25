"""Tests for pure helpers in flowtracker/research/autoeval/evaluate.py.

Covers only logic that does NOT require Gemini API calls or subprocess
execution:

- GRADE_MAP completeness
- Dataclass construction (EvalIssue, ParameterGrade, AgentEvalResult, LastRunResult)
- load_matrix() — yaml matrix loader
- _extract_json() — JSON extraction with markdown-fence fallbacks
- read_report() — path resolution and missing-file handling
- read_agent_evidence() — returns "" when no traces/evidence
- append_results_tsv() — TSV round-trip (header + row shape)
- write_last_run() — writes last_run.json + archive
- append_fix_tracker() — noop when tracker file missing

NOTE: evaluate.py is IMMUTABLE per its module docstring. These tests must
never force a change to the module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# google-genai is under the [autoeval] extra, but the top-level import of
# evaluate.py does not pull it in (it is imported lazily inside
# eval_with_gemini). Keep this guard for safety in case that changes.
pytest.importorskip("yaml", reason="pyyaml required for autoeval evaluate")

from flowtracker.research.autoeval import evaluate as ev  # noqa: E402


# ---------------------------------------------------------------------------
# GRADE_MAP
# ---------------------------------------------------------------------------


class TestGradeMap:
    """GRADE_MAP covers every grade A+ through F with int numeric values."""

    def test_all_grades_present(self):
        expected = {
            "A+", "A", "A-",
            "B+", "B", "B-",
            "C+", "C", "C-",
            "D+", "D", "D-",
            "F",
        }
        assert set(ev.GRADE_MAP.keys()) == expected

    def test_all_values_are_ints(self):
        assert all(isinstance(v, int) for v in ev.GRADE_MAP.values())

    def test_grade_ordering_monotonic(self):
        """Higher letter grades map to higher numerics."""
        assert ev.GRADE_MAP["A+"] > ev.GRADE_MAP["A"] > ev.GRADE_MAP["A-"]
        assert ev.GRADE_MAP["A-"] > ev.GRADE_MAP["B+"] > ev.GRADE_MAP["B-"]
        assert ev.GRADE_MAP["B-"] > ev.GRADE_MAP["C+"] > ev.GRADE_MAP["C-"]
        assert ev.GRADE_MAP["C-"] > ev.GRADE_MAP["D+"] > ev.GRADE_MAP["D-"]
        assert ev.GRADE_MAP["D-"] > ev.GRADE_MAP["F"]

    def test_specific_anchor_values(self):
        """Rubric-critical anchor values — see EVAL_SYSTEM_TEMPLATE."""
        assert ev.GRADE_MAP["A+"] == 97
        assert ev.GRADE_MAP["A-"] == 90  # target grade
        assert ev.GRADE_MAP["B"] == 83
        assert ev.GRADE_MAP["F"] == 50


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Construction of evaluate.py dataclasses with required/optional fields."""

    def test_eval_issue_all_required(self):
        issue = ev.EvalIssue(
            type="PROMPT_FIX",
            section="Analytical Depth",
            issue="Missing NIM analysis",
            suggestion="Add NIM trend chart",
        )
        assert issue.type == "PROMPT_FIX"
        assert issue.section == "Analytical Depth"
        assert issue.issue == "Missing NIM analysis"
        assert issue.suggestion == "Add NIM trend chart"

    def test_parameter_grade_construction(self):
        pg = ev.ParameterGrade(grade="A-", numeric=90, rationale="Solid coverage")
        assert pg.grade == "A-"
        assert pg.numeric == 90
        assert pg.rationale == "Solid coverage"

    def test_agent_eval_result_required_only(self):
        """Optional fields default to empty collections / zero / empty string."""
        result = ev.AgentEvalResult(
            agent="business",
            stock="SBIN",
            sector="PSU bank",
            grade="B+",
            grade_numeric=87,
        )
        assert result.parameters == {}
        assert result.issues == []
        assert result.strengths == []
        assert result.summary == ""
        assert result.report_length == 0
        assert result.run_duration_s == 0.0
        assert result.eval_duration_s == 0.0
        assert result.run_skipped is False
        assert result.raw_gemini_response == ""

    def test_agent_eval_result_with_optionals(self):
        issue = ev.EvalIssue(type="DATA_FIX", section="x", issue="y", suggestion="z")
        pg = ev.ParameterGrade(grade="B", numeric=83, rationale="ok")
        result = ev.AgentEvalResult(
            agent="ownership",
            stock="HDFCBANK",
            sector="Private bank",
            grade="A-",
            grade_numeric=90,
            parameters={"analytical_depth": pg},
            issues=[issue],
            strengths=["Strong FII breakdown"],
            summary="Good report overall.",
            report_length=12_000,
            run_duration_s=123.4,
            eval_duration_s=15.0,
            run_skipped=False,
        )
        assert result.parameters["analytical_depth"].numeric == 83
        assert len(result.issues) == 1
        assert result.issues[0].type == "DATA_FIX"
        assert result.strengths == ["Strong FII breakdown"]
        assert result.run_duration_s == 123.4

    def test_last_run_result_defaults(self):
        lr = ev.LastRunResult(sector="bfsi", stock="SBIN", timestamp="2026-04-15T00:00:00Z")
        assert lr.results == {}
        assert lr.all_passing is False
        assert lr.failing_agents == []


# ---------------------------------------------------------------------------
# load_matrix
# ---------------------------------------------------------------------------


class TestLoadMatrix:
    """load_matrix reads eval_matrix.yaml from the autoeval package dir."""

    def test_returns_dict_with_expected_keys(self):
        matrix = ev.load_matrix()
        assert isinstance(matrix, dict)
        assert "sectors" in matrix
        assert "agents" in matrix
        assert "target_grade_numeric" in matrix

    def test_sectors_contain_bfsi_with_stock(self):
        matrix = ev.load_matrix()
        assert "bfsi" in matrix["sectors"]
        assert matrix["sectors"]["bfsi"]["stock"] == "SBIN"
        assert "type" in matrix["sectors"]["bfsi"]

    def test_target_grade_numeric_is_int(self):
        matrix = ev.load_matrix()
        assert isinstance(matrix["target_grade_numeric"], int)
        assert matrix["target_grade_numeric"] == 90


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    """_extract_json handles raw JSON, fenced code blocks, and brace fallback."""

    def test_direct_parse(self):
        result = ev._extract_json('{"grade": "A-", "numeric": 90}')
        assert result == {"grade": "A-", "numeric": 90}

    def test_markdown_fence_with_json_tag(self):
        text = '```json\n{"foo": "bar"}\n```'
        assert ev._extract_json(text) == {"foo": "bar"}

    def test_markdown_fence_no_tag(self):
        text = '```\n{"foo": 1}\n```'
        assert ev._extract_json(text) == {"foo": 1}

    def test_fence_with_surrounding_prose(self):
        text = 'Here is the result:\n```json\n{"grade": "B", "issues": []}\n```\nDone.'
        assert ev._extract_json(text) == {"grade": "B", "issues": []}

    def test_brace_fallback(self):
        """No fences, but a JSON object is embedded in prose."""
        text = 'analysis... {"grade": "A", "ok": true} trailing text'
        result = ev._extract_json(text)
        assert result == {"grade": "A", "ok": True}

    def test_returns_none_on_unparseable(self):
        assert ev._extract_json("no json here at all") is None

    def test_returns_none_on_empty(self):
        assert ev._extract_json("") is None

    def test_nested_object_via_brace_fallback(self):
        text = 'noise {"outer": {"inner": 42}} more noise'
        result = ev._extract_json(text)
        # The regex is greedy on `.*` so it captures the full brace span.
        assert result == {"outer": {"inner": 42}}


# ---------------------------------------------------------------------------
# read_report
# ---------------------------------------------------------------------------


class TestReadReport:
    """read_report resolves ~/vault/stocks/{stock}/reports/{agent}.md."""

    def test_missing_report_returns_empty_string(self, tmp_path, monkeypatch):
        """Point HOME at an empty tmp dir so the report cannot exist."""
        monkeypatch.setenv("HOME", str(tmp_path))
        # Path.home() resolves from $HOME on POSIX
        assert ev.read_report("business", "NONEXIST_STOCK") == ""

    def test_reads_existing_report(self, tmp_path, monkeypatch):
        """Plant a fake report under the expected vault path."""
        monkeypatch.setenv("HOME", str(tmp_path))
        stock = "TESTCO"
        agent = "business"
        reports_dir = tmp_path / "vault" / "stocks" / stock / "reports"
        reports_dir.mkdir(parents=True)
        report_path = reports_dir / f"{agent}.md"
        report_path.write_text("# Business Report\n\nContent here.")

        content = ev.read_report(agent, stock)
        assert content == "# Business Report\n\nContent here."


# ---------------------------------------------------------------------------
# read_agent_evidence
# ---------------------------------------------------------------------------


class TestReadAgentEvidence:
    """read_agent_evidence returns "" when no traces/evidence exist."""

    def test_no_evidence_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert ev.read_agent_evidence("business", "NOSTOCK") == ""

    def test_loads_legacy_evidence(self, tmp_path, monkeypatch):
        """When only legacy evidence JSON exists (no traces), fall back to it."""
        monkeypatch.setenv("HOME", str(tmp_path))
        stock = "TESTCO"
        agent = "business"
        evidence_dir = tmp_path / "vault" / "stocks" / stock / "evidence"
        evidence_dir.mkdir(parents=True)
        evidence = [
            {"tool": "get_fundamentals", "args": {}, "is_error": False, "result_summary": "ok"},
            {"tool": "get_price_history", "args": {}, "is_error": True, "result_summary": "timeout"},
        ]
        (evidence_dir / f"{agent}.json").write_text(json.dumps(evidence))

        out = ev.read_agent_evidence(agent, stock)
        assert out.startswith("## Agent Execution Log")
        assert "Tools called (2 total)" in out
        assert "get_fundamentals" in out
        assert "Tool errors (1)" in out
        assert "timeout" in out

    def test_loads_pipeline_trace(self, tmp_path, monkeypatch):
        """Prefer pipeline trace over legacy evidence when available."""
        monkeypatch.setenv("HOME", str(tmp_path))
        stock = "TESTCO"
        agent = "business"
        traces_dir = tmp_path / "vault" / "stocks" / stock / "traces"
        traces_dir.mkdir(parents=True)
        pipeline = {
            "agents": {
                agent: {
                    "tools_available": ["get_fundamentals", "get_price_history", "get_news"],
                    "tool_calls": [
                        {"tool": "get_fundamentals", "args": {}, "is_error": False},
                    ],
                    "cost": {
                        "total_cost_usd": 0.42,
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "model": "claude-sonnet",
                    },
                    "duration_seconds": 12.3,
                    "status": "success",
                }
            }
        }
        (traces_dir / "20260414T100000.json").write_text(json.dumps(pipeline))

        out = ev.read_agent_evidence(agent, stock)
        assert "## Agent Execution Log" in out
        assert "Tools available (3)" in out
        assert "Tools NEVER called" in out
        assert "get_price_history" in out
        assert "get_news" in out
        assert "Cost: $0.42" in out


# ---------------------------------------------------------------------------
# append_results_tsv
# ---------------------------------------------------------------------------


class TestAppendResultsTsv:
    """append_results_tsv writes header on first call, data rows on subsequent."""

    def test_creates_header_on_first_write(self, tmp_path, monkeypatch):
        """Point the module Path(__file__).parent at tmp_path for this test."""
        # append_results_tsv uses Path(__file__).parent -- we can't easily patch
        # that, so instead patch the Path class used inside the function via
        # monkeypatching the module-level Path attribute to point at tmp.
        # Simpler: monkeypatch the resolved tsv path by patching Path construction.
        # Cleanest: patch the module's Path to a subclass whose __file__-style
        # parent resolves to tmp_path. Instead we directly set results.tsv at
        # evaluate.__file__.parent using a fresh empty path, then restore.
        #
        # Use a monkeypatch on Path(__file__).parent by patching the function's
        # internal Path call via a wrapper.
        real_path_cls = ev.Path
        tsv_target = tmp_path / "results.tsv"

        def fake_path(arg=None, *a, **kw):
            # Redirect only calls that build "<autoeval_dir>/results.tsv"
            p = real_path_cls(arg, *a, **kw) if arg is not None else real_path_cls()
            return p

        # Easier route: monkeypatch Path(__file__).parent via __file__ attribute.
        # The function does Path(__file__).parent / "results.tsv".
        # Redirect __file__ of the evaluate module to a file inside tmp_path.
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        result = ev.AgentEvalResult(
            agent="business", stock="SBIN", sector="PSU bank",
            grade="B+", grade_numeric=87,
            summary="Decent report",
        )
        ev.append_results_tsv({"business": result}, sector="bfsi", cycle=1)

        written = tsv_target.read_text()
        lines = written.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("timestamp\tcycle\tagent\tstock\tsector\tgrade\tgrade_numeric")
        data = lines[1].split("\t")
        # indices per header: 0=ts 1=cycle 2=agent 3=stock 4=sector 5=grade 6=num
        assert data[1] == "1"
        assert data[2] == "business"
        assert data[3] == "SBIN"
        assert data[4] == "bfsi"
        assert data[5] == "B+"
        assert data[6] == "87"

    def test_appends_without_rewriting_header(self, tmp_path, monkeypatch):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))
        tsv_target = tmp_path / "results.tsv"

        r1 = ev.AgentEvalResult(agent="a1", stock="S1", sector="t", grade="A", grade_numeric=93)
        r2 = ev.AgentEvalResult(agent="a2", stock="S1", sector="t", grade="B", grade_numeric=83)
        ev.append_results_tsv({"a1": r1}, sector="x", cycle=0)
        ev.append_results_tsv({"a2": r2}, sector="x", cycle=0)

        lines = tsv_target.read_text().strip().split("\n")
        # 1 header + 2 data rows
        assert len(lines) == 3
        # header appears only once
        assert sum(1 for l in lines if l.startswith("timestamp\t")) == 1

    def test_prompt_fixes_counted(self, tmp_path, monkeypatch):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))
        tsv_target = tmp_path / "results.tsv"

        issues = [
            ev.EvalIssue(type="PROMPT_FIX", section="s", issue="i", suggestion="x"),
            ev.EvalIssue(type="PROMPT_FIX", section="s", issue="i2", suggestion="x2"),
            ev.EvalIssue(type="DATA_FIX", section="s", issue="i3", suggestion="x3"),
        ]
        r = ev.AgentEvalResult(
            agent="business", stock="SBIN", sector="t",
            grade="B", grade_numeric=83, issues=issues,
        )
        ev.append_results_tsv({"business": r}, sector="bfsi", cycle=2)

        lines = tsv_target.read_text().strip().split("\n")
        data = lines[1].split("\t")
        # prompt_fixes column is index 10
        assert data[10] == "2"


# ---------------------------------------------------------------------------
# write_last_run
# ---------------------------------------------------------------------------


class TestWriteLastRun:
    """write_last_run writes last_run.json AND a timestamped archive copy."""

    def test_writes_both_files(self, tmp_path, monkeypatch):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        result = ev.AgentEvalResult(
            agent="business", stock="SBIN", sector="PSU bank",
            grade="A-", grade_numeric=90,
        )
        last_run = ev.LastRunResult(
            sector="bfsi",
            stock="SBIN",
            timestamp="2026-04-15T00:00:00Z",
            results={"business": result},
            all_passing=True,
            failing_agents=[],
        )
        ev.write_last_run(last_run)

        last_path = tmp_path / "last_run.json"
        assert last_path.exists()
        payload = json.loads(last_path.read_text())
        assert payload["sector"] == "bfsi"
        assert payload["stock"] == "SBIN"
        assert payload["all_passing"] is True
        assert payload["results"]["business"]["grade"] == "A-"
        assert payload["results"]["business"]["grade_numeric"] == 90

        history_dir = tmp_path / "eval_history"
        assert history_dir.exists() and history_dir.is_dir()
        archives = list(history_dir.glob("*_bfsi.json"))
        assert len(archives) == 1
        archive_payload = json.loads(archives[0].read_text())
        assert archive_payload == payload  # archive identical to last_run.json

    def test_sector_slash_sanitized(self, tmp_path, monkeypatch):
        """A sector like 'all_for_business' stays intact; '/' is replaced with '_'."""
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        last_run = ev.LastRunResult(
            sector="bfsi/psu",
            stock="SBIN",
            timestamp="2026-04-15T00:00:00Z",
            all_passing=False,
            failing_agents=["business"],
        )
        ev.write_last_run(last_run)

        archives = list((tmp_path / "eval_history").glob("*.json"))
        assert len(archives) == 1
        # No literal "/" in the archive filename
        assert "/" not in archives[0].name
        assert "bfsi_psu" in archives[0].name


# ---------------------------------------------------------------------------
# append_fix_tracker
# ---------------------------------------------------------------------------


class TestAppendFixTracker:
    """append_fix_tracker is a noop when fix_tracker.md is missing, but
    appends rows otherwise."""

    def test_noop_when_tracker_missing(self, tmp_path, monkeypatch):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        # No fix_tracker.md in tmp_path — function should return silently.
        issue = ev.EvalIssue(type="PROMPT_FIX", section="s", issue="i", suggestion="x")
        r = ev.AgentEvalResult(
            agent="a", stock="S", sector="t",
            grade="B", grade_numeric=83, issues=[issue],
        )
        ev.append_fix_tracker({"a": r}, sector="bfsi", cycle=0)

        # Nothing created
        assert not (tmp_path / "fix_tracker.md").exists()

    def test_appends_issues_when_tracker_exists(self, tmp_path, monkeypatch, capsys):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        tracker = tmp_path / "fix_tracker.md"
        tracker.write_text(
            "| ID | Agent | Sector | Stock | Cycle | Type | Section | Issue | Suggestion | Status | Owner | Notes |\n"
            "| -- | ----- | ------ | ----- | ----- | ---- | ------- | ----- | ---------- | ------ | ----- | ----- |\n"
        )
        issues = [
            ev.EvalIssue(type="PROMPT_FIX", section="depth", issue="miss", suggestion="add"),
            ev.EvalIssue(type="DATA_FIX", section="data", issue="empty", suggestion="fix"),
        ]
        r = ev.AgentEvalResult(
            agent="business", stock="SBIN", sector="PSU bank",
            grade="B", grade_numeric=83, issues=issues,
        )
        ev.append_fix_tracker({"business": r}, sector="bfsi", cycle=1)

        content = tracker.read_text()
        assert "PROMPT_FIX" in content
        assert "DATA_FIX" in content
        # Two new rows appended
        new_rows = [
            line for line in content.splitlines()
            if line.startswith("| ") and "SBIN" in line
        ]
        assert len(new_rows) == 2

    def test_escapes_pipes_in_text(self, tmp_path, monkeypatch):
        fake_module_file = tmp_path / "evaluate.py"
        fake_module_file.write_text("# placeholder")
        monkeypatch.setattr(ev, "__file__", str(fake_module_file))

        tracker = tmp_path / "fix_tracker.md"
        tracker.write_text("| ID |\n| -- |\n")

        issue = ev.EvalIssue(
            type="PROMPT_FIX",
            section="a|b",
            issue="line1\nline2 with | pipe",
            suggestion="fix | it",
        )
        r = ev.AgentEvalResult(
            agent="a", stock="S", sector="t",
            grade="B", grade_numeric=83, issues=[issue],
        )
        ev.append_fix_tracker({"a": r}, sector="bfsi", cycle=0)

        content = tracker.read_text()
        # Pipes in text fields are replaced by "/"; newlines by space
        assert "a/b" in content
        assert "line1 line2 with / pipe" in content
        assert "fix / it" in content


# ---------------------------------------------------------------------------
# Sector-KPI pre-run guard (PR-11)
# ---------------------------------------------------------------------------


class TestSectorKpisSkipGuard:
    """_eval_sector skips agents that depend on sector_kpis when no extracted
    KPIs are available for the symbol. Unrelated agents run normally.

    Exercises _agent_uses_sector_kpis + _sector_kpis_populated by patching the
    latter at the module boundary so we don't need a live DB or concall cache.
    """

    @pytest.fixture
    def _no_run_agent(self, monkeypatch):
        """Stub run_agent so a failed pre-guard doesn't shell out to flowtrack."""
        calls = {"count": 0}

        def fake_run(agent, stock):
            calls["count"] += 1
            return 0.1, True

        monkeypatch.setattr(ev, "run_agent", fake_run)
        return calls

    def test_skips_agent_when_sector_kpis_missing(self, monkeypatch, capsys, _no_run_agent):
        """sector agent uses sector_kpis → SKIP with SKIP_MISSING_KPIS marker."""
        monkeypatch.setattr(ev, "_sector_kpis_populated", lambda _sym: False)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="sector", sector_name="bfsi",
            sector_cfg={"stock": "SUNPHARMA", "type": "Pharma"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade == "SKIP"
        assert "SKIP_MISSING_KPIS" in result.summary
        assert "SUNPHARMA" in result.summary
        assert "backfill_sector_kpis.py" in result.summary
        assert _no_run_agent["count"] == 0, "agent must NOT be invoked when skipped"
        err = capsys.readouterr().err
        assert "SKIP: sector_kpis missing for SUNPHARMA" in err

    def test_runs_agent_when_sector_kpis_present(self, monkeypatch, _no_run_agent):
        """KPIs populated → agent runs normally (no SKIP)."""
        monkeypatch.setattr(ev, "_sector_kpis_populated", lambda _sym: True)
        monkeypatch.setattr(ev, "read_report", lambda _a, _s: "# Report\n\nbody")
        monkeypatch.setattr(ev, "read_agent_evidence", lambda _a, _s: "")

        async def fake_eval(agent, stock, sector_type, report_md, evidence=""):
            return ev.AgentEvalResult(
                agent=agent, stock=stock, sector=sector_type,
                grade="A-", grade_numeric=90,
            )

        monkeypatch.setattr(ev, "eval_with_gemini", fake_eval)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="sector", sector_name="bfsi",
            sector_cfg={"stock": "SBIN", "type": "PSU bank"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade == "A-"
        assert _no_run_agent["count"] == 1

    def test_does_not_skip_unrelated_agent(self, monkeypatch, _no_run_agent):
        """ownership agent never touches sector_kpis → runs even when KPIs absent."""
        monkeypatch.setattr(ev, "_sector_kpis_populated", lambda _sym: False)
        monkeypatch.setattr(ev, "read_report", lambda _a, _s: "# Report\n\nbody")
        monkeypatch.setattr(ev, "read_agent_evidence", lambda _a, _s: "")

        async def fake_eval(agent, stock, sector_type, report_md, evidence=""):
            return ev.AgentEvalResult(
                agent=agent, stock=stock, sector=sector_type,
                grade="B+", grade_numeric=87,
            )

        monkeypatch.setattr(ev, "eval_with_gemini", fake_eval)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="ownership", sector_name="bfsi",
            sector_cfg={"stock": "SBIN", "type": "PSU bank"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade != "SKIP"
        assert _no_run_agent["count"] == 1

    def test_agent_uses_sector_kpis_classifier(self):
        """Direct coverage of the prompt-inspection helper."""
        # sector + financials reference sector_kpis in their V2 prompts
        assert ev._agent_uses_sector_kpis("sector") is True
        assert ev._agent_uses_sector_kpis("financials") is True
        # ownership/valuation/risk/technical do not
        assert ev._agent_uses_sector_kpis("ownership") is False
        assert ev._agent_uses_sector_kpis("valuation") is False
        assert ev._agent_uses_sector_kpis("risk") is False
        # unknown agent → False (defensive)
        assert ev._agent_uses_sector_kpis("nonexistent_agent_xyz") is False


class TestFnoPositioningEligibilityGuard:
    """_eval_sector skips fno_positioning for symbols outside the NSE F&O
    eligibility universe. Other agents are unaffected."""

    @pytest.fixture
    def _no_run_agent(self, monkeypatch):
        """Stub run_agent so a failed pre-guard doesn't shell out to flowtrack."""
        calls = {"count": 0}

        def fake_run(agent, stock):
            calls["count"] += 1
            return 0.1, True

        monkeypatch.setattr(ev, "run_agent", fake_run)
        return calls

    def test_skips_fno_positioning_when_not_eligible(self, monkeypatch, capsys, _no_run_agent):
        """fno_positioning + non-eligible stock → SKIP with SKIP_NOT_FNO_ELIGIBLE marker."""
        monkeypatch.setattr(ev, "_fno_eligible", lambda _sym: False)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="fno_positioning", sector_name="bfsi",
            sector_cfg={"stock": "TINPLATE", "type": "Steel/SME"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade == "SKIP"
        assert "SKIP_NOT_FNO_ELIGIBLE" in result.summary
        assert "TINPLATE" in result.summary
        assert "fno universe refresh" in result.summary
        assert _no_run_agent["count"] == 0, "agent must NOT be invoked when skipped"
        err = capsys.readouterr().err
        assert "SKIP: TINPLATE not in NSE F&O eligibility universe" in err

    def test_runs_fno_positioning_when_eligible(self, monkeypatch, _no_run_agent):
        """fno_positioning + eligible stock → agent runs (no SKIP)."""
        monkeypatch.setattr(ev, "_fno_eligible", lambda _sym: True)
        monkeypatch.setattr(ev, "_sector_kpis_populated", lambda _sym: True)
        monkeypatch.setattr(ev, "read_report", lambda _a, _s: "# Report\n\nbody")
        monkeypatch.setattr(ev, "read_agent_evidence", lambda _a, _s: "")

        async def fake_eval(agent, stock, sector_type, report_md, evidence=""):
            return ev.AgentEvalResult(
                agent=agent, stock=stock, sector=sector_type,
                grade="A-", grade_numeric=90,
            )

        monkeypatch.setattr(ev, "eval_with_gemini", fake_eval)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="fno_positioning", sector_name="bfsi",
            sector_cfg={"stock": "RELIANCE", "type": "Conglomerate"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade == "A-"
        assert _no_run_agent["count"] == 1

    def test_does_not_skip_other_agents_when_not_fno_eligible(self, monkeypatch, _no_run_agent):
        """ownership agent on a non-F&O stock → runs normally; eligibility guard
        is scoped to fno_positioning only."""
        monkeypatch.setattr(ev, "_fno_eligible", lambda _sym: False)
        monkeypatch.setattr(ev, "_sector_kpis_populated", lambda _sym: True)
        monkeypatch.setattr(ev, "read_report", lambda _a, _s: "# Report\n\nbody")
        monkeypatch.setattr(ev, "read_agent_evidence", lambda _a, _s: "")

        async def fake_eval(agent, stock, sector_type, report_md, evidence=""):
            return ev.AgentEvalResult(
                agent=agent, stock=stock, sector=sector_type,
                grade="B+", grade_numeric=87,
            )

        monkeypatch.setattr(ev, "eval_with_gemini", fake_eval)
        import asyncio
        result = asyncio.run(ev._eval_sector(
            agent="ownership", sector_name="auto",
            sector_cfg={"stock": "TINPLATE", "type": "Steel/SME"},
            target_numeric=90, skip_run=False, cycle=0,
        ))
        assert result.grade != "SKIP"
        assert _no_run_agent["count"] == 1

    def test_fno_eligible_helper_failure_soft(self, monkeypatch):
        """If FlowStore raises (DB missing, table missing), helper returns False
        so the SKIP path engages instead of crashing the whole run."""
        class _BoomStore:
            def __enter__(self): raise RuntimeError("simulated DB boom")
            def __exit__(self, *a): return False

        monkeypatch.setattr("flowtracker.store.FlowStore", lambda *a, **k: _BoomStore())
        assert ev._fno_eligible("RELIANCE") is False
