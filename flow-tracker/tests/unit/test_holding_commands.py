"""CLI tests for `flowtracker.holding_commands` (the `flowtrack holding ...` group).

Covers all 7 subcommands: add, remove, list, fetch, show, changes, shareholders.

External clients are mocked at the import site inside `holding_commands`:
    - flowtracker.holding_commands.NSEHoldingClient   (used by `fetch`)
    - flowtracker.holding_commands.ScreenerClient     (used by `shareholders`)

Both are used as context managers (`with X() as inst`) so the mocks are
shaped accordingly via `__enter__`/`__exit__`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from flowtracker.holding_client import NSEHoldingError
from flowtracker.holding_models import PromoterPledge, ShareholdingRecord
from flowtracker.main import app
from flowtracker.screener_client import ScreenerError
from flowtracker.store import FlowStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cm_mock(inner: MagicMock) -> MagicMock:
    """Wrap an instance MagicMock in a context-manager mock (`with X() as i`)."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _sample_records(symbol: str = "SBIN", quarter: str = "2025-12-31") -> list[ShareholdingRecord]:
    return [
        ShareholdingRecord(symbol=symbol, quarter_end=quarter, category="Promoter", percentage=57.5),
        ShareholdingRecord(symbol=symbol, quarter_end=quarter, category="FII", percentage=11.2),
        ShareholdingRecord(symbol=symbol, quarter_end=quarter, category="MF", percentage=7.8),
        ShareholdingRecord(symbol=symbol, quarter_end=quarter, category="Public", percentage=23.5),
    ]


def _sample_pledges(symbol: str = "SBIN") -> list[PromoterPledge]:
    return [PromoterPledge(symbol=symbol, quarter_end="2025-12-31", pledge_pct=2.5, encumbered_pct=3.1)]


# ---------------------------------------------------------------------------
# add / remove / list (no client mocking required — store-only)
# ---------------------------------------------------------------------------


class TestAddCommand:
    def test_add_single_symbol(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "add", "sbin"])
        assert result.exit_code == 0
        assert "SBIN" in result.output

        # Verify it actually landed in the watchlist (uppercased).
        with FlowStore(db_path=tmp_db) as s:
            entries = s.get_watchlist()
        symbols = {e.symbol for e in entries}
        assert "SBIN" in symbols

    def test_add_multiple_symbols(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "add", "RELIANCE", "TCS", "INFY"])
        assert result.exit_code == 0
        assert "Added 3 symbol(s)" in result.output

        with FlowStore(db_path=tmp_db) as s:
            symbols = {e.symbol for e in s.get_watchlist()}
        assert {"RELIANCE", "TCS", "INFY"}.issubset(symbols)


