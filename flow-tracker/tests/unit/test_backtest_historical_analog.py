"""Tests for the Historical Analog backtest harness — Part 3 PR-B2.

Covers safe vault path (FLOWTRACK_BACKTEST_OUT_DIR), cohort audit columns
in the TSV, and the O(n) sampler dedup fix. Mirrors the macro-as-of pattern
from PR-A1.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from flowtracker.research import briefing as briefing_mod
from flowtracker.research.autoeval import backtest_historical_analog as bh
from flowtracker.research.briefing import (
    BriefingEnvelope,
    save_envelope,
)


# ---------------------------------------------------------------------------
# 1. run_analog_agent_as_of passes FLOWTRACK_BACKTEST_OUT_DIR
# ---------------------------------------------------------------------------

def test_run_agent_passes_backtest_out_dir_env(monkeypatch):
    captured: dict = {}

    class _Proc:
        returncode = 0

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return _Proc()

    monkeypatch.setattr(bh.subprocess, "run", fake_run)
    duration, ok = bh.run_analog_agent_as_of("SBIN", "2023-12-31")
    assert ok is True
    env = captured["env"]
    assert env["FLOWTRACK_AS_OF"] == "2023-12-31"
    out_dir = env["FLOWTRACK_BACKTEST_OUT_DIR"]
    assert out_dir.endswith("/backtest/2023-12-31/SBIN")
    assert "/.local/share/flowtracker/" in out_dir
    assert "PATH" in env  # parent env preserved


# ---------------------------------------------------------------------------
# 2-3. save_envelope redirect for historical_analog only
# ---------------------------------------------------------------------------

def _make_envelope(agent: str, symbol: str = "SBIN") -> BriefingEnvelope:
    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        report=f"# {agent} report\n",
        briefing={"agent": agent, "top_analogs": []},
    )


def test_save_envelope_redirects_historical_analog_to_backtest_dir(
    tmp_path, monkeypatch
):
    # Real vault target (must NOT be touched)
    real_vault = tmp_path / "real_vault" / "stocks"
    monkeypatch.setattr(briefing_mod, "_VAULT_BASE", real_vault)

    backtest_dir = tmp_path / "bt_out"
    monkeypatch.setenv("FLOWTRACK_BACKTEST_OUT_DIR", str(backtest_dir))

    env = _make_envelope("historical_analog", "SBIN")
    save_envelope(env)

    # Briefing should land in override dir
    assert (backtest_dir / "historical_analog.json").exists()
    data = json.loads((backtest_dir / "historical_analog.json").read_text())
    assert data["agent"] == "historical_analog"

    # Real vault briefings dir for SBIN must NOT exist
    leaked = real_vault / "SBIN" / "briefings" / "historical_analog.json"
    assert not leaked.exists(), f"Override leaked into real vault: {leaked}"


def test_save_envelope_no_redirect_for_other_agents(tmp_path, monkeypatch):
    real_vault = tmp_path / "real_vault" / "stocks"
    monkeypatch.setattr(briefing_mod, "_VAULT_BASE", real_vault)
    backtest_dir = tmp_path / "bt_out"
    monkeypatch.setenv("FLOWTRACK_BACKTEST_OUT_DIR", str(backtest_dir))

    env = _make_envelope("business", "SBIN")
    save_envelope(env)

    # business should still write to legacy symbol vault, NOT override dir
    legacy = real_vault / "SBIN" / "briefings" / "business.json"
    assert legacy.exists()
    assert not (backtest_dir / "business.json").exists()
    assert not (backtest_dir / "historical_analog.json").exists()


# ---------------------------------------------------------------------------
# 4. load_briefing override
# ---------------------------------------------------------------------------

def test_load_briefing_uses_override_when_as_of_set(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    override_dir = (
        tmp_path
        / ".local"
        / "share"
        / "flowtracker"
        / "backtest"
        / "2023-12-31"
        / "SBIN"
    )
    override_dir.mkdir(parents=True)
    payload = {"agent": "historical_analog", "top_analogs": [{"return_12m_pct": 5}]}
    (override_dir / "historical_analog.json").write_text(json.dumps(payload))

    out = bh.load_briefing("SBIN", "2023-12-31")
    assert out is not None
    assert out["agent"] == "historical_analog"
    assert out["top_analogs"][0]["return_12m_pct"] == 5

    # Without as_of_date arg → falls back to legacy ~/vault path (which is empty)
    assert bh.load_briefing("SBIN") is None


# ---------------------------------------------------------------------------
# 5-6. score_sample records cohort stats / handles empty cohort
# ---------------------------------------------------------------------------

def test_score_sample_records_cohort_stats():
    sample_meta = {
        "symbol": "ABC", "as_of_date": "2024-01-01", "return_12m_pct": -30.0,
    }
    briefing = {
        "directional_adjustments": {
            "upside": "Unchanged", "base": "Unchanged", "downside": "Thicker",
        },
        "top_analogs": [
            {"return_12m_pct": -20}, {"return_12m_pct": -10},
            {"return_12m_pct": 0}, {"return_12m_pct": 10},
            {"return_12m_pct": 20},
        ],
        "relaxation_level": 1,
    }
    res = bh.score_sample(sample_meta, briefing)
    assert res.cohort_n == 5
    # statistics.quantiles(n=4) default method='exclusive' on n=5 returns
    # [-15.0, 0.0, 15.0] — verify p25/p75 match the library output exactly
    # (don't hand-recompute; just assert the contract).
    assert res.cohort_p25_12m == pytest.approx(-15.0)
    assert res.cohort_p75_12m == pytest.approx(15.0)
    assert res.relaxation_level == 1


def test_score_sample_handles_empty_cohort():
    sample_meta = {
        "symbol": "ABC", "as_of_date": "2024-01-01", "return_12m_pct": -30.0,
    }
    briefing = {
        "directional_adjustments": {"downside": "Thicker"},
        "top_analogs": [],
    }
    res = bh.score_sample(sample_meta, briefing)
    assert res.cohort_n == 0
    assert res.cohort_p25_12m is None
    assert res.cohort_p75_12m is None
    assert res.relaxation_level is None
    # Existing error path preserved
    assert res.error == "No cohort 12m returns to compute quartile"


# ---------------------------------------------------------------------------
# 7. Sampler O(n) dedup with large population
# ---------------------------------------------------------------------------

def test_stratified_sampler_no_dup_at_n_50():
    # 200 unique (symbol, as_of_date) keys spread across the 3 outcome buckets,
    # plus a wodge of literal duplicates appended to the tail to verify dedup
    # by composite key (the previous `row not in sample` was O(n²) and
    # dict-comparison-heavy).
    population = []
    for i in range(60):
        population.append({
            "symbol": f"R{i}", "as_of_date": "2024-03-31",
            "return_12m_pct": 25.0, "outcome_label": "recovered",
        })
        population.append({
            "symbol": f"S{i}", "as_of_date": "2024-03-31",
            "return_12m_pct": 5.0, "outcome_label": "sideways",
        })
        population.append({
            "symbol": f"B{i}", "as_of_date": "2024-03-31",
            "return_12m_pct": -25.0, "outcome_label": "blew_up",
        })
    population.extend(population[:20])  # literal duplicates

    start = time.monotonic()
    sample = bh.stratified_sample(population, n=50, seed=7)
    elapsed = time.monotonic() - start

    assert len(sample) == 50
    keys = [(r["symbol"], r["as_of_date"]) for r in sample]
    assert len(set(keys)) == 50, "duplicate (symbol, as_of_date) leaked"
    assert elapsed < 1.0, f"sampler too slow: {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# 8. --skip-run miss prints expected path
# ---------------------------------------------------------------------------

def test_skip_run_fails_loud_with_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Stub out load_mature_analog_points so we don't hit the real DB
    monkeypatch.setattr(
        bh, "load_mature_analog_points",
        lambda cutoff_age_days=450: [
            {"symbol": "GHOST", "as_of_date": "2023-06-30",
             "return_12m_pct": -5.0, "outcome_label": "sideways"},
        ],
    )
    # Bypass open() for TSV write (we only care about print output)
    monkeypatch.setattr(bh, "append_backtest_tsv", lambda *a, **k: None)

    monkeypatch.setattr(
        "sys.argv",
        ["backtest_historical_analog.py", "--n", "1", "--skip-run", "--seed", "1"],
    )
    bh.main()
    out = capsys.readouterr().out
    expected_path = (
        tmp_path / ".local" / "share" / "flowtracker" / "backtest"
        / "2023-06-30" / "GHOST" / "historical_analog.json"
    )
    assert str(expected_path) in out
    assert "--skip-run" in out


# ---------------------------------------------------------------------------
# 9. timezone-aware datetime in TSV
# ---------------------------------------------------------------------------

def test_uses_timezone_aware_datetime(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "BACKTEST_RESULTS_TSV", tmp_path / "out.tsv")
    sample = bh.BacktestSample(
        symbol="X", as_of_date="2024-01-01", realized_12m_pct=5.0,
        realized_quartile=2, directional_call={"upside": "Unchanged"},
    )
    bh.append_backtest_tsv([sample], {})
    contents = (tmp_path / "out.tsv").read_text()
    # First data row's timestamp should carry tz offset
    lines = [ln for ln in contents.splitlines() if ln and not ln.startswith("#")]
    assert len(lines) >= 2  # header + one row
    data_row = lines[1]
    ts = data_row.split("\t")[0]
    assert "+00:00" in ts or ts.endswith("Z"), f"timestamp lacks tz: {ts}"
