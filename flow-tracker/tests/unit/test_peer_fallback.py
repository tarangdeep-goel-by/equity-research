"""Regression test for get_peer_comparison() auto-fallback to Screener."""
from unittest.mock import MagicMock
from flowtracker.research.data_api import ResearchDataAPI


def _make_api(subject_snap, peer_links, peer_snaps, screener_peers, screener_snaps):
    """Build a ResearchDataAPI with a mocked store for fallback tests."""
    store = MagicMock()
    store.get_company_snapshot.return_value = subject_snap
    store.get_peer_links.return_value = peer_links
    store.get_peers.return_value = screener_peers

    def _snapshots(symbols):
        pool = {s["symbol"]: s for s in (peer_snaps + screener_snaps)}
        return [pool[s] for s in symbols if s in pool]

    store.get_company_snapshots.side_effect = _snapshots

    api = ResearchDataAPI()
    api._store = store
    return api


def test_get_peer_comparison_empty_yahoo_falls_back_to_screener():
    api = _make_api(
        subject_snap={"symbol": "BANKBARODA", "industry": "Banks - Regional"},
        peer_links=[],
        peer_snaps=[],
        screener_peers=[{"peer_symbol": "CANBK"}, {"peer_symbol": "PNB"}],
        screener_snaps=[
            {"symbol": "CANBK", "industry": "Banks - Regional"},
            {"symbol": "PNB", "industry": "Banks - Regional"},
        ],
    )
    result = api.get_peer_comparison("BANKBARODA")
    assert result["source"] == "screener_fallback"
    assert result["fallback_reason"] == "No Yahoo peers found for this symbol"
    assert result["peer_count"] == 2
    assert all(p.get("screener_fallback") for p in result["peers"])


def test_get_peer_comparison_sector_mismatch_falls_back_to_screener():
    api = _make_api(
        subject_snap={"symbol": "SBIN", "industry": "Banks - Regional"},
        peer_links=[
            {"peer_symbol": "LT", "score": 0.2},
            {"peer_symbol": "RELIANCE", "score": 0.2},
            {"peer_symbol": "TATAMOTORS", "score": 0.2},
            {"peer_symbol": "HDFCBANK", "score": 0.2},
        ],
        peer_snaps=[
            {"symbol": "LT", "industry": "Civil Construction"},
            {"symbol": "RELIANCE", "industry": "Refineries & Marketing"},
            {"symbol": "TATAMOTORS", "industry": "Auto Manufacturers"},
            {"symbol": "HDFCBANK", "industry": "Banks - Regional"},
        ],
        screener_peers=[{"peer_symbol": "CANBK"}, {"peer_symbol": "PNB"}],
        screener_snaps=[
            {"symbol": "CANBK", "industry": "Banks - Regional"},
            {"symbol": "PNB", "industry": "Banks - Regional"},
        ],
    )
    result = api.get_peer_comparison("SBIN")
    assert result["source"] == "screener_fallback"
    assert "mismatched" in result["fallback_reason"]
    assert result["peer_count"] == 2


def test_get_peer_comparison_happy_path_keeps_yahoo():
    api = _make_api(
        subject_snap={"symbol": "SUNPHARMA", "industry": "Pharma"},
        peer_links=[
            {"peer_symbol": "DRREDDY", "score": 0.3},
            {"peer_symbol": "CIPLA", "score": 0.3},
            {"peer_symbol": "LUPIN", "score": 0.3},
            {"peer_symbol": "DIVISLAB", "score": 0.3},
        ],
        peer_snaps=[
            {"symbol": "DRREDDY", "industry": "Pharma"},
            {"symbol": "CIPLA", "industry": "Pharma"},
            {"symbol": "LUPIN", "industry": "Pharma"},
            {"symbol": "DIVISLAB", "industry": "Pharma"},
        ],
        screener_peers=[],
        screener_snaps=[],
    )
    result = api.get_peer_comparison("SUNPHARMA")
    assert result["source"] == "yahoo_recommendations"
    assert "fallback_reason" not in result
    assert result["peer_count"] == 4
    assert all(p.get("yahoo_score") == 0.3 for p in result["peers"])


def test_get_peer_comparison_missing_subject_industry_skips_mismatch_check():
    # If subject has no industry label, we can't validate — return Yahoo as-is.
    api = _make_api(
        subject_snap={"symbol": "NEWSTOCK"},  # no industry
        peer_links=[{"peer_symbol": "XYZ", "score": 0.1}],
        peer_snaps=[{"symbol": "XYZ", "industry": "Anything"}],
        screener_peers=[],
        screener_snaps=[],
    )
    result = api.get_peer_comparison("NEWSTOCK")
    assert result["source"] == "yahoo_recommendations"
    assert result["peer_count"] == 1
