"""Pydantic models for F&O (futures & options) ingestion pipeline.

Covers four data sources:
- Daily F&O bhavcopy (per-contract EOD: OHLC, OI, volume, settle price)
- Participant-wise OI (FII/DII/Pro/Client long+short across instrument categories)
- Live option chain snapshot (per-strike CE/PE OI/IV/volume)
- F&O-eligible symbol universe (quarterly refresh)

Units: turnover in crores, prices in ₹, OI/volume in contracts.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# F&O bhavcopy (per-contract EOD)
# ---------------------------------------------------------------------------

class FnoContractRaw(BaseModel, extra="ignore"):
    """Raw CSV row from NSE F&O bhavcopy (new 2024+ format).

    Column names match NSE's ISO-style bhavcopy header exactly. All values are
    strings pre-parsing; FnoClient converts into `FnoContract` with typed fields.
    """
    TradDt: str
    TckrSymb: str
    FinInstrmTp: str  # STF/STO/IDF/IDO
    XpryDt: str       # "YYYY-MM-DD"
    StrkPric: str = ""
    OptnTp: str = ""  # CE/PE/""
    OpnPric: str = ""
    HghPric: str = ""
    LwPric: str = ""
    ClsPric: str = ""
    SttlmPric: str = ""
    TtlTradgVol: str = ""
    TtlTrfVal: str = ""  # rupees (divide by 1e7 for crores)
    OpnIntrst: str = ""
    ChngInOpnIntrst: str = ""


class FnoContract(BaseModel):
    """Per-contract daily EOD snapshot."""
    trade_date: date
    symbol: str
    instrument: str       # FUTSTK / OPTSTK / FUTIDX / OPTIDX
    expiry_date: date
    strike: float | None = None
    option_type: str | None = None  # CE / PE / None (for futures)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    settle_price: float | None = None
    contracts_traded: int = 0
    turnover_cr: float = 0.0
    open_interest: int = 0
    change_in_oi: int = 0
    implied_volatility: float | None = None


# ---------------------------------------------------------------------------
# Participant-wise OI
# ---------------------------------------------------------------------------

class FnoParticipantOi(BaseModel):
    """Daily long/short OI for one (participant, instrument_category) bucket.

    participant: FII / DII / Pro / Client
    instrument_category: idx_fut / idx_opt_ce / idx_opt_pe / stk_fut / stk_opt_ce / stk_opt_pe
    """
    trade_date: date
    participant: str
    instrument_category: str
    long_oi: int = 0
    short_oi: int = 0
    long_turnover_cr: float | None = None
    short_turnover_cr: float | None = None


# ---------------------------------------------------------------------------
# F&O-eligible universe
# ---------------------------------------------------------------------------

class FnoUniverse(BaseModel):
    """Snapshot row for an F&O-eligible symbol."""
    symbol: str
    eligible_since: date
    last_verified: date


# ---------------------------------------------------------------------------
# Option chain (live snapshot)
# ---------------------------------------------------------------------------

class OptionChainStrike(BaseModel):
    """Per-strike CE+PE snapshot."""
    strike: float
    ce_oi: int = 0
    ce_change_oi: int = 0
    ce_volume: int = 0
    ce_iv: float | None = None
    ce_last_price: float | None = None
    pe_oi: int = 0
    pe_change_oi: int = 0
    pe_volume: int = 0
    pe_iv: float | None = None
    pe_last_price: float | None = None


class OptionChainSnapshot(BaseModel):
    """Snapshot of a stock's option chain at a point in time."""
    symbol: str
    expiry_date: date
    underlying_price: float
    fetched_at: datetime
    strikes: list[OptionChainStrike]
