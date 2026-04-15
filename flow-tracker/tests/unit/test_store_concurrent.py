"""Tests for concurrent FlowStore access via WAL mode.

Validates that SQLite WAL journal mode allows safe concurrent reads and writes
without data corruption or locking errors.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from flowtracker.store import FlowStore
from tests.fixtures.factories import make_daily_flow, make_quarterly_results


@pytest.fixture
def initialized_db(tmp_db):
    """Pre-initialize schema so concurrent threads don't race on DDL."""
    with FlowStore(db_path=tmp_db) as store:
        pass  # Schema created
    return tmp_db


class TestConcurrentWrites:
    """Two writers inserting to the same or different tables concurrently."""

    def test_concurrent_writes_same_table(self, initialized_db):
        """Two writers inserting different date ranges don't corrupt data."""
        errors: list[Exception] = []

        def writer(db_path: Path, flows: list) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    store.upsert_flows(flows)
            except Exception as e:
                errors.append(e)

        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        flows_a = [make_daily_flow(dt=today, category="FII")]
        flows_b = [make_daily_flow(dt=yesterday, category="FII")]

        t1 = threading.Thread(target=writer, args=(initialized_db, flows_a))
        t2 = threading.Thread(target=writer, args=(initialized_db, flows_b))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Writer threads raised: {errors}"

        with FlowStore(db_path=initialized_db) as store:
            flows = store.get_flows(days=7)
        assert len(flows) == 2

    def test_concurrent_writes_different_tables(self, initialized_db):
        """Writers to different tables don't interfere."""
        errors: list[Exception] = []
        today = date.today().isoformat()

        def write_flows(db_path: Path) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    # Use today's date so get_flows(days=7) below always includes it,
                    # regardless of when the test runs (factory default is hardcoded).
                    store.upsert_flows([make_daily_flow(dt=today)])
            except Exception as e:
                errors.append(e)

        def write_quarterly(db_path: Path) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    store.upsert_quarterly_results(make_quarterly_results("SBIN", n=2))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_flows, args=(initialized_db,))
        t2 = threading.Thread(target=write_quarterly, args=(initialized_db,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Writer threads raised: {errors}"

        with FlowStore(db_path=initialized_db) as store:
            assert len(store.get_flows(days=7)) >= 1
            assert len(store.get_quarterly_results("SBIN")) >= 1


class TestConcurrentReadWrite:
    """Reader doesn't block writer and sees consistent data."""

    def test_concurrent_read_write(self, tmp_db):
        """Reader and writer run simultaneously without crash."""
        # Pre-populate
        with FlowStore(db_path=tmp_db) as store:
            store.upsert_flows([make_daily_flow(dt="2026-03-25")])

        results: list[int] = []
        errors: list[Exception] = []

        def reader(db_path: Path) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    flows = store.get_flows(days=30)
                    results.append(len(flows))
            except Exception as e:
                errors.append(e)

        def writer(db_path: Path) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    store.upsert_flows([make_daily_flow(dt="2026-03-26")])
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=reader, args=(tmp_db,))
        t2 = threading.Thread(target=writer, args=(tmp_db,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Threads raised: {errors}"
        # Reader saw either 1 or 2 rows (depends on timing), but no crash
        assert results[0] >= 1

    def test_many_concurrent_readers(self, tmp_db):
        """10 concurrent readers all get consistent results."""
        today = date.today().isoformat()
        with FlowStore(db_path=tmp_db) as store:
            # Use today's date so get_flows(days=7) always sees the row,
            # regardless of when the test runs (factory default is hardcoded).
            store.upsert_flows([make_daily_flow(dt=today)])

        results: list[int] = []
        errors: list[Exception] = []

        def reader(db_path: Path) -> None:
            try:
                with FlowStore(db_path=db_path) as store:
                    results.append(len(store.get_flows(days=7)))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader, args=(tmp_db,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Reader threads raised: {errors}"
        assert all(r >= 1 for r in results)
        assert len(results) == 10


class TestLockRecovery:
    """WAL mode handles lock contention gracefully."""

    def test_store_recovers_from_busy_writer(self, tmp_db):
        """One writer holds a long transaction; another writer waits and succeeds.

        SQLite WAL mode with default busy_timeout should allow the second writer
        to retry and succeed once the first commits.
        """
        barrier = threading.Barrier(2, timeout=10)
        errors: list[Exception] = []

        def slow_writer(db_path: Path) -> None:
            """Holds an open transaction briefly."""
            try:
                conn = sqlite3.connect(str(db_path), timeout=10)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO daily_flows (date, category, buy_value, sell_value, net_value) "
                    "VALUES ('2026-03-20', 'FII', 10000, 11000, -1000)"
                )
                barrier.wait()  # Signal that we hold the lock
                time.sleep(0.3)  # Hold lock briefly
                conn.commit()
                conn.close()
            except Exception as e:
                errors.append(e)

        def fast_writer(db_path: Path) -> None:
            """Tries to write while slow_writer holds the lock."""
            try:
                barrier.wait()  # Wait until slow_writer has the lock
                # SQLite will retry internally thanks to the timeout
                with FlowStore(db_path=db_path) as store:
                    store.upsert_flows([make_daily_flow(dt="2026-03-21")])
            except Exception as e:
                errors.append(e)

        # Initialize schema first
        with FlowStore(db_path=tmp_db) as store:
            pass

        t1 = threading.Thread(target=slow_writer, args=(tmp_db,))
        t2 = threading.Thread(target=fast_writer, args=(tmp_db,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not errors, f"Threads raised: {errors}"

        with FlowStore(db_path=tmp_db) as store:
            flows = store.get_flows(days=30)
        assert len(flows) == 2


class TestLargeBatch:
    """Bulk insert correctness."""

    def test_large_batch_upsert(self, tmp_db):
        """Insert 1000 flow records at once; verify count and no corruption."""
        from datetime import date, timedelta

        flows = []
        base = date(2023, 1, 1)
        for i in range(500):
            d = base + timedelta(days=i)
            ds = d.isoformat()
            flows.append(make_daily_flow(dt=ds, category="FII", buy=10000 + i, sell=11000 + i))
            flows.append(make_daily_flow(dt=ds, category="DII", buy=8000 + i, sell=7500 + i))

        assert len(flows) == 1000

        with FlowStore(db_path=tmp_db) as store:
            count = store.upsert_flows(flows)
            assert count == 1000

            # get_flows uses date('now', ...) so use raw SQL to verify old dates
            all_rows = store._conn.execute(
                "SELECT * FROM daily_flows ORDER BY date, category"
            ).fetchall()
            assert len(all_rows) == 1000

            # Spot check: FII and DII each have 500 records
            fii_rows = [r for r in all_rows if r["category"] == "FII"]
            dii_rows = [r for r in all_rows if r["category"] == "DII"]
            assert len(fii_rows) == 500
            assert len(dii_rows) == 500
