"""Macro indicators domain (split from FlowStore, refactor P1.4).

Daily macro snapshots (FX/VIX/crude/yields), RBI WSS system credit, GST
collections, CPI / IIP / PMI monthly series, and yield-curve helpers. Methods
moved verbatim from store.py; they run on the FlowStore instance via mixin
composition, so ``self._conn`` is the shared connection. Feature-specific
pydantic models (GST/CPI/IIP/PMI) are imported lazily inside the methods, as in
the original.
"""

from __future__ import annotations

from flowtracker.macro_models import MacroSnapshot, MacroSystemCredit


class MacroMixin:
    """Macro daily snapshots + system credit + GST/CPI/IIP/PMI + yield curve."""

    def upsert_macro_snapshots(self, snapshots: list[MacroSnapshot]) -> int:
        """Insert or replace macro daily snapshots.

        Includes the four G-sec tenors (1Y / 5Y / 10Y / 30Y). Fields that
        aren't supplied in a given snapshot stay NULL on existing rows because
        ``INSERT OR REPLACE`` rewrites the row whole — the caller is expected
        to merge multi-source data upstream (yfinance for FX/VIX/crude, CCIL
        for the live yield curve, FBIL/seed for historical tenors).
        """
        cursor = self._conn.cursor()
        count = 0
        for s in snapshots:
            cursor.execute(
                "INSERT OR REPLACE INTO macro_daily "
                "(date, india_vix, usd_inr, eur_inr, gbp_inr, brent_crude, "
                "gsec_1y, gsec_5y, gsec_10y, gsec_30y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (s.date, s.india_vix, s.usd_inr, s.eur_inr, s.gbp_inr,
                 s.brent_crude, s.gsec_1y, s.gsec_5y, s.gsec_10y, s.gsec_30y),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    @staticmethod
    def _row_to_macro_snapshot(row) -> MacroSnapshot:
        """Build a ``MacroSnapshot`` from a ``macro_daily`` row, tolerating
        rows that pre-date the gsec-tenor migration (missing keys → None)."""
        keys = row.keys() if hasattr(row, "keys") else []
        return MacroSnapshot(
            date=row["date"],
            india_vix=row["india_vix"],
            usd_inr=row["usd_inr"],
            eur_inr=row["eur_inr"],
            gbp_inr=row["gbp_inr"],
            brent_crude=row["brent_crude"],
            gsec_1y=row["gsec_1y"] if "gsec_1y" in keys else None,
            gsec_5y=row["gsec_5y"] if "gsec_5y" in keys else None,
            gsec_10y=row["gsec_10y"],
            gsec_30y=row["gsec_30y"] if "gsec_30y" in keys else None,
        )

    def get_macro_latest(self) -> MacroSnapshot | None:
        """Get the most recent macro snapshot."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return self._row_to_macro_snapshot(row)

    def get_macro_previous(self) -> MacroSnapshot | None:
        """Get the second most recent macro snapshot (for delta display)."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1 OFFSET 1"
        ).fetchone()
        if not row:
            return None
        return self._row_to_macro_snapshot(row)

    def get_macro_trend(self, days: int = 30) -> list[MacroSnapshot]:
        """Get macro snapshots for the last N days, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM macro_daily "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC",
            (f"-{days}",),
        ).fetchall()
        return [self._row_to_macro_snapshot(r) for r in rows]

    def upsert_system_credit(self, record: MacroSystemCredit) -> int:
        """Insert or replace one weekly RBI WSS system-credit record.

        Idempotent: re-running with the same release_date overwrites with
        whatever the parser produced this round (allowing late-day re-fetches
        to fill in fields the morning fetch couldn't extract).
        """
        cursor = self._conn.execute(
            "INSERT OR REPLACE INTO macro_system_credit "
            "(release_date, as_of_date, aggregate_deposits_cr, bank_credit_cr, "
            " deposit_growth_yoy, credit_growth_yoy, non_food_credit_growth_yoy, "
            " cd_ratio, m3_growth_yoy, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.release_date, record.as_of_date,
                record.aggregate_deposits_cr, record.bank_credit_cr,
                record.deposit_growth_yoy, record.credit_growth_yoy,
                record.non_food_credit_growth_yoy,
                record.cd_ratio, record.m3_growth_yoy, record.source,
            ),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_latest_system_credit(self) -> MacroSystemCredit | None:
        """Most recent RBI WSS system-credit record."""
        row = self._conn.execute(
            "SELECT * FROM macro_system_credit ORDER BY release_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MacroSystemCredit(
            release_date=row["release_date"],
            as_of_date=row["as_of_date"],
            aggregate_deposits_cr=row["aggregate_deposits_cr"],
            bank_credit_cr=row["bank_credit_cr"],
            deposit_growth_yoy=row["deposit_growth_yoy"],
            credit_growth_yoy=row["credit_growth_yoy"],
            non_food_credit_growth_yoy=row["non_food_credit_growth_yoy"],
            cd_ratio=row["cd_ratio"],
            m3_growth_yoy=row["m3_growth_yoy"],
            source=row["source"] or "RBI_WSS",
        )

    def get_system_credit_trend(self, weeks: int = 12) -> list[MacroSystemCredit]:
        """Return up to ``weeks`` most-recent system-credit records (newest first)."""
        rows = self._conn.execute(
            "SELECT * FROM macro_system_credit ORDER BY release_date DESC LIMIT ?",
            (weeks,),
        ).fetchall()
        return [MacroSystemCredit(
            release_date=r["release_date"],
            as_of_date=r["as_of_date"],
            aggregate_deposits_cr=r["aggregate_deposits_cr"],
            bank_credit_cr=r["bank_credit_cr"],
            deposit_growth_yoy=r["deposit_growth_yoy"],
            credit_growth_yoy=r["credit_growth_yoy"],
            non_food_credit_growth_yoy=r["non_food_credit_growth_yoy"],
            cd_ratio=r["cd_ratio"],
            m3_growth_yoy=r["m3_growth_yoy"],
            source=r["source"] or "RBI_WSS",
        ) for r in rows]

    def upsert_gst_collections(self, rows: list) -> int:
        """Insert-or-replace a batch of ``GSTCollectionMonth`` records.

        ``rows`` is typed loosely as ``list`` so this module does not need to
        import ``gst_models``. Each element must expose the
        ``GSTCollectionMonth`` attribute surface (period, gross_collection_cr,
        cgst_cr, sgst_cr, igst_cr, cess_cr, domestic_cr, imports_cr,
        growth_yoy_pct, source_url). Returns the number of rows touched.

        Idempotent: a re-upsert of the same ``period`` replaces (not
        duplicates) the row — the table has ``UNIQUE(period)``.
        """
        if not rows:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO gst_collections_monthly "
                "(period, gross_collection_cr, cgst_cr, sgst_cr, igst_cr, "
                "cess_cr, domestic_cr, imports_cr, growth_yoy_pct, source_url, "
                "fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.period,
                    r.gross_collection_cr,
                    r.cgst_cr,
                    r.sgst_cr,
                    r.igst_cr,
                    r.cess_cr,
                    r.domestic_cr,
                    r.imports_cr,
                    r.growth_yoy_pct,
                    r.source_url,
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_gst_latest(self):
        """Return the row with the most recent ``period``, as a
        ``GSTCollectionMonth`` instance, or ``None`` if the table is empty.

        Import is local because the store module deliberately avoids a
        top-level dependency on every feature's pydantic models — the
        ``gst_models`` import only fires if the caller actually invokes this
        method."""
        from flowtracker.gst_models import GSTCollectionMonth

        row = self._conn.execute(
            "SELECT period, gross_collection_cr, cgst_cr, sgst_cr, igst_cr, "
            "cess_cr, domestic_cr, imports_cr, growth_yoy_pct, source_url "
            "FROM gst_collections_monthly "
            "ORDER BY period DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        return GSTCollectionMonth(**dict(row))

    def get_gst_trend(self, months: int) -> list[dict]:
        """Return the last ``months`` rows as plain dicts, newest first."""
        if months < 1:
            return []
        rows = self._conn.execute(
            "SELECT period, gross_collection_cr, cgst_cr, sgst_cr, igst_cr, "
            "cess_cr, domestic_cr, imports_cr, growth_yoy_pct, source_url, "
            "fetched_at "
            "FROM gst_collections_monthly "
            "ORDER BY period DESC LIMIT ?",
            (int(months),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_gst_yoy_series(self) -> list[dict]:
        """Compute the YoY% growth series by joining each row to the same
        month one year prior. Returns dicts ordered by ``period`` ASCENDING.
        """
        rows = self._conn.execute(
            """
            SELECT cur.period AS period,
                   cur.gross_collection_cr AS gross_cr,
                   prior.gross_collection_cr AS prior_year_gross_cr,
                   CASE
                       WHEN prior.gross_collection_cr IS NULL
                            OR prior.gross_collection_cr = 0
                            OR cur.gross_collection_cr IS NULL
                       THEN NULL
                       ELSE ((cur.gross_collection_cr - prior.gross_collection_cr)
                             * 100.0 / prior.gross_collection_cr)
                   END AS computed_yoy_pct
            FROM gst_collections_monthly AS cur
            LEFT JOIN gst_collections_monthly AS prior
              ON prior.period = (
                  printf('%04d-%s',
                         CAST(substr(cur.period, 1, 4) AS INTEGER) - 1,
                         substr(cur.period, 6, 2))
              )
            WHERE prior.gross_collection_cr IS NOT NULL
            ORDER BY cur.period ASC
            """,
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # CPI monthly inflation (feat/macro-expansion, 2026-05-26)
    # ------------------------------------------------------------------

    def upsert_cpi_monthly(self, rows: list) -> int:
        """Insert-or-replace a batch of ``CPIMonth`` records.

        ``rows`` is typed loosely as ``list`` so this module does not need to
        import ``cpi_models`` at the top. Each element must expose the
        ``CPIMonth`` attribute surface (period, cpi_index, yoy_pct, source,
        source_url). Returns the count of rows touched. Idempotent on
        ``period``.
        """
        if not rows:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO cpi_monthly "
                "(period, cpi_index, yoy_pct, source, source_url, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.period,
                    r.cpi_index,
                    r.yoy_pct,
                    getattr(r, "source", "seed"),
                    getattr(r, "source_url", None),
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_cpi_latest(self):
        """Return the row with the most recent ``period`` as a ``CPIMonth``."""
        from flowtracker.cpi_models import CPIMonth

        row = self._conn.execute(
            "SELECT period, cpi_index, yoy_pct, source, source_url "
            "FROM cpi_monthly ORDER BY period DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        return CPIMonth(**dict(row))

    def get_cpi_trend(self, months: int) -> list[dict]:
        """Return the last ``months`` rows as plain dicts, newest first."""
        if months < 1:
            return []
        rows = self._conn.execute(
            "SELECT period, cpi_index, yoy_pct, source, source_url, fetched_at "
            "FROM cpi_monthly ORDER BY period DESC LIMIT ?",
            (int(months),),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # IIP monthly industrial production (feat/macro-expansion)
    # ------------------------------------------------------------------

    def upsert_iip_monthly(self, rows: list) -> int:
        if not rows:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO iip_monthly "
                "(period, iip_index, yoy_pct, source, source_url, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.period,
                    r.iip_index,
                    r.yoy_pct,
                    getattr(r, "source", "seed"),
                    getattr(r, "source_url", None),
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_iip_latest(self):
        from flowtracker.iip_models import IIPMonth

        row = self._conn.execute(
            "SELECT period, iip_index, yoy_pct, source, source_url "
            "FROM iip_monthly ORDER BY period DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        return IIPMonth(**dict(row))

    def get_iip_trend(self, months: int) -> list[dict]:
        if months < 1:
            return []
        rows = self._conn.execute(
            "SELECT period, iip_index, yoy_pct, source, source_url, fetched_at "
            "FROM iip_monthly ORDER BY period DESC LIMIT ?",
            (int(months),),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # PMI monthly Services + Manufacturing (feat/macro-expansion)
    # ------------------------------------------------------------------

    def upsert_pmi_monthly(self, rows: list) -> int:
        """Insert-or-replace ``PMIMonth`` records.

        Semantics: a row with only services_pmi set (Manufacturing release
        not yet out for the month) is valid and will be replaced when the
        Manufacturing follow-up upsert lands. The replace overwrites BOTH
        columns, so the caller is responsible for merging a partial fetch
        against the existing row when only one side is supplied. The default
        seed ships both columns together; the live ``pmi fetch --source-url``
        path handles single-side updates by passing through whatever the
        parser extracted (None for the missing side).
        """
        if not rows:
            return 0
        cursor = self._conn.cursor()
        count = 0
        for r in rows:
            cursor.execute(
                "INSERT OR REPLACE INTO pmi_monthly "
                "(period, services_pmi, manufacturing_pmi, source, source_url, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    r.period,
                    r.services_pmi,
                    r.manufacturing_pmi,
                    getattr(r, "source", "seed"),
                    getattr(r, "source_url", None),
                ),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_pmi_latest(self):
        from flowtracker.pmi_models import PMIMonth

        row = self._conn.execute(
            "SELECT period, services_pmi, manufacturing_pmi, source, source_url "
            "FROM pmi_monthly ORDER BY period DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        return PMIMonth(**dict(row))

    def get_pmi_trend(self, months: int) -> list[dict]:
        if months < 1:
            return []
        rows = self._conn.execute(
            "SELECT period, services_pmi, manufacturing_pmi, source, source_url, fetched_at "
            "FROM pmi_monthly ORDER BY period DESC LIMIT ?",
            (int(months),),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Yield-curve helpers (feat/macro-expansion)
    # ------------------------------------------------------------------

    def get_yield_curve_latest(self):
        """Return today's (or most-recent) G-sec curve as a dict
        ``{"date": ..., "gsec_1y": ..., "gsec_5y": ..., "gsec_10y": ...,
        "gsec_30y": ...}``, or ``None`` if macro_daily is empty.

        Reads from ``macro_daily`` directly so the live CCIL-scraped curve
        and historical seed both flow through one surface.
        """
        row = self._conn.execute(
            "SELECT date, gsec_1y, gsec_5y, gsec_10y, gsec_30y "
            "FROM macro_daily "
            "WHERE gsec_1y IS NOT NULL OR gsec_5y IS NOT NULL "
            "OR gsec_10y IS NOT NULL OR gsec_30y IS NOT NULL "
            "ORDER BY date DESC LIMIT 1",
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_yield_curve_history(self, days: int = 365) -> list[dict]:
        """Return non-null curve observations from the last N days,
        ordered date ascending (chart-friendly)."""
        rows = self._conn.execute(
            "SELECT date, gsec_1y, gsec_5y, gsec_10y, gsec_30y "
            "FROM macro_daily "
            "WHERE date >= date('now', ? || ' days') "
            "AND (gsec_1y IS NOT NULL OR gsec_5y IS NOT NULL "
            "OR gsec_10y IS NOT NULL OR gsec_30y IS NOT NULL) "
            "ORDER BY date ASC",
            (f"-{days}",),
        ).fetchall()
        return [dict(r) for r in rows]
