"""Offline tests for the SEC EDGAR client (US add-on, Phase 3.1).

All tests are fixture-backed — no network. Fixtures under
``tests/fixtures/edgar/`` are trimmed companyfacts (mapped tags only) for AAPL,
JPM, MSFT plus a small company_tickers slice.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from flowtracker.edgar_client import EdgarClient

_FIX = Path(__file__).parent.parent / "fixtures" / "edgar"


def _facts(symbol: str) -> dict:
    return json.loads((_FIX / f"companyfacts_{symbol}.json").read_text())


@pytest.fixture
def client() -> EdgarClient:
    c = EdgarClient()
    c.close()  # don't keep a live httpx client open; tests never hit the network
    return c


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

def test_pad_cik() -> None:
    assert EdgarClient.pad_cik(320193) == "0000320193"
    assert EdgarClient.pad_cik("320193") == "0000320193"
    assert EdgarClient.pad_cik("0000320193") == "0000320193"


def test_cik_for_from_local_map(client: EdgarClient) -> None:
    client.load_ticker_map_from(_FIX / "company_tickers.json")
    assert client.cik_for("AAPL") == "0000320193"
    assert client.cik_for("jpm") == "0000019617"
    assert client.cik_for("MSFT") == "0000789019"
    assert client.cik_for("NOTREAL") is None


# ---------------------------------------------------------------------------
# Annual normalization
# ---------------------------------------------------------------------------

def test_normalize_annual_aapl_fy2023(client: EdgarClient) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    by_year = {r["fiscal_year"]: r for r in rows}
    fy23 = by_year[2023]
    # Revenue ~$383B, stored in USD millions → ~383,285.
    assert 380_000 < fy23["revenue"] < 390_000
    assert fy23["net_income"] > 0
    assert fy23["total_assets"] > 0
    # EPS is per-share USD, single digits for AAPL post-split.
    assert 0 < fy23["eps"] < 20
    assert fy23["currency"] == "USD"
    assert fy23["market"] == "NASDAQ"
    assert fy23["symbol"] == "AAPL"


def test_normalize_annual_free_cash_flow_derived(client: EdgarClient) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    fy23 = next(r for r in rows if r["fiscal_year"] == 2023)
    # FCF = OCF − capex; for FY2023 AAPL it's positive and below OCF.
    assert fy23["free_cash_flow"] is not None
    assert 0 < fy23["free_cash_flow"] < fy23["operating_cash_flow"]


def test_normalize_annual_one_row_per_year(client: EdgarClient) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    years = [r["fiscal_year"] for r in rows]
    assert len(years) == len(set(years)), "restatement dedupe must keep one row per fiscal_year"


def test_normalize_annual_jpm_bank(client: EdgarClient) -> None:
    # JPM is a bank — huge assets, valid revenue/NI.
    rows = client.normalize_annual(_facts("JPM"), "JPM", market="NYSE")
    populated = [r for r in rows if r["total_assets"]]
    assert populated, "expected some JPM rows with total_assets"
    recent = max(populated, key=lambda r: r["fiscal_year"])
    assert recent["total_assets"] > 1_000_000  # >$1T in millions
    assert recent["market"] == "NYSE"


def test_normalize_annual_magnitude_is_millions(client: EdgarClient) -> None:
    # Raw companyfacts revenue is ~3.8e11; stored should be ~3.8e5 (millions).
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    fy23 = next(r for r in rows if r["fiscal_year"] == 2023)
    assert fy23["revenue"] < 1e7  # not raw USD


# ---------------------------------------------------------------------------
# Quarterly normalization
# ---------------------------------------------------------------------------

def test_normalize_quarterly_aapl(client: EdgarClient) -> None:
    rows = client.normalize_quarterly(_facts("AAPL"), "AAPL")
    assert rows
    for r in rows:
        assert r["fiscal_period"] in {"Q1", "Q2", "Q3"}
        assert r["quarter_end"]
        assert r["currency"] == "USD"
    # quarter ends are unique (restatement dedupe).
    ends = [r["quarter_end"] for r in rows]
    assert len(ends) == len(set(ends))
    # A populated quarter has single-quarter revenue (well below annual).
    with_rev = [r for r in rows if r["revenue"]]
    assert with_rev
    assert all(r["revenue"] < 200_000 for r in with_rev)


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_normalize_handles_empty_facts(client: EdgarClient) -> None:
    assert client.normalize_annual({"facts": {"us-gaap": {}}}, "X") == []
    assert client.normalize_quarterly({}, "X") == []


def test_unmapped_tag_logging_does_not_crash(client: EdgarClient, caplog) -> None:
    # Facts with a single irrelevant tag → all mapped fields unmapped, but no crash.
    facts = {"facts": {"us-gaap": {"SomeRandomTag": {"units": {"USD": []}}}}}
    with caplog.at_level(logging.INFO, logger="flowtracker.edgar_client"):
        rows = client.normalize_annual(facts, "X")
    assert rows == []
    assert any("no us-gaap tag" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Store round-trip (upsert + read back via temp-DB FlowStore)
# ---------------------------------------------------------------------------

def test_annual_rows_upsert_and_read_back(client: EdgarClient, store) -> None:
    rows = client.normalize_annual(_facts("AAPL"), "AAPL")
    # Drop partial stub years that lack the core metrics (keep DB clean).
    rows = [r for r in rows if r["revenue"] is not None]
    n = store.upsert_us_annual_financials(rows)
    assert n == len(rows)
    back = store.get_us_annual_financials("AAPL", "NASDAQ")
    assert back
    fy23 = next(r for r in back if r["fiscal_year"] == 2023)
    assert 380_000 < fy23["revenue"] < 390_000
    assert fy23["currency"] == "USD"
    # Idempotent re-upsert.
    store.upsert_us_annual_financials(rows)
    assert len(store.get_us_annual_financials("AAPL", "NASDAQ")) == len(back)


def test_quarterly_rows_upsert_and_read_back(client: EdgarClient, store) -> None:
    rows = client.normalize_quarterly(_facts("AAPL"), "AAPL")
    rows = [r for r in rows if r["revenue"] is not None]
    n = store.upsert_us_quarterly_financials(rows)
    assert n == len(rows)
    back = store.get_us_quarterly_financials("AAPL", "NASDAQ")
    assert back
    assert all(r["currency"] == "USD" for r in back)
