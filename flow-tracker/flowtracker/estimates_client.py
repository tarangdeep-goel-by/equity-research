"""Consensus estimates client — analyst targets and earnings surprises via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import date

import yfinance as yf

from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.fund_client import nse_symbol

logger = logging.getLogger(__name__)


def _format_quarter(value) -> str:
    """Format a yfinance earnings-history index value as YYYY-MM-DD.

    Real yfinance returns `pd.Timestamp` (DatetimeIndex). Some test mocks pass a
    plain string like "2025Q1" or "Q1 2025" — pass those through unchanged.
    Returns empty string for unparseable / NaT / None inputs.
    """
    if value is None:
        return ""
    # pandas Timestamp / numpy datetime — render as YYYY-MM-DD
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            s = iso()
        except Exception:
            return ""
        # Drop time component if present
        return s.split("T")[0] if s and s != "NaT" else ""
    s = str(value).strip()
    if s in ("", "NaT", "nan", "None"):
        return ""
    # If it looks like an ISO datetime ("2025-03-31 00:00:00"), keep the date part.
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


def _extract_cy_ny_eps(ticker) -> tuple[float | None, float | None]:
    """Pull consensus EPS for current year (`0y`) and next year (`+1y`) from
    yfinance's `earnings_estimate` DataFrame. Returns (None, None) on any
    failure / empty / missing-row / NaN path."""
    try:
        ee = ticker.earnings_estimate
    except Exception:
        return None, None
    if ee is None or getattr(ee, "empty", True):
        return None, None
    if "avg" not in ee.columns:
        return None, None

    def _row_avg(period: str) -> float | None:
        if period not in ee.index:
            return None
        val = ee.loc[period, "avg"]
        if val is None or str(val) == "nan":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return _row_avg("0y"), _row_avg("+1y")


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

            _eg = info.get("earningsGrowth")
            eps_cy, eps_ny = _extract_cy_ny_eps(ticker)
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
                eps_current_year=eps_cy,
                eps_next_year=eps_ny,
                earnings_growth=_eg * 100 if _eg is not None else None,
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
                    for idx, row in eh.iterrows():
                        actual = row.get("epsActual")
                        estimate = row.get("epsEstimate")
                        surprise = None
                        if actual is not None and estimate is not None and estimate != 0:
                            surprise = round((actual - estimate) / abs(estimate) * 100, 2)
                        # quarter is the DataFrame index (named "quarter"), not a column.
                        # Real yfinance returns a DatetimeIndex; legacy mocks may pass it
                        # as a column with a default RangeIndex. Prefer the column when
                        # present (avoids picking up "0", "1", ...); otherwise use index.
                        col_q = str(row.get("quarter", "") or "").strip()
                        quarter = col_q or _format_quarter(idx)
                        if not quarter:
                            # Skip rows we can't anchor to a quarter — quarter_end is part
                            # of the UNIQUE constraint and must never be empty.
                            logger.warning(
                                "Skipping earnings row for %s: no quarter (idx=%r)",
                                symbol,
                                idx,
                            )
                            continue
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

    def fetch_estimate_revisions(self, symbol: str) -> dict | None:
        """Fetch EPS trend + revision counts from yfinance."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))

            eps_trend = ticker.eps_trend
            eps_revisions = ticker.eps_revisions

            trend_data: dict[str, dict] = {}
            if eps_trend is not None and not eps_trend.empty:
                for period in eps_trend.index:
                    row: dict = {}
                    for col, key in [
                        ("current", "current"),
                        ("7daysAgo", "7d_ago"),
                        ("30daysAgo", "30d_ago"),
                        ("60daysAgo", "60d_ago"),
                        ("90daysAgo", "90d_ago"),
                    ]:
                        if col in eps_trend.columns:
                            val = eps_trend.loc[period, col]
                            if val is not None and str(val) != "nan":
                                row[key] = float(val)
                    if row:
                        trend_data[str(period)] = row

            rev_data: dict[str, dict] = {}
            if eps_revisions is not None and not eps_revisions.empty:
                for period in eps_revisions.index:
                    row_r: dict = {}
                    for col, key in [
                        ("upLast7days", "up_7d"),
                        ("upLast30days", "up_30d"),
                        ("downLast30days", "down_30d"),
                        ("downLast7Days", "down_7d"),
                    ]:
                        if col in eps_revisions.columns:
                            val = eps_revisions.loc[period, col]
                            if val is not None and str(val) != "nan":
                                row_r[key] = int(val)
                    if row_r:
                        rev_data[str(period)] = row_r

            if not trend_data and not rev_data:
                logger.warning("No estimate revision data for %s", symbol)
                return None

            # Compute momentum score
            period_weights = {"0q": 0.15, "+1q": 0.15, "0y": 0.35, "+1y": 0.35}
            weighted_change = 0.0
            total_weight = 0.0
            for period, weight in period_weights.items():
                t = trend_data.get(period, {})
                current = t.get("current")
                ago_90 = t.get("90d_ago")
                if current is not None and ago_90 is not None and ago_90 != 0:
                    change = (current - ago_90) / abs(ago_90)
                    weighted_change += change * weight
                    total_weight += weight

            if total_weight > 0:
                weighted_change /= total_weight

            # Net revision bonus
            total_up = 0
            total_down = 0
            for period in rev_data.values():
                total_up += period.get("up_30d", 0)
                total_down += period.get("down_30d", 0)
            net_rev = total_up - total_down
            revision_bonus = net_rev / max(total_up + total_down, 1)

            momentum_score = max(0.0, min(1.0, 0.5 + weighted_change * 2 + revision_bonus * 0.1))
            momentum_score = round(momentum_score, 3)

            if momentum_score > 0.6:
                momentum_signal = "positive"
            elif momentum_score < 0.4:
                momentum_signal = "negative"
            else:
                momentum_signal = "neutral"

            return {
                "symbol": symbol.upper(),
                "eps_trend": trend_data,
                "eps_revisions": rev_data,
                "momentum_score": momentum_score,
                "momentum_signal": momentum_signal,
            }
        except Exception as e:
            logger.warning("Failed to fetch estimate revisions for %s: %s", symbol, e)
            return None

    def fetch_events_calendar(self, symbol: str) -> dict | None:
        """Fetch upcoming events calendar: earnings date, ex-dividend, consensus estimates."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))
            cal = ticker.calendar
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                return None
            if isinstance(cal, dict):
                raw = cal
            else:
                raw = cal.to_dict() if hasattr(cal, "to_dict") else {}

            result: dict = {"symbol": symbol.upper()}

            # Earnings date
            earnings = raw.get("Earnings Date")
            if earnings:
                if isinstance(earnings, list):
                    result["next_earnings"] = str(earnings[0])
                else:
                    result["next_earnings"] = str(earnings)
                try:
                    from datetime import date as dt_date
                    ed = dt_date.fromisoformat(result["next_earnings"])
                    result["days_to_earnings"] = (ed - dt_date.today()).days
                except (ValueError, TypeError):
                    pass

            # Ex-dividend date
            ex_div = raw.get("Ex-Dividend Date")
            if ex_div:
                result["ex_dividend_date"] = str(ex_div)
                try:
                    from datetime import date as dt_date
                    exd = dt_date.fromisoformat(str(ex_div))
                    delta = (dt_date.today() - exd).days
                    if delta >= 0:
                        result["days_since_ex_dividend"] = delta
                    else:
                        result["days_to_ex_dividend"] = abs(delta)
                except (ValueError, TypeError):
                    pass

            # Consensus estimates (next quarter)
            eps_avg = raw.get("Earnings Average")
            eps_high = raw.get("Earnings High")
            eps_low = raw.get("Earnings Low")
            if any(v is not None for v in [eps_avg, eps_high, eps_low]):
                result["earnings_estimate"] = {}
                if eps_avg is not None:
                    result["earnings_estimate"]["avg"] = float(eps_avg)
                if eps_high is not None:
                    result["earnings_estimate"]["high"] = float(eps_high)
                if eps_low is not None:
                    result["earnings_estimate"]["low"] = float(eps_low)

            rev_avg = raw.get("Revenue Average")
            rev_high = raw.get("Revenue High")
            rev_low = raw.get("Revenue Low")
            if any(v is not None for v in [rev_avg, rev_high, rev_low]):
                result["revenue_estimate_cr"] = {}
                if rev_avg is not None:
                    result["revenue_estimate_cr"]["avg"] = round(float(rev_avg) / 1e7, 2)
                if rev_high is not None:
                    result["revenue_estimate_cr"]["high"] = round(float(rev_high) / 1e7, 2)
                if rev_low is not None:
                    result["revenue_estimate_cr"]["low"] = round(float(rev_low) / 1e7, 2)

            return result if len(result) > 1 else None
        except Exception as e:
            logger.warning("Failed to fetch events calendar for %s: %s", symbol, e)
            return None

    def fetch_revenue_estimates(self, symbol: str) -> dict | None:
        """Fetch consensus revenue estimates from yfinance."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))
            rev_est = ticker.revenue_estimate
            if rev_est is None or (hasattr(rev_est, "empty") and rev_est.empty):
                return None

            periods = []
            for period in rev_est.index:
                row = {}
                for col, key in [
                    ("avg", "avg"), ("low", "low"), ("high", "high"),
                    ("numberOfAnalysts", "num_analysts"),
                    ("yearAgoRevenue", "year_ago_revenue"),
                    ("growth", "growth"),
                ]:
                    if col in rev_est.columns:
                        val = rev_est.loc[period, col]
                        if val is not None and str(val) != "nan":
                            # Convert INR to crores for monetary values
                            if col in ("avg", "low", "high", "yearAgoRevenue"):
                                row[key + "_cr"] = round(float(val) / 1e7, 2)
                            elif col == "numberOfAnalysts":
                                row[key] = int(val)
                            else:
                                row[key] = round(float(val), 4)
                if row:
                    periods.append({"period": str(period), **row})

            return {"symbol": symbol.upper(), "periods": periods} if periods else None
        except Exception as e:
            logger.warning("Failed to fetch revenue estimates for %s: %s", symbol, e)
            return None

    def fetch_growth_estimates(self, symbol: str) -> dict | None:
        """Fetch growth estimates (stock vs index) from yfinance."""
        try:
            ticker = yf.Ticker(nse_symbol(symbol))
            growth_est = ticker.growth_estimates
            if growth_est is None or (hasattr(growth_est, "empty") and growth_est.empty):
                return None

            # growth_estimates has columns like stock ticker and index
            # Try to find stockTrend and indexTrend columns
            cols = growth_est.columns.tolist()
            stock_col = None
            index_col = None
            for c in cols:
                cl = str(c).lower()
                if "stock" in cl or nse_symbol(symbol).replace(".NS", "") in str(c):
                    stock_col = c
                elif "index" in cl or "industry" in cl:
                    index_col = c

            # Fallback: first col = stock, second = index
            if stock_col is None and len(cols) >= 1:
                stock_col = cols[0]
            if index_col is None and len(cols) >= 2:
                index_col = cols[1]

            periods = []
            ltg = {"stock": None, "index": None}

            for period in growth_est.index:
                entry = {"period": str(period)}
                if stock_col is not None:
                    val = growth_est.loc[period, stock_col]
                    if val is not None and str(val) != "nan":
                        entry["stock_growth"] = round(float(val), 4)
                if index_col is not None:
                    val = growth_est.loc[period, index_col]
                    if val is not None and str(val) != "nan":
                        entry["index_growth"] = round(float(val), 4)

                sg = entry.get("stock_growth")
                ig = entry.get("index_growth")
                if sg is not None and ig is not None:
                    entry["vs_index"] = "outperforming" if sg > ig else "underperforming" if sg < ig else "inline"

                if str(period).upper() == "LTG" or "long" in str(period).lower():
                    ltg["stock"] = entry.get("stock_growth")
                    ltg["index"] = entry.get("index_growth")
                else:
                    periods.append(entry)

            if not periods and ltg["stock"] is None:
                return None

            return {"symbol": symbol.upper(), "periods": periods, "ltg": ltg}
        except Exception as e:
            logger.warning("Failed to fetch growth estimates for %s: %s", symbol, e)
            return None

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
