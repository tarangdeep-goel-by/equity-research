"""CLI tests for `flowtracker.fno_commands`.

Exercises the F&O CLI (`flowtrack fno ...`) against a real on-disk SQLite
store (via the ``FLOWTRACKER_DB`` env var + ``tmp_db`` fixture) with
``FnoClient`` patched at the ``fno_commands`` import site.

The client is used as a context manager, so patches are wired as
``MagicMock(return_value=cm)`` where ``cm.__enter__`` yields the inner
client mock.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from freezegun import freeze_time
from typer.testing import CliRunner

from flowtracker.fno_models import (
    FnoContract,
    FnoParticipantOi,
    FnoUniverse,
)
from flowtracker.main import app
from flowtracker.store import FlowStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_contract(
    *,
    trade_date: date = date(2026, 4, 17),
    symbol: str = "RELIANCE",
    instrument: str = "FUTSTK",
    strike: float | None = None,
    option_type: str | None = None,
    open_interest: int = 1_000_000,
) -> FnoContract:
    return FnoContract(
        trade_date=trade_date,
        symbol=symbol,
        instrument=instrument,
        expiry_date=date(2026, 4, 24),
        strike=strike,
        option_type=option_type,
        close=1490.0,
        open_interest=open_interest,
    )


def _mk_participant(
    *,
    trade_date: date = date(2026, 4, 17),
    participant: str = "FII",
    instrument_category: str = "stk_fut",
) -> FnoParticipantOi:
    return FnoParticipantOi(
        trade_date=trade_date,
        participant=participant,
        instrument_category=instrument_category,
        long_oi=100_000,
        short_oi=50_000,
    )


def _make_fno_client_cm(
    *,
    contracts: list[FnoContract] | None = None,
    participants: list[FnoParticipantOi] | None = None,
    universe: list[FnoUniverse] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Return ``(cls_mock, inner_mock)`` — ``cls_mock`` patched in place of
    ``FnoClient`` at the ``fno_commands`` import site. ``cls_mock()`` returns
    a context manager whose ``__enter__`` yields ``inner_mock``.
    """
    inner = MagicMock()
    inner.fetch_fno_bhavcopy.return_value = contracts or []
    inner.fetch_participant_oi.return_value = participants or []
    inner.fetch_eligible_universe.return_value = universe or []
    inner.fetch_option_chain.return_value = None

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    cls = MagicMock(return_value=cm)
    return cls, inner


# ---------------------------------------------------------------------------
# fno fetch
# ---------------------------------------------------------------------------


def test_fetch_command_calls_client_and_upserts(
    tmp_db: Path, store: FlowStore, monkeypatch
):
    """fno fetch --date → calls client, upserts to store, prints summary."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    contracts = [
        _mk_contract(instrument="FUTSTK"),
        _mk_contract(instrument="OPTSTK", strike=1500.0, option_type="CE"),
    ]
    participants = [
        _mk_participant(participant="FII", instrument_category="stk_fut"),
        _mk_participant(participant="DII", instrument_category="stk_fut"),
        _mk_participant(participant="Client", instrument_category="stk_fut"),
    ]
    cls, inner = _make_fno_client_cm(contracts=contracts, participants=participants)

    with patch("flowtracker.fno_commands.FnoClient", cls):
        result = runner.invoke(app, ["fno", "fetch", "--date", "2026-04-17"])

    assert result.exit_code == 0, result.output
    inner.fetch_fno_bhavcopy.assert_called_once_with(date(2026, 4, 17))
    inner.fetch_participant_oi.assert_called_once_with(date(2026, 4, 17))

    # Summary table should show the two counts.
    assert "bhavcopy contracts" in result.output
    assert "2" in result.output
    assert "participant OI rows" in result.output
    assert "3" in result.output


def test_fetch_command_empty_returns_exit_1(
    tmp_db: Path, store: FlowStore, monkeypatch
):
    """Empty results from both endpoints → exit 1 with 'holiday' hint."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    cls, inner = _make_fno_client_cm(contracts=[], participants=[])

    with patch("flowtracker.fno_commands.FnoClient", cls):
        result = runner.invoke(app, ["fno", "fetch", "--date", "2026-04-18"])

    assert result.exit_code == 1
    assert "No F&O data" in result.output or "holiday" in result.output.lower()


