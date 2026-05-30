"""US market domain (US add-on, Phase 3).

Upsert + get methods for the ALL-NEW ``us_*`` tables. US data lives ONLY here;
India tables gain zero new rows and India read paths are untouched. Methods run
on the FlowStore instance via mixin composition, so ``self._conn`` is the shared
connection. Monetary values are USD millions; per-share / price values are raw
USD; percentages are percent form (25.0 = 25%).

Upserts take a list of plain dicts (keyed by column name) and use
``INSERT ... ON CONFLICT(<unique key>) DO UPDATE`` so re-fetches are idempotent.
Each row is run through ``_validate_row(table, row, market=..., currency='USD')``
and warnings are logged via ``_val_logger`` (never raised).
"""

from __future__ import annotations

from flowtracker.store_domains._shared import _validate_row, _val_logger

# (symbol, market, cik, sector) — small validation universe seeded into
# symbol_registry by FlowStore.seed_us_validation_universe() (manual helper,
# NOT auto-run). Spans NASDAQ + NYSE and several GICS sectors.
US_VALIDATION_UNIVERSE: list[tuple[str, str, str, str]] = [
    ("AAPL", "NASDAQ", "320193", "Technology"),
    ("MSFT", "NASDAQ", "789019", "Technology"),
    ("NVDA", "NASDAQ", "1045810", "Technology"),
    ("JPM", "NYSE", "19617", "Financials"),
    ("XOM", "NYSE", "34088", "Energy"),
    ("UNH", "NYSE", "731766", "Health Care"),
]


def _norm(row: dict) -> dict:
    """Return a copy with symbol upper-cased and market/currency defaulted."""
    r = dict(row)
    if r.get("symbol"):
        r["symbol"] = str(r["symbol"]).upper()
    r.setdefault("market", "NASDAQ")
    r.setdefault("currency", "USD")
    return r


