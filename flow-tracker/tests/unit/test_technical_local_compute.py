"""Local-compute fallback for MACD / Bollinger Bands / ADX.

FMP technical-indicator endpoints aren't on our plan, so the fallback path in
``ResearchDataAPI.get_technical_indicators`` augments the result with
locally-computed MACD(12,26,9), Bollinger(20, 2σ), and ADX(14, Wilder).

Tests cover:
  * pure-math correctness against synthetic price series
  * FMP-prefer behaviour (don't overwrite when FMP supplies the field)
  * insufficient-history degradation
  * the data_quality_note surface
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.fmp_models import FMPTechnicalIndicator
from flowtracker.research.data_api import (
    ResearchDataAPI,
    _adx_wilder,
    _ema,
)
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Pure-math helpers
# ---------------------------------------------------------------------------


class TestEma:
    def test_constant_series_collapses_to_constant(self):
        out = _ema([5.0] * 30, period=12)
        # Constant input -> constant output (no drift from seed).
        assert all(abs(x - 5.0) < 1e-9 for x in out)

    def test_step_function_converges_upward(self):
        # 30 bars at 100, then 30 bars at 200. EMA must rise toward 200.
        series = [100.0] * 30 + [200.0] * 30
        out = _ema(series, period=12)
        assert out[-1] > out[30]
        assert out[-1] < 200  # not yet fully converged at 30 bars in
        assert out[-1] > 180  # but well past the midpoint

    def test_seed_is_sma_of_first_period(self):
        series = [float(i) for i in range(1, 21)]  # 1..20
        out = _ema(series, period=10)
        # Seed = mean(1..10) = 5.5
        assert math.isclose(out[9], 5.5, abs_tol=1e-9)

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            _ema([1.0, 2.0, 3.0], period=10)


class TestAdxWilder:
    def test_strong_uptrend_yields_high_adx_and_plus_di_dominance(self):
        # 60 bars of monotonic uptrend: high/low/close all rising 1pt/day.
        n = 60
        closes = [100.0 + i for i in range(n)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = _adx_wilder(highs, lows, closes, period=14)
        assert result is not None
        # In a clean uptrend, +DI dominates -DI and ADX is firmly trending.
        assert result["plus_di"] > result["minus_di"]
        assert result["adx"] > 20

    def test_strong_downtrend_yields_minus_di_dominance(self):
        n = 60
        closes = [200.0 - i for i in range(n)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = _adx_wilder(highs, lows, closes, period=14)
        assert result is not None
        assert result["minus_di"] > result["plus_di"]
        assert result["adx"] > 20

    def test_too_short_returns_none(self):
        result = _adx_wilder([1.0, 2.0], [0.5, 1.5], [0.8, 1.8], period=14)
        assert result is None


# ---------------------------------------------------------------------------
# Integration: get_technical_indicators wires local compute
# ---------------------------------------------------------------------------


def _seed_synthetic_history(store: FlowStore, symbol: str, n_bars: int = 60) -> None:
    """Insert n_bars of synthetic daily_stock_data — gentle uptrend."""
    from datetime import date, timedelta

    base = date.fromisoformat("2026-01-01")
    rows: list[DailyStockData] = []
    cursor = base
    inserted = 0
    while inserted < n_bars:
        if cursor.weekday() < 5:  # weekdays only
            price = 100.0 + inserted * 0.5
            rows.append(DailyStockData(
                date=cursor.isoformat(),
                symbol=symbol,
                open=price - 0.5,
                high=price + 1.0,
                low=price - 1.5,
                close=price,
                prev_close=price - 0.5,
                volume=1000000,
                turnover=price * 1000,
            ))
            inserted += 1
        cursor += timedelta(days=1)
    store.upsert_daily_stock_data(rows)


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI on a fresh, empty test DB. Tests seed their own data."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    store = FlowStore(db_path=tmp_db)
    a = ResearchDataAPI()
    yield a
    a.close()
    store.close()


class TestGetTechnicalIndicatorsLocalCompute:
    def test_fallback_populates_macd_bb_adx_with_note(
        self, api: ResearchDataAPI, tmp_db: Path,
    ):
        """60 bars of history, no FMP rows -> locally-computed fields appear."""
        _seed_synthetic_history(api._store, "SYNTH", n_bars=60)
        rows = api.get_technical_indicators("SYNTH")
        assert rows, "expected at least one row"
        r = rows[0]

        # MACD trio
        assert "macd" in r and r["macd"] is not None
        assert "macd_signal" in r and r["macd_signal"] is not None
        assert "macd_histogram" in r and r["macd_histogram"] is not None
        # MACD = MACD line - signal => histogram should equal that subtraction.
        assert math.isclose(
            r["macd_histogram"], r["macd"] - r["macd_signal"], abs_tol=0.01,
        )

        # Bollinger Bands ordering: lower < middle < upper
        assert r["bollinger_lower"] < r["bollinger_middle"] < r["bollinger_upper"]

        # ADX trio (clean uptrend -> +DI > -DI, ADX in valid 0-100 range)
        assert r["adx_plus_di"] > r["adx_minus_di"]
        assert 0 <= r["adx"] <= 100

        # Surface the data_quality_note so callers can flag the source gap.
        assert r["data_quality_note"] == (
            "MACD/BB/ADX computed locally — FMP source unavailable"
        )

    def test_fmp_macd_preferred_over_local(
        self, api: ResearchDataAPI,
    ):
        """When FMP supplies macd/adx, the FMP rows are kept; local compute is
        only appended as supplementary (BB always local; macd/adx only if missing).
        """
        _seed_synthetic_history(api._store, "PREF", n_bars=60)
        api._store.upsert_fmp_technical_indicators([
            FMPTechnicalIndicator(symbol="PREF", date="2026-03-15", indicator="rsi", value=55.0),
            FMPTechnicalIndicator(symbol="PREF", date="2026-03-15", indicator="macd", value=999.0),
            FMPTechnicalIndicator(symbol="PREF", date="2026-03-15", indicator="adx", value=42.0),
        ])
        rows = api.get_technical_indicators("PREF")
        # FMP rows preserved as-is — find the macd row, confirm 999.
        macd_rows = [r for r in rows if r.get("indicator") == "macd"]
        assert macd_rows and macd_rows[0]["value"] == 999.0
        adx_rows = [r for r in rows if r.get("indicator") == "adx"]
        assert adx_rows and adx_rows[0]["value"] == 42.0

        # Augmented row carries Bollinger (always local) but NOT macd/adx scalars
        # (FMP supplied them; we don't double-write).
        augmented = [r for r in rows if "bollinger_upper" in r]
        assert augmented, "expected an augmented row with Bollinger"
        a = augmented[0]
        assert a.get("bollinger_lower") is not None
        assert a.get("bollinger_middle") is not None
        # macd/adx not re-supplied when FMP already has them.
        assert "macd" not in a
        assert "adx" not in a

    def test_fmp_partial_local_fills_macd_when_missing(
        self, api: ResearchDataAPI,
    ):
        """FMP gives RSI/SMA only. Local compute fills macd + adx + BB."""
        _seed_synthetic_history(api._store, "PART", n_bars=60)
        api._store.upsert_fmp_technical_indicators([
            FMPTechnicalIndicator(symbol="PART", date="2026-03-15", indicator="rsi", value=60.0),
            FMPTechnicalIndicator(symbol="PART", date="2026-03-15", indicator="sma_50", value=110.0),
        ])
        rows = api.get_technical_indicators("PART")
        augmented = [r for r in rows if "bollinger_upper" in r]
        assert augmented, "expected augmented row"
        a = augmented[0]
        assert a.get("macd") is not None
        assert a.get("adx") is not None
        assert a.get("bollinger_upper") is not None
        assert a.get("data_quality_note") == (
            "MACD/BB/ADX computed locally — FMP source unavailable"
        )

    def test_insufficient_history_returns_note(
        self, api: ResearchDataAPI,
    ):
        """<30 bars of price history -> insufficient-history note."""
        _seed_synthetic_history(api._store, "TINY", n_bars=10)
        rows = api.get_technical_indicators("TINY")
        # Either empty (unchanged behaviour for <50 bars) or a single row that
        # carries the explicit note.
        if rows:
            r = rows[0]
            assert r.get("data_quality_note") == "insufficient history for MACD/BB/ADX"
            assert r.get("macd") is None
            assert r.get("bollinger_upper") is None
        # else: no rows is also acceptable; the agent will narrate "no technicals"

    def test_no_history_returns_empty(
        self, api: ResearchDataAPI,
    ):
        """No daily_stock_data at all -> empty list, no crash."""
        rows = api.get_technical_indicators("GHOST")
        assert rows == []
