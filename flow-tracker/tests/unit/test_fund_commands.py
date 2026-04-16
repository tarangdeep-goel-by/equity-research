"""CLI tests for ``flowtracker.fund_commands``.

Exercises every subcommand of ``flowtrack fund`` against a real on-disk
SQLite store, with ``FundClient`` and ``ScreenerClient`` patched at their
``fund_commands`` import sites.

* ``FundClient`` is a plain class — patched as a class, instantiation returns
  the mock instance.
* ``ScreenerClient`` is used as a context manager (``with ScreenerClient() as
  sc:``) — wrapped accordingly.
* ``time.sleep`` is patched to keep the suite fast (backfill sleeps 3s/symbol).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from flowtracker.fund_client import YFinanceError
from flowtracker.fund_models import (
    AnnualEPS,
    AnnualFinancials,
    LiveSnapshot,
    QuarterlyResult,
    ScreenerRatios,
    ValuationSnapshot,
)
from flowtracker.main import app
from flowtracker.screener_client import ScreenerError
from flowtracker.store import FlowStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_live_snapshot(symbol: str = "SBIN", sector: str = "Financial Services") -> LiveSnapshot:
    return LiveSnapshot(
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector=sector,
        industry="Banks",
        price=820.0,
        market_cap=7_300_000_000_000,
        pe_trailing=9.5,
        pe_forward=8.0,
        pb_ratio=1.8,
        ev_ebitda=6.5,
        roe=18.0,
        debt_to_equity=0.5,
    )


def _make_valuation_snapshot(symbol: str = "SBIN") -> ValuationSnapshot:
    return ValuationSnapshot(
        symbol=symbol,
        date="2026-04-15",
        price=820.0,
        market_cap=730_000.0,
        pe_trailing=9.5,
    )


def _make_fund_client_mock(
    *,
    live: LiveSnapshot | None = None,
    snapshot: ValuationSnapshot | None = None,
    historical_pe: list[ValuationSnapshot] | None = None,
    snapshot_error: Exception | None = None,
    live_error: Exception | None = None,
) -> MagicMock:
    """Build a plain (non-CM) FundClient mock with safe defaults."""
    client = MagicMock()
    if live_error is not None:
        client.get_live_snapshot.side_effect = live_error
    else:
        client.get_live_snapshot.return_value = live or _make_live_snapshot()
    if snapshot_error is not None:
        client.fetch_valuation_snapshot.side_effect = snapshot_error
    else:
        client.fetch_valuation_snapshot.return_value = snapshot or _make_valuation_snapshot()
    client.compute_historical_pe.return_value = historical_pe or []
    return client


def _make_screener_cm_mock(
    *,
    company_id: str = "12345",
    warehouse_id: str = "67890",
    quarters: list[QuarterlyResult] | None = None,
    annual: list[AnnualEPS] | None = None,
    annual_fin: list[AnnualFinancials] | None = None,
    ratios: list[ScreenerRatios] | None = None,
    chart_datasets: list[dict] | None = None,
    peers: list[dict] | None = None,
    schedules: dict | None = None,
    fetch_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Return ``(cm, inner)`` — cm acts as the patched ``ScreenerClient``
    class, ``cm()`` returns a context-manager whose ``__enter__`` yields
    ``inner`` (the actual client mock).
    """
    inner = MagicMock()
    inner._get_both_ids.return_value = (company_id, warehouse_id)
    inner.fetch_company_page.return_value = "<html></html>"
    inner.parse_quarterly_from_html.return_value = quarters or []
    inner.download_excel.return_value = b""
    inner.parse_annual_eps.return_value = annual or []
    inner.parse_annual_financials.return_value = annual_fin or []
    inner.parse_ratios_from_html.return_value = ratios or []
    inner.parse_quarterly_results.return_value = quarters or []
    inner.fetch_chart_data_by_type.return_value = {"datasets": chart_datasets or []}
    inner.fetch_peers.return_value = peers or []
    inner.fetch_schedules.return_value = schedules or {}
    inner.fetch_all_with_annual.return_value = (
        quarters or [],
        annual or [],
        annual_fin or [],
    )
    if fetch_error is not None:
        # Fail at the first call so the backfill aborts cleanly.
        inner.fetch_company_page.side_effect = fetch_error

    cm_instance = MagicMock()
    cm_instance.__enter__ = MagicMock(return_value=inner)
    cm_instance.__exit__ = MagicMock(return_value=False)
    cls = MagicMock(return_value=cm_instance)
    return cls, inner