class UsMarketMixin:
    """Upsert + get for us_* tables (daily prices, financials, valuation,
    consensus, insider, institutional holdings)."""

    def _us_upsert(
        self,
        table: str,
        rows: list[dict],
        columns: tuple[str, ...],
        conflict_cols: tuple[str, ...],
    ) -> int:
        """Generic batch upsert helper for the us_* tables.

        ``columns`` is the full insert column list; ``conflict_cols`` is the
        UNIQUE key. Non-conflict columns are refreshed via DO UPDATE. Each row
        is validated (warnings logged, never raised).
        """
        if not rows:
            return 0
        update_cols = [c for c in columns if c not in conflict_cols]
        col_sql = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        set_sql = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        set_sql = f"{set_sql}, fetched_at=datetime('now')" if set_sql else "fetched_at=datetime('now')"
        sql = (
            f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(conflict_cols)}) DO UPDATE SET {set_sql}"
        )
        cur = self._conn.cursor()
        count = 0
        for raw in rows:
            r = _norm(raw)
            warnings = _validate_row(
                table, r, market=r["market"], currency=r["currency"],
            )
            if warnings:
                _val_logger.warning(
                    "%s %s: %s", table, r.get("symbol"), "; ".join(warnings),
                )
            cur.execute(sql, tuple(r.get(c) for c in columns))
            count += 1
        self._conn.commit()
        return count

    def _us_get(self, table: str, symbol: str, market: str, order_by: str) -> list[dict]:
        rows = self._conn.execute(
            f"SELECT * FROM {table} WHERE symbol = ? AND market = ? ORDER BY {order_by}",
            (symbol.upper(), market),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- us_daily_prices --

    _US_DAILY_PRICES_COLS = (
        "symbol", "market", "date", "open", "high", "low", "close",
        "volume", "adj_close",
    )

    def upsert_us_daily_prices(self, rows: list[dict]) -> int:
        """Batch upsert daily OHLCV. Conflict key: (symbol, market, date)."""
        return self._us_upsert(
            "us_daily_prices", rows, self._US_DAILY_PRICES_COLS,
            ("symbol", "market", "date"),
        )

    def get_us_daily_prices(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Daily prices for a symbol, most recent first."""
        return self._us_get("us_daily_prices", symbol, market, "date DESC")

    # -- us_annual_financials --

    _US_ANNUAL_COLS = (
        "symbol", "market", "currency", "fiscal_year", "revenue", "net_income",
        "total_assets", "total_equity", "total_debt", "total_cash", "eps",
        "operating_cash_flow", "free_cash_flow", "shares_outstanding",
        # Phase 3.5b wide columns.
        "fiscal_year_end", "equity_capital", "reserves", "borrowings",
        "interest", "profit_before_tax", "tax", "operating_profit",
        "depreciation", "num_shares", "net_block", "cwip", "cash_and_bank",
        "receivables", "inventory", "other_liabilities", "cfi", "cff",
        "rnd_expense", "stock_based_comp", "sga",
    )

    def upsert_us_annual_financials(self, rows: list[dict]) -> int:
        """Batch upsert annual financials. Conflict: (symbol, market, fiscal_year)."""
        return self._us_upsert(
            "us_annual_financials", rows, self._US_ANNUAL_COLS,
            ("symbol", "market", "fiscal_year"),
        )

    def get_us_annual_financials(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Annual financials for a symbol, most recent fiscal_year first."""
        return self._us_get("us_annual_financials", symbol, market, "fiscal_year DESC")

    # -- us_quarterly_financials --

    _US_QUARTERLY_COLS = (
        "symbol", "market", "currency", "quarter_end", "fiscal_year",
        "fiscal_period", "revenue", "net_income", "eps",
    )

    def upsert_us_quarterly_financials(self, rows: list[dict]) -> int:
        """Batch upsert quarterly financials. Conflict: (symbol, market, quarter_end)."""
        return self._us_upsert(
            "us_quarterly_financials", rows, self._US_QUARTERLY_COLS,
            ("symbol", "market", "quarter_end"),
        )

    def get_us_quarterly_financials(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Quarterly financials for a symbol, most recent quarter_end first."""
        return self._us_get("us_quarterly_financials", symbol, market, "quarter_end DESC")

    # -- us_valuation_snapshot --

    _US_VALUATION_COLS = (
        "symbol", "market", "currency", "date", "price", "market_cap",
        "enterprise_value", "pe_trailing", "pe_forward", "pb", "dividend_yield",
        "beta", "total_cash", "total_debt", "free_cash_flow", "operating_margin",
        "net_margin", "roe",
    )

    def upsert_us_valuation_snapshot(self, rows: list[dict]) -> int:
        """Batch upsert valuation snapshots. Conflict: (symbol, market, date)."""
        return self._us_upsert(
            "us_valuation_snapshot", rows, self._US_VALUATION_COLS,
            ("symbol", "market", "date"),
        )

    def get_us_valuation_snapshot(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Valuation snapshots for a symbol, most recent date first."""
        return self._us_get("us_valuation_snapshot", symbol, market, "date DESC")

    # -- us_consensus_estimates --

    _US_CONSENSUS_COLS = (
        "symbol", "market", "currency", "date", "target_mean", "target_median",
        "target_high", "target_low",
        "num_analysts", "recommendation", "forward_pe", "forward_eps",
        "eps_current_year", "eps_next_year", "earnings_growth", "current_price",
    )

    def upsert_us_consensus_estimates(self, rows: list[dict]) -> int:
        """Batch upsert consensus estimates. Conflict: (symbol, market, date)."""
        return self._us_upsert(
            "us_consensus_estimates", rows, self._US_CONSENSUS_COLS,
            ("symbol", "market", "date"),
        )

    def get_us_consensus_estimates(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Consensus estimates for a symbol, most recent date first."""
        return self._us_get("us_consensus_estimates", symbol, market, "date DESC")

    # -- us_insider_transactions --

    _US_INSIDER_COLS = (
        "symbol", "market", "currency", "filing_date", "transaction_date",
        "owner_name", "owner_title", "transaction_code", "shares",
        "price_per_share", "value", "shares_owned_after", "is_director",
        "is_officer",
    )

    def upsert_us_insider_transactions(self, rows: list[dict]) -> int:
        """Batch upsert insider (Form 4) transactions.

        Conflict: (symbol, market, transaction_date, owner_name,
        transaction_code, shares).
        """
        return self._us_upsert(
            "us_insider_transactions", rows, self._US_INSIDER_COLS,
            ("symbol", "market", "transaction_date", "owner_name",
             "transaction_code", "shares"),
        )

    def get_us_insider_transactions(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Insider transactions for a symbol, most recent transaction_date first."""
        return self._us_get(
            "us_insider_transactions", symbol, market, "transaction_date DESC",
        )

    # -- us_institutional_holdings --

    _US_INSTITUTIONAL_COLS = (
        "symbol", "market", "currency", "cusip", "manager_name", "manager_cik",
        "quarter_end", "shares", "value_usd", "investment_discretion",
        "put_call",
    )

    def upsert_us_institutional_holdings(self, rows: list[dict]) -> int:
        """Batch upsert 13F institutional holdings.

        Conflict: (symbol, market, manager_cik, quarter_end, put_call).
        ``put_call`` defaults to '' (empty-string sentinel) for plain long
        positions so SQLite uniqueness constrains duplicates.
        """
        normed = []
        for r in rows:
            r2 = dict(r)
            r2.setdefault("put_call", "")
            normed.append(r2)
        return self._us_upsert(
            "us_institutional_holdings", normed, self._US_INSTITUTIONAL_COLS,
            ("symbol", "market", "manager_cik", "quarter_end", "put_call"),
        )

    def get_us_institutional_holdings(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Institutional holdings for a symbol, largest value first."""
        return self._us_get(
            "us_institutional_holdings", symbol, market, "value_usd DESC",
        )

    # -- us_short_interest --

    _US_SHORT_INTEREST_COLS = (
        "symbol", "market", "currency", "settlement_date", "short_interest",
        "avg_daily_volume", "days_to_cover",
    )

    def upsert_us_short_interest(self, rows: list[dict]) -> int:
        """Batch upsert bi-monthly short-interest rows (Nasdaq/FINRA).

        Conflict: (symbol, market, settlement_date) — one position per
        settlement date per listing.
        """
        return self._us_upsert(
            "us_short_interest", rows, self._US_SHORT_INTEREST_COLS,
            ("symbol", "market", "settlement_date"),
        )

    def get_us_short_interest(self, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Short-interest history for a symbol, most recent settlement first."""
        return self._us_get(
            "us_short_interest", symbol, market, "settlement_date DESC",
        )

    # -- us_macro_daily (market-wide; symbol-less) --

    _US_MACRO_DAILY_COLS = (
        "date", "vix", "dxy", "ust_3m", "ust_5y", "ust_10y", "ust_30y",
        "wti_crude", "brent_crude", "gold",
    )

    def upsert_us_macro_daily(self, rows: list[dict]) -> int:
        """Insert or replace US daily macro snapshots. Conflict key: (date).

        Market-wide table (no symbol), so this uses a plain INSERT OR REPLACE
        keyed on the UNIQUE(date) constraint, mirroring the India
        ``upsert_macro_snapshots`` pattern rather than the symbol-scoped
        ``_us_upsert`` helper. Accepts plain dicts keyed by column name (or
        ``USMacroSnapshot`` instances via ``.model_dump()`` upstream); missing
        fields persist as NULL.
        """
        if not rows:
            return 0
        col_sql = ", ".join(self._US_MACRO_DAILY_COLS)
        placeholders = ", ".join(["?"] * len(self._US_MACRO_DAILY_COLS))
        sql = (
            f"INSERT OR REPLACE INTO us_macro_daily ({col_sql}) "
            f"VALUES ({placeholders})"
        )
        cur = self._conn.cursor()
        count = 0
        for row in rows:
            r = dict(row)
            cur.execute(sql, tuple(r.get(c) for c in self._US_MACRO_DAILY_COLS))
            count += cur.rowcount
        self._conn.commit()
        return count

    def get_us_macro_daily(self, days: int = 7) -> list[dict]:
        """Most recent ``days`` US macro snapshot rows, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM us_macro_daily ORDER BY date DESC LIMIT ?",
            (days,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- us_macro_monthly (market-wide; symbol-less) --
    #
    # Monthly CPI / Industrial Production from FRED. Mirrors the India
    # ``cpi_monthly`` / ``iip_monthly`` store surface but keyed by
    # (series, period) so both series share one table. India CPI/IIP tables
    # and read paths are untouched.

    def upsert_us_macro_monthly(self, rows: list[dict]) -> int:
        """Insert-or-replace a batch of US monthly macro rows.

        Each row is a plain dict exposing ``series`` ('cpi'|'iip'),
        ``period`` ('YYYY-MM-01'), ``index_value``, ``yoy_pct``, ``source``,
        ``source_url``. Returns the count of rows touched. Idempotent on the
        ``UNIQUE(series, period)`` key.
        """
        if not rows:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO us_macro_monthly "
                "(period, series, index_value, yoy_pct, source, source_url, "
                "fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.get("period"),
                    r.get("series"),
                    r.get("index_value"),
                    r.get("yoy_pct"),
                    r.get("source", "FRED"),
                    r.get("source_url"),
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_us_macro_monthly_latest(self, series: str) -> dict | None:
        """Return the most-recent row for ``series`` ('cpi'|'iip') as a dict."""
        row = self._conn.execute(
            "SELECT period, series, index_value, yoy_pct, source, source_url "
            "FROM us_macro_monthly WHERE series = ? "
            "ORDER BY period DESC LIMIT 1",
            (series,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_us_macro_monthly_trend(self, series: str, months: int) -> list[dict]:
        """Return the last ``months`` rows for ``series`` as dicts, newest first."""
        if months < 1:
            return []
        rows = self._conn.execute(
            "SELECT period, series, index_value, yoy_pct, source, source_url, "
            "fetched_at "
            "FROM us_macro_monthly WHERE series = ? "
            "ORDER BY period DESC LIMIT ?",
            (series, int(months)),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- us_company_snapshot (denormalized peers/benchmarks source of truth) --

    _US_COMPANY_SNAPSHOT_COLS = (
        "symbol", "market", "currency", "name", "industry", "cmp", "market_cap",
        "pe_trailing", "pe_forward", "pb", "ev_ebitda", "peg", "div_yield",
        "operating_margin", "net_margin", "roe", "roa", "roce", "roic",
        "fcf_yield", "revenue_growth", "earnings_growth", "beta",
        "debt_to_equity", "current_ratio", "high_52w", "low_52w",
    )

    def upsert_us_company_snapshot(
        self, symbol: str, market: str, fields: dict,
    ) -> int:
        """Insert or update the US company snapshot for (symbol, market).

        COALESCE-safe: any column omitted from ``fields`` (or passed as None)
        preserves the existing stored value rather than nulling it, so partial
        re-builds never clobber a previously-populated metric. ``symbol`` is
        upper-cased; ``currency`` defaults to 'USD'.
        """
        sym = symbol.upper()
        currency = fields.get("currency") or "USD"
        # Value columns are everything except the (symbol, market) PK.
        value_cols = [
            c for c in self._US_COMPANY_SNAPSHOT_COLS if c not in ("symbol", "market")
        ]
        col_sql = ", ".join(self._US_COMPANY_SNAPSHOT_COLS)
        placeholders = ", ".join(["?"] * len(self._US_COMPANY_SNAPSHOT_COLS))
        # COALESCE(excluded.col, us_company_snapshot.col) keeps the old value
        # when the new one is NULL.
        set_sql = ", ".join(
            f"{c}=COALESCE(excluded.{c}, us_company_snapshot.{c})" for c in value_cols
        )
        sql = (
            f"INSERT INTO us_company_snapshot ({col_sql}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(symbol, market) DO UPDATE SET {set_sql}, "
            f"updated_at=datetime('now')"
        )
        row = {**fields, "symbol": sym, "market": market, "currency": currency}
        self._conn.execute(
            sql, tuple(row.get(c) for c in self._US_COMPANY_SNAPSHOT_COLS)
        )
        self._conn.commit()
        return 1

    def get_us_company_snapshot(
        self, symbol: str, market: str = "NASDAQ",
    ) -> dict | None:
        """Return the US company snapshot for (symbol, market), or None."""
        row = self._conn.execute(
            "SELECT * FROM us_company_snapshot WHERE symbol = ? AND market = ?",
            (symbol.upper(), market),
        ).fetchone()
        return dict(row) if row else None

    def get_us_company_snapshots(
        self, symbols: list[str], market: str = "NASDAQ",
    ) -> list[dict]:
        """Return US snapshots for the given symbols in one market. Only existing rows."""
        if not symbols:
            return []
        placeholders = ",".join("?" * len(symbols))
        rows = self._conn.execute(
            f"SELECT * FROM us_company_snapshot "  # noqa: S608
            f"WHERE market = ? AND symbol IN ({placeholders}) ORDER BY symbol",
            [market, *[s.upper() for s in symbols]],
        ).fetchall()
        return [dict(r) for r in rows]

    # -- us_market_breadth_daily (market-wide; symbol-less, index-keyed) --
    #
    # Mirrors the India `market_breadth_daily` surface but over the US universe
    # in `us_daily_prices`, grouped by GICS sector. `index_name` is "US 500"
    # (whole US universe) or "US <sector_key>". Computed by us_breadth_compute.py.
    # India breadth tables and read paths are untouched.

    def upsert_us_breadth(self, snapshots: list) -> int:
        """Insert or replace US market-breadth snapshots.

        Accepts a list of ``BreadthSnapshot`` instances (the same model India
        breadth uses). UNIQUE(date, index_name) — re-running for the same date
        overwrites (idempotent recompute).
        """
        cursor = self._conn.cursor()
        count = 0
        for s in snapshots:
            cursor.execute(
                "INSERT OR REPLACE INTO us_market_breadth_daily "
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

    def get_us_breadth_latest(self) -> list:
        """Return all index_name rows for the most recent US breadth date.

        Returns a list of ``BreadthSnapshot`` ordered by index_name (empty list
        when no US breadth has been computed yet).
        """
        from flowtracker.store import _row_to_breadth

        row = self._conn.execute(
            "SELECT MAX(date) AS d FROM us_market_breadth_daily"
        ).fetchone()
        if not row or row["d"] is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM us_market_breadth_daily WHERE date = ? "
            "ORDER BY index_name",
            (row["d"],),
        ).fetchall()
        return [_row_to_breadth(r) for r in rows]

    def get_us_breadth_history(self, index_name: str, days: int = 30) -> list:
        """Last ``days`` US breadth snapshots for one index_name, newest first."""
        from flowtracker.store import _row_to_breadth

        rows = self._conn.execute(
            "SELECT * FROM us_market_breadth_daily WHERE index_name = ? "
            "ORDER BY date DESC LIMIT ?",
            (index_name, days),
        ).fetchall()
        return [_row_to_breadth(r) for r in rows]
