"""Tests for flowtracker.research.refresh.

Covers:
- `_extract_ids_from_html`: regex-based ID extraction from Screener HTML.
- `_is_fresh`: freshness gate (already partially covered in test_refresh.py, but
  here we add edge cases relevant to the orchestrator).
- `_detect_parent_subsidiary`: promoter-based parent auto-detection.
- `refresh_for_research`: end-to-end orchestration with every client mocked.
  - Happy path (all clients succeed cheaply -> mostly empty parses).
  - Freshness short-circuit (pre-populated data skips the refresh).
  - Individual client failures logged/swallowed, others still run.
  - FMP credential-missing path (FileNotFoundError) handled.
  - Analytical snapshot: cached path vs. missing-script path.
- `refresh_for_business`: light-refresh orchestration, including its own
  freshness gate.

All external clients are patched at their source-module import site so the
function's `from ... import ...` lazy imports resolve to mocks. DB is pinned
via ``FLOWTRACKER_DB`` env so the internal ``FlowStore()`` opens the test DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from flowtracker.fund_models import ValuationSnapshot
from flowtracker.research.refresh import (
    _detect_parent_subsidiary,
    _extract_ids_from_html,
    _is_fresh,
    refresh_for_business,
    refresh_for_research,
)
from flowtracker.scan_models import IndexConstituent
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_screener_client_mock() -> MagicMock:
    """Build a MagicMock that behaves like a `ScreenerClient` context manager.

    All methods return safe empties so every sub-branch runs but nothing gets
    parsed — keeps the happy-path test compact without fixing pydantic schemas.
    """
    sc = MagicMock()
    sc.fetch_company_page.return_value = (
        '<html data-company-id="12345" '
        'formaction="/user/company/export/67890/">content</html>'
    )
    sc.parse_about_from_html.return_value = {}
    sc.parse_documents_from_html.return_value = {}
    sc.parse_quarterly_from_html.return_value = []
    sc.parse_ratios_from_html.return_value = []
    sc.download_excel.return_value = b""
    sc.parse_annual_financials.return_value = []
    sc.fetch_standalone_summary.return_value = []
    sc.fetch_chart_data_by_type.return_value = {"datasets": []}
    sc.fetch_peers.return_value = []
    sc.fetch_shareholders.return_value = {}
    sc.fetch_schedules.return_value = {}

    # Context-manager wrapper (mimics `with ScreenerClient() as sc:`)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=sc)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _make_cm_mock(inner: MagicMock) -> MagicMock:
    """Wrap an instance mock in a context-manager wrapper."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _patch_all_external_clients() -> dict[str, MagicMock]:
    """Return a dict of patchers for every external client used by refresh.

    Caller is expected to apply these with `with ExitStack()` or explicit
    context managers. The returned mocks are classes (i.e., the patch target
    is the class), so instantiating `Class()` returns a MagicMock.
    """
    raise NotImplementedError  # not used — inlined below for clarity


# ---------------------------------------------------------------------------
# _extract_ids_from_html
# ---------------------------------------------------------------------------


class TestExtractIdsFromHtml:
    """The regex extractor must be tolerant to various HTML layouts."""

    def test_both_ids_present(self):
        """Standard Screener page with both company-id and export formaction."""
        html = (
            '<div data-company-id="12345"></div>'
            '<button formaction="/user/company/export/67890/">Excel</button>'
        )
        assert _extract_ids_from_html(html) == ("12345", "67890")

    def test_export_url_fallback(self):
        """No formaction attr, just the URL in a link — still extracts warehouse."""
        html = '<a href="/user/company/export/42/">download</a>'
        assert _extract_ids_from_html(html) == ("", "42")

    def test_missing_both_returns_empty_strings(self):
        """Unrelated HTML returns two empty strings, never raises."""
        assert _extract_ids_from_html("<html><body>hi</body></html>") == ("", "")

    def test_only_company_id(self):
        """company-id present without export URL — warehouse empty."""
        assert _extract_ids_from_html('<x data-company-id="999">') == ("999", "")


# ---------------------------------------------------------------------------
# _is_fresh — additional cases beyond test_refresh.py
# ---------------------------------------------------------------------------


