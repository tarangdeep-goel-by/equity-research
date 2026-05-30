"""US macro indicators (US add-on, feat/us-macro).

Covers the all-new US macro path that mirrors the India macro path:
  * USMacroSnapshot model (construction + optional-None)
  * us_macro_daily store round-trip (upsert -> get)
  * MacroClient.fetch_us_macro_snapshot (mocked yfinance — field mapping,
    ^TNX -> ust_10y in percent, resilience to empty/failed tickers)
  * data_api routing: _run_market=NASDAQ -> US data; unset/NSE -> India data
    (India macro_daily path must stay unaffected)
  * get_macro_indicators tool: NASDAQ returns US data (not the n/a envelope);
    India (unset) returns India data

Offline, temp-DB, no network/LLM (yfinance mocked).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from flowtracker.macro_client import MacroClient
from flowtracker.macro_models import MacroSnapshot, USMacroSnapshot
from flowtracker.store import FlowStore


def _make_hist(closes: list[float], dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"Close": closes}, index=idx)


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
class TestUSMacroSnapshotModel:
    def test_minimal(self):
        m = USMacroSnapshot(date="2026-05-29")
        assert m.date == "2026-05-29"
        assert m.vix is None
        assert m.dxy is None
        assert m.ust_3m is None
        assert m.ust_10y is None
        assert m.gold is None

    def test_all_fields(self):
        m = USMacroSnapshot(
            date="2026-05-29", vix=18.2, dxy=99.1, ust_3m=4.3, ust_5y=3.9,
            ust_10y=4.44, ust_30y=4.7, wti_crude=62.0, brent_crude=65.0,
            gold=3300.0,
        )
        assert m.vix == 18.2
        assert m.ust_10y == 4.44
        assert m.wti_crude == 62.0
        assert m.gold == 3300.0


# --------------------------------------------------------------------------- #
# Store round-trip
# --------------------------------------------------------------------------- #
class TestUSMacroStore:
    def test_upsert_then_get(self, store: FlowStore):
        n = store.upsert_us_macro_daily([
            {
                "date": "2026-05-29", "vix": 18.2, "dxy": 99.1, "ust_3m": 4.3,
                "ust_5y": 3.9, "ust_10y": 4.44, "ust_30y": 4.7,
                "wti_crude": 62.0, "brent_crude": 65.0, "gold": 3300.0,
            },
        ])
        assert n == 1
        rows = store.get_us_macro_daily(7)
        assert len(rows) == 1
        r = rows[0]
        assert r["date"] == "2026-05-29"
        assert r["vix"] == 18.2
        assert r["ust_10y"] == 4.44
        assert r["gold"] == 3300.0

    def test_upsert_idempotent_on_date(self, store: FlowStore):
        store.upsert_us_macro_daily([{"date": "2026-05-29", "vix": 18.2}])
        store.upsert_us_macro_daily([{"date": "2026-05-29", "vix": 19.5}])
        rows = store.get_us_macro_daily(7)
        assert len(rows) == 1
        assert rows[0]["vix"] == 19.5

    def test_empty_rows_noop(self, store: FlowStore):
        assert store.upsert_us_macro_daily([]) == 0

    def test_india_macro_daily_untouched(self, store: FlowStore):
        """Writing us_macro_daily must not touch India macro_daily."""
        store.upsert_macro_snapshots([
            MacroSnapshot(date="2026-05-29", india_vix=14.5, gsec_10y=6.4),
        ])
        store.upsert_us_macro_daily([{"date": "2026-05-29", "vix": 18.2}])
        india = store.get_macro_latest()
        assert india is not None
        assert india.india_vix == 14.5
        assert india.gsec_10y == 6.4


# --------------------------------------------------------------------------- #
# Fetcher (mocked yfinance)
# --------------------------------------------------------------------------- #
class TestFetchUSMacroSnapshot:
    def test_field_mapping_and_percent(self):
        hist_map = {
            "^VIX": _make_hist([18.2], ["2026-05-29"]),
            "DX-Y.NYB": _make_hist([99.10], ["2026-05-29"]),
            "^IRX": _make_hist([4.30], ["2026-05-29"]),
            "^FVX": _make_hist([3.90], ["2026-05-29"]),
            "^TNX": _make_hist([4.44], ["2026-05-29"]),   # 10Y yield in percent
            "^TYX": _make_hist([4.70], ["2026-05-29"]),
            "CL=F": _make_hist([62.0], ["2026-05-29"]),
            "BZ=F": _make_hist([65.0], ["2026-05-29"]),
            "GC=F": _make_hist([3300.0], ["2026-05-29"]),
        }

        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = hist_map.get(symbol, pd.DataFrame())
            return t

        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with MacroClient() as client:
                snaps = client.fetch_us_macro_snapshot(days=5)

        assert len(snaps) == 1
        s = snaps[0]
        assert s.date == "2026-05-29"
        assert s.vix == 18.2
        assert s.dxy == 99.10
        assert s.ust_3m == 4.30
        assert s.ust_5y == 3.90
        assert s.ust_10y == 4.44   # ^TNX stored as-is in percent
        assert s.ust_30y == 4.70
        assert s.wti_crude == 62.0
        assert s.brent_crude == 65.0
        assert s.gold == 3300.0

    def test_failed_ticker_field_stays_none(self):
        """A ticker that raises leaves its field None without aborting."""
        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "^TNX":
                t.history.side_effect = RuntimeError("network down")
            elif symbol == "^VIX":
                t.history.return_value = _make_hist([18.2], ["2026-05-29"])
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with MacroClient() as client:
                snaps = client.fetch_us_macro_snapshot(days=5)

        assert len(snaps) == 1
        assert snaps[0].vix == 18.2
        assert snaps[0].ust_10y is None  # failed ticker -> None, not aborted

    def test_all_empty_returns_empty(self):
        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with MacroClient() as client:
                snaps = client.fetch_us_macro_snapshot(days=5)
        assert snaps == []


# --------------------------------------------------------------------------- #
# data_api routing — US run vs India run
# --------------------------------------------------------------------------- #
def _seed_both(tmp_db: Path) -> None:
    """Seed both an India macro_daily row and a us_macro_daily row."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_macro_snapshots([
            MacroSnapshot(
                date="2026-05-29", india_vix=14.5, usd_inr=85.2, gsec_10y=6.40,
            ),
        ])
        store.upsert_us_macro_daily([
            {
                "date": "2026-05-29", "vix": 18.2, "dxy": 99.1, "ust_3m": 4.3,
                "ust_5y": 3.9, "ust_10y": 4.44, "ust_30y": 4.7,
                "wti_crude": 62.0, "brent_crude": 65.0, "gold": 3300.0,
            },
        ])


