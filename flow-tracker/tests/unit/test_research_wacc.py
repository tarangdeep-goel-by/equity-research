"""Tests for research/wacc.py — beta, CoE, CoD, WACC, terminal growth.

Regression coverage for the BFSI/insurance-Beta-null bug where compute-analytics.py
crashed on `cost_of_debt is None` and clobbered beta_blume/beta_raw/beta_r_squared
for every banking & insurance stock (HDFCLIFE, SBIN, HDFCBANK, ICICIBANK, etc.).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from flowtracker.market import Market
from flowtracker.research.wacc import (
    INDIA_ERP,
    STATUTORY_TAX_RATE,
    US_ERP,
    US_STATUTORY_TAX_RATE,
    SMALL_CAP_THRESHOLD_CR,
    beta_index_symbol,
    build_wacc_params,
    compute_cost_of_debt,
    compute_cost_of_equity,
    compute_nifty_beta,
)


def _gen_weekly_prices(n_weeks: int, start_price: float = 100.0, drift: float = 0.0) -> list[dict]:
    """Generate ``n_weeks + 1`` daily price points spanning n_weeks weeks
    (Friday closes are kept by the weekly-resampler in compute_nifty_beta)."""
    out: list[dict] = []
    d = date(2023, 1, 6)  # a Friday
    p = start_price
    for i in range(n_weeks + 1):
        out.append({"date": d.isoformat(), "close": p})
        d += timedelta(days=7)
        p *= (1 + drift)
    return out


class TestComputeNiftyBeta:
    def test_correlated_returns_yield_beta(self):
        """Stock returns = 1.5 * index returns + noise → raw beta ~1.5."""
        import random
        random.seed(42)
        index_prices = _gen_weekly_prices(80, 20000, 0.0)
        # Inject independent random walks scaled 1.5x for the stock.
        # Use returns from index series + noise to drive stock prices.
        idx_closes = [p["close"] for p in index_prices]
        idx_returns = [
            math.log(idx_closes[i] / idx_closes[i - 1])
            if idx_closes[i - 1] > 0 else 0.0
            for i in range(1, len(idx_closes))
        ]
        # Inject randomness so the index series isn't degenerate.
        import numpy as np
        rng = np.random.default_rng(42)
        idx_returns_with_noise = [r + rng.normal(0, 0.01) for r in idx_returns]
        # Reconstruct index closes with noise.
        new_idx = [idx_closes[0]]
        for r in idx_returns_with_noise:
            new_idx.append(new_idx[-1] * math.exp(r))
        index_prices = [{"date": p["date"], "close": c} for p, c in zip(index_prices, new_idx)]

        # Stock returns = 1.5 * index returns + small idiosyncratic noise.
        stock_closes = [100.0]
        for r in idx_returns_with_noise:
            stock_r = 1.5 * r + rng.normal(0, 0.005)
            stock_closes.append(stock_closes[-1] * math.exp(stock_r))
        stock_prices = [{"date": p["date"], "close": c} for p, c in zip(index_prices, stock_closes)]

        result = compute_nifty_beta(stock_prices, index_prices)
        assert "raw_beta" in result
        # Beta should be in the 1.0-2.0 ballpark with this construction.
        assert 1.0 < result["raw_beta"] < 2.0
        assert result["num_weeks"] >= 52

    def test_insufficient_data_returns_error(self):
        """Less than 53 weeks of common data → error dict."""
        index_prices = _gen_weekly_prices(20, 1000, 0.001)
        stock_prices = [{"date": p["date"], "close": p["close"] * 2} for p in index_prices]
        result = compute_nifty_beta(stock_prices, index_prices)
        assert "error" in result
        assert "num_weeks" in result

    def test_no_overlap_returns_error(self):
        index_prices = [{"date": "2024-01-05", "close": 1000}]
        stock_prices = [{"date": "2025-01-05", "close": 100}]
        result = compute_nifty_beta(stock_prices, index_prices)
        assert "error" in result


class TestBuildWaccParamsBFSI:
    """Regression: when is_bfsi=True, cost_of_debt is explicitly None.
    Callers that did wacc_data.get('cost_of_debt', {}).get('kd_pretax') used
    to crash with AttributeError because get() returns the explicit-None
    rather than the default empty dict.
    """

    def _common_kwargs(self, **overrides):
        # 80 weeks of synthetic prices — enough to clear the 53-week threshold.
        index_prices = _gen_weekly_prices(80, 20000, 0.001)
        stock_prices = [
            {"date": p["date"], "close": p["close"] * 0.05 * (1 + 0.0005 * i)}
            for i, p in enumerate(index_prices)
        ]
        kwargs = dict(
            symbol="HDFCLIFE",
            stock_prices=stock_prices,
            index_prices=index_prices,
            rf=0.069,
            interest=0.0,
            borrowings=0.0,
            pbt=1000.0,
            mcap_cr=80000.0,
            pe_band=None,
            industry="Life Insurance",
            is_bfsi=True,
            effective_tax_rate=0.25,
        )
        kwargs.update(overrides)
        return kwargs

    def test_bfsi_returns_none_cost_of_debt(self):
        """BFSI/insurance flag must yield cost_of_debt=None (skip CoD compute)."""
        result = build_wacc_params(**self._common_kwargs())
        assert result["is_bfsi"] is True
        # The explicit-None is the trigger for the compute-analytics bug.
        assert result["cost_of_debt"] is None
        assert result["wacc_result"] is None
        # WACC for BFSI = cost of equity.
        assert result["wacc"] == result["ke"]

    def test_bfsi_beta_still_populated(self):
        """Beta dict must be present even when CoD is skipped — this is
        precisely what the HDFCLIFE bug was hiding."""
        result = build_wacc_params(**self._common_kwargs())
        beta = result["beta"]
        assert isinstance(beta, dict)
        # Either error or raw_beta — the dict shape itself is the fix.
        assert "raw_beta" in beta or "error" in beta

    def test_compute_analytics_pattern_handles_none_cost_of_debt(self):
        """Smoke-test the exact dict-access pattern compute-analytics.py uses
        (post-fix). Pre-fix this raised ``AttributeError: 'NoneType' object
        has no attribute 'get'`` and clobbered beta_blume / beta_raw /
        beta_r_squared for every BFSI & insurance stock.
        """
        wacc_data = build_wacc_params(**self._common_kwargs())

        # The fixed pattern: `or {}` guards against explicit-None.
        cod = wacc_data.get("cost_of_debt") or {}
        assert cod == {}  # because BFSI sets it to None
        # ... and then .get() works without raising.
        assert cod.get("kd_pretax") is None

        beta = wacc_data.get("beta", {})
        assert isinstance(beta, dict)
        # blume_beta should be populated when the regression succeeds, or a
        # default 1.0 when it fails — never erased.
        beta_blume = beta.get("blume_beta")
        if "error" not in beta:
            assert beta_blume is not None


class TestBuildWaccParamsNonBFSI:
    """Sanity check: non-BFSI path still computes cost_of_debt as a dict."""

    def test_non_bfsi_returns_cod_dict(self):
        index_prices = _gen_weekly_prices(80, 20000, 0.001)
        stock_prices = [
            {"date": p["date"], "close": p["close"] * 0.05 * (1 + 0.0005 * i)}
            for i, p in enumerate(index_prices)
        ]
        result = build_wacc_params(
            symbol="TCS",
            stock_prices=stock_prices,
            index_prices=index_prices,
            rf=0.069,
            interest=200.0,
            borrowings=5000.0,
            pbt=50000.0,
            mcap_cr=900000.0,
            pe_band=None,
            industry="Information Technology Services",
            is_bfsi=False,
            effective_tax_rate=0.25,
        )
        assert result["cost_of_debt"] is not None
        assert isinstance(result["cost_of_debt"], dict)
        # WACC blends CoE and CoD, so it should differ from CoE for a leveraged co.
        assert "kd_pretax" in result["cost_of_debt"]


class TestCostOfDebtTaxClamp:
    """Tax-shield must never raise post-tax cost of debt above pre-tax.

    Regression for NTPC-style negative effective tax rates (e.g. -11.66% from
    deferred-tax credits / regulatory adjustments).
    """

    def test_cost_of_debt_negative_effective_tax(self):
        result = compute_cost_of_debt(
            interest=100.0,
            borrowings=5000.0,
            pbt=1000.0,
            rf=0.07,
            effective_tax_rate=-0.1166,
        )
        assert result["tax_rate_used"] == round(STATUTORY_TAX_RATE, 4)
        assert result["kd_posttax"] < result["kd_pretax"]
        assert result["tax_rate_anomalous"] is True

    def test_cost_of_debt_normal_tax(self):
        result = compute_cost_of_debt(
            interest=100.0,
            borrowings=5000.0,
            pbt=1000.0,
            rf=0.07,
            effective_tax_rate=0.25,
        )
        assert result["tax_rate_used"] == 0.25
        assert result["kd_posttax"] < result["kd_pretax"]
        assert result["tax_rate_anomalous"] is False

    def test_cost_of_debt_unprofitable(self):
        result = compute_cost_of_debt(
            interest=100.0,
            borrowings=5000.0,
            pbt=-500.0,
            rf=0.07,
            effective_tax_rate=0.25,
        )
        assert result["tax_rate_used"] == 0.0
        assert result["kd_posttax"] == result["kd_pretax"]
        assert result["tax_rate_anomalous"] is False


# --- Market-aware WACC (US support) ---


class TestNSEDefaultRegressionLock:
    """Hard constraint: market=NSE (the default) must be byte-identical to the
    pre-market-aware behavior."""

    def test_cost_of_equity_nse_default_matches_explicit_india_erp(self):
        # Passing INDIA_ERP explicitly == omitting erp (config fills it) == market=NSE.
        a = compute_cost_of_equity(0.07, 1.2, INDIA_ERP, 100000.0)
        b = compute_cost_of_equity(0.07, 1.2, None, 100000.0, market=Market.NSE)
        c = compute_cost_of_equity(0.07, 1.2, INDIA_ERP, 100000.0, market=Market.NSE)
        assert a == b == c
        # Manual CAPM check, no small-cap premium (mcap above threshold).
        assert a["ke"] == round(0.07 + 1.2 * INDIA_ERP, 4)
        assert a["small_cap_premium"] == 0.0
        assert a["erp"] == INDIA_ERP

    def test_nse_small_cap_premium_unchanged(self):
        res = compute_cost_of_equity(
            0.07, 1.0, None, SMALL_CAP_THRESHOLD_CR - 1, market=Market.NSE
        )
        assert res["small_cap_premium"] == 0.03
        assert res["ke"] == round(0.07 + 1.0 * INDIA_ERP + 0.03, 4)

    def test_cost_of_debt_nse_clamp_uses_india_statutory(self):
        res = compute_cost_of_debt(100.0, 5000.0, 1000.0, 0.07, -0.1, market=Market.NSE)
        assert res["tax_rate_used"] == round(STATUTORY_TAX_RATE, 4)
        assert res["tax_rate_anomalous"] is True

    def test_beta_index_nse_is_nifty500(self):
        assert beta_index_symbol(Market.NSE) == "^CRSLDX"
        assert beta_index_symbol(Market.BSE) == "^CRSLDX"


class TestUSMarketWacc:
    def test_beta_index_us_is_sp500(self):
        assert beta_index_symbol(Market.NASDAQ) == "^GSPC"
        assert beta_index_symbol(Market.NYSE) == "^GSPC"

    def test_cost_of_equity_us_uses_us_erp_no_smallcap(self):
        # mcap below the INR-crore threshold must NOT trigger a premium for US.
        res = compute_cost_of_equity(
            0.043, 1.1, None, mcap_cr=10.0, market=Market.NASDAQ
        )
        assert res["erp"] == US_ERP
        assert res["small_cap_premium"] == 0.0
        assert res["ke"] == round(0.043 + 1.1 * US_ERP, 4)

    def test_cost_of_debt_us_clamp_uses_us_statutory(self):
        # Effective rate of 0.30 exceeds the 24% US ceiling → clamp + flag.
        res = compute_cost_of_debt(
            100.0, 5000.0, 1000.0, 0.043, 0.30, market=Market.NASDAQ
        )
        assert res["tax_rate_used"] == round(US_STATUTORY_TAX_RATE, 4)
        assert res["tax_rate_anomalous"] is True
        # 0.24 is fine for India? No — India ceiling is 0.2517, so 0.24 valid there.
        res_in = compute_cost_of_debt(
            100.0, 5000.0, 1000.0, 0.07, 0.24, market=Market.NSE
        )
        assert res_in["tax_rate_used"] == 0.24
        assert res_in["tax_rate_anomalous"] is False

    def test_us_large_cap_wacc_in_reasonable_range(self, monkeypatch):
        """A US large-cap with mocked beta yields Ke/WACC in a sane 7-12% band.
        Mock the beta regression so no price data / network is needed."""
        import flowtracker.research.wacc as wacc_mod

        monkeypatch.setattr(
            wacc_mod,
            "compute_market_beta",
            lambda sp, ip, market=Market.NSE: {
                "raw_beta": 1.05,
                "blume_beta": 1.03,
                "r_squared": 0.55,
                "num_weeks": 104,
            },
        )

        result = build_wacc_params(
            symbol="MSFT",
            stock_prices=[],  # ignored — beta is mocked
            index_prices=[],
            rf=0.043,  # ~US 10Y
            interest=2000.0,
            borrowings=80000.0,
            pbt=900000.0,
            mcap_cr=3_000_000.0,  # $3T in $mn
            pe_band=None,
            industry="Software",
            is_bfsi=False,
            effective_tax_rate=0.18,
            market=Market.NASDAQ,
        )
        # ERP/tax came from US config.
        assert result["cost_of_equity"]["erp"] == US_ERP
        assert result["cost_of_debt"]["tax_rate_used"] == 0.18  # valid < 0.24
        # Ke = 0.043 + 1.03*0.046 ≈ 0.0904; no small-cap premium for US.
        assert result["cost_of_equity"]["small_cap_premium"] == 0.0
        assert 0.07 <= result["ke"] <= 0.12
        assert 0.07 <= result["wacc"] <= 0.12

    def test_build_wacc_params_us_selects_us_beta_index_path(self, monkeypatch):
        """Confirm build_wacc_params forwards market into compute_market_beta so
        the US beta benchmark (^GSPC) selection applies."""
        import flowtracker.research.wacc as wacc_mod

        captured = {}

        def fake_beta(sp, ip, market=Market.NSE):
            captured["market"] = market
            return {"raw_beta": 1.0, "blume_beta": 1.0, "r_squared": 0.5, "num_weeks": 60}

        monkeypatch.setattr(wacc_mod, "compute_market_beta", fake_beta)
        build_wacc_params(
            symbol="AAPL",
            stock_prices=[],
            index_prices=[],
            rf=0.043,
            interest=0.0,
            borrowings=0.0,
            pbt=1000.0,
            mcap_cr=1_000_000.0,
            pe_band=None,
            is_bfsi=True,
            market=Market.NYSE,
        )
        assert captured["market"] == Market.NYSE
        assert beta_index_symbol(captured["market"]) == "^GSPC"
