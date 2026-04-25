"""Tests for research/wacc.py — beta, CoE, CoD, WACC, terminal growth.

Regression coverage for the BFSI/insurance-Beta-null bug where compute-analytics.py
crashed on `cost_of_debt is None` and clobbered beta_blume/beta_raw/beta_r_squared
for every banking & insurance stock (HDFCLIFE, SBIN, HDFCBANK, ICICIBANK, etc.).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from flowtracker.research.wacc import (
    build_wacc_params,
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
