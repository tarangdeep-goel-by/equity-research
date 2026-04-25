"""Tests for the macro-autoeval as-of plumbing (Part 3 PR-A1)."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

pytest.importorskip("yaml")

from flowtracker.research.autoeval import evaluate_macro as em  # noqa: E402
from flowtracker.research.autoeval.evaluate import AgentEvalResult  # noqa: E402


class _FakeProc:
    def __init__(self):
        self.returncode = 0
        self._poll_calls = 0

    def poll(self):
        self._poll_calls += 1
        return None if self._poll_calls == 1 else 0

    @property
    def stderr(self):
        class _S:
            def readline(self_inner): return ""
            def __iter__(self_inner): return iter([])
        return _S()

    def kill(self): pass
    def wait(self): return 0


def test_run_macro_agent_passes_flowtrack_as_of(monkeypatch):
    captured = {}

    def fake_popen(cmd, cwd=None, stdout=None, stderr=None, text=None, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return _FakeProc()

    monkeypatch.setattr(em.subprocess, "Popen", fake_popen)
    _, ok = em.run_macro_agent("2025-11-01", "NIFTY")
    assert ok is True
    env = captured["env"]
    assert env["FLOWTRACK_AS_OF"] == "2025-11-01"
    assert env["FLOWTRACK_MACRO_OUT_DIR"].endswith("/vault/macro/2025-11-01")
    assert "PATH" in env  # parent env preserved
    assert "macro" in captured["cmd"] and "-s" in captured["cmd"]


class _FakeAPI:
    def __init__(self, payload): self._payload = payload
    def get_macro_catalog(self): return self._payload


def _patch_api(monkeypatch, payload):
    import flowtracker.research.data_api as data_api_mod
    monkeypatch.setattr(data_api_mod, "ResearchDataAPI", lambda *a, **kw: _FakeAPI(payload))


def test_fetch_anchor_catalog_filters_by_as_of(monkeypatch):
    _patch_api(monkeypatch, {"anchors": [
        {"name": "ES FY24", "status": "complete", "publication_date": "2024-01-31"},
        {"name": "MPR Oct", "status": "complete", "publication_date": "2025-11-01"},
        {"name": "MPR Dec", "status": "complete", "publication_date": "2025-12-08"},
    ]})
    out = em.fetch_anchor_catalog(as_of_date="2025-11-01")
    assert set(out) == {"ES FY24", "MPR Oct"}


def test_fetch_anchor_catalog_warns_when_no_publication_date(monkeypatch, capsys):
    _patch_api(monkeypatch, {"anchors": [
        {"name": "A", "status": "complete"},
        {"name": "B", "status": "complete"},
        {"name": "C", "status": "missing"},
    ]})
    out = em.fetch_anchor_catalog(as_of_date="2025-11-01")
    assert "no publication_date" in capsys.readouterr().err.lower()
    assert set(out) == {"A", "B"}


def test_fetch_anchor_catalog_no_as_of_returns_all_complete(monkeypatch):
    _patch_api(monkeypatch, {"anchors": [
        {"name": "A1", "status": "complete", "publication_date": "2024-01-01"},
        {"name": "A2", "status": "complete", "publication_date": "2030-01-01"},
        {"name": "A3", "status": "missing"},
    ]})
    assert set(em.fetch_anchor_catalog()) == {"A1", "A2"}


def test_eval_macro_report_retries_on_gemini_failure(monkeypatch):
    monkeypatch.setattr(em, "GEMINI_RETRY_BACKOFF_S", 0)
    calls = {"n": 0}

    async def succeed_third():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError(f"transient {calls['n']}")
        return "OK"

    out = asyncio.run(em._gemini_with_retry(succeed_third, attempts=3, backoff_s=0))
    assert out == "OK" and calls["n"] == 3


def test_eval_macro_report_gives_up_after_attempts(monkeypatch):
    monkeypatch.setattr(em, "GEMINI_RETRY_BACKOFF_S", 0)
    fake_sdk = type(sys)("claude_agent_sdk")

    class _Opts:
        def __init__(self, **kw): self.kw = kw

    async def _query_always_raises(prompt=None, options=None):
        raise RuntimeError("gemini 503 boom")
        yield  # pragma: no cover

    fake_sdk.ClaudeAgentOptions = _Opts
    fake_sdk.query = _query_always_raises
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    result = asyncio.run(em.eval_macro_report("2025-11-01", "fake report", ["A1"]))
    assert result.grade == "ERR"
    assert result.grade_numeric == 0
    assert "boom" in result.summary.lower()


def test_archive_eval_run_writes_json_with_as_of_and_note(monkeypatch, tmp_path):
    monkeypatch.setattr(em, "MACRO_HISTORY_DIR", tmp_path / "eval_history")
    result = AgentEvalResult(
        agent="macro", stock="NIFTY", sector="_macro_",
        grade="A-", grade_numeric=90, summary="ok", report_length=4321,
    )
    path = em.archive_eval_run(
        result=result, as_of_date="2025-11-01",
        anchors=["ES FY24", "MPR Oct"], report_md="# body\n",
        note="baseline", run_duration_s=12.5,
    )
    assert path.exists()
    a = json.loads(path.read_text())
    assert a["agent"] == "macro"
    assert a["as_of_date"] == "2025-11-01"
    assert a["note"] == "baseline"
    assert a["anchors_used"] == ["ES FY24", "MPR Oct"]
    assert a["report_chars"] == len("# body\n")
    assert a["run_duration_s"] == 12.5
    assert a["result"]["grade"] == "A-"
    assert "ts" in a
    assert len(a["report_sha256"]) == 64
    assert path.name.startswith("macro_") and path.suffix == ".json"


def test_drop_cycle_arg_replaced_with_note(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluate_macro", "--cycle", "1"])
    with pytest.raises(SystemExit):
        em.main()
    # --note is accepted (parser builds without raising on this arg)
    monkeypatch.setattr(sys, "argv", ["evaluate_macro", "--note", "baseline", "--skip-run"])
    # main() will try to run; stub async_main to a no-op so we only validate parse
    monkeypatch.setattr(em, "async_main", lambda args: None)
    monkeypatch.setattr(em.asyncio, "run", lambda coro: coro if coro is None else None)
    em.main()  # should not raise SystemExit
