"""Historical Analog Agent: retrieval + scoring infrastructure.

Turns the 10-year history already in FlowStore (16 yrs daily OHLCV, 16 yrs
quarterly shareholding, 10 yrs quarterly financials, 24 yrs annual, 16 yrs
insider, 16 yrs pledge, 21 yrs PE via screener_charts) into a
retrieval space for pattern-matching current setups against past ones.

Three responsibilities:
  1. **compute_feature_vector(symbol, as_of_date)** — build a 16-dim
     fingerprint. Every input is strictly filtered to date <= as_of_date
     so an analog at (X, 2020-Q1) never leaks post-2020 info.
  2. **compute_forward_returns(symbol, as_of_date)** — 3m/6m/12m forward
     returns read from daily_stock_data.adj_close (Sprint 0 split/bonus
     adjusted). Raw close would phantom-distort every cohort member.
  3. **retrieve_top_k_analogs(target_symbol, target_date, target_features, k)**
     — z-scored Euclidean distance across continuous features, hard-filter
     to same/adjacent industry + same mcap bucket, exclude any rows within
     2 years of target_date (data-leakage guard).

Consumed by the 3 MCP tools (get_historical_analogs, get_analog_cohort_stats,
get_setup_feature_vector) registered in research/tools.py.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any

from flowtracker.store import FlowStore

_CONT_FEATURES = (
    "pe_trailing", "pe_percentile_10y",
    "roce_current", "roce_3yr_delta",
    "revenue_cagr_3yr", "opm_trend",
    "promoter_pct", "fii_pct", "fii_delta_2q",
    "mf_pct", "mf_delta_2q", "pledge_pct",
    "price_vs_sma200", "delivery_pct_6m", "rsi_14",
)

_CAT_FEATURES = ("industry", "mcap_bucket")


# ---------------------------------------------------------------------------
# Feature vector
# ---------------------------------------------------------------------------


def _qtr_offset(qtr: str, n_quarters: int) -> str:
    """Return a quarter-end `n_quarters` earlier than `qtr` (shift by 91*n days, rounded)."""
    y, m, d = (int(x) for x in qtr.split("-"))
    # Quarter ends: Mar 31, Jun 30, Sep 30, Dec 31. Shift by 3-month blocks.
    for _ in range(n_quarters):
        if m == 3:
            y, m, d = y - 1, 12, 31
        elif m == 6:
            m, d = 3, 31
        elif m == 9:
            m, d = 6, 30
        elif m == 12:
            m, d = 9, 30
        else:
            # Non-standard — fall back to approx 91 days
            dt = date(y, m, d) - timedelta(days=91)
            y, m, d = dt.year, dt.month, dt.day
    return f"{y:04d}-{m:02d}-{d:02d}"


def _latest_shareholding_pct(store: FlowStore, symbol: str, category: str, as_of: str) -> float | None:
    row = store._conn.execute(
        "SELECT percentage FROM shareholding "
        "WHERE symbol = ? AND category = ? AND quarter_end <= ? "
        "ORDER BY quarter_end DESC LIMIT 1",
        (symbol.upper(), category, as_of),
    ).fetchone()
    return row["percentage"] if row else None


def _pct_at_or_before(store: FlowStore, symbol: str, category: str, target_qtr: str) -> float | None:
    """Shareholding pct at or immediately before target_qtr."""
    return _latest_shareholding_pct(store, symbol, category, target_qtr)


def _pe_percentile(store: FlowStore, symbol: str, as_of: str, years: int = 10) -> float | None:
    """Percentile rank of as_of PE within symbol's trailing `years` PE series
    from screener_charts (chart_type='pe')."""
    cutoff = (date.fromisoformat(as_of) - timedelta(days=years * 365)).isoformat()
    rows = store._conn.execute(
        "SELECT date, value FROM screener_charts "
        "WHERE symbol = ? AND chart_type = 'pe' "
        "AND date >= ? AND date <= ? ORDER BY date",
        (symbol.upper(), cutoff, as_of),
    ).fetchall()
    if len(rows) < 8:
        return None
    values = [r["value"] for r in rows if r["value"] is not None]
    if not values:
        return None
    current = values[-1]
    below = sum(1 for v in values if v <= current)
    return round(below / len(values) * 100, 2)


def _pe_trailing_at(store: FlowStore, symbol: str, as_of: str) -> float | None:
    row = store._conn.execute(
        "SELECT value FROM screener_charts WHERE symbol = ? AND chart_type = 'pe' "
        "AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol.upper(), as_of),
    ).fetchone()
    return row["value"] if row else None


def _roce_at(store: FlowStore, symbol: str, as_of: str, years_back: int = 0) -> float | None:
    """ROCE from annual_financials. years_back=0 for latest FY<=as_of; 3 for 3-yr-prior."""
    # Compute approximate target fiscal year
    target_fy_end = date.fromisoformat(as_of) - timedelta(days=years_back * 365)
    row = store._conn.execute(
        "SELECT total_assets, net_income, borrowings, reserves, equity_capital "
        "FROM annual_financials WHERE symbol = ? AND fiscal_year_end <= ? "
        "ORDER BY fiscal_year_end DESC LIMIT 1",
        (symbol.upper(), target_fy_end.isoformat()),
    ).fetchone()
    if not row or not row["net_income"]:
        return None
    capital_employed = (row["borrowings"] or 0) + (row["reserves"] or 0) + (row["equity_capital"] or 0)
    if capital_employed <= 0:
        return None
    return round(row["net_income"] / capital_employed * 100, 2)


def _revenue_cagr_3yr(store: FlowStore, symbol: str, as_of: str) -> float | None:
    rows = store._conn.execute(
        "SELECT fiscal_year_end, revenue FROM annual_financials WHERE symbol = ? "
        "AND fiscal_year_end <= ? AND revenue IS NOT NULL "
        "ORDER BY fiscal_year_end DESC LIMIT 4",
        (symbol.upper(), as_of),
    ).fetchall()
    if len(rows) < 4:
        return None
    latest, earliest = rows[0]["revenue"], rows[3]["revenue"]
    if earliest is None or earliest <= 0 or latest is None:
        return None
    return round(((latest / earliest) ** (1 / 3) - 1) * 100, 2)


def _opm_trend(store: FlowStore, symbol: str, as_of: str) -> float | None:
    """OPM trend = slope across last 8 quarters (pp per quarter)."""
    rows = store._conn.execute(
        "SELECT quarter_end, operating_margin FROM quarterly_results "
        "WHERE symbol = ? AND quarter_end <= ? AND operating_margin IS NOT NULL "
        "ORDER BY quarter_end DESC LIMIT 8",
        (symbol.upper(), as_of),
    ).fetchall()
    if len(rows) < 4:
        return None
    # Linear slope via simple least-squares; x = quarter index (0 = earliest)
    ys = [r["operating_margin"] for r in reversed(rows)]
    n = len(ys)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    return round(num / den, 3) if den else None


def _price_vs_sma200(store: FlowStore, symbol: str, as_of: str) -> float | None:
    rows = store._conn.execute(
        "SELECT COALESCE(adj_close, close) AS px FROM daily_stock_data "
        "WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 200",
        (symbol.upper(), as_of),
    ).fetchall()
    if len(rows) < 200:
        return None
    closes = [r["px"] for r in rows]
    sma200 = sum(closes) / 200
    if sma200 <= 0:
        return None
    return round(closes[0] / sma200, 3)


def _rsi_14(store: FlowStore, symbol: str, as_of: str) -> float | None:
    rows = store._conn.execute(
        "SELECT COALESCE(adj_close, close) AS px FROM daily_stock_data "
        "WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 15",
        (symbol.upper(), as_of),
    ).fetchall()
    if len(rows) < 15:
        return None
    closes = [r["px"] for r in rows]  # newest first
    gains, losses = [], []
    for i in range(14):
        diff = closes[i] - closes[i + 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains) / 14
    avg_l = sum(losses) / 14
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)


def _delivery_pct_6m(store: FlowStore, symbol: str, as_of: str) -> float | None:
    cutoff = (date.fromisoformat(as_of) - timedelta(days=180)).isoformat()
    row = store._conn.execute(
        "SELECT AVG(delivery_pct) AS avg_dp FROM daily_stock_data "
        "WHERE symbol = ? AND date BETWEEN ? AND ? AND delivery_pct IS NOT NULL",
        (symbol.upper(), cutoff, as_of),
    ).fetchone()
    return round(row["avg_dp"], 2) if row and row["avg_dp"] is not None else None


def _industry(store: FlowStore, symbol: str) -> str | None:
    """Current industry from index_constituents. Point-in-time industry
    history isn't tracked; current is a reasonable proxy."""
    row = store._conn.execute(
        "SELECT industry FROM index_constituents "
        "WHERE symbol = ? AND industry IS NOT NULL LIMIT 1",
        (symbol.upper(),),
    ).fetchone()
    return row["industry"] if row else None


