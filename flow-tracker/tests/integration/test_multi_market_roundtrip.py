"""WS6 — Phase-2 exit-gate proof: a synthetic non-NSE row round-trips through
store → validation → display-format → a pure-compute method WITHOUT touching any
India/NSE-specific path, and coexists with an NSE row of the same symbol+date.

This is the gate that proves the multi-market schema is genuinely market-ready:
the same column set, validation cluster, formatter, and compute helper all handle
a USD/NASDAQ row correctly while the legacy INR/NSE behavior is unchanged.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from flowtracker.market import Market, fmt_monetary, market_symbol
from flowtracker.store import FlowStore
from flowtracker.store_domains._shared import _percentile_rank, _validate_row

# A synthetic USD market cap in millions large enough to exceed the INR-crore
# upper bound (valuation_snapshot.market_cap hi = ₹25L Cr = 2.5e7). Interpreted
# as USD millions this is a fine (if synthetic mega-cap) value; interpreted as
# crores it blows past the ceiling — exactly the India-specific assumption we
# must NOT apply to a USD row. 3.0e7 mn > 2.5e7 crore-bound.
MSFT_MARKET_CAP_USD_MN = 30_000_000.0
DATE = "2026-05-29"


def _load_migration_script():
    """Import scripts/migrate-market-pk.py (not a package) by file path."""
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "migrate-market-pk.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_market_pk", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _insert_valuation_row(store: FlowStore, *, symbol, market, currency, market_cap,
                          net_margin=None, date=DATE):
    """Direct-SQL insert of a valuation_snapshot row with explicit market/currency.

    The ValuationSnapshot pydantic model carries no market/currency field, so we
    write the row directly to simulate a non-NSE listing (per WS6 spec)."""
    store._conn.execute(
        "INSERT INTO valuation_snapshot (symbol, market, currency, date, market_cap, net_margin) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (symbol, market, currency, date, market_cap, net_margin),
    )
    store._conn.commit()


class TestMultiMarketRoundtrip:
    def test_store_nasdaq_row_and_registry(self, tmp_db):
        """STORE: a NASDAQ/USD valuation row + symbol_registry entry persist, and
        the registry derives currency=USD / fiscal_year_system=CALENDAR from the
        market config (never passed in)."""
        store = FlowStore(db_path=tmp_db)
        try:
            _insert_valuation_row(
                store, symbol="MSFT", market="NASDAQ", currency="USD",
                market_cap=MSFT_MARKET_CAP_USD_MN,
            )
            store.upsert_symbol_registry(
                "MSFT", market="NASDAQ",
                company_name="Microsoft", sector="Technology",
            )

            entry = store.get_symbol_registry_entry("MSFT", "NASDAQ")
            assert entry is not None
            # WS1 derives currency + fiscal_year_system from MarketConfig.
            assert entry["currency"] == "USD"
            assert entry["fiscal_year_system"] == "CALENDAR"
            assert entry["company_name"] == "Microsoft"

            row = store._conn.execute(
                "SELECT market, currency, market_cap FROM valuation_snapshot "
                "WHERE symbol = ? AND market = ?",
                ("MSFT", "NASDAQ"),
            ).fetchone()
            assert row["market"] == "NASDAQ"
            assert row["currency"] == "USD"
            assert row["market_cap"] == MSFT_MARKET_CAP_USD_MN
        finally:
            store.close()

    def test_validation_is_market_parameterized(self):
        """VALIDATION: the big USD market_cap produces NO warning under USD (crore
        bound skipped), but a bad percentage IS flagged. The same row under
        NSE/INR DOES flag the market_cap — proving the parameterization matters."""
        good_usd_row = {"market_cap": MSFT_MARKET_CAP_USD_MN}
        # USD: crore-magnitude bound skipped → no warning on the huge market_cap.
        assert _validate_row("valuation_snapshot", good_usd_row,
                             market="NASDAQ", currency="USD") == []

        # Same row, but with a nonsense percentage — currency-agnostic bound still
        # applies, so net_margin=250 is flagged even for USD.
        bad_pct_row = {"market_cap": MSFT_MARKET_CAP_USD_MN, "net_margin": 250}
        usd_warnings = _validate_row("valuation_snapshot", bad_pct_row,
                                     market="NASDAQ", currency="USD")
        assert any("net_margin" in w for w in usd_warnings)
        assert not any("market_cap" in w for w in usd_warnings)

        # Contrast: validated as NSE/INR, the crore bound DOES catch the market_cap.
        inr_warnings = _validate_row("valuation_snapshot", good_usd_row,
                                     market="NSE", currency="INR")
        assert any("market_cap" in w for w in inr_warnings)

    def test_display_format_per_market(self):
        """DISPLAY: fmt_monetary renders the market's currency + magnitude label."""
        usd = fmt_monetary(MSFT_MARKET_CAP_USD_MN, Market.NASDAQ)
        assert usd.startswith("$")
        assert usd.endswith("mn")

        inr = fmt_monetary(1234.56, Market.NSE)
        assert inr.startswith("₹")
        assert inr.endswith("Cr")

    def test_pure_compute_is_market_agnostic(self):
        """COMPUTE: _percentile_rank is a pure numeric helper — it gives the same
        answer regardless of market, currency, or units. Run it on the row's
        market_cap against a peer series of USD-million mega-caps."""
        peer_caps_usd_mn = [500_000.0, 1_000_000.0, 2_000_000.0, 3_000_000.0]
        pct = _percentile_rank(MSFT_MARKET_CAP_USD_MN, peer_caps_usd_mn)
        # MSFT is larger than all 4 peers → 100th percentile (<= definition).
        assert pct == 100.0

        # Identity check: feeding the equivalent magnitudes in any unit yields the
        # same rank — the compute makes no India/INR/crore assumption.
        scaled = [c / 10 for c in peer_caps_usd_mn]
        assert _percentile_rank(MSFT_MARKET_CAP_USD_MN / 10, scaled) == 100.0

    def test_multi_market_coexistence_no_collision(self, tmp_db):
        """NO-COLLISION: after folding `market` into the UNIQUE key (WS5 rebuild),
        an NSE row and a NASDAQ row for the SAME symbol+date coexist (2 rows), and
        a duplicate (MSFT, NASDAQ, date) is rejected by the UNIQUE constraint."""
        store = FlowStore(db_path=tmp_db)
        store.close()  # release the WAL connection before the script reopens the DB

        # Apply the WS5 manual rebuild to the temp DB: valuation_snapshot UNIQUE
        # becomes (symbol, market, date).
        migrate = _load_migration_script()
        conn = sqlite3.connect(str(tmp_db))
        try:
            rebuilt = migrate.rebuild_table(
                conn, "valuation_snapshot",
                ("symbol", "market", "date"), dry_run=False,
            )
            conn.commit()
        finally:
            conn.close()
        assert rebuilt is True

        store = FlowStore(db_path=tmp_db)
        try:
            # Same symbol + same date, different markets — must coexist.
            _insert_valuation_row(store, symbol="MSFT", market="NSE",
                                  currency="INR", market_cap=100.0)
            _insert_valuation_row(store, symbol="MSFT", market="NASDAQ",
                                  currency="USD", market_cap=MSFT_MARKET_CAP_USD_MN)

            count = store._conn.execute(
                "SELECT COUNT(*) AS n FROM valuation_snapshot WHERE symbol = ? AND date = ?",
                ("MSFT", DATE),
            ).fetchone()["n"]
            assert count == 2

            # A duplicate (MSFT, NASDAQ, date) now collides on the new UNIQUE key.
            with pytest.raises(sqlite3.IntegrityError):
                store._conn.execute(
                    "INSERT INTO valuation_snapshot (symbol, market, currency, date, market_cap) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("MSFT", "NASDAQ", "USD", DATE, 9_999_999.0),
                )
        finally:
            store.close()

    def test_india_ticker_formatting_untouched(self):
        """INDIA-PATH-UNTOUCHED: the NASDAQ symbol gets NO `.NS` suffix, while the
        legacy NSE path still appends `.NS` — no India formatting leaked in."""
        assert market_symbol("MSFT", Market.NASDAQ) == "MSFT"
        assert market_symbol("RELIANCE", Market.NSE) == "RELIANCE.NS"
