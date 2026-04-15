"""Unit tests for flowtracker/mf_commands.py — CLI wiring for AMFI/SEBI MF data.

Mocks AMFIClient and SEBIClient at import site so no HTTP is performed.
Uses tmp_db + FLOWTRACKER_DB env to isolate writes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time
from typer.testing import CliRunner

from flowtracker.mf_client import AMFIFetchError
from flowtracker.mf_commands import app as mf_app
from flowtracker.mf_models import AMFIReportRow, MFAUMSummary, MFDailyFlow
from flowtracker.sebi_client import SEBIFetchError
from flowtracker.store import FlowStore

runner = CliRunner()


# -- Helpers ----------------------------------------------------------------

def _sample_rows() -> list[AMFIReportRow]:
    return [
        AMFIReportRow(
            category="Equity",
            sub_category="Large Cap Fund",
            num_schemes=35,
            funds_mobilized=15000.0,
            redemption=12000.0,
            net_flow=3000.0,
            aum=250000.0,
        ),
        AMFIReportRow(
            category="Debt",
            sub_category="Liquid Fund",
            num_schemes=40,
            funds_mobilized=22000.0,
            redemption=21000.0,
            net_flow=1000.0,
            aum=600000.0,
        ),
    ]


def _sample_summary(month: str = "2026-03") -> MFAUMSummary:
    return MFAUMSummary(
        month=month,
        total_aum=4500000.0,
        equity_aum=2500000.0,
        debt_aum=1200000.0,
        hybrid_aum=500000.0,
        other_aum=300000.0,
        equity_net_flow=25000.0,
        debt_net_flow=-5000.0,
        hybrid_net_flow=3000.0,
    )


def _make_amfi_mock(rows, summary):
    """Build a MagicMock that satisfies `with AMFIClient() as client: client.fetch_*(...)`."""
    instance = MagicMock()
    instance.fetch_monthly.return_value = (rows, summary)
    cm = MagicMock()
    cm.__enter__.return_value = instance
    cm.__exit__.return_value = None
    factory = MagicMock(return_value=cm)
    return factory, instance


def _make_amfi_range_mock(results):
    instance = MagicMock()
    instance.fetch_range.return_value = results
    cm = MagicMock()
    cm.__enter__.return_value = instance
    cm.__exit__.return_value = None
    factory = MagicMock(return_value=cm)
    return factory, instance


def _make_sebi_mock(flows):
    instance = MagicMock()
    instance.fetch_daily.return_value = flows
    cm = MagicMock()
    cm.__enter__.return_value = instance
    cm.__exit__.return_value = None
    factory = MagicMock(return_value=cm)
    return factory, instance


# -- fetch ------------------------------------------------------------------

class TestFetch:
    def test_fetch_explicit_month_year(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        rows = _sample_rows()
        summary = _sample_summary("2026-03")
        factory, instance = _make_amfi_mock(rows, summary)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(mf_app, ["fetch", "--month", "3", "--year", "2026"])

        assert result.exit_code == 0, result.output
        instance.fetch_monthly.assert_called_once_with(2026, 3)

        # Persisted to store
        with FlowStore(db_path=tmp_db) as s:
            latest = s.get_mf_latest_aum()
        assert latest is not None
        assert latest.month == "2026-03"

    @freeze_time("2026-04-15")
    def test_fetch_default_uses_previous_month(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        rows = _sample_rows()
        summary = _sample_summary("2026-03")
        factory, instance = _make_amfi_mock(rows, summary)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(mf_app, ["fetch"])

        assert result.exit_code == 0, result.output
        # Frozen at 2026-04-15 -> default is previous month: year=2026, month=3
        instance.fetch_monthly.assert_called_once_with(2026, 3)

    @freeze_time("2026-01-10")
    def test_fetch_default_january_rolls_back_year(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        rows = _sample_rows()
        summary = _sample_summary("2025-12")
        factory, instance = _make_amfi_mock(rows, summary)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(mf_app, ["fetch"])

        assert result.exit_code == 0, result.output
        instance.fetch_monthly.assert_called_once_with(2025, 12)

    def test_fetch_amfi_error_exits_1(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        instance = MagicMock()
        instance.fetch_monthly.side_effect = AMFIFetchError("boom")
        cm = MagicMock()
        cm.__enter__.return_value = instance
        cm.__exit__.return_value = None
        factory = MagicMock(return_value=cm)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(mf_app, ["fetch", "--month", "3", "--year", "2026"])

        assert result.exit_code == 1
        assert "boom" in result.output


# -- backfill ---------------------------------------------------------------

class TestBackfill:
    def test_backfill_three_months(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        results = [
            (_sample_rows(), _sample_summary("2019-04")),
            (_sample_rows(), _sample_summary("2019-05")),
            (_sample_rows(), _sample_summary("2019-06")),
        ]
        factory, instance = _make_amfi_range_mock(results)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(
                mf_app, ["backfill", "--from", "2019-04", "--to", "2019-06"]
            )

        assert result.exit_code == 0, result.output
        instance.fetch_range.assert_called_once_with(2019, 4, 2019, 6)
        assert "Backfill complete" in result.output
        assert "3 months" in result.output

    def test_backfill_invalid_from_format_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # No HTTP should happen; date parse fails first.
        result = runner.invoke(mf_app, ["backfill", "--from", "abc", "--to", "2019-06"])
        assert result.exit_code == 1
        assert "Invalid month format" in result.output

    def test_backfill_empty_results_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        factory, instance = _make_amfi_range_mock([])

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(
                mf_app, ["backfill", "--from", "2019-04", "--to", "2019-06"]
            )

        assert result.exit_code == 1
        assert "No data fetched" in result.output

    @freeze_time("2026-04-15")
    def test_backfill_default_to_uses_previous_month(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        results = [(_sample_rows(), _sample_summary("2019-04"))]
        factory, instance = _make_amfi_range_mock(results)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(mf_app, ["backfill", "--from", "2019-04"])

        assert result.exit_code == 0, result.output
        # Default end = previous month from 2026-04-15 -> 2026-03
        instance.fetch_range.assert_called_once_with(2019, 4, 2026, 3)

    def test_backfill_amfi_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        instance = MagicMock()
        instance.fetch_range.side_effect = AMFIFetchError("network down")
        cm = MagicMock()
        cm.__enter__.return_value = instance
        cm.__exit__.return_value = None
        factory = MagicMock(return_value=cm)

        with patch("flowtracker.mf_commands.AMFIClient", factory):
            result = runner.invoke(
                mf_app, ["backfill", "--from", "2019-04", "--to", "2019-06"]
            )

        assert result.exit_code == 1
        assert "network down" in result.output


# -- summary / flows / aum (read-only) --------------------------------------

class TestSummary:
    def test_summary_populated(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["summary"])
        assert result.exit_code == 0

    def test_summary_empty_exits_1(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["summary"])
        assert result.exit_code == 1
        assert "No MF data available" in result.output


class TestFlows:
    def test_flows_default_period(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["flows"])
        assert result.exit_code == 0

    def test_flows_with_category_filter(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["flows", "-p", "6m", "-c", "Equity"])
        assert result.exit_code == 0

    def test_flows_period_no_suffix(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Period parser also accepts plain int
        result = runner.invoke(mf_app, ["flows", "-p", "12"])
        assert result.exit_code == 0

    def test_flows_invalid_period_exits_1(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["flows", "-p", "abc"])
        assert result.exit_code == 1
        assert "Invalid period" in result.output


class TestAum:
    def test_aum_populated(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["aum"])
        assert result.exit_code == 0

    def test_aum_empty_store(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["aum"])
        # display gracefully prints "No AUM trend data available." and returns
        assert result.exit_code == 0
        assert "No AUM trend data available" in result.output


# -- daily fetch / summary / trend -----------------------------------------

class TestDailyFetch:
    def test_daily_fetch_happy_path(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        flows = [
            MFDailyFlow(
                date="2026-04-01",
                category="Equity",
                gross_purchase=5000.0,
                gross_sale=4200.0,
                net_investment=800.0,
            ),
            MFDailyFlow(
                date="2026-04-01",
                category="Debt",
                gross_purchase=3000.0,
                gross_sale=3500.0,
                net_investment=-500.0,
            ),
        ]
        factory, instance = _make_sebi_mock(flows)

        with patch("flowtracker.mf_commands.SEBIClient", factory):
            result = runner.invoke(mf_app, ["daily", "fetch"])

        assert result.exit_code == 0, result.output
        assert "Fetched 2 records" in result.output
        instance.fetch_daily.assert_called_once_with()

    def test_daily_fetch_empty_exits_1(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        factory, _ = _make_sebi_mock([])

        with patch("flowtracker.mf_commands.SEBIClient", factory):
            result = runner.invoke(mf_app, ["daily", "fetch"])

        assert result.exit_code == 1
        assert "No daily MF data" in result.output

    def test_daily_fetch_sebi_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        instance = MagicMock()
        instance.fetch_daily.side_effect = SEBIFetchError("sebi bad")
        cm = MagicMock()
        cm.__enter__.return_value = instance
        cm.__exit__.return_value = None
        factory = MagicMock(return_value=cm)

        with patch("flowtracker.mf_commands.SEBIClient", factory):
            result = runner.invoke(mf_app, ["daily", "fetch"])

        assert result.exit_code == 1
        assert "sebi bad" in result.output


class TestDailySummary:
    def test_daily_summary_populated(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["daily", "summary"])
        assert result.exit_code == 0

    def test_daily_summary_empty(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["daily", "summary"])
        assert result.exit_code == 0
        assert "No daily MF data available" in result.output


class TestDailyTrend:
    def test_daily_trend_populated(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["daily", "trend", "-d", "10"])
        assert result.exit_code == 0

    def test_daily_trend_empty(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(mf_app, ["daily", "trend"])
        assert result.exit_code == 0
        assert "No daily MF trend data" in result.output
