"""Tests for `flowtracker.fno_client` — NSE F&O bhavcopy, participant OI,
option chain, and universe fetchers.

Uses respx to mock the four NSE endpoints (bhavcopy archive, participant OI
archive, option-chain API + preflight, fo_mktlots archive) with realistic
response shapes stored in `tests/fixtures/fno/`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from freezegun import freeze_time

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
@freeze_time("2026-04-17")
def test_fetch_eligible_universe_parses_csv():
    """fo_mktlots CSV → FnoUniverse rows (eligible_since/last_verified = today).

    Clock frozen so the `today` assertion stays stable as wall-clock drifts.
    """
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
