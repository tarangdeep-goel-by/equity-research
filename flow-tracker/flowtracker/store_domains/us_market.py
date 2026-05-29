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