@pytest.fixture(autouse=True)
def _no_sleep():
    """Globally stub ``time.sleep`` so backfill rate-limit waits don't slow tests."""
    with patch("flowtracker.fund_commands.time.sleep"):
        yield


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


class TestFundFetch:
    """`flowtrack fund fetch` — yfinance valuation snapshot, single & bulk."""

    def test_fetch_single_symbol_persists(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock()
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(app, ["fund", "fetch", "-s", "sbin"])

        assert result.exit_code == 0, result.output
        assert "Done" in result.output
        client.fetch_valuation_snapshot.assert_called_once_with("SBIN")

    def test_fetch_no_scanner_symbols_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No -s and no scanner constituents → exit 1 with hint."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with patch("flowtracker.fund_commands.FundClient") as fc:
            result = runner.invoke(app, ["fund", "fetch"])
        assert result.exit_code == 1
        assert "scan refresh" in result.output
        fc.assert_not_called()

    def test_fetch_yfinance_error_continues(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """A YFinanceError on a single symbol is reported and not fatal."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock(snapshot_error=YFinanceError("network"))
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(app, ["fund", "fetch", "-s", "SBIN"])
        assert result.exit_code == 0
        assert "SBIN" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


class TestFundShow:
    """`flowtrack fund show` — live yfinance snapshot, no storage."""

    def test_show_renders_live_snapshot(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock()
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(app, ["fund", "show", "sbin"])
        assert result.exit_code == 0
        client.get_live_snapshot.assert_called_once_with("SBIN")

    def test_show_yfinance_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock(live_error=YFinanceError("no data for ZZZZ"))
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(app, ["fund", "show", "ZZZZ"])
        assert result.exit_code == 1
        assert "ZZZZ" in result.output or "no data" in result.output


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


class TestFundHistory:
    """`flowtrack fund history` — read quarterly results from store."""

    def test_history_with_populated_store(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "history", "sbin"])
        assert result.exit_code == 0

    def test_history_custom_quarters(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "history", "sbin", "-q", "4"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------


class TestFundValuation:
    """`flowtrack fund valuation` — display valuation bands from store."""

    def test_valuation_default_period(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "valuation", "sbin"])
        assert result.exit_code == 0

    def test_valuation_invalid_period_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "valuation", "SBIN", "--period", "10y"])
        assert result.exit_code == 1
        assert "Invalid period" in result.output

    def test_valuation_1y_period_runs(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "valuation", "SBIN", "--period", "1y"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# peers
# ---------------------------------------------------------------------------


class TestFundPeers:
    """`flowtrack fund peers` — live peer comparison via FundClient."""

    def test_peers_explicit_with_flag(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """`--with` skips the sector-detection branch entirely."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock()
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(
                app, ["fund", "peers", "sbin", "--with", "TCS,INFY"]
            )
        assert result.exit_code == 0
        # Three live snapshots: SBIN + 2 peers; sector detection NOT used.
        assert client.get_live_snapshot.call_count == 3

    def test_peers_no_data_for_any_peer(
        self, tmp_db: Path, populated_store: FlowStore, monkeypatch
    ):
        """All peer fetches fail → exit 1 with explanatory message."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client = _make_fund_client_mock(live_error=YFinanceError("404"))
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(
                app, ["fund", "peers", "sbin", "--with", "TCS,INFY"]
            )
        assert result.exit_code == 1
        assert "No data" in result.output

    def test_peers_auto_detect_no_sector_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No --with and a snapshot without sector → exit 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        snap = _make_live_snapshot(sector=None)  # type: ignore[arg-type]
        client = _make_fund_client_mock(live=snap)
        with patch("flowtracker.fund_commands.FundClient", return_value=client):
            result = runner.invoke(app, ["fund", "peers", "SBIN"])
        assert result.exit_code == 1
        assert "Cannot detect sector" in result.output


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


class TestFundBackfill:
    """`flowtrack fund backfill` — Screener.in + yfinance multi-stream."""

    def test_backfill_empty_watchlist_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """No -s and empty watchlist → exit 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(app, ["fund", "backfill"])
        assert result.exit_code == 1
        assert "Watchlist is empty" in result.output

    def test_backfill_single_symbol_writes_streams(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """Quarters + annual + ratios from Screener AND P/E snapshots from yfinance."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        quarter = QuarterlyResult(
            symbol="SBIN",
            quarter_end="2026-03-31",
            revenue=120000.0,
            net_income=18000.0,
        )
        annual_eps = AnnualEPS(
            symbol="SBIN", fiscal_year_end="2026-03-31", eps=72.0
        )
        annual_fin = AnnualFinancials(
            symbol="SBIN", fiscal_year_end="2026-03-31", revenue=480000.0
        )
        ratios = ScreenerRatios(
            symbol="SBIN", fiscal_year_end="2026-03-31", roce_pct=15.0
        )
        pe_snap = _make_valuation_snapshot()

        sc_cls, sc_inner = _make_screener_cm_mock(
            quarters=[quarter],
            annual=[annual_eps],
            annual_fin=[annual_fin],
            ratios=[ratios],
        )
        client = _make_fund_client_mock(historical_pe=[pe_snap])

        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls), patch(
            "flowtracker.fund_commands.FundClient", return_value=client
        ):
            result = runner.invoke(app, ["fund", "backfill", "-s", "sbin"])

        assert result.exit_code == 0, result.output
        assert "Backfill complete" in result.output

        # All 4 streams were written to the store.
        with FlowStore(db_path=tmp_db) as fresh:
            qrs = fresh.get_quarterly_results("SBIN")
            assert len(qrs) >= 1
        # Screener page + excel were both fetched, then P/E was computed.
        sc_inner.fetch_company_page.assert_called_once_with("SBIN")
        sc_inner.download_excel.assert_called_once_with("SBIN")
        client.compute_historical_pe.assert_called_once()

    def test_backfill_quarters_only_skips_pe_stream(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """`--quarters-only` runs Screener stream but NOT the yfinance P/E stream."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, sc_inner = _make_screener_cm_mock()
        client = _make_fund_client_mock()
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls), patch(
            "flowtracker.fund_commands.FundClient", return_value=client
        ):
            result = runner.invoke(
                app, ["fund", "backfill", "-s", "SBIN", "--quarters-only"]
            )
        assert result.exit_code == 0
        client.compute_historical_pe.assert_not_called()
        sc_inner.fetch_company_page.assert_called_once()

    def test_backfill_valuation_only_skips_screener_html(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """`--valuation-only` skips HTML+excel parsing but still loads annual EPS."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        annual_eps = AnnualEPS(
            symbol="SBIN", fiscal_year_end="2026-03-31", eps=72.0
        )
        sc_cls, sc_inner = _make_screener_cm_mock(annual=[annual_eps])
        client = _make_fund_client_mock(historical_pe=[_make_valuation_snapshot()])
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls), patch(
            "flowtracker.fund_commands.FundClient", return_value=client
        ):
            result = runner.invoke(
                app, ["fund", "backfill", "-s", "SBIN", "--valuation-only"]
            )
        assert result.exit_code == 0
        # In valuation-only branch we use fetch_all_with_annual, NOT fetch_company_page.
        sc_inner.fetch_company_page.assert_not_called()
        sc_inner.fetch_all_with_annual.assert_called_once_with("SBIN")
        client.compute_historical_pe.assert_called_once()

    def test_backfill_screener_login_failure_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        """A ScreenerError raised by entering the CM aborts with exit 1."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        cm = MagicMock()
        cm.__enter__ = MagicMock(side_effect=ScreenerError("login failed"))
        cm.__exit__ = MagicMock(return_value=False)
        sc_cls = MagicMock(return_value=cm)

        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "backfill", "-s", "SBIN"])
        assert result.exit_code == 1
        assert "login failed" in result.output


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------


class TestFundCharts:
    """`flowtrack fund charts` — fetch + persist Screener.in chart datasets."""

    def test_charts_stores_dataset(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        datasets = [
            {
                "metric": "Price",
                "label": "Price",
                "values": [["2026-01-01", 800.0], ["2026-02-01", 850.0]],
            }
        ]
        sc_cls, sc_inner = _make_screener_cm_mock(chart_datasets=datasets)
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(
                app, ["fund", "charts", "-s", "sbin", "-t", "price"]
            )
        assert result.exit_code == 0, result.output
        assert "Stored" in result.output
        sc_inner.fetch_chart_data_by_type.assert_called_once_with("12345", "price")

    def test_charts_empty_datasets_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, _ = _make_screener_cm_mock(chart_datasets=[])
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "charts", "-s", "SBIN"])
        assert result.exit_code == 1
        assert "No chart data" in result.output

    def test_charts_screener_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, sc_inner = _make_screener_cm_mock()
        sc_inner.fetch_chart_data_by_type.side_effect = ScreenerError("API down")
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "charts", "-s", "SBIN"])
        assert result.exit_code == 1
        assert "API down" in result.output


