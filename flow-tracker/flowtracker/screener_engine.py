"""Composite screening engine — multi-factor scoring across all data layers."""

from __future__ import annotations

import logging
from datetime import date

from flowtracker.screener_models import FactorScore, StockScore
from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)

# Factor weights (must sum to 1.0)
_WEIGHTS = {
    "ownership": 0.20,
    "insider": 0.15,
    "valuation": 0.15,
    "earnings": 0.15,
    "quality": 0.10,
    "delivery": 0.10,
    "estimates": 0.10,
    "risk": 0.05,
}


class ScreenerEngine:
    """Multi-factor stock screening engine."""

    def __init__(self, store: FlowStore) -> None:
        self._store = store
        self._cache: dict[str, dict] = {}

    def score_stock(self, symbol: str) -> StockScore | None:
        """Compute full scorecard for a single stock."""
        factors = []
        factors.append(self._score_ownership(symbol))
        factors.append(self._score_insider(symbol))
        factors.append(self._score_valuation(symbol))
        factors.append(self._score_earnings(symbol))
        factors.append(self._score_quality(symbol))
        factors.append(self._score_delivery(symbol))
        factors.append(self._score_estimates(symbol))
        factors.append(self._score_risk(symbol))

        # Compute weighted composite
        total_weight = 0.0
        weighted_sum = 0.0
        for f in factors:
            w = _WEIGHTS.get(f.factor, 0)
            if f.score >= 0:  # -1 means no data
                weighted_sum += f.score * w
                total_weight += w

        composite = weighted_sum / total_weight if total_weight > 0 else 0

        # Get company info
        constituents = self._store.get_index_constituents()
        info = {c.symbol: c for c in constituents}
        c = info.get(symbol)

        return StockScore(
            symbol=symbol,
            company_name=c.company_name if c else None,
            industry=c.industry if c else None,
            composite_score=round(composite, 1),
            factors=factors,
        )

    def screen_all(
        self, symbols: list[str] | None = None, factor: str | None = None,
    ) -> list[StockScore]:
        """Score and rank all stocks. Optionally filter to a single factor."""
        if symbols is None:
            symbols = self._store.get_all_scanner_symbols()

        scores: list[StockScore] = []
        for sym in symbols:
            score = self.score_stock(sym)
            if score:
                scores.append(score)

        # Sort by composite or single factor
        if factor and factor in _WEIGHTS:
            scores.sort(
                key=lambda s: next(
                    (f.score for f in s.factors if f.factor == factor), 0
                ),
                reverse=True,
            )
        else:
            scores.sort(key=lambda s: s.composite_score, reverse=True)

        for i, s in enumerate(scores):
            s.rank = i + 1

        return scores

    # -- Individual Factor Scoring --

    def _score_ownership(self, symbol: str) -> FactorScore:
        """Ownership momentum: MF accumulation trend, FII→MF handoff."""
        changes = self._store.get_shareholding_changes(symbol)
        if not changes:
            return FactorScore(factor="ownership", score=-1, detail="No data")

        mf_chg = next((c.change_pct for c in changes if c.category == "MF"), 0)
        fii_chg = next((c.change_pct for c in changes if c.category == "FII"), 0)
        dii_chg = next((c.change_pct for c in changes if c.category == "DII"), 0)

        # Score: MF accumulation is strongest signal
        score = 50.0
        score += mf_chg * 15  # +1% MF = +15 points
        score += dii_chg * 5  # +1% DII = +5 points
        # FII exit with MF pickup = handoff (bullish)
        if fii_chg < 0 and mf_chg > 0:
            score += 10
        elif fii_chg > 0 and mf_chg > 0:
            score += 5  # Both accumulating

        detail = f"MF {mf_chg:+.1f}% FII {fii_chg:+.1f}% DII {dii_chg:+.1f}%"
        return FactorScore(
            factor="ownership", score=_clamp(score), raw_value=mf_chg, detail=detail,
        )

    def _score_insider(self, symbol: str) -> FactorScore:
        """Insider conviction: promoter buying is the strongest signal."""
        trades = self._store.get_insider_by_symbol(symbol, days=90)
        if not trades:
            return FactorScore(factor="insider", score=-1, detail="No data")

        buys = [t for t in trades if t.transaction_type == "Buy"]
        sells = [t for t in trades if t.transaction_type == "Sell"]
        promoter_buys = [t for t in buys if "Promoter" in t.person_category]

        buy_val = sum(t.value for t in buys) / 1e7  # crores
        sell_val = sum(t.value for t in sells) / 1e7
        promo_buy_val = sum(t.value for t in promoter_buys) / 1e7

        score = 50.0
        if promo_buy_val > 10:
            score += 30  # Large promoter buying
        elif promo_buy_val > 1:
            score += 15
        elif promo_buy_val > 0:
            score += 5

        if buy_val > sell_val * 2:
            score += 10
        elif sell_val > buy_val * 2:
            score -= 15

        # Cluster buying (multiple insiders)
        unique_buyers = len({t.person_name for t in buys})
        if unique_buyers >= 3:
            score += 10

        detail = f"Buy ₹{buy_val:.0f}Cr Sell ₹{sell_val:.0f}Cr PromoterBuy ₹{promo_buy_val:.0f}Cr"
        return FactorScore(
            factor="insider", score=_clamp(score), raw_value=promo_buy_val, detail=detail,
        )

    def _score_valuation(self, symbol: str) -> FactorScore:
        """Valuation: forward P/E vs trailing, upside to target."""
        est = self._store.get_estimate_latest(symbol)
        if not est:
            return FactorScore(factor="valuation", score=-1, detail="No data")

        score = 50.0
        upside = None

        if est.target_mean and est.current_price and est.current_price > 0:
            upside = (est.target_mean - est.current_price) / est.current_price * 100
            if upside > 30:
                score += 25
            elif upside > 15:
                score += 15
            elif upside > 0:
                score += 5
            elif upside < -15:
                score -= 15

        if est.forward_pe:
            if est.forward_pe < 15:
                score += 10
            elif est.forward_pe < 25:
                score += 5
            elif est.forward_pe > 50:
                score -= 10

        # DCF margin of safety (FMP)
        dcf_detail = ""
        try:
            dcf = self._store.get_fmp_dcf_latest(symbol)
            if dcf and dcf.dcf and dcf.stock_price and dcf.stock_price > 0:
                dcf_margin = (dcf.dcf - dcf.stock_price) / dcf.stock_price * 100
                if dcf_margin > 30:
                    score += 15
                    dcf_detail = f" DCF +{dcf_margin:.0f}%"
                elif dcf_margin < -20:
                    score -= 10
                    dcf_detail = f" DCF {dcf_margin:.0f}%"
                else:
                    dcf_detail = f" DCF {dcf_margin:+.0f}%"
        except Exception:
            pass

        detail = f"Upside {upside:+.0f}%" if upside else "No target"
        if est.forward_pe:
            detail += f" FwdPE {est.forward_pe:.0f}"
        detail += dcf_detail
        return FactorScore(
            factor="valuation", score=_clamp(score), raw_value=upside, detail=detail,
        )

    def _score_earnings(self, symbol: str) -> FactorScore:
        """Earnings quality: surprise %, margin trajectory."""
        surprises = self._store.get_surprises(symbol)
        if not surprises:
            return FactorScore(factor="earnings", score=-1, detail="No data")

        score = 50.0
        avg_surprise = 0
        valid = [s for s in surprises if s.surprise_pct is not None]
        if valid:
            avg_surprise = sum(s.surprise_pct for s in valid) / len(valid)
            if avg_surprise > 10:
                score += 25
            elif avg_surprise > 0:
                score += 10
            elif avg_surprise < -10:
                score -= 20

        # Check for consecutive beats
        beats = sum(1 for s in valid if (s.surprise_pct or 0) > 0)
        if beats >= 3:
            score += 10

        detail = f"Avg surprise {avg_surprise:+.1f}% ({beats}/{len(valid)} beats)"
        return FactorScore(
            factor="earnings", score=_clamp(score), raw_value=avg_surprise, detail=detail,
        )

    def _score_quality(self, symbol: str) -> FactorScore:
        """Business quality: ROCE trend, cash conversion from annual financials."""
        rows = self._store._conn.execute(
            "SELECT * FROM annual_financials WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT 3",
            (symbol,),
        ).fetchall()

        if not rows:
            return FactorScore(factor="quality", score=-1, detail="No data")

        from flowtracker.fund_models import AnnualFinancials
        financials = [AnnualFinancials(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            revenue=r["revenue"], net_income=r["net_income"],
            profit_before_tax=r["profit_before_tax"], interest=r["interest"],
            total_assets=r["total_assets"], other_liabilities=r["other_liabilities"],
            equity_capital=r["equity_capital"], reserves=r["reserves"],
            borrowings=r["borrowings"], cfo=r["cfo"], cfi=r["cfi"],
        ) for r in rows]

        score = 50.0
        latest = financials[0]

        # ROCE
        roce = latest.roce
        if roce and roce > 0.20:
            score += 20
        elif roce and roce > 0.12:
            score += 10
        elif roce and roce < 0.05:
            score -= 10

        # Cash conversion
        cfo_ratio = latest.cfo_to_net_income
        if cfo_ratio and cfo_ratio > 1.0:
            score += 10
        elif cfo_ratio and cfo_ratio < 0.5:
            score -= 10

        # D/E
        de = latest.debt_to_equity
        if de and de > 2.0:
            score -= 10
        elif de and de < 0.5:
            score += 5

        detail_parts = []
        if roce:
            detail_parts.append(f"ROCE {roce*100:.0f}%")
        if cfo_ratio:
            detail_parts.append(f"CFO/NI {cfo_ratio:.1f}x")
        if de is not None:
            detail_parts.append(f"D/E {de:.1f}")

        return FactorScore(
            factor="quality", score=_clamp(score),
            raw_value=roce, detail=" ".join(detail_parts) or "No metrics",
        )

    def _score_delivery(self, symbol: str) -> FactorScore:
        """Market signal: delivery % trend from bhavcopy data."""
        records = self._store.get_stock_delivery(symbol, days=30)
        if not records:
            return FactorScore(factor="delivery", score=-1, detail="No data")

        avg_delivery = sum(r.delivery_pct or 0 for r in records) / len(records)
        high_delivery_days = sum(1 for r in records if (r.delivery_pct or 0) > 60)

        score = 50.0
        if avg_delivery > 60:
            score += 25
        elif avg_delivery > 45:
            score += 10
        elif avg_delivery < 25:
            score -= 15

        if high_delivery_days >= 10:
            score += 10

        # Volume trend (increasing delivery % = accumulation)
        if len(records) >= 10:
            recent = sum(r.delivery_pct or 0 for r in records[:5]) / 5
            older = sum(r.delivery_pct or 0 for r in records[5:10]) / 5
            if recent > older + 5:
                score += 10  # Rising delivery trend

        detail = f"Avg {avg_delivery:.0f}% ({high_delivery_days} days >60%)"
        return FactorScore(
            factor="delivery", score=_clamp(score), raw_value=avg_delivery, detail=detail,
        )

    def _score_estimates(self, symbol: str) -> FactorScore:
        """Analyst consensus: recommendation and target."""
        est = self._store.get_estimate_latest(symbol)
        if not est or not est.recommendation:
            return FactorScore(factor="estimates", score=-1, detail="No data")

        score = 50.0
        rec = est.recommendation.lower()
        if rec in ("strong_buy",):
            score += 25
        elif rec in ("buy",):
            score += 15
        elif rec in ("hold",):
            score += 0
        elif rec in ("sell", "strong_sell"):
            score -= 20

        if est.num_analysts and est.num_analysts >= 10:
            score += 5  # Well-covered stock

        if est.earnings_growth and est.earnings_growth > 0.2:
            score += 10
        elif est.earnings_growth and est.earnings_growth < 0:
            score -= 10

        detail = f"{rec.replace('_', ' ').title()}"
        if est.num_analysts:
            detail += f" ({est.num_analysts} analysts)"
        if est.earnings_growth:
            detail += f" EG {est.earnings_growth*100:+.0f}%"

        return FactorScore(
            factor="estimates", score=_clamp(score),
            raw_value=est.recommendation_score, detail=detail,
        )

    def _score_risk(self, symbol: str) -> FactorScore:
        """Risk factors: promoter pledge, high D/E, FII crowding."""
        score = 70.0  # Start positive (no risk = good)

        # Promoter pledge
        pledges = self._store._conn.execute(
            "SELECT pledge_pct FROM promoter_pledge WHERE symbol = ? "
            "ORDER BY quarter_end DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        pledge_pct = pledges["pledge_pct"] if pledges else 0

        if pledge_pct > 50:
            score -= 40
        elif pledge_pct > 20:
            score -= 20
        elif pledge_pct > 5:
            score -= 10

        # FII crowding risk
        holdings = self._store.get_shareholding(symbol, limit=1)
        fii_pct = next((h.percentage for h in holdings if h.category == "FII"), 0)
        if fii_pct > 50:
            score -= 15  # FII exit risk
        elif fii_pct > 40:
            score -= 5

        detail_parts = []
        if pledge_pct > 0:
            detail_parts.append(f"Pledge {pledge_pct:.0f}%")
        if fii_pct > 30:
            detail_parts.append(f"FII {fii_pct:.0f}%")

        return FactorScore(
            factor="risk", score=_clamp(score),
            raw_value=pledge_pct, detail=" ".join(detail_parts) or "Low risk",
        )


def _clamp(v: float) -> float:
    """Clamp score to 0-100 range."""
    return max(0.0, min(100.0, v))