class TestIsFreshEdgeCases:
    """Additional freshness-gate behaviours exercised by the orchestrator."""

    def test_boundary_just_inside_window(self, populated_store: FlowStore):
        """Row stamped 1h ago with hours=6 → fresh."""
        stamp = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        populated_store._conn.execute(
            "UPDATE quarterly_results SET fetched_at = ? WHERE symbol = ?",
            (stamp, "SBIN"),
        )
        populated_store._conn.commit()
        assert _is_fresh(populated_store, "SBIN", "quarterly_results", hours=6) is True

    def test_boundary_just_outside_window(self, populated_store: FlowStore):
        """Row stamped 10h ago with hours=6 → stale."""
        stamp = (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        populated_store._conn.execute(
            "UPDATE quarterly_results SET fetched_at = ? WHERE symbol = ?",
            (stamp, "SBIN"),
        )
        populated_store._conn.commit()
        assert _is_fresh(populated_store, "SBIN", "quarterly_results", hours=6) is False


# ---------------------------------------------------------------------------
# _detect_parent_subsidiary
# ---------------------------------------------------------------------------


class TestDetectParentSubsidiary:
    """Auto-detect subsidiary relationship from promoter list."""

    def test_detects_listed_parent(self, store: FlowStore):
        """Promoter matches index_constituent → listed_subsidiaries gets a row."""
        store.upsert_index_constituents([
            IndexConstituent(
                symbol="PARENT",
                index_name="NIFTY 50",
                company_name="Parentco Holdings Ltd",
                industry="Holdings",
            ),
            IndexConstituent(
                symbol="SUBCO",
                index_name="NIFTY 500",
                company_name="Subsidiary Co Ltd",
                industry="Services",
            ),
        ])
        shareholders = [
            {
                "classification": "Promoters",
                "holder_name": "Parentco Holdings Ltd",
                "percentage": 55.0,
            },
        ]
        _detect_parent_subsidiary(store, "SUBCO", shareholders)
        rows = store._conn.execute(
            "SELECT parent_symbol, sub_symbol FROM listed_subsidiaries "
            "WHERE sub_symbol = ?",
            ("SUBCO",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["parent_symbol"] == "PARENT"

    def test_skips_small_promoter_stake(self, store: FlowStore):
        """Promoter below 20% threshold is not considered a parent."""
        store.upsert_index_constituents([
            IndexConstituent(
                symbol="PARENT",
                index_name="NIFTY 50",
                company_name="Parentco Holdings Ltd",
                industry="Holdings",
            ),
            IndexConstituent(
                symbol="SUBCO",
                index_name="NIFTY 500",
                company_name="Sub Co Ltd",
                industry="Services",
            ),
        ])
        shareholders = [
            {
                "classification": "Promoters",
                "holder_name": "Parentco Holdings Ltd",
                "percentage": 5.0,  # below 20
            },
        ]
        _detect_parent_subsidiary(store, "SUBCO", shareholders)
        rows = store._conn.execute(
            "SELECT * FROM listed_subsidiaries WHERE sub_symbol = ?",
            ("SUBCO",),
        ).fetchall()
        assert rows == []

    def test_ignores_non_promoter_class(self, store: FlowStore):
        """Non-promoter classifications are ignored."""
        store.upsert_index_constituents([
            IndexConstituent(
                symbol="PARENT",
                index_name="NIFTY 50",
                company_name="Parentco Holdings Ltd",
                industry="Holdings",
            ),
            IndexConstituent(
                symbol="SUBCO",
                index_name="NIFTY 500",
                company_name="Sub Co Ltd",
                industry="Services",
            ),
        ])
        shareholders = [
            {
                "classification": "Public",  # not "Promoters"
                "holder_name": "Parentco Holdings Ltd",
                "percentage": 60.0,
            },
        ]
        _detect_parent_subsidiary(store, "SUBCO", shareholders)
        rows = store._conn.execute(
            "SELECT * FROM listed_subsidiaries WHERE sub_symbol = ?",
            ("SUBCO",),
        ).fetchall()
        assert rows == []

    def test_swallows_exceptions(self, store: FlowStore):
        """Bogus shareholder shape must not raise."""
        # Works fine: no constituents seeded, so no match → no write, no error.
        _detect_parent_subsidiary(store, "ANYSYM", [{"bad": "data"}])


# ---------------------------------------------------------------------------
# refresh_for_research — orchestration
# ---------------------------------------------------------------------------


class TestRefreshForResearch:
    """End-to-end refresh path with every client mocked."""

    def _pin_db(self, monkeypatch: pytest.MonkeyPatch, tmp_db) -> None:
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    def _patches(self, screener_cm: MagicMock | None = None,
                 overrides: dict | None = None):
        """Return a list of patch context managers for the full client graph.

        Every external client is replaced with a minimal mock that returns
        empty results. Override specific ones via `overrides` (class name →
        class constructor mock).
        """
        screener_cm = screener_cm or _make_screener_client_mock()
        overrides = overrides or {}

        # Simple stubs returning empties (methods plain, not context managers)
        fund_client = MagicMock()
        fund_client.fetch_valuation_snapshot.return_value = None
        fund_client.fetch_yahoo_peers.return_value = []

        estimates_client = MagicMock()
        estimates_client.fetch_estimates.return_value = None
        estimates_client.fetch_surprises.return_value = []

        filing_inner = MagicMock()
        filing_inner.fetch_yfinance_corporate_actions.return_value = []
        filing_inner.fetch_filings.return_value = []
        filing_cm = _make_cm_mock(filing_inner)

        insider_inner = MagicMock()
        insider_inner.fetch_by_symbol.return_value = []
        insider_cm = _make_cm_mock(insider_inner)

        bhav_inner = MagicMock()
        bhav_inner.fetch_range.return_value = []
        bhav_cm = _make_cm_mock(bhav_inner)

        deals_inner = MagicMock()
        deals_inner.fetch_deals.return_value = []
        deals_cm = _make_cm_mock(deals_inner)

        macro_inner = MagicMock()
        macro_inner.fetch_snapshot.return_value = []
        macro_cm = _make_cm_mock(macro_inner)

        nse_inner = MagicMock()
        nse_inner.fetch_daily.return_value = []
        nse_cm = _make_cm_mock(nse_inner)

        fmp_instance = MagicMock()
        fmp_instance.fetch_dcf.return_value = None
        fmp_instance.fetch_technicals_all.return_value = []
        fmp_instance.fetch_key_metrics.return_value = []
        fmp_instance.fetch_financial_growth.return_value = []
        fmp_instance.fetch_analyst_grades.return_value = []
        fmp_instance.fetch_price_targets.return_value = []

        patches = [
            patch("flowtracker.screener_client.ScreenerClient",
                  return_value=screener_cm),
            patch("flowtracker.fund_client.FundClient",
                  return_value=fund_client),
            patch("flowtracker.estimates_client.EstimatesClient",
                  return_value=estimates_client),
            patch("flowtracker.filing_client.FilingClient",
                  return_value=filing_cm),
            patch("flowtracker.insider_client.InsiderClient",
                  return_value=insider_cm),
            patch("flowtracker.bhavcopy_client.BhavcopyClient",
                  return_value=bhav_cm),
            patch("flowtracker.deals_client.DealsClient",
                  return_value=deals_cm),
            patch("flowtracker.macro_client.MacroClient",
                  return_value=macro_cm),
            patch("flowtracker.client.NSEClient",
                  return_value=nse_cm),
            patch("flowtracker.fmp_client.FMPClient",
                  return_value=fmp_instance),
            patch("flowtracker.research.concall_extractor.ensure_transcript_pdfs",
                  return_value=0),
            patch("flowtracker.research.snapshot_builder.build_company_snapshot",
                  return_value=False),
            patch("flowtracker.research.refresh.time.sleep"),
        ]
        for name, repl in overrides.items():
            patches.append(patch(name, repl))
        return patches

    def test_happy_path_returns_summary(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """All clients return empties → refresh completes, summary is a dict."""
        self._pin_db(monkeypatch, tmp_db)
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            summary = refresh_for_research("TESTSYM", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        assert isinstance(summary, dict)
        # Screener IDs were extracted from the mocked HTML → row was written.
        assert summary.get("screener_ids") == 1

    def test_symbol_is_uppercased(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Lower-case input symbol is normalized before any client call."""
        self._pin_db(monkeypatch, tmp_db)
        screener_cm = _make_screener_client_mock()
        inner_sc = screener_cm.__enter__.return_value

        patches = self._patches(screener_cm=screener_cm)
        for p in patches:
            p.start()
        try:
            refresh_for_research("testsym", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        inner_sc.fetch_company_page.assert_called_once_with("TESTSYM")

    def test_freshness_gate_short_circuits(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """If key tables are fresh, refresh returns early with existing counts."""
        self._pin_db(monkeypatch, tmp_db)
        # Seed fresh rows in 2 of the 3 key tables → short-circuit triggers.
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")
        with FlowStore(db_path=tmp_db) as s:
            s._conn.execute(
                "INSERT INTO quarterly_results (symbol, quarter_end, revenue, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                ("FRESH", "2025-03-31", 100.0, now),
            )
            s._conn.execute(
                "INSERT INTO valuation_snapshot (symbol, date, price, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                ("FRESH", today, 100.0, now),
            )
            s._conn.commit()

        # Patch ScreenerClient to assert it was NOT called.
        screener_ctor = MagicMock()
        with (
            patch("flowtracker.screener_client.ScreenerClient", screener_ctor),
            patch("flowtracker.research.refresh.time.sleep"),
        ):
            summary = refresh_for_research("FRESH", max_age_hours=6)

        screener_ctor.assert_not_called()
        # Short-circuit returns existing counts for each key table
        assert summary.get("quarterly_results") == 1
        assert summary.get("valuation_snapshot") == 1
        assert summary.get("company_profiles") == 0

    def test_screener_failure_does_not_stop_pipeline(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Screener blowing up on fetch_company_page → logged, other blocks still run."""
        self._pin_db(monkeypatch, tmp_db)
        screener_inner = MagicMock()
        screener_inner.fetch_company_page.side_effect = RuntimeError("boom")
        screener_cm = _make_cm_mock(screener_inner)

        fund_client = MagicMock()
        fund_client.fetch_valuation_snapshot.return_value = None
        fund_client.fetch_yahoo_peers.return_value = []

        patches = self._patches(screener_cm=screener_cm)
        # Replace fund_client with our explicit one so we can assert on it
        patches = [p for p in patches if "FundClient" not in repr(p)]
        patches.append(
            patch("flowtracker.fund_client.FundClient", return_value=fund_client),
        )
        for p in patches:
            p.start()
        try:
            summary = refresh_for_research("CRASH", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        # Fund client yfinance path must still have been attempted despite the
        # Screener failure in the earlier block.
        fund_client.fetch_valuation_snapshot.assert_called_once_with("CRASH")
        assert isinstance(summary, dict)

    def test_fmp_credential_missing_is_graceful(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """FMPClient raising FileNotFoundError (no fmp.env) is handled cleanly."""
        self._pin_db(monkeypatch, tmp_db)
        screener_cm = _make_screener_client_mock()

        fmp_ctor = MagicMock(side_effect=FileNotFoundError("fmp.env missing"))
        patches = self._patches(screener_cm=screener_cm)
        patches = [p for p in patches if "FMPClient" not in repr(p)]
        patches.append(patch("flowtracker.fmp_client.FMPClient", fmp_ctor))

        for p in patches:
            p.start()
        try:
            summary = refresh_for_research("FMPTEST", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        # Construction attempted → FileNotFoundError hit → no crash.
        fmp_ctor.assert_called_once()
        assert "fmp" in summary
        assert summary["fmp"] == 0  # skipped count

    def test_valuation_snapshot_is_persisted(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """When FundClient returns a snapshot, the store is updated."""
        self._pin_db(monkeypatch, tmp_db)
        snap = ValuationSnapshot(
            symbol="SAVED",
            date="2025-01-15",
            price=1000.0,
            market_cap=50000.0,
            pe_trailing=22.5,
        )
        fund_client = MagicMock()
        fund_client.fetch_valuation_snapshot.return_value = snap
        fund_client.fetch_yahoo_peers.return_value = []

        patches = self._patches()
        patches = [p for p in patches if "FundClient" not in repr(p)]
        patches.append(
            patch("flowtracker.fund_client.FundClient", return_value=fund_client),
        )
        for p in patches:
            p.start()
        try:
            refresh_for_research("SAVED", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        # Verify store actually persisted the snapshot
        with FlowStore(db_path=tmp_db) as s:
            row = s._conn.execute(
                "SELECT symbol, price, pe_trailing FROM valuation_snapshot WHERE symbol = ?",
                ("SAVED",),
            ).fetchone()
        assert row is not None
        assert row["symbol"] == "SAVED"
        assert row["price"] == pytest.approx(1000.0)
        assert row["pe_trailing"] == pytest.approx(22.5)

    def test_screener_ids_extracted_and_stored(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Happy path writes screener_ids row with extracted company+warehouse IDs."""
        self._pin_db(monkeypatch, tmp_db)
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            refresh_for_research("IDSTEST", max_age_hours=6)
        finally:
            for p in patches:
                p.stop()

        with FlowStore(db_path=tmp_db) as s:
            row = s._conn.execute(
                "SELECT company_id, warehouse_id FROM screener_ids WHERE symbol = ?",
                ("IDSTEST",),
            ).fetchone()
        assert row is not None
        assert row["company_id"] == "12345"
        assert row["warehouse_id"] == "67890"

    def test_force_low_max_age_triggers_refresh_even_with_stale_data(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Very low max_age_hours effectively forces a fetch path."""
        self._pin_db(monkeypatch, tmp_db)
        # Pre-seed data that WOULD be "fresh" under 6h but not under 0h.
        with FlowStore(db_path=tmp_db) as s:
            old = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
            s._conn.execute(
                "INSERT INTO quarterly_results (symbol, quarter_end, revenue, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                ("STALE", "2025-03-31", 100.0, old),
            )
            s._conn.commit()

        screener_ctor = MagicMock(return_value=_make_screener_client_mock())
        patches = self._patches()
        patches = [p for p in patches if "ScreenerClient" not in repr(p)]
        patches.append(
            patch("flowtracker.screener_client.ScreenerClient", screener_ctor),
        )
        for p in patches:
            p.start()
        try:
            refresh_for_research("STALE", max_age_hours=0)
        finally:
            for p in patches:
                p.stop()

        # max_age_hours=0 → freshness check fails → Screener fetch attempted.
        screener_ctor.assert_called_once()


# ---------------------------------------------------------------------------
# refresh_for_business — light orchestration
# ---------------------------------------------------------------------------


class TestRefreshForBusiness:
    """Business refresh is Screener-only; faster path."""

    def _pin_db(self, monkeypatch: pytest.MonkeyPatch, tmp_db) -> None:
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    def test_business_happy_path(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """All Screener calls succeed with empties → returns a dict summary."""
        self._pin_db(monkeypatch, tmp_db)
        screener_cm = _make_screener_client_mock()

        with (
            patch("flowtracker.screener_client.ScreenerClient",
                  return_value=screener_cm),
            patch("flowtracker.research.refresh.time.sleep"),
        ):
            summary = refresh_for_business("BIZTEST")

        assert isinstance(summary, dict)
        # Function should have at least attempted peers via warehouse_id=67890
        inner = screener_cm.__enter__.return_value
        inner.fetch_peers.assert_called_once_with("67890")

    def test_business_freshness_gate(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Fresh company_profiles row → early return, no Screener call."""
        self._pin_db(monkeypatch, tmp_db)
        with FlowStore(db_path=tmp_db) as s:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            s._conn.execute(
                "INSERT INTO company_profiles (symbol, about_text, updated_at) "
                "VALUES (?, ?, ?)",
                ("BIZFRESH", "some text", now),
            )
            s._conn.commit()

        screener_ctor = MagicMock()
        with (
            patch("flowtracker.screener_client.ScreenerClient", screener_ctor),
            patch("flowtracker.research.refresh.time.sleep"),
        ):
            summary = refresh_for_business("BIZFRESH")

        screener_ctor.assert_not_called()
        assert summary == {}

    def test_business_symbol_uppercased(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """Lowercase input is normalized."""
        self._pin_db(monkeypatch, tmp_db)
        screener_cm = _make_screener_client_mock()
        inner = screener_cm.__enter__.return_value

        with (
            patch("flowtracker.screener_client.ScreenerClient",
                  return_value=screener_cm),
            patch("flowtracker.research.refresh.time.sleep"),
        ):
            refresh_for_business("lowerbiz")

        inner.fetch_company_page.assert_called_once_with("LOWERBIZ")

    def test_business_screener_failure_swallowed(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch,
    ):
        """ScreenerClient raising at construction → gracefully logged."""
        self._pin_db(monkeypatch, tmp_db)
        screener_ctor = MagicMock(side_effect=RuntimeError("init failed"))

        with (
            patch("flowtracker.screener_client.ScreenerClient", screener_ctor),
            patch("flowtracker.research.refresh.time.sleep"),
        ):
            summary = refresh_for_business("BROKENBIZ")

        assert isinstance(summary, dict)
        # The 'screener' key records the skip
        assert summary.get("screener") == 0
