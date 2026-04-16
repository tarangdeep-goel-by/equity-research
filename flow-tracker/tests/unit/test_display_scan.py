"""Unit tests for flowtracker.scan_display — Rich render helpers.

Each test swaps the module-level `console` for a buffered Console, invokes the
render function, and asserts key strings appear in the captured output.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from flowtracker import scan_display
from flowtracker.holding_models import PromoterPledge, ShareholdingChange
from flowtracker.scan_models import BatchFetchResult, IndexConstituent, ScanSummary


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    con = Console(file=buf, force_terminal=True, width=200)
    return con, buf


# ---------------------------------------------------------------------------
# display_constituents
# ---------------------------------------------------------------------------


class TestDisplayConstituents:
    def test_happy_path(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        constituents = [
            IndexConstituent(
                symbol="RELIANCE",
                index_name="NIFTY 50",
                company_name="Reliance Industries",
                industry="Oil & Gas",
            ),
            IndexConstituent(
                symbol="SBIN",
                index_name="NIFTY 50",
                company_name=None,
                industry=None,
            ),
        ]
        scan_display.display_constituents(constituents)

        out = buf.getvalue()
        assert "RELIANCE" in out
        assert "SBIN" in out
        assert "NIFTY 50" in out
        # None fields should render as em-dash fallback
        assert "—" in out

    def test_empty(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        scan_display.display_constituents([])

        assert "No constituents found" in buf.getvalue()


# ---------------------------------------------------------------------------
# display_scan_deviations
# ---------------------------------------------------------------------------


class TestDisplayScanDeviations:
    def test_happy_path_mixed_signs(self, monkeypatch):
        """Exercises positive (green), negative (red), and zero (dim) branches."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        changes = [
            ShareholdingChange(
                symbol="HDFCBANK",
                category="FII",
                prev_quarter_end="2025-09-30",
                curr_quarter_end="2025-12-31",
                prev_pct=20.0,
                curr_pct=22.5,
                change_pct=2.5,
            ),
            ShareholdingChange(
                symbol="ICICIBANK",
                category="FII",
                prev_quarter_end="2025-09-30",
                curr_quarter_end="2025-12-31",
                prev_pct=18.0,
                curr_pct=15.0,
                change_pct=-3.0,
            ),
            ShareholdingChange(
                symbol="TCS",
                category="MF",
                prev_quarter_end="2025-09-30",
                curr_quarter_end="2025-12-31",
                prev_pct=5.0,
                curr_pct=5.0,
                change_pct=0.0,
            ),
        ]
        scan_display.display_scan_deviations(changes)

        out = buf.getvalue()
        assert "HDFCBANK" in out
        assert "ICICIBANK" in out
        assert "TCS" in out
        assert "Shareholding Deviations" in out
        assert "+2.50%" in out
        assert "-3.00%" in out

    def test_empty(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        scan_display.display_scan_deviations([])

        assert "No shareholding deviations found" in buf.getvalue()


# ---------------------------------------------------------------------------
# display_handoff_signals
# ---------------------------------------------------------------------------


class TestDisplayHandoffSignals:
    def test_happy_path(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        fii = ShareholdingChange(
            symbol="INFY",
            category="FII",
            prev_quarter_end="2025-09-30",
            curr_quarter_end="2025-12-31",
            prev_pct=30.0,
            curr_pct=27.0,
            change_pct=-3.0,
        )
        mf = ShareholdingChange(
            symbol="INFY",
            category="MF",
            prev_quarter_end="2025-09-30",
            curr_quarter_end="2025-12-31",
            prev_pct=8.0,
            curr_pct=10.5,
            change_pct=2.5,
        )
        scan_display.display_handoff_signals([(fii, mf)])

        out = buf.getvalue()
        assert "INFY" in out
        assert "Handoff Signals" in out
        assert "-3.00%" in out
        assert "+2.50%" in out

    def test_empty(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        scan_display.display_handoff_signals([])

        assert "No handoff signals found" in buf.getvalue()


# ---------------------------------------------------------------------------
# display_scan_summary
# ---------------------------------------------------------------------------


class TestDisplayScanSummary:
    def test_happy_path_with_missing_truncation(self, monkeypatch):
        """Exercises the >10 missing symbols truncation branch."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        summary = ScanSummary(
            total_symbols=50,
            symbols_with_data=40,
            latest_quarter="2025-12-31",
            missing_symbols=[f"SYM{i}" for i in range(15)],
        )
        scan_display.display_scan_summary(summary)

        out = buf.getvalue()
        assert "Scanner Status" in out
        assert "50" in out
        assert "40" in out
        assert "2025-12-31" in out
        assert "+5 more" in out  # 15 missing - 10 shown

    def test_zero_totals(self, monkeypatch):
        """Division-by-zero guard: total_symbols == 0 sets pct to 0."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        summary = ScanSummary(
            total_symbols=0,
            symbols_with_data=0,
            latest_quarter=None,
            missing_symbols=[],
        )
        scan_display.display_scan_summary(summary)

        out = buf.getvalue()
        assert "Scanner Status" in out
        assert "None" in out  # no missing symbols
        assert "—" in out  # em-dash for missing quarter


# ---------------------------------------------------------------------------
# display_batch_result
# ---------------------------------------------------------------------------


class TestDisplayBatchResult:
    def test_success(self, monkeypatch):
        """All fetched, no failures → green border, no error lines."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        result = BatchFetchResult(total=10, fetched=10, skipped=0, failed=0, errors=[])
        scan_display.display_batch_result(result)

        out = buf.getvalue()
        assert "Batch Fetch Complete" in out
        assert "Fetched 10 / Total 10" in out

    def test_with_errors(self, monkeypatch):
        """Failures present → yellow border and error lines rendered."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        result = BatchFetchResult(
            total=5,
            fetched=3,
            skipped=1,
            failed=1,
            errors=["FOO: timeout", "BAR: 404"],
        )
        scan_display.display_batch_result(result)

        out = buf.getvalue()
        assert "Fetched 3 / Total 5" in out
        assert "Skipped: 1" in out
        assert "Failed: 1" in out
        assert "FOO: timeout" in out
        assert "BAR: 404" in out


# ---------------------------------------------------------------------------
# display_pledge_stocks
# ---------------------------------------------------------------------------


class TestDisplayPledgeStocks:
    def test_all_risk_tiers(self, monkeypatch):
        """One pledge per risk bucket: HIGH (>=20), MEDIUM (>=5), LOW (<5)."""
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        pledges = [
            PromoterPledge(
                symbol="HIGHRISK",
                quarter_end="2025-12-31",
                pledge_pct=35.0,
                encumbered_pct=40.0,
            ),
            PromoterPledge(
                symbol="MEDRISK",
                quarter_end="2025-12-31",
                pledge_pct=10.0,
                encumbered_pct=12.0,
            ),
            PromoterPledge(
                symbol="LOWRISK",
                quarter_end="2025-12-31",
                pledge_pct=1.5,
                encumbered_pct=2.0,
            ),
        ]
        scan_display.display_pledge_stocks(pledges)

        out = buf.getvalue()
        assert "HIGHRISK" in out
        assert "MEDRISK" in out
        assert "LOWRISK" in out
        assert "HIGH" in out
        assert "MEDIUM" in out
        assert "LOW" in out
        assert "Promoter Pledging" in out

    def test_empty(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(scan_display, "console", con)

        scan_display.display_pledge_stocks([])

        assert "No stocks with significant promoter pledging" in buf.getvalue()
