"""Holdings & ownership domain (split from FlowStore, refactor P1.4).

Shareholding records + changes/handoff signals, promoter pledges, shareholding
breakdown, AR ESOP / five-year / ADR-GDR summaries, bulk/block deals, insider
transactions, MF scheme holdings, shareholder details, and ADR program
directory. Methods moved verbatim from store.py; they run on the FlowStore
instance via mixin composition, so ``self._conn`` is the shared connection. The
validation helpers live in store_domains/_shared.py.
"""

from __future__ import annotations

from datetime import date

from flowtracker.holding_models import (
    ShareholdingRecord,
    ShareholdingChange,
    PromoterPledge,
    ShareholdingBreakdown,
)
from flowtracker.deals_models import BulkBlockDeal
from flowtracker.insider_models import InsiderTransaction
from flowtracker.mfportfolio_models import MFSchemeHolding, MFHoldingChange
from flowtracker.store_domains._shared import _validate_row, _val_logger


class HoldingsMixin:
    """Shareholding, pledges, breakdown, deals, insider, MF holdings, ADR programs."""

    def upsert_shareholding(self, records: list[ShareholdingRecord]) -> int:
        """Insert or replace shareholding records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            # Check for existing value before replace
            existing = self._conn.execute(
                "SELECT percentage FROM shareholding WHERE symbol = ? AND quarter_end = ? AND category = ?",
                (r.symbol, r.quarter_end, r.category),
            ).fetchone()
            if existing and existing["percentage"] != r.percentage:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("shareholding", r.symbol, f"{r.quarter_end}|{r.category}",
                     "percentage", str(existing["percentage"]), str(r.percentage)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO shareholding (symbol, quarter_end, category, percentage) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.category, r.percentage),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_shareholding(self, symbol: str, limit: int = 8) -> list[ShareholdingRecord]:
        """Get shareholding records for a symbol, most recent quarters first.

        `limit` is the number of QUARTERS requested. Row budget is computed
        dynamically from the actual distinct categories present for this
        symbol — post-2023 Screener data has 7 categories (Promoter, FII, DII,
        MF, Insurance, Public, AIF) while pre-2023 data has 4-6. Hard-coding
        `limit*6` previously dropped ~1 quarter of data for symbols with 7
        categories (e.g. HDFCBANK returned 11 quarters instead of 12).
        """
        cat_row = self._conn.execute(
            "SELECT COUNT(DISTINCT category) FROM shareholding WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        cats_per_quarter = (cat_row[0] if cat_row and cat_row[0] else 7)
        row_budget = limit * cats_per_quarter
        rows = self._conn.execute(
            "SELECT * FROM shareholding WHERE symbol = ? "
            "ORDER BY quarter_end DESC, category LIMIT ?",
            (symbol.upper(), row_budget),
        ).fetchall()
        return [ShareholdingRecord(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            category=r["category"], percentage=r["percentage"],
        ) for r in rows]

    def get_shareholding_changes(self, symbol: str) -> list[ShareholdingChange]:
        """Get quarter-over-quarter shareholding changes for a symbol."""
        rows = self._conn.execute(
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.symbol = ? "
            "AND s1.quarter_end = (SELECT MAX(quarter_end) FROM shareholding WHERE symbol = ?) "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC",
            (symbol.upper(), symbol.upper()),
        ).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_biggest_changes(self, category: str | None = None, limit: int = 10) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all watchlist stocks."""
        cat_filter = "AND s1.category = ?" if category else ""
        params: list = []

        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN watchlist w ON s1.symbol = w.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            f") {cat_filter} "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC LIMIT ?"
        )
        if category:
            params = [category, limit]
        else:
            params = [limit]

        rows = self._conn.execute(query, params).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_handoff_signals(self, limit: int = 20) -> list[tuple[ShareholdingChange, ShareholdingChange]]:
        """Find stocks where FII decreased AND MF increased (handoff pattern).

        Returns list of (fii_change, mf_change) tuples.
        """
        # Get all latest QoQ changes for scanner stocks
        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN index_constituents ic ON s1.symbol = ic.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            ") "
            "AND s1.category IN ('FII', 'MF') "
            "GROUP BY s1.symbol, s1.category "
            "ORDER BY s1.symbol"
        )
        rows = self._conn.execute(query).fetchall()

        # Group by symbol, find FII-down + MF-up pairs
        by_symbol: dict[str, dict[str, ShareholdingChange]] = {}
        for r in rows:
            change = ShareholdingChange(
                symbol=r["symbol"], category=r["category"],
                prev_quarter_end=r["prev_qtr"], curr_quarter_end=r["curr_qtr"],
                prev_pct=r["prev_pct"], curr_pct=r["curr_pct"],
                change_pct=r["curr_pct"] - r["prev_pct"],
            )
            by_symbol.setdefault(r["symbol"], {})[r["category"]] = change

        handoffs: list[tuple[ShareholdingChange, ShareholdingChange]] = []
        for symbol, cats in by_symbol.items():
            fii = cats.get("FII")
            mf = cats.get("MF")
            if fii and mf and fii.change_pct < 0 and mf.change_pct > 0:
                handoffs.append((fii, mf))

        # Sort by FII selling magnitude
        handoffs.sort(key=lambda x: x[0].change_pct)
        return handoffs[:limit]

    def upsert_promoter_pledges(self, pledges: list[PromoterPledge]) -> int:
        """Insert or replace promoter pledge records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for p in pledges:
            existing = self._conn.execute(
                "SELECT pledge_pct, encumbered_pct FROM promoter_pledge WHERE symbol = ? AND quarter_end = ?",
                (p.symbol, p.quarter_end),
            ).fetchone()
            if existing and (existing["pledge_pct"] != p.pledge_pct or existing["encumbered_pct"] != p.encumbered_pct):
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("promoter_pledge", p.symbol, p.quarter_end,
                     "pledge_pct", str(existing["pledge_pct"]), str(p.pledge_pct)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO promoter_pledge (symbol, quarter_end, pledge_pct, encumbered_pct) "
                "VALUES (?, ?, ?, ?)",
                (p.symbol, p.quarter_end, p.pledge_pct, p.encumbered_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_promoter_pledge(self, symbol: str, limit: int = 8) -> list[PromoterPledge]:
        """Get promoter pledge history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM promoter_pledge WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def get_high_pledge_stocks(self, min_pledge_pct: float = 1.0, limit: int = 20) -> list[PromoterPledge]:
        """Get stocks with high promoter pledging from latest quarter, joined with scanner stocks."""
        rows = self._conn.execute(
            "SELECT pp.* FROM promoter_pledge pp "
            "INNER JOIN index_constituents ic ON pp.symbol = ic.symbol "
            "WHERE pp.quarter_end = ("
            "  SELECT MAX(pp2.quarter_end) FROM promoter_pledge pp2 WHERE pp2.symbol = pp.symbol"
            ") AND pp.pledge_pct >= ? "
            "ORDER BY pp.pledge_pct DESC LIMIT ?",
            (min_pledge_pct, limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def upsert_shareholding_breakdown(self, breakdowns: list[ShareholdingBreakdown]) -> int:
        """Insert or replace granular shareholding sub-category rows."""
        if not breakdowns:
            return 0
        all_fields = self._BREAKDOWN_PCT_FIELDS + self._BREAKDOWN_INT_FIELDS
        cols_sql = ", ".join(("symbol", "quarter_end", *all_fields))
        placeholders = ", ".join(["?"] * (2 + len(all_fields)))
        sql = (
            f"INSERT OR REPLACE INTO shareholding_breakdown ({cols_sql}) "
            f"VALUES ({placeholders})"
        )
        cur = self._conn.cursor()
        count = 0
        for b in breakdowns:
            params = [b.symbol.upper(), b.quarter_end]
            for fld in all_fields:
                params.append(getattr(b, fld, None))
            cur.execute(sql, params)
            count += cur.rowcount
        self._conn.commit()
        return count

    def get_shareholding_breakdown(
        self, symbol: str, limit: int = 8,
    ) -> list[ShareholdingBreakdown]:
        """Latest-first granular breakdown rows for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM shareholding_breakdown WHERE symbol = ? "
            "ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        out: list[ShareholdingBreakdown] = []
        for r in rows:
            kw: dict = {"symbol": r["symbol"], "quarter_end": r["quarter_end"]}
            for fld in self._BREAKDOWN_PCT_FIELDS + self._BREAKDOWN_INT_FIELDS:
                kw[fld] = r[fld] if fld in r.keys() else None
            kw["fetched_at"] = r["fetched_at"] if "fetched_at" in r.keys() else None
            out.append(ShareholdingBreakdown(**kw))
        return out

    def get_latest_shareholding_breakdown(
        self, symbol: str,
    ) -> ShareholdingBreakdown | None:
        """Single most-recent breakdown row, or None when nothing on file."""
        rows = self.get_shareholding_breakdown(symbol, limit=1)
        return rows[0] if rows else None

    def upsert_ar_esop_summary(
        self,
        symbol: str,
        fiscal_year: str,
        *,
        total_plans: int | None = None,
        options_outstanding: float | None = None,
        options_outstanding_pct_paidup: float | None = None,
        options_granted_fy: float | None = None,
        options_exercised_fy: float | None = None,
        options_lapsed_fy: float | None = None,
        weighted_avg_exercise_price: float | None = None,
        plans_json: str | None = None,
    ) -> int:
        """Persist (or replace) one ESOP summary row.

        `plans_json` is the raw JSON string for the per-plan list — pass
        `json.dumps(plans_list)` from the caller; this method does not
        re-serialize.
        """
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO ar_esop_summary "
            "(symbol, fiscal_year, total_plans, options_outstanding, "
            "options_outstanding_pct_paidup, options_granted_fy, "
            "options_exercised_fy, options_lapsed_fy, "
            "weighted_avg_exercise_price, plans_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol.upper(), fiscal_year, total_plans, options_outstanding,
                options_outstanding_pct_paidup, options_granted_fy,
                options_exercised_fy, options_lapsed_fy,
                weighted_avg_exercise_price, plans_json,
            ),
        )
        self._conn.commit()
        return cur.rowcount

    def get_ar_esop_summary(self, symbol: str, limit: int = 5) -> list[dict]:
        """Latest-first ESOP summary rows for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM ar_esop_summary WHERE symbol = ? "
            "ORDER BY fiscal_year DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_five_year_summary(self, symbol: str, rows: list) -> int:
        """Persist (or replace) parsed 5/10-year highlight rows for a symbol.

        `rows` is an iterable of FiveYearHighlight Pydantic instances (or
        dicts with the same fields). Idempotent on (symbol, fy_end).
        Returns the number of rows written.

        Newer ARs supersede older ones — a row with the same fy_end from
        a more recent AR will overwrite the older value via INSERT OR
        REPLACE. Caller should walk ARs in chronological order
        (oldest first) so the newest restated values win.
        """
        cur = self._conn.cursor()
        sym_upper = symbol.upper()
        count = 0
        for r in rows:
            d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
            cur.execute(
                "INSERT OR REPLACE INTO ar_five_year_summary "
                "(symbol, fy_end, revenue, operating_profit, pat, eps, "
                "net_worth, total_assets, borrowings, cfo, capex, "
                "dividend_per_share, num_shares, source_ar_fy, raw_unit) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sym_upper, d.get("fy_end"),
                    d.get("revenue"), d.get("operating_profit"), d.get("pat"),
                    d.get("eps"), d.get("net_worth"), d.get("total_assets"),
                    d.get("borrowings"), d.get("cfo"), d.get("capex"),
                    d.get("dividend_per_share"), d.get("num_shares"),
                    d.get("source_ar_fy"), d.get("raw_unit"),
                ),
            )
            count += 1
        self._conn.commit()
        return count

    def get_five_year_summary(self, symbol: str, limit: int = 11) -> list[dict]:
        """Latest-first restated 5/10-year highlights for a symbol.

        Returns up to `limit` rows ordered by fy_end DESC. Empty list when
        the symbol has no AR-restated highlights persisted (i.e., the AR
        section was image-rendered, missing, or extraction never ran).
        """
        rows = self._conn.execute(
            "SELECT * FROM ar_five_year_summary WHERE symbol = ? "
            "ORDER BY fy_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_adr_gdr_outstanding(
        self,
        symbol: str,
        as_of_date: str,
        *,
        listed_on: str | None = None,
        sponsor_bank: str | None = None,
        adr_ratio: str | None = None,
        units_outstanding: float | None = None,
        underlying_shares_outstanding: float | None = None,
        pct_of_total_equity: float | None = None,
        source: str = "manual_seed",
        notes: str | None = None,
    ) -> int:
        """Insert or replace one ADR/GDR outstanding row keyed by (symbol, as_of_date)."""
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO adr_gdr_outstanding "
            "(symbol, as_of_date, listed_on, sponsor_bank, adr_ratio, "
            "units_outstanding, underlying_shares_outstanding, "
            "pct_of_total_equity, source, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol.upper(), as_of_date, listed_on, sponsor_bank, adr_ratio,
                units_outstanding, underlying_shares_outstanding,
                pct_of_total_equity, source, notes,
            ),
        )
        self._conn.commit()
        return cur.rowcount

    def get_adr_gdr_outstanding(self, symbol: str, limit: int = 5) -> list[dict]:
        """Latest-first ADR/GDR rows for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM adr_gdr_outstanding WHERE symbol = ? "
            "ORDER BY as_of_date DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_deals(self, deals: list[BulkBlockDeal]) -> int:
        """Insert or replace bulk/block deal records."""
        cursor = self._conn.cursor()
        count = 0
        for d in deals:
            cursor.execute(
                "INSERT OR REPLACE INTO bulk_block_deals "
                "(date, deal_type, symbol, client_name, buy_sell, quantity, price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (d.date, d.deal_type, d.symbol, d.client_name, d.buy_sell,
                 d.quantity, d.price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_deals_latest(self) -> list[BulkBlockDeal]:
        """Get deals for the most recent day."""
        row = self._conn.execute("SELECT MAX(date) as d FROM bulk_block_deals").fetchone()
        if not row or not row["d"]:
            return []
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE date = ? ORDER BY deal_type, symbol",
            (row["d"],),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_by_symbol(self, symbol: str) -> list[BulkBlockDeal]:
        """Get all deals for a specific symbol."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE symbol = ? ORDER BY date DESC",
            (symbol,),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_top(self, days: int = 30, limit: int = 20) -> list[BulkBlockDeal]:
        """Get biggest deals by value in the last N days."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals "
            "WHERE date >= date('now', ? || ' days') AND price IS NOT NULL "
            "ORDER BY (quantity * price) DESC LIMIT ?",
            (f"-{days}", limit),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def upsert_insider_transactions(self, trades: list[InsiderTransaction]) -> int:
        """Insert or replace insider transaction records."""
        cursor = self._conn.cursor()
        today_iso = date.today().isoformat()
        count = 0
        for t in trades:
            # NSE occasionally emits future/implausible transaction dates (a
            # transaction can't be reported before it happens). Reject them so
            # they never pollute the table. See issue #175.
            if t.date and t.date > today_iso:
                _val_logger.warning(
                    "insider_transactions %s: dropping future-dated row %s > today %s",
                    t.symbol, t.date, today_iso,
                )
                continue
            warnings = _validate_row("insider_transactions", t.model_dump())
            if warnings:
                _val_logger.warning("insider_transactions %s/%s: %s", t.symbol, t.date, "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO insider_transactions "
                "(date, symbol, person_name, person_category, transaction_type, "
                "quantity, value, mode, holding_before_pct, holding_after_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t.date, t.symbol, t.person_name, t.person_category,
                 t.transaction_type, t.quantity, t.value, t.mode,
                 t.holding_before_pct, t.holding_after_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_insider_by_symbol(self, symbol: str, days: int = 1825) -> list[InsiderTransaction]:
        """Get insider transactions for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    def get_promoter_buys(self, days: int = 30) -> list[InsiderTransaction]:
        """Get promoter buying transactions."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions "
            "WHERE person_category LIKE '%Promoter%' "
            "AND transaction_type = 'Buy' "
            "AND date >= date('now', ? || ' days') "
            "ORDER BY value DESC",
            (f"-{days}",),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    def upsert_mf_scheme_holdings(self, holdings: list[MFSchemeHolding]) -> int:
        """Insert or replace MF scheme holding records."""
        cursor = self._conn.cursor()
        count = 0
        for h in holdings:
            warnings = _validate_row("mf_scheme_holdings", h.model_dump())
            if warnings:
                _val_logger.warning("mf_scheme_holdings %s/%s/%s: %s", h.amc, h.month, h.stock_name[:20], "; ".join(warnings))
            cursor.execute(
                "INSERT OR REPLACE INTO mf_scheme_holdings "
                "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (h.month, h.amc, h.scheme_name, h.isin, h.stock_name,
                 h.quantity, h.market_value_cr, h.pct_of_nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_stock_holdings(self, search: str) -> list[MFSchemeHolding]:
        """Get MF holdings for a stock by name, ISIN, or NSE symbol."""
        query = (
            "SELECT * FROM mf_scheme_holdings "
            "WHERE (UPPER(stock_name) LIKE ? OR isin = ?) "
            "AND month = (SELECT MAX(month) FROM mf_scheme_holdings) "
            "ORDER BY market_value_cr DESC"
        )
        rows = self._conn.execute(query, (f"%{search}%", search)).fetchall()

        # If empty and looks like an NSE symbol, resolve via index_constituents
        if not rows and search == search.upper() and " " not in search:
            ic = self._conn.execute(
                "SELECT company_name FROM index_constituents WHERE symbol = ? LIMIT 1",
                (search,),
            ).fetchone()
            if ic and ic["company_name"]:
                name = ic["company_name"]
                for suffix in (" Limited", " Ltd.", " Ltd"):
                    if name.endswith(suffix):
                        name = name[: -len(suffix)].strip()
                        break
                rows = self._conn.execute(query, (f"%{name}%", search)).fetchall()

        return [MFSchemeHolding(
            month=r["month"], amc=r["amc"], scheme_name=r["scheme_name"],
            isin=r["isin"], stock_name=r["stock_name"], quantity=r["quantity"],
            market_value_cr=r["market_value_cr"], pct_of_nav=r["pct_of_nav"],
        ) for r in rows]

    def get_mf_holding_changes(
        self, month: str | None = None, change_type: str = "buy", limit: int = 30,
    ) -> list[MFHoldingChange]:
        """Get month-over-month MF holding changes.

        change_type: "buy" for new+increased, "sell" for exits+decreased
        """
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        # Find previous month
        year, mon = int(month[:4]), int(month[5:7])
        if mon == 1:
            prev_month = f"{year - 1}-12"
        else:
            prev_month = f"{year}-{mon - 1:02d}"

        if change_type == "buy":
            # New positions (in curr but not in prev) + increased positions
            rows = self._conn.execute("""
                SELECT c.stock_name, c.isin, c.amc, c.scheme_name,
                    ? as prev_month, ? as curr_month,
                    COALESCE(p.quantity, 0) as prev_qty, c.quantity as curr_qty,
                    c.quantity - COALESCE(p.quantity, 0) as qty_change,
                    COALESCE(p.market_value_cr, 0) as prev_value,
                    c.market_value_cr as curr_value,
                    CASE WHEN p.isin IS NULL THEN 'NEW' ELSE 'INCREASE' END as change_type
                FROM mf_scheme_holdings c
                LEFT JOIN mf_scheme_holdings p ON c.isin = p.isin
                    AND c.amc = p.amc AND c.scheme_name = p.scheme_name
                    AND p.month = ?
                WHERE c.month = ?
                    AND (p.isin IS NULL OR c.quantity > p.quantity)
                ORDER BY c.market_value_cr - COALESCE(p.market_value_cr, 0) DESC
                LIMIT ?
            """, (prev_month, month, prev_month, month, limit)).fetchall()
        else:
            # Exits (in prev but not in curr) + decreased positions
            rows = self._conn.execute("""
                SELECT p.stock_name, p.isin, p.amc, p.scheme_name,
                    ? as prev_month, ? as curr_month,
                    p.quantity as prev_qty, COALESCE(c.quantity, 0) as curr_qty,
                    COALESCE(c.quantity, 0) - p.quantity as qty_change,
                    p.market_value_cr as prev_value,
                    COALESCE(c.market_value_cr, 0) as curr_value,
                    CASE WHEN c.isin IS NULL THEN 'EXIT' ELSE 'DECREASE' END as change_type
                FROM mf_scheme_holdings p
                LEFT JOIN mf_scheme_holdings c ON p.isin = c.isin
                    AND p.amc = c.amc AND p.scheme_name = c.scheme_name
                    AND c.month = ?
                WHERE p.month = ?
                    AND (c.isin IS NULL OR c.quantity < p.quantity)
                ORDER BY p.market_value_cr - COALESCE(c.market_value_cr, 0) DESC
                LIMIT ?
            """, (prev_month, month, month, prev_month, limit)).fetchall()

        return [MFHoldingChange(
            stock_name=r["stock_name"], isin=r["isin"], amc=r["amc"],
            scheme_name=r["scheme_name"], prev_month=r["prev_month"],
            curr_month=r["curr_month"], prev_qty=r["prev_qty"],
            curr_qty=r["curr_qty"], qty_change=r["qty_change"],
            prev_value=r["prev_value"], curr_value=r["curr_value"],
            change_type=r["change_type"],
        ) for r in rows]

    def get_mf_portfolio_summary(self, month: str | None = None) -> list[dict]:
        """Get AMC-level portfolio summary for a month."""
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        rows = self._conn.execute(
            "SELECT amc, COUNT(DISTINCT scheme_name) as num_schemes, "
            "COUNT(DISTINCT isin) as num_stocks, "
            "SUM(market_value_cr) as total_value_cr "
            "FROM mf_scheme_holdings WHERE month = ? "
            "GROUP BY amc ORDER BY total_value_cr DESC",
            (month,),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_shareholder_details(self, symbol: str, data: dict[str, list[dict]]) -> int:
        """Store individual shareholder data from Screener API."""
        count = 0
        for classification, holders in data.items():
            for holder in holders:
                name = holder.get("name", "")
                for quarter, pct in holder.get("values", {}).items():
                    if pct is None:
                        continue
                    try:
                        pct_val = float(pct)
                    except (ValueError, TypeError):
                        continue
                    self._conn.execute(
                        "INSERT INTO shareholder_detail "
                        "(symbol, classification, holder_name, quarter, percentage) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(symbol, classification, holder_name, quarter) "
                        "DO UPDATE SET percentage=excluded.percentage, fetched_at=datetime('now')",
                        (symbol, classification, name, quarter, pct_val),
                    )
                    count += 1
        self._conn.commit()
        return count

    def get_shareholder_details(
        self, symbol: str, classification: str | None = None
    ) -> list[dict]:
        """Get stored shareholder details, optionally filtered by classification."""
        if classification:
            rows = self._conn.execute(
                "SELECT * FROM shareholder_detail "
                "WHERE symbol = ? AND classification = ? "
                "ORDER BY quarter DESC, percentage DESC",
                (symbol, classification),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM shareholder_detail WHERE symbol = ? "
                "ORDER BY classification, quarter DESC, percentage DESC",
                (symbol,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_adr_programs(self, rows: list) -> int:
        """Insert or replace a batch of ``AdrProgram`` records.

        ``rows`` is typed loosely as ``list`` to avoid pulling
        ``adr_models`` into the store module's import surface — but in
        practice every element must expose the ``AdrProgram`` attributes
        (nse_symbol, company_name, us_ticker, program_type, sponsorship,
        depositary, ratio, country). Returns the number of rows touched.
        """
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO adr_programs "
                "(nse_symbol, company_name, us_ticker, program_type, "
                "sponsorship, depositary, ratio, country, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.nse_symbol,
                    r.company_name,
                    r.us_ticker,
                    r.program_type,
                    r.sponsorship,
                    r.depositary,
                    r.ratio,
                    r.country,
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_adr_programs(self, nse_symbol: str | None = None) -> list[dict]:
        """Return DR program rows as plain dicts.

        If ``nse_symbol`` is given, filters to programs that map to that
        NSE listing (case-insensitive). Otherwise returns every program
        ordered by company_name for stable display.
        """
        if nse_symbol:
            sql = (
                "SELECT nse_symbol, company_name, us_ticker, program_type, "
                "sponsorship, depositary, ratio, country, ingested_at "
                "FROM adr_programs WHERE nse_symbol = ? "
                "ORDER BY company_name, us_ticker"
            )
            rows = self._conn.execute(sql, (nse_symbol.upper().strip(),)).fetchall()
        else:
            sql = (
                "SELECT nse_symbol, company_name, us_ticker, program_type, "
                "sponsorship, depositary, ratio, country, ingested_at "
                "FROM adr_programs ORDER BY company_name, us_ticker"
            )
            rows = self._conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
