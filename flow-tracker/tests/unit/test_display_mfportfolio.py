"""Unit tests for flowtracker/mfportfolio_display.py.

Targets the four public display functions. Captures Rich console output
to a StringIO buffer by monkeypatching the module-level `console`.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from flowtracker import mfportfolio_display as mod
from flowtracker.mfportfolio_models import MFHoldingChange, MFSchemeHolding


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    # no force_terminal: Rich otherwise re-reads COLUMNS from env and clamps
    # column width on narrow CI runners even when width= is explicit.
    con = Console(file=buf, width=200, no_color=True)
    return con, buf


# ---------------------------------------------------------------------------
# display_mfport_fetch_result
# ---------------------------------------------------------------------------


def test_display_mfport_fetch_result(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    mod.display_mfport_fetch_result(1234, "2026-02", ["SBI", "ICICI", "PPFAS"])
    out = buf.getvalue()
    assert "1,234" in out
    assert "2026-02" in out
    assert "SBI" in out
    assert "ICICI" in out
    assert "Fetch Complete" in out


# ---------------------------------------------------------------------------
# display_stock_holdings
# ---------------------------------------------------------------------------


def test_display_stock_holdings_empty(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    mod.display_stock_holdings([], "RELIANCE")
    out = buf.getvalue()
    assert "No MF holdings" in out
    assert "RELIANCE" in out


def test_display_stock_holdings_populated(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    holdings = [
        MFSchemeHolding(
            month="2026-02",
            amc="SBI",
            scheme_name="SBI Bluechip Fund Regular Plan Growth Option",
            isin="INE002A01018",
            stock_name="Reliance Industries",
            quantity=1_500_000,
            market_value_cr=4250.75,
            pct_of_nav=3.42,
        ),
    ]
    mod.display_stock_holdings(holdings, "RELIANCE")
    out = buf.getvalue()
    assert "2026-02" in out
    assert "SBI" in out
    # scheme_name is truncated to 28 chars
    assert "SBI Bluechip Fund Regular Pl" in out
    assert "1,500,000" in out
    assert "4,250.8" in out  # 4250.75 rounds to 4,250.8 with {:,.1f}
    assert "3.42%" in out


# ---------------------------------------------------------------------------
# display_top_changes
# ---------------------------------------------------------------------------


def test_display_top_changes_empty(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    mod.display_top_changes([], "Top Buys")
    out = buf.getvalue()
    assert "No holding changes" in out


def test_display_top_changes_populated(monkeypatch):
    """Exercise all four change_type branches and positive+negative val_chg."""
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)

    def _change(change_type: str, prev_value: float, curr_value: float,
                stock: str) -> MFHoldingChange:
        return MFHoldingChange(
            stock_name=stock,
            isin=f"INE000A0{change_type[:3]}01",
            amc="SBI",
            scheme_name=f"SBI {change_type} Fund",
            prev_month="2026-01",
            curr_month="2026-02",
            prev_qty=1000,
            curr_qty=2000,
            qty_change=1000,
            prev_value=prev_value,
            curr_value=curr_value,
            change_type=change_type,
        )

    changes = [
        _change("NEW", 0.0, 500.0, "Stock A"),
        _change("EXIT", 300.0, 0.0, "Stock B"),         # negative val_chg
        _change("INCREASE", 100.0, 250.0, "Stock C"),
        _change("DECREASE", 400.0, 150.0, "Stock D"),   # negative val_chg
        _change("UNKNOWN", 50.0, 75.0, "Stock E"),      # no type_color branch
    ]
    mod.display_top_changes(changes, "Top MF Moves")
    out = buf.getvalue()
    assert "Top MF Moves" in out
    assert "NEW" in out
    assert "EXIT" in out
    assert "INCREASE" in out
    assert "DECREASE" in out
    assert "UNKNOWN" in out
    assert "Stock A" in out
    assert "Stock D" in out
    assert "+1,000" in out  # qty_change formatted with sign


# ---------------------------------------------------------------------------
# display_amc_summary
# ---------------------------------------------------------------------------


def test_display_amc_summary_empty(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    mod.display_amc_summary([])
    out = buf.getvalue()
    assert "No portfolio data" in out


def test_display_amc_summary_populated(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(mod, "console", con)
    summary = [
        {"amc": "SBI", "num_schemes": 42, "num_stocks": 523, "total_value_cr": 785432.0},
        {"amc": "ICICI", "num_schemes": 38, "num_stocks": 498, "total_value_cr": 612100.5},
    ]
    mod.display_amc_summary(summary)
    out = buf.getvalue()
    assert "Summary by AMC" in out
    assert "SBI" in out
    assert "ICICI" in out
    assert "42" in out
    assert "523" in out
    assert "785,432" in out
    assert "612,10" in out  # 612,101 after rounding