def _mcap_bucket(store: FlowStore, symbol: str, as_of: str) -> str | None:
    """Approximate mcap bucket from adj_close × shares_outstanding.
    Buckets: largecap (>₹20,000 Cr), midcap (₹5,000–20,000 Cr), smallcap (<₹5,000 Cr)."""
    px_row = store._conn.execute(
        "SELECT COALESCE(adj_close, close) AS px FROM daily_stock_data "
        "WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol.upper(), as_of),
    ).fetchone()
    if not px_row:
        return None
    shares_row = store._conn.execute(
        "SELECT shares_outstanding FROM quarterly_balance_sheet "
        "WHERE symbol = ? AND quarter_end <= ? AND shares_outstanding IS NOT NULL "
        "ORDER BY quarter_end DESC LIMIT 1",
        (symbol.upper(), as_of),
    ).fetchone()
    if not shares_row or not shares_row["shares_outstanding"]:
        return None
    mcap_cr = (px_row["px"] * shares_row["shares_outstanding"]) / 1e7
    if mcap_cr >= 20000:
        return "largecap"
    if mcap_cr >= 5000:
        return "midcap"
    return "smallcap"


def _pledge_pct(store: FlowStore, symbol: str, as_of: str) -> float | None:
    row = store._conn.execute(
        "SELECT pledge_pct FROM promoter_pledge "
        "WHERE symbol = ? AND quarter_end <= ? ORDER BY quarter_end DESC LIMIT 1",
        (symbol.upper(), as_of),
    ).fetchone()
    return row["pledge_pct"] if row else None