# ---------------------------------------------------------------------------
# fno universe refresh
# ---------------------------------------------------------------------------


@freeze_time("2026-04-17")
def test_universe_refresh_shows_added(
    tmp_db: Path, store: FlowStore, monkeypatch
):
    """Refresh prints ``Added:`` diff vs pre-existing universe.

    Note: ``upsert_fno_universe`` uses INSERT OR REPLACE — it never deletes
    rows (per the command's own docstring: "rows retained in DB"). So the
    "Removed" branch of the CLI is effectively dead code given current store
    semantics: pre-existing symbols stay in ``fno_universe`` and therefore
    remain in ``before``/``after`` sets. We only assert the ``Added`` side.
    """
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    # Pre-populate the store with RELIANCE, TCS, OLDSYM.
    existing = [
        FnoUniverse(symbol=s, eligible_since=date(2020, 1, 1), last_verified=date(2026, 4, 10))
        for s in ("RELIANCE", "TCS", "OLDSYM")
    ]
    store.upsert_fno_universe(existing)

    # Client returns RELIANCE, TCS, NEWSYM. OLDSYM stays in DB (retained).
    today = date.today()
    new_universe = [
        FnoUniverse(symbol=s, eligible_since=today, last_verified=today)
        for s in ("RELIANCE", "TCS", "NEWSYM")
    ]
    cls, inner = _make_fno_client_cm(universe=new_universe)

    with patch("flowtracker.fno_commands.FnoClient", cls):
        result = runner.invoke(app, ["fno", "universe", "refresh"])

    assert result.exit_code == 0, result.output
    assert "Added" in result.output
    assert "NEWSYM" in result.output

    # Confirm OLDSYM is indeed retained in the DB (justifying the "dead
    # code" comment above — the CLI cannot report it as Removed because the
    # store does not actually remove it).
    eligible = set(store.get_fno_eligible_stocks())
    assert "OLDSYM" in eligible
    assert "NEWSYM" in eligible


# ---------------------------------------------------------------------------
# fno summary
# ---------------------------------------------------------------------------


def test_summary_command_non_eligible_symbol(
    tmp_db: Path, store: FlowStore, monkeypatch
):
    """Unknown symbol → exit 1 with 'not F&O-eligible' message."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    result = runner.invoke(app, ["fno", "summary", "--symbol", "RANDOMCO"])

    assert result.exit_code == 1
    assert "not F&O-eligible" in result.output


# ---------------------------------------------------------------------------
# fno backfill
# ---------------------------------------------------------------------------


def test_backfill_skips_existing(
    tmp_db: Path, store: FlowStore, monkeypatch
):
    """Dates with pre-existing fno_contracts rows are skipped when --skip-existing."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    # Pre-populate fno_contracts for 2026-04-17 — backfill should skip this day.
    existing_date = date(2026, 4, 17)
    store.upsert_fno_contracts([_mk_contract(trade_date=existing_date)])

    # Client always returns one contract per fetch (should NOT be called for 17th).
    cls, inner = _make_fno_client_cm(
        contracts=[_mk_contract(trade_date=date(2026, 4, 15))],
        participants=[_mk_participant(trade_date=date(2026, 4, 15))],
    )

    # Backfill range: 15th (Wed) → 17th (Fri). 16th (Thu) also a weekday.
    # Weekdays only: 15, 16, 17. 17 should be skipped.
    with patch("flowtracker.fno_commands.FnoClient", cls):
        result = runner.invoke(
            app,
            [
                "fno", "backfill",
                "--from", "2026-04-15",
                "--to", "2026-04-17",
            ],
        )

    assert result.exit_code == 0, result.output

    # 17th must NOT have been fetched; 15th and 16th should have been.
    fetched_dates = [c.args[0] for c in inner.fetch_fno_bhavcopy.call_args_list]
    assert existing_date not in fetched_dates
    assert date(2026, 4, 15) in fetched_dates
    assert date(2026, 4, 16) in fetched_dates
    assert "skipped" in result.output.lower()
