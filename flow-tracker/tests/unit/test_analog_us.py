"""US historical-analog cohort tests (#17 — market-aware fingerprint).

Covers: US feature-vector shape (valuation/quality/momentum/size; ownership
dims null), USD mcap buckets, computed PE-percentile, market-isolated z-score
stats, US forward returns, and market-isolated retrieval. India behavior is
exercised by test_analog_builder.py and must stay byte-identical.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.store import FlowStore


@pytest.fixture
def store(tmp_db) -> FlowStore:
    s = FlowStore(db_path=tmp_db)
    yield s
    s.close()


def _seed_us_prices(store: FlowStore, symbol: str, n_days: int, start: str,
                    base: float = 100.0, step: float = 0.1) -> None:
    """Seed n_days of consecutive us_daily_prices (rising) from `start`."""
    d0 = date.fromisoformat(start)
    rows = []
    for i in range(n_days):
        d = (d0 + timedelta(days=i)).isoformat()
        px = base + i * step
        rows.append({"symbol": symbol, "market": "NASDAQ", "date": d,
                     "open": px, "high": px + 1, "low": px - 1, "close": px,
                     "volume": 1_000_000, "adj_close": px})
    store.upsert_us_daily_prices(rows)


def _seed_us_annuals(store: FlowStore, symbol: str, years: list[int],
                     eps: float = 5.0, rev: float = 1000.0) -> None:
    rows = []
    for i, y in enumerate(years):
        rows.append({"symbol": symbol, "market": "NASDAQ", "currency": "USD",
                     "fiscal_year": y, "fiscal_year_end": f"{y}-12-31",
                     "revenue": rev * (1.1 ** i), "net_income": rev * 0.2,
                     "operating_profit": rev * 0.3 * (1.05 ** i), "eps": eps,
                     "total_equity": 2000.0, "total_debt": 500.0,
                     "shares_outstanding": 1_000_000_000})
    store.upsert_us_annual_financials(rows)


def _seed_hist_state(store: FlowStore, symbol: str, qtr: str, market: str,
                     industry: str, mcap: str, pe: float, roce: float) -> None:
    store._conn.execute(
        "INSERT OR REPLACE INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, industry, mcap_bucket, market) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (symbol, qtr, pe, roce, industry, mcap, market),
    )
    store._conn.execute(
        "INSERT OR REPLACE INTO analog_forward_returns "
        "(symbol, as_of_date, return_12m_pct, outcome_label, market) VALUES (?, ?, ?, ?, ?)",
        (symbol, qtr, 25.0, "recovered", market),
    )
    store._conn.commit()


class TestUsFeatureVector:
    def test_us_fingerprint_shape(self, store: FlowStore):
        from flowtracker.research.analog_builder import compute_feature_vector
        store.upsert_symbol_registry("ZZUS", "NASDAQ", company_name="Z", cik="1",
                                     sector="Technology", industry="Semiconductors")
        # ~10yr of daily bars so PE-percentile (close at each FY-end) AND
        # SMA200 (200 most-recent bars) both have inputs.
        _seed_us_prices(store, "ZZUS", 3700, "2016-06-01", base=100.0, step=0.02)
        _seed_us_annuals(store, "ZZUS", list(range(2016, 2026)))
        v = compute_feature_vector(store, "ZZUS", "2026-05-31", market="NASDAQ")
        # Valuation + quality + momentum + size present
        assert v["pe_trailing"] is not None
        assert v["pe_percentile_10y"] is not None  # >=8 annual PE points
        assert v["roce_current"] is not None
        assert v["revenue_cagr_3yr"] is not None
        assert v["opm_trend"] is not None
        assert v["price_vs_sma200"] is not None     # 260 bars >= 200
        assert v["rsi_14"] is not None
        assert v["mcap_bucket"] == "largecap"        # 1e9 sh × ~$200 = $200bn
        assert v["industry"] == "Semiconductors"
        # India-only ownership/flow dims are null for a US listing
        for k in ("promoter_pct", "fii_pct", "fii_delta_2q", "mf_pct",
                  "mf_delta_2q", "pledge_pct", "delivery_pct_6m"):
            assert v[k] is None, k

    def test_usd_mcap_buckets(self, store: FlowStore):
        from flowtracker.research.analog_builder import _us_mcap_bucket
        # 1e9 shares × $100 = $100bn → largecap
        store.upsert_symbol_registry("BIGUS", "NASDAQ", cik="2")
        _seed_us_prices(store, "BIGUS", 5, "2026-05-20", base=100.0, step=0.0)
        _seed_us_annuals(store, "BIGUS", [2025])
        assert _us_mcap_bucket(store, "BIGUS", "2026-05-31") == "largecap"

    def test_pe_percentile_needs_8_years(self, store: FlowStore):
        from flowtracker.research.analog_builder import _us_pe_percentile
        store.upsert_symbol_registry("FEWUS", "NASDAQ", cik="3")
        _seed_us_prices(store, "FEWUS", 30, "2026-04-01")
        _seed_us_annuals(store, "FEWUS", [2024, 2025])  # only 2 yrs
        assert _us_pe_percentile(store, "FEWUS", "2026-05-31") is None


class TestMarketIsolation:
    def test_universe_stds_market_scoped(self, store: FlowStore):
        from flowtracker.research.analog_builder import _universe_stds
        # India rows with huge PE spread; US rows tight — US stds must ignore India.
        _seed_hist_state(store, "INDA", "2024-03-31", "NSE", "Banks", "largecap", 5.0, 10.0)
        _seed_hist_state(store, "INDB", "2024-03-31", "NSE", "Banks", "largecap", 500.0, 10.0)
        _seed_hist_state(store, "USA1", "2024-03-31", "NASDAQ", "Semiconductors", "largecap", 20.0, 30.0)
        _seed_hist_state(store, "USA2", "2024-03-31", "NASDAQ", "Semiconductors", "largecap", 22.0, 31.0)
        us_std = _universe_stds(store, market="NASDAQ")["pe_trailing"]
        in_std = _universe_stds(store, market="NSE")["pe_trailing"]
        assert us_std < 5.0           # tight US spread (20 vs 22)
        assert in_std > 100.0         # wide India spread (5 vs 500)

    def test_retrieval_market_scoped(self, store: FlowStore):
        from flowtracker.research.analog_builder import retrieve_top_k_analogs
        # Seed both an India and a US cohort in the same industry+bucket.
        for s in ("USX1", "USX2", "USX3", "USX4", "USX5", "USX6"):
            _seed_hist_state(store, s, "2023-06-30", "NASDAQ", "Semiconductors", "largecap", 21.0, 30.0)
        for s in ("INX1", "INX2", "INX3"):
            _seed_hist_state(store, s, "2023-06-30", "NSE", "Semiconductors", "largecap", 21.0, 30.0)
        target = {"pe_trailing": 21.0, "roce_current": 30.0,
                  "industry": "Semiconductors", "mcap_bucket": "largecap"}
        out = retrieve_top_k_analogs(store, "TGT", "2026-05-31", target, k=20, market="NASDAQ")
        markets = {a["symbol"] for a in out["analogs"]}
        assert markets and all(m.startswith("USX") for m in markets)  # only US cohort


class TestUsForwardReturns:
    def test_us_forward_returns_from_us_prices(self, store: FlowStore):
        from flowtracker.research.analog_builder import compute_forward_returns
        store.upsert_symbol_registry("RETUS", "NASDAQ", cik="9")
        # 400 consecutive rising days: 12m-fwd return is strongly positive.
        _seed_us_prices(store, "RETUS", 400, "2024-01-01", base=100.0, step=0.5)
        r = compute_forward_returns(store, "RETUS", "2024-02-01", market="NASDAQ")
        assert r["return_3m_pct"] is not None and r["return_3m_pct"] > 0
        assert r["return_12m_pct"] is not None and r["return_12m_pct"] > 0
        assert r["outcome_label"] == "recovered"
        # US excess-vs-sector / vs-index are null in the first cut.
        assert r["excess_12m_vs_nifty"] is None
        assert r["excess_12m_vs_sector"] is None
