"""Tests for insider_client.py — NSE insider/SAST transaction parsing."""

from __future__ import annotations

import respx

from flowtracker.insider_client import InsiderClient, _parse_int_safe, _parse_float_safe


# -- Fixture data --

_INSIDER_ITEM = {
    "symbol": "  SBIN  ",
    "acqfromDt": "20-Mar-2026",
    "tdpTransactionType": "Buy",
    "secAcq": "50000",
    "secVal": "41000000",
    "acqName": "Rajesh Kumar",
    "personCategory": "Promoters",
    "acqMode": "Market Purchase",
    "befAcqSharesPerc": "45.20",
    "afterAcqSharesPerc": "45.25",
}

_INSIDER_ITEM_SELL = {
    "symbol": "INFY",
    "acqfromDt": "15/03/2026",
    "tdpTransactionType": "Sell",
    "secAcq": "10000",
    "secVal": "14550000",
    "acqName": "Nilekani Trust",
    "personCategory": "Director",
    "acqMode": "Off Market",
    "befAcqSharesPerc": None,
    "afterAcqSharesPerc": None,
}

_INSIDER_ITEM_DISPOSAL = {
    "symbol": "TECHM",
    "acqfromDt": "10-03-2026",
    "tdpTransactionType": "",
    "secAcq": "Disposal of shares",
    "secVal": "5000000",
    "acqName": "Anish Contractor",
    "personCategory": "KMP",
    "acqMode": "",
    "befAcqSharesPerc": "0.10",
    "afterAcqSharesPerc": "0.05",
}


class TestParseIntSafe:
    """Test module-level _parse_int_safe helper."""

    def test_int_value(self):
        assert _parse_int_safe(50000) == 50000

    def test_string_int(self):
        assert _parse_int_safe("50000") == 50000

    def test_string_with_commas(self):
        assert _parse_int_safe("1,00,000") == 100000

    def test_float_string(self):
        assert _parse_int_safe("50000.75") == 50000

    def test_none_returns_zero(self):
        assert _parse_int_safe(None) == 0

    def test_garbage_returns_zero(self):
        assert _parse_int_safe("Disposal of shares") == 0

    def test_empty_string_returns_zero(self):
        assert _parse_int_safe("") == 0


class TestParseFloatSafe:
    """Test module-level _parse_float_safe helper."""

    def test_float_value(self):
        assert _parse_float_safe(45.20) == 45.20

    def test_string_float(self):
        assert _parse_float_safe("45.20") == 45.20

    def test_string_with_commas(self):
        assert _parse_float_safe("41,000,000") == 41000000.0

    def test_none_returns_none(self):
        assert _parse_float_safe(None) is None

    def test_zero_returns_none(self):
        assert _parse_float_safe(0) is None

    def test_garbage_returns_none(self):
        assert _parse_float_safe("abc") is None


class TestParseDate:
    """Test InsiderClient._parse_date static method."""

    def test_dd_mon_yyyy(self):
        assert InsiderClient._parse_date("20-Mar-2026") == "2026-03-20"

    def test_dd_mm_yyyy(self):
        assert InsiderClient._parse_date("15-03-2026") == "2026-03-15"

    def test_dd_slash_mm_yyyy(self):
        assert InsiderClient._parse_date("15/03/2026") == "2026-03-15"

    def test_yyyy_mm_dd(self):
        assert InsiderClient._parse_date("2026-03-15") == "2026-03-15"

    def test_empty_returns_none(self):
        assert InsiderClient._parse_date("") is None

    def test_whitespace_only_returns_none(self):
        assert InsiderClient._parse_date("   ") is None

    def test_unparseable_returns_none(self):
        assert InsiderClient._parse_date("not-a-date") is None


