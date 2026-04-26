"""yfinance client for Indian equity fundamentals."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import yfinance as yf

from flowtracker.fund_models import LiveSnapshot, QuarterlyResult, ValuationSnapshot


class YFinanceError(Exception):
    """Raised when yfinance returns no data."""


def nse_symbol(symbol: str) -> str:
    """Convert watchlist symbol to yfinance format. TECHM -> TECHM.NS"""
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def _safe_get(df: Any, row: str, col: Any) -> float | None:
    """Safely extract a value from a DataFrame."""
    try:
        val = df.loc[row, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _div100(val: float | None) -> float | None:
    """yfinance debtToEquity is in %, convert to ratio."""
    return val / 100 if val is not None else None


def _to_cr(val: float | None) -> float | None:
    """Convert raw rupees to crores (÷1e7)."""
    return val / 1e7 if val is not None else None


def _to_pct(val: float | None) -> float | None:
    """Convert decimal ratio (0.25) to percentage (25.0)."""
    return val * 100 if val is not None else None


def _ev_ebitda_currency_safe(info: dict[str, Any]) -> float | None:
    """Currency-safe EV/EBITDA from yfinance ``info``.

    yfinance reports ``enterpriseValue`` in the display ``currency`` (INR for
    ``.NS`` listings) but ``ebitda`` in the company's ``financialCurrency``
    (USD for ADR-listed Indian IT stocks like INFY, HCLTECH, WIT — they file
    ADRs in USD, so Yahoo serves their EBITDA in USD millions). The
    ``enterpriseToEbitda`` field is the raw INR-EV / USD-EBITDA ratio, which
    inflates EV/EBITDA by ~84x for those names (INFY=994, HCLTECH=1192).

    Detection: ``financialCurrency != currency`` and both are populated.
    Fix: pull ``usd_inr`` from macro_snapshot, compute
    ``ev / (ebitda * usd_inr)`` to get sane INR-INR ratio. If macro is
    unavailable, fall back to a sanity check — if yfinance's
    ``enterpriseToEbitda`` is in [0, 100], trust it; otherwise return None
    rather than letting a 1000x value reach the agent.
    """
    raw = info.get("enterpriseToEbitda")
    fin_ccy = info.get("financialCurrency")
    disp_ccy = info.get("currency")

    # Happy path: same currency, value is sane → trust yfinance.
    if not fin_ccy or not disp_ccy or fin_ccy == disp_ccy:
        if raw is not None and 0 < raw < 100:
            return raw
        # Same-currency but absurd → drop it.
        if raw is not None and (raw <= 0 or raw >= 100):
            return None
        return raw

    # Cross-currency case (e.g. INFY: financialCurrency=USD, currency=INR).
    ev = info.get("enterpriseValue")
    ebitda = info.get("ebitda")
    if ev is None or ebitda is None or ebitda == 0:
        # Can't recompute; only return raw if it's at least sane.
        if raw is not None and 0 < raw < 100:
            return raw
        return None

    # Pull live FX rate from macro_snapshot.
    try:
        from flowtracker.store import FlowStore
        with FlowStore() as _s:
            macro = _s.get_macro_latest()
            fx = macro.usd_inr if macro and macro.usd_inr else None
    except Exception:
        fx = None

    if fx is None or fx <= 0:
        # No FX rate; refuse to publish a wrong number.
        if raw is not None and 0 < raw < 100:
            return raw
        return None

    # Convert EBITDA from financial currency to display currency.
    if fin_ccy == "USD" and disp_ccy == "INR":
        ebitda_inr = ebitda * fx
    elif fin_ccy == "INR" and disp_ccy == "USD":
        ebitda_inr = ebitda / fx
    else:
        # Some other cross-currency combo; bail.
        if raw is not None and 0 < raw < 100:
            return raw
        return None

    if ebitda_inr == 0:
        return None
    ratio = ev / ebitda_inr
    # Sanity-clamp: EV/EBITDA in [-50, 200] is plausible (negative for
    # loss-making, very-high for high-growth); anything outside is data junk.
    if ratio < -50 or ratio > 200:
        return None
    return round(ratio, 3)


# Candidate row labels in yfinance income_stmt for Net Premium Earned. Indian
# life insurers (HDFCLIFE, SBILIFE, ICICIPRULI, LICI) currently expose only
# "Total Revenue" / "Operating Revenue" — both are Schedule III revenue (which
# bundles MTM on policyholder funds and is NOT the clean underwriting top
# line). The fallback list below covers labels yfinance does use for some
# global insurers and would adopt if Indian coverage improved. See the audit
# at the head of this commit. When none of these rows exist in the frame, the
# returned value is None and the swap layer in
# ResearchDataAPI._apply_insurance_headline falls back to revenue with a
# data_quality_note.
_PREMIUM_EARNED_ROWS: tuple[str, ...] = (
    "Net Premiums Earned",
    "Total Premiums Earned",
    "Premiums Earned",
    "Premium Earned",
    "Net Premium Earned",
    "Premium Income Net",
    "Net Premium Income",
)


def _extract_premium_earned(df: Any, col: Any) -> float | None:
    """Probe an income-statement DataFrame for a Net-Premium-Earned-style row.

    Returns the raw rupee value (yfinance native units) or None if no
    candidate row is present. Caller is responsible for unit conversion.
    """
    for label in _PREMIUM_EARNED_ROWS:
        val = _safe_get(df, label, col)
        if val is not None:
            return val
    return None


class FundClient:
    """yfinance client for fundamentals data."""

    def __init__(self) -> None:
        self._ticker_cache: dict[str, tuple[float, yf.Ticker]] = {}
        self._info_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes

    def _ticker(self, symbol: str) -> yf.Ticker:
        yf_sym = nse_symbol(symbol)
        now = time.time()
        if yf_sym in self._ticker_cache:
            ts, ticker = self._ticker_cache[yf_sym]
            if now - ts < self._cache_ttl:
                return ticker
        ticker = yf.Ticker(yf_sym)
        self._ticker_cache[yf_sym] = (now, ticker)
        return ticker

    def _info(self, symbol: str) -> dict[str, Any]:
        yf_sym = nse_symbol(symbol)
        now = time.time()
        if yf_sym in self._info_cache:
            ts, info = self._info_cache[yf_sym]
            if now - ts < self._cache_ttl:
                return info
        ticker = self._ticker(symbol)
        info = ticker.info or {}
        if not info or info.get("quoteType") is None:
            raise YFinanceError(f"No data found for {symbol}")
        self._info_cache[yf_sym] = (now, info)
        return info

    # -- Live (no storage) --

    def get_live_snapshot(self, symbol: str) -> LiveSnapshot:
        """Fetch current ratios and metrics. Never stored."""
        info = self._info(symbol)
        return LiveSnapshot(
            symbol=symbol,
            company_name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            market_cap=info.get("marketCap"),
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            ev_ebitda=_ev_ebitda_currency_safe(info),
            dividend_yield=info.get("dividendYield"),
            roe=_to_pct(info.get("returnOnEquity")),
            roa=_to_pct(info.get("returnOnAssets")),
            gross_margin=_to_pct(info.get("grossMargins")),
            operating_margin=_to_pct(info.get("operatingMargins")),
            net_margin=_to_pct(info.get("profitMargins")),
            debt_to_equity=_div100(info.get("debtToEquity")),
            current_ratio=info.get("currentRatio"),
            free_cash_flow=info.get("freeCashflow"),
            revenue_growth=_to_pct(info.get("revenueGrowth")),
            earnings_growth=_to_pct(info.get("earningsGrowth")),
        )

    # -- Stored (fetched -> persisted) --

    def fetch_quarterly_results(self, symbol: str) -> list[QuarterlyResult]:
        """Fetch quarterly income data from yfinance (~5 quarters).

        For insurers, also probes for Net Premium Earned via
        `_extract_premium_earned`. yfinance's revenue rows for Indian life
        insurers (TotalRevenue / OperatingRevenue) are Schedule III revenue
        which bundles MTM on policyholder funds — not the underwriting top
        line. ``net_premium_earned`` stays None when no premium-style row is
        exposed; the read-side swap layer
        (`ResearchDataAPI._apply_insurance_headline`) handles the fallback.
        """
        ticker = self._ticker(symbol)
        df = ticker.get_income_stmt(freq="quarterly")
        if df is None or df.empty:
            return []

        results = []
        for col in df.columns:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            revenue = _safe_get(df, "TotalRevenue", col)
            gross_profit = _safe_get(df, "GrossProfit", col)
            operating_income = _safe_get(df, "OperatingIncome", col)
            net_income = _safe_get(df, "NetIncome", col)
            ebitda = _safe_get(df, "EBITDA", col)
            eps = _safe_get(df, "BasicEPS", col)
            eps_diluted = _safe_get(df, "DilutedEPS", col)
            # Insurance only — None for non-insurers (no such row in their
            # frames). yfinance doesn't currently expose this for Indian life
            # insurers either; included for forward compatibility.
            net_premium_earned = _extract_premium_earned(df, col)

            operating_margin = None
            if operating_income is not None and revenue and revenue != 0:
                operating_margin = operating_income / revenue

            net_margin = None
            if net_income is not None and revenue and revenue != 0:
                net_margin = net_income / revenue

            results.append(QuarterlyResult(
                symbol=symbol,
                quarter_end=date_str,
                revenue=revenue,
                gross_profit=gross_profit,
                operating_income=operating_income,
                net_income=net_income,
                ebitda=ebitda,
                eps=eps,
                eps_diluted=eps_diluted,
                operating_margin=operating_margin,
                net_margin=net_margin,
                net_premium_earned=net_premium_earned,
            ))
        return results

    def fetch_annual_net_premium_earned(self, symbol: str) -> dict[str, float]:
        """Probe yfinance annual income_stmt for Net Premium Earned, year-by-year.

        Returns ``{fiscal_year_end: net_premium_earned_in_crores}``. Empty when
        no premium-style row is present (the case today for HDFCLIFE, SBILIFE,
        ICICIPRULI, LICI — yfinance only exposes TotalRevenue / OperatingRevenue
        for these tickers, both of which are Schedule III "Revenue from
        operations" mixed with MTM on policyholder investment funds).

        Forward-compatible with future yfinance schema changes that surface
        Net Premium Earned via any of the labels in `_PREMIUM_EARNED_ROWS`.

        Values are converted to crores (yfinance returns raw rupees).
        """
        try:
            ticker = self._ticker(symbol)
            df = ticker.income_stmt
        except Exception:
            return {}
        if df is None or df.empty:
            return {}
        out: dict[str, float] = {}
        for col in df.columns:
            fy_end = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            raw = _extract_premium_earned(df, col)
            if raw is not None:
                cr = _to_cr(raw)
                if cr is not None:
                    out[fy_end] = cr
        return out

    def _latest_cash_flow(self, symbol: str) -> tuple[float | None, float | None]:
        """Fall back to annual cash flow statement when ``info`` fields are empty.

        ``info.get('freeCashflow')`` and ``info.get('operatingCashflow')`` are
        routinely ``None`` for NSE listings, but the annual cash-flow statement
        (``ticker.get_cash_flow(freq='yearly')``) reliably exposes
        ``FreeCashFlow`` / ``OperatingCashFlow`` rows. Returns ``(ocf, fcf)`` in
        raw rupees; callers still need to convert to crores.
        """
        try:
            df = self._ticker(symbol).get_cash_flow(freq="yearly")
        except Exception:
            return None, None
        if df is None or df.empty or len(df.columns) == 0:
            return None, None
        latest_col = df.columns[0]

        def _extract(row: str) -> float | None:
            try:
                val = df.loc[row, latest_col]
            except (KeyError, TypeError):
                return None
            if val is None or str(val) == "nan":
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        return _extract("OperatingCashFlow"), _extract("FreeCashFlow")

    def fetch_valuation_snapshot(self, symbol: str) -> ValuationSnapshot:
        """Fetch today's valuation metrics for storage."""
        info = self._info(symbol)
        ocf_raw = info.get("operatingCashflow")
        fcf_raw = info.get("freeCashflow")
        if ocf_raw is None or fcf_raw is None:
            ocf_fallback, fcf_fallback = self._latest_cash_flow(symbol)
            if ocf_raw is None:
                ocf_raw = ocf_fallback
            if fcf_raw is None:
                fcf_raw = fcf_fallback
        # pegRatio is frequently missing for NSE listings; trailingPegRatio is
        # the documented fallback and populated more consistently.
        peg = info.get("pegRatio")
        if peg is None:
            peg = info.get("trailingPegRatio")
        return ValuationSnapshot(
            symbol=symbol,
            date=date.today().isoformat(),
            # Price context
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            market_cap=_to_cr(info.get("marketCap")),
            enterprise_value=_to_cr(info.get("enterpriseValue")),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            beta=info.get("beta"),
            # Valuation multiples
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            ev_ebitda=_ev_ebitda_currency_safe(info),
            ev_revenue=info.get("enterpriseToRevenue"),
            ps_ratio=info.get("priceToSalesTrailing12Months"),
            peg_ratio=peg,
            # Profitability
            gross_margin=_to_pct(info.get("grossMargins")),
            operating_margin=_to_pct(info.get("operatingMargins")),
            net_margin=_to_pct(info.get("profitMargins")),
            roe=_to_pct(info.get("returnOnEquity")),
            roa=_to_pct(info.get("returnOnAssets")),
            # Growth
            revenue_growth=_to_pct(info.get("revenueGrowth")),
            earnings_growth=_to_pct(info.get("earningsGrowth")),
            earnings_quarterly_growth=_to_pct(info.get("earningsQuarterlyGrowth")),
            # Yield
            dividend_yield=info.get("dividendYield"),
            # Balance sheet
            debt_to_equity=_div100(info.get("debtToEquity")),
            current_ratio=info.get("currentRatio"),
            total_cash=_to_cr(info.get("totalCash")),
            total_debt=_to_cr(info.get("totalDebt")),
            book_value_per_share=info.get("bookValue"),
            # Cash flow
            free_cash_flow=_to_cr(fcf_raw),
            operating_cash_flow=_to_cr(ocf_raw),
            # Per-share
            revenue_per_share=info.get("revenuePerShare"),
            cash_per_share=info.get("totalCashPerShare"),
            # Liquidity
            avg_volume=info.get("averageVolume"),
            float_shares=info.get("floatShares"),
            shares_outstanding=info.get("sharesOutstanding"),
        )

    def fetch_yahoo_peers(self, symbol: str) -> list[dict]:
        """Fetch Yahoo Finance recommended similar stocks.

        Returns list of dicts: [{peer_symbol: str, score: float}, ...].
        Score: lower = more similar (0-1 range typical).
        Returns empty list on failure (404, timeout, parse error).
        """
        import httpx

        yf_sym = nse_symbol(symbol)
        url = f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{yf_sym}"
        try:
            resp = httpx.get(url, timeout=10.0, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()

            results = data.get("finance", {}).get("result", [])
            if not results:
                return []

            recommended = results[0].get("recommendedSymbols", [])
            peers = []
            for item in recommended:
                raw_sym = item.get("symbol", "")
                score = item.get("score", 0)
                # Strip exchange suffix (.NS, .BO)
                peer_sym = raw_sym.replace(".NS", "").replace(".BO", "")
                if peer_sym:
                    peers.append({"peer_symbol": peer_sym, "score": score})
            return peers
        except Exception:
            return []

    def fetch_quarterly_bs_cf(self, symbol: str) -> dict:
        """Fetch quarterly balance sheet and cash flow from yfinance.
        Returns {'balance_sheet': [list of quarter dicts], 'cash_flow': [list of quarter dicts]}
        Values converted from raw INR to crores (÷1e7).
        """
        ticker = self._ticker(symbol)
        result = {"symbol": symbol.upper(), "balance_sheet": [], "cash_flow": []}

        # -- Balance Sheet --
        try:
            bs = ticker.quarterly_balance_sheet
            if bs is not None and not bs.empty:
                _BS_FIELDS = {
                    "Total Assets": "total_assets",
                    "Total Debt": "total_debt",
                    "Long Term Debt": "long_term_debt",
                    "Stockholders Equity": "stockholders_equity",
                    "Cash And Cash Equivalents": "cash_and_equivalents",
                    "Net Debt": "net_debt",
                    "Investments And Advances": "investments",
                    "Net PPE": "net_ppe",
                    "Ordinary Shares Number": "shares_outstanding",
                    "Total Liabilities Net Minority Interest": "total_liabilities",
                    "Minority Interest": "minority_interest",
                }
                for col in bs.columns:
                    quarter_end = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                    row_data = {"quarter_end": quarter_end}
                    has_data = False
                    for yf_field, our_field in _BS_FIELDS.items():
                        val = _safe_get(bs, yf_field, col)
                        if val is not None:
                            # Convert to crores (shares_outstanding stays as-is)
                            if our_field != "shares_outstanding":
                                val = round(val / 1e7, 2)
                            else:
                                val = round(val)
                            row_data[our_field] = val
                            has_data = True
                    if has_data:
                        result["balance_sheet"].append(row_data)
        except Exception:
            pass

        # -- Cash Flow --
        try:
            cf = ticker.quarterly_cashflow
            if cf is not None and not cf.empty:
                _CF_FIELDS = {
                    "Operating Cash Flow": "operating_cash_flow",
                    "Free Cash Flow": "free_cash_flow",
                    "Capital Expenditure": "capital_expenditure",
                    "Investing Cash Flow": "investing_cash_flow",
                    "Financing Cash Flow": "financing_cash_flow",
                    "Change In Working Capital": "change_in_working_capital",
                    "Depreciation And Amortization": "depreciation",
                    "Cash Dividends Paid": "dividends_paid",
                    "Net Income From Continuing Operations": "net_income",
                }
                for col in cf.columns:
                    quarter_end = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                    row_data = {"quarter_end": quarter_end}
                    has_data = False
                    for yf_field, our_field in _CF_FIELDS.items():
                        val = _safe_get(cf, yf_field, col)
                        if val is not None:
                            val = round(val / 1e7, 2)  # Convert to crores
                            row_data[our_field] = val
                            has_data = True
                    if has_data:
                        result["cash_flow"].append(row_data)
        except Exception:
            pass

        return result

    def compute_historical_pe(
        self, symbol: str, annual_eps: list, weekly_prices: list[tuple[str, float, int]] | None = None
    ) -> list:
        """Compute historical weekly P/E from annual EPS + weekly prices.

        Args:
            symbol: Stock symbol (e.g., 'TECHM')
            annual_eps: List of AnnualEPS objects with fiscal_year_end and eps fields
            weekly_prices: Optional pre-fetched list of (date_iso, close_price, volume) tuples.
                          If None, fetches from yfinance.

        Returns:
            List of ValuationSnapshot objects with date, price, and pe_trailing populated.
        """
        if not annual_eps:
            return []

        if weekly_prices is None:
            weekly_prices = self.fetch_weekly_prices(symbol)

        if not weekly_prices:
            return []

        # Sort annual EPS by fiscal year end (ascending)
        sorted_eps = sorted(annual_eps, key=lambda a: a.fiscal_year_end)

        snapshots = []
        for date_str, close_price, _volume in weekly_prices:
            if close_price <= 0:
                continue

            # Find the most recent annual EPS as of this date
            # (fiscal year end <= this date)
            applicable_eps = None
            for ae in sorted_eps:
                if ae.fiscal_year_end <= date_str:
                    applicable_eps = ae
                else:
                    break  # sorted ascending, so no need to continue

            if applicable_eps is None or applicable_eps.eps <= 0:
                continue

            pe = close_price / applicable_eps.eps

            # Sanity check: skip extreme P/E values (likely data errors)
            if pe > 200 or pe < 1:
                continue

            snapshots.append(ValuationSnapshot(
                symbol=symbol,
                date=date_str,
                price=close_price,
                pe_trailing=pe,
            ))

        return snapshots

    def fetch_weekly_prices(self, symbol: str, period: str = "10y") -> list[tuple[str, float, int]]:
        """Fetch weekly closing prices and volume for historical P/E computation.
        Returns list of (date_iso, close_price, volume) tuples.
        """
        ticker = self._ticker(symbol)
        hist = ticker.history(period=period, interval="1wk")
        if hist is None or hist.empty:
            return []
        return [
            (idx.strftime("%Y-%m-%d"), float(row["Close"]), int(row.get("Volume", 0)))
            for idx, row in hist.iterrows()
            if row["Close"] is not None and str(row["Close"]) != "nan"
        ]
