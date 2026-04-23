"""Unit tests for F&O store methods (Sprint 2).

Covers upsert_fno_contracts, upsert_fno_participant_oi, upsert_fno_universe,
get_fno_oi_history, get_fno_contracts_for_date, get_pcr, get_basis,
get_oi_percentile, get_fii_derivative_positioning, get_fno_eligible_stocks.

Note on clock: tests that drive data via `date.today()` (OI history/percentile)
are NOT wrapped in @freeze_time because their production path
(store.get_fno_oi_history) filters via SQLite's `date('now')`, which freezegun
does not mock. Under real wall-clock, Python and SQLite time move together,
so these tests remain robust. See individual test docstrings for details.
"""

from __future__ import annotations

from datetime import date, timedelta

from flowtracker.fno_models import (
    FnoContract,
    FnoParticipantOi,
    FnoUniverse,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _mk_contract(**overrides) -> FnoContract:
    defaults = dict(
        trade_date=date(2026, 4, 17),
        symbol="RELIANCE",
        instrument="FUTSTK",
        expiry_date=date(2026, 4, 24),
        close=1490.0,
        open_interest=1_000_000,
    )
    defaults.update(overrides)
    return FnoContract(**defaults)


def _mk_participant(**overrides) -> FnoParticipantOi:
    defaults = dict(
        trade_date=date(2026, 4, 17),
        participant="FII",
        instrument_category="stk_fut",
        long_oi=100_000,
        short_oi=50_000,
    )
    defaults.update(overrides)
    return FnoParticipantOi(**defaults)


def _mk_universe(symbol="RELIANCE", **overrides) -> FnoUniverse:
    defaults = dict(
        symbol=symbol,
        eligible_since=date(2020, 1, 1),
        last_verified=date(2026, 4, 17),
    )
    defaults.update(overrides)
    return FnoUniverse(**defaults)


def _insert_spot(store, symbol: str, d: date, close: float) -> None:
    """Insert a minimal daily_stock_data row (raw SQL — no upsert helper needed)."""
    store._conn.execute(
        "INSERT OR REPLACE INTO daily_stock_data "
        "(date, symbol, open, high, low, close, prev_close, volume, turnover) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d.isoformat(), symbol, close, close, close, close, close, 0, 0.0),
    )
    store._conn.commit()


# ---------------------------------------------------------------------------
# upsert_fno_contracts
# ---------------------------------------------------------------------------

def test_upsert_fno_contracts_insert_and_replace(store):
    """Insert 3 mixed contracts; re-upsert FUTSTK with new OI and verify replacement."""
    contracts = [
        _mk_contract(instrument="FUTSTK", strike=None, option_type=None, open_interest=1_000_000),
        _mk_contract(instrument="OPTSTK", strike=1500.0, option_type="CE", open_interest=200_000),
        _mk_contract(instrument="OPTSTK", strike=1500.0, option_type="PE", open_interest=300_000),
    ]
    store.upsert_fno_contracts(contracts)

    rows = store._conn.execute(
        "SELECT * FROM fno_contracts WHERE symbol='RELIANCE' AND trade_date='2026-04-17'"
    ).fetchall()
    assert len(rows) == 3

    # Re-upsert the FUTSTK row with new OI
    store.upsert_fno_contracts([
        _mk_contract(
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=2_500_000,
        )
    ])
    fut_rows = store._conn.execute(
        "SELECT open_interest FROM fno_contracts "
        "WHERE symbol='RELIANCE' AND instrument='FUTSTK' AND trade_date='2026-04-17'"
    ).fetchall()
    assert len(fut_rows) == 1
    assert fut_rows[0]["open_interest"] == 2_500_000


def test_upsert_fno_contracts_future_without_strike(store):
    """FUTSTK with None strike/option_type → stored with sentinels, returned as None."""
    store.upsert_fno_contracts([
        _mk_contract(instrument="FUTSTK", strike=None, option_type=None)
    ])
    # Raw row has sentinel values
    raw = store._conn.execute(
        "SELECT strike, option_type FROM fno_contracts WHERE symbol='RELIANCE'"
    ).fetchone()
    assert raw["strike"] == -1
    assert raw["option_type"] == ""
    # But get_fno_contracts_for_date normalizes back to None
    out = store.get_fno_contracts_for_date("RELIANCE", date(2026, 4, 17))
    assert len(out) == 1
    assert out[0]["strike"] is None
    assert out[0]["option_type"] is None


# ---------------------------------------------------------------------------
# get_fno_oi_history
# ---------------------------------------------------------------------------

def test_get_fno_oi_history_returns_front_month(store):
    """With two expiries per trade_date, only rows for the nearest expiry come back.

    Note: intentionally NOT wrapped in @freeze_time — get_fno_oi_history's
    90-day window is computed via SQLite's `date('now')`, which is not
    mockable by freezegun. Python's date.today() and SQLite's date('now')
    already move together under real wall-clock, so the test is robust.
    """
    today = date.today()
    apr_expiry = today + timedelta(days=7)
    may_expiry = today + timedelta(days=42)
    contracts = []
    for offset, oi in [(2, 1_000_000), (1, 1_050_000), (0, 1_100_000)]:
        td = today - timedelta(days=offset)
        # Near-month (front) expiry
        contracts.append(_mk_contract(
            trade_date=td, expiry_date=apr_expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=oi,
        ))
        # Far-month expiry (should be excluded by front-month filter)
        contracts.append(_mk_contract(
            trade_date=td, expiry_date=may_expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=oi + 500_000,
        ))
    store.upsert_fno_contracts(contracts)

    history = store.get_fno_oi_history("RELIANCE", days=90)
    assert len(history) == 3
    # Ordered ASC
    dates_asc = [h["trade_date"] for h in history]
    assert dates_asc == sorted(dates_asc)
    # All rows belong to the front (apr) expiry
    for h in history:
        assert h["expiry_date"] == apr_expiry.isoformat()


def test_get_fno_oi_history_window_filter(store):
    """`days` filter excludes rows older than today - days.

    See note on test_get_fno_oi_history_returns_front_month re: unfrozen clock.
    """
    today = date.today()
    expiry = today + timedelta(days=14)
    contracts = []
    for offset in [100, 50, 10]:
        td = today - timedelta(days=offset)
        contracts.append(_mk_contract(
            trade_date=td, expiry_date=expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=1_000_000,
        ))
    store.upsert_fno_contracts(contracts)

    history = store.get_fno_oi_history("RELIANCE", days=30)
    assert len(history) == 1
    assert history[0]["trade_date"] == (today - timedelta(days=10)).isoformat()


# ---------------------------------------------------------------------------
# get_pcr
# ---------------------------------------------------------------------------

def test_get_pcr(store):
    """PCR = total PE OI / total CE OI across all option rows on that date."""
    store.upsert_fno_contracts([
        _mk_contract(
            instrument="OPTSTK", strike=1500.0, option_type="CE",
            open_interest=200_000,
        ),
        _mk_contract(
            instrument="OPTSTK", strike=1500.0, option_type="PE",
            open_interest=300_000,
        ),
    ])
    pcr = store.get_pcr("RELIANCE", date(2026, 4, 17))
    assert pcr is not None
    assert pcr["total_ce_oi"] == 200_000
    assert pcr["total_pe_oi"] == 300_000
    assert pcr["pcr_oi"] == 1.5


def test_get_pcr_returns_none_when_no_data(store):
    """No option rows for the date → None."""
    assert store.get_pcr("RELIANCE", date(2026, 4, 17)) is None


def test_get_pcr_returns_none_when_zero_ce(store):
    """Only PE rows (zero CE OI) → None (avoids divide-by-zero)."""
    store.upsert_fno_contracts([
        _mk_contract(
            instrument="OPTSTK", strike=1500.0, option_type="PE",
            open_interest=300_000,
        ),
    ])
    assert store.get_pcr("RELIANCE", date(2026, 4, 17)) is None


# ---------------------------------------------------------------------------
# get_basis
# ---------------------------------------------------------------------------

def test_get_basis(store):
    """Futures close 1490 vs spot close 1485 → basis_abs=5, basis_pct≈0.337."""
    as_of = date(2026, 4, 17)
    expiry = date(2026, 4, 24)
    _insert_spot(store, "RELIANCE", as_of, 1485.0)
    store.upsert_fno_contracts([
        _mk_contract(
            trade_date=as_of, expiry_date=expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            close=1490.0,
        ),
    ])

    basis = store.get_basis("RELIANCE", as_of)
    assert basis is not None
    assert basis["spot"] == 1485.0
    assert basis["futures"] == 1490.0
    assert basis["basis_abs"] == 5.0
    assert abs(basis["basis_pct"] - 0.336700) < 1e-3
    assert basis["expiry_date"] == "2026-04-24"
    assert basis["days_to_expiry"] == 7


def test_get_basis_returns_none_when_missing(store):
    """Missing either side (spot or futures) → None."""
    as_of = date(2026, 4, 17)
    # No data at all
    assert store.get_basis("RELIANCE", as_of) is None

    # Only spot, no futures
    _insert_spot(store, "RELIANCE", as_of, 1485.0)
    assert store.get_basis("RELIANCE", as_of) is None

    # Only futures, no spot (different symbol)
    store.upsert_fno_contracts([
        _mk_contract(
            trade_date=as_of, symbol="INFY", expiry_date=date(2026, 4, 24),
            instrument="FUTSTK", strike=None, option_type=None,
            close=1490.0,
        ),
    ])
    assert store.get_basis("INFY", as_of) is None


# ---------------------------------------------------------------------------
# get_oi_percentile
# ---------------------------------------------------------------------------

def test_get_oi_percentile(store):
    """Linear 90-day OI series: max-day percentile ≈100, min-day ≈low.

    See note on test_get_fno_oi_history_returns_front_month re: unfrozen clock.
    """
    today = date.today()
    expiry = today + timedelta(days=14)
    contracts = []
    # Values increase linearly, most recent trade_date = highest OI
    # offset=89 is oldest (lowest OI), offset=0 is newest (highest OI)
    for offset in range(90):
        td = today - timedelta(days=offset)
        oi = 1_000_000 + (89 - offset) * 100_000  # 1M to ~9.9M
        contracts.append(_mk_contract(
            trade_date=td, expiry_date=expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=oi,
        ))
    store.upsert_fno_contracts(contracts)

    # Newest day has the highest OI → ≈100%
    pct_high = store.get_oi_percentile("RELIANCE", today, lookback_days=90)
    assert pct_high is not None
    assert pct_high >= 99.0  # at or near 100

    # Oldest day in-window has the lowest OI → very low percentile
    oldest_in_window = today - timedelta(days=89)
    pct_low = store.get_oi_percentile("RELIANCE", oldest_in_window, lookback_days=90)
    assert pct_low is not None
    assert pct_low <= 5.0


def test_get_oi_percentile_returns_none_when_thin(store):
    """<5 data points → None.

    See note on test_get_fno_oi_history_returns_front_month re: unfrozen clock.
    """
    today = date.today()
    expiry = today + timedelta(days=14)
    contracts = []
    for offset in range(4):  # only 4 days
        contracts.append(_mk_contract(
            trade_date=today - timedelta(days=offset),
            expiry_date=expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            open_interest=1_000_000,
        ))
    store.upsert_fno_contracts(contracts)
    assert store.get_oi_percentile("RELIANCE", today, lookback_days=90) is None


# ---------------------------------------------------------------------------
# upsert_fno_universe
# ---------------------------------------------------------------------------

def test_upsert_fno_universe_preserves_eligible_since(store):
    """Re-upsert preserves original eligible_since; last_verified is updated."""
    store.upsert_fno_universe([
        _mk_universe(
            symbol="RELIANCE",
            eligible_since=date(2020, 1, 1),
            last_verified=date(2026, 4, 17),
        )
    ])
    store.upsert_fno_universe([
        _mk_universe(
            symbol="RELIANCE",
            eligible_since=date(2025, 6, 1),  # newer — should be ignored
            last_verified=date(2026, 4, 20),
        )
    ])

    row = store._conn.execute(
        "SELECT eligible_since, last_verified FROM fno_universe WHERE symbol='RELIANCE'"
    ).fetchone()
    assert row["eligible_since"] == "2020-01-01"
    assert row["last_verified"] == "2026-04-20"


# ---------------------------------------------------------------------------
# get_fno_eligible_stocks
# ---------------------------------------------------------------------------

def test_get_fno_eligible_stocks_sorted(store):
    """Eligible stocks are returned in alphabetical order."""
    store.upsert_fno_universe([
        _mk_universe(symbol="RELIANCE"),
        _mk_universe(symbol="TCS"),
        _mk_universe(symbol="INFY"),
    ])
    out = store.get_fno_eligible_stocks()
    assert out == ["INFY", "RELIANCE", "TCS"]


# ---------------------------------------------------------------------------
# get_fii_derivative_positioning
# ---------------------------------------------------------------------------

def test_get_fii_derivative_positioning(store):
    """FII rows across 6 categories aggregate; DII rows are excluded."""
    as_of = date(2026, 4, 17)
    categories = [
        "idx_fut", "idx_opt_ce", "idx_opt_pe",
        "stk_fut", "stk_opt_ce", "stk_opt_pe",
    ]
    rows = [
        _mk_participant(
            trade_date=as_of, participant="FII",
            instrument_category=cat,
            long_oi=100_000 + i * 10_000,
            short_oi=50_000 + i * 5_000,
        )
        for i, cat in enumerate(categories)
    ]
    # DII row must be excluded from the FII-only query
    rows.append(_mk_participant(
        trade_date=as_of, participant="DII",
        instrument_category="stk_fut",
        long_oi=999_999_999, short_oi=0,
    ))
    store.upsert_fno_participant_oi(rows)

    result = store.get_fii_derivative_positioning(as_of, days=1)
    assert result is not None
    assert result["as_of"] == as_of.isoformat()
    assert result["rows_found"] == 6  # DII row excluded
    assert set(result["by_category"].keys()) == set(categories)
    # Each bucket has all four metrics
    for cat, bucket in result["by_category"].items():
        assert "long_oi" in bucket
        assert "short_oi" in bucket
        assert "net_oi" in bucket
        assert "net_long_pct" in bucket
        assert bucket["net_oi"] == bucket["long_oi"] - bucket["short_oi"]
    # Spot-check one bucket: idx_fut (i=0) → long=100k, short=50k, net=50k
    idx_fut = result["by_category"]["idx_fut"]
    assert idx_fut["long_oi"] == 100_000
    assert idx_fut["short_oi"] == 50_000
    assert idx_fut["net_oi"] == 50_000
    assert abs(idx_fut["net_long_pct"] - (100_000 / 150_000 * 100)) < 1e-6


# ---------------------------------------------------------------------------
# get_fno_contracts_for_date (sentinel normalization, mixed rows)
# ---------------------------------------------------------------------------

def test_get_fno_contracts_for_date_normalizes_sentinels(store):
    """FUTSTK sentinels (-1/'') are normalized to None in the output row dicts."""
    as_of = date(2026, 4, 17)
    store.upsert_fno_contracts([
        _mk_contract(
            trade_date=as_of, instrument="FUTSTK",
            strike=None, option_type=None,
        ),
        _mk_contract(
            trade_date=as_of, instrument="OPTSTK",
            strike=1500.0, option_type="CE",
        ),
    ])

    rows = store.get_fno_contracts_for_date("RELIANCE", as_of)
    assert len(rows) == 2

    futures = [r for r in rows if r["instrument"] == "FUTSTK"]
    options = [r for r in rows if r["instrument"] == "OPTSTK"]
    assert len(futures) == 1 and len(options) == 1

    assert futures[0]["strike"] is None
    assert futures[0]["option_type"] is None
    assert options[0]["strike"] == 1500.0
    assert options[0]["option_type"] == "CE"
