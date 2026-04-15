"""CLI tests for ``flowtracker.portfolio_commands``.

Covers all 5 subcommands (``add``, ``remove``, ``view``, ``concentration``,
``summary``) via ``CliRunner`` against a real on-disk SQLite store. No HTTP
mocking is required — every code path goes store → display only.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flowtracker.main import app
from flowtracker.store import FlowStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestPortfolioAdd:
    """`flowtrack portfolio add` — create or update a holding."""

    def test_add_creates_holding(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """A successful add stores the holding and prints confirmation."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(
            app,
            ["portfolio", "add", "tcs", "--qty", "10", "--cost", "3500.0"],
        )
        assert result.exit_code == 0
        assert "TCS" in result.output  # symbol is uppercased before display

        # Re-open the store and confirm persistence.
        store.close()
        with FlowStore(db_path=tmp_db) as fresh:
            holdings = fresh.get_portfolio_holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "TCS"
        assert holdings[0].quantity == 10
        assert holdings[0].avg_cost == 3500.0

    def test_add_with_optional_flags(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """Optional --date and --notes flags are persisted on the holding."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(
            app,
            [
                "portfolio", "add", "WIPRO",
                "--qty", "25", "--cost", "450",
                "--date", "2026-01-15",
                "--notes", "IT diversification",
            ],
        )
        assert result.exit_code == 0

        store.close()
        with FlowStore(db_path=tmp_db) as fresh:
            holdings = fresh.get_portfolio_holdings()
        assert holdings[0].buy_date == "2026-01-15"
        assert holdings[0].notes == "IT diversification"

    def test_add_missing_required_qty(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """Omitting --qty/--cost yields a non-zero exit (Typer usage error)."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "add", "TCS"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestPortfolioRemove:
    """`flowtrack portfolio remove` — delete an existing holding."""

    def test_remove_existing(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Removing a known holding succeeds and shows a confirmation."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "remove", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output

        # And it is actually gone from the store.
        populated_store.close()
        with FlowStore(db_path=tmp_db) as fresh:
            symbols = {h.symbol for h in fresh.get_portfolio_holdings()}
        assert "SBIN" not in symbols

    def test_remove_missing_symbol_prints_warning(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """Removing an unknown symbol exits 0 but prints a yellow warning."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "remove", "NOPE"])
        # Source uses a console.print warning, not typer.Exit, so exit is 0.
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------


class TestPortfolioView:
    """`flowtrack portfolio view` — list holdings with CMP and P&L."""

    def test_view_empty_portfolio_exits_nonzero(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """An empty portfolio prints a hint and exits 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "view"])
        assert result.exit_code == 1
        assert "no holdings" in result.output.lower()

    def test_view_populated_portfolio(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """Populated store renders both fixture symbols in the table."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "view"])
        assert result.exit_code == 0
        assert "SBIN" in result.output
        assert "INFY" in result.output


# ---------------------------------------------------------------------------
# concentration
# ---------------------------------------------------------------------------


class TestPortfolioConcentration:
    """`flowtrack portfolio concentration` — sector weight breakdown."""

    def test_concentration_empty_exits_nonzero(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No holdings → exit code 1 with a yellow message."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "concentration"])
        assert result.exit_code == 1
        assert "no holdings" in result.output.lower()

    def test_concentration_multi_sector(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """Two fixture holdings span Banks (SBIN) and IT (INFY) sectors."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "concentration"])
        assert result.exit_code == 0
        # Both fixture sectors should appear.
        assert "Banks" in result.output
        assert "IT" in result.output
        # Sector concentration table title is rendered.
        assert "Sector" in result.output

    def test_concentration_unknown_sector_for_orphan_symbol(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """A holding without an index_constituents row falls into 'Unknown'."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Add a holding for a symbol that has no constituent row.
        result = runner.invoke(
            app,
            ["portfolio", "add", "ZZNEW", "--qty", "5", "--cost", "100.0"],
        )
        assert result.exit_code == 0

        result = runner.invoke(app, ["portfolio", "concentration"])
        assert result.exit_code == 0
        assert "Unknown" in result.output


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestPortfolioSummary:
    """`flowtrack portfolio summary` — invested, P&L, top gainer/loser."""

    def test_summary_empty_exits_nonzero(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No holdings → exit code 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "summary"])
        assert result.exit_code == 1
        assert "no holdings" in result.output.lower()

    def test_summary_with_pnl(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """Populated store renders Holdings, Total Invested and a P&L line."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["portfolio", "summary"])
        assert result.exit_code == 0
        assert "Holdings" in result.output
        assert "Invested" in result.output
        # With 2 fixture holdings + valuation snapshots, P&L block renders
        # along with top gainer/loser annotations.
        assert "P&L" in result.output
        assert "Top Gainer" in result.output
        assert "Top Loser" in result.output

    def test_summary_no_price_data_falls_back_to_invested(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """Without valuation snapshots the value defaults to invested cost."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Seed a holding directly so no valuation_snapshot row exists.
        result = runner.invoke(
            app,
            ["portfolio", "add", "TCS", "--qty", "10", "--cost", "3000.0"],
        )
        assert result.exit_code == 0

        result = runner.invoke(app, ["portfolio", "summary"])
        assert result.exit_code == 0
        # Total Invested should equal 30000 (10 * 3000).
        assert "30,000" in result.output
        # No top gainer/loser block when there is no live price data.
        assert "Top Gainer" not in result.output
