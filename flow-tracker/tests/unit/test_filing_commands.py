"""Tests for filing_commands.py — CLI wiring around FilingClient + FlowStore.

NOT TESTED (documented intentional gaps):
- `extract` subcommand: spins up asyncio + Claude API extraction; out of scope.
- `open_filing` subcommand: invokes `subprocess.run(["open", ...])` which is
  macOS-specific and side-effecting; not worth the mock surface for ~5 lines.

All other subcommands (`fetch`, `download`, `list`, `annual_reports`) are
covered with FilingClient mocked at the `flowtracker.filing_commands` import
site so the real BSE/NSE HTTP layer never executes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from flowtracker.filing_commands import app as filing_app
from flowtracker.filing_models import CorporateFiling
from flowtracker.store import FlowStore

runner = CliRunner()


# -- Helpers --


def _cm(inner: MagicMock) -> MagicMock:
    """Wrap a mock instance as a context manager (so `with X() as y` returns inner)."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _sample_filings() -> list[CorporateFiling]:
    return [
        CorporateFiling(
            symbol="SBIN",
            bse_scrip_code="500112",
            filing_date="2026-01-25",
            category="Result",
            subcategory="Financial Results",
            headline="Q3 FY26 Results",
            attachment_name="Q3_results.pdf",
            pdf_flag=0,
            file_size=250000,
            news_id="NEWS001",
        ),
        CorporateFiling(
            symbol="SBIN",
            bse_scrip_code="500112",
            filing_date="2026-01-28",
            category="Company Update",
            subcategory="Earnings Call Transcript",
            headline="Concall Transcript Q3 FY26",
            attachment_name="concall_q3.pdf",
            pdf_flag=1,
            file_size=500000,
            news_id="NEWS002",
        ),
    ]


# -- fetch --


class TestFetch:
    def test_fetch_no_download_stores_filings(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        filings = _sample_filings()
        client_inner = MagicMock()
        client_inner.fetch_research_filings.return_value = filings

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["fetch", "sbin", "-y", "2"])

        assert result.exit_code == 0, result.output
        client_inner.fetch_research_filings.assert_called_once()
        # Ensure no PDF download happened on the no-download path.
        client_inner.download_filing.assert_not_called()
        # Summary table renders.
        assert "Filing Summary" in result.output
        assert "SBIN" in result.output
        # Stored in DB.
        with FlowStore(db_path=tmp_db) as s:
            assert len(s.get_filings("SBIN")) == 2

    def test_fetch_with_download_invokes_download_loop(
        self, tmp_db: Path, store: FlowStore, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        filings = _sample_filings()
        downloaded_path = tmp_path / "fake.pdf"
        downloaded_path.write_text("PDF")

        client_inner = MagicMock()
        client_inner.fetch_research_filings.return_value = filings
        client_inner.download_filing.return_value = downloaded_path

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["fetch", "sbin", "--download"])

        assert result.exit_code == 0, result.output
        assert client_inner.download_filing.call_count == 2
        assert "Downloaded" in result.output
        # Paths persisted.
        with FlowStore(db_path=tmp_db) as s:
            stored = s.get_filings("SBIN")
            assert all(f.local_path == str(downloaded_path) for f in stored)

    def test_fetch_empty_exits_nonzero(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        client_inner = MagicMock()
        client_inner.fetch_research_filings.return_value = []

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["fetch", "BOGUSXYZ"])

        assert result.exit_code == 1
        assert "No filings found" in result.output


# -- download --


