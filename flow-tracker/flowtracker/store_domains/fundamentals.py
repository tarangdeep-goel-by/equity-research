"""Fundamentals domain (split from FlowStore, refactor P1.4).

Quarterly results, annual financials, standalone financials, quarterly balance
sheet + cash flow, financial schedules, Screener ratios, and data-quality
flags. Methods moved verbatim from store.py; they run on the FlowStore instance
via mixin composition, so ``self._conn`` is the shared connection. The
validation helpers live in store_domains/_shared.py.
"""

from __future__ import annotations

from flowtracker.fund_models import QuarterlyResult, ScreenerRatios
from flowtracker.store_domains._shared import _validate_row, _val_logger


class FundamentalsMixin:
    """Quarterly/annual/standalone financials, BS/CF, schedules, ratios, DQ flags."""

    def upsert_quarterly_results(self, results: list[QuarterlyResult]) -> int:
        """Insert or replace quarterly results. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in results:
            existing = self._conn.execute(
                "SELECT revenue FROM quarterly_results WHERE symbol = ? AND quarter_end = ?",
                (r.symbol, r.quarter_end),
            ).fetchone()
            warnings = _validate_row(
                "quarterly_results", r.model_dump(),
                market=getattr(r, "market", "NSE"), currency=getattr(r, "currency", "INR"),
            )
            if warnings:
                _val_logger.warning("quarterly_results %s/%s: %s", r.symbol, r.quarter_end, "; ".join(warnings))
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("quarterly_results", r.symbol, r.quarter_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO quarterly_results "
                "(symbol, quarter_end, revenue, gross_profit, operating_income, net_income, "
                "ebitda, eps, eps_diluted, operating_margin, net_margin, "
                "expenses, other_income, depreciation, interest, profit_before_tax, tax_pct, "
                "net_premium_earned) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.revenue, r.gross_profit, r.operating_income,
                 r.net_income, r.ebitda, r.eps, r.eps_diluted, r.operating_margin, r.net_margin,
                 r.expenses, r.other_income, r.depreciation, r.interest, r.profit_before_tax, r.tax_pct,
                 r.net_premium_earned),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_quarterly_results(self, symbol: str, limit: int = 12) -> list[QuarterlyResult]:
        """Get stored quarterly results, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_results WHERE symbol = ? "
            "ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [QuarterlyResult(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            revenue=r["revenue"], gross_profit=r["gross_profit"],
            operating_income=r["operating_income"], net_income=r["net_income"],
            ebitda=r["ebitda"], eps=r["eps"], eps_diluted=r["eps_diluted"],
            operating_margin=r["operating_margin"], net_margin=r["net_margin"],
            expenses=r["expenses"], other_income=r["other_income"],
            depreciation=r["depreciation"], interest=r["interest"],
            profit_before_tax=r["profit_before_tax"], tax_pct=r["tax_pct"],
            net_premium_earned=r["net_premium_earned"],
        ) for r in rows]

    def upsert_annual_financials(self, records: list) -> int:
        """Insert or replace annual financials. Audit-logged."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            existing = self._conn.execute(
                "SELECT revenue FROM annual_financials WHERE symbol = ? AND fiscal_year_end = ?",
                (r.symbol, r.fiscal_year_end),
            ).fetchone()
            warnings = _validate_row(
                "annual_financials", r.model_dump(),
                market=getattr(r, "market", "NSE"), currency=getattr(r, "currency", "INR"),
            )
            if warnings:
                _val_logger.warning("annual_financials %s/%s: %s", r.symbol, r.fiscal_year_end, "; ".join(warnings))
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("annual_financials", r.symbol, r.fiscal_year_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO annual_financials "
                "(symbol, fiscal_year_end, revenue, employee_cost, other_income, depreciation, "
                "interest, profit_before_tax, tax, net_income, eps, dividend_amount, "
                "equity_capital, reserves, borrowings, other_liabilities, total_assets, "
                "net_block, cwip, investments, other_assets, receivables, inventory, "
                "cash_and_bank, num_shares, cfo, cfi, cff, net_cash_flow, price, "
                "raw_material_cost, power_and_fuel, other_mfr_exp, selling_and_admin, "
                "other_expenses_detail, total_expenses, operating_profit, net_premium_earned) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.fiscal_year_end, r.revenue, r.employee_cost, r.other_income,
                 r.depreciation, r.interest, r.profit_before_tax, r.tax, r.net_income,
                 r.eps, r.dividend_amount, r.equity_capital, r.reserves, r.borrowings,
                 r.other_liabilities, r.total_assets, r.net_block, r.cwip, r.investments,
                 r.other_assets, r.receivables, r.inventory, r.cash_and_bank, r.num_shares,
                 r.cfo, r.cfi, r.cff, r.net_cash_flow, r.price,
                 r.raw_material_cost, r.power_and_fuel, r.other_mfr_exp, r.selling_and_admin,
                 r.other_expenses_detail, r.total_expenses, r.operating_profit,
                 r.net_premium_earned),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_annual_financials(self, symbol: str, limit: int = 10) -> list:
        """Get stored annual financials, most recent first."""
        from flowtracker.fund_models import AnnualFinancials
        rows = self._conn.execute(
            "SELECT * FROM annual_financials WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [AnnualFinancials(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            revenue=r["revenue"], employee_cost=r["employee_cost"],
            other_income=r["other_income"], depreciation=r["depreciation"],
            interest=r["interest"], profit_before_tax=r["profit_before_tax"],
            tax=r["tax"], net_income=r["net_income"], eps=r["eps"],
            dividend_amount=r["dividend_amount"], equity_capital=r["equity_capital"],
            reserves=r["reserves"], borrowings=r["borrowings"],
            other_liabilities=r["other_liabilities"], total_assets=r["total_assets"],
            net_block=r["net_block"], cwip=r["cwip"], investments=r["investments"],
            other_assets=r["other_assets"], receivables=r["receivables"],
            inventory=r["inventory"], cash_and_bank=r["cash_and_bank"],
            num_shares=r["num_shares"], cfo=r["cfo"], cfi=r["cfi"],
            cff=r["cff"], net_cash_flow=r["net_cash_flow"], price=r["price"],
            raw_material_cost=r["raw_material_cost"], power_and_fuel=r["power_and_fuel"],
            other_mfr_exp=r["other_mfr_exp"], selling_and_admin=r["selling_and_admin"],
            other_expenses_detail=r["other_expenses_detail"], total_expenses=r["total_expenses"],
            operating_profit=r["operating_profit"],
            net_premium_earned=r["net_premium_earned"],
        ) for r in rows]

    # -- Data Quality Flags (Screener reclassification discontinuities) --

    def upsert_data_quality_flags(self, flags: list) -> int:
        """Insert/replace flags. Idempotent on (symbol, curr_fy, line).

        flags: iterable of flowtracker.data_quality.Flag dataclasses.
        Returns row count written.
        """
        cursor = self._conn.cursor()
        count = 0
        for f in flags:
            cursor.execute(
                "INSERT OR REPLACE INTO data_quality_flags "
                "(symbol, prior_fy, curr_fy, line, prior_val, curr_val, "
                "jump_pct, rev_change_pct, flag_type, severity) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f.symbol.upper(), f.prior_fy, f.curr_fy, f.line,
                    f.prior_val, f.curr_val, f.jump_pct, f.revenue_change_pct,
                    f.flag_type, f.severity,
                ),
            )
            count += 1
        self._conn.commit()
        return count

    def get_data_quality_flags(
        self, symbol: str, min_severity: str | None = None
    ) -> list[dict]:
        """Get flags for a symbol, ordered by curr_fy DESC, severity HIGH→LOW.

        min_severity: if set, returns only flags at or above this tier
                      ("LOW" returns all, "HIGH" only HIGH).
        """
        sev_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        sql = (
            "SELECT symbol, prior_fy, curr_fy, line, prior_val, curr_val, "
            "jump_pct, rev_change_pct, flag_type, severity "
            "FROM data_quality_flags WHERE symbol = ?"
        )
        params: tuple = (symbol.upper(),)
        if min_severity:
            allowed = [s for s, r in sev_rank.items() if r >= sev_rank[min_severity]]
            sql += f" AND severity IN ({','.join('?' * len(allowed))})"
            params = (*params, *allowed)
        sql += " ORDER BY curr_fy DESC, severity"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def clear_data_quality_flags(self, symbol: str | None = None) -> int:
        """Delete flags. If symbol is None, deletes all (for full re-backfill)."""
        cursor = self._conn.cursor()
        if symbol:
            cursor.execute(
                "DELETE FROM data_quality_flags WHERE symbol = ?",
                (symbol.upper(),),
            )
        else:
            cursor.execute("DELETE FROM data_quality_flags")
        self._conn.commit()
        return cursor.rowcount

    # -- Standalone Financials (for SOTP: consolidated - standalone = subsidiary contribution) --

    def upsert_standalone_financials(self, records: list[dict]) -> int:
        """Insert or replace standalone financials summary."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO standalone_financials "
                "(symbol, fiscal_year_end, revenue, net_income, total_assets, equity_capital, reserves) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (r["symbol"], r["fiscal_year_end"], r.get("revenue"), r.get("net_income"),
                 r.get("total_assets"), r.get("equity_capital"), r.get("reserves")),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_standalone_financials(self, symbol: str, limit: int = 10) -> list[dict]:
        """Get stored standalone financials summary, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM standalone_financials WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Screener Ratios --

    def upsert_screener_ratios(self, ratios: list[ScreenerRatios]) -> int:
        """Insert or replace screener ratios."""
        cursor = self._conn.cursor()
        count = 0
        for r in ratios:
            cursor.execute(
                "INSERT OR REPLACE INTO screener_ratios "
                "(symbol, fiscal_year_end, debtor_days, inventory_days, days_payable, "
                "cash_conversion_cycle, working_capital_days, roce_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.fiscal_year_end, r.debtor_days, r.inventory_days,
                 r.days_payable, r.cash_conversion_cycle, r.working_capital_days, r.roce_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_screener_ratios(self, symbol: str, limit: int = 10) -> list[ScreenerRatios]:
        """Get stored screener ratios, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM screener_ratios WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [ScreenerRatios(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            debtor_days=r["debtor_days"], inventory_days=r["inventory_days"],
            days_payable=r["days_payable"], cash_conversion_cycle=r["cash_conversion_cycle"],
            working_capital_days=r["working_capital_days"], roce_pct=r["roce_pct"],
        ) for r in rows]

    def upsert_schedules(self, symbol: str, section: str, parent: str, data: dict) -> int:
        """Store schedule (sub-item breakdown) data."""
        count = 0
        for sub_item, periods in data.items():
            if not isinstance(periods, dict):
                continue
            for period, value in periods.items():
                if value is None:
                    continue
                try:
                    val = float(str(value).replace(",", "").replace("%", ""))
                except (ValueError, TypeError):
                    continue
                self._conn.execute(
                    "INSERT INTO financial_schedules "
                    "(symbol, section, parent_item, sub_item, period, value) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol, section, parent_item, sub_item, period) "
                    "DO UPDATE SET value=excluded.value, fetched_at=datetime('now')",
                    (symbol, section, parent, sub_item, period, val),
                )
                count += 1
        self._conn.commit()
        return count

    def get_schedules(self, symbol: str, section: str | None = None) -> list[dict]:
        """Get stored schedule data, optionally filtered by section."""
        if section:
            rows = self._conn.execute(
                "SELECT * FROM financial_schedules "
                "WHERE symbol = ? AND section = ? "
                "ORDER BY parent_item, sub_item, period",
                (symbol, section),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM financial_schedules WHERE symbol = ? "
                "ORDER BY section, parent_item, sub_item, period",
                (symbol,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_quarterly_balance_sheet(self, symbol: str, rows: list[dict]) -> int:
        """Upsert quarterly balance sheet data."""
        count = 0
        for row in rows:
            warnings = _validate_row(
                "quarterly_balance_sheet", row,
                market=row.get("market", "NSE"), currency=row.get("currency", "INR"),
            )
            if warnings:
                _val_logger.warning("quarterly_balance_sheet %s/%s: %s", symbol, row.get("quarter_end"), "; ".join(warnings))
            self._conn.execute(
                """INSERT INTO quarterly_balance_sheet
                   (symbol, quarter_end, total_assets, total_debt, long_term_debt,
                    stockholders_equity, cash_and_equivalents, net_debt, investments,
                    net_ppe, shares_outstanding, total_liabilities, minority_interest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, quarter_end) DO UPDATE SET
                    total_assets=excluded.total_assets, total_debt=excluded.total_debt,
                    long_term_debt=excluded.long_term_debt, stockholders_equity=excluded.stockholders_equity,
                    cash_and_equivalents=excluded.cash_and_equivalents, net_debt=excluded.net_debt,
                    investments=excluded.investments, net_ppe=excluded.net_ppe,
                    shares_outstanding=excluded.shares_outstanding, total_liabilities=excluded.total_liabilities,
                    minority_interest=excluded.minority_interest, fetched_at=datetime('now')""",
                (symbol.upper(), row["quarter_end"],
                 row.get("total_assets"), row.get("total_debt"), row.get("long_term_debt"),
                 row.get("stockholders_equity"), row.get("cash_and_equivalents"),
                 row.get("net_debt"), row.get("investments"), row.get("net_ppe"),
                 row.get("shares_outstanding"), row.get("total_liabilities"),
                 row.get("minority_interest")),
            )
            count += 1
        self._conn.commit()
        return count

    def upsert_quarterly_cash_flow(self, symbol: str, rows: list[dict]) -> int:
        """Upsert quarterly cash flow data.

        Each row may carry an explicit ``source`` field — used to mark rows
        sourced from Screener (fiscal-year cadence) vs yfinance (true
        quarterly). Defaults to ``'yfinance'`` for backward compatibility
        with callers that don't pass it.
        """
        count = 0
        for row in rows:
            warnings = _validate_row(
                "quarterly_cash_flow", row,
                market=row.get("market", "NSE"), currency=row.get("currency", "INR"),
            )
            if warnings:
                _val_logger.warning("quarterly_cash_flow %s/%s: %s", symbol, row.get("quarter_end"), "; ".join(warnings))
            self._conn.execute(
                """INSERT INTO quarterly_cash_flow
                   (symbol, quarter_end, operating_cash_flow, free_cash_flow, capital_expenditure,
                    investing_cash_flow, financing_cash_flow, change_in_working_capital,
                    depreciation, dividends_paid, net_income, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, quarter_end) DO UPDATE SET
                    operating_cash_flow=excluded.operating_cash_flow, free_cash_flow=excluded.free_cash_flow,
                    capital_expenditure=excluded.capital_expenditure, investing_cash_flow=excluded.investing_cash_flow,
                    financing_cash_flow=excluded.financing_cash_flow, change_in_working_capital=excluded.change_in_working_capital,
                    depreciation=excluded.depreciation, dividends_paid=excluded.dividends_paid,
                    net_income=excluded.net_income, source=excluded.source, fetched_at=datetime('now')""",
                (symbol.upper(), row["quarter_end"],
                 row.get("operating_cash_flow"), row.get("free_cash_flow"),
                 row.get("capital_expenditure"), row.get("investing_cash_flow"),
                 row.get("financing_cash_flow"), row.get("change_in_working_capital"),
                 row.get("depreciation"), row.get("dividends_paid"), row.get("net_income"),
                 row.get("source", "yfinance")),
            )
            count += 1
        self._conn.commit()
        return count

    def get_quarterly_balance_sheet(self, symbol: str, limit: int = 8) -> list[dict]:
        """Get quarterly balance sheet data, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_balance_sheet WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_quarterly_cash_flow(self, symbol: str, limit: int = 8) -> list[dict]:
        """Get quarterly cash flow data, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_cash_flow WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows]
