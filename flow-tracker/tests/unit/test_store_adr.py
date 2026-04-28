"""Tests for ``adr_programs`` store methods.

Round-trip: upsert → get all → get filtered by NSE symbol.
"""

from __future__ import annotations

from flowtracker.adr_models import AdrProgram
from flowtracker.store import FlowStore


def _make_programs() -> list[AdrProgram]:
    """Three programs spanning ADS/GDR and mapped/unmapped NSE symbols."""
    return [
        AdrProgram(
            nse_symbol="INFY",
            company_name="Infosys Limited",
            us_ticker="INFY",
            program_type="ADS",
            sponsorship="sponsored",
            depositary="Deutsche Bank",
            ratio="1 ADS = 1 equity share",
        ),
        AdrProgram(
            nse_symbol="ICICIBANK",
            company_name="ICICI Bank Limited",
            us_ticker="IBN",
            program_type="ADS",
            sponsorship="sponsored",
            depositary="Deutsche Bank",
            ratio="1 ADS = 2 equity shares",
        ),
        AdrProgram(
            # Unmapped NSE side — verifies NULL nse_symbol round-trip
            nse_symbol=None,
            company_name="Sify Technologies Limited",
            us_ticker="SIFY",
            program_type="ADS",
            sponsorship="sponsored",
            depositary="Citi",
            ratio="1 ADS = 1 equity share",
        ),
    ]


# ---------------------------------------------------------------------------
# upsert + get round-trip
# ---------------------------------------------------------------------------


def test_upsert_and_get_all(store: FlowStore):
    """Insert three programs then read them all back."""
    programs = _make_programs()
    count = store.upsert_adr_programs(programs)
    assert count == 3

    rows = store.get_adr_programs()
    assert len(rows) == 3
    names = {r["company_name"] for r in rows}
    assert names == {
        "Infosys Limited",
        "ICICI Bank Limited",
        "Sify Technologies Limited",
    }


def test_get_preserves_field_values(store: FlowStore):
    """All non-key fields round-trip through SQLite intact."""
    store.upsert_adr_programs([_make_programs()[0]])
    rows = store.get_adr_programs("INFY")
    assert len(rows) == 1
    row = rows[0]
    assert row["nse_symbol"] == "INFY"
    assert row["company_name"] == "Infosys Limited"
    assert row["us_ticker"] == "INFY"
    assert row["program_type"] == "ADS"
    assert row["sponsorship"] == "sponsored"
    assert row["depositary"] == "Deutsche Bank"
    assert row["ratio"] == "1 ADS = 1 equity share"
    assert row["country"] == "India"
    assert row["ingested_at"] is not None


def test_get_returns_empty_when_db_empty(store: FlowStore):
    assert store.get_adr_programs() == []
    assert store.get_adr_programs("INFY") == []


# ---------------------------------------------------------------------------
# Filter by NSE symbol
# ---------------------------------------------------------------------------


def test_filter_by_nse_symbol(store: FlowStore):
    """``get_adr_programs(nse_symbol)`` returns only matching rows."""
    store.upsert_adr_programs(_make_programs())

    infy_rows = store.get_adr_programs("INFY")
    assert len(infy_rows) == 1
    assert infy_rows[0]["company_name"] == "Infosys Limited"

    icici_rows = store.get_adr_programs("ICICIBANK")
    assert len(icici_rows) == 1
    assert icici_rows[0]["us_ticker"] == "IBN"


def test_filter_is_case_insensitive(store: FlowStore):
    """Lowercase user input still matches the uppercase stored symbol."""
    store.upsert_adr_programs(_make_programs())
    rows = store.get_adr_programs("infy")
    assert len(rows) == 1
    assert rows[0]["nse_symbol"] == "INFY"


def test_filter_no_match_returns_empty(store: FlowStore):
    store.upsert_adr_programs(_make_programs())
    assert store.get_adr_programs("NOSUCHSYMBOL") == []


def test_unmapped_program_not_returned_by_symbol_filter(store: FlowStore):
    """Programs with NULL nse_symbol surface in the all-list but never
    in a symbol-filtered query."""
    store.upsert_adr_programs(_make_programs())
    all_rows = store.get_adr_programs()
    sify = [r for r in all_rows if r["us_ticker"] == "SIFY"][0]
    assert sify["nse_symbol"] is None
    # No symbol filter can reach a NULL nse_symbol row
    assert store.get_adr_programs("SIFY") == []


# ---------------------------------------------------------------------------
# Idempotency / upsert semantics
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent(store: FlowStore):
    """Re-upserting the same row replaces (not duplicates) — PK is (company_name, us_ticker)."""
    programs = _make_programs()
    store.upsert_adr_programs(programs)
    store.upsert_adr_programs(programs)
    rows = store.get_adr_programs()
    assert len(rows) == 3


def test_upsert_overwrites_changed_fields(store: FlowStore):
    """A second upsert with different metadata replaces the prior row."""
    p_old = AdrProgram(
        nse_symbol="INFY",
        company_name="Infosys Limited",
        us_ticker="INFY",
        program_type="ADS",
        depositary="JPMorgan",  # wrong value
        ratio="1 ADS = 1 equity share",
    )
    store.upsert_adr_programs([p_old])
    p_new = AdrProgram(
        nse_symbol="INFY",
        company_name="Infosys Limited",
        us_ticker="INFY",
        program_type="ADS",
        depositary="Deutsche Bank",  # corrected
        ratio="1 ADS = 1 equity share",
    )
    store.upsert_adr_programs([p_new])
    rows = store.get_adr_programs("INFY")
    assert len(rows) == 1
    assert rows[0]["depositary"] == "Deutsche Bank"


def test_upsert_empty_list_is_noop(store: FlowStore):
    assert store.upsert_adr_programs([]) == 0
    assert store.get_adr_programs() == []