def compute_feature_vector(store: FlowStore, symbol: str, as_of_date: str) -> dict[str, Any]:
    """Build the 16-feature vector for (symbol, as_of_date).

    Strict temporal cutoff: every query uses `<= as_of_date`. Any field that
    can't be computed (missing data) is None; consumers handle None as
    "feature unavailable" rather than failing.
    """
    symbol = symbol.upper()

    promoter = _pct_at_or_before(store, symbol, "Promoter", as_of_date)
    fii_now = _pct_at_or_before(store, symbol, "FII", as_of_date)
    mf_now = _pct_at_or_before(store, symbol, "MF", as_of_date)
    fii_2q = _pct_at_or_before(store, symbol, "FII", _qtr_offset(as_of_date, 2))
    mf_2q = _pct_at_or_before(store, symbol, "MF", _qtr_offset(as_of_date, 2))

    roce_now = _roce_at(store, symbol, as_of_date, years_back=0)
    roce_3yr = _roce_at(store, symbol, as_of_date, years_back=3)

    return {
        "pe_trailing": _pe_trailing_at(store, symbol, as_of_date),
        "pe_percentile_10y": _pe_percentile(store, symbol, as_of_date),
        "roce_current": roce_now,
        "roce_3yr_delta": (roce_now - roce_3yr) if (roce_now is not None and roce_3yr is not None) else None,
        "revenue_cagr_3yr": _revenue_cagr_3yr(store, symbol, as_of_date),
        "opm_trend": _opm_trend(store, symbol, as_of_date),
        "promoter_pct": promoter,
        "fii_pct": fii_now,
        "fii_delta_2q": (fii_now - fii_2q) if (fii_now is not None and fii_2q is not None) else None,
        "mf_pct": mf_now,
        "mf_delta_2q": (mf_now - mf_2q) if (mf_now is not None and mf_2q is not None) else None,
        "pledge_pct": _pledge_pct(store, symbol, as_of_date),
        "price_vs_sma200": _price_vs_sma200(store, symbol, as_of_date),
        "delivery_pct_6m": _delivery_pct_6m(store, symbol, as_of_date),
        "rsi_14": _rsi_14(store, symbol, as_of_date),
        "industry": _industry(store, symbol),
        "mcap_bucket": _mcap_bucket(store, symbol, as_of_date),
    }


# ---------------------------------------------------------------------------
# Forward returns
# ---------------------------------------------------------------------------


