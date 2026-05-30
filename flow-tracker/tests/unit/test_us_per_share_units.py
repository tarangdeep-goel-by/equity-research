"""US per-share unit correctness (currency/conversion regression).

Stored monetary aggregates differ by market: India in CRORES (×1e7 → rupees),
US in USD MILLIONS (×1e6 → dollars). ``num_shares`` is a raw count in both.
Several per-share computations historically hardcoded the India ×1e7 factor,
which inflated every US per-share figure ~10x (BVPS, reverse-DCF implied price,
adjusted book value). ``ResearchDataAPI._agg_per_share_factor`` now selects the
right factor by market; these tests pin the unit-correct US numbers and assert
the India path is unchanged.
"""

import pytest

from flowtracker.store import FlowStore
from flowtracker.research.data_api import ResearchDataAPI, _run_market

US_MARKET = "NASDAQ"


def _seed_us_financials(store, symbol, market, *, equity_capital, reserves,
                        total_assets, borrowings, other_liabilities,
                        num_shares, price):
    """Seed a US symbol with deterministic USD-millions financials (3 FYs)."""
    store.upsert_symbol_registry(
        symbol, market, company_name=f"{symbol} Inc.",
        sector="Technology", gics="Technology", cik="000000",
    )
    rows = []
    for i, fy in enumerate((2024, 2023, 2022)):
        rows.append({
            "symbol": symbol, "market": market, "currency": "USD",
            "fiscal_year": fy, "fiscal_year_end": f"{fy}-12-31",
            "revenue": 100_000.0 - i * 5_000.0,
            "net_income": 20_000.0 - i * 1_000.0,
            "eps": 5.0, "operating_cash_flow": 25_000.0 - i * 1_000.0,
            "free_cash_flow": 22_000.0, "operating_profit": 24_000.0,
            "profit_before_tax": 23_000.0, "tax": 4_000.0,
            "depreciation": 3_000.0, "interest": 0.0,
            "total_assets": total_assets, "total_equity": equity_capital + reserves,
            "equity_capital": equity_capital, "reserves": reserves,
            "total_debt": borrowings, "borrowings": borrowings,
            "total_cash": 30_000.0, "cash_and_bank": 30_000.0,
            "net_block": 40_000.0, "receivables": 5_000.0, "inventory": 2_000.0,
            "other_liabilities": other_liabilities, "cwip": 0.0,
            "num_shares": num_shares, "shares_outstanding": num_shares,
            "cfi": -2_000.0, "cff": -5_000.0,
            "rnd_expense": 8_000.0, "stock_based_comp": 2_000.0, "sga": 10_000.0,
        })
    store.upsert_us_annual_financials(rows)
    store.upsert_us_valuation_snapshot([{
        "symbol": symbol, "market": market, "currency": "USD",
        "date": "2025-05-29", "price": price, "market_cap": price * num_shares / 1e6,
        "pe_trailing": 20.0, "roe": 25.0,
    }])


@pytest.fixture
def api(tmp_path, monkeypatch):
    db = tmp_path / "units.db"
    monkeypatch.setenv("FLOWTRACKER_DB", str(db))
    with FlowStore(db_path=db) as store:
        _seed_us_financials(
            store, "USTEST", US_MARKET,
            equity_capital=50_000.0, reserves=0.0,
            total_assets=100_000.0, borrowings=40_000.0, other_liabilities=20_000.0,
            num_shares=1_000_000_000.0, price=200.0,
        )
    token = _run_market.set(US_MARKET)
    a = ResearchDataAPI()
    try:
        yield a
    finally:
        a.close()
        _run_market.reset(token)


# --------------------------------------------------------------------------- #
# Factor helper
# --------------------------------------------------------------------------- #

def test_factor_is_millions_for_us(api):
    assert api._agg_per_share_factor("USTEST") == 1e6


def test_factor_is_crores_for_india(tmp_path, monkeypatch):
    # Outside any US run-context, an India symbol resolves NSE → ×1e7.
    db = tmp_path / "india.db"
    monkeypatch.setenv("FLOWTRACKER_DB", str(db))
    with FlowStore(db_path=db):
        pass
    a = ResearchDataAPI()  # no run-market override set
    try:
        assert a._agg_per_share_factor("SBIN") == 1e7
    finally:
        a.close()


# --------------------------------------------------------------------------- #
# Sector BVPS / adjusted-BV — exact USD values (would be 10x with the old ×1e7)
# --------------------------------------------------------------------------- #

def test_us_realestate_adjusted_bv_not_inflated(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda s: "Real Estate - Development")
    res = api.get_realestate_metrics("USTEST")
    years = res["years"]
    # (assets 100,000 − borrowings 40,000 − other_liab 20,000) $mn = 40,000 $mn
    # ÷ 1e9 shares × 1e6 = $40.00/sh.  Old ×1e7 would give $400.00.
    assert years[0]["adjusted_bv_per_share"] == pytest.approx(40.0, abs=0.01)


def test_us_bfsi_bvps_not_inflated(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda s: "Banks - Diversified")
    res = api.get_bfsi_metrics("USTEST")
    years = res["years"]
    # net_worth = equity_capital 50,000 + reserves 0 = 50,000 $mn
    # ÷ 1e9 shares × 1e6 = $50.00/sh.  Old ×1e7 would give $500.00.
    assert years[0]["book_value_per_share"] == pytest.approx(50.0, abs=0.01)


def test_us_insurance_bvps_not_inflated(api, monkeypatch):
    monkeypatch.setattr(api, "_get_industry", lambda s: "Insurance - Property & Casualty")
    res = api.get_insurance_metrics("USTEST")
    years = res["years"]
    assert years[0]["book_value_per_share"] == pytest.approx(50.0, abs=0.01)


# --------------------------------------------------------------------------- #
# Reverse DCF — differential proof the factor flows through both sites
# --------------------------------------------------------------------------- #

def test_us_reverse_dcf_factor_flows_through(api, monkeypatch):
    """With the US (1e6) factor, every implied price is exactly 1/10 of what the
    old India (1e7) factor produced on identical data — proving the bug is fixed
    at both sensitivity sites."""
    # Stub WACC so the test stays offline (real get_wacc_params hits yfinance).
    monkeypatch.setattr(api, "get_wacc_params",
                        lambda s: {"ke": 0.10, "wacc": 0.10, "terminal_growth": 0.04})
    us = api.get_reverse_dcf("USTEST")
    assert "sensitivity" in us and us["sensitivity"], us
    us_prices = [c["implied_price"] for c in us["sensitivity"] if c["implied_price"]]
    assert us_prices, "expected non-null implied prices"

    monkeypatch.setattr(api, "_agg_per_share_factor", lambda s: 1e7)
    india_factor = api.get_reverse_dcf("USTEST")
    in_prices = [c["implied_price"] for c in india_factor["sensitivity"] if c["implied_price"]]

    assert len(us_prices) == len(in_prices)
    # Each US price is 1/10 of the India-factor price (allowing 2-dp rounding on
    # both independently-rounded values).
    for u, i in zip(us_prices, in_prices):
        assert u == pytest.approx(i / 10, abs=0.02)
