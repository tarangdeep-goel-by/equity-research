"""F&O derivatives domain (split from FlowStore, refactor P1.4).

Per-contract EOD rows, participant-wise OI, the F&O-eligible universe, and the
derived analytics (PCR, basis, OI percentile, FII positioning). Methods moved
verbatim from store.py; they run on the FlowStore instance via mixin
composition, so ``self._conn`` is the shared connection.
"""

from __future__ import annotations

from datetime import date

from flowtracker.fno_models import FnoContract, FnoParticipantOi, FnoUniverse


class DerivativesMixin:
    """F&O contracts, participant OI, universe, and derived analytics."""

    def upsert_fno_contracts(self, contracts: list[FnoContract]) -> int:
        """Insert or replace per-contract EOD F&O rows.

        Maps `strike is None` -> -1 and `option_type is None` -> '' because
        SQLite PRIMARY KEY columns cannot be NULL. No audit_log writes — OI
        moves daily and would flood the log. Returns count of rows touched.
        """
        cursor = self._conn.cursor()
        count = 0
        for c in contracts:
            strike = c.strike if c.strike is not None else -1
            option_type = c.option_type if c.option_type is not None else ""
            cursor.execute(
                "INSERT OR REPLACE INTO fno_contracts ("
                "trade_date, symbol, instrument, expiry_date, strike, option_type, "
                "open, high, low, close, settle_price, "
                "contracts_traded, turnover_cr, open_interest, change_in_oi, "
                "implied_volatility"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    c.trade_date.isoformat(), c.symbol, c.instrument,
                    c.expiry_date.isoformat(), strike, option_type,
                    c.open, c.high, c.low, c.close, c.settle_price,
                    c.contracts_traded, c.turnover_cr, c.open_interest,
                    c.change_in_oi, c.implied_volatility,
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fno_participant_oi(self, rows: list[FnoParticipantOi]) -> int:
        """Insert or replace participant-wise OI rows. No audit_log writes."""
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO fno_participant_oi ("
                "trade_date, participant, instrument_category, "
                "long_oi, short_oi, long_turnover_cr, short_turnover_cr"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    r.trade_date.isoformat(), r.participant, r.instrument_category,
                    r.long_oi, r.short_oi, r.long_turnover_cr, r.short_turnover_cr,
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_fno_universe(self, entries: list[FnoUniverse]) -> int:
        """Insert or replace F&O-eligible symbol rows.

        Preserves existing `eligible_since` on update; only overwrites
        `last_verified`. Used for quarterly refresh so we don't lose the
        original eligibility date.
        """
        cursor = self._conn.cursor()
        count = 0
        for e in entries:
            existing = self._conn.execute(
                "SELECT eligible_since FROM fno_universe WHERE symbol = ?",
                (e.symbol,),
            ).fetchone()
            eligible_since = (
                existing["eligible_since"] if existing
                else e.eligible_since.isoformat()
            )
            cursor.execute(
                "INSERT OR REPLACE INTO fno_universe ("
                "symbol, eligible_since, last_verified"
                ") VALUES (?, ?, ?)",
                (e.symbol, eligible_since, e.last_verified.isoformat()),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_fno_oi_history(self, symbol: str, days: int = 90) -> list[dict]:
        """Return daily OI series for the symbol's front-month stock future.

        For each trade_date in the last `days` days, picks the FUTSTK row with
        the nearest non-expired expiry (MIN(expiry_date) where expiry_date >=
        trade_date). Ordered oldest-first.
        """
        rows = self._conn.execute(
            "SELECT f.trade_date, f.expiry_date, f.close, f.settle_price, "
            "f.open_interest, f.change_in_oi, f.contracts_traded, f.turnover_cr "
            "FROM fno_contracts f "
            "INNER JOIN ("
            "  SELECT trade_date, MIN(expiry_date) AS front_expiry "
            "  FROM fno_contracts "
            "  WHERE symbol = ? AND instrument = 'FUTSTK' "
            "    AND expiry_date >= trade_date "
            "    AND trade_date >= date('now', ? || ' days') "
            "  GROUP BY trade_date"
            ") m ON f.trade_date = m.trade_date AND f.expiry_date = m.front_expiry "
            "WHERE f.symbol = ? AND f.instrument = 'FUTSTK' "
            "ORDER BY f.trade_date ASC",
            (symbol.upper(), f"-{days}", symbol.upper()),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_fno_contracts_for_date(self, symbol: str, trade_date: date) -> list[dict]:
        """Return all F&O contracts for a symbol on a given trade_date.

        Normalizes sentinel values in output: strike == -1 -> None,
        option_type == '' -> None.
        """
        rows = self._conn.execute(
            "SELECT * FROM fno_contracts WHERE symbol = ? AND trade_date = ?",
            (symbol.upper(), trade_date.isoformat()),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("strike") == -1:
                d["strike"] = None
            if d.get("option_type") == "":
                d["option_type"] = None
            out.append(d)
        return out

    def get_pcr(self, symbol: str, as_of: date) -> dict | None:
        """Return put/call ratio (PCR_OI) for a symbol on a given date.

        Aggregates CE vs PE open_interest across all option strikes and
        expiries for the symbol on that date. Returns None if no option
        rows found or total_ce_oi is zero.
        """
        rows = self._conn.execute(
            "SELECT option_type, SUM(open_interest) AS total_oi "
            "FROM fno_contracts "
            "WHERE symbol = ? AND trade_date = ? "
            "  AND option_type IN ('CE', 'PE') "
            "GROUP BY option_type",
            (symbol.upper(), as_of.isoformat()),
        ).fetchall()
        if not rows:
            return None
        ce_oi = 0
        pe_oi = 0
        for r in rows:
            if r["option_type"] == "CE":
                ce_oi = int(r["total_oi"] or 0)
            elif r["option_type"] == "PE":
                pe_oi = int(r["total_oi"] or 0)
        if ce_oi == 0:
            return None
        return {
            "pcr_oi": pe_oi / ce_oi,
            "total_ce_oi": ce_oi,
            "total_pe_oi": pe_oi,
        }

    def get_basis(self, symbol: str, as_of: date) -> dict | None:
        """Return futures basis (front-month FUTSTK close minus spot close).

        Spot close comes from daily_stock_data.close; futures close comes
        from the front-month FUTSTK row for the symbol on the date. Returns
        None if either side is missing.
        """
        spot_row = self._conn.execute(
            "SELECT close FROM daily_stock_data "
            "WHERE symbol = ? AND date = ?",
            (symbol.upper(), as_of.isoformat()),
        ).fetchone()
        if not spot_row or spot_row["close"] is None:
            return None
        spot = float(spot_row["close"])

        fut_row = self._conn.execute(
            "SELECT close, expiry_date FROM fno_contracts "
            "WHERE symbol = ? AND trade_date = ? AND instrument = 'FUTSTK' "
            "  AND expiry_date >= ? "
            "ORDER BY expiry_date ASC "
            "LIMIT 1",
            (symbol.upper(), as_of.isoformat(), as_of.isoformat()),
        ).fetchone()
        if not fut_row or fut_row["close"] is None:
            return None
        futures = float(fut_row["close"])
        expiry_iso = fut_row["expiry_date"]
        expiry_d = date.fromisoformat(expiry_iso)

        if spot == 0:
            return None
        return {
            "spot": spot,
            "futures": futures,
            "basis_abs": futures - spot,
            "basis_pct": (futures - spot) / spot * 100,
            "expiry_date": expiry_iso,
            "days_to_expiry": (expiry_d - as_of).days,
        }

    def get_oi_percentile(
        self, symbol: str, as_of: date, lookback_days: int = 90
    ) -> float | None:
        """Return rank-percentile of front-month OI on `as_of` vs lookback.

        Uses the same front-month logic as get_fno_oi_history. Simple rank-
        based percentile: (# values <= current) / total * 100. Returns None
        if fewer than 5 data points or no row for `as_of`.
        """
        history = self.get_fno_oi_history(symbol, days=lookback_days)
        if len(history) < 5:
            return None
        current = None
        series = []
        for row in history:
            oi = row.get("open_interest")
            if oi is None:
                continue
            series.append(oi)
            if row.get("trade_date") == as_of.isoformat():
                current = oi
        if current is None or len(series) < 5:
            return None
        count_le = sum(1 for v in series if v <= current)
        return count_le / len(series) * 100

    def get_fii_derivative_positioning(
        self, as_of: date, days: int = 1
    ) -> dict | None:
        """Return FII long/short/net OI by instrument_category over a window.

        Pulls fno_participant_oi rows where participant='FII' for the date
        range (as_of - days + 1) through as_of. For each instrument_category
        aggregates long_oi/short_oi across the window. Returns None if no
        rows found. Top-level keys: `as_of`, `rows_found`, `by_category`
        (dict keyed by instrument_category).
        """
        from datetime import timedelta
        start = as_of - timedelta(days=max(days - 1, 0))
        rows = self._conn.execute(
            "SELECT instrument_category, "
            "       SUM(long_oi) AS long_oi, "
            "       SUM(short_oi) AS short_oi "
            "FROM fno_participant_oi "
            "WHERE participant = 'FII' "
            "  AND trade_date BETWEEN ? AND ? "
            "GROUP BY instrument_category",
            (start.isoformat(), as_of.isoformat()),
        ).fetchall()
        if not rows:
            return None
        by_category: dict[str, dict] = {}
        for r in rows:
            long_oi = int(r["long_oi"] or 0)
            short_oi = int(r["short_oi"] or 0)
            total = long_oi + short_oi
            by_category[r["instrument_category"]] = {
                "long_oi": long_oi,
                "short_oi": short_oi,
                "net_oi": long_oi - short_oi,
                "net_long_pct": (long_oi / total * 100) if total > 0 else None,
            }
        return {
            "as_of": as_of.isoformat(),
            "rows_found": len(rows),
            "by_category": by_category,
        }

    def get_fno_eligible_stocks(self) -> list[str]:
        """Return sorted list of F&O-eligible symbols from fno_universe."""
        rows = self._conn.execute(
            "SELECT symbol FROM fno_universe ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]
