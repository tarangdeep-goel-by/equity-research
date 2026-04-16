"""Tests for `flowtracker/research_commands.py` — the `flowtrack research`
sub-typer.

Coverage strategy:
    The module mixes pure-CLI commands (data, thesis-check, thesis-status) with
    async-Claude-driven commands (business, thesis, run, autoeval) and a stub
    (verify). We exercise:
      * `data <tool>` — round-trip through ResearchDataAPI on a real populated
        store, asserting JSON output shape.
      * `data` argument validation (unknown tool, missing symbol).
      * `thesis-check` and `thesis-status` against a vault-rooted at tmp_path,
        with and without YAML tracker files.
      * `compare` — symbol count guards plus a fully mocked happy path
        (run_comparison_agent + assemble_comparison_report stubbed, browser
        suppressed) so we exercise the orchestration code without invoking the
        Claude SDK.
      * `verify` — currently a stub that only prints a placeholder.
      * `autoeval` — argument validation + `--progress` shortcut (the eval main
        function is patched).
      * `--help` smoke for the heavyweight async commands (`run`, `business`,
        `thesis`, `explain`, `fundamentals`) which we cannot fully execute
        without launching the Claude SDK / opening browsers.

UNTESTED (documented):
    * `fundamentals` — fetches via Screener/yfinance/NSE clients, renders Jinja
      templates, and shells out to `open`. Pure side-effect surface.
    * `business`, `thesis`, `explain`, `run` — wrap async multi-agent
      orchestration via `claude_agent_sdk`. Their happy paths require a live
      SDK; we only cover their `--help` text and arg-validation branches.
    * `autoeval` (eval body) — shells out via sys.argv mutation to the
      autoeval evaluate.main; we only cover the dispatch branches.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from flowtracker.main import app
from flowtracker.research.briefing import (
    AgentCost,
    AgentTrace,
    BriefingEnvelope,
)
from flowtracker.store import FlowStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(symbol: str = "SBIN") -> BriefingEnvelope:
    """Minimal envelope suitable for synthesis/comparison/explainer mocks."""
    return BriefingEnvelope(
        agent="comparison",
        symbol=symbol,
        report="# Comparison Report\n\nSBIN vs INFY summary.",
        briefing={"verdict": "neutral"},
        evidence=[],
        cost=AgentCost(total_cost_usd=0.05, duration_seconds=12.0),
    )


def _make_trace(agent: str = "comparison", symbol: str = "SBIN") -> AgentTrace:
    return AgentTrace(
        agent=agent,
        symbol=symbol,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:12+00:00",
        duration_seconds=12.0,
        cost=AgentCost(total_cost_usd=0.05, duration_seconds=12.0),
    )


_TRACKER_YAML_PASSING = """\
---
symbol: SBIN
entry_price: 750.0
entry_date: "2025-06-15"
conditions:
  - metric: quarterly_results.revenue
    operator: ">"
    threshold: 1.0
    label: "Revenue is positive"
    status: pending
  - metric: valuation_snapshot.pe_trailing
    operator: "<"
    threshold: 99999
    label: "PE below ceiling"
    status: pending
