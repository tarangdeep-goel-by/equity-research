"""Offline tests for the SEC EDGAR ownership parsers (US add-on, Phase 3.3).

Fixture-backed — no network. Fixtures under ``tests/fixtures/edgar/``:

* ``form4_aapl.xml`` — real AAPL Form 4 (officer, single sale).
* ``form4_aapl_director.xml`` — real AAPL Form 4 (director, 3 txns: S, S, G).
* ``13f_berkshire.xml`` — real Berkshire 13F infotable trimmed to 6 issuers
  (2026-Q1 → dollars convention; mix of mapped + unmapped CUSIPs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.edgar_ownership import (
    _normalize_13f_value,
    _value_in_thousands,
    parse_13f_infotable,
    parse_form4,
)
from flowtracker.store import FlowStore

_FIX = Path(__file__).parent.parent / "fixtures" / "edgar"


def _xml(name: str) -> str:
    return (_FIX / name).read_text()


# --------------------------------------------------------------------------- #
# Form 4 parsing
# --------------------------------------------------------------------------- #

def test_parse_form4_officer_single_sale() -> None:
    rows = parse_form4(_xml("form4_aapl.xml"), filing_date="2026-05-12")
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "AAPL"
    assert r["currency"] == "USD"
    assert r["filing_date"] == "2026-05-12"
    assert r["transaction_date"] == "2026-05-08"
    assert r["transaction_code"] == "S"
    assert r["shares"] == 1274.0
    assert r["price_per_share"] == 290.0
    assert r["value"] == pytest.approx(1274 * 290)  # shares × price
    assert r["shares_owned_after"] == 38713.0
    assert r["is_officer"] == 1
    assert r["is_director"] == 0
    assert r["owner_title"] == "Principal Accounting Officer"
    assert r["owner_name"] == "Borders Ben"


def test_parse_form4_director_multiple_transactions() -> None:
    rows = parse_form4(_xml("form4_aapl_director.xml"))
    # Three non-derivative transactions: two sales + one gift.
    assert len(rows) == 3
    codes = [r["transaction_code"] for r in rows]
    assert codes == ["S", "S", "G"]
    for r in rows:
        assert r["is_director"] == 1
        assert r["is_officer"] == 0
        assert r["owner_name"] == "LEVINSON ARTHUR D"
    # Sale has a real price → value computed; gift has price 0 → value 0.
    sale = rows[0]
    assert sale["shares"] == 149527.0
    assert sale["price_per_share"] == pytest.approx(284.57)
    assert sale["value"] == pytest.approx(149527 * 284.57)
    gift = rows[2]
    assert gift["price_per_share"] == 0.0
    assert gift["value"] == 0.0


def test_parse_form4_defaults_symbol_from_issuer() -> None:
    # No explicit symbol → falls back to issuerTradingSymbol; filing_date falls
    # back to periodOfReport.
    rows = parse_form4(_xml("form4_aapl.xml"))
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["filing_date"] == "2026-05-08"  # periodOfReport


def test_parse_form4_empty_table() -> None:
    xml = "<ownershipDocument><issuer><issuerTradingSymbol>X</issuerTradingSymbol>" \
          "</issuer></ownershipDocument>"
    assert parse_form4(xml) == []


# --------------------------------------------------------------------------- #
# 13F parsing + value magnitude convention
# --------------------------------------------------------------------------- #

def test_parse_13f_basic_holdings_and_magnitude() -> None:
    rows = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BERKSHIRE HATHAWAY INC", "2026-03-31",
    )
    assert len(rows) == 6
    by_cusip = {r["cusip"]: r for r in rows}
    # Apple: 692,000 sh, value $175,622,680 → 2026 (dollars) → /1e6 USD millions.
    aapl = by_cusip["037833100"]
    assert aapl["symbol"] == "AAPL"  # CUSIP resolved via seed map
    assert aapl["shares"] == 692000.0
    assert aapl["value_usd"] == pytest.approx(175.62268, rel=1e-4)
    assert aapl["manager_cik"] == "1067983"
    assert aapl["manager_name"] == "BERKSHIRE HATHAWAY INC"
    assert aapl["quarter_end"] == "2026-03-31"
    assert aapl["investment_discretion"] == "DFND"


def test_parse_13f_unmapped_cusip_kept_as_symbol() -> None:
    rows = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BERKSHIRE HATHAWAY INC", "2026-03-31",
    )
    by_cusip = {r["cusip"]: r for r in rows}
    # Ally Financial CUSIP is not in the validation seed map → symbol == cusip,
    # row is NOT dropped.
    ally = by_cusip["02005N100"]
    assert ally["symbol"] == "02005N100"
    assert ally["cusip"] == "02005N100"


def test_parse_13f_custom_cusip_map() -> None:
    rows = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BRK", "2026-03-31",
        cusip_map={"02005N100": "ALLY"},
    )
    ally = next(r for r in rows if r["cusip"] == "02005N100")
    assert ally["symbol"] == "ALLY"


def test_13f_value_thousands_vs_dollars_convention() -> None:
    # Pre-2023 → thousands; 2023+ → dollars.
    assert _value_in_thousands("2022-12-31") is True
    assert _value_in_thousands("2023-03-31") is False
    assert _value_in_thousands("2026-03-31") is False
    assert _value_in_thousands(None) is False
    # 100,000 reported value:
    #   thousands → 100,000 × 1e3 / 1e6 = 100 USD millions
    #   dollars   → 100,000 / 1e6       = 0.1 USD millions
    assert _normalize_13f_value(100_000, in_thousands=True) == pytest.approx(100.0)
    assert _normalize_13f_value(100_000, in_thousands=False) == pytest.approx(0.1)
    assert _normalize_13f_value(None, in_thousands=False) is None


def test_13f_pre2023_thousands_roundtrip() -> None:
    # Reparse the same fixture as if it were a 2022 period: every value_usd
    # should be 1000× larger than the 2026 (dollars) reading.
    dollars = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BRK", "2026-03-31",
    )
    thousands = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BRK", "2022-12-31",
    )
    for d, t in zip(dollars, thousands):
        assert t["value_usd"] == pytest.approx(d["value_usd"] * 1000, rel=1e-6)


# --------------------------------------------------------------------------- #
# Store round-trip (temp DB)
# --------------------------------------------------------------------------- #

def test_insider_upsert_readback(tmp_db) -> None:
    rows = parse_form4(_xml("form4_aapl_director.xml"), filing_date="2026-05-08")
    with FlowStore(db_path=tmp_db) as store:
        n = store.upsert_us_insider_transactions(rows)
        assert n == 3
        got = store.get_us_insider_transactions("AAPL")
        assert len(got) == 3
        codes = {r["transaction_code"] for r in got}
        assert codes == {"S", "G"}
        assert all(r["is_director"] == 1 for r in got)
        assert all(r["currency"] == "USD" for r in got)


def test_institutional_upsert_readback(tmp_db) -> None:
    rows = parse_13f_infotable(
        _xml("13f_berkshire.xml"), "1067983", "BERKSHIRE HATHAWAY INC", "2026-03-31",
    )
    with FlowStore(db_path=tmp_db) as store:
        n = store.upsert_us_institutional_holdings(rows)
        assert n == 6
        # AAPL resolved from CUSIP.
        aapl = store.get_us_institutional_holdings("AAPL")
        assert len(aapl) == 1
        assert aapl[0]["cusip"] == "037833100"
        assert aapl[0]["value_usd"] == pytest.approx(175.62268, rel=1e-4)
        assert aapl[0]["shares"] == 692000.0
        # Unmapped CUSIP stored under the CUSIP string as symbol.
        ally = store.get_us_institutional_holdings("02005N100")
        assert len(ally) == 1
        assert ally[0]["cusip"] == "02005N100"


# --------------------------------------------------------------------------- #
# Schedule 13D / 13G parsing (#19 beneficial ownership)
# --------------------------------------------------------------------------- #

def test_parse_13g_happy_path() -> None:
    from flowtracker.edgar_ownership import parse_schedule_13dg
    rows = parse_schedule_13dg(
        _xml("sc_13g_aapl.xml"), symbol="AAPL",
        filing_date="2026-04-29", accession="0002100119-26-000139",
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "AAPL"
    assert r["filing_type"] == "SCHEDULE 13G"
    assert r["is_activist"] == 0          # 13G = passive
    assert r["reporting_person"] == "Vanguard Capital Management"
    assert r["type_of_reporting_person"] == "IA"
    assert r["shares"] == 1_099_168_953.0
    assert r["percent_of_class"] == 7.48
    assert r["sole_voting"] == 145_321_305.0
    assert r["event_date"] == "2026-03-31"   # MM/DD/YYYY → ISO
    assert r["accession"] == "0002100119-26-000139"
    assert r["filing_date"] == "2026-04-29"


def test_parse_13d_marks_activist() -> None:
    """A SCHEDULE 13D submission type → is_activist=1."""
    from flowtracker.edgar_ownership import parse_schedule_13dg
    xml = _xml("sc_13g_aapl.xml").replace("SCHEDULE 13G", "SCHEDULE 13D")
    rows = parse_schedule_13dg(xml, symbol="AAPL")
    assert rows and rows[0]["is_activist"] == 1
    assert rows[0]["filing_type"] == "SCHEDULE 13D"


def test_parse_13dg_rejects_non_schedule_xml() -> None:
    from flowtracker.edgar_ownership import parse_schedule_13dg
    assert parse_schedule_13dg("<foo/>", symbol="X") == []
    assert parse_schedule_13dg("not xml at all", symbol="X") == []
    # A valid edgarSubmission that isn't 13D/13G is rejected.
    other = ('<edgarSubmission xmlns="http://www.sec.gov/edgar/x">'
             '<headerData><submissionType>4</submissionType></headerData></edgarSubmission>')
    assert parse_schedule_13dg(other, symbol="X") == []


def test_parse_13dg_multiple_reporting_persons() -> None:
    """Group filings list several coverPageHeaderReportingPersonDetails → one row each."""
    from flowtracker.edgar_ownership import parse_schedule_13dg
    raw = _xml("sc_13g_aapl.xml")
    # Duplicate the reporting-person block to simulate a group filing.
    start = raw.index("<coverPageHeaderReportingPersonDetails>")
    end = raw.index("</coverPageHeaderReportingPersonDetails>") + len("</coverPageHeaderReportingPersonDetails>")
    block = raw[start:end]
    second = block.replace("Vanguard Capital Management", "Vanguard Group Inc")
    raw2 = raw[:end] + second + raw[end:]
    rows = parse_schedule_13dg(raw2, symbol="AAPL", accession="acc1")
    names = {r["reporting_person"] for r in rows}
    assert names == {"Vanguard Capital Management", "Vanguard Group Inc"}