# ---------------------------------------------------------------------------
# peer (Screener.in)
# ---------------------------------------------------------------------------


class TestFundPeer:
    """`flowtrack fund peer` — Screener.in peer comparison fetch & store."""

    def test_peer_stores_peers(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        peers = [
            {
                "name": "HDFC Bank",
                "cmp": 1700.0,
                "pe": 18.5,
                "market_cap": 1_300_000.0,
                "div_yield": 1.2,
                "np_qtr": 16000.0,
                "qtr_profit_var": 12.5,
                "sales_qtr": 80000.0,
                "roce": 22.0,
            },
            {
                "name": "ICICI Bank",
                "cmp": 1100.0,
                "pe": 17.0,
                "market_cap": 800_000.0,
                "div_yield": 1.0,
                "np_qtr": 11000.0,
                "qtr_profit_var": 10.0,
                "sales_qtr": 50000.0,
                "roce": 20.0,
            },
        ]
        sc_cls, sc_inner = _make_screener_cm_mock(peers=peers)
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "peer", "-s", "sbin"])
        assert result.exit_code == 0, result.output
        assert "Stored" in result.output
        sc_inner.fetch_peers.assert_called_once_with("67890")

        with FlowStore(db_path=tmp_db) as fresh:
            stored = fresh.get_peers("SBIN")
        assert len(stored) == 2

    def test_peer_empty_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, _ = _make_screener_cm_mock(peers=[])
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "peer", "-s", "SBIN"])
        assert result.exit_code == 1
        assert "No peer data" in result.output


