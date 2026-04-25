"""Unit tests for F&O positioning methods on ResearchDataAPI (Sprint 3).

Covers the 5 read facades: get_fno_positioning, get_oi_history,
get_option_chain_concentration, get_fii_derivative_flow, get_futures_basis.
Both happy and empty paths. See test_fno_store.py for store-level coverage.

OI/history tests use real today() because SQLite's date('now') is not mockable
by freezegun (same constraint as test_fno_store.py).
"""

from __future__ import annotations

from datetime import date, timedelta

from flowtracker.fno_models import FnoContract, FnoParticipantOi, FnoUniverse
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


def _mk_contract(**ov):
    d = dict(trade_date=date(2026, 4, 17), symbol="RELIANCE",
             instrument="FUTSTK", expiry_date=date(2026, 4, 24),
             close=1490.0, open_interest=1_000_000)
    d.update(ov)
    return FnoContract(**d)


def _mk_participant(**ov):
    d = dict(trade_date=date(2026, 4, 17), participant="FII",
             instrument_category="idx_fut", long_oi=100_000, short_oi=50_000)
    d.update(ov)
    return FnoParticipantOi(**d)


def _mk_universe(symbol="RELIANCE"):
    return FnoUniverse(symbol=symbol, eligible_since=date(2020, 1, 1),
                       last_verified=date(2026, 4, 17))


def _spot(store, symbol, d, close):
    store._conn.execute(
        "INSERT OR REPLACE INTO daily_stock_data "
        "(date, symbol, open, high, low, close, prev_close, volume, turnover) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d.isoformat(), symbol, close, close, close, close, close, 0, 0.0),
    )
    store._conn.commit()


def _series(store, symbol="RELIANCE", days=25, base=1_000_000, step=50_000):
    """Insert `days` of front-month FUTSTK rows (monotonic OI), return today."""
    today = date.today()
    expiry = today + timedelta(days=14)
    store.upsert_fno_contracts([
        _mk_contract(
            trade_date=today - timedelta(days=off), expiry_date=expiry,
            instrument="FUTSTK", strike=None, option_type=None,
            close=1490.0, open_interest=base + (days - 1 - off) * step,
        )
        for off in range(days)
    ])
    return today


# --- empty-path coverage (combined into one test per method) ---

def test_empty_paths_for_non_fno_symbol(tmp_db):
    """All 5 methods return None / [] when symbol not in fno_universe."""
    with FlowStore(db_path=tmp_db) as store:
        api = ResearchDataAPI(store=store)
        assert api.get_fno_positioning("RELIANCE") is None
        assert api.get_oi_history("RELIANCE") == []
        assert api.get_option_chain_concentration("RELIANCE") is None
        assert api.get_futures_basis("RELIANCE") == []
        assert api.get_fii_derivative_flow() == []  # fii flow is market-wide


def test_fno_positioning_eligible_but_no_data(tmp_db):
    """Universe-eligible but no contract rows → fno_eligible=True with empties."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        api = ResearchDataAPI(store=store)
        out = api.get_fno_positioning("RELIANCE")
    assert out is not None
    assert out["fno_eligible"] is True
    assert out["as_of_date"] is None
    assert out["futures_positioning"] == {}
    assert out["data_freshness"]["last_trade_date"] is None


def test_option_chain_none_when_no_options(tmp_db):
    """Eligible + only futures rows → None."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        store.upsert_fno_contracts([_mk_contract(strike=None, option_type=None)])
        api = ResearchDataAPI(store=store)
        assert api.get_option_chain_concentration("RELIANCE") is None


# --- happy paths ---

