"""Tests for scripts/backfill_universe_v2.py — universe-wide shareholding /
chart / pledge / qBS / qCF / estimate-revision backfill.

We import the script via importlib (it's not a package), then unit-test:
  * select_universe — liquidity filter + coverage exclusion
  * _already_processed — idempotent skip from progress log
  * backfill_symbol — per-symbol orchestration aggregates stats + isolates
    fetcher failures
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from flowtracker.holding_models import (
    PromoterPledge,
    ShareholdingRecord,
)
from flowtracker.holding_client import NSEHoldingError
from flowtracker.screener_client import ScreenerError

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "backfill_universe_v2.py"
)


@pytest.fixture
def script(monkeypatch, tmp_path):
    """Load the script as a module and point its progress log at a temp file
    so tests can't see / be polluted by a real run."""
    spec = importlib.util.spec_from_file_location("backfill_universe_v2", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_PROGRESS_LOG", tmp_path / "progress.log")
    return mod


# ---------------------------------------------------------------------------
# select_universe
# ---------------------------------------------------------------------------


def _seed_daily(store, symbol, days=120, close=100.0, volume=1_000_000):
    """Insert N unique daily-stock rows for one symbol so it clears the
    liquidity filter (>= min_days, avg turnover = close*volume/1e7 = 10 Cr).
    """
    from datetime import date as _date, timedelta

    start = _date(2024, 1, 1)
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        store._conn.execute(
            """
            INSERT OR IGNORE INTO daily_stock_data
              (date, symbol, open, high, low, close, prev_close, volume, turnover)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (d, symbol, close, close, close, close, close, volume,
             close * volume),
        )
    store._conn.commit()


def _seed_coverage(store, symbol, *, sh_quarters=4, with_charts=True):
    """Mark a symbol as 'fully covered' (>= 4 shareholding quarters + chart row)
    so select_universe excludes it."""
    if sh_quarters:
        records = [
            ShareholdingRecord(
                symbol=symbol,
                quarter_end=f"2025-{(q + 1) * 3:02d}-30",
                category="Promoter",
                percentage=50.0,
            )
            for q in range(sh_quarters)
        ]
        store.upsert_shareholding(records)
    if with_charts:
        store._conn.execute(
            "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
            "VALUES (?, 'pe', 'PE', '2024-01-01', 15.5)",
            (symbol,),
        )
        store._conn.commit()


def test_select_universe_includes_liquid_uncovered(script, store):
    _seed_daily(store, "NEWSTOCK")
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "NEWSTOCK" in syms


def test_select_universe_excludes_illiquid(script, store):
    # Below min_days threshold — only 50 daily rows.
    _seed_daily(store, "THINLY", days=50)
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "THINLY" not in syms


def test_select_universe_excludes_low_turnover(script, store):
    # Avg turnover = 100 * 100 / 1e7 = 0.001 Cr, well below 1.0.
    _seed_daily(store, "PENNY", close=100.0, volume=100)
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "PENNY" not in syms


def test_select_universe_excludes_fully_covered_symbol(script, store):
    _seed_daily(store, "COVERED")
    _seed_coverage(store, "COVERED", sh_quarters=4, with_charts=True)
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "COVERED" not in syms


def test_select_universe_includes_partial_coverage(script, store):
    # 4 quarters of shareholding but NO charts row → still needs processing.
    _seed_daily(store, "HALFCOV")
    _seed_coverage(store, "HALFCOV", sh_quarters=4, with_charts=False)
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "HALFCOV" in syms

    # Charts but only 2 shareholding quarters → still needs processing.
    _seed_daily(store, "FEWQ")
    _seed_coverage(store, "FEWQ", sh_quarters=2, with_charts=True)
    syms = script.select_universe(store, min_turnover_cr=1.0, min_days=100)
    assert "FEWQ" in syms


# ---------------------------------------------------------------------------
# _already_processed (resume-skip via progress log)
# ---------------------------------------------------------------------------


def test_already_processed_empty_when_no_log(script):
    assert script._already_processed() == set()


def test_already_processed_reads_all_statuses(script):
    log = script._PROGRESS_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as fp:
        for sym, status in [
            ("OK1", "ok"),
            ("FAIL1", "fail"),
            ("PART1", "partial"),
            ("EMPTY1", "empty"),
        ]:
            fp.write(json.dumps({
                "ts": "2026-05-26T10:00:00",
                "symbol": sym,
                "status": status,
                "note": "",
            }) + "\n")
        # Malformed line should be silently skipped, not crash the parser.
        fp.write("not-json\n")

    assert script._already_processed() == {"OK1", "FAIL1", "PART1", "EMPTY1"}


def test_log_progress_appends_jsonl(script):
    script._log_progress("SBIN", "ok", "sh=10 ch=200")
    script._log_progress("INFY", "fail", "404")
    lines = script._PROGRESS_LOG.read_text().splitlines()
    assert len(lines) == 2
    rec0 = json.loads(lines[0])
    assert rec0["symbol"] == "SBIN" and rec0["status"] == "ok"
    rec1 = json.loads(lines[1])
    assert rec1["symbol"] == "INFY" and rec1["status"] == "fail"


# ---------------------------------------------------------------------------
# backfill_symbol — happy path + per-fetcher isolation
# ---------------------------------------------------------------------------


def _mock_holding_client_ok(symbol="SBIN"):
    """Returns (records, pledges, breakdowns) like fetch_latest_quarters_full."""
    client = MagicMock()
    client.fetch_latest_quarters_full.return_value = (
        [ShareholdingRecord(
            symbol=symbol, quarter_end="2025-03-31",
            category="Promoter", percentage=50.0,
        )],
        [PromoterPledge(
            symbol=symbol, quarter_end="2025-03-31",
            pledge_pct=5.0, encumbered_pct=5.0,
        )],
        [],
    )
    return client


def _mock_screener_client_ok():
    sc = MagicMock()
    sc.fetch_company_page.return_value = (
        '<div id="company-info" data-company-id="999" data-warehouse-id="888"></div>'
    )
    sc._get_both_ids.return_value = ("999", "888")
    sc.fetch_chart_data_by_type.return_value = {
        "datasets": [
            {"metric": "PE", "values": [["2024-01-01", 15.0], ["2024-02-01", 16.0]]}
        ]
    }
    return sc


def _mock_fund_client_ok():
    fc = MagicMock()
    fc.fetch_quarterly_bs_cf.return_value = {
        "symbol": "SBIN",
        "balance_sheet": [
            {"quarter_end": "2025-03-31", "total_assets": 100.0}
        ],
        "cash_flow": [
            {"quarter_end": "2025-03-31", "operating_cash_flow": 10.0}
        ],
    }
    return fc


def _mock_estimates_client_ok():
    ec = MagicMock()
    ec.fetch_estimate_revisions.return_value = {
        "symbol": "SBIN",
        "eps_trend": {"0y": {"current": 50.0}},
        "eps_revisions": {},
        "momentum_score": 0.55,
        "momentum_signal": "neutral",
    }
    return ec


def test_backfill_symbol_happy_path(script, store):
    sc = _mock_screener_client_ok()
    hc = _mock_holding_client_ok("SBIN")
    fc = _mock_fund_client_ok()
    ec = _mock_estimates_client_ok()

    stats, errors = script.backfill_symbol(sc, hc, fc, ec, store, "SBIN")

    assert errors == []
    assert stats["sh_rows"] == 1
    assert stats["pledge_rows"] == 1
    # 'pe' + 'price' both fetched and each returns the same 2-point dataset.
    assert stats["chart_points"] == 4
    assert stats["qbs_rows"] == 1
    assert stats["qcf_rows"] == 1
    assert stats["est_rev_rows"] >= 1

    # Verify the rows actually landed in the DB.
    sh = store.get_shareholding("SBIN", limit=10)
    assert any(r.category == "Promoter" for r in sh)


def test_backfill_symbol_isolates_shareholding_failure(script, store):
    sc = _mock_screener_client_ok()
    hc = MagicMock()
    hc.fetch_latest_quarters_full.side_effect = NSEHoldingError("XBRL 404")
    fc = _mock_fund_client_ok()
    ec = _mock_estimates_client_ok()

    stats, errors = script.backfill_symbol(sc, hc, fc, ec, store, "SBIN")

    # Shareholding error captured, but charts/qBS/qCF/est_rev still ran.
    assert any("shareholding" in e for e in errors)
    assert stats["sh_rows"] == 0
    assert stats["chart_points"] == 4
    assert stats["qbs_rows"] == 1
    assert stats["est_rev_rows"] >= 1


def test_backfill_symbol_isolates_charts_failure(script, store):
    sc = MagicMock()
    sc.fetch_company_page.side_effect = ScreenerError("login expired")
    sc._get_both_ids.return_value = ("", "")
    hc = _mock_holding_client_ok("SBIN")
    fc = _mock_fund_client_ok()
    ec = _mock_estimates_client_ok()

    stats, errors = script.backfill_symbol(sc, hc, fc, ec, store, "SBIN")

    assert any("charts" in e for e in errors)
    assert stats["sh_rows"] == 1
    assert stats["chart_points"] == 0
    assert stats["qbs_rows"] == 1