class TestDownload:
    def test_download_no_filings_in_db(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Patch FilingClient anyway so any accidental call would fail loudly.
        with patch("flowtracker.filing_commands.FilingClient") as mock_cls:
            result = runner.invoke(filing_app, ["download", "NONESUCH"])
            mock_cls.assert_not_called()

        assert result.exit_code == 1
        assert "No filings in DB" in result.output

    def test_download_loops_and_persists_paths(
        self, tmp_db: Path, store: FlowStore, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Seed our own filings (not via populated_store — its make_filings uses
        # symbol-independent news_ids that collide on UNIQUE(news_id)).
        store.upsert_filings(_sample_filings())

        downloaded_path = tmp_path / "downloaded.pdf"
        downloaded_path.write_text("PDF")

        client_inner = MagicMock()
        client_inner.download_filing.return_value = downloaded_path

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["download", "sbin"])

        assert result.exit_code == 0, result.output
        # Both seeded filings download.
        assert client_inner.download_filing.call_count == 2
        assert "Downloaded 2 new PDFs" in result.output

        with FlowStore(db_path=tmp_db) as s:
            for f in s.get_filings("SBIN"):
                assert f.local_path == str(downloaded_path)

    def test_download_skips_existing_local_paths(
        self, tmp_db: Path, store: FlowStore, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        # Pre-populate filings with local_path that exists on disk.
        existing = tmp_path / "already.pdf"
        existing.write_text("PDF")
        filings = _sample_filings()
        for f in filings:
            f.local_path = str(existing)
        store.upsert_filings(filings)

        client_inner = MagicMock()

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["download", "sbin"])

        assert result.exit_code == 0, result.output
        # Both already on disk → skipped, no downloads.
        client_inner.download_filing.assert_not_called()
        assert "skipped 2" in result.output


# -- list --


class TestList:
    def test_list_renders_table(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store.upsert_filings(_sample_filings())
        result = runner.invoke(filing_app, ["list", "sbin"])

        assert result.exit_code == 0, result.output
        assert "Corporate Filings" in result.output
        assert "SBIN" in result.output

    def test_list_with_category_filter(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store.upsert_filings(_sample_filings())
        # Filter for "Earnings Call" — should keep just the concall row.
        result = runner.invoke(
            filing_app, ["list", "sbin", "-c", "Earnings Call"]
        )

        assert result.exit_code == 0, result.output
        assert "Concall" in result.output
        assert "Q3 FY26 Results" not in result.output

    def test_list_empty_symbol_graceful(
        self, tmp_db: Path, store: FlowStore, monkeypatch
    ):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        result = runner.invoke(filing_app, ["list", "GHOST"])

        # Empty path returns silently with exit 0.
        assert result.exit_code == 0
        assert "No filings" in result.output


# -- annual-reports --


class TestAnnualReports:
    def test_annual_reports_renders(self, monkeypatch):
        client_inner = MagicMock()
        client_inner.fetch_annual_reports.return_value = [
            {
                "from_year": "2024",
                "to_year": "2025",
                "company_name": "STATE BANK OF INDIA",
                "url": "https://example.com/ar.pdf",
            },
        ]

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["annual-reports", "sbin"])

        assert result.exit_code == 0, result.output
        assert "Annual Reports" in result.output
        assert "STATE BANK" in result.output
        client_inner.fetch_annual_reports.assert_called_once_with("SBIN")

    def test_annual_reports_empty_exits_nonzero(self, monkeypatch):
        client_inner = MagicMock()
        client_inner.fetch_annual_reports.return_value = []

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(filing_app, ["annual-reports", "GHOSTCO"])

        assert result.exit_code == 1
        assert "No annual reports" in result.output

    def test_annual_reports_with_download(self, tmp_path: Path, monkeypatch):
        client_inner = MagicMock()
        client_inner.fetch_annual_reports.return_value = [
            {
                "from_year": "2024",
                "to_year": "2025",
                "company_name": "STATE BANK OF INDIA",
                "url": "https://example.com/ar.pdf",
            },
        ]
        client_inner.download_url.return_value = tmp_path / "ar.pdf"

        with patch(
            "flowtracker.filing_commands.FilingClient",
            return_value=_cm(client_inner),
        ):
            result = runner.invoke(
                filing_app, ["annual-reports", "sbin", "--download"]
            )

        assert result.exit_code == 0, result.output
        client_inner.download_url.assert_called_once()
        # Verify download_url args: (url, symbol, kind, filename)
        args, _ = client_inner.download_url.call_args
        assert args[1] == "SBIN"
        assert args[2] == "annual_reports"
        assert "annual_report_2024_2025.pdf" in args[3]
