"""Tests for `flowtracker.fno_client` — NSE F&O bhavcopy, participant OI,
option chain, and universe fetchers.

Uses respx to mock the four NSE endpoints (bhavcopy archive, participant OI
archive, option-chain API + preflight, fo_mktlots archive) with realistic
response shapes stored in `tests/fixtures/fno/`.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from flowtracker.fno_client import FnoClient, FnoFetchError


FIXTURES = Path(__file__).parent.parent / "fixtures" / "fno"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# fetch_fno_bhavcopy
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_fno_bhavcopy_parses_csv():
    """Bhavcopy CSV → FnoContract rows with correct instrument + turnover mapping."""
    trade_date = date(2026, 4, 17)
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        "BhavCopy_NSE_FO_0_0_0_20260417_F_0000.csv"
    )
    respx.get(url).respond(200, text=_read("sample_bhavcopy.csv"))

    with FnoClient() as client:
        contracts = client.fetch_fno_bhavcopy(trade_date)

    # Row 4 has empty TckrSymb and is skipped — so 3 valid rows.
    assert len(contracts) == 3

    by_sym_instr = {(c.symbol, c.instrument): c for c in contracts}
    assert ("RELIANCE", "FUTSTK") in by_sym_instr
    assert ("RELIANCE", "OPTSTK") in by_sym_instr
    assert ("NIFTY", "OPTIDX") in by_sym_instr

    futstk = by_sym_instr[("RELIANCE", "FUTSTK")]
    assert futstk.strike is None
    assert futstk.option_type is None
    assert futstk.expiry_date == date(2026, 4, 24)
    # turnover_cr = 22380000000 / 1e7 = 2238.0
    assert futstk.turnover_cr == pytest.approx(2238.0)
    assert futstk.open_interest == 12_000_000

    optstk = by_sym_instr[("RELIANCE", "OPTSTK")]
    assert optstk.strike == 1500.0
    assert optstk.option_type == "CE"

    optidx = by_sym_instr[("NIFTY", "OPTIDX")]
    assert optidx.strike == 22500.0
    assert optidx.option_type == "PE"


@respx.mock
def test_fetch_fno_bhavcopy_404_returns_empty():
    """A 404 (holiday/weekend) returns [] without raising."""
    trade_date = date(2026, 4, 17)
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        "BhavCopy_NSE_FO_0_0_0_20260417_F_0000.csv"
    )
    respx.get(url).respond(404)

    with FnoClient() as client:
        contracts = client.fetch_fno_bhavcopy(trade_date)

    assert contracts == []


@respx.mock
def test_fetch_fno_bhavcopy_skips_empty_ticker_rows():
    """Rows with blank TckrSymb are skipped silently."""
    trade_date = date(2026, 4, 17)
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        "BhavCopy_NSE_FO_0_0_0_20260417_F_0000.csv"
    )
    respx.get(url).respond(200, text=_read("sample_bhavcopy.csv"))

    with FnoClient() as client:
        contracts = client.fetch_fno_bhavcopy(trade_date)

    # No contract should have an empty symbol, even though the CSV has such a row.
    assert all(c.symbol for c in contracts)
    assert len(contracts) == 3  # 4 data rows - 1 empty-ticker row


# Strike validation: OPTSTK/OPTIDX must have a strike; futures may omit it.

_BHAV_URL = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_20260417_F_0000.csv"
)
_BHAV_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,"
    "LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
    "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,"
    "Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)


def _bhav_csv(instr: str, strike: str, optn: str) -> str:
    row = (
        f"2026-04-17,2026-04-17,FO,NSE,{instr},1,INE002A01018,RELIANCE,EQ,"
        f"2026-04-24,2026-04-24,{strike},{optn},X,20,25,18,20,20,22,"
        f"1491.30,0,200000,10000,5000,100000000,200,FO,250,,,,,"
    )
    return f"{_BHAV_HEADER}\n{row}\n"


@respx.mock
def test_bhavcopy_optstk_missing_strike_raises():
    """OPTSTK row with empty StrkPric must raise FnoFetchError identifying the row."""
    respx.get(_BHAV_URL).respond(200, text=_bhav_csv("STO", "", "CE"))

    with FnoClient() as client, pytest.raises(FnoFetchError) as exc_info:
        client.fetch_fno_bhavcopy(date(2026, 4, 17))

    msg = str(exc_info.value).lower()
    assert "strike" in msg and "reliance" in msg and "2026-04-24" in msg


@respx.mock
def test_bhavcopy_optstk_valid_strike_parses():
    """OPTSTK row with StrkPric='1500.0' parses correctly with strike=1500.0."""
    respx.get(_BHAV_URL).respond(200, text=_bhav_csv("STO", "1500.0", "CE"))

    with FnoClient() as client:
        contracts = client.fetch_fno_bhavcopy(date(2026, 4, 17))

    assert len(contracts) == 1
    assert contracts[0].instrument == "OPTSTK"
    assert contracts[0].strike == 1500.0
    assert contracts[0].option_type == "CE"


@respx.mock
def test_bhavcopy_futstk_missing_strike_parses_as_none():
    """FUTSTK row with empty StrkPric is legal — strike stays None (no regression)."""
    respx.get(_BHAV_URL).respond(200, text=_bhav_csv("STF", "", ""))

    with FnoClient() as client:
        contracts = client.fetch_fno_bhavcopy(date(2026, 4, 17))

    assert len(contracts) == 1
    assert contracts[0].instrument == "FUTSTK"
    assert contracts[0].strike is None
    assert contracts[0].option_type is None


# ---------------------------------------------------------------------------
# fetch_participant_oi
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_participant_oi_parses_csv():
    """4 participants × 6 instrument categories = 24 rows."""
    trade_date = date(2026, 4, 17)
    url = (
        "https://archives.nseindia.com/content/nsccl/"
        "fao_participant_oi_17042026.csv"
    )
    respx.get(url).respond(200, text=_read("sample_participant_oi.csv"))

    with FnoClient() as client:
        rows = client.fetch_participant_oi(trade_date)

    assert len(rows) == 24  # 4 × 6

    participants = {r.participant for r in rows}
    assert participants == {"Client", "FII", "DII", "Pro"}

    categories_per_participant = {
        p: {r.instrument_category for r in rows if r.participant == p}
        for p in participants
    }
    expected_categories = {
        "idx_fut", "idx_opt_ce", "idx_opt_pe",
        "stk_fut", "stk_opt_ce", "stk_opt_pe",
    }
    for p, cats in categories_per_participant.items():
        assert cats == expected_categories, f"{p} missing categories: {expected_categories - cats}"

    # Spot-check a numeric mapping: FII Future Stock Long = 5_500_000, Short = 4_400_000
    fii_stk_fut = next(
        r for r in rows if r.participant == "FII" and r.instrument_category == "stk_fut"
    )
    assert fii_stk_fut.long_oi == 5_500_000
    assert fii_stk_fut.short_oi == 4_400_000

    # All rows should carry the supplied trade_date
    assert all(r.trade_date == trade_date for r in rows)


@respx.mock
def test_fetch_participant_oi_404_returns_empty():
    trade_date = date(2026, 4, 17)
    url = (
        "https://archives.nseindia.com/content/nsccl/"
        "fao_participant_oi_17042026.csv"
    )
    respx.get(url).respond(404)

    with FnoClient() as client:
        rows = client.fetch_participant_oi(trade_date)

    assert rows == []


# ---------------------------------------------------------------------------
# fetch_eligible_universe
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_eligible_universe_parses_csv():
    """fo_mktlots CSV → FnoUniverse rows (eligible_since/last_verified = today)."""
    url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
    respx.get(url).respond(200, text=_read("sample_fo_mktlots.csv"))

    with FnoClient() as client:
        universe = client.fetch_eligible_universe()

    symbols = {u.symbol for u in universe}
    assert symbols == {"RELIANCE", "TCS", "INFY"}

    today = date.today()
    for u in universe:
        assert u.eligible_since == today
        assert u.last_verified == today


# ---------------------------------------------------------------------------
# fetch_option_chain
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_option_chain_filters_to_nearest_expiry():
    """Snapshot filters to expiryDates[0] and decodes CE/PE fields correctly."""
    respx.get("https://www.nseindia.com/option-chain").respond(200, text="<html>ok</html>")
    respx.get(
        "https://www.nseindia.com/api/option-chain-equities",
        params={"symbol": "RELIANCE"},
    ).respond(200, text=_read("sample_option_chain.json"))

    with FnoClient() as client:
        snap = client.fetch_option_chain("RELIANCE")

    assert snap.symbol == "RELIANCE"
    assert snap.expiry_date == date(2026, 4, 24)
    assert snap.underlying_price == pytest.approx(1491.3)

    # 3 strikes on 24-Apr; the 29-May row must be filtered out.
    assert len(snap.strikes) == 3
    strikes_by_price = {s.strike: s for s in snap.strikes}
    assert set(strikes_by_price.keys()) == {1400.0, 1500.0, 1600.0}

    atm = strikes_by_price[1500.0]
    assert atm.ce_oi == 300_000
    assert atm.ce_change_oi == 15_000
    assert atm.ce_volume == 5_000
    assert atm.ce_iv == pytest.approx(24.0)
    assert atm.ce_last_price == pytest.approx(20.0)
    assert atm.pe_oi == 250_000
    assert atm.pe_iv == pytest.approx(26.0)
    assert atm.pe_last_price == pytest.approx(35.0)


@respx.mock
def test_fetch_option_chain_calls_preflight():
    """Preflight is hit before the /api/option-chain-equities call."""
    preflight = respx.get("https://www.nseindia.com/option-chain").respond(
        200, text="<html>ok</html>"
    )
    api = respx.get(
        "https://www.nseindia.com/api/option-chain-equities",
        params={"symbol": "RELIANCE"},
    ).respond(200, text=_read("sample_option_chain.json"))

    with FnoClient() as client:
        client.fetch_option_chain("RELIANCE")

    assert preflight.called
    assert api.called
    # Preflight must have been called at least once before the API.
    assert preflight.call_count >= 1
    assert api.call_count == 1


@respx.mock
def test_retry_refreshes_cookies_on_403():
    """A 403 response triggers a cookie refresh before the retry."""
    preflight = respx.get("https://www.nseindia.com/option-chain").respond(
        200, text="<html>ok</html>"
    )
    # First call 403, second call 200 with valid JSON.
    api = respx.get(
        "https://www.nseindia.com/api/option-chain-equities",
        params={"symbol": "RELIANCE"},
    ).mock(
        side_effect=[
            httpx.Response(403),
            httpx.Response(200, text=_read("sample_option_chain.json")),
        ]
    )

    with FnoClient() as client:
        snap = client.fetch_option_chain("RELIANCE")

    # Preflight called at least twice: once initial, once after 403.
    assert preflight.call_count >= 2
    assert api.call_count == 2
    assert snap.symbol == "RELIANCE"


@respx.mock
def test_retry_gives_up_after_max_attempts(monkeypatch):
    """3 × 500 responses exhaust retries and raise FnoFetchError."""
    # Skip exponential backoff so the test is fast.
    monkeypatch.setattr("flowtracker.fno_client.time.sleep", lambda *_: None)

    trade_date = date(2026, 4, 17)
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        "BhavCopy_NSE_FO_0_0_0_20260417_F_0000.csv"
    )
    respx.get(url).respond(500)

    with FnoClient() as client:
        with pytest.raises(FnoFetchError):
            client.fetch_fno_bhavcopy(trade_date)


def test_context_manager_closes_client():
    """Exiting the `with` block closes the underlying httpx.Client."""
    with FnoClient() as client:
        inner = client._client
        assert not inner.is_closed
    assert inner.is_closed


# ---------------------------------------------------------------------------
# Format-fallback + column-count fragility fixes (PR-5)
# ---------------------------------------------------------------------------


@respx.mock
def test_option_chain_parses_short_year_expiry():
    """`"17-Apr-26"` (2-digit year) is parsed via the `%d-%b-%y` fallback."""
    payload = {
        "records": {
            "expiryDates": ["17-Apr-26"],
            "underlyingValue": 1500.0,
            "data": [
                {
                    "strikePrice": 1500,
                    "expiryDate": "17-Apr-26",
                    "CE": {"openInterest": 100, "changeinOpenInterest": 0,
                           "totalTradedVolume": 0, "impliedVolatility": 20.0,
                           "lastPrice": 10.0},
                    "PE": {"openInterest": 100, "changeinOpenInterest": 0,
                           "totalTradedVolume": 0, "impliedVolatility": 22.0,
                           "lastPrice": 12.0},
                },
            ],
        }
    }
    respx.get("https://www.nseindia.com/option-chain").respond(200, text="<html>ok</html>")
    respx.get(
        "https://www.nseindia.com/api/option-chain-equities",
        params={"symbol": "RELIANCE"},
    ).respond(200, text=json.dumps(payload))

    with FnoClient() as client:
        snap = client.fetch_option_chain("RELIANCE")

    assert snap.expiry_date == date(2026, 4, 17)
    assert len(snap.strikes) == 1


@respx.mock
def test_participant_oi_logs_warning_on_column_mismatch(caplog):
    """A CSV with a missing participant column logs a warning and marks the affected
    category's long/short OI as None rather than silently zero-filling."""
    trade_date = date(2026, 4, 17)
    url = (
        "https://archives.nseindia.com/content/nsccl/"
        "fao_participant_oi_17042026.csv"
    )

    # Drop the two "Option Stock Put" columns → header has 11 per-category cols
    # instead of 12 (6 categories × 2). Parser should WARN + leave stk_opt_pe
    # long_oi/short_oi as None, other categories still parse normally.
    bad_csv = (
        "NSE - NSCCL\n"
        "Participant wise Open Interest\n"
        "Date: 17-Apr-2026\n"
        "\n"
        "Client Type,Future Index Long,Future Index Short,"
        "Option Index Call Long,Option Index Put Long,"
        "Option Index Call Short,Option Index Put Short,"
        "Future Stock Long,Future Stock Short,"
        "Option Stock Call Long,Option Stock Call Short,"
        "Total Long Contracts,Total Short Contracts\n"
        "FII,1000,2000,3000,4000,5000,6000,7000,8000,9000,10000,20000,25000\n"
    )
    respx.get(url).respond(200, text=bad_csv)

    with caplog.at_level(logging.WARNING, logger="flowtracker.fno_client"):
        with FnoClient() as client:
            rows = client.fetch_participant_oi(trade_date)

    # A WARNING about column mismatch must have been emitted.
    assert any(
        "column" in rec.message.lower() and rec.levelno == logging.WARNING
        for rec in caplog.records
    ), f"expected column-mismatch warning, got: {[r.message for r in caplog.records]}"

    # Parser still yielded 6 rows (one per category) — no raise.
    assert len(rows) == 6
    by_cat = {r.instrument_category: r for r in rows}

    # Known/matched categories keep real values.
    assert by_cat["stk_fut"].long_oi == 7000
    assert by_cat["stk_fut"].short_oi == 8000

    # Unmatched category (stk_opt_pe) is marked None, NOT zero-filled.
    assert by_cat["stk_opt_pe"].long_oi is None
    assert by_cat["stk_opt_pe"].short_oi is None
