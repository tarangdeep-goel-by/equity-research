"""Research / analyst-data domain (split from FlowStore, refactor P1.4).

Consensus estimates + earnings surprises + estimate revisions, FMP technical
indicators, corporate filings, FDA inspections, exchange surveillance flags,
and the IPO pipeline (calendar / subscription / listings). Methods moved
verbatim from store.py; they run on the FlowStore instance via mixin
composition, so ``self._conn`` is the shared connection. Loosely-typed
feature models (FDA / surveillance) are constructed by the caller or read out
as plain dicts, as in the original.
"""

from __future__ import annotations

from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.filing_models import CorporateFiling
from flowtracker.fmp_models import FMPTechnicalIndicator
from flowtracker.ipo_models import IPOIssue, IPOListing, IPOSubscription


class ResearchMixin:
    """Estimates, surprises, revisions, FMP technicals, filings, FDA, surveillance, IPO."""

    def upsert_consensus_estimates(self, estimates: list[ConsensusEstimate]) -> int:
        """Insert or replace consensus estimate records."""
        cursor = self._conn.cursor()
        count = 0
        for e in estimates:
            cursor.execute(
                "INSERT OR REPLACE INTO consensus_estimates "
                "(symbol, date, target_mean, target_median, target_high, target_low, "
                "num_analysts, recommendation, recommendation_score, forward_pe, "
                "forward_eps, eps_current_year, eps_next_year, earnings_growth, current_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e.symbol, e.date, e.target_mean, e.target_median, e.target_high,
                 e.target_low, e.num_analysts, e.recommendation, e.recommendation_score,
                 e.forward_pe, e.forward_eps, e.eps_current_year, e.eps_next_year,
                 e.earnings_growth, e.current_price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_earnings_surprises(self, surprises: list[EarningsSurprise]) -> int:
        """Insert or replace earnings surprise records."""
        cursor = self._conn.cursor()
        count = 0
        for s in surprises:
            cursor.execute(
                "INSERT OR REPLACE INTO earnings_surprises "
                "(symbol, quarter_end, eps_actual, eps_estimate, surprise_pct) "
                "VALUES (?, ?, ?, ?, ?)",
                (s.symbol, s.quarter_end, s.eps_actual, s.eps_estimate, s.surprise_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_estimate_latest(self, symbol: str) -> ConsensusEstimate | None:
        """Get the most recent estimate for a symbol."""
        row = self._conn.execute(
            "SELECT * FROM consensus_estimates WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return ConsensusEstimate(
            symbol=row["symbol"], date=row["date"],
            target_mean=row["target_mean"], target_median=row["target_median"],
            target_high=row["target_high"], target_low=row["target_low"],
            num_analysts=row["num_analysts"], recommendation=row["recommendation"],
            recommendation_score=row["recommendation_score"],
            forward_pe=row["forward_pe"], forward_eps=row["forward_eps"],
            eps_current_year=row["eps_current_year"], eps_next_year=row["eps_next_year"],
            earnings_growth=row["earnings_growth"], current_price=row["current_price"],
        )

    def get_all_latest_estimates(self) -> list[ConsensusEstimate]:
        """Get latest estimate for each symbol, ranked by upside."""
        rows = self._conn.execute(
            "SELECT ce.* FROM consensus_estimates ce "
            "INNER JOIN (SELECT symbol, MAX(date) as max_date FROM consensus_estimates "
            "GROUP BY symbol) latest "
            "ON ce.symbol = latest.symbol AND ce.date = latest.max_date "
            "ORDER BY CASE WHEN ce.target_mean IS NOT NULL AND ce.current_price IS NOT NULL "
            "AND ce.current_price > 0 "
            "THEN (ce.target_mean - ce.current_price) / ce.current_price ELSE -999 END DESC"
        ).fetchall()
        return [ConsensusEstimate(
            symbol=r["symbol"], date=r["date"],
            target_mean=r["target_mean"], target_median=r["target_median"],
            target_high=r["target_high"], target_low=r["target_low"],
            num_analysts=r["num_analysts"], recommendation=r["recommendation"],
            recommendation_score=r["recommendation_score"],
            forward_pe=r["forward_pe"], forward_eps=r["forward_eps"],
            eps_current_year=r["eps_current_year"], eps_next_year=r["eps_next_year"],
            earnings_growth=r["earnings_growth"], current_price=r["current_price"],
        ) for r in rows]

    def get_surprises(self, symbol: str) -> list[EarningsSurprise]:
        """Get earnings surprises for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises WHERE symbol = ? ORDER BY quarter_end DESC",
            (symbol,),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    def get_recent_surprises(self, days: int = 90) -> list[EarningsSurprise]:
        """Get recent earnings surprises across all stocks."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises "
            "WHERE quarter_end >= date('now', ? || ' days') "
            "ORDER BY ABS(COALESCE(surprise_pct, 0)) DESC",
            (f"-{days}",),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    def upsert_estimate_revisions(self, data: dict) -> int:
        """Upsert estimate revision data (all periods for one symbol)."""
        symbol = data["symbol"]
        today = data.get("date") or __import__("datetime").date.today().isoformat()
        count = 0
        for period, trend in data.get("eps_trend", {}).items():
            rev = data.get("eps_revisions", {}).get(period, {})
            self._conn.execute(
                """INSERT INTO estimate_revisions
                   (symbol, date, period, eps_current, eps_7d_ago, eps_30d_ago, eps_60d_ago, eps_90d_ago,
                    revisions_up_7d, revisions_up_30d, revisions_down_7d, revisions_down_30d,
                    momentum_score, momentum_signal)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, date, period) DO UPDATE SET
                    eps_current=excluded.eps_current, eps_7d_ago=excluded.eps_7d_ago,
                    eps_30d_ago=excluded.eps_30d_ago, eps_60d_ago=excluded.eps_60d_ago,
                    eps_90d_ago=excluded.eps_90d_ago,
                    revisions_up_7d=excluded.revisions_up_7d, revisions_up_30d=excluded.revisions_up_30d,
                    revisions_down_7d=excluded.revisions_down_7d, revisions_down_30d=excluded.revisions_down_30d,
                    momentum_score=excluded.momentum_score, momentum_signal=excluded.momentum_signal,
                    fetched_at=datetime('now')""",
                (symbol, today, period,
                 trend.get("current"), trend.get("7d_ago"), trend.get("30d_ago"),
                 trend.get("60d_ago"), trend.get("90d_ago"),
                 rev.get("up_7d"), rev.get("up_30d"), rev.get("down_7d"), rev.get("down_30d"),
                 data.get("momentum_score"), data.get("momentum_signal")),
            )
            count += 1
        self._conn.commit()
        return count

    def get_estimate_revisions(self, symbol: str) -> list[dict]:
        """Get latest estimate revision data for all periods."""
        rows = self._conn.execute(
            """SELECT * FROM estimate_revisions
               WHERE symbol = ? AND date = (
                   SELECT MAX(date) FROM estimate_revisions WHERE symbol = ?
               ) ORDER BY period""",
            (symbol.upper(), symbol.upper()),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_fmp_technical_indicators(self, records: list[FMPTechnicalIndicator]) -> int:
        """Insert or replace FMP technical indicator records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO fmp_technical_indicators "
                "(symbol, date, indicator, value) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.date, r.indicator, r.value),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_fmp_technical_indicators(self, symbol: str) -> list[FMPTechnicalIndicator]:
        """Get latest value per indicator for a symbol."""
        rows = self._conn.execute(
            "SELECT t1.* FROM fmp_technical_indicators t1 "
            "INNER JOIN (SELECT symbol, indicator, MAX(date) as max_date "
            "FROM fmp_technical_indicators WHERE symbol = ? "
            "GROUP BY symbol, indicator) t2 "
            "ON t1.symbol = t2.symbol AND t1.indicator = t2.indicator "
            "AND t1.date = t2.max_date",
            (symbol,),
        ).fetchall()
        return [FMPTechnicalIndicator(
            symbol=r["symbol"], date=r["date"],
            indicator=r["indicator"], value=r["value"],
        ) for r in rows]

    def upsert_filings(self, filings: list[CorporateFiling]) -> int:
        """Insert or replace corporate filing records."""
        cursor = self._conn.cursor()
        count = 0
        for f in filings:
            if not f.news_id:
                continue
            cursor.execute(
                "INSERT OR REPLACE INTO corporate_filings "
                "(symbol, bse_scrip_code, filing_date, category, subcategory, "
                "headline, attachment_name, pdf_flag, file_size, news_id, local_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f.symbol, f.bse_scrip_code, f.filing_date, f.category,
                 f.subcategory, f.headline, f.attachment_name, f.pdf_flag,
                 f.file_size, f.news_id, f.local_path),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_filings(
        self, symbol: str, category: str | None = None, limit: int = 50,
    ) -> list[CorporateFiling]:
        """Get stored filings for a symbol."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM corporate_filings WHERE symbol = ? "
                "AND (category LIKE ? OR subcategory LIKE ?) "
                "ORDER BY filing_date DESC LIMIT ?",
                (symbol, f"%{category}%", f"%{category}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM corporate_filings WHERE symbol = ? "
                "ORDER BY filing_date DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [CorporateFiling(
            symbol=r["symbol"], bse_scrip_code=r["bse_scrip_code"],
            filing_date=r["filing_date"], category=r["category"],
            subcategory=r["subcategory"] or "", headline=r["headline"],
            attachment_name=r["attachment_name"], pdf_flag=r["pdf_flag"],
            file_size=r["file_size"], news_id=r["news_id"],
            local_path=r["local_path"],
        ) for r in rows]

    def upsert_fda_inspections(self, symbol: str, rows: list) -> int:
        """Upsert openFDA-sourced inspection / drug-enforcement rows.

        ``rows`` are FdaInspection pydantic models (see fda_models.FdaInspection).
        ``symbol`` is the NSE symbol (uppercased on insert) — supplied by the
        caller because openFDA records carry only the FDA-side firm name and
        cannot be back-mapped to NSE tickers automatically.

        Returns the count of rows attempted (matches list length on success).
        Empty fei_number / inspection_date are persisted as the empty-string
        sentinel so the (symbol, fei_number, inspection_date) PK enforces
        uniqueness without NULL-collision quirks.
        """
        if not rows:
            return 0
        sym = symbol.upper().strip()
        sql = (
            "INSERT OR REPLACE INTO fda_inspections "
            "(symbol, firm_name, fei_number, inspection_date, classification, "
            "product_area, country, posted_date, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    sym,
                    r.firm_name,
                    r.fei_number or "",
                    r.inspection_date.isoformat() if r.inspection_date else "",
                    r.classification,
                    r.product_area,
                    r.country,
                    r.posted_date.isoformat() if r.posted_date else None,
                ),
            )
        self._conn.commit()
        return len(rows)

    def get_fda_inspections(self, symbol: str, limit: int = 50) -> list[dict]:
        """Return stored FDA inspection rows for ``symbol``, newest first.

        Sort key is ``inspection_date DESC`` then ``posted_date DESC`` —
        ``inspection_date`` may be the empty-string sentinel for malformed
        upstream rows, which sort to the end.
        """
        sql = (
            "SELECT symbol, firm_name, fei_number, inspection_date, "
            "classification, product_area, country, posted_date, ingested_at "
            "FROM fda_inspections WHERE symbol = ? "
            "ORDER BY inspection_date DESC, posted_date DESC "
            "LIMIT ?"
        )
        rows = self._conn.execute(
            sql, (symbol.upper().strip(), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # NSE/BSE surveillance flags (ASM/ESM/GSM)
    # ------------------------------------------------------------------

    def upsert_surveillance_flags(self, rows: list) -> int:
        """Insert-or-replace a batch of ``SurveillanceFlag`` rows.

        ``rows`` is typed loosely as ``list`` to avoid coupling the store
        module to ``surveillance_models``; in practice each element must
        expose the ``SurveillanceFlag`` attributes (symbol, alert_type,
        stage, exchange, effective_date, reason). Returns the number of
        rows touched (matches the input length on a clean upsert; INSERT
        OR REPLACE on the (symbol, alert_type, exchange, effective_date)
        UNIQUE key replaces in place rather than duplicating).
        """
        if not rows:
            return 0
        cursor = self._conn.cursor()
        sql = (
            "INSERT OR REPLACE INTO surveillance_flags "
            "(symbol, alert_type, stage, exchange, effective_date, reason, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))"
        )
        count = 0
        for r in rows:
            cursor.execute(
                sql,
                (
                    r.symbol,
                    r.alert_type,
                    r.stage,
                    r.exchange,
                    r.effective_date,
                    r.reason,
                ),
            )
            count += 1
        self._conn.commit()
        return count

    def get_surveillance_flags(
        self,
        symbol: str | None = None,
        *,
        active_only: bool = True,
        alert_type: str | None = None,
        exchange: str | None = None,
    ) -> list[dict]:
        """Return surveillance-flag rows as plain dicts.

        ``active_only`` is accepted for forward-compat — today every row in
        ``surveillance_flags`` is treated as active (the exchanges' feeds
        only list scrips currently under surveillance, so a row's presence
        in the table is itself the active signal). When a future deactivation
        column is added, this flag will gate it. Today it is a no-op.

        Filtering:
        - ``symbol`` (case-insensitive) — exact symbol match.
        - ``alert_type`` — one of ``"ASM"``, ``"ESM"``, ``"GSM"``.
        - ``exchange`` — one of ``"NSE"``, ``"BSE"``.
        """
        del active_only  # see docstring
        clauses: list[str] = []
        params: list = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper().strip())
        if alert_type:
            clauses.append("alert_type = ?")
            params.append(alert_type.upper().strip())
        if exchange:
            clauses.append("exchange = ?")
            params.append(exchange.upper().strip())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT id, symbol, alert_type, stage, exchange, "
            "effective_date, reason, fetched_at "
            "FROM surveillance_flags"
            + where
            + " ORDER BY exchange, alert_type, symbol, effective_date DESC"
        )
        rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def is_under_surveillance(self, symbol: str) -> bool:
        """Return True if ``symbol`` carries at least one surveillance flag.

        Used by the composite screener to surface a risk-flag column and to
        optionally exclude flagged stocks via ``--exclude-surveillance``.
        Case-insensitive match on ``symbol``.
        """
        if not symbol:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM surveillance_flags WHERE symbol = ? LIMIT 1",
            (symbol.upper().strip(),),
        ).fetchone()
        return row is not None

    # -- IPO + SME pipeline (live-fetch from NSE + BSE, 2026-05-26 feat/ipo-pipeline) --

    def upsert_ipo_calendar(self, issues: list[IPOIssue]) -> int:
        """Upsert IPO calendar rows. Returns number of input rows persisted.

        Idempotency: UNIQUE(issuer_name, open_date). Re-fetches refresh price
        band / size / lot which NSE sometimes adjusts before the open.
        """
        if not issues:
            return 0
        sql = (
            "INSERT OR REPLACE INTO ipo_calendar "
            "(issuer_name, symbol, segment, exchange, open_date, close_date, "
            "listing_date, price_band_low, price_band_high, issue_size_cr, "
            "lot_size, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))"
        )
        for i in issues:
            self._conn.execute(
                sql,
                (
                    i.issuer_name,
                    i.symbol,
                    i.segment,
                    i.exchange,
                    i.open_date,
                    i.close_date,
                    i.listing_date,
                    i.price_band_low,
                    i.price_band_high,
                    i.issue_size_cr,
                    i.lot_size,
                ),
            )
        self._conn.commit()
        return len(issues)

    def upsert_ipo_subscription(self, rows: list[IPOSubscription]) -> int:
        """Upsert subscription snapshots. UNIQUE(issuer_name, as_of_date)."""
        if not rows:
            return 0
        sql = (
            "INSERT OR REPLACE INTO ipo_subscription "
            "(issuer_name, as_of_date, qib_times, nii_times, retail_times, "
            "employee_times, total_times, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    r.issuer_name,
                    r.as_of_date,
                    r.qib_times,
                    r.nii_times,
                    r.retail_times,
                    r.employee_times,
                    r.total_times,
                ),
            )
        self._conn.commit()
        return len(rows)

    def upsert_ipo_listings(self, rows: list[IPOListing]) -> int:
        """Upsert listing-day records. UNIQUE(symbol, listing_date)."""
        if not rows:
            return 0
        sql = (
            "INSERT OR REPLACE INTO ipo_listings "
            "(symbol, issuer_name, listing_date, listing_price, "
            "listing_day_close, listing_pop_pct, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    r.symbol.upper(),
                    r.issuer_name,
                    r.listing_date,
                    r.listing_price,
                    r.listing_day_close,
                    r.listing_pop_pct,
                ),
            )
        self._conn.commit()
        return len(rows)

    def get_ipo_upcoming(self) -> list[IPOIssue]:
        """Return upcoming issues — open_date in the future OR within 7 days past.

        The 7-day rear window keeps an issue visible right after it closes so
        the post-close subscription panel still has context. Rows with no
        open_date (BSE SME stub rows where we couldn't parse) are returned
        last.
        """
        sql = (
            "SELECT issuer_name, symbol, segment, exchange, open_date, "
            "close_date, listing_date, price_band_low, price_band_high, "
            "issue_size_cr, lot_size FROM ipo_calendar "
            "WHERE open_date IS NULL "
            "   OR open_date >= date('now', '-7 day') "
            "ORDER BY (open_date IS NULL), open_date ASC, issuer_name ASC"
        )
        rows = self._conn.execute(sql).fetchall()
        return [IPOIssue(**dict(r)) for r in rows]

    def get_ipo_subscription(self, issuer: str) -> list[IPOSubscription]:
        """Return subscription snapshots for an issuer (substring match)."""
        sql = (
            "SELECT issuer_name, as_of_date, qib_times, nii_times, "
            "retail_times, employee_times, total_times "
            "FROM ipo_subscription "
            "WHERE LOWER(issuer_name) LIKE ? "
            "ORDER BY as_of_date ASC"
        )
        pattern = f"%{issuer.lower().strip()}%"
        rows = self._conn.execute(sql, (pattern,)).fetchall()
        return [IPOSubscription(**dict(r)) for r in rows]

    def get_ipo_listings(self, days: int = 30) -> list[IPOListing]:
        """Return listings whose listing_date is within the last ``days`` days."""
        sql = (
            "SELECT symbol, issuer_name, listing_date, listing_price, "
            "listing_day_close, listing_pop_pct FROM ipo_listings "
            "WHERE listing_date >= date('now', ?) "
            "ORDER BY listing_date DESC"
        )
        rows = self._conn.execute(sql, (f"-{int(days)} day",)).fetchall()
        return [IPOListing(**dict(r)) for r in rows]
