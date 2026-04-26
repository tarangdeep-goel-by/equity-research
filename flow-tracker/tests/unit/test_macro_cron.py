"""Smoke tests for the monthly macro-eval cron (PR-A3)."""
from __future__ import annotations

import os
import plistlib
from pathlib import Path


def _root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "plists").is_dir() and (parent / "flowtracker").is_dir():
            return parent
    raise RuntimeError("flow-tracker root not found")


ROOT = _root()
SCRIPT = ROOT / "scripts" / "monthly-macro-eval.sh"
PLIST = ROOT / "scripts" / "plists" / "com.flowtracker.monthly-macro-eval.plist.tmpl"


def test_monthly_macro_eval_sh_exists_and_executable() -> None:
    assert SCRIPT.exists() and os.access(SCRIPT, os.X_OK)


def test_monthly_macro_eval_plist_parses_xml() -> None:
    data = plistlib.loads(PLIST.read_bytes())
    assert data["Label"] == "com.flowtracker.monthly-macro-eval"
    assert any("monthly-macro-eval.sh" in a for a in data["ProgramArguments"])
    assert {e.get("Day") for e in data["StartCalendarInterval"]} == {2, 17}


def test_setup_crons_includes_macro_eval() -> None:
    assert "com.flowtracker.monthly-macro-eval" in (ROOT / "scripts" / "setup-crons.sh").read_text()