class TestParseTrade:
    """Test InsiderClient._parse_trade with fixture items."""

    def test_buy_transaction(self):
        client = InsiderClient()
        trade = client._parse_trade(_INSIDER_ITEM)
        assert trade is not None
        assert trade.symbol == "SBIN"
        assert trade.date == "2026-03-20"
        assert trade.transaction_type == "Buy"
        assert trade.person_name == "Rajesh Kumar"
        assert trade.person_category == "Promoters"
        assert trade.quantity == 50000
        assert trade.value == 4.1  # 41000000 rupees → 4.1 crores
        assert trade.mode == "Market Purchase"
        assert trade.holding_before_pct == 45.20
        assert trade.holding_after_pct == 45.25
        client.close()

    def test_sell_transaction(self):
        client = InsiderClient()
        trade = client._parse_trade(_INSIDER_ITEM_SELL)
        assert trade is not None
        assert trade.symbol == "INFY"
        assert trade.transaction_type == "Sell"
        assert trade.holding_before_pct is None
        assert trade.holding_after_pct is None
        client.close()

    def test_disposal_fallback_txn_type(self):
        """When tdpTransactionType is empty, falls back to secAcq text."""
        client = InsiderClient()
        trade = client._parse_trade(_INSIDER_ITEM_DISPOSAL)
        assert trade is not None
        assert trade.symbol == "TECHM"
        assert trade.transaction_type == "Sell"  # "Disposal" in secAcq -> "Sell"
        client.close()

    def test_missing_symbol_returns_none(self):
        client = InsiderClient()
        item = {**_INSIDER_ITEM, "symbol": "  "}
        trade = client._parse_trade(item)
        assert trade is None
        client.close()

    def test_holding_pct_with_real_nse_keys(self):
        """
        NSE's live JSON response uses 'befAcqSharesPer' / 'afterAcqSharesPer'
        (NO trailing 'c'). The parser historically read 'befAcqSharesPerc'
        / 'afterAcqSharesPerc' and silently produced NULL holding_before_pct
        and holding_after_pct for ALL 313k+ historical insider transactions.
        Verified empirically by hitting the live NSE endpoint. Keep this test
        whenever NSE's schema might shift.
        """
        client = InsiderClient()
        item = {
            "symbol": "360ONE",
            "acqfromDt": "08-Apr-2026",
            "tdpTransactionType": "Pledge",
            "secAcq": "10000",
            "secVal": "9717000",
            "acqName": "RONAK RAMESH SHETH",
            "personCategory": "Employees/Designated Employees",
            "acqMode": "Pledge Creation",
            "befAcqSharesPer": "0.03",
            "afterAcqSharesPer": "0.03",
        }
        trade = client._parse_trade(item)
        assert trade is not None
        assert trade.holding_before_pct == 0.03
        assert trade.holding_after_pct == 0.03
        client.close()

    def test_missing_date_returns_none(self):
        client = InsiderClient()
        item = {**_INSIDER_ITEM, "acqfromDt": "", "intimDt": ""}
        trade = client._parse_trade(item)
        assert trade is None
        client.close()

    def test_zero_qty_and_zero_value_returns_none(self):
        """Items with no meaningful quantity/value are skipped."""
        client = InsiderClient()
        item = {**_INSIDER_ITEM, "secAcq": "garbage", "secVal": "0"}
        trade = client._parse_trade(item)
        assert trade is None
        client.close()


class TestParseResponse:
    """Test InsiderClient._parse_response with list and dict formats."""

    def test_list_format(self):
        client = InsiderClient()
        trades = client._parse_response([_INSIDER_ITEM, _INSIDER_ITEM_SELL])
        assert len(trades) == 2
        client.close()

    def test_dict_with_data_key(self):
        client = InsiderClient()
        trades = client._parse_response({"data": [_INSIDER_ITEM]})
        assert len(trades) == 1
        client.close()

    def test_empty_list(self):
        client = InsiderClient()
        trades = client._parse_response([])
        assert trades == []
        client.close()

    def test_empty_dict(self):
        client = InsiderClient()
        trades = client._parse_response({})
        assert trades == []
        client.close()


class TestFetchRecent:
    """Test fetch with respx mock."""

    def test_fetch_recent_with_mock(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/companies-listing").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/corporates-pit").respond(
                200, json=[_INSIDER_ITEM],
            )
            with InsiderClient() as client:
                trades = client._fetch_range(
                    __import__("datetime").date(2026, 3, 20),
                    __import__("datetime").date(2026, 3, 26),
                )
            assert len(trades) == 1
            assert trades[0].symbol == "SBIN"