def test_fno_positioning_happy_path(tmp_db):
    """Universe + 25d futures + spot + options + FII rows → composite snapshot."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        today = _series(store, days=25)
        _spot(store, "RELIANCE", today, 1485.0)
        opt_exp = today + timedelta(days=14)
        store.upsert_fno_contracts([
            _mk_contract(trade_date=today, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1480.0, option_type="CE",
                         open_interest=300_000, implied_volatility=22.5),
            _mk_contract(trade_date=today, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1500.0, option_type="CE",
                         open_interest=200_000, implied_volatility=20.0),
            _mk_contract(trade_date=today, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1480.0, option_type="PE",
                         open_interest=400_000),
            _mk_contract(trade_date=today, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1500.0, option_type="PE",
                         open_interest=100_000),
        ])
        store.upsert_fno_participant_oi([
            _mk_participant(trade_date=today, instrument_category="idx_fut",
                            long_oi=120_000, short_oi=80_000),  # 60%
            _mk_participant(trade_date=today, instrument_category="stk_fut",
                            long_oi=60_000, short_oi=40_000),   # 60%
        ])
        api = ResearchDataAPI(store=store)
        out = api.get_fno_positioning("RELIANCE")

    assert out["fno_eligible"] is True
    assert out["as_of_date"] == today.isoformat()

    fp = out["futures_positioning"]
    assert fp["current_oi"] == 1_000_000 + 24 * 50_000
    assert fp["oi_percentile_90d"] >= 90.0
    assert fp["oi_trend_20d"] == "building"
    assert fp["basis_pct"] > 0 and fp["basis_label"] == "contango"
    assert fp["oi_change_5d_pct"] > 0

    op = out["options_positioning"]
    assert op["pcr_oi"] == 1.0  # PE 500k / CE 500k
    assert op["pcr_oi_label"] == "neutral"
    # 1480: 300k CE + 400k PE = 700k > 1500: 300k → max pain 1480
    assert op["max_pain_strike"] == 1480.0
    # ATM IV: strike 1480 (closer to spot 1485) → 22.5
    assert op["atm_iv"] == 22.5

    fii = out["fii_derivative_stance"]
    assert fii["index_fut_net_long_pct"] == 60.0
    assert fii["stock_fut_net_long_pct"] == 60.0
    assert fii["index_fut_net_long_trend"] == "flat"  # only 1 day → flat
    assert out["data_freshness"]["days_since_update"] == 0


def test_oi_history_happy_path(tmp_db):
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        _series(store, days=10)
        api = ResearchDataAPI(store=store)
        history = api.get_oi_history("RELIANCE", days=90)
    assert len(history) == 10
    for row in history:
        assert "trade_date" in row and "open_interest" in row and "close" in row


def test_option_chain_happy_path(tmp_db):
    """Top CE/PE strike + max pain pulled from front-expiry OPTSTK rows."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        as_of = date(2026, 4, 17)
        opt_exp = date(2026, 4, 24)
        store.upsert_fno_contracts([
            _mk_contract(trade_date=as_of, expiry_date=opt_exp,
                         instrument="FUTSTK", strike=None, option_type=None),
            _mk_contract(trade_date=as_of, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1480.0, option_type="CE",
                         open_interest=200_000),
            _mk_contract(trade_date=as_of, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1500.0, option_type="CE",
                         open_interest=600_000),  # highest CE
            _mk_contract(trade_date=as_of, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1480.0, option_type="PE",
                         open_interest=900_000),  # highest PE
            _mk_contract(trade_date=as_of, expiry_date=opt_exp,
                         instrument="OPTSTK", strike=1500.0, option_type="PE",
                         open_interest=100_000),
        ])
        api = ResearchDataAPI(store=store)
        out = api.get_option_chain_concentration("RELIANCE")
    assert out["expiry_date"] == "2026-04-24"
    assert out["call_oi_concentration"]["strike"] == 1500.0
    assert out["call_oi_concentration"]["oi"] == 600_000
    assert out["put_oi_concentration"]["strike"] == 1480.0
    assert out["put_oi_concentration"]["oi"] == 900_000
    assert out["total_ce_oi"] == 800_000
    assert out["total_pe_oi"] == 1_000_000
    # 1480 = 1.1M combined > 1500 = 700k → max pain 1480
    assert out["max_pain_strike"] == 1480.0


