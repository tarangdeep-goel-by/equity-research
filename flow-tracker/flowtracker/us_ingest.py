"""US ingestion wrappers (US add-on, Phase 3.2).

Thin fetch-and-store helpers that pull US equity data through the EXISTING
market-aware clients (``FundClient``, ``EstimatesClient``) and route the results
into the ``us_*`` tables via the ``UsMarketMixin`` upserts.

No new fetch protocol is introduced: yfinance access reuses ``FundClient``'s
ticker/info machinery, and estimates reuse ``EstimatesClient.fetch_estimates``.
Every fetch defaults to ``Market.NASDAQ`` so US tickers format as bare symbols
(no ``.NS`` suffix) per ``market_symbol``.

Magnitude convention (must match ``_USD_VALIDATION_RULES`` in
``store_domains/_shared.py``): monetary aggregates (market_cap, enterprise_value,
total_cash, total_debt, free_cash_flow) are stored in **USD millions** via
``to_aggregate(raw_usd, Market.NASDAQ)`` (÷1e6). Per-share / price values and
ratios / percentages are stored **raw** (price, pe_*, pb, beta, margins, roe,
dividend_yield). Currency is always ``'USD'``, market ``'NASDAQ'`` (or the
passed US market).
"""

from __future__ import annotations

from datetime import date

from flowtracker.estimates_client import EstimatesClient
from flowtracker.fund_client import FundClient, _to_pct
from flowtracker.market import Market, to_aggregate


def _mn(raw: float | None, market: Market) -> float | None:
    """Raw USD → USD millions (÷1e6 for US markets). ``None`` passes through."""
    return to_aggregate(raw, market)


# ---------------------------------------------------------------------------
# 1. US daily prices  → us_daily_prices
# ---------------------------------------------------------------------------

def fetch_us_daily_prices(
    symbol: str,
    market: Market = Market.NASDAQ,
    period: str = "1y",
    client: FundClient | None = None,
) -> list[dict]:
    """Fetch daily OHLCV + adj_close for a US ticker via yfinance.

    Reuses ``FundClient``'s cached, market-aware ``yf.Ticker`` (bare US ticker,
    no suffix). Returns rows keyed for ``store.upsert_us_daily_prices``:
    ``symbol, market, date, open, high, low, close, volume, adj_close``.
    Currency is implicit USD for the daily-prices table (no currency column).
    """
    client = client or FundClient()
    ticker = client._ticker(symbol, market)
    # auto_adjust=False keeps raw OHLC and exposes a separate "Adj Close" column.
    hist = ticker.history(period=period, auto_adjust=False)
    if hist is None or getattr(hist, "empty", True):
        return []

    sym = symbol.upper()
    mkt = market.value
    rows: list[dict] = []
    for idx, row in hist.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        close = row.get("Close")
        if close is None or str(close) == "nan":
            continue
        adj = row.get("Adj Close")
        if adj is None or str(adj) == "nan":
            adj = close
        rows.append({
            "symbol": sym,
            "market": mkt,
            "date": date_str,
            "open": _f(row.get("Open")),
            "high": _f(row.get("High")),
            "low": _f(row.get("Low")),
            "close": _f(close),
            "volume": _i(row.get("Volume")),
            "adj_close": _f(adj),
        })
    return rows


def fetch_and_store_us_daily_prices(
    store,
    symbol: str,
    market: Market = Market.NASDAQ,
    period: str = "1y",
    client: FundClient | None = None,
) -> int:
    """Fetch US daily prices and upsert into ``us_daily_prices``. Returns count."""
    rows = fetch_us_daily_prices(symbol, market=market, period=period, client=client)
    return store.upsert_us_daily_prices(rows)


# ---------------------------------------------------------------------------
# 2. US valuation snapshot  → us_valuation_snapshot
# ---------------------------------------------------------------------------

def fetch_us_valuation_snapshot(
    symbol: str,
    market: Market = Market.NASDAQ,
    client: FundClient | None = None,
) -> dict | None:
    """Fetch today's US valuation snapshot from yfinance ``info``.

    Built directly from market-aware ``FundClient._info(symbol, market)`` rather
    than ``fetch_valuation_snapshot`` (which is India-default and crore-converts).
    Monetary fields are scaled to USD millions; ratios / per-share stay raw.
    Returns a row keyed for ``store.upsert_us_valuation_snapshot`` or ``None`` if
    no data is available.
    """
    client = client or FundClient()
    info = client._info(symbol, market)
    if not info:
        return None

    fcf_raw = info.get("freeCashflow")

    return {
        "symbol": symbol.upper(),
        "market": market.value,
        "currency": "USD",
        "date": date.today().isoformat(),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": _mn(info.get("marketCap"), market),
        "enterprise_value": _mn(info.get("enterpriseValue"), market),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "total_cash": _mn(info.get("totalCash"), market),
        "total_debt": _mn(info.get("totalDebt"), market),
        "free_cash_flow": _mn(fcf_raw, market),
        "operating_margin": _to_pct(info.get("operatingMargins")),
        "net_margin": _to_pct(info.get("profitMargins")),
        "roe": _to_pct(info.get("returnOnEquity")),
    }


def fetch_and_store_us_valuation_snapshot(
    store,
    symbol: str,
    market: Market = Market.NASDAQ,
    client: FundClient | None = None,
) -> int:
    """Fetch US valuation snapshot and upsert. Returns count (0 or 1)."""
    row = fetch_us_valuation_snapshot(symbol, market=market, client=client)
    if row is None:
        return 0
    return store.upsert_us_valuation_snapshot([row])


# ---------------------------------------------------------------------------
# 3. US consensus estimates  → us_consensus_estimates
# ---------------------------------------------------------------------------

def fetch_us_consensus_estimates(
    symbol: str,
    market: Market = Market.NASDAQ,
    client: EstimatesClient | None = None,
) -> dict | None:
    """Fetch analyst consensus for a US ticker via the market-aware
    ``EstimatesClient.fetch_estimates``.

    Maps the returned ``ConsensusEstimate`` model to the
    ``us_consensus_estimates`` upsert keys. Target prices / EPS are raw USD.
    Returns ``None`` when yfinance has no estimates.
    """
    client = client or EstimatesClient()
    est = client.fetch_estimates(symbol, market=market)
    if est is None:
        return None
    return {
        "symbol": symbol.upper(),
        "market": market.value,
        "currency": "USD",
        "date": est.date,
        "target_mean": est.target_mean,
        "target_median": est.target_median,
        "num_analysts": est.num_analysts,
        "recommendation": est.recommendation,
        "forward_pe": est.forward_pe,
        "forward_eps": est.forward_eps,
        "eps_current_year": est.eps_current_year,
        "eps_next_year": est.eps_next_year,
        "earnings_growth": est.earnings_growth,
        "current_price": est.current_price,
    }


def fetch_and_store_us_consensus_estimates(
    store,
    symbol: str,
    market: Market = Market.NASDAQ,
    client: EstimatesClient | None = None,
) -> int:
    """Fetch US consensus estimates and upsert. Returns count (0 or 1)."""
    row = fetch_us_consensus_estimates(symbol, market=market, client=client)
    if row is None:
        return 0
    return store.upsert_us_consensus_estimates([row])


# ---------------------------------------------------------------------------
# small coercion helpers
# ---------------------------------------------------------------------------

def _f(val) -> float | None:
    if val is None or str(val) == "nan":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _i(val) -> int | None:
    f = _f(val)
    return int(f) if f is not None else None