class TestRemoveCommand:
    def test_remove_symbol(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # populated_store seeds SBIN + INFY into the watchlist.
        result = runner.invoke(app, ["holding", "remove", "sbin"])
        assert result.exit_code == 0
        assert "Removed SBIN" in result.output

        with FlowStore(db_path=tmp_db) as s:
            symbols = {e.symbol for e in s.get_watchlist()}
        assert "SBIN" not in symbols


class TestListCommand:
    def test_list_with_entries(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "list"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "INFY" in result.output

    def test_list_empty(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "list"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()


# ---------------------------------------------------------------------------
# fetch — mocks NSEHoldingClient
# ---------------------------------------------------------------------------


class TestFetchCommand:
    def test_fetch_single_symbol(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """`fetch -s SBIN -q 4` calls the client and stores the returned records."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        client_inner = MagicMock()
        client_inner.fetch_latest_quarters.return_value = (
            _sample_records("SBIN"),
            _sample_pledges("SBIN"),
        )
        with patch(
            "flowtracker.holding_commands.NSEHoldingClient",
            return_value=_cm_mock(client_inner),
        ):
            result = runner.invoke(app, ["holding", "fetch", "--symbol", "sbin", "--quarters", "4"])

        assert result.exit_code == 0, result.output
        client_inner.fetch_latest_quarters.assert_called_once_with("SBIN", 4)

        # The records should have been persisted via store.upsert_shareholding.
        with FlowStore(db_path=tmp_db) as s:
            saved = s.get_shareholding("SBIN", limit=8)
        assert len(saved) == 4

    def test_fetch_uses_watchlist_when_no_symbol(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """No --symbol → iterate every watchlist entry."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Seed two symbols into the watchlist.
        with FlowStore(db_path=tmp_db) as s:
            s.add_to_watchlist("RELIANCE")
            s.add_to_watchlist("HDFCBANK")

        client_inner = MagicMock()
        client_inner.fetch_latest_quarters.side_effect = [
            (_sample_records("RELIANCE"), []),
            (_sample_records("HDFCBANK"), []),
        ]
        with patch(
            "flowtracker.holding_commands.NSEHoldingClient",
            return_value=_cm_mock(client_inner),
        ):
            result = runner.invoke(app, ["holding", "fetch"])

        assert result.exit_code == 0, result.output
        called_syms = [c.args[0] for c in client_inner.fetch_latest_quarters.call_args_list]
        assert set(called_syms) == {"RELIANCE", "HDFCBANK"}

    def test_fetch_empty_watchlist_exits_1(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """No --symbol and no watchlist entries → exit 1 with a yellow hint."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "fetch"])
        assert result.exit_code == 1
        assert "empty" in result.output.lower()

    def test_fetch_handles_per_symbol_error(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """A NSEHoldingError on a per-symbol fetch is caught and reported, exit 0."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        client_inner = MagicMock()
        client_inner.fetch_latest_quarters.side_effect = NSEHoldingError("boom")
        with patch(
            "flowtracker.holding_commands.NSEHoldingClient",
            return_value=_cm_mock(client_inner),
        ):
            result = runner.invoke(app, ["holding", "fetch", "-s", "BADSYM"])

        assert result.exit_code == 0
        assert "Error fetching BADSYM" in result.output

    def test_fetch_no_records_warns(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """Empty records list prints a 'No data' warning, exit 0."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        client_inner = MagicMock()
        client_inner.fetch_latest_quarters.return_value = ([], [])
        with patch(
            "flowtracker.holding_commands.NSEHoldingClient",
            return_value=_cm_mock(client_inner),
        ):
            result = runner.invoke(app, ["holding", "fetch", "-s", "EMPTY"])

        assert result.exit_code == 0
        assert "No data for EMPTY" in result.output

    def test_fetch_client_construction_error_exits_1(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """An NSEHoldingError raised by the outer `with NSEHoldingClient()` block exits 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Seed watchlist so the function reaches the outer try/except.
        with FlowStore(db_path=tmp_db) as s:
            s.add_to_watchlist("SBIN")

        # __enter__ raises — simulating cookie-acquire failure or similar.
        cm = MagicMock()
        cm.__enter__ = MagicMock(side_effect=NSEHoldingError("cookie failure"))
        cm.__exit__ = MagicMock(return_value=False)
        with patch("flowtracker.holding_commands.NSEHoldingClient", return_value=cm):
            result = runner.invoke(app, ["holding", "fetch"])

        assert result.exit_code == 1
        assert "cookie failure" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


class TestShowCommand:
    def test_show_with_data(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "show", "sbin"])
        assert result.exit_code == 0
        assert "SBIN" in result.output

    def test_show_no_data(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """Symbol with no shareholding rows → graceful 'No shareholding data' message."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "show", "ZZZ"])
        assert result.exit_code == 0
        assert "ZZZ" in result.output


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------


class TestChangesCommand:
    def test_changes_with_category_filter(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "changes", "--category", "FII", "--limit", "5"])
        assert result.exit_code == 0

    def test_changes_default(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "changes"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# shareholders — mocks ScreenerClient
# ---------------------------------------------------------------------------


class TestShareholdersCommand:
    def _shareholders_payload(self) -> dict[str, list[dict]]:
        return {
            "promoters": [
                {"name": "Promoter Co A", "values": {"Dec 2025": "55.00", "Sep 2025": "55.00"}},
            ],
            "foreign_institutions": [
                {"name": "Foreign Fund X", "values": {"Dec 2025": "8.50"}},
            ],
            "domestic_institutions": [],
            "public": [],
        }

    def test_shareholders_happy_path_uses_cached_ids(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """When screener_ids are cached, `_get_both_ids` is NOT called."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Pre-populate the screener_ids cache so the network branch is skipped.
        with FlowStore(db_path=tmp_db) as s:
            s.upsert_screener_ids("SBIN", "12345", "67890")

        sc_inner = MagicMock()
        sc_inner.fetch_shareholders.return_value = self._shareholders_payload()
        with patch(
            "flowtracker.holding_commands.ScreenerClient",
            return_value=_cm_mock(sc_inner),
        ):
            result = runner.invoke(
                app, ["holding", "shareholders", "-s", "sbin"]
            )

        assert result.exit_code == 0, result.output
        sc_inner.fetch_shareholders.assert_called_once_with("12345")
        sc_inner._get_both_ids.assert_not_called()
        assert "Stored" in result.output

        # Verify rows were persisted to the shareholder_detail table.
        with FlowStore(db_path=tmp_db) as s:
            details = s.get_shareholder_details("SBIN")
        assert len(details) > 0

    def test_shareholders_fetches_ids_when_not_cached(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No cached ids → `_get_both_ids` is called and the result is cached."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        sc_inner = MagicMock()
        sc_inner._get_both_ids.return_value = ("99999", "11111")
        sc_inner.fetch_shareholders.return_value = self._shareholders_payload()
        with patch(
            "flowtracker.holding_commands.ScreenerClient",
            return_value=_cm_mock(sc_inner),
        ):
            result = runner.invoke(app, ["holding", "shareholders", "-s", "RELIANCE"])

        assert result.exit_code == 0, result.output
        sc_inner._get_both_ids.assert_called_once_with("RELIANCE")
        sc_inner.fetch_shareholders.assert_called_once_with("99999")

        with FlowStore(db_path=tmp_db) as s:
            cached = s.get_screener_ids("RELIANCE")
        assert cached == ("99999", "11111")

    def test_shareholders_with_classification_filter(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with FlowStore(db_path=tmp_db) as s:
            s.upsert_screener_ids("SBIN", "12345", "67890")

        sc_inner = MagicMock()
        sc_inner.fetch_shareholders.return_value = self._shareholders_payload()
        with patch(
            "flowtracker.holding_commands.ScreenerClient",
            return_value=_cm_mock(sc_inner),
        ):
            result = runner.invoke(
                app,
                ["holding", "shareholders", "-s", "SBIN", "-c", "promoters"],
            )

        assert result.exit_code == 0, result.output

    def test_shareholders_empty_payload_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """All-empty `data.values()` → 'No shareholder data returned' + exit 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with FlowStore(db_path=tmp_db) as s:
            s.upsert_screener_ids("SBIN", "12345", "67890")

        sc_inner = MagicMock()
        sc_inner.fetch_shareholders.return_value = {
            "promoters": [],
            "foreign_institutions": [],
            "domestic_institutions": [],
            "public": [],
        }
        with patch(
            "flowtracker.holding_commands.ScreenerClient",
            return_value=_cm_mock(sc_inner),
        ):
            result = runner.invoke(app, ["holding", "shareholders", "-s", "SBIN"])

        assert result.exit_code == 1
        assert "No shareholder data" in result.output

    def test_shareholders_screener_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """A ScreenerError raised inside the `with` block exits 1 with the message."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with FlowStore(db_path=tmp_db) as s:
            s.upsert_screener_ids("SBIN", "12345", "67890")

        sc_inner = MagicMock()
        sc_inner.fetch_shareholders.side_effect = ScreenerError("rate limited")
        with patch(
            "flowtracker.holding_commands.ScreenerClient",
            return_value=_cm_mock(sc_inner),
        ):
            result = runner.invoke(app, ["holding", "shareholders", "-s", "SBIN"])

        assert result.exit_code == 1
        assert "rate limited" in result.output