---
Body.
"""


# ---------------------------------------------------------------------------
# data — happy path on populated store
# ---------------------------------------------------------------------------


class TestDataCommand:
    def test_company_info_returns_json_with_symbol(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """`data company_info -s SBIN` round-trips through ResearchDataAPI and
        prints JSON containing the symbol key."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["research", "data", "company_info", "-s", "SBIN"])
        assert result.exit_code == 0, result.output
        assert "SBIN" in result.output
        # Output is rich-printed JSON — strip any color codes by best-effort.
        # Just assert the symbol key is present in the printed payload.
        assert "symbol" in result.output

    def test_macro_snapshot_no_symbol_required(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """`macro_snapshot` is in the no-symbol allowlist; runs with no -s."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["research", "data", "macro_snapshot"])
        assert result.exit_code == 0, result.output

    def test_raw_flag_emits_compact_json(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """--raw uses plain print() of json.dumps — no rich formatting."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(
            app, ["research", "data", "company_info", "-s", "SBIN", "--raw"]
        )
        assert result.exit_code == 0, result.output
        # The raw output should start with `{` and parse as JSON.
        # CliRunner captures stdout; rich's JSON pretty printer would produce
        # multi-line output, but plain `print` puts the dict on one line.
        line = next(
            (ln for ln in result.output.splitlines() if ln.strip().startswith("{")),
            "",
        )
        assert line, f"no JSON line in output: {result.output!r}"
        parsed = json.loads(line)
        assert parsed.get("symbol") == "SBIN"

    def test_unknown_tool_exits_one(self, tmp_db: Path, monkeypatch):
        """Unknown tool prints an error and exits 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(
            app, ["research", "data", "not_a_real_tool", "-s", "SBIN"]
        )
        assert result.exit_code == 1
        assert "Unknown tool" in result.output

    def test_missing_symbol_for_per_symbol_tool_exits_one(
        self, tmp_db: Path, monkeypatch
    ):
        """A symbol-required tool without -s exits with code 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["research", "data", "company_info"])
        assert result.exit_code == 1
        assert "symbol" in result.output.lower()

    @pytest.mark.parametrize(
        "tool",
        [
            "quarterly_results",
            "annual_financials",
            "screener_ratios",
            "shareholding",
            "valuation_snapshot",
            "fii_dii_streak",
            "fii_dii_flows",
            "composite_score",
        ],
    )
    def test_data_tool_dispatch_covers_lambda_branch(
        self,
        tool: str,
        tmp_db: Path,
        populated_store: FlowStore,
        monkeypatch,
    ):
        """Each tool-name branch in the dispatch dict is exercised at least
        once. Tools may legitimately return empty results — we only require a
        clean exit and no crash. Drives coverage of the data() lambda map."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        argv = ["research", "data", tool]
        # All but the no_symbol allowlist need -s.
        if tool not in {"macro_snapshot", "fii_dii_streak", "fii_dii_flows"}:
            argv.extend(["-s", "SBIN"])
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, f"{tool}: {result.output}"


# ---------------------------------------------------------------------------
# thesis-check — vault-backed
# ---------------------------------------------------------------------------


class TestThesisCheck:
    def test_no_tracker_file_exits_one(
        self, tmp_db: Path, populated_store: FlowStore, tmp_path: Path, monkeypatch
    ):
        """When no tracker file exists in the vault, exits 1 with a helpful
        message pointing at the expected location."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        monkeypatch.setattr(
            "flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path
        )
        result = runner.invoke(app, ["research", "thesis-check", "-s", "NOSUCH"])
        assert result.exit_code == 1
        assert "No thesis tracker" in result.output

    def test_tracker_with_conditions_renders_table(
        self, tmp_db: Path, populated_store: FlowStore, tmp_path: Path, monkeypatch
    ):
        """A valid tracker file produces a status table and exit 0."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        monkeypatch.setattr(
            "flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path
        )
        # Write a minimal tracker file for SBIN.
        d = tmp_path / "SBIN"
        d.mkdir(parents=True, exist_ok=True)
        (d / "thesis-tracker.md").write_text(_TRACKER_YAML_PASSING)

        result = runner.invoke(app, ["research", "thesis-check", "-s", "SBIN"])
        assert result.exit_code == 0, result.output
        assert "SBIN" in result.output
        # Table headers should appear.
        assert "Condition" in result.output


# ---------------------------------------------------------------------------
# thesis-status — vault-backed
# ---------------------------------------------------------------------------


class TestThesisStatus:
    def test_no_trackers_exits_one(self, tmp_path: Path, monkeypatch):
        """No tracker dirs in the vault => exit 1."""
        # The status command iterates the vault root; point it at empty tmp.
        monkeypatch.setattr(
            "flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path
        )
        result = runner.invoke(app, ["research", "thesis-status"])
        assert result.exit_code == 1
        assert "No thesis trackers" in result.output

    def test_with_tracker_renders_table(
        self, tmp_db: Path, populated_store: FlowStore, tmp_path: Path, monkeypatch
    ):
        """One tracker file => table with the symbol shows."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        monkeypatch.setattr(
            "flowtracker.research.thesis_tracker._VAULT_BASE", tmp_path
        )
        d = tmp_path / "SBIN"
        d.mkdir(parents=True, exist_ok=True)
        (d / "thesis-tracker.md").write_text(_TRACKER_YAML_PASSING)

        result = runner.invoke(app, ["research", "thesis-status"])
        assert result.exit_code == 0, result.output
        assert "SBIN" in result.output


