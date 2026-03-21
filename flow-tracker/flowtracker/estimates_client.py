"""Consensus estimates client — analyst targets and earnings surprises via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import date

import yfinance as yf

from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.fund_client import nse_symbol

logger = logging.getLogger(__name__)


class EstimatesClient:
    """Client for consensus estimates via yfinance."""

    def fetch_estimates(self, symbol: str) -> ConsensusEstimate | None:
        """Fetch analyst estimates for a single stock."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))
            info = ticker.info or {}

            if not info or info.get("quoteType") is None:
                logger.warning("No data for %s", symbol)
                return None

            return ConsensusEstimate(
                symbol=symbol,
                date=date.today().isoformat(),
                target_mean=info.get("targetMeanPrice"),
                target_median=info.get("targetMedianPrice"),
                target_high=info.get("targetHighPrice"),
                target_low=info.get("targetLowPrice"),
                num_analysts=info.get("numberOfAnalystOpinions"),
                recommendation=info.get("recommendationKey"),
                recommendation_score=info.get("recommendationMean"),
                forward_pe=info.get("forwardPE"),
                forward_eps=info.get("forwardEps"),
                earnings_growth=info.get("earningsGrowth"),
                current_price=info.get("currentPrice") or info.get("regularMarketPrice"),
            )
        except Exception as e:
            logger.warning("Failed to fetch estimates for %s: %s", symbol, e)
            return None

    def fetch_surprises(self, symbol: str) -> list[EarningsSurprise]:
        """Fetch earnings surprises for a single stock."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))

            # Try quarterly_earnings first (more reliable)
            try:
                qe = ticker.quarterly_earnings
                if qe is not None and not qe.empty:
                    surprises = []
                    for idx, row in qe.iterrows():
                        quarter = str(idx)
                        surprise_pct = None
                        if "Surprise(%)" in row.index:
                            val = row["Surprise(%)"]
                            if val is not None and str(val) != "nan":
                                surprise_pct = float(val)

                        actual = None
                        estimate = None
                        if "Earnings" in row.index:
                            val = row["Earnings"]
                            if val is not None and str(val) != "nan":
                                actual = float(val)

                        surprises.append(EarningsSurprise(
                            symbol=symbol,
                            quarter_end=quarter,
                            eps_actual=actual,
                            eps_estimate=estimate,
                            surprise_pct=surprise_pct,
                        ))
                    return surprises
            except Exception:
                pass

            # Fallback: try earnings_history
            try:
                eh = ticker.get_earnings_history()
                if eh is not None and not eh.empty:
                    surprises = []
                    for _, row in eh.iterrows():
                        actual = row.get("epsActual")
                        estimate = row.get("epsEstimate")
                        surprise = None
                        if actual is not None and estimate is not None and estimate != 0:
                            surprise = round((actual - estimate) / abs(estimate) * 100, 2)
                        quarter = str(row.get("quarter", ""))
                        surprises.append(EarningsSurprise(
                            symbol=symbol,
                            quarter_end=quarter,
                            eps_actual=float(actual) if actual is not None else None,
                            eps_estimate=float(estimate) if estimate is not None else None,
                            surprise_pct=surprise,
                        ))
                    return surprises
            except Exception:
                pass

            return []
        except Exception as e:
            logger.warning("Failed to fetch surprises for %s: %s", symbol, e)
            return []

    def fetch_batch(
        self, symbols: list[str],
    ) -> tuple[list[ConsensusEstimate], list[EarningsSurprise]]:
        """Fetch estimates and surprises for multiple stocks."""
        estimates: list[ConsensusEstimate] = []
        surprises: list[EarningsSurprise] = []

        for i, symbol in enumerate(symbols):
            logger.info("Fetching estimates %d/%d: %s", i + 1, len(symbols), symbol)

            est = self.fetch_estimates(symbol)
            if est:
                estimates.append(est)

            surps = self.fetch_surprises(symbol)
            surprises.extend(surps)

            if i < len(symbols) - 1:
                time.sleep(0.3)

        return estimates, surprises
