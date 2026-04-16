"""Snapshot tests for every CLI --help output.

Locks down the visible surface of all flowtrack commands. If a command's
help text changes (option added/removed/renamed, flag description edited,
callback docstring reworded), the snapshot diff forces an explicit review.

Purpose:
    Catches silent option removal, typo fixes that break muscle memory,
    and argparse/Typer wiring regressions.

Update snapshots intentionally:
    uv run pytest tests/contract/test_cli_help_snapshot.py --snapshot-update

Runs in-process via Typer's CliRunner (~4s for all 119 commands), so it
stays in the default (non-slow) test suite.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from flowtracker.main import app
from tests.unit.test_smoke import HELP_COMMANDS

runner = CliRunner()

# Force deterministic rendering: no ANSI colors, fixed terminal width,
# dumb terminal so Rich doesn't emit cursor/control sequences.
_ENV = {"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"}


def _help_key(cmd_path: list[str]) -> str:
    """Stable key for the snapshot dict — same format every run."""
    return " ".join(cmd_path) if cmd_path else "(root)"


@pytest.mark.timeout(60)
def test_help_outputs_match_snapshot(snapshot):
    """Every CLI command --help output is snapshotted.

    Gate: if you change CLI surface intentionally, re-run with
    ``--snapshot-update`` to accept the new shape.
    """
    outputs: dict[str, str] = {}
    for cmd_path in HELP_COMMANDS:
        result = runner.invoke(app, cmd_path, env=_ENV, catch_exceptions=False)
        assert result.exit_code == 0, (
            f"{cmd_path} --help failed (exit {result.exit_code}): "
            f"{result.output[:200]}"
        )
        outputs[_help_key(cmd_path)] = result.output
    assert outputs == snapshot