# ---------------------------------------------------------------------------
# schedules
# ---------------------------------------------------------------------------


class TestFundSchedules:
    """`flowtrack fund schedules` — line-item breakdowns from Screener.in."""

    def test_schedules_stores_breakdown(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        data = {
            "Domestic Sales": {"Mar 2024": 100.0, "Mar 2025": 120.0},
            "Export Sales": {"Mar 2024": 50.0, "Mar 2025": 60.0},
        }
        sc_cls, sc_inner = _make_screener_cm_mock(schedules=data)
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(
                app,
                [
                    "fund", "schedules",
                    "-s", "sbin",
                    "--section", "profit-loss",
                    "--parent", "Sales",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "Stored" in result.output
        sc_inner.fetch_schedules.assert_called_once_with(
            "12345", "profit-loss", "Sales"
        )

    def test_schedules_empty_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, _ = _make_screener_cm_mock(schedules={})
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(
                app, ["fund", "schedules", "-s", "SBIN"]
            )
        assert result.exit_code == 1
        assert "No schedule" in result.output

    def test_schedules_screener_error_exits_1(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        sc_cls, sc_inner = _make_screener_cm_mock()
        sc_inner.fetch_schedules.side_effect = ScreenerError("schedule fetch failed")
        with patch("flowtracker.fund_commands.ScreenerClient", sc_cls):
            result = runner.invoke(app, ["fund", "schedules", "-s", "SBIN"])
        assert result.exit_code == 1
        assert "schedule fetch failed" in result.output
