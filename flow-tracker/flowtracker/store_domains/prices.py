"""Prices & market-data domain (split from FlowStore, refactor P1.4).

Commodity prices + gold/silver ETF NAVs + gold-FII correlation, index daily
prices, MF scheme NAVs, market-breadth snapshots, daily stock OHLCV/delivery,
Screener chart data, corporate actions + split/bonus adjusted-close recompute,
and delisted-symbol / unresolved-cliff survivorship tracking. Methods moved
verbatim from store.py; they run on the FlowStore instance via mixin
composition, so ``self._conn`` and cross-calls like ``self.recompute_adj_close``
/ ``self.invalidate_screener_price_charts`` resolve unchanged. The module-level
``_row_to_breadth`` helper stays in store.py and is imported lazily inside the
breadth getters to avoid a circular import (store.py imports this mixin).
"""

from __future__ import annotations

import logging

from flowtracker.commodity_models import CommodityPrice, GoldETFNav, GoldCorrelation
from flowtracker.mf_nav_models import MFSchemeNav
from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.bhavcopy_models import DailyStockData

# Same logger name as store.py so corporate-action / adj-close log lines keep
# their original "flowtracker.store" channel after the move (behavior-preserving).
_logger = logging.getLogger("flowtracker.store")


class PricesMixin:
    """Commodities/ETF/index/MF-NAV/breadth/OHLCV/charts/corporate-actions/survivorship."""

    def upsert_commodity_prices(self, prices: list[CommodityPrice]) -> int:
        """Insert or replace commodity price records."""
        import math
        cursor = self._conn.cursor()
        count = 0
        for p in prices:
            if math.isnan(p.price):
                continue
            cursor.execute(
                "INSERT OR REPLACE INTO commodity_prices (date, symbol, price, unit) "
                "VALUES (?, ?, ?, ?)",
                (p.date, p.symbol, p.price, p.unit),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_etf_navs(self, navs: list[GoldETFNav]) -> int:
        """Insert or replace gold ETF NAV records."""
        cursor = self._conn.cursor()
        count = 0
        for n in navs:
            cursor.execute(
                "INSERT OR REPLACE INTO gold_etf_nav (date, scheme_code, scheme_name, nav) "
                "VALUES (?, ?, ?, ?)",
                (n.date, n.scheme_code, n.scheme_name, n.nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_commodity_prices(self, symbol: str, days: int = 30) -> list[CommodityPrice]:
        """Get commodity prices for a symbol, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM commodity_prices WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [CommodityPrice(
            date=r["date"], symbol=r["symbol"], price=r["price"], unit=r["unit"],
        ) for r in rows]

    def get_etf_navs(self, scheme_code: str, days: int = 365) -> list[GoldETFNav]:
        """Get ETF NAVs for a scheme, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM gold_etf_nav WHERE scheme_code = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (scheme_code, f"-{days}"),
        ).fetchall()
        return [GoldETFNav(
            date=r["date"], scheme_code=r["scheme_code"],
            scheme_name=r["scheme_name"], nav=r["nav"],
        ) for r in rows]

    def get_gold_fii_correlation(self, days: int = 30) -> list[GoldCorrelation]:
        """Get FII daily net flows aligned with gold price changes."""
        rows = self._conn.execute(
            "SELECT df.date, df.net_value AS fii_net, "
            "cp_gold.price AS gold_close, cp_inr.price AS gold_inr "
            "FROM daily_flows df "
            "LEFT JOIN commodity_prices cp_gold ON df.date = cp_gold.date AND cp_gold.symbol = 'GOLD' "
            "LEFT JOIN commodity_prices cp_inr ON df.date = cp_inr.date AND cp_inr.symbol = 'GOLD_INR' "
            "WHERE df.category = 'FII' AND cp_gold.price IS NOT NULL "
            "AND df.date >= date('now', ? || ' days') "
            "ORDER BY df.date DESC",
            (f"-{days}",),
        ).fetchall()

        results: list[GoldCorrelation] = []
        for i, r in enumerate(rows):
            # Calculate day-over-day gold change %
            if i + 1 < len(rows) and rows[i + 1]["gold_close"]:
                prev_gold = rows[i + 1]["gold_close"]
                change_pct = round((r["gold_close"] - prev_gold) / prev_gold * 100, 2) if prev_gold else 0.0
            else:
                change_pct = 0.0

            results.append(GoldCorrelation(
                date=r["date"],
                fii_net=r["fii_net"],
                gold_close=r["gold_close"],
                gold_change_pct=change_pct,
                gold_inr=r["gold_inr"],
            ))
        return results

    def upsert_index_daily_prices(self, records: list[dict]) -> int:
        """Upsert daily index price records. Returns count of rows upserted."""
        count = 0
        for r in records:
            self._conn.execute(
                "INSERT OR REPLACE INTO index_daily_prices (date, index_ticker, close) VALUES (?, ?, ?)",
                (r["date"], r["index_ticker"], r["close"]),
            )
            count += 1
        self._conn.commit()
        return count

    def get_index_prices(self, index_ticker: str, days: int = 800) -> list[dict]:
        """Get daily index closing prices, most recent first."""
        rows = self._conn.execute(
            "SELECT date, close FROM index_daily_prices "
            "WHERE index_ticker = ? ORDER BY date DESC LIMIT ?",
            (index_ticker, days),
        ).fetchall()
        return [{"date": r["date"], "close": r["close"]} for r in rows]

    def upsert_mf_scheme_navs(self, navs: list[MFSchemeNav]) -> int:
        """Insert or replace daily NAV rows for one or many schemes.

        Idempotent on the (scheme_code, date) PK; re-running a backfill
        overwrites prior rows so corrected mfapi values propagate. Each
        row also refreshes ``scheme_name`` (in case mfapi renames a
        scheme, e.g. "Bluechip" → "Large Cap").
        """
        if not navs:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for n in navs:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_scheme_nav_daily "
                "(scheme_code, date, scheme_name, nav) "
                "VALUES (?, ?, ?, ?)",
                (n.scheme_code, n.date, n.scheme_name, n.nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_scheme_nav_latest(self, scheme_code: int) -> MFSchemeNav | None:
        """Most recent NAV row for a scheme; ``None`` if not stored."""
        row = self._conn.execute(
            "SELECT scheme_code, date, scheme_name, nav "
            "FROM mf_scheme_nav_daily "
            "WHERE scheme_code = ? "
            "ORDER BY date DESC LIMIT 1",
            (scheme_code,),
        ).fetchone()
        if not row:
            return None
        return MFSchemeNav(
            scheme_code=row["scheme_code"],
            date=row["date"],
            scheme_name=row["scheme_name"],
            nav=row["nav"],
        )

    def get_mf_scheme_nav_history(
        self,
        scheme_code: int,
        days: int | None = None,
    ) -> list[MFSchemeNav]:
        """Historical NAV rows for a scheme (oldest-first).

        ``days``: when set, restricts to the last N days; otherwise
        returns the full stored history.
        """
        if days is not None:
            rows = self._conn.execute(
                "SELECT scheme_code, date, scheme_name, nav "
                "FROM mf_scheme_nav_daily "
                "WHERE scheme_code = ? "
                "AND date >= date('now', ? || ' days') "
                "ORDER BY date ASC",
                (scheme_code, f"-{int(days)}"),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT scheme_code, date, scheme_name, nav "
                "FROM mf_scheme_nav_daily "
                "WHERE scheme_code = ? "
                "ORDER BY date ASC",
                (scheme_code,),
            ).fetchall()
        return [
            MFSchemeNav(
                scheme_code=r["scheme_code"],
                date=r["date"],
                scheme_name=r["scheme_name"],
                nav=r["nav"],
            )
            for r in rows
        ]

    def get_mf_scheme_nav_universe(self) -> list[tuple[int, str, str, str, int]]:
        """List every stored scheme with coverage summary.

        Returns rows of (scheme_code, scheme_name, first_date,
        last_date, row_count) ordered by scheme_code. Used by
        ``flowtrack mf nav coverage`` to verify backfill health at a
        glance.
        """
        rows = self._conn.execute(
            "SELECT scheme_code, "
            "       MIN(scheme_name) AS scheme_name, "
            "       MIN(date) AS first_date, "
            "       MAX(date) AS last_date, "
            "       COUNT(*) AS n "
            "FROM mf_scheme_nav_daily "
            "GROUP BY scheme_code "
            "ORDER BY scheme_code"
        ).fetchall()
        return [
            (r["scheme_code"], r["scheme_name"], r["first_date"], r["last_date"], r["n"])
            for r in rows
        ]

    def upsert_breadth_snapshots(self, snapshots: list[BreadthSnapshot]) -> int:
        """Insert or replace market-breadth snapshots.

        UNIQUE(date, index_name) — re-running for the same date overwrites
        (idempotent recompute).
        """
        cursor = self._conn.cursor()
        count = 0
        for s in snapshots:
            cursor.execute(
                "INSERT OR REPLACE INTO market_breadth_daily "
                "(date, index_name, total, pct_above_200dma, advance, decline, "
                " unchanged, new_52w_highs, new_52w_lows, ad_ratio) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s.date, s.index_name, s.total, s.pct_above_200dma,
                    s.advance, s.decline, s.unchanged,
                    s.new_52w_highs, s.new_52w_lows, s.ad_ratio,
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_breadth_latest(self, index_name: str) -> BreadthSnapshot | None:
        """Most recent breadth snapshot for an index."""
        from flowtracker.store import _row_to_breadth
        row = self._conn.execute(
            "SELECT * FROM market_breadth_daily WHERE index_name = ? "
            "ORDER BY date DESC LIMIT 1",
            (index_name,),
        ).fetchone()
        if not row:
            return None
        return _row_to_breadth(row)

    def get_breadth_trend(
        self, index_name: str, days: int = 30,
    ) -> list[BreadthSnapshot]:
        """Last N days of breadth for an index, most recent first."""
        from flowtracker.store import _row_to_breadth
        rows = self._conn.execute(
            "SELECT * FROM market_breadth_daily WHERE index_name = ? "
            "ORDER BY date DESC LIMIT ?",
            (index_name, days),
        ).fetchall()
        return [_row_to_breadth(r) for r in rows]

    def get_breadth_for_date(self, date_str: str) -> list[BreadthSnapshot]:
        """All indices' breadth snapshots for one date."""
        from flowtracker.store import _row_to_breadth
        rows = self._conn.execute(
            "SELECT * FROM market_breadth_daily WHERE date = ? "
            "ORDER BY index_name",
            (date_str,),
        ).fetchall()
        return [_row_to_breadth(r) for r in rows]

    def upsert_daily_stock_data(self, records: list[DailyStockData]) -> int:
        """Insert or replace daily stock data records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO daily_stock_data "
                "(date, symbol, open, high, low, close, prev_close, volume, "
                "turnover, delivery_qty, delivery_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.date, r.symbol, r.open, r.high, r.low, r.close, r.prev_close,
                 r.volume, r.turnover, r.delivery_qty, r.delivery_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_top_delivery(self, date_str: str | None = None, limit: int = 20) -> list[DailyStockData]:
        """Get stocks with highest delivery % for a date (default: latest)."""
        if date_str is None:
            row = self._conn.execute("SELECT MAX(date) as d FROM daily_stock_data").fetchone()
            if not row or not row["d"]:
                return []
            date_str = row["d"]
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE date = ? AND delivery_pct IS NOT NULL "
            "ORDER BY delivery_pct DESC LIMIT ?",
            (date_str, limit),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    def get_stock_delivery(self, symbol: str, days: int = 30) -> list[DailyStockData]:
        """Get delivery trend for a specific stock."""
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    def upsert_chart_data(self, symbol: str, chart_type: str, datasets: list[dict]) -> int:
        """Store chart API datasets. Each dataset has metric, label, values."""
        count = 0
        for ds in datasets:
            metric = ds.get("metric", "")
            for item in ds.get("values", []):
                date_val, value = item[0], item[1]
                self._conn.execute(
                    "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol, chart_type, metric, date) DO UPDATE SET value=excluded.value",
                    (symbol, chart_type, metric, str(date_val), value),
                )
                count += 1
                # Volume dataset includes delivery % as third element: {"delivery": pct}
                if len(item) > 2 and isinstance(item[2], dict) and "delivery" in item[2]:
                    self._conn.execute(
                        "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(symbol, chart_type, metric, date) DO UPDATE SET value=excluded.value",
                        (symbol, chart_type, f"{metric}_Delivery", str(date_val), item[2]["delivery"]),
                    )
                    count += 1
        self._conn.commit()
        return count

    def invalidate_screener_price_charts(self, symbol: str) -> int:
        """Delete cached Screener price chart rows for symbol.

        Called after a split/bonus corporate action lands: Screener's stored
        price series becomes stale (pre-adjustment) until the next fetch, and
        a discontinuity cliff at ex-date will skew any downstream chart/
        analysis. Deletion forces the next `fund chart` / scheduled refresh
        to re-fetch the now-post-adjusted series from Screener.

        Only invalidates chart_type='price' — PE is a ratio (P/E), where both
        numerator and denominator halve together on split/bonus, so the ratio
        is adjustment-invariant. No cascade needed for chart_type='pe'.

        Returns rows deleted.
        """
        cur = self._conn.execute(
            "DELETE FROM screener_charts WHERE symbol = ? AND chart_type = 'price'",
            (symbol.upper(),),
        )
        self._conn.commit()
        return cur.rowcount

    def get_chart_data(self, symbol: str, chart_type: str) -> list[dict]:
        """Get stored chart data grouped by metric."""
        rows = self._conn.execute(
            "SELECT metric, date, value FROM screener_charts "
            "WHERE symbol = ? AND chart_type = ? ORDER BY metric, date",
            (symbol, chart_type),
        ).fetchall()
        from collections import defaultdict

        grouped: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            grouped[r["metric"]].append({"date": r["date"], "value": r["value"]})
        return [{"metric": m, "values": v} for m, v in grouped.items()]

    def upsert_corporate_actions(
        self, actions: list[dict], recompute_adj_close: bool = True,
    ) -> int:
        """Store corporate actions.

        Sync hook: by default, recomputes daily_stock_data.adj_close for every
        symbol whose actions were modified. This keeps the adjusted-price
        surface consistent with corporate_actions the moment new rows land.

        Pass recompute_adj_close=False from batch backfill paths that do their
        own end-of-run recompute (avoids redundant work across many symbols).
        """
        count = 0
        touched_symbols: dict[str, list[str]] = {}
        for a in actions:
            self._conn.execute(
                "INSERT OR REPLACE INTO corporate_actions "
                "(symbol, ex_date, action_type, ratio_text, multiplier, dividend_amount, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a["symbol"], a["ex_date"], a["action_type"], a.get("ratio_text"),
                 a.get("multiplier"), a.get("dividend_amount"), a["source"]),
            )
            count += 1
            if a["action_type"] in ("split", "bonus"):
                touched_symbols.setdefault(a["symbol"].upper(), []).append(a["action_type"])
        self._conn.commit()

        if recompute_adj_close and touched_symbols:
            for sym, action_types in touched_symbols.items():
                self.recompute_adj_close(sym)
                # Invalidate any cached Screener price chart — it's now stale
                # (pre-adjustment). Next fund chart fetch will repopulate from
                # Screener's post-adjusted series. PE chart stays valid (ratio).
                deleted = self.invalidate_screener_price_charts(sym)
                if deleted:
                    _logger.info(
                        "invalidated %d screener_chart rows for %s after %s",
                        deleted, sym, action_types,
                    )

        return count

    def delete_corporate_action(
        self, symbol: str, ex_date: str, action_type: str,
        source: str = "bse", recompute_adj_close: bool = True,
    ) -> int:
        """Delete a single corporate action row (for data corrections).

        Sync hook: by default, re-runs recompute_adj_close(symbol) so the
        adjusted-price surface drops the now-removed multiplier immediately.
        Mirrors the upsert hook — a deletion is just an opposite-direction
        correction and must keep adj_close in sync the same way.
        """
        cursor = self._conn.execute(
            "DELETE FROM corporate_actions WHERE symbol = ? AND ex_date = ? "
            "AND action_type = ? AND source = ?",
            (symbol.upper(), ex_date, action_type, source),
        )
        self._conn.commit()
        deleted = cursor.rowcount
        if deleted and recompute_adj_close and action_type in ("split", "bonus"):
            self.recompute_adj_close(symbol.upper())
            n = self.invalidate_screener_price_charts(symbol.upper())
            if n:
                _logger.info(
                    "invalidated %d screener_chart rows for %s after delete %s",
                    n, symbol.upper(), [action_type],
                )
        return deleted

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        """Get all corporate actions for a symbol, ordered by date desc."""
        rows = self._conn.execute(
            "SELECT * FROM corporate_actions WHERE symbol = ? ORDER BY ex_date DESC",
            (symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_delisted_symbols(self, rows: list[dict]) -> int:
        """Upsert ``delisted_symbols`` rows. Reason ∈ {gap_180d, manually_parked, unknown}."""
        for r in rows:
            self._conn.execute(
                "INSERT OR REPLACE INTO delisted_symbols "
                "(symbol, last_active_date, observations, reason) VALUES (?, ?, ?, ?)",
                (r["symbol"].upper(), r.get("last_active_date"),
                 r.get("observations"), r.get("reason", "unknown")),
            )
        self._conn.commit()
        return len(rows)

    def get_delisted_symbols(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT symbol, last_active_date, observations, reason, detected_at "
            "FROM delisted_symbols ORDER BY symbol"
        ).fetchall()
        return [dict(r) for r in rows]

    def detect_delisted_from_gaps(self, gap_days: int = 180) -> list[dict]:
        """Single GROUP BY scan — symbols whose latest bhavcopy row is ≥gap_days old."""
        rows = self._conn.execute(
            "SELECT symbol, MAX(date) AS last_active_date, COUNT(*) AS observations "
            "FROM daily_stock_data GROUP BY symbol "
            "HAVING DATE(MAX(date)) <= DATE('now', '-' || ? || ' days')",
            (gap_days,),
        ).fetchall()
        return [{"symbol": r["symbol"], "last_active_date": r["last_active_date"],
                 "observations": r["observations"], "reason": "gap_180d"} for r in rows]

    def upsert_unresolved_cliffs(self, rows: list[dict]) -> int:
        for r in rows:
            self._conn.execute(
                "INSERT OR REPLACE INTO unresolved_cliffs "
                "(symbol, trade_date, prev_close, close, return_pct) VALUES (?, ?, ?, ?, ?)",
                (r["symbol"].upper(), r["trade_date"], r.get("prev_close"),
                 r.get("close"), r.get("return_pct")),
            )
        self._conn.commit()
        return len(rows)

    def get_unresolved_cliffs(self, symbol: str | None = None) -> list[dict]:
        if symbol:
            rows = self._conn.execute(
                "SELECT symbol, trade_date, prev_close, close, return_pct, detected_at "
                "FROM unresolved_cliffs WHERE symbol = ? ORDER BY trade_date DESC",
                (symbol.upper(),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT symbol, trade_date, prev_close, close, return_pct, detected_at "
                "FROM unresolved_cliffs ORDER BY symbol, trade_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def recompute_adj_close(self, symbol: str) -> int:
        """Populate daily_stock_data.adj_close + adj_factor for symbol.

        For each price row at date D:
            adj_factor = product of effective multipliers for all split/bonus
                         actions with ex_date > D (convention: ex_date row is
                         already post-action, so actions apply strictly to
                         dates BEFORE ex_date).
            adj_close  = close / adj_factor

        **Price-cliff verification**: before applying an action's multiplier,
        cross-check against the actual close/prev_close ratio at ex_date. If
        the observed ratio is inconsistent with the declared multiplier (either
        no cliff — NSE already reconciled the historical series — or large
        mismatch — data-quality issue), the action is skipped. This guards
        against:
          • Old actions where NSE bhavcopy historical data is pre-adjusted
            (e.g. BAJFINANCE 2016-09-08 has action recorded but price ratio
            is 1.02, not 0.2 — applying would phantom-amplify pre-2016 by 10x).
          • Corporate_actions rows with stale/wrong multipliers.

        Note: actions with NULL or missing close/prev_close at ex_date pass
        through unchecked (can't verify without price data). Compound actions
        on same ex_date are verified against the combined multiplier.

        Returns number of rows updated.
        """
        symbol = symbol.upper()
        rows = self._conn.execute(
            "SELECT date, close FROM daily_stock_data WHERE symbol = ? ORDER BY date DESC",
            (symbol,),
        ).fetchall()
        if not rows:
            return 0

        raw_actions = [a for a in self.get_split_bonus_actions(symbol) if a.get("multiplier")]

        # Group actions by ex_date → compose combined multiplier per date.
        # Verify against observed price cliff at ex_date before accepting.
        from collections import defaultdict
        per_date: dict[str, float] = defaultdict(lambda: 1.0)
        for a in raw_actions:
            per_date[a["ex_date"]] *= a["multiplier"]

        verified_actions: list[tuple[str, float]] = []
        for ex_date, composed_mult in per_date.items():
            px = self._conn.execute(
                "SELECT close, prev_close FROM daily_stock_data "
                "WHERE symbol = ? AND date = ?",
                (symbol, ex_date),
            ).fetchone()
            if px and px["close"] and px["prev_close"] and px["prev_close"] > 0:
                observed_ratio = px["close"] / px["prev_close"]
                expected_ratio = 1.0 / composed_mult
                # Forward splits/bonuses: expected_ratio < 1 (price drops).
                # Reverse splits: expected_ratio > 1 (price jumps — multiplier
                # < 1, e.g. GESHIP 2006-10-16 0.8 means 5:4 consolidation).
                # Verification rules:
                #   (a) Forward action (mult > 1) with no cliff present
                #       (observed > 0.85) — data already reconciled. Skip.
                #   (b) Reverse action (mult < 1) with no jump present
                #       (observed < 1.15) — same pattern. Skip.
                #   (c) Cliff/jump direction matches but magnitude way off
                #       (more than ±30% of expected). Skip.
                if composed_mult > 1.0 and observed_ratio > 0.85:
                    continue
                if composed_mult < 1.0 and observed_ratio < 1.15:
                    continue
                if abs(observed_ratio - expected_ratio) > 0.3 * expected_ratio:
                    continue
            # No price data to verify (e.g. pre-bhavcopy era, weekend ex_date),
            # OR verification passed.
            verified_actions.append((ex_date, composed_mult))

        if not verified_actions:
            self._conn.execute(
                "UPDATE daily_stock_data SET adj_close = close, adj_factor = 1.0 "
                "WHERE symbol = ?",
                (symbol,),
            )
            self._conn.commit()
            return len(rows)

        # Sort latest-first for the two-pointer walk.
        actions_desc = sorted(verified_actions, key=lambda a: a[0], reverse=True)

        running_factor = 1.0
        action_idx = 0
        updates: list[tuple[float, float, str, str]] = []

        for row in rows:  # latest → earliest
            date = row["date"]
            close = row["close"]
            while action_idx < len(actions_desc) and actions_desc[action_idx][0] > date:
                running_factor *= actions_desc[action_idx][1]
                action_idx += 1
            adj_close = close / running_factor if running_factor else close
            updates.append((adj_close, running_factor, symbol, date))

        self._conn.executemany(
            "UPDATE daily_stock_data SET adj_close = ?, adj_factor = ? "
            "WHERE symbol = ? AND date = ?",
            updates,
        )
        self._conn.commit()
        return len(updates)

    def get_split_bonus_actions(self, symbol: str) -> list[dict]:
        """Get split + bonus actions for adjustment factor computation.

        Dedup is per (ex_date, action_type) — not per ex_date — so a genuine
        compound action (split AND bonus on same ex_date, e.g. BAJFINANCE
        2025-06-16: 1:2 split × 1:4 bonus → total multiplier 10) is preserved.
        Within each (ex_date, action_type) group, BSE wins over yfinance
        because yfinance can't distinguish bonus from split and often
        mis-classifies the event type.

        NULL-multiplier inference: if a split/bonus row has a NULL multiplier
        but the daily_stock_data shows a real price cliff at ex_date (close/
        prev_close < 0.80), the multiplier is inferred as prev_close / close.
        This recovers actions that were captured structurally but lost their
        ratio metadata (e.g. ANGELONE 2026-02-26, BEML 2025-11-03, ADANIPOWER
        2025-09-22 — all show 50%+ single-day drops with no declared
        multiplier). Inferred rows are tagged with source='inferred' so
        verification downstream can treat them consistently.

        Empirical check: for nearly all symbols with same-date split + bonus
        reports, the two multipliers match (yfinance + BSE describing the
        same event). BAJFINANCE is the compound-action exception this dedup
        strategy correctly handles by keeping both rows.
        """
        symbol_upper = symbol.upper()

        # Infer multipliers for NULL-multiplier rows that have a clear cliff.
        inferred = self._conn.execute(
            """SELECT ca.ex_date, ca.action_type,
                      d.prev_close / NULLIF(d.close, 0) AS inferred_mult
               FROM corporate_actions ca
               JOIN daily_stock_data d
                 ON d.symbol = ca.symbol AND d.date = ca.ex_date
               WHERE ca.symbol = ?
                 AND ca.action_type IN ('split', 'bonus')
                 AND ca.multiplier IS NULL
                 AND d.prev_close > 0
                 AND d.close / d.prev_close < 0.80""",
            (symbol_upper,),
        ).fetchall()

        rows = self._conn.execute(
            "SELECT * FROM corporate_actions WHERE symbol = ? "
            "AND action_type IN ('split', 'bonus') AND multiplier IS NOT NULL "
            "ORDER BY ex_date ASC, action_type ASC, source ASC",
            (symbol_upper,),
        ).fetchall()

        # Key by (ex_date, action_type). BSE wins within a group.
        by_key: dict[tuple[str, str], dict] = {}
        for r in rows:
            d = dict(r)
            key = (d["ex_date"], d["action_type"])
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = d
            elif existing["source"] == "yfinance" and d["source"] == "bse":
                by_key[key] = d
            # Otherwise keep the existing row (BSE already claimed it, or
            # yfinance after BSE arriving late — first-write-wins).

        # Merge in inferred multipliers for NULL-multiplier rows where we
        # detected a real price cliff. Only inject when no explicit row
        # already exists for (ex_date, action_type) — respects existing data.
        for inf in inferred:
            key = (inf["ex_date"], inf["action_type"])
            if key in by_key:
                continue
            by_key[key] = {
                "symbol": symbol_upper,
                "ex_date": inf["ex_date"],
                "action_type": inf["action_type"],
                "multiplier": round(inf["inferred_mult"], 6),
                "ratio_text": "inferred_from_cliff",
                "dividend_amount": None,
                "source": "inferred",
            }

        # Cross-type collision: when yfinance reports type X with multiplier M
        # and BSE reports type Y (different) on the same date with the SAME
        # multiplier, they're describing the same event — drop the yfinance
        # duplicate to avoid double-multiplying. Match is heuristic but safe:
        # multiplier equality on same date across opposing types strongly
        # implies a single event.
        dates_with_bse_multipliers: dict[str, set[float]] = {}
        for (ex_date, at), row in by_key.items():
            if row["source"] == "bse":
                dates_with_bse_multipliers.setdefault(ex_date, set()).add(row["multiplier"])
        filtered: dict[tuple[str, str], dict] = {}
        for key, row in by_key.items():
            ex_date = key[0]
            if (
                row["source"] == "yfinance"
                and ex_date in dates_with_bse_multipliers
                and row["multiplier"] in dates_with_bse_multipliers[ex_date]
            ):
                # BSE already has an action on this date with the same multiplier
                # — assume it's the same event reported twice, skip the yfinance row.
                continue
            filtered[key] = row

        # Deterministic order: compound actions sharing ex_date (split + bonus)
        # must audit in the same sequence every run — tie-break on action_type
        # then multiplier so recompute_adj_close sees a stable iteration order.
        return sorted(
            filtered.values(),
            key=lambda r: (r["ex_date"], r["action_type"], r["multiplier"]),
        )