def test_fii_flow_happy_path(tmp_db):
    """Two days × 4 categories → newest-first list with computed net_long_pct;
    DII row excluded; idx_opt_ce/pe aggregate as long+short.
    """
    with FlowStore(db_path=tmp_db) as store:
        today = date.today()
        d1, d2 = today, today - timedelta(days=1)
        rows = []
        for d in [d1, d2]:
            rows += [
                _mk_participant(trade_date=d, instrument_category="idx_fut",
                                long_oi=120_000, short_oi=80_000),  # 60
                _mk_participant(trade_date=d, instrument_category="stk_fut",
                                long_oi=50_000, short_oi=50_000),   # 50
                _mk_participant(trade_date=d, instrument_category="idx_opt_ce",
                                long_oi=10_000, short_oi=5_000),
                _mk_participant(trade_date=d, instrument_category="idx_opt_pe",
                                long_oi=8_000, short_oi=4_000),
            ]
        rows.append(_mk_participant(trade_date=d1, participant="DII",
                                     instrument_category="idx_fut",
                                     long_oi=999_999_999, short_oi=0))
        store.upsert_fno_participant_oi(rows)
        api = ResearchDataAPI(store=store)
        out = api.get_fii_derivative_flow(days=10)
    assert len(out) == 2
    assert out[0]["trade_date"] == d1.isoformat()
    head = out[0]
    assert head["index_fut_long_oi"] == 120_000
    assert head["index_fut_net_long_pct"] == 60.0
    assert head["stock_fut_net_long_pct"] == 50.0
    assert head["index_opt_ce_oi"] == 15_000
    assert head["index_opt_pe_oi"] == 12_000


def test_fii_flow_zero_denominator_yields_none(tmp_db):
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_participant_oi([
            _mk_participant(trade_date=date.today(), instrument_category="idx_fut",
                            long_oi=0, short_oi=0),
        ])
        api = ResearchDataAPI(store=store)
        out = api.get_fii_derivative_flow(days=10)
    assert out[0]["index_fut_net_long_pct"] is None


def test_futures_basis_happy_path(tmp_db):
    """3 days futures + matching spot → 3 basis rows newest-first."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        today = date.today()
        expiry = today + timedelta(days=10)
        contracts = []
        for off, (fut, spot) in enumerate(
            [(1500.0, 1495.0), (1495.0, 1490.0), (1490.0, 1490.0)]
        ):
            td = today - timedelta(days=off)
            contracts.append(_mk_contract(
                trade_date=td, expiry_date=expiry,
                instrument="FUTSTK", strike=None, option_type=None, close=fut,
            ))
            _spot(store, "RELIANCE", td, spot)
        store.upsert_fno_contracts(contracts)
        api = ResearchDataAPI(store=store)
        out = api.get_futures_basis("RELIANCE", days=30)
    assert len(out) == 3
    assert out[0]["trade_date"] == today.isoformat()
    head = out[0]
    assert head["spot_close"] == 1495.0
    assert head["futures_close"] == 1500.0
    assert abs(head["basis_pct"] - ((1500.0 - 1495.0) / 1495.0 * 100)) < 1e-3
    assert head["expiry_date"] == expiry.isoformat()
    assert head["days_to_expiry"] == 10
    assert out[2]["basis_pct"] == 0.0  # futures == spot


def test_futures_basis_skips_when_spot_missing(tmp_db):
    """Days with futures but no spot row are silently skipped."""
    with FlowStore(db_path=tmp_db) as store:
        store.upsert_fno_universe([_mk_universe()])
        today = date.today()
        expiry = today + timedelta(days=7)
        store.upsert_fno_contracts([
            _mk_contract(trade_date=today, expiry_date=expiry,
                         instrument="FUTSTK", strike=None, option_type=None, close=1500.0),
            _mk_contract(trade_date=today - timedelta(days=1), expiry_date=expiry,
                         instrument="FUTSTK", strike=None, option_type=None, close=1495.0),
        ])
        _spot(store, "RELIANCE", today, 1495.0)
        api = ResearchDataAPI(store=store)
        out = api.get_futures_basis("RELIANCE", days=30)
    assert len(out) == 1
    assert out[0]["trade_date"] == today.isoformat()