class TestMacroRouting:
    def test_us_run_macro_snapshot(self, tmp_db, monkeypatch):
        from flowtracker.research.data_api import ResearchDataAPI, _run_market

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        token = _run_market.set("NASDAQ")
        try:
            with ResearchDataAPI() as api:
                data = api.get_macro_snapshot()
        finally:
            _run_market.reset(token)

        # US fields present; India fields absent.
        assert data["vix"] == 18.2
        assert data["ust_10y"] == 4.44
        assert data["dxy"] == 99.1
        assert data["wti_crude"] == 62.0
        assert "india_vix" not in data
        assert "gsec_10y" not in data

    def test_india_run_macro_snapshot_unaffected(self, tmp_db, monkeypatch):
        """No run context -> India macro_daily path, byte-identical fields."""
        from flowtracker.research.data_api import ResearchDataAPI

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        with ResearchDataAPI() as api:
            data = api.get_macro_snapshot()

        assert data["india_vix"] == 14.5
        assert data["usd_inr"] == 85.2
        assert data["gsec_10y"] == 6.40
        assert "vix" not in data  # US-only field never leaks into India path
        assert "dxy" not in data

    def test_us_run_macro_indicators(self, tmp_db, monkeypatch):
        from flowtracker.research.data_api import ResearchDataAPI, _run_market

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        token = _run_market.set("NASDAQ")
        try:
            with ResearchDataAPI() as api:
                data = api.get_macro_indicators(12)
        finally:
            _run_market.reset(token)

        # US yield curve + vix/dxy/crude block; CPI/IIP/PMI null for US.
        assert data["yield_curve"]["latest"]["ust_10y"] == 4.44
        assert data["vix_dxy_crude"]["vix"] == 18.2
        assert data["vix_dxy_crude"]["dxy"] == 99.1
        assert data.get("cpi") is None
        assert data.get("pmi") is None

    def test_india_run_macro_indicators_unaffected(self, tmp_db, monkeypatch):
        """No run context -> India CPI/IIP/PMI + G-sec yield-curve shape."""
        from flowtracker.research.data_api import ResearchDataAPI

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        with ResearchDataAPI() as api:
            data = api.get_macro_indicators(12)

        # India shape: cpi/iip/pmi/yield_curve keys with latest/trend/history.
        assert "cpi" in data
        assert "iip" in data
        assert "pmi" in data
        assert "yield_curve" in data
        # No US-only block leaks into India path.
        assert "vix_dxy_crude" not in data


# --------------------------------------------------------------------------- #
# Tool — get_macro_indicators routes US vs India (no n/a envelope for US)
# --------------------------------------------------------------------------- #
class TestMacroIndicatorsTool:
    def test_us_run_returns_us_data(self, tmp_db, monkeypatch):
        import asyncio

        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        token = _run_market.set("NASDAQ")
        try:
            result = asyncio.run(t.get_macro_indicators.handler({"months": 12}))
        finally:
            _run_market.reset(token)

        text = result["content"][0]["text"]
        payload = json.loads(text)
        # Not the not-applicable envelope.
        assert payload.get("status") != "not_applicable"
        assert payload["yield_curve"]["latest"]["ust_10y"] == 4.44
        assert payload["vix_dxy_crude"]["vix"] == 18.2

    def test_india_run_returns_india_data(self, tmp_db, monkeypatch):
        import asyncio

        from flowtracker.research import tools as t

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        _seed_both(tmp_db)
        result = asyncio.run(t.get_macro_indicators.handler({"months": 12}))

        payload = json.loads(result["content"][0]["text"])
        assert payload.get("status") != "not_applicable"
        assert "cpi" in payload
        assert "yield_curve" in payload
        assert "vix_dxy_crude" not in payload
