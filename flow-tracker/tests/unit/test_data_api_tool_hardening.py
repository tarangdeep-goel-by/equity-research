"""Phase-2 tool-layer hardening fixes (feat/tool-layer-hardening).

Covers:
  1. _percentile_rank / get_valuation_matrix tolerate non-numeric ('-') values
  2. enterprise_value recomputed after a share-count reconcile (EV inflation)
  5. get_listed_subsidiaries curated-map fallback (NTPC -> NTPCGREEN)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI, _percentile_rank
from flowtracker.store import FlowStore


@pytest.fixture
def api(tmp_db: Path, monkeypatch) -> ResearchDataAPI:
    FlowStore(db_path=tmp_db).close()
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# --- Fix 1: non-numeric tolerance ---

class TestPercentileRankTolerance:
    def test_drops_non_numeric_values_no_raise(self):
        # A '-' placeholder mixed into a numeric column must not raise.
        out = _percentile_rank([10.0, 20.0, "-", 30.0], 25.0)
        # 2 of the 3 numeric values (10, 20) are below 25 -> 67%.
        assert out == round(100 * 2 / 3)

    def test_non_numeric_target_returns_zero(self):
        assert _percentile_rank([10.0, 20.0, 30.0], "-") == 0

    def test_all_non_numeric_returns_zero(self):
        assert _percentile_rank(["-", "NA"], 5.0) == 0


class TestValuationMatrixTolerance:
    def test_dash_in_numeric_column_does_not_raise(self, api: ResearchDataAPI):
        store = api._store
        # Subject + 2 peers; one peer's pe_trailing is a Screener '-' string.
        store._conn.execute(
            "INSERT INTO company_snapshot (symbol, pe_trailing, pb) "
            "VALUES ('SUBJ', 25.0, 4.0)"
        )
        store._conn.execute(
            "INSERT INTO company_snapshot (symbol, pe_trailing, pb) "
            "VALUES ('PEER1', 30.0, 5.0)"
        )
        store._conn.execute(
            "INSERT INTO company_snapshot (symbol, pe_trailing, pb) "
            "VALUES ('PEER2', '-', 6.0)"  # contaminated numeric column
        )
        store._conn.execute(
            "INSERT INTO peer_links (symbol, peer_symbol, score) VALUES ('SUBJ', 'PEER1', 1.0)"
        )
        store._conn.execute(
            "INSERT INTO peer_links (symbol, peer_symbol, score) VALUES ('SUBJ', 'PEER2', 2.0)"
        )
        store._conn.commit()

        # Must not raise "'<' not supported between float and str".
        out = api.get_valuation_matrix("SUBJ")
        # pb column (3 clean numerics) still computes stats.
        assert "pb" in out["sector_stats"]
        # subject pb percentile is computed without error.
        assert "pb" in out["subject_percentiles"]


# --- Fix 2: EV recompute after reconcile ---

class TestEnterpriseValueReconcile:
    def test_ev_recomputed_from_corrected_mcap(self, tmp_db, monkeypatch):
        """After a 2x-share reconcile, EV = mcap + total_debt - total_cash
        (all in crores), not the stale yfinance EV."""
        from flowtracker.fund_models import AnnualFinancials, ValuationSnapshot

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with FlowStore(tmp_db) as store:
            # yfinance: 2x shares + 2x mcap + 2x EV (the bug).
            store.upsert_valuation_snapshot(ValuationSnapshot(
                symbol="PIDILITIND",
                date=date.today().isoformat(),
                price=3000.0,
                market_cap=305000.0,          # doubled yfinance mcap
                enterprise_value=303000.0,     # stale doubled EV
                shares_outstanding=1_016_666_666,  # ~2x
                total_debt=1000.0,             # crores
                total_cash=3000.0,             # crores
                pe_trailing=80.0,
            ))
            # Screener: correct ~508M shares.
            store.upsert_annual_financials([AnnualFinancials(
                symbol="PIDILITIND",
                fiscal_year_end="2025-03-31",
                num_shares=508_000_000.0,
                revenue=12000.0,
                net_income=1500.0,
            )])

        api = ResearchDataAPI()
        try:
            snap = api.get_valuation_snapshot("PIDILITIND")
        finally:
            api.close()

        corrected_mcap = round(3000.0 * 508_000_000 / 1e7, 2)
        assert abs(snap["market_cap"] - corrected_mcap) < 1.0
        # EV recomputed from corrected mcap (+debt -cash), not the stale 303000.
        expected_ev = round(corrected_mcap + 1000.0 - 3000.0, 2)
        assert abs(snap["enterprise_value"] - expected_ev) < 1.0
        assert snap["enterprise_value"] < 200000.0  # nowhere near the stale 2x value


# --- Fix 5: curated SOTP fallback ---

class TestCuratedSubsidiaryFallback:
    def _seed_parent_shares(self, store, symbol):
        store._conn.execute(
            "INSERT INTO valuation_snapshot (symbol, date, shares_outstanding) "
            "VALUES (?, ?, 9700000000)",
            (symbol, date.today().isoformat()),
        )
        store._conn.commit()

    def test_ntpc_includes_curated_ntpcgreen(self, api: ResearchDataAPI, monkeypatch):
        import sys
        import types

        self._seed_parent_shares(api._store, "NTPC")
        # Stub yfinance so curated rows get priced (mcap 0 is fine).
        monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
            Ticker=lambda sym: type("T", (), {"info": {"marketCap": 0}})()
        ))
        out = api.get_listed_subsidiaries("NTPC")
        assert out is not None
        green = [s for s in out["subsidiaries"] if s["symbol"] == "NTPCGREEN"]
        assert len(green) == 1
        assert green[0]["source"] == "curated_map"
        assert "confirm" in green[0]["verify_note"].lower()

    def test_db_rows_take_precedence_over_curated(self, api: ResearchDataAPI, monkeypatch):
        import sys
        import types

        # Real DB row for NTPC -> curated map must NOT be merged in.
        api._store.upsert_listed_subsidiary("NTPC", "REALSUB", "Real Sub", 70.0, "Sub")
        self._seed_parent_shares(api._store, "NTPC")
        monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
            Ticker=lambda sym: type("T", (), {"info": {"marketCap": 0}})()
        ))
        out = api.get_listed_subsidiaries("NTPC")
        syms = {s["symbol"] for s in out["subsidiaries"]}
        assert "REALSUB" in syms
        assert "NTPCGREEN" not in syms  # curated suppressed when DB has rows

    def test_sbin_curated_has_two_subsidiaries(self, api: ResearchDataAPI, monkeypatch):
        import sys
        import types

        self._seed_parent_shares(api._store, "SBIN")
        monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(
            Ticker=lambda sym: type("T", (), {"info": {"marketCap": 0}})()
        ))
        out = api.get_listed_subsidiaries("SBIN")
        syms = {s["symbol"] for s in out["subsidiaries"]}
        assert {"SBILIFE", "SBICARD"} <= syms


# --- Fix 4: DCF growth cap raised 0.30 -> 0.45 ---

class TestDcfGrowthCap:
    def _seed_fcf_history(self, store, symbol, fcfs):
        """fcfs is most-recent-first; stored as cfo (cfi=0)."""
        from flowtracker.fund_models import AnnualFinancials
        rows = []
        for i, fcf in enumerate(fcfs):
            year = 2025 - i
            rows.append(AnnualFinancials(
                symbol=symbol,
                fiscal_year_end=f"{year}-03-31",
                revenue=10000.0,
                net_income=1000.0,
                cfo=fcf,
                cfi=0.0,
            ))
        store.upsert_annual_financials(rows)

    def test_cagr_between_30_and_45_now_unknown(self, api: ResearchDataAPI):
        # 5y FCF: oldest=100, latest=332 -> CAGR ~35% (was rejected at 0.30 cap).
        self._seed_fcf_history(api._store, "PIDILITIND", [332.0, 250.0, 180.0, 130.0, 100.0])
        assert api._classify_dcf_empty_reason("PIDILITIND") == "unknown"

    def test_cagr_above_45_still_rejected(self, api: ResearchDataAPI):
        # 5y FCF: oldest=100, latest=506 -> CAGR ~50% (still implausible).
        self._seed_fcf_history(api._store, "WILDGROW", [506.0, 340.0, 225.0, 150.0, 100.0])
        assert api._classify_dcf_empty_reason("WILDGROW") == "growth_above_limits"


# --- Fix 3: reverse-DCF wider-window market-cap fallback ---

class TestReverseDcfMcapFallback:
    def test_uses_wider_window_when_7day_misses(self, api: ResearchDataAPI):
        from datetime import timedelta

        from flowtracker.fund_models import AnnualFinancials

        # 2 years of financials so reverse_dcf gets past the early guard.
        api._store.upsert_annual_financials([
            AnnualFinancials(
                symbol="HINDUNILVR", fiscal_year_end="2025-03-31",
                revenue=60000.0, net_income=10000.0, profit_before_tax=13000.0,
                tax=3000.0, cfo=11000.0, net_block=5000.0, cwip=200.0,
                depreciation=1000.0, equity_capital=235.0, reserves=50000.0,
            ),
            AnnualFinancials(
                symbol="HINDUNILVR", fiscal_year_end="2024-03-31",
                revenue=58000.0, net_income=9500.0, profit_before_tax=12500.0,
                tax=2900.0, cfo=10500.0, net_block=4800.0, cwip=180.0,
                depreciation=950.0, equity_capital=235.0, reserves=47000.0,
            ),
        ])
        # Market-cap row is 30 days old -> outside the snapshot's 7-day window,
        # inside the reverse_dcf 90-day fallback.
        stale_date = (date.today() - timedelta(days=30)).isoformat()
        api._store._conn.execute(
            "INSERT INTO valuation_snapshot (symbol, date, price, market_cap, pe_trailing) "
            "VALUES ('HINDUNILVR', ?, 2400.0, 564000.0, 55.0)",
            (stale_date,),
        )
        api._store._conn.commit()

        out = api.get_reverse_dcf("HINDUNILVR")
        # Pre-fix this returned {"error": "No market cap data"}.
        assert "error" not in out or out.get("error") != "No market cap data"
