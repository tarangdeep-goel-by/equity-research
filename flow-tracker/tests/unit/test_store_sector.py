"""Tests for sector_benchmarks and sector aggregation store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore


# -- sector_benchmarks CRUD --


def test_upsert_and_get_sector_benchmark(store: FlowStore):
    """Round-trip a single sector benchmark."""
    store.upsert_sector_benchmark(
        "SBIN", "pe_trailing", 9.5, [7.0, 8.0, 9.5, 12.0, 16.0, 25.0],
    )

    result = store.get_sector_benchmark("SBIN", "pe_trailing")
    assert result is not None
    assert result["subject_symbol"] == "SBIN"
    assert result["metric"] == "pe_trailing"
    assert result["subject_value"] == 9.5
    assert result["peer_count"] == 6
    assert result["sector_min"] == 7.0
    assert result["sector_max"] == 25.0
    assert result["sector_median"] is not None
    assert result["percentile"] is not None


def test_get_sector_benchmark_empty(store: FlowStore):
    """Returns None when no benchmark exists."""
    assert store.get_sector_benchmark("UNKNOWN", "pe_trailing") is None


def test_get_all_sector_benchmarks(store: FlowStore):
    """Returns all metrics for a symbol."""
    store.upsert_sector_benchmark("SBIN", "pe_trailing", 9.5, [7.0, 12.0])
    store.upsert_sector_benchmark("SBIN", "pb_ratio", 1.8, [1.2, 2.5])
    store.upsert_sector_benchmark("SBIN", "roe", 18.5, [12.0, 20.0])

    result = store.get_all_sector_benchmarks("SBIN")
    assert len(result) == 3
    metrics = {r["metric"] for r in result}
    assert metrics == {"pe_trailing", "pb_ratio", "roe"}


def test_get_all_sector_benchmarks_empty(store: FlowStore):
    """Returns empty list when no benchmarks exist for symbol."""
    assert store.get_all_sector_benchmarks("UNKNOWN") == []


def test_clear_sector_benchmarks(store: FlowStore):
    """Clears all benchmarks for a specific symbol."""
    store.upsert_sector_benchmark("SBIN", "pe_trailing", 9.5, [7.0, 12.0])
    store.upsert_sector_benchmark("SBIN", "pb_ratio", 1.8, [1.2, 2.5])
    store.upsert_sector_benchmark("INFY", "pe_trailing", 28.0, [22.0, 35.0])

    store.clear_sector_benchmarks("SBIN")

    assert store.get_all_sector_benchmarks("SBIN") == []
    # INFY data should be unaffected
    assert len(store.get_all_sector_benchmarks("INFY")) == 1


def test_upsert_sector_benchmark_empty_peers(store: FlowStore):
    """Empty peer list sets all stats to None."""
    store.upsert_sector_benchmark("SBIN", "pe_trailing", 9.5, [])

    result = store.get_sector_benchmark("SBIN", "pe_trailing")
    assert result is not None
    assert result["peer_count"] == 0
    assert result["sector_median"] is None
    assert result["percentile"] is None


# -- sector aggregation (needs populated_store with cross-table data) --


def test_get_sector_list(populated_store: FlowStore):
    """Returns distinct industry names from index constituents."""
    result = populated_store.get_sector_list()
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "Banks" in result
    assert "IT - Software" in result
