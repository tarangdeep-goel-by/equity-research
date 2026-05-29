"""Valuation, sector & FMP domain (split from FlowStore, refactor P1.4).

Per-stock valuation snapshots + PE/PB bands, index valuations + percentiles,
sector overview/detail/ranking + MF flows, peers, company snapshot aggregation,
FMP datasets (DCF / key metrics / growth / grades / price targets), sector
benchmarks, and the analytical-snapshot screen. Methods moved verbatim from
store.py; they run on the FlowStore instance via mixin composition, so
``self._conn`` and self cross-calls resolve unchanged. Sector queries use the
derived-DII shareholding CTE and the percentile helper from
store_domains/_shared.py.
"""

from __future__ import annotations

import statistics

from flowtracker.fund_models import ValuationSnapshot, ValuationBand
from flowtracker.indexpe_models import IndexValuation
from flowtracker.fmp_models import (
    FMPDcfValue, FMPKeyMetrics,
    FMPFinancialGrowth, FMPAnalystGrade, FMPPriceTarget,
)
from flowtracker.store_domains._shared import (
    _SHAREHOLDING_WITH_DII,
    _percentile_rank,
    _validate_row,
    _val_logger,
)


class ValuationMixin:
    """Valuation bands, index valuations, sector analytics, peers, FMP, benchmarks, analytics screen."""

    def upsert_valuation_snapshot(self, snapshot: ValuationSnapshot) -> int:
        """Insert or replace a valuation snapshot. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        existing = self._conn.execute(
            "SELECT pe_trailing FROM valuation_snapshot WHERE symbol = ? AND date = ?",
            (snapshot.symbol, snapshot.date),
        ).fetchone()
        warnings = _validate_row(
            "valuation_snapshot", snapshot.model_dump(),
            market=getattr(snapshot, "market", "NSE"), currency=getattr(snapshot, "currency", "INR"),
        )
        if warnings:
            _val_logger.warning("valuation_snapshot %s/%s: %s", snapshot.symbol, snapshot.date, "; ".join(warnings))
        if existing and existing["pe_trailing"] != snapshot.pe_trailing:
            cursor.execute(
                "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("valuation_snapshot", snapshot.symbol, snapshot.date,
                 "pe_trailing", str(existing["pe_trailing"]), str(snapshot.pe_trailing)),
            )
        cursor.execute(
            "INSERT OR REPLACE INTO valuation_snapshot "
            "(symbol, date, price, market_cap, enterprise_value, "
            "fifty_two_week_high, fifty_two_week_low, beta, "
            "pe_trailing, pe_forward, pb_ratio, ev_ebitda, ev_revenue, ps_ratio, peg_ratio, "
            "gross_margin, operating_margin, net_margin, roe, roa, "
            "revenue_growth, earnings_growth, earnings_quarterly_growth, "
            "dividend_yield, debt_to_equity, current_ratio, total_cash, total_debt, "
            "book_value_per_share, free_cash_flow, operating_cash_flow, "
            "revenue_per_share, cash_per_share, avg_volume, float_shares, shares_outstanding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot.symbol, snapshot.date, snapshot.price, snapshot.market_cap,
             snapshot.enterprise_value, snapshot.fifty_two_week_high, snapshot.fifty_two_week_low,
             snapshot.beta, snapshot.pe_trailing, snapshot.pe_forward, snapshot.pb_ratio,
             snapshot.ev_ebitda, snapshot.ev_revenue, snapshot.ps_ratio, snapshot.peg_ratio,
             snapshot.gross_margin, snapshot.operating_margin, snapshot.net_margin,
             snapshot.roe, snapshot.roa, snapshot.revenue_growth, snapshot.earnings_growth,
             snapshot.earnings_quarterly_growth, snapshot.dividend_yield,
             snapshot.debt_to_equity, snapshot.current_ratio, snapshot.total_cash,
             snapshot.total_debt, snapshot.book_value_per_share, snapshot.free_cash_flow,
             snapshot.operating_cash_flow, snapshot.revenue_per_share, snapshot.cash_per_share,
             snapshot.avg_volume, snapshot.float_shares, snapshot.shares_outstanding),
        )
        self._conn.commit()
        return cursor.rowcount

    def upsert_valuation_snapshots(self, snapshots: list[ValuationSnapshot]) -> int:
        """Batch insert valuation snapshots."""
        count = 0
        for s in snapshots:
            count += self.upsert_valuation_snapshot(s)
        return count

    def get_valuation_history(self, symbol: str, days: int = 365) -> list[ValuationSnapshot]:
        """Get valuation snapshots for the last N days, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM valuation_snapshot "
            "WHERE symbol = ? AND date >= date('now', ? || ' days') "
            "ORDER BY date ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()
        def _snap(r) -> ValuationSnapshot:
            d = dict(r)
            return ValuationSnapshot(
                symbol=d["symbol"], date=d["date"], price=d["price"],
                market_cap=d.get("market_cap"), enterprise_value=d.get("enterprise_value"),
                fifty_two_week_high=d.get("fifty_two_week_high"),
                fifty_two_week_low=d.get("fifty_two_week_low"),
                beta=d.get("beta"),
                pe_trailing=d.get("pe_trailing"), pe_forward=d.get("pe_forward"),
                pb_ratio=d.get("pb_ratio"), ev_ebitda=d.get("ev_ebitda"),
                ev_revenue=d.get("ev_revenue"), ps_ratio=d.get("ps_ratio"),
                peg_ratio=d.get("peg_ratio"),
                gross_margin=d.get("gross_margin"), operating_margin=d.get("operating_margin"),
                net_margin=d.get("net_margin"), roe=d.get("roe"), roa=d.get("roa"),
                revenue_growth=d.get("revenue_growth"), earnings_growth=d.get("earnings_growth"),
                earnings_quarterly_growth=d.get("earnings_quarterly_growth"),
                dividend_yield=d.get("dividend_yield"),
                debt_to_equity=d.get("debt_to_equity"), current_ratio=d.get("current_ratio"),
                total_cash=d.get("total_cash"), total_debt=d.get("total_debt"),
                book_value_per_share=d.get("book_value_per_share"),
                free_cash_flow=d.get("free_cash_flow"),
                operating_cash_flow=d.get("operating_cash_flow"),
                revenue_per_share=d.get("revenue_per_share"), cash_per_share=d.get("cash_per_share"),
                avg_volume=d.get("avg_volume"), float_shares=d.get("float_shares"),
                shares_outstanding=d.get("shares_outstanding"),
            )
        return [_snap(r) for r in rows]

    def _pe_series_from_charts(self, symbol: str, days: int) -> list[tuple[str, float]]:
        """Return [(date, pe_value), ...] from screener_charts for chart_type='pe'.

        Phase 3.1 fix: valuation_snapshot only has ~28 days of data (since daily cron
        was started recently), but screener_charts has historical PE series going back
        to 2005 for mature stocks. Prefer charts when available.

        Returns empty list if no rows found (caller falls back to valuation_snapshot).
        """
        rows = self._conn.execute(
            "SELECT date, value FROM screener_charts "
            "WHERE symbol = ? AND chart_type = 'pe' AND metric = 'Price to Earning' "
            "AND date >= date('now', ? || ' days') AND value IS NOT NULL "
            "ORDER BY date ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()
        return [(r["date"], r["value"]) for r in rows]

    def _pb_series_from_charts(self, symbol: str, days: int) -> list[tuple[str, float]]:
        """Return [(date, pb_value), ...] from screener_charts for chart_type='pbv'.

        Mirrors `_pe_series_from_charts` for the PB band. Banks don't trade on PE,
        so PB band is the primary BFSI valuation signal — but valuation_snapshot
        has shallow history. screener_charts holds the deep PBV series Screener
        exposes via `?type=pbv`.

        Returns empty list if no rows found (caller falls back to valuation_snapshot).
        """
        rows = self._conn.execute(
            "SELECT date, value FROM screener_charts "
            "WHERE symbol = ? AND chart_type = 'pbv' AND metric = 'Price to book value' "
            "AND date >= date('now', ? || ' days') AND value IS NOT NULL "
            "ORDER BY date ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()
        return [(r["date"], r["value"]) for r in rows]

    def get_valuation_band(self, symbol: str, metric: str, days: int = 1095) -> ValuationBand | None:
        """Compute min/max/median/percentile for a valuation metric over N days.

        metric must be a column name in valuation_snapshot (e.g., 'pe_trailing', 'ev_ebitda', 'pb_ratio').

        For metric='pe_trailing' and 'pb_ratio', reads from screener_charts (chart_type='pe' / 'pbv') first —
        that table has deep history (2005+ for mature stocks), while valuation_snapshot
        only has ~28 days since the daily cron was started recently. Falls back to
        valuation_snapshot if no chart data is available.

        Aliases: 'pb' resolves to 'pb_ratio' (matches the prompt-doc convention at
        prompts.py:736 — `get_valuation(band, metric='pb')`).
        """
        # Aliases — keep the resolved name as the canonical metric for SQL/output.
        metric_aliases = {"pb": "pb_ratio", "pe": "pe_trailing"}
        metric = metric_aliases.get(metric, metric)

        # Validate metric name to prevent SQL injection
        valid_metrics = {
            "pe_trailing", "pe_forward", "pb_ratio", "ev_ebitda", "ev_revenue",
            "ps_ratio", "peg_ratio", "dividend_yield", "beta",
            "gross_margin", "operating_margin", "net_margin", "roe", "roa",
        }
        if metric not in valid_metrics:
            return None

        # Phase 3.1: prefer screener_charts for PE (deeper history)
        if metric == "pe_trailing":
            series = self._pe_series_from_charts(symbol, days)
            if series:
                # series is already date ASC from the SQL ORDER BY
                chart_latest_date, chart_latest_val = series[-1]
                period_start = series[0][0]
                period_end = chart_latest_date
                current_val = chart_latest_val
                values = [v for _, v in series]

                # If the daily cron produced a newer snapshot than the weekly chart
                # refresh, splice it in as one extra observation rather than just
                # replacing current_val — otherwise min/max/median/percentile would
                # describe a different set than current_val sits in. Note: Screener
                # "Price to Earning" and yfinance pe_trailing are both TTM but can
                # diverge by 1-3% due to methodology; we accept that splice since the
                # band is an approximation.
                snap_latest = self._conn.execute(
                    "SELECT pe_trailing, date FROM valuation_snapshot "
                    "WHERE symbol = ? AND pe_trailing IS NOT NULL "
                    "ORDER BY date DESC LIMIT 1",
                    (symbol.upper(),),
                ).fetchone()
                if snap_latest is not None and snap_latest["date"] > chart_latest_date:
                    values.append(snap_latest["pe_trailing"])
                    current_val = snap_latest["pe_trailing"]
                    period_end = snap_latest["date"]

                values_sorted = sorted(values)
                n = len(values_sorted)
                min_val = values_sorted[0]
                max_val = values_sorted[-1]
                median_val = (
                    values_sorted[n // 2]
                    if n % 2 == 1
                    else (values_sorted[n // 2 - 1] + values_sorted[n // 2]) / 2
                )
                below = sum(1 for v in values_sorted if v < current_val)
                percentile = (below / n) * 100

                return ValuationBand(
                    symbol=symbol.upper(),
                    metric=metric,
                    min_val=min_val,
                    max_val=max_val,
                    median_val=median_val,
                    current_val=current_val,
                    percentile=percentile,
                    num_observations=n,
                    period_start=period_start,
                    period_end=period_end,
                )
            # else: no chart data — fall through to valuation_snapshot path below

        # Same charts-first treatment for PB (banks don't trade on PE — PB band is
        # the primary BFSI valuation signal). Mirrors the PE path above.
        if metric == "pb_ratio":
            series = self._pb_series_from_charts(symbol, days)
            if series:
                chart_latest_date, chart_latest_val = series[-1]
                period_start = series[0][0]
                period_end = chart_latest_date
                current_val = chart_latest_val
                values = [v for _, v in series]

                # Splice in a newer valuation_snapshot.pb_ratio if the daily cron
                # produced a fresher row than the weekly chart refresh.
                snap_latest = self._conn.execute(
                    "SELECT pb_ratio, date FROM valuation_snapshot "
                    "WHERE symbol = ? AND pb_ratio IS NOT NULL "
                    "ORDER BY date DESC LIMIT 1",
                    (symbol.upper(),),
                ).fetchone()
                if snap_latest is not None and snap_latest["date"] > chart_latest_date:
                    values.append(snap_latest["pb_ratio"])
                    current_val = snap_latest["pb_ratio"]
                    period_end = snap_latest["date"]

                values_sorted = sorted(values)
                n = len(values_sorted)
                min_val = values_sorted[0]
                max_val = values_sorted[-1]
                median_val = (
                    values_sorted[n // 2]
                    if n % 2 == 1
                    else (values_sorted[n // 2 - 1] + values_sorted[n // 2]) / 2
                )
                below = sum(1 for v in values_sorted if v < current_val)
                percentile = (below / n) * 100

                return ValuationBand(
                    symbol=symbol.upper(),
                    metric=metric,
                    min_val=min_val,
                    max_val=max_val,
                    median_val=median_val,
                    current_val=current_val,
                    percentile=percentile,
                    num_observations=n,
                    period_start=period_start,
                    period_end=period_end,
                )
            # else: no pbv chart data — fall through to valuation_snapshot path below

        rows = self._conn.execute(
            f"SELECT {metric}, date FROM valuation_snapshot "
            f"WHERE symbol = ? AND date >= date('now', ? || ' days') AND {metric} IS NOT NULL "
            f"ORDER BY {metric} ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()

        if not rows:
            return None

        values = [r[metric] for r in rows]
        n = len(values)
        min_val = values[0]
        max_val = values[-1]
        median_val = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2

        # Get current value (most recent)
        latest = self._conn.execute(
            f"SELECT {metric} FROM valuation_snapshot "
            f"WHERE symbol = ? AND {metric} IS NOT NULL "
            f"ORDER BY date DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if latest is None:
            return None
        current_val = latest[metric]

        # Compute percentile
        below = sum(1 for v in values if v < current_val)
        percentile = (below / n) * 100

        dates = [r["date"] for r in rows]
        return ValuationBand(
            symbol=symbol.upper(),
            metric=metric,
            min_val=min_val,
            max_val=max_val,
            median_val=median_val,
            current_val=current_val,
            percentile=percentile,
            num_observations=n,
            period_start=min(dates),
            period_end=max(dates),
        )

    def upsert_index_valuations(self, valuations: list[IndexValuation]) -> int:
        """Insert or replace daily index PE/PB/Div-Yield rows.

        Idempotent on the (date, index_name) UNIQUE constraint; re-running
        a backfill overwrites prior rows with the latest niftyindices values.
        """
        if not valuations:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for v in valuations:
            cursor.execute(
                "INSERT OR REPLACE INTO index_valuation_daily "
                "(date, index_name, pe, pb, dividend_yield) "
                "VALUES (?, ?, ?, ?, ?)",
                (v.date, v.index_name.upper(), v.pe, v.pb, v.dividend_yield),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_index_valuation_history(
        self,
        index_name: str,
        days: int | None = None,
    ) -> list[IndexValuation]:
        """Return historical index valuation rows oldest-first.

        ``days``: when set, restricts to the last N days; otherwise returns
        the full stored history.
        """
        canonical = index_name.strip().upper()
        if days is not None:
            rows = self._conn.execute(
                "SELECT date, index_name, pe, pb, dividend_yield "
                "FROM index_valuation_daily "
                "WHERE index_name = ? "
                "AND date >= date('now', ? || ' days') "
                "ORDER BY date ASC",
                (canonical, f"-{int(days)}"),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT date, index_name, pe, pb, dividend_yield "
                "FROM index_valuation_daily "
                "WHERE index_name = ? "
                "ORDER BY date ASC",
                (canonical,),
            ).fetchall()
        return [
            IndexValuation(
                date=r["date"],
                index_name=r["index_name"],
                pe=r["pe"],
                pb=r["pb"],
                dividend_yield=r["dividend_yield"],
            )
            for r in rows
        ]

    def get_index_valuation_latest(self, index_name: str) -> IndexValuation | None:
        """Most recent index-valuation row for ``index_name``."""
        canonical = index_name.strip().upper()
        row = self._conn.execute(
            "SELECT date, index_name, pe, pb, dividend_yield "
            "FROM index_valuation_daily "
            "WHERE index_name = ? "
            "ORDER BY date DESC LIMIT 1",
            (canonical,),
        ).fetchone()
        if not row:
            return None
        return IndexValuation(
            date=row["date"],
            index_name=row["index_name"],
            pe=row["pe"],
            pb=row["pb"],
            dividend_yield=row["dividend_yield"],
        )

    def get_index_valuation_percentile(self, index_name: str) -> dict:
        """Current PE/PB/Div-Yield percentile vs the full stored distribution.

        Returns a dict with current values, 10-year (full-history) medians,
        percentile ranks (0-100, inclusive of equal-or-lower observations),
        and the sample size used for ranking. Returns an empty dict when
        no history is available.

        Used by ``flowtrack indexpe percentile`` to answer regime questions
        such as "is the current Smallcap 250 PE rich vs the 10-yr median".
        """
        canonical = index_name.strip().upper()
        rows = self._conn.execute(
            "SELECT pe, pb, dividend_yield "
            "FROM index_valuation_daily "
            "WHERE index_name = ? "
            "ORDER BY date ASC",
            (canonical,),
        ).fetchall()
        if not rows:
            return {}

        latest = self.get_index_valuation_latest(canonical)
        if latest is None:
            return {}

        # Outlier guard: index PE explodes toward infinity when aggregate
        # earnings collapse to ~0 (e.g. NIFTY MEDIA/AUTO/REALTY during COVID →
        # PE 700-7800) and a handful of source glitches sit even higher
        # (SMALLCAP 250 PE 44,711 in 2016, MNC 58,551 in 2021). These are real
        # rows but analytically meaningless and skew the distribution, so they
        # are excluded from the percentile/median sample. Current values are
        # still reported as-is by get_index_valuation_latest.
        pe_series = [r["pe"] for r in rows if r["pe"] is not None and 0 < r["pe"] <= 200]
        pb_series = [r["pb"] for r in rows if r["pb"] is not None and 0 < r["pb"] <= 40]
        divy_series = [r["dividend_yield"] for r in rows if r["dividend_yield"] is not None and 0 <= r["dividend_yield"] <= 15]

        first_row = self._conn.execute(
            "SELECT date FROM index_valuation_daily "
            "WHERE index_name = ? ORDER BY date ASC LIMIT 1",
            (canonical,),
        ).fetchone()
        last_row = self._conn.execute(
            "SELECT date FROM index_valuation_daily "
            "WHERE index_name = ? ORDER BY date DESC LIMIT 1",
            (canonical,),
        ).fetchone()

        return {
            "index_name": canonical,
            "as_of_date": latest.date,
            "current": {
                "pe": latest.pe,
                "pb": latest.pb,
                "dividend_yield": latest.dividend_yield,
            },
            "median_10y": {
                "pe": statistics.median(pe_series) if pe_series else None,
                "pb": statistics.median(pb_series) if pb_series else None,
                "dividend_yield": statistics.median(divy_series) if divy_series else None,
            },
            "pe_percentile": _percentile_rank(latest.pe, pe_series),
            "pb_percentile": _percentile_rank(latest.pb, pb_series),
            "divy_percentile": _percentile_rank(latest.dividend_yield, divy_series),
            "sample_size": len(pe_series),
            "history_start": first_row["date"] if first_row else None,
            "history_end": last_row["date"] if last_row else None,
        }

    def get_sector_overview(self) -> list[dict]:
        """Get sector-level ownership shifts + delivery + price signals.

        Returns list of dicts with industry, num_stocks, avg changes per category,
        avg delivery %, avg price change %.
        """
        rows = self._conn.execute(f"""
            WITH sh AS ({_SHAREHOLDING_WITH_DII})
            SELECT
                ic.industry,
                COUNT(DISTINCT ic.symbol) as num_stocks,
                AVG(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as avg_fii_change,
                AVG(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as avg_mf_change,
                AVG(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as avg_dii_change,
                AVG(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as avg_promoter_change,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN sh s1 ON ic.symbol = s1.symbol
            INNER JOIN sh s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM sh s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                -- Outlier filter excludes split/bonus ex-dates where raw
                -- close/prev_close ratio reflects mechanical adjustment, not
                -- real price movement (NSE bhavcopy stores both unadjusted).
                SELECT ic2.industry,
                    AVG(d.delivery_pct) as avg_delivery_pct,
                    AVG((d.close - d.prev_close) / NULLIF(d.prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data d
                INNER JOIN index_constituents ic2 ON d.symbol = ic2.symbol
                WHERE d.date >= date('now', '-30 days')
                    AND d.delivery_pct IS NOT NULL
                    AND abs((d.close - d.prev_close) / NULLIF(d.prev_close, 0)) < 0.30
                GROUP BY ic2.industry
            ) del_stats ON ic.industry = del_stats.industry
            WHERE ic.industry IS NOT NULL
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM sh s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.industry
            HAVING num_stocks >= 3
            ORDER BY avg_mf_change DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_sector_detail(self, industry: str) -> list[dict]:
        """Get stock-level ownership + delivery + price data for a sector."""
        rows = self._conn.execute(f"""
            WITH sh AS ({_SHAREHOLDING_WITH_DII})
            SELECT
                ic.symbol,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage END) as curr_fii,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage END) as curr_mf,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as fii_change,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as mf_change,
                MAX(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as dii_change,
                MAX(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as promoter_change,
                vs.pe_trailing,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN sh s1 ON ic.symbol = s1.symbol
            INNER JOIN sh s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM sh s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                SELECT symbol, pe_trailing FROM valuation_snapshot
                WHERE (symbol, date) IN (
                    SELECT symbol, MAX(date) FROM valuation_snapshot GROUP BY symbol
                )
            ) vs ON ic.symbol = vs.symbol
            LEFT JOIN (
                -- Outlier filter excludes split/bonus ex-dates (mechanical
                -- price ratio, not real movement — see get_sector_summary).
                SELECT symbol,
                    AVG(delivery_pct) as avg_delivery_pct,
                    AVG((close - prev_close) / NULLIF(prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data
                WHERE date >= date('now', '-30 days') AND delivery_pct IS NOT NULL
                    AND abs((close - prev_close) / NULLIF(prev_close, 0)) < 0.30
                GROUP BY symbol
            ) del_stats ON ic.symbol = del_stats.symbol
            WHERE ic.industry = ?
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM sh s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.symbol
            ORDER BY mf_change DESC
        """, (industry,)).fetchall()
        return [dict(r) for r in rows]

    def get_sector_list(self) -> list[str]:
        """Get distinct industry names from index constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT industry FROM index_constituents "
            "WHERE industry IS NOT NULL ORDER BY industry"
        ).fetchall()
        return [r["industry"] for r in rows]

    def get_sector_valuation_summary(self, industry: str) -> dict:
        """Get aggregate valuation metrics for a sector/industry.

        Joins index_constituents → valuation_snapshot (latest per stock)
        → screener_ratios (latest ROCE per stock).
        Returns stock count, total mcap, median PE/PB/ROCE, PE range, top 5 by mcap.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol, ic.company_name,
                vs.market_cap, vs.pe_trailing, vs.pb_ratio,
                sr.roce_pct
            FROM index_constituents ic
            LEFT JOIN valuation_snapshot vs ON ic.symbol = vs.symbol
                AND vs.date = (
                    SELECT MAX(v2.date) FROM valuation_snapshot v2
                    WHERE v2.symbol = ic.symbol
                )
            LEFT JOIN screener_ratios sr ON ic.symbol = sr.symbol
                AND sr.fiscal_year_end = (
                    SELECT MAX(sr2.fiscal_year_end) FROM screener_ratios sr2
                    WHERE sr2.symbol = ic.symbol
                )
            WHERE ic.industry = ?
        """, (industry,)).fetchall()

        if not rows:
            return {
                "industry": industry, "stock_count": 0, "total_mcap_cr": 0.0,
                "median_pe": None, "median_pb": None, "median_roce": None,
                "pe_range": {"min": None, "max": None},
                "top_by_mcap": [],
            }

        def _median(vals: list[float]) -> float | None:
            if not vals:
                return None
            s = sorted(vals)
            n = len(s)
            if n % 2 == 1:
                return round(s[n // 2], 2)
            return round((s[n // 2 - 1] + s[n // 2]) / 2, 2)

        pe_vals = [r["pe_trailing"] for r in rows if r["pe_trailing"] and r["pe_trailing"] > 0]
        pb_vals = [r["pb_ratio"] for r in rows if r["pb_ratio"] and r["pb_ratio"] > 0]
        roce_vals = [r["roce_pct"] for r in rows if r["roce_pct"] is not None]
        mcaps = [(r["symbol"], r["company_name"], r["market_cap"] or 0, r["pe_trailing"]) for r in rows]
        mcaps.sort(key=lambda x: x[2], reverse=True)

        return {
            "industry": industry,
            "stock_count": len(rows),
            "total_mcap_cr": round(sum(r["market_cap"] or 0 for r in rows), 2),
            "median_pe": _median(pe_vals),
            "median_pb": _median(pb_vals),
            "median_roce": _median(roce_vals),
            "pe_range": {
                "min": round(min(pe_vals), 2) if pe_vals else None,
                "max": round(max(pe_vals), 2) if pe_vals else None,
            },
            "top_by_mcap": [
                {"symbol": s, "company_name": cn, "mcap_cr": round(mc, 2), "pe": round(pe, 2) if pe else None}
                for s, cn, mc, pe in mcaps[:5]
            ],
        }

    def get_sector_mf_flows(self, industry: str) -> dict:
        """Get MF ownership change summary for a sector/industry.

        Joins index_constituents → shareholding (latest vs previous quarter,
        category='MF'). Returns counts of stocks where MF% increased/decreased,
        avg change, and top additions/reductions.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol,
                s1.percentage AS curr_pct,
                s2.percentage AS prev_pct,
                s1.percentage - s2.percentage AS mf_change
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
                AND s1.category = 'MF'
                AND s1.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = ic.symbol AND s3.category = 'MF'
                )
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s2.category = 'MF'
                AND s2.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol AND s4.category = 'MF'
                    AND s4.quarter_end < s1.quarter_end
                )
            WHERE ic.industry = ?
        """, (industry,)).fetchall()

        if not rows:
            return {
                "industry": industry, "total_stocks": 0,
                "mf_increased": 0, "mf_decreased": 0, "avg_mf_change_pct": 0.0,
                "top_additions": [], "top_reductions": [],
            }

        changes = [{"symbol": r["symbol"], "mf_change_pct": round(r["mf_change"], 2)} for r in rows]
        increased = [c for c in changes if c["mf_change_pct"] > 0]
        decreased = [c for c in changes if c["mf_change_pct"] < 0]
        avg_change = round(sum(c["mf_change_pct"] for c in changes) / len(changes), 2)

        top_additions = sorted(increased, key=lambda x: x["mf_change_pct"], reverse=True)[:5]
        top_reductions = sorted(decreased, key=lambda x: x["mf_change_pct"])[:5]

        return {
            "industry": industry,
            "total_stocks": len(changes),
            "mf_increased": len(increased),
            "mf_decreased": len(decreased),
            "avg_mf_change_pct": avg_change,
            "top_additions": top_additions,
            "top_reductions": top_reductions,
        }

    def get_sector_stocks_ranked(self, industry: str) -> list[dict]:
        """Get all stocks in a sector ranked by market cap, with key metrics.

        Joins index_constituents → valuation_snapshot (latest) →
        shareholding (latest FII/MF %) → screener_ratios (latest ROCE).
        Returns list of dicts sorted by mcap descending.
        """
        rows = self._conn.execute("""
            SELECT
                ic.symbol, ic.company_name,
                vs.market_cap, vs.pe_trailing,
                sr.roce_pct,
                asnap.bfsi_roa_pct,
                fii.percentage AS fii_pct,
                mf.percentage AS mf_pct,
                vs.earnings_growth AS price_change_1yr_pct
            FROM index_constituents ic
            LEFT JOIN valuation_snapshot vs ON ic.symbol = vs.symbol
                AND vs.date = (
                    SELECT MAX(v2.date) FROM valuation_snapshot v2
                    WHERE v2.symbol = ic.symbol
                )
            LEFT JOIN screener_ratios sr ON ic.symbol = sr.symbol
                AND sr.fiscal_year_end = (
                    SELECT MAX(sr2.fiscal_year_end) FROM screener_ratios sr2
                    WHERE sr2.symbol = ic.symbol
                )
            LEFT JOIN analytical_snapshot asnap ON ic.symbol = asnap.symbol
                AND asnap.computed_date = (
                    SELECT MAX(a2.computed_date) FROM analytical_snapshot a2
                    WHERE a2.symbol = ic.symbol
                )
            LEFT JOIN shareholding fii ON ic.symbol = fii.symbol
                AND fii.category = 'FII'
                AND fii.quarter_end = (
                    SELECT MAX(f2.quarter_end) FROM shareholding f2
                    WHERE f2.symbol = ic.symbol AND f2.category = 'FII'
                )
            LEFT JOIN shareholding mf ON ic.symbol = mf.symbol
                AND mf.category = 'MF'
                AND mf.quarter_end = (
                    SELECT MAX(m2.quarter_end) FROM shareholding m2
                    WHERE m2.symbol = ic.symbol AND m2.category = 'MF'
                )
            WHERE ic.industry = ?
            ORDER BY vs.market_cap DESC
        """, (industry,)).fetchall()

        return [{
            "symbol": r["symbol"],
            "company_name": r["company_name"],
            "mcap_cr": round(r["market_cap"], 2) if r["market_cap"] else None,
            "pe": round(r["pe_trailing"], 2) if r["pe_trailing"] else None,
            "roce_pct": round(r["roce_pct"], 2) if r["roce_pct"] else None,
            # BFSI-only: ROA from analytical_snapshot.bfsi_roa_pct (computed
            # by the weekly analytics cron). ROCE is meaningless for banks/
            # NBFCs, so sector charts for BFSI prefer the ROA axis.
            "roa_pct": round(r["bfsi_roa_pct"], 2) if r["bfsi_roa_pct"] else None,
            "fii_pct": round(r["fii_pct"], 2) if r["fii_pct"] else None,
            "mf_pct": round(r["mf_pct"], 2) if r["mf_pct"] else None,
            "price_change_1yr_pct": round(r["price_change_1yr_pct"], 2) if r["price_change_1yr_pct"] else None,
        } for r in rows]

    def upsert_peers(self, symbol: str, peers: list[dict]) -> int:
        """Store peer comparison data."""
        count = 0
        for p in peers:
            name = p.get("name", p.get("sno", ""))
            if not name:
                continue
            self._conn.execute(
                "INSERT INTO peer_comparison "
                "(symbol, peer_name, peer_symbol, cmp, pe, market_cap, div_yield, "
                "np_qtr, qtr_profit_var, sales_qtr, qtr_sales_var, roce) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol, peer_name) DO UPDATE SET "
                "peer_symbol=excluded.peer_symbol, "
                "cmp=excluded.cmp, pe=excluded.pe, market_cap=excluded.market_cap, "
                "div_yield=excluded.div_yield, np_qtr=excluded.np_qtr, "
                "qtr_profit_var=excluded.qtr_profit_var, sales_qtr=excluded.sales_qtr, "
                "qtr_sales_var=excluded.qtr_sales_var, roce=excluded.roce, "
                "fetched_at=datetime('now')",
                (
                    symbol,
                    name,
                    p.get("peer_symbol"),
                    p.get("cmp") or p.get("cmp_rs") or p.get("cmprs"),
                    p.get("pe") or p.get("p_e"),
                    p.get("market_cap") or p.get("market_cap_cr") or p.get("mar_caprscr"),
                    p.get("div_yield") or p.get("div_yld_pct") or p.get("div_yldpct"),
                    p.get("np_qtr") or p.get("np_qtr_cr") or p.get("np_qtrrscr"),
                    p.get("qtr_profit_var") or p.get("qtr_profit_var_pct") or p.get("qtr_profit_varpct"),
                    p.get("sales_qtr") or p.get("sales_qtr_cr") or p.get("sales_qtrrscr"),
                    p.get("qtr_sales_var") or p.get("qtr_sales_var_pct") or p.get("qtr_sales_varpct"),
                    p.get("roce") or p.get("roce_pct") or p.get("rocepct"),
                ),
            )
            count += 1
        self._conn.commit()
        return count

    def get_peers(self, symbol: str) -> list[dict]:
        """Get stored peer comparison data."""
        rows = self._conn.execute(
            "SELECT * FROM peer_comparison WHERE symbol = ? ORDER BY market_cap DESC",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_snapshot_screener(self, symbol: str, data: dict) -> int:
        """Write Screener-owned columns to company_snapshot. Never touches yfinance columns.
        Note: industry/sector are owned by yfinance — not written here."""
        self._conn.execute(
            """INSERT INTO company_snapshot (symbol, name, cmp, market_cap, pe_trailing, roce,
                sales_qtr, qtr_sales_var, np_qtr, qtr_profit_var, screener_updated_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name, cmp=excluded.cmp,
                market_cap=excluded.market_cap, pe_trailing=excluded.pe_trailing, roce=excluded.roce,
                sales_qtr=excluded.sales_qtr, qtr_sales_var=excluded.qtr_sales_var,
                np_qtr=excluded.np_qtr, qtr_profit_var=excluded.qtr_profit_var,
                screener_updated_at=datetime('now'), updated_at=datetime('now')""",
            (symbol.upper(), data.get("name"), data.get("cmp"),
             data.get("market_cap"), data.get("pe_trailing"), data.get("roce"),
             data.get("sales_qtr"), data.get("qtr_sales_var"), data.get("np_qtr"),
             data.get("qtr_profit_var")),
        )
        self._conn.commit()
        return 1

    def upsert_snapshot_yfinance(self, symbol: str, data: dict) -> int:
        """Write yfinance-owned columns to company_snapshot. Never touches Screener columns."""
        self._conn.execute(
            """INSERT INTO company_snapshot (symbol, sector, industry, pe_forward, pb, ev_ebitda, peg, div_yield,
                operating_margin, net_margin, roe, roa, revenue_growth, earnings_growth,
                beta, debt_to_equity, current_ratio, high_52w, low_52w, yfinance_updated_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
                sector=excluded.sector,
                industry=excluded.industry,
                pe_forward=excluded.pe_forward, pb=excluded.pb, ev_ebitda=excluded.ev_ebitda,
                peg=excluded.peg, div_yield=excluded.div_yield,
                operating_margin=excluded.operating_margin, net_margin=excluded.net_margin,
                roe=excluded.roe, roa=excluded.roa,
                revenue_growth=excluded.revenue_growth, earnings_growth=excluded.earnings_growth,
                beta=excluded.beta, debt_to_equity=excluded.debt_to_equity,
                current_ratio=excluded.current_ratio, high_52w=excluded.high_52w, low_52w=excluded.low_52w,
                yfinance_updated_at=datetime('now'), updated_at=datetime('now')""",
            (symbol.upper(), data.get("sector"), data.get("industry"),
             data.get("pe_forward"), data.get("pb"), data.get("ev_ebitda"),
             data.get("peg"), data.get("div_yield"), data.get("operating_margin"),
             data.get("net_margin"), data.get("roe"), data.get("roa"),
             data.get("revenue_growth"), data.get("earnings_growth"), data.get("beta"),
             data.get("debt_to_equity"), data.get("current_ratio"),
             data.get("high_52w"), data.get("low_52w")),
        )
        self._conn.commit()
        return 1

    def upsert_snapshot_ownership(self, symbol: str, data: dict) -> int:
        """Write ownership columns to company_snapshot."""
        self._conn.execute(
            """INSERT INTO company_snapshot (symbol, promoter_holding, promoter_pledge, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
                promoter_holding=excluded.promoter_holding, promoter_pledge=excluded.promoter_pledge,
                updated_at=datetime('now')""",
            (symbol.upper(), data.get("promoter_holding"), data.get("promoter_pledge")),
        )
        self._conn.commit()
        return 1

    def upsert_snapshot_computed(self, symbol: str, data: dict) -> int:
        """Write computed-only columns (roic, fcf_yield) to company_snapshot.

        These are derived in snapshot_builder from annual_financials +
        valuation_snapshot — not ingested from any external source. Missing keys
        are written as NULL (pass only the keys you computed).
        """
        self._conn.execute(
            """INSERT INTO company_snapshot (symbol, roic, fcf_yield, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(symbol) DO UPDATE SET
                roic=COALESCE(excluded.roic, company_snapshot.roic),
                fcf_yield=COALESCE(excluded.fcf_yield, company_snapshot.fcf_yield),
                updated_at=datetime('now')""",
            (symbol.upper(), data.get("roic"), data.get("fcf_yield")),
        )
        self._conn.commit()
        return 1

    def get_company_snapshot(self, symbol: str) -> dict | None:
        """Get company snapshot for a single symbol."""
        row = self._conn.execute(
            "SELECT * FROM company_snapshot WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        return dict(row) if row else None

    def get_company_snapshots(self, symbols: list[str]) -> list[dict]:
        """Get snapshots for multiple symbols. Returns only those that exist."""
        if not symbols:
            return []
        placeholders = ",".join("?" * len(symbols))
        rows = self._conn.execute(
            f"SELECT * FROM company_snapshot WHERE symbol IN ({placeholders}) ORDER BY symbol",  # noqa: S608
            [s.upper() for s in symbols],
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_fmp_dcf(self, records: list[FMPDcfValue]) -> int:
        """Insert or replace FMP DCF records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_dcf "
                "(symbol, date, dcf, stock_price) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.date, r.dcf, r.stock_price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_key_metrics(self, records: list[FMPKeyMetrics]) -> int:
        """Insert or replace FMP key metrics records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            warnings = _validate_row(
                "fmp_key_metrics", r.model_dump(),
                market=getattr(r, "market", "NSE"), currency=getattr(r, "currency", "INR"),
            )
            if warnings:
                _val_logger.warning("fmp_key_metrics %s/%s: %s", r.symbol, r.date, "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_key_metrics "
                "(symbol, date, revenue_per_share, net_income_per_share, "
                "operating_cash_flow_per_share, free_cash_flow_per_share, "
                "cash_per_share, book_value_per_share, tangible_book_value_per_share, "
                "shareholders_equity_per_share, interest_debt_per_share, "
                "market_cap, enterprise_value, pe_ratio, price_to_sales_ratio, "
                "pb_ratio, ev_to_sales, ev_to_ebitda, ev_to_operating_cash_flow, "
                "ev_to_free_cash_flow, earnings_yield, free_cash_flow_yield, "
                "debt_to_equity, debt_to_assets, dividend_yield, payout_ratio, "
                "roe, roa, roic, net_profit_margin_dupont, asset_turnover, "
                "equity_multiplier) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.revenue_per_share, r.net_income_per_share,
                 r.operating_cash_flow_per_share, r.free_cash_flow_per_share,
                 r.cash_per_share, r.book_value_per_share, r.tangible_book_value_per_share,
                 r.shareholders_equity_per_share, r.interest_debt_per_share,
                 r.market_cap, r.enterprise_value, r.pe_ratio, r.price_to_sales_ratio,
                 r.pb_ratio, r.ev_to_sales, r.ev_to_ebitda, r.ev_to_operating_cash_flow,
                 r.ev_to_free_cash_flow, r.earnings_yield, r.free_cash_flow_yield,
                 r.debt_to_equity, r.debt_to_assets, r.dividend_yield, r.payout_ratio,
                 r.roe, r.roa, r.roic, r.net_profit_margin_dupont, r.asset_turnover,
                 r.equity_multiplier),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_financial_growth(self, records: list[FMPFinancialGrowth]) -> int:
        """Insert or replace FMP financial growth records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_financial_growth "
                "(symbol, date, revenue_growth, gross_profit_growth, ebitda_growth, "
                "operating_income_growth, net_income_growth, eps_growth, "
                "eps_diluted_growth, dividends_per_share_growth, "
                "operating_cash_flow_growth, free_cash_flow_growth, "
                "asset_growth, debt_growth, book_value_per_share_growth, "
                "revenue_growth_3y, revenue_growth_5y, revenue_growth_10y, "
                "net_income_growth_3y, net_income_growth_5y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.revenue_growth, r.gross_profit_growth,
                 r.ebitda_growth, r.operating_income_growth, r.net_income_growth,
                 r.eps_growth, r.eps_diluted_growth, r.dividends_per_share_growth,
                 r.operating_cash_flow_growth, r.free_cash_flow_growth,
                 r.asset_growth, r.debt_growth, r.book_value_per_share_growth,
                 r.revenue_growth_3y, r.revenue_growth_5y, r.revenue_growth_10y,
                 r.net_income_growth_3y, r.net_income_growth_5y),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_analyst_grades(self, records: list[FMPAnalystGrade]) -> int:
        """Insert or replace FMP analyst grade records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_analyst_grades "
                "(symbol, date, grading_company, previous_grade, new_grade) "
                "VALUES (?, ?, ?, ?, ?)",
                (r.symbol, r.date, r.grading_company, r.previous_grade, r.new_grade),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fmp_price_targets(self, records: list[FMPPriceTarget]) -> int:
        """Insert or replace FMP price target records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_price_targets "
                "(symbol, published_date, analyst_name, analyst_company, "
                "price_target, price_when_posted) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (r.symbol, r.published_date, r.analyst_name, r.analyst_company,
                 r.price_target, r.price_when_posted),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_fmp_dcf_latest(self, symbol: str) -> FMPDcfValue | None:
        """Get the most recent DCF value for a symbol."""
        row = self._conn.execute(
            "SELECT * FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return FMPDcfValue(
            symbol=row["symbol"], date=row["date"],
            dcf=row["dcf"], stock_price=row["stock_price"],
        )

    def get_fmp_dcf_history(self, symbol: str, limit: int = 10) -> list[FMPDcfValue]:
        """Get DCF history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPDcfValue(
            symbol=r["symbol"], date=r["date"],
            dcf=r["dcf"], stock_price=r["stock_price"],
        ) for r in rows]

    def get_fmp_key_metrics(self, symbol: str, limit: int = 10) -> list[FMPKeyMetrics]:
        """Get key metrics history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_key_metrics WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPKeyMetrics(
            symbol=r["symbol"], date=r["date"],
            revenue_per_share=r["revenue_per_share"],
            net_income_per_share=r["net_income_per_share"],
            operating_cash_flow_per_share=r["operating_cash_flow_per_share"],
            free_cash_flow_per_share=r["free_cash_flow_per_share"],
            cash_per_share=r["cash_per_share"],
            book_value_per_share=r["book_value_per_share"],
            tangible_book_value_per_share=r["tangible_book_value_per_share"],
            shareholders_equity_per_share=r["shareholders_equity_per_share"],
            interest_debt_per_share=r["interest_debt_per_share"],
            market_cap=r["market_cap"], enterprise_value=r["enterprise_value"],
            pe_ratio=r["pe_ratio"], price_to_sales_ratio=r["price_to_sales_ratio"],
            pb_ratio=r["pb_ratio"], ev_to_sales=r["ev_to_sales"],
            ev_to_ebitda=r["ev_to_ebitda"],
            ev_to_operating_cash_flow=r["ev_to_operating_cash_flow"],
            ev_to_free_cash_flow=r["ev_to_free_cash_flow"],
            earnings_yield=r["earnings_yield"],
            free_cash_flow_yield=r["free_cash_flow_yield"],
            debt_to_equity=r["debt_to_equity"], debt_to_assets=r["debt_to_assets"],
            dividend_yield=r["dividend_yield"], payout_ratio=r["payout_ratio"],
            roe=r["roe"], roa=r["roa"], roic=r["roic"],
            net_profit_margin_dupont=r["net_profit_margin_dupont"],
            asset_turnover=r["asset_turnover"],
            equity_multiplier=r["equity_multiplier"],
        ) for r in rows]

    def get_fmp_financial_growth(self, symbol: str, limit: int = 10) -> list[FMPFinancialGrowth]:
        """Get financial growth history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_financial_growth WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPFinancialGrowth(
            symbol=r["symbol"], date=r["date"],
            revenue_growth=r["revenue_growth"],
            gross_profit_growth=r["gross_profit_growth"],
            ebitda_growth=r["ebitda_growth"],
            operating_income_growth=r["operating_income_growth"],
            net_income_growth=r["net_income_growth"],
            eps_growth=r["eps_growth"],
            eps_diluted_growth=r["eps_diluted_growth"],
            dividends_per_share_growth=r["dividends_per_share_growth"],
            operating_cash_flow_growth=r["operating_cash_flow_growth"],
            free_cash_flow_growth=r["free_cash_flow_growth"],
            asset_growth=r["asset_growth"], debt_growth=r["debt_growth"],
            book_value_per_share_growth=r["book_value_per_share_growth"],
            revenue_growth_3y=r["revenue_growth_3y"],
            revenue_growth_5y=r["revenue_growth_5y"],
            revenue_growth_10y=r["revenue_growth_10y"],
            net_income_growth_3y=r["net_income_growth_3y"],
            net_income_growth_5y=r["net_income_growth_5y"],
        ) for r in rows]

    def get_fmp_analyst_grades(self, symbol: str, limit: int = 20) -> list[FMPAnalystGrade]:
        """Get analyst grades for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_analyst_grades WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPAnalystGrade(
            symbol=r["symbol"], date=r["date"],
            grading_company=r["grading_company"],
            previous_grade=r["previous_grade"],
            new_grade=r["new_grade"],
        ) for r in rows]

    def get_fmp_price_targets(self, symbol: str, limit: int = 20) -> list[FMPPriceTarget]:
        """Get price targets for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM fmp_price_targets WHERE symbol = ? "
            "ORDER BY published_date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [FMPPriceTarget(
            symbol=r["symbol"], published_date=r["published_date"],
            analyst_name=r["analyst_name"], analyst_company=r["analyst_company"],
            price_target=r["price_target"], price_when_posted=r["price_when_posted"],
        ) for r in rows]

    def upsert_sector_benchmark(
        self,
        symbol: str,
        metric: str,
        subject_value: float | None,
        peer_values: list[float],
    ) -> None:
        """Insert or replace a sector benchmark row for symbol+metric."""
        peer_count = len(peer_values)
        if peer_count == 0:
            sector_median = sector_p25 = sector_p75 = sector_min = sector_max = None
            percentile = None
        else:
            sorted_vals = sorted(peer_values)
            sector_median = statistics.median(sorted_vals)
            quantiles = statistics.quantiles(sorted_vals, n=4) if peer_count >= 2 else [sorted_vals[0]] * 3
            sector_p25 = quantiles[0]
            sector_p75 = quantiles[-1]
            sector_min = sorted_vals[0]
            sector_max = sorted_vals[-1]
            if subject_value is not None:
                percentile = sum(1 for v in peer_values if v <= subject_value) / peer_count * 100
            else:
                percentile = None

        self._conn.execute(
            "INSERT OR REPLACE INTO sector_benchmarks "
            "(subject_symbol, metric, subject_value, peer_count, "
            "sector_median, sector_p25, sector_p75, sector_min, sector_max, "
            "percentile, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (symbol, metric, subject_value, peer_count,
             sector_median, sector_p25, sector_p75, sector_min, sector_max,
             percentile),
        )
        self._conn.commit()

    def get_sector_benchmark(self, symbol: str, metric: str) -> dict | None:
        """Get a single sector benchmark row."""
        row = self._conn.execute(
            "SELECT * FROM sector_benchmarks WHERE subject_symbol = ? AND metric = ?",
            (symbol, metric),
        ).fetchone()
        return dict(row) if row else None

    def get_all_sector_benchmarks(self, symbol: str) -> list[dict]:
        """Get all sector benchmark rows for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM sector_benchmarks WHERE subject_symbol = ? ORDER BY metric",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]

    def clear_sector_benchmarks(self, symbol: str) -> None:
        """Delete all sector benchmark rows for a symbol."""
        self._conn.execute(
            "DELETE FROM sector_benchmarks WHERE subject_symbol = ?",
            (symbol,),
        )
        self._conn.commit()

    def upsert_analytical_snapshot(self, row: dict) -> None:
        """Upsert a single analytical snapshot row."""
        cols = [c[1] for c in self._conn.execute(
            "PRAGMA table_info(analytical_snapshot)"
        ).fetchall() if c[1] != "id"]
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO analytical_snapshot ({col_names}) VALUES ({placeholders})"
        self._conn.execute(sql, [row.get(c) for c in cols])
        self._conn.commit()

    def get_analytical_snapshot(self, symbol: str) -> dict | None:
        """Get latest analytical snapshot for a stock."""
        row = self._conn.execute(
            "SELECT * FROM analytical_snapshot WHERE symbol = ? "
            "ORDER BY computed_date DESC LIMIT 1",
            (symbol.upper(),)
        ).fetchone()
        return dict(row) if row else None

    def get_analytical_snapshots_all(self, computed_date: str | None = None) -> list[dict]:
        """Get latest snapshots for all stocks. For screening and batch operations."""
        if computed_date:
            rows = self._conn.execute(
                "SELECT * FROM analytical_snapshot WHERE computed_date = ?",
                (computed_date,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT a.* FROM analytical_snapshot a
                   INNER JOIN (
                       SELECT symbol, MAX(computed_date) as max_date
                       FROM analytical_snapshot GROUP BY symbol
                   ) b ON a.symbol = b.symbol AND a.computed_date = b.max_date"""
            ).fetchall()
        return [dict(r) for r in rows]

    def screen_by_analytics(self, filters: dict) -> list[dict]:
        """Screen stocks by analytical metrics.

        Filter keys: _min suffix (>=), _max suffix (<=), no suffix (exact match).
        Example: {"f_score_min": 7, "eq_signal": "high_quality"}
        """
        allowed = {c[1] for c in self._conn.execute(
            "PRAGMA table_info(analytical_snapshot)"
        ).fetchall()}

        conditions = []
        params = []
        for key, value in filters.items():
            if key.endswith("_min"):
                col = key[:-4]
                if col not in allowed:
                    continue
                conditions.append(f"{col} >= ?")
                params.append(value)
            elif key.endswith("_max"):
                col = key[:-4]
                if col not in allowed:
                    continue
                conditions.append(f"{col} <= ?")
                params.append(value)
            else:
                if key not in allowed:
                    continue
                conditions.append(f"{key} = ?")
                params.append(value)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""SELECT a.* FROM analytical_snapshot a
                  INNER JOIN (
                      SELECT symbol, MAX(computed_date) as max_date
                      FROM analytical_snapshot GROUP BY symbol
                  ) b ON a.symbol = b.symbol AND a.computed_date = b.max_date
                  WHERE {where}
                  ORDER BY a.composite_score DESC"""
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