def _price_at_or_before(store: FlowStore, symbol: str, target_date: str) -> float | None:
    row = store._conn.execute(
        "SELECT COALESCE(adj_close, close) AS px FROM daily_stock_data "
        "WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (symbol.upper(), target_date),
    ).fetchone()
    return row["px"] if row else None


def _price_at_or_after(store: FlowStore, symbol: str, target_date: str) -> float | None:
    row = store._conn.execute(
        "SELECT COALESCE(adj_close, close) AS px FROM daily_stock_data "
        "WHERE symbol = ? AND date >= ? ORDER BY date ASC LIMIT 1",
        (symbol.upper(), target_date),
    ).fetchone()
    return row["px"] if row else None


def _fwd_return(
    store: FlowStore, symbol: str, from_date: str, days: int,
) -> float | None:
    start = _price_at_or_before(store, symbol, from_date)
    target_date = (date.fromisoformat(from_date) + timedelta(days=days)).isoformat()
    end = _price_at_or_after(store, symbol, target_date)
    if start is None or end is None or start <= 0:
        return None
    return round((end - start) / start * 100, 2)


def classify_outcome(return_12m_pct: float | None) -> str | None:
    """Coarse bucket for 12-month forward return."""
    if return_12m_pct is None:
        return None
    if return_12m_pct >= 20.0:
        return "recovered"
    if return_12m_pct <= -20.0:
        return "blew_up"
    return "sideways"


def compute_forward_returns(
    store: FlowStore, symbol: str, as_of_date: str,
    sector_proxy_symbol: str | None = None,
    nifty_proxy_symbol: str = "NIFTY",
) -> dict[str, Any]:
    """Compute 3m/6m/12m forward returns + excess vs sector + excess vs Nifty.
    Reads adj_close so splits/bonuses after as_of_date don't phantom-distort."""
    r3 = _fwd_return(store, symbol, as_of_date, 90)
    r6 = _fwd_return(store, symbol, as_of_date, 180)
    r12 = _fwd_return(store, symbol, as_of_date, 365)

    excess_12m_vs_nifty = None
    if r12 is not None:
        nifty_r12 = _fwd_return(store, nifty_proxy_symbol, as_of_date, 365)
        if nifty_r12 is not None:
            excess_12m_vs_nifty = round(r12 - nifty_r12, 2)

    excess_3m_vs_sector = None
    excess_12m_vs_sector = None
    if sector_proxy_symbol:
        sec_r3 = _fwd_return(store, sector_proxy_symbol, as_of_date, 90)
        sec_r12 = _fwd_return(store, sector_proxy_symbol, as_of_date, 365)
        if r3 is not None and sec_r3 is not None:
            excess_3m_vs_sector = round(r3 - sec_r3, 2)
        if r12 is not None and sec_r12 is not None:
            excess_12m_vs_sector = round(r12 - sec_r12, 2)

    return {
        "return_3m_pct": r3,
        "return_6m_pct": r6,
        "return_12m_pct": r12,
        "excess_3m_vs_sector": excess_3m_vs_sector,
        "excess_12m_vs_sector": excess_12m_vs_sector,
        "excess_12m_vs_nifty": excess_12m_vs_nifty,
        "outcome_label": classify_outcome(r12),
    }


# ---------------------------------------------------------------------------
# k-NN retrieval
# ---------------------------------------------------------------------------


def feature_distance(
    a: dict[str, Any], b: dict[str, Any], stds: dict[str, float],
) -> float:
    """Z-scored Euclidean distance over continuous features. None values
    on either side of a feature skip that dimension (don't crash)."""
    sq_sum = 0.0
    contributing = 0
    for k in _CONT_FEATURES:
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None:
            continue
        s = stds.get(k, 1.0) or 1.0
        sq_sum += ((va - vb) / s) ** 2
        contributing += 1
    if contributing == 0:
        return float("inf")
    # Normalize by contributing dimensions so partial-feature candidates aren't
    # unfairly penalized relative to full-feature ones.
    return math.sqrt(sq_sum / contributing * len(_CONT_FEATURES))


def _universe_stds(store: FlowStore) -> dict[str, float]:
    """Per-feature stdev across the whole historical_states table.
    Used to z-score the distance metric so pe_trailing (wide range) doesn't
    dominate pledge_pct (narrow range)."""
    stds: dict[str, float] = {}
    for feat in _CONT_FEATURES:
        rows = store._conn.execute(
            f"SELECT {feat} AS v FROM historical_states WHERE {feat} IS NOT NULL"
        ).fetchall()
        vals = [r["v"] for r in rows]
        if len(vals) >= 2:
            try:
                stds[feat] = statistics.stdev(vals)
            except statistics.StatisticsError:
                stds[feat] = 1.0
        else:
            stds[feat] = 1.0
    return stds


