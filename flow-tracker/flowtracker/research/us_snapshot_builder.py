"""Build ``us_company_snapshot`` from existing US DB tables + yfinance ``.info``.

US analogue of :func:`flowtracker.research.snapshot_builder.build_company_snapshot`.
Assembles one denormalized row per US listing — the single source of truth for
US peers / benchmarks / valuation-matrix — from:

  * ``us_valuation_snapshot`` (latest row): cmp / market_cap / enterprise_value /
    pe_trailing / pe_forward / pb / div_yield / beta / operating_margin /
    net_margin / roe. These are already unit-normalized (USD millions for
    aggregates, percent form for margins/roe) by the WS-2 ingest adapter.
  * yfinance ``.info`` (via ``FundClient()._info(symbol, Market(market))``):
    name, peg, 52-week high/low, current_ratio, debt_to_equity, revenue_growth,
    earnings_growth, roa. yfinance raw fractions are normalized the same way the
    India snapshot does (``_to_pct`` for percentages, ``_div100`` for D/E).
  * Computed from ``us_annual_financials``: ev_ebitda (EV / ebitda), roce, roic,
    fcf_yield. Mirrors the India ``snapshot_builder._build_computed`` formulas;
    US aggregates are USD millions so no crore conversion is applied.

``industry`` is the GRANULAR yfinance industry captured on ``symbol_registry``
(e.g. 'Semiconductors', 'Banks - Diversified') — the same label the data_api US
sector resolver prefers. Falls back to the ``.info`` industry / coarse sector.

Upsert is COALESCE-safe: a metric whose inputs are absent is left out of the
``fields`` dict and the existing stored value is preserved. No India tables are
touched.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)

_US_MARKETS = ("NASDAQ", "NYSE")


def _resolve_market(symbol: str, store: FlowStore) -> str:
    """Return the registered US market for ``symbol`` (NASDAQ/NYSE), default NASDAQ."""
    for market in _US_MARKETS:
        if store.get_symbol_registry_entry(symbol, market):
            return market
    return "NASDAQ"


def _from_valuation(symbol: str, market: str, store: FlowStore) -> dict:
    """Pull the market-relevant fields from the latest us_valuation_snapshot row."""
    rows = store.get_us_valuation_snapshot(symbol, market)
    if not rows:
        return {}
    latest = rows[0]  # get_us_valuation_snapshot returns date DESC
    return {
        "cmp": latest.get("price"),
        "market_cap": latest.get("market_cap"),
        "pe_trailing": latest.get("pe_trailing"),
        "pe_forward": latest.get("pe_forward"),
        "pb": latest.get("pb"),
        "div_yield": latest.get("dividend_yield"),
        "operating_margin": latest.get("operating_margin"),
        "net_margin": latest.get("net_margin"),
        "roe": latest.get("roe"),
        "beta": latest.get("beta"),
    }


def _from_info(symbol: str, market: str) -> dict:
    """Pull name + ratios yfinance ``.info`` exposes that the snapshot lacks.

    Normalized to the same units the India snapshot uses: ``_to_pct`` for
    percentages (revenue/earnings growth, roa), ``_div100`` for debtToEquity.
    Non-fatal — returns {} on any error so a missing network call never blocks
    the snapshot build.
    """
    try:
        from flowtracker.fund_client import FundClient, _div100, _to_pct
        from flowtracker.market import Market

        info = FundClient()._info(symbol, Market(market))
    except Exception:  # pragma: no cover — network/lookup failure is non-fatal
        return {}
    if not info:
        return {}

    return {
        "name": info.get("longName") or info.get("shortName"),
        "peg": info.get("pegRatio") or info.get("trailingPegRatio"),
        "high_52w": info.get("fiftyTwoWeekHigh"),
        "low_52w": info.get("fiftyTwoWeekLow"),
        "current_ratio": info.get("currentRatio"),
        "debt_to_equity": _div100(info.get("debtToEquity")),
        "revenue_growth": _to_pct(info.get("revenueGrowth")),
        "earnings_growth": _to_pct(info.get("earningsGrowth")),
        "roa": _to_pct(info.get("returnOnAssets")),
    }


def _compute_ev_ebitda(symbol: str, market: str, store: FlowStore) -> float | None:
    """EV / EBITDA from us_valuation_snapshot.enterprise_value and annual EBITDA.

    For US listings EV and EBITDA are both reported in USD (no cross-currency
    inflation as with ADR-listed Indian names), so EV/EBITDA = EV / operating_
    profit-proxy. We use ``operating_profit + depreciation`` as the EBITDA proxy
    from us_annual_financials when EBITDA isn't stored directly.
    """
    vals = store.get_us_valuation_snapshot(symbol, market)
    if not vals:
        return None
    ev = vals[0].get("enterprise_value")
    if not ev or ev <= 0:
        return None
    annuals = store.get_us_annual_financials(symbol, market)
    if not annuals:
        return None
    latest = annuals[0]  # fiscal_year DESC
    op = latest.get("operating_profit")
    dep = latest.get("depreciation") or 0
    if op is None:
        return None
    ebitda = op + dep
    if ebitda <= 0:
        return None
    return round(ev / ebitda, 2)


def _compute_returns(symbol: str, market: str, store: FlowStore) -> dict:
    """Compute roce, roic, fcf_yield from us_annual_financials (+ latest mcap).

    Mirrors ``snapshot_builder._build_computed`` but on US aggregates (USD
    millions, no crore conversion). Only keys whose inputs are all present are
    returned; absent metrics are left for the COALESCE-safe upsert to preserve.
    """
    data: dict = {}
    annuals = store.get_us_annual_financials(symbol, market)
    if not annuals:
        return data
    latest = annuals[0]

    op = latest.get("operating_profit")
    pbt = latest.get("profit_before_tax") or 0
    tax = latest.get("tax") or 0
    equity_capital = latest.get("equity_capital") or 0
    reserves = latest.get("reserves") or 0
    borrowings = latest.get("borrowings") or 0
    cash = latest.get("cash_and_bank")
    if cash is None:
        cash = latest.get("total_cash") or 0

    # --- ROCE = EBIT / capital employed ---
    # capital_employed = total_equity + total_debt (or equity_capital+reserves+borrowings)
    total_equity = latest.get("total_equity")
    total_debt = latest.get("total_debt")
    if op is not None and op != 0:
        if total_equity is not None and total_debt is not None:
            capital_employed = total_equity + total_debt
        else:
            capital_employed = (equity_capital + reserves) + borrowings
        if capital_employed and capital_employed > 0:
            data["roce"] = round(op / capital_employed * 100, 2)

    # --- ROIC = NOPAT / invested_capital ---
    if op is not None and op != 0:
        eff_tax_rate = (tax / pbt) if pbt and pbt > 0 else 0.25
        if eff_tax_rate < 0:
            eff_tax_rate = 0.25
        if eff_tax_rate > 1:
            eff_tax_rate = 1.0
        nopat = op * (1 - eff_tax_rate)
        invested_capital = (equity_capital + reserves) + borrowings - cash
        if invested_capital and invested_capital > 0:
            data["roic"] = round(nopat / invested_capital * 100, 2)

    # --- FCF yield = (CFO - capex) / mcap * 100 ---
    mcap = None
    vals = store.get_us_valuation_snapshot(symbol, market)
    if vals:
        mcap = vals[0].get("market_cap")
    if mcap and mcap > 0:
        cfo = latest.get("operating_cash_flow")
        fcf = latest.get("free_cash_flow")
        if fcf is not None:
            data["fcf_yield"] = round(fcf / mcap * 100, 2)
        elif cfo is not None and len(annuals) >= 2:
            prev = annuals[1]
            nb_t = latest.get("net_block") or 0
            nb_t1 = prev.get("net_block") or 0
            cwip_t = latest.get("cwip") or 0
            cwip_t1 = prev.get("cwip") or 0
            dep = latest.get("depreciation") or 0
            capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + dep
            data["fcf_yield"] = round((cfo - capex) / mcap * 100, 2)

    return data


def _resolve_industry(symbol: str, market: str, store: FlowStore, info_fields: dict) -> str | None:
    """Granular registry industry, falling back to .info industry / coarse sector."""
    entry = store.get_symbol_registry_entry(symbol, market) or {}
    granular = (entry.get("industry") or "").strip()
    if granular:
        return granular
    # .info already fetched upstream — but name is the only field we kept; the
    # registry should carry industry. Fall back to coarse sector/gics.
    for raw in (entry.get("sector"), entry.get("gics")):
        if raw and raw.strip():
            return raw.strip()
    return None


def build_us_company_snapshot(symbol: str, store: FlowStore) -> bool:
    """Build/update ``us_company_snapshot`` for a US listing.

    Assembles the row from us_valuation_snapshot + yfinance ``.info`` +
    computed (ev_ebitda / roce / roic / fcf_yield from us_annual_financials).
    Returns True if any data was written.
    """
    symbol = symbol.upper()
    market = _resolve_market(symbol, store)

    fields: dict = {"currency": "USD"}
    fields.update(_from_valuation(symbol, market, store))
    info_fields = _from_info(symbol, market)
    fields.update(info_fields)

    ev_ebitda = _compute_ev_ebitda(symbol, market, store)
    if ev_ebitda is not None:
        fields["ev_ebitda"] = ev_ebitda
    fields.update(_compute_returns(symbol, market, store))

    industry = _resolve_industry(symbol, market, store, info_fields)
    if industry:
        fields["industry"] = industry

    # Drop keys whose values are None so the COALESCE-safe upsert preserves any
    # previously-stored value rather than re-nulling it.
    populated = {k: v for k, v in fields.items() if v is not None}
    # Always carry the identity/currency triplet even if everything else is empty.
    if len(populated) <= 1:  # only 'currency'
        logger.info("[us_snapshot] %s: no data available, skipping", symbol)
        return False

    store.upsert_us_company_snapshot(symbol, market, populated)
    logger.info(
        "[us_snapshot] %s (%s): built (%d fields)", symbol, market, len(populated),
    )
    return True
