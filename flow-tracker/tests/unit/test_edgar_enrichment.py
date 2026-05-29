"""Offline tests for Phase 3.5b EDGAR enrichment (WS-2).

Asserts ``normalize_annual`` emits the wider native-US fields with sane values
from the re-fetched (richer) AAPL fixture, plus a store round-trip of the new
columns. All fixture-backed — no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.edgar_client import EdgarClient

_FIX = Path(__file__).parent.parent / "fixtures" / "edgar"


def _facts(symbol: str) -> dict:
    return json.loads((_FIX / f"companyfacts_{symbol}.json").read_text())


@pytest.fixture
def client() -> EdgarClient:
    c = EdgarClient()
    c.close()  # no network in tests
    return c


def test_normalize_annual_enriched_fields_aapl(client: EdgarClient) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    by_year = {r["fiscal_year"]: r for r in rows}
    fy24 = by_year[2024]

    # Core (unchanged) — revenue ~$391B in USD millions.
    assert 385_000 < fy24["revenue"] < 397_000

    # Enriched duration fields.
    assert fy24["rnd_expense"] > 0
    assert fy24["operating_profit"] > 0
    assert fy24["sga"] > 0
    assert fy24["stock_based_comp"] > 0
    assert fy24["depreciation"] > 0
    assert fy24["tax"] > 0
    assert fy24["profit_before_tax"] > 0
    # Cash flow from investing / financing present.
    assert fy24["cfi"] is not None
    assert fy24["cff"] is not None

    # Enriched instant fields.
    assert fy24["net_block"] > 0
    assert fy24["receivables"] > 0
    assert fy24["inventory"] > 0
    assert fy24["cash_and_bank"] == fy24["total_cash"]

    # borrowings is an alias of total_debt.
    assert fy24["borrowings"] == fy24["total_debt"]

    # num_shares = raw diluted count (NOT scaled to millions) → > 1e9.
    assert fy24["num_shares"] > 1e9

    # fiscal_year_end is a YYYY-MM-DD string for that fiscal year.
    fye = fy24["fiscal_year_end"]
    assert isinstance(fye, str)
    assert len(fye) == 10 and fye[4] == "-" and fye[7] == "-"
    assert fye.startswith("2024")


def test_normalize_annual_pbt_derivation_consistent(client: EdgarClient) -> None:
    """When all three are present, pbt ≈ net_income + tax (within rounding)."""
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    fy24 = next(r for r in rows if r["fiscal_year"] == 2024)
    assert abs(fy24["profit_before_tax"] - (fy24["net_income"] + fy24["tax"])) < 1.0


def test_enriched_rows_upsert_and_read_back(client: EdgarClient, store) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    rows = [r for r in rows if r["revenue"] is not None]
    store.upsert_us_annual_financials(rows)
    back = store.get_us_annual_financials("AAPL", "NASDAQ")
    fy24 = next(r for r in back if r["fiscal_year"] == 2024)

    # New columns persisted through the wider upsert + SELECT *.
    assert fy24["rnd_expense"] > 0
    assert fy24["operating_profit"] > 0
    assert fy24["net_block"] > 0
    assert fy24["num_shares"] > 1e9
    assert fy24["fiscal_year_end"].startswith("2024")
    assert fy24["borrowings"] == fy24["total_debt"]


def test_store_roundtrip_explicit_new_columns(store) -> None:
    """Upsert a hand-built row exercising every new column, read it back."""
    row = {
        "symbol": "TEST", "market": "NASDAQ", "currency": "USD",
        "fiscal_year": 2024, "fiscal_year_end": "2024-09-28",
        "revenue": 1000.0, "net_income": 200.0,
        "equity_capital": 50.0, "reserves": 300.0, "borrowings": 120.0,
        "interest": 5.0, "profit_before_tax": 250.0, "tax": 50.0,
        "operating_profit": 260.0, "depreciation": 30.0,
        "num_shares": 5_000_000_000.0, "net_block": 400.0, "cwip": 10.0,
        "cash_and_bank": 80.0, "receivables": 60.0, "inventory": 40.0,
        "other_liabilities": 70.0, "cfi": -90.0, "cff": -110.0,
        "rnd_expense": 100.0, "stock_based_comp": 25.0, "sga": 150.0,
    }
    assert store.upsert_us_annual_financials([row]) == 1
    back = store.get_us_annual_financials("TEST", "NASDAQ")
    assert len(back) == 1
    got = back[0]
    for col in (
        "fiscal_year_end", "equity_capital", "reserves", "borrowings",
        "interest", "profit_before_tax", "tax", "operating_profit",
        "depreciation", "num_shares", "net_block", "cwip", "cash_and_bank",
        "receivables", "inventory", "other_liabilities", "cfi", "cff",
        "rnd_expense", "stock_based_comp", "sga",
    ):
        assert got[col] == row[col], col


def test_quarterly_fiscal_year_from_original_filing():
    """A prior-quarter restated as a comparative in a later 10-Q carries that
    later filing's fy in SEC companyfacts. The normalizer must take fy/fp from
    the ORIGINAL 10-Q (earliest filed) while keeping the freshest value."""
    from flowtracker.edgar_client import EdgarClient

    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            # Original FY2025 Q1 10-Q (Dec-2024 quarter), filed Jan 2025.
            {"form": "10-Q", "fp": "Q1", "fy": 2025,
             "start": "2024-09-29", "end": "2024-12-28", "val": 124_300_000_000,
             "filed": "2025-01-30"},
            # Same Dec-2024 quarter restated as a comparative in the FY2026 Q1
            # 10-Q (filed Jan 2026) — SEC tags it fy=2026.
            {"form": "10-Q", "fp": "Q1", "fy": 2026,
             "start": "2024-09-29", "end": "2024-12-28", "val": 124_350_000_000,
             "filed": "2026-01-30"},
        ]}},
    }}}
    ec = EdgarClient.__new__(EdgarClient)
    rows = ec.normalize_quarterly(facts, "AAPL")
    row = next(r for r in rows if r["quarter_end"] == "2024-12-28")
    assert row["fiscal_year"] == 2025, "fy must come from the original 10-Q, not the comparative"
    assert row["fiscal_period"] == "Q1"
    assert row["revenue"] == 124_350.0, "value should be the freshest (restated) figure"
