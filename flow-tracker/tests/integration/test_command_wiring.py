"""Integration tests: CLI command → store → display wiring.

Uses CliRunner to invoke read-only commands against populated_store.
Verifies exit codes and output content — no HTTP mocking needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowtracker.main import app
from flowtracker.store import FlowStore

runner = CliRunner()


class TestSummaryCommand:
    def test_summary_shows_fii_dii(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["summary"])
        assert result.exit_code == 0
        assert "FII" in result.output or "DII" in result.output

    def test_summary_empty_store(self, tmp_db: Path, store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["summary"])
        assert result.exit_code == 1


class TestFlowsCommand:
    def test_flows_default_period(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["flows", "-p", "7d"])
        assert result.exit_code == 0

    def test_flows_invalid_period(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["flows", "-p", "abc"])
        assert result.exit_code == 1


class TestStreakCommand:
    def test_streak_shows_direction(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["streak"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "buying" in output_lower or "selling" in output_lower


class TestScreenTopCommand:
    def test_screen_top_watchlist(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["screen", "top", "--watchlist"])
        assert result.exit_code == 0


class TestPortfolioViewCommand:
    def test_portfolio_view(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "view"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "INFY" in result.output


class TestAlertListCommand:
    def test_alert_list(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["alert", "list"])
        assert result.exit_code == 0


class TestMFSummaryCommand:
    def test_mf_summary(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["mf", "summary"])
        assert result.exit_code == 0


class TestHoldingListCommand:
    def test_holding_list(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["holding", "list"])
        assert result.exit_code == 0
