"""Market registry domain (split from FlowStore, refactor P1.4).

Index constituents + scanner universe, watchlist, Screener.in id cache,
company profiles + documents, peer links, and the listed-subsidiary (SOTP)
mapping. Methods moved verbatim from store.py; they run on the FlowStore
instance via mixin composition, so ``self._conn`` is the shared connection.
"""

from __future__ import annotations

from flowtracker.scan_models import IndexConstituent
from flowtracker.holding_models import WatchlistEntry, ShareholdingChange


class MarketRegistryMixin:
    """Index constituents, watchlist, screener ids, profiles, docs, peers, SOTP."""

    def add_to_watchlist(self, symbol: str, company_name: str | None = None) -> None:
        """Add a symbol to the watchlist."""
        self._conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, company_name) VALUES (?, ?)",
            (symbol.upper(), company_name),
        )
        self._conn.commit()

    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove a symbol from the watchlist."""
        self._conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        self._conn.commit()

    def get_watchlist(self) -> list[WatchlistEntry]:
        """Get all watchlist entries."""
        rows = self._conn.execute("SELECT * FROM watchlist ORDER BY symbol").fetchall()
        return [WatchlistEntry(
            symbol=r["symbol"], company_name=r["company_name"], added_at=r["added_at"],
        ) for r in rows]

    def upsert_index_constituents(self, constituents: list[IndexConstituent]) -> int:
        """Insert or replace index constituents."""
        cursor = self._conn.cursor()
        count = 0
        for c in constituents:
            cursor.execute(
                "INSERT OR REPLACE INTO index_constituents (symbol, index_name, company_name, industry) "
                "VALUES (?, ?, ?, ?)",
                (c.symbol, c.index_name, c.company_name, c.industry),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_index_constituents(self, index_name: str | None = None) -> list[IndexConstituent]:
        """Get index constituents, optionally filtered by index name."""
        if index_name:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents WHERE index_name = ? ORDER BY symbol",
                (index_name,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents ORDER BY index_name, symbol"
            ).fetchall()
        return [IndexConstituent(
            symbol=r["symbol"], index_name=r["index_name"],
            company_name=r["company_name"], industry=r["industry"],
        ) for r in rows]

    def get_all_scanner_symbols(self) -> list[str]:
        """Get distinct symbols from index_constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT symbol FROM index_constituents ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]

    def get_scanner_deviations(
        self, category: str | None = None, limit: int = 20, min_change: float = 0.0,
    ) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all index constituents."""
        cat_filter = "AND s1.category = ?" if category else ""
        min_filter = f"AND ABS(s1.percentage - s2.percentage) >= {min_change}" if min_change > 0 else ""
        params: list = []

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
            f") {cat_filter} {min_filter} "
            "GROUP BY s1.symbol, s1.category "
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

    def upsert_screener_ids(self, symbol: str, company_id: str, warehouse_id: str) -> None:
        """Cache Screener.in company_id and warehouse_id for a symbol."""
        self._conn.execute(
            "INSERT INTO screener_ids (symbol, company_id, warehouse_id, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(symbol) DO UPDATE SET company_id=excluded.company_id, "
            "warehouse_id=excluded.warehouse_id, updated_at=excluded.updated_at",
            (symbol, company_id, warehouse_id),
        )
        self._conn.commit()

    def get_screener_ids(self, symbol: str) -> tuple[str, str] | None:
        """Get cached (company_id, warehouse_id) or None."""
        row = self._conn.execute(
            "SELECT company_id, warehouse_id FROM screener_ids WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        return (row["company_id"], row["warehouse_id"]) if row else None

    # --- Symbol Registry (WS1: multi-market dimension) ---

    def upsert_symbol_registry(
        self,
        symbol: str,
        market: str = "NSE",
        *,
        isin: str | None = None,
        company_name: str | None = None,
        sector: str | None = None,
        gics: str | None = None,
        cik: str | None = None,
    ) -> None:
        """Insert or update a symbol_registry entry.

        Currency + fiscal_year_system are derived from the market config (never
        passed in). isin/company_name/sector/gics/cik use COALESCE on conflict so
        a partial update never nulls out existing data; currency/
        fiscal_year_system/updated_at are always refreshed. ``cik`` is the SEC
        EDGAR identifier (US add-on, Phase 3) — NULL for India rows.
        """
        from flowtracker.market import Market, market_config

        cfg = market_config(Market(market))
        currency = cfg.currency
        fys = "APR_MAR" if cfg.fiscal_year_end_month == 3 else "CALENDAR"
        self._conn.execute(
            """INSERT INTO symbol_registry
               (symbol, market, isin, company_name, currency, fiscal_year_system,
                sector, gics, cik, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(symbol, market) DO UPDATE SET
                 isin=COALESCE(excluded.isin, symbol_registry.isin),
                 company_name=COALESCE(excluded.company_name, symbol_registry.company_name),
                 sector=COALESCE(excluded.sector, symbol_registry.sector),
                 gics=COALESCE(excluded.gics, symbol_registry.gics),
                 cik=COALESCE(excluded.cik, symbol_registry.cik),
                 currency=excluded.currency,
                 fiscal_year_system=excluded.fiscal_year_system,
                 updated_at=datetime('now')""",
            (symbol.upper(), market, isin, company_name, currency, fys, sector, gics, cik),
        )
        self._conn.commit()

    def get_symbol_registry_entry(self, symbol: str, market: str = "NSE") -> dict | None:
        """Get a single symbol_registry entry as a dict, or None."""
        row = self._conn.execute(
            "SELECT * FROM symbol_registry WHERE symbol = ? AND market = ?",
            (symbol.upper(), market),
        ).fetchone()
        return dict(row) if row else None

    def get_symbol_registry(self, market: str | None = None) -> list[dict]:
        """Get all symbol_registry entries, optionally filtered by market."""
        if market:
            rows = self._conn.execute(
                "SELECT * FROM symbol_registry WHERE market = ? ORDER BY market, symbol",
                (market,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM symbol_registry ORDER BY market, symbol"
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_peer_links(self, symbol: str, peers: list[dict]) -> int:
        """Replace all Yahoo peer links for a symbol."""
        symbol = symbol.upper()
        self._conn.execute("DELETE FROM peer_links WHERE symbol = ?", (symbol,))
        count = 0
        for p in peers:
            peer_sym = p.get("peer_symbol", "").upper()
            if not peer_sym or peer_sym == symbol:
                continue
            self._conn.execute(
                "INSERT INTO peer_links (symbol, peer_symbol, score) VALUES (?, ?, ?)",
                (symbol, peer_sym, p.get("score")),
            )
            count += 1
        self._conn.commit()
        return count

    def get_peer_links(self, symbol: str) -> list[dict]:
        """Get Yahoo-recommended peers ordered by similarity score (lower = more similar)."""
        rows = self._conn.execute(
            "SELECT * FROM peer_links WHERE symbol = ? ORDER BY score ASC",
            (symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_company_profile(self, symbol: str, data: dict) -> None:
        """Insert or update company profile (about text, key points)."""
        import json as _json
        self._conn.execute(
            "INSERT INTO company_profiles (symbol, about_text, key_points_json, screener_url, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(symbol) DO UPDATE SET "
            "about_text=excluded.about_text, key_points_json=excluded.key_points_json, "
            "screener_url=excluded.screener_url, updated_at=datetime('now')",
            (
                symbol.upper(),
                data.get("about_text", ""),
                _json.dumps(data.get("key_points", []), ensure_ascii=False),
                data.get("screener_url", ""),
            ),
        )
        self._conn.commit()

    def get_company_profile(self, symbol: str) -> dict | None:
        """Get company profile. Returns dict with about_text, key_points, screener_url."""
        import json as _json
        row = self._conn.execute(
            "SELECT * FROM company_profiles WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["key_points"] = _json.loads(d.pop("key_points_json", "[]") or "[]")
        return d

    # --- Company Documents ---

    def upsert_documents(self, symbol: str, docs_dict: dict) -> int:
        """Store concall/annual report URLs from Screener documents section.

        docs_dict: output of ScreenerClient.parse_documents_from_html
        """
        count = 0
        symbol = symbol.upper()
        for concall in docs_dict.get("concalls", []):
            period = concall.get("quarter", "")
            for doc_type, key in [
                ("concall_transcript", "transcript_url"),
                ("concall_ppt", "ppt_url"),
                ("concall_recording", "recording_url"),
            ]:
                url = concall.get(key, "")
                if url and period:
                    self._conn.execute(
                        "INSERT INTO company_documents (symbol, doc_type, period, url, updated_at) "
                        "VALUES (?, ?, ?, ?, datetime('now')) "
                        "ON CONFLICT(symbol, doc_type, period) DO UPDATE SET "
                        "url=excluded.url, updated_at=datetime('now')",
                        (symbol, doc_type, period, url),
                    )
                    count += 1

        for ar in docs_dict.get("annual_reports", []):
            period = ar.get("year", "")
            url = ar.get("url", "")
            if url and period:
                self._conn.execute(
                    "INSERT INTO company_documents (symbol, doc_type, period, url, updated_at) "
                    "VALUES (?, ?, ?, ?, datetime('now')) "
                    "ON CONFLICT(symbol, doc_type, period) DO UPDATE SET "
                    "url=excluded.url, updated_at=datetime('now')",
                    (symbol, "annual_report", period, url),
                )
                count += 1

        self._conn.commit()
        return count

    def get_documents(self, symbol: str, doc_type: str | None = None) -> list[dict]:
        """Get stored company documents, optionally filtered by type."""
        if doc_type:
            rows = self._conn.execute(
                "SELECT * FROM company_documents WHERE symbol = ? AND doc_type = ? "
                "ORDER BY period DESC",
                (symbol.upper(), doc_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM company_documents WHERE symbol = ? ORDER BY doc_type, period DESC",
                (symbol.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Listed Subsidiaries (SOTP) --

    def upsert_listed_subsidiary(
        self, parent_symbol: str, sub_symbol: str, sub_name: str,
        ownership_pct: float, relationship: str = "", notes: str = "",
    ) -> None:
        """Upsert a parent→subsidiary mapping."""
        self._conn.execute(
            """INSERT INTO listed_subsidiaries
               (parent_symbol, sub_symbol, sub_name, parent_ownership_pct, relationship, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(parent_symbol, sub_symbol) DO UPDATE SET
               sub_name=excluded.sub_name, parent_ownership_pct=excluded.parent_ownership_pct,
               relationship=excluded.relationship, notes=excluded.notes, updated_at=datetime('now')""",
            (parent_symbol.upper(), sub_symbol.upper(), sub_name, ownership_pct, relationship, notes),
        )
        self._conn.commit()

    def get_listed_subsidiaries(self, parent_symbol: str) -> list[dict]:
        """Get all listed subsidiaries for a parent company."""
        rows = self._conn.execute(
            "SELECT * FROM listed_subsidiaries WHERE parent_symbol = ? ORDER BY parent_ownership_pct DESC",
            (parent_symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_parent_companies(self, sub_symbol: str) -> list[dict]:
        """Get parent companies that hold this subsidiary (reverse lookup)."""
        rows = self._conn.execute(
            "SELECT * FROM listed_subsidiaries WHERE sub_symbol = ?",
            (sub_symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]
