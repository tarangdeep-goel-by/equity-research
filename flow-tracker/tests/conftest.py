"""Root-level fixtures shared across all test levels."""

from __future__ import annotations

import os
from pathlib import Path

# Pin terminal width + disable ANSI BEFORE any flowtracker/rich/typer import
# so Rich's Console picks these up at creation time. CliRunner's env={} kwarg
# is applied AFTER app import and cannot change an already-created Console,
# which was the root cause of flaky CLI snapshot tests on CI (narrow runner
# terminals vs. wide dev terminals producing different wrap behaviour).
os.environ.setdefault("COLUMNS", "120")
os.environ.setdefault("NO_COLOR", "1")
os.environ.setdefault("TERM", "dumb")

import pytest

from flowtracker.store import FlowStore


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Fresh temporary database path. FlowStore creates schema on init."""
    return tmp_path / "test_flows.db"


@pytest.fixture
def store(tmp_db: Path) -> FlowStore:
    """Initialized FlowStore at temp path. Schema + migrations applied automatically."""
    s = FlowStore(db_path=tmp_db)
    yield s
    s.close()


@pytest.fixture
def populated_store(store: FlowStore) -> FlowStore:
    """Store pre-populated with realistic fixture data across all key tables.

    2 symbols (SBIN, INFY), 8 quarters, 5 years annual, 30 days price data,
    insider trades, estimates, FMP data, alerts, portfolio holdings.
    """
    from tests.fixtures.factories import populate_all

    populate_all(store)
    return store


@pytest.fixture
def golden_dir() -> Path:
    """Path to the golden API response fixtures directory."""
    return Path(__file__).parent / "fixtures" / "golden"