def retrieve_top_k_analogs(
    store: FlowStore,
    target_symbol: str,
    target_date: str,
    target_features: dict[str, Any],
    k: int = 20,
    exclusion_years: int = 2,
) -> list[dict[str, Any]]:
    """Return the top-K closest historical_states rows to `target_features`.

    Filters:
      - Hard: matching industry + matching mcap_bucket (loose adjacency logic
        can come in Phase 2; MVP keeps it tight).
      - Leakage guard: exclude any row where symbol == target_symbol AND
        quarter_end within `exclusion_years` of target_date.

    Each returned dict has the candidate's features + computed distance +
    forward returns joined from analog_forward_returns.
    """
    industry = target_features.get("industry")
    mcap_bucket = target_features.get("mcap_bucket")

    cutoff_date = (
        date.fromisoformat(target_date) - timedelta(days=exclusion_years * 365)
    ).isoformat()

    # Join historical_states + analog_forward_returns. Filter by industry + mcap.
    sql = """
        SELECT
            hs.symbol AS symbol, hs.quarter_end AS quarter_end,
            hs.pe_trailing, hs.pe_percentile_10y,
            hs.roce_current, hs.roce_3yr_delta,
            hs.revenue_cagr_3yr, hs.opm_trend,
            hs.promoter_pct, hs.fii_pct, hs.fii_delta_2q,
            hs.mf_pct, hs.mf_delta_2q, hs.pledge_pct,
            hs.price_vs_sma200, hs.delivery_pct_6m, hs.rsi_14,
            hs.industry, hs.mcap_bucket,
            afr.return_3m_pct, afr.return_6m_pct, afr.return_12m_pct,
            afr.excess_3m_vs_sector, afr.excess_12m_vs_sector, afr.excess_12m_vs_nifty,
            afr.outcome_label
        FROM historical_states hs
        LEFT JOIN analog_forward_returns afr
          ON afr.symbol = hs.symbol AND afr.as_of_date = hs.quarter_end
        WHERE 1=1
    """
    args: list[Any] = []
    if industry is not None:
        sql += " AND hs.industry = ?"
        args.append(industry)
    if mcap_bucket is not None:
        sql += " AND hs.mcap_bucket = ?"
        args.append(mcap_bucket)

    # Leakage: exclude target_symbol's own rows within exclusion_years of target_date
    sql += " AND NOT (hs.symbol = ? AND hs.quarter_end > ?)"
    args.extend([target_symbol.upper(), cutoff_date])

    rows = store._conn.execute(sql, args).fetchall()

    stds = _universe_stds(store)

    scored: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        dist = feature_distance(target_features, d, stds)
        if not math.isfinite(dist):
            continue
        d["distance"] = round(dist, 4)
        scored.append(d)

    scored.sort(key=lambda r: r["distance"])
    return scored[:k]


# ---------------------------------------------------------------------------
# Cohort statistics
# ---------------------------------------------------------------------------


def cohort_stats(cohort: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate recovery rate, median return, blow-up rate, tail percentiles."""
    returns_12m = [c["return_12m_pct"] for c in cohort if c.get("return_12m_pct") is not None]
    labels = [c.get("outcome_label") for c in cohort]
    n = len(cohort)

    out: dict[str, Any] = {"count": n}
    if returns_12m:
        sorted_r = sorted(returns_12m)
        out["median_return_12m_pct"] = round(statistics.median(sorted_r), 2)
        out["p10_return_12m_pct"] = round(sorted_r[max(0, int(0.1 * len(sorted_r)) - 1)], 2)
        out["p90_return_12m_pct"] = round(sorted_r[min(len(sorted_r) - 1, int(0.9 * len(sorted_r)) - 1)], 2)
    if n > 0:
        out["recovery_rate_pct"] = round(labels.count("recovered") / n * 100, 1)
        out["blow_up_rate_pct"] = round(labels.count("blew_up") / n * 100, 1)
        out["sideways_rate_pct"] = round(labels.count("sideways") / n * 100, 1)
    return out
