"""Unit tests for F&O Pydantic models (Sprint 2).

Covers: FnoContractRaw, FnoContract, FnoParticipantOi, FnoUniverse,
OptionChainStrike, OptionChainSnapshot.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from flowtracker.fno_models import (
    FnoContract,
    FnoContractRaw,
    FnoParticipantOi,
    FnoUniverse,
    OptionChainSnapshot,
    OptionChainStrike,
)


def test_fno_contract_raw_ignores_unknown_columns():
    """FnoContractRaw should silently ignore unknown CSV columns (extra='ignore')."""
    raw = FnoContractRaw(
        TradDt="2026-04-17",
        TckrSymb="RELIANCE",
        FinInstrmTp="STF",
        XpryDt="2026-04-24",
        ExtraJunk="ignored",
    )
    assert raw.TradDt == "2026-04-17"
    assert raw.TckrSymb == "RELIANCE"
    assert raw.FinInstrmTp == "STF"
    assert raw.XpryDt == "2026-04-24"
    # Extra field is dropped, not stored
    assert not hasattr(raw, "ExtraJunk")


def test_fno_contract_future_has_none_strike():
    """FUTSTK row constructed with strike=None and option_type=None preserves both."""
    c = FnoContract(
        trade_date=date(2026, 4, 17),
        symbol="RELIANCE",
        instrument="FUTSTK",
        expiry_date=date(2026, 4, 24),
        strike=None,
        option_type=None,
        close=1490.0,
    )
    assert c.strike is None
    assert c.option_type is None
    assert c.instrument == "FUTSTK"


def test_fno_contract_option_has_strike_and_type():
    """OPTSTK row accepts numeric strike + CE/PE option_type."""
    c = FnoContract(
        trade_date=date(2026, 4, 17),
        symbol="RELIANCE",
        instrument="OPTSTK",
        expiry_date=date(2026, 4, 24),
        strike=1500.0,
        option_type="CE",
    )
    assert c.strike == 1500.0
    assert c.option_type == "CE"
    # Defaults for unspecified numeric fields
    assert c.contracts_traded == 0
    assert c.turnover_cr == 0.0
    assert c.open_interest == 0
    assert c.change_in_oi == 0
    assert c.implied_volatility is None


def test_fno_participant_oi_defaults():
    """FnoParticipantOi: long/short OI default to 0, turnover fields default to None."""
    p = FnoParticipantOi(
        trade_date=date(2026, 4, 17),
        participant="FII",
        instrument_category="stk_fut",
    )
    assert p.long_oi == 0
    assert p.short_oi == 0
    assert p.long_turnover_cr is None
    assert p.short_turnover_cr is None


def test_fno_universe_requires_all_dates():
    """FnoUniverse fails validation if eligible_since or last_verified missing."""
    # Missing eligible_since
    with pytest.raises(ValidationError):
        FnoUniverse(symbol="RELIANCE", last_verified=date(2026, 4, 17))
    # Missing last_verified
    with pytest.raises(ValidationError):
        FnoUniverse(symbol="RELIANCE", eligible_since=date(2020, 1, 1))


def test_option_chain_strike_defaults():
    """OptionChainStrike with only `strike`: OI/vol fields default to 0, IV/last to None."""
    s = OptionChainStrike(strike=1500.0)
    assert s.strike == 1500.0
    assert s.ce_oi == 0
    assert s.ce_change_oi == 0
    assert s.ce_volume == 0
    assert s.pe_oi == 0
    assert s.pe_change_oi == 0
    assert s.pe_volume == 0
    assert s.ce_iv is None
    assert s.ce_last_price is None
    assert s.pe_iv is None
    assert s.pe_last_price is None


def test_option_chain_snapshot_composition():
    """OptionChainSnapshot composes a list of OptionChainStrike rows."""
    snap = OptionChainSnapshot(
        symbol="RELIANCE",
        expiry_date=date(2026, 4, 24),
        underlying_price=1485.0,
        fetched_at=datetime(2026, 4, 17, 15, 30),
        strikes=[
            OptionChainStrike(strike=1480.0, ce_oi=1000, pe_oi=2000),
            OptionChainStrike(strike=1500.0, ce_oi=1500, pe_oi=2500),
        ],
    )
    assert len(snap.strikes) == 2
    assert snap.strikes[0].strike == 1480.0
    assert snap.strikes[1].pe_oi == 2500
    assert snap.underlying_price == 1485.0


def test_fno_contract_raw_all_fields_populated():
    """Full FnoContractRaw round-trip — all fields stay as strings via model_dump."""
    raw = FnoContractRaw(
        TradDt="2026-04-17",
        TckrSymb="RELIANCE",
        FinInstrmTp="STO",
        XpryDt="2026-04-24",
        StrkPric="1500.00",
        OptnTp="CE",
        OpnPric="25.5",
        HghPric="30.0",
        LwPric="20.0",
        ClsPric="28.0",
        SttlmPric="28.5",
        TtlTradgVol="123456",
        TtlTrfVal="1234567890",
        OpnIntrst="500000",
        ChngInOpnIntrst="10000",
    )
    dumped = raw.model_dump()
    # Every value remains a string (raw CSV row, no type coercion at this layer)
    for value in dumped.values():
        assert isinstance(value, str)
    assert dumped["TckrSymb"] == "RELIANCE"
    assert dumped["StrkPric"] == "1500.00"
    assert dumped["OptnTp"] == "CE"
    assert dumped["OpnIntrst"] == "500000"
