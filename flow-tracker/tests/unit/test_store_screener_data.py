"""Tests for screener_charts, peer_comparison, shareholder_detail, and financial_schedules store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore


# -- screener_charts --


def test_upsert_and_get_chart_data(store: FlowStore):
    """Round-trip chart data with metric/date/value structure."""
    datasets = [
        {
            "metric": "PE",
            "values": [("2025-01-01", 9.5), ("2025-02-01", 10.0), ("2025-03-01", 9.8)],
        },
        {
            "metric": "Price",
            "values": [("2025-01-01", 750.0), ("2025-02-01", 780.0)],
        },
    ]
    count = store.upsert_chart_data("SBIN", "historical", datasets)
    assert count == 5  # 3 + 2 data points

    result = store.get_chart_data("SBIN", "historical")
    assert len(result) == 2  # 2 metrics
    metrics = {r["metric"] for r in result}
    assert metrics == {"PE", "Price"}

    pe_data = [r for r in result if r["metric"] == "PE"][0]
    assert len(pe_data["values"]) == 3


def test_get_chart_data_empty_db(store: FlowStore):
    """Returns empty list when no chart data exists."""
    assert store.get_chart_data("UNKNOWN", "historical") == []


def test_upsert_chart_data_idempotent(store: FlowStore):
    """Upserting same data twice doesn't create duplicates."""
    datasets = [{"metric": "PE", "values": [("2025-01-01", 9.5)]}]
    store.upsert_chart_data("SBIN", "historical", datasets)
    store.upsert_chart_data("SBIN", "historical", datasets)

    result = store.get_chart_data("SBIN", "historical")
    assert len(result) == 1
    assert len(result[0]["values"]) == 1


# -- peer_comparison --


def test_upsert_and_get_peers(store: FlowStore):
    """Round-trip peer comparison data."""
    peers = [
        {"name": "Bank of Baroda", "peer_symbol": "BOB", "cmp": 250.0, "pe": 7.0, "market_cap": 50000.0},
        {"name": "PNB", "peer_symbol": "PNB", "cmp": 100.0, "pe": 8.0, "market_cap": 20000.0},
    ]
    count = store.upsert_peers("SBIN", peers)
    assert count == 2

    result = store.get_peers("SBIN")
    assert len(result) == 2
    # Ordered by market_cap DESC
    assert result[0]["market_cap"] >= result[1]["market_cap"]


def test_get_peers_empty_db(store: FlowStore):
    """Returns empty list when no peer data exists."""
    assert store.get_peers("UNKNOWN") == []


def test_upsert_peers_name_field_variants(store: FlowStore):
    """Peers use 'name' field (or 'sno' fallback) from dict."""
    peers = [{"name": "HDFC Bank", "cmp": 1700.0, "pe": 20.0, "market_cap": 1200000.0}]
    count = store.upsert_peers("SBIN", peers)
    assert count == 1

    result = store.get_peers("SBIN")
    assert result[0]["peer_name"] == "HDFC Bank"


# -- shareholder_detail --


def test_upsert_and_get_shareholder_details(store: FlowStore):
    """Round-trip shareholder details with classification structure."""
    data = {
        "Promoter": [
            {"name": "Govt of India", "values": {"Mar 2025": 57.5, "Dec 2024": 57.6}},
        ],
        "FII": [
            {"name": "Vanguard", "values": {"Mar 2025": 2.1}},
            {"name": "BlackRock", "values": {"Mar 2025": 1.8}},
        ],
    }
    count = store.upsert_shareholder_details("SBIN", data)
    assert count == 4  # 2 + 1 + 1

    result = store.get_shareholder_details("SBIN")
    assert len(result) == 4


def test_get_shareholder_details_classification_filter(store: FlowStore):
    """Filter by classification returns only matching holders."""
    data = {
        "Promoter": [
            {"name": "Govt of India", "values": {"Mar 2025": 57.5}},
        ],
        "FII": [
            {"name": "Vanguard", "values": {"Mar 2025": 2.1}},
        ],
    }
    store.upsert_shareholder_details("SBIN", data)

    result = store.get_shareholder_details("SBIN", classification="Promoter")
    assert len(result) == 1
    assert result[0]["classification"] == "Promoter"
    assert result[0]["holder_name"] == "Govt of India"


def test_get_shareholder_details_empty_db(store: FlowStore):
    """Returns empty list when no data exists."""
    assert store.get_shareholder_details("UNKNOWN") == []


# -- financial_schedules --


def test_upsert_and_get_schedules(store: FlowStore):
    """Round-trip schedule data with section/parent/sub_item structure."""
    data = {
        "Interest Earned": {"Mar 2025": 52000.0, "Mar 2024": 48000.0},
        "Other Income": {"Mar 2025": 5000.0, "Mar 2024": 4500.0},
    }
    count = store.upsert_schedules("SBIN", "profit-loss", "Revenue", data)
    assert count == 4  # 2 sub_items x 2 periods

    result = store.get_schedules("SBIN", section="profit-loss")
    assert len(result) == 4


def test_get_schedules_section_filter(store: FlowStore):
    """Section filter returns only matching section."""
    data1 = {"Interest Earned": {"Mar 2025": 52000.0}}
    data2 = {"Total Assets": {"Mar 2025": 500000.0}}
    store.upsert_schedules("SBIN", "profit-loss", "Revenue", data1)
    store.upsert_schedules("SBIN", "balance-sheet", "Assets", data2)

    pl_result = store.get_schedules("SBIN", section="profit-loss")
    assert len(pl_result) == 1
    assert pl_result[0]["section"] == "profit-loss"

    bs_result = store.get_schedules("SBIN", section="balance-sheet")
    assert len(bs_result) == 1
    assert bs_result[0]["section"] == "balance-sheet"


def test_get_schedules_no_filter_returns_all(store: FlowStore):
    """Without section filter, returns all sections."""
    data1 = {"Interest Earned": {"Mar 2025": 52000.0}}
    data2 = {"Total Assets": {"Mar 2025": 500000.0}}
    store.upsert_schedules("SBIN", "profit-loss", "Revenue", data1)
    store.upsert_schedules("SBIN", "balance-sheet", "Assets", data2)

    result = store.get_schedules("SBIN")
    assert len(result) == 2


def test_get_schedules_empty_db(store: FlowStore):
    """Returns empty list when no schedule data exists."""
    assert store.get_schedules("UNKNOWN") == []


def test_upsert_schedules_skips_none_values(store: FlowStore):
    """None values in data dict are skipped."""
    data = {"Interest Earned": {"Mar 2025": 52000.0, "Mar 2024": None}}
    count = store.upsert_schedules("SBIN", "profit-loss", "Revenue", data)
    assert count == 1  # Only the non-None value


def test_upsert_shareholder_details_skips_none_pct(store: FlowStore):
    """None percentage values are skipped."""
    data = {
        "Promoter": [
            {"name": "Govt of India", "values": {"Mar 2025": 57.5, "Dec 2024": None}},
        ],
    }
    count = store.upsert_shareholder_details("SBIN", data)
    assert count == 1  # Only the non-None value
