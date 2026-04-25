"""SOTP auto-discovery tests (PR-14, issue #11). Today-relative dates."""

from __future__ import annotations

import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


def _seed_listing(s, sym, listed_on):
    s._conn.execute(
        "INSERT INTO daily_stock_data (date, symbol, open, high, low, close, "
        "prev_close, volume, turnover) VALUES (?, ?, 100, 105, 95, 100, 100, 1000, 1e5)",
        (listed_on.isoformat(), sym),
    )
    s._conn.commit()


def _seed_promoter(s, sym, holder, pct, q):
    s._conn.execute(
        "INSERT INTO shareholder_detail (symbol, classification, holder_name, "
        "quarter, percentage) VALUES (?, 'Promoters', ?, ?, ?)",
        (sym, holder, q, pct),
    )
    s._conn.commit()


def _seed_company(s, sym, name):
    s._conn.execute(
        "INSERT INTO index_constituents (symbol, index_name, company_name, industry) "
        "VALUES (?, 'NIFTY 50', ?, 'Test')",
        (sym, name),
    )
    s._conn.commit()


def _seed_ntpc_with_green(api, days_ago=60):
    today = date.today()
    _seed_company(api._store, "NTPC", "NTPC LIMITED")
    _seed_listing(api._store, "NTPCGREEN", today - timedelta(days=days_ago))
    _seed_promoter(api._store, "NTPCGREEN", "NTPC Limited", 88.0, "Mar 2026")


def test_discover_recent_listings_finds_within_window(api):
    today = date.today()
    _seed_listing(api._store, "FRESH30", today - timedelta(days=30))
    _seed_listing(api._store, "OLD200", today - timedelta(days=200))
    _seed_listing(api._store, "FRESH90", today - timedelta(days=90))
    syms = {r["symbol"] for r in api._discover_recent_listings(days=180)}
    assert syms == {"FRESH30", "FRESH90"}


def test_discover_recent_listings_empty_when_no_recent(api):
    _seed_listing(api._store, "OLD1", date.today() - timedelta(days=400))
    assert api._discover_recent_listings(days=180) == []


def test_find_promoter_owned_children_substring_match(api):
    _seed_company(api._store, "NTPC", "NTPC LIMITED")
    _seed_promoter(api._store, "NTPCGREEN", "NTPC Limited", 89.0, "Mar 2026")
    hits = api._find_promoter_owned_children("NTPC", ["NTPCGREEN"], min_pct=50.0)
    assert len(hits) == 1 and hits[0]["symbol"] == "NTPCGREEN"
    assert hits[0]["parent_ownership_pct"] == 89.0
    assert hits[0]["last_quarter"] == "Mar 2026"


def test_find_promoter_owned_children_no_match_below_threshold(api):
    _seed_company(api._store, "NTPC", "NTPC LIMITED")
    _seed_promoter(api._store, "NTPCGREEN", "NTPC Limited", 30.0, "Mar 2026")
    assert api._find_promoter_owned_children("NTPC", ["NTPCGREEN"], min_pct=50.0) == []


def test_find_promoter_owned_children_no_match_unrelated_promoter(api):
    _seed_company(api._store, "NTPC", "NTPC LIMITED")
    _seed_promoter(api._store, "RANDOMCO", "Some Random Holdings", 75.0, "Mar 2026")
    assert api._find_promoter_owned_children("NTPC", ["RANDOMCO"], min_pct=50.0) == []


def test_get_listed_subsidiaries_augments_with_auto_discovered(api, monkeypatch):
    _seed_ntpc_with_green(api)
    api._store.upsert_listed_subsidiary("NTPC", "OLDCURATED", "Old Curated", 60.0, "Sub")
    api._store._conn.execute(
        "INSERT INTO valuation_snapshot (symbol, date, shares_outstanding) "
        "VALUES ('NTPC', ?, 9700000000)",
        (date.today().isoformat(),),
    )
    api._store._conn.commit()
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
        Ticker=lambda sym: type("T", (), {"info": {"marketCap": 0}})()
    ))
    out = api.get_listed_subsidiaries("NTPC")
    assert out and len(out["subsidiaries"]) == 1
    assert len(out["auto_discovered_candidates"]) == 1
    assert out["auto_discovered_candidates"][0]["symbol"] == "NTPCGREEN"
    assert out["auto_discovered_candidates"][0]["confidence"] == "auto_discovered_needs_verification"


def test_get_listed_subsidiaries_zero_manual_with_auto_returns_dict(api):
    _seed_ntpc_with_green(api)
    out = api.get_listed_subsidiaries("NTPC")
    assert out and out["subsidiaries"] == []
    assert len(out["auto_discovered_candidates"]) == 1
    assert out["auto_discovered_candidates"][0]["symbol"] == "NTPCGREEN"


def test_get_listed_subsidiaries_zero_manual_zero_auto_returns_none(api):
    _seed_company(api._store, "NTPC", "NTPC LIMITED")
    assert api.get_listed_subsidiaries("NTPC") is None


def test_auto_discovery_window_meta_present(api):
    _seed_ntpc_with_green(api)
    out = api.get_listed_subsidiaries("NTPC")
    assert out["_meta"]["auto_discovery_window_days"] == 180


def test_company_name_normalization():
    assert (
        ResearchDataAPI._clean_company_name("NTPC LIMITED")
        == ResearchDataAPI._clean_company_name("ntpc Ltd.")
        == "ntpc"
    )
