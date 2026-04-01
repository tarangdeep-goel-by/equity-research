"""Extended CLI command integration tests.

Uses CliRunner to invoke read-only commands against populated_store.
All commands use FLOWTRACKER_DB env var to point to the tmp database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flowtracker.main import app
from flowtracker.store import FlowStore

runner = CliRunner()


def _run(tmp_db, populated_store, monkeypatch, args: list[str]):
    """Helper: set env, invoke command, return result."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Gold / Commodity commands
# ---------------------------------------------------------------------------


class TestGoldCommands:
    def test_gold_prices(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["gold", "prices"])
        assert result.exit_code == 0
        assert "Gold" in result.output or len(result.output) > 10

    def test_gold_etfs(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["gold", "etfs"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Macro commands
# ---------------------------------------------------------------------------


class TestMacroCommands:
    def test_macro_summary(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["macro", "summary"])
        assert result.exit_code == 0
        assert "VIX" in result.output or "Macro" in result.output

    def test_macro_trend(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["macro", "trend"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Insider commands
# ---------------------------------------------------------------------------


class TestInsiderCommands:
    def test_insider_stock(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["insider", "stock", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Insider" in result.output

    def test_insider_promoter_buys(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["insider", "promoter-buys"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Deals commands
# ---------------------------------------------------------------------------


class TestDealsCommands:
    def test_deals_summary(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["deals", "summary"])
        assert result.exit_code == 0

    def test_deals_stock(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["deals", "stock", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Deal" in result.output


# ---------------------------------------------------------------------------
# Estimates commands
# ---------------------------------------------------------------------------


class TestEstimatesCommands:
    def test_estimates_stock(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["estimates", "stock", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Target" in result.output

    def test_estimates_upside(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["estimates", "upside"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# FMP commands
# ---------------------------------------------------------------------------


class TestFMPCommands:
    def test_fmp_dcf(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["fmp", "dcf", "-s", "SBIN"])
        assert result.exit_code == 0
        assert "DCF" in result.output or "Intrinsic" in result.output

    def test_fmp_technicals(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["fmp", "technicals", "-s", "SBIN"])
        assert result.exit_code == 0
        assert "RSI" in result.output or "SMA" in result.output or "Technical" in result.output


# ---------------------------------------------------------------------------
# Holding commands
# ---------------------------------------------------------------------------


class TestHoldingCommands:
    def test_holding_show(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["holding", "show", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Promoter" in result.output

    def test_holding_changes(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["holding", "changes"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# MF Portfolio commands
# ---------------------------------------------------------------------------


class TestMFPortCommands:
    def test_mfport_stock(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["mfport", "stock", "SBIN"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Sector commands
# ---------------------------------------------------------------------------


class TestSectorCommands:
    def test_sector_overview(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["sector", "overview"])
        assert result.exit_code == 0

    def test_sector_list(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["sector", "list"])
        assert result.exit_code == 0

    def test_sector_detail(self, tmp_db, populated_store, monkeypatch):
        # Use "Banks" which matches SBIN's industry in the fixture data
        result = _run(tmp_db, populated_store, monkeypatch, ["sector", "detail", "Banks"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Screen commands
# ---------------------------------------------------------------------------


class TestScreenCommands:
    def test_screen_score(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["screen", "score", "SBIN"])
        # exit_code 0 = score found, 1 = no data (both acceptable)
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Research data commands
# ---------------------------------------------------------------------------


class TestResearchDataCommands:
    def test_research_data_quarterly_results(self, tmp_db, populated_store, monkeypatch):
        result = _run(
            tmp_db, populated_store, monkeypatch,
            ["research", "data", "quarterly_results", "-s", "SBIN"],
        )
        assert result.exit_code == 0
        # Output is JSON — should contain revenue or quarter data
        assert "revenue" in result.output.lower() or "quarter" in result.output.lower() or "{" in result.output


# ---------------------------------------------------------------------------
# Bhavcopy commands
# ---------------------------------------------------------------------------


class TestBhavcopyCommands:
    def test_bhavcopy_delivery(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["bhavcopy", "delivery", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Delivery" in result.output


# ---------------------------------------------------------------------------
# Fund commands
# ---------------------------------------------------------------------------


class TestFundCommands:
    def test_fund_history(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["fund", "history", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output or "Quarter" in result.output

    def test_fund_valuation(self, tmp_db, populated_store, monkeypatch):
        result = _run(tmp_db, populated_store, monkeypatch, ["fund", "valuation", "SBIN"])
        assert result.exit_code == 0