# ---------------------------------------------------------------------------
# compare — orchestration with mocked agent + assembly + browser
# ---------------------------------------------------------------------------


class TestCompare:
    def test_one_symbol_rejected(self, monkeypatch):
        """Need at least 2 symbols — single symbol => exit 1."""
        result = runner.invoke(app, ["research", "compare", "SBIN"])
        assert result.exit_code == 1
        assert "at least 2" in result.output.lower()

    def test_six_symbols_rejected(self, monkeypatch):
        """Capped at 5 symbols — 6 => exit 1."""
        result = runner.invoke(
            app, ["research", "compare", "A", "B", "C", "D", "E", "F"]
        )
        assert result.exit_code == 1
        assert "maximum 5" in result.output.lower()

    def test_compare_two_symbols_happy_path(
        self, tmp_db: Path, populated_store: FlowStore, tmp_path: Path, monkeypatch
    ):
        """Happy path: comparison agent + report assembly mocked, browser
        suppressed. Should exit 0 and print the report path."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Mock the async agent — return (envelope, trace).
        envelope = _make_envelope()
        trace = _make_trace()
        async def _fake_agent(**kwargs):
            return envelope, trace

        monkeypatch.setattr(
            "flowtracker.research.agent.run_comparison_agent", _fake_agent
        )

        # Stub assembly to write tiny files inside tmp_path.
        html_path = tmp_path / "compare.html"
        md_path = tmp_path / "compare.md"
        html_path.write_text("<html></html>")
        md_path.write_text("# md")

        def _fake_assemble(symbols, env):
            return html_path, md_path

        monkeypatch.setattr(
            "flowtracker.research.assembly.assemble_comparison_report",
            _fake_assemble,
        )

        # Suppress browser open + trace save
        monkeypatch.setattr("webbrowser.open", lambda *a, **kw: True)
        monkeypatch.setattr(
            "flowtracker.research.briefing.save_trace",
            lambda t: tmp_path / "trace.json",
        )

        result = runner.invoke(app, ["research", "compare", "SBIN", "INFY"])
        assert result.exit_code == 0, result.output
        assert "Report saved" in result.output
        # Symbols are uppercased and joined for the header
        assert "SBIN" in result.output and "INFY" in result.output


# ---------------------------------------------------------------------------
# explain — full happy path with mocked agent
# ---------------------------------------------------------------------------


class TestExplain:
    def test_neither_symbol_nor_file_exits_one(self):
        """No --symbol and no --file => exit 1."""
        result = runner.invoke(app, ["research", "explain"])
        assert result.exit_code == 1
        assert "Provide" in result.output or "symbol" in result.output.lower()

    def test_missing_file_exits_one(self, tmp_path: Path):
        """--file pointing at a non-existent path => exit 1."""
        bogus = tmp_path / "nope.md"
        result = runner.invoke(app, ["research", "explain", "-f", str(bogus)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_no_thesis_dir_for_symbol_exits_one(self, tmp_path: Path, monkeypatch):
        """--symbol with no vault thesis dir => exit 1."""
        # Re-route HOME so vault path is empty
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(app, ["research", "explain", "-s", "NOSUCH"])
        assert result.exit_code == 1
        assert "No thesis" in result.output

    def test_explain_with_file_happy_path(self, tmp_path: Path, monkeypatch):
        """Provide a real --file. Mock run_explainer_agent + render + browser
        so we exercise the whole explain() body end-to-end."""
        # Build an input markdown of plausible size (>10 chars).
        md = tmp_path / "sbin-thesis.md"
        md.write_text("# SBIN technical thesis\n" + ("body line\n" * 100))

        # Mock the explainer agent to return a long-enough friendly report.
        long_friendly = "## Friendly\n" + ("explained line\n" * 200)
        envelope = BriefingEnvelope(
            agent="explainer",
            symbol="SBIN",
            report=long_friendly,
            briefing={},
            evidence=[],
            cost=AgentCost(total_cost_usd=0.02, duration_seconds=5.0),
        )
        trace = AgentTrace(
            agent="explainer",
            symbol="SBIN",
            started_at="2026-01-01T00:00:00+00:00",
        )

        async def _fake_explainer(symbol, technical_md, model):
            return envelope, trace

        monkeypatch.setattr(
            "flowtracker.research.agent.run_explainer_agent", _fake_explainer
        )
        # Suppress HTML rendering — return a simple stub.
        monkeypatch.setattr(
            "flowtracker.research.assembly._render_html",
            lambda md_text, sym, name, dt: "<html>ok</html>",
        )
        # Suppress trace persistence and browser open.
        monkeypatch.setattr(
            "flowtracker.research.briefing.save_trace",
            lambda t: tmp_path / "trace.json",
        )
        monkeypatch.setattr("webbrowser.open", lambda *a, **kw: True)

        result = runner.invoke(app, ["research", "explain", "-f", str(md)])
        assert result.exit_code == 0, result.output
        # The friendly md should have been written next to the input
        friendly_path = tmp_path / "sbin-thesis-friendly.md"
        assert friendly_path.exists()
        assert "Friendly" in friendly_path.read_text()


# ---------------------------------------------------------------------------
# verify — current implementation is a stub
# ---------------------------------------------------------------------------


class TestVerifyStub:
    def test_verify_prints_not_implemented(self, monkeypatch):
        """The verify subcommand currently prints a placeholder. Exit 0."""
        result = runner.invoke(
            app, ["research", "verify", "financials", "-s", "SBIN"]
        )
        assert result.exit_code == 0
        assert "not yet implemented" in result.output.lower()


# ---------------------------------------------------------------------------
# autoeval — argument validation + progress shortcut
# ---------------------------------------------------------------------------


class TestAutoeval:
    def test_no_agent_no_sector_exits_one(self, monkeypatch):
        """Without --agent or --sector, autoeval exits 1."""
        result = runner.invoke(app, ["research", "autoeval"])
        assert result.exit_code == 1
        assert "agent" in result.output.lower() or "sector" in result.output.lower()

    def test_progress_flag_calls_progress_main(self, monkeypatch):
        """`--progress` short-circuits to the progress chart helper."""
        called = {"n": 0}

        def _fake_progress():
            called["n"] += 1

        monkeypatch.setattr(
            "flowtracker.research.autoeval.progress.main", _fake_progress
        )
        result = runner.invoke(app, ["research", "autoeval", "--progress"])
        assert result.exit_code == 0, result.output
        assert called["n"] == 1

    def test_agent_first_dispatches_to_eval_main(self, monkeypatch):
        """Agent-first mode mutates sys.argv and calls evaluate.main; both are
        patched so we can assert wiring without running the real evaluator."""
        called = {"n": 0, "argv": None}

        def _fake_eval():
            import sys as _sys
            called["n"] += 1
            called["argv"] = list(_sys.argv)

        monkeypatch.setattr(
            "flowtracker.research.autoeval.evaluate.main", _fake_eval
        )
        result = runner.invoke(
            app, ["research", "autoeval", "-a", "business", "--cycle", "3"]
        )
        assert result.exit_code == 0, result.output
        assert called["n"] == 1
        # sys.argv was prefixed with "evaluate" and the agent name flowed in
        assert "evaluate" in called["argv"][0]
        assert "--agent" in called["argv"]
        assert "business" in called["argv"]
        assert "--cycle" in called["argv"]


# ---------------------------------------------------------------------------
# --help smoke for async-heavy commands. These cannot be exercised end-to-end
# without spawning the Claude SDK, so we just verify the typer plumbing is
# intact (help text renders, exit 0).
# ---------------------------------------------------------------------------


class TestHelpSmoke:
    @pytest.mark.parametrize(
        "subcmd",
        ["fundamentals", "business", "thesis", "explain", "run", "autoeval"],
    )
    def test_subcommand_help_renders(self, subcmd):
        # Force a wide, color-less terminal so help text doesn't wrap "--help"
        # mid-line (ANSI + narrow width on CI otherwise breaks the substring check).
        result = runner.invoke(
            app,
            ["research", subcmd, "--help"],
            env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
        )
        assert result.exit_code == 0, result.output
        # Each command's typer-generated help should mention --help.
        assert "--help" in result.output
