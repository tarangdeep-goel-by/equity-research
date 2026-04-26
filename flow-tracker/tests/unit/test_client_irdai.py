"""Tests for irdai_client.py — Net Premium Earned ingestion path.

Covers parsing, validation, lookup, backfill round-trip, and the integration
with ``ResearchDataAPI._apply_insurance_headline`` (the swap layer flips off
the ``data_quality_note`` once the column is populated).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from flowtracker.fund_models import AnnualFinancials, QuarterlyResult
from flowtracker.irdai_client import (
    IRDAIClient,
    IRDAIClientError,
    backfill_all,
    backfill_symbol,
    default_client,
)
from flowtracker.irdai_models import NetPremiumDatapoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_dataset() -> dict:
    """A minimal in-memory dataset with two insurers covering both annual and quarterly."""
    return {
        "_meta": {"description": "test fixture"},
        "datapoints": [
            {
                "symbol": "HDFCLIFE",
                "fiscal_period": "FY25",
                "period_end": "2025-03-31",
                "net_premium_earned_cr": 70537.0,
                "source_url": "https://example.test/hdfclife-fy25",
            },
            {
                "symbol": "HDFCLIFE",
                "fiscal_period": "FY25-Q4",
                "period_end": "2025-03-31",
                "net_premium_earned_cr": 23522.0,
                "source_url": "https://example.test/hdfclife-fy25q4",
            },
            {
                "symbol": "SBILIFE",
                "fiscal_period": "FY25",
                "period_end": "2025-03-31",
                "net_premium_earned_cr": 84493.0,
                "source_url": "https://example.test/sbilife-fy25",
            },
        ],
    }


@pytest.fixture
def fake_client(fake_dataset: dict) -> IRDAIClient:
    return IRDAIClient(dataset=fake_dataset)


# ---------------------------------------------------------------------------
# NetPremiumDatapoint model
# ---------------------------------------------------------------------------


class TestNetPremiumDatapoint:
    """Construction, validation, optional fields, computed properties."""

    def test_minimal_construction(self):
        p = NetPremiumDatapoint(
            symbol="HDFCLIFE",
            fiscal_period="FY25",
            period_end="2025-03-31",
            net_premium_earned_cr=70537.0,
        )
        assert p.symbol == "HDFCLIFE"
        assert p.fiscal_period == "FY25"
        assert p.period_end == "2025-03-31"
        assert p.net_premium_earned_cr == 70537.0
        assert p.source_url is None
        assert p.fetched_at is None

    def test_symbol_uppercased(self):
        p = NetPremiumDatapoint(
            symbol="hdfclife",
            fiscal_period="FY25",
            period_end="2025-03-31",
            net_premium_earned_cr=100.0,
        )
        assert p.symbol == "HDFCLIFE"

    def test_fiscal_period_uppercased(self):
        p = NetPremiumDatapoint(
            symbol="HDFCLIFE",
            fiscal_period="fy25-q3",
            period_end="2024-12-31",
            net_premium_earned_cr=100.0,
        )
        assert p.fiscal_period == "FY25-Q3"

    @pytest.mark.parametrize(
        "bad_period",
        ["FY2025", "FY25-Q5", "Q1FY25", "FY-25", "2025FY", "FY25-X"],
    )
    def test_bad_fiscal_period_rejected(self, bad_period: str):
        with pytest.raises(ValidationError):
            NetPremiumDatapoint(
                symbol="HDFCLIFE",
                fiscal_period=bad_period,
                period_end="2025-03-31",
                net_premium_earned_cr=100.0,
            )

    @pytest.mark.parametrize(
        "bad_date", ["31-03-2025", "2025/03/31", "March 2025", "20250331"]
    )
    def test_bad_period_end_rejected(self, bad_date: str):
        with pytest.raises(ValidationError):
            NetPremiumDatapoint(
                symbol="HDFCLIFE",
                fiscal_period="FY25",
                period_end=bad_date,
                net_premium_earned_cr=100.0,
            )

    def test_zero_premium_rejected(self):
        with pytest.raises(ValidationError):
            NetPremiumDatapoint(
                symbol="HDFCLIFE",
                fiscal_period="FY25",
                period_end="2025-03-31",
                net_premium_earned_cr=0.0,
            )

    def test_negative_premium_rejected(self):
        with pytest.raises(ValidationError):
            NetPremiumDatapoint(
                symbol="HDFCLIFE",
                fiscal_period="FY25",
                period_end="2025-03-31",
                net_premium_earned_cr=-100.0,
            )

    def test_unit_error_lakh_for_crore_rejected(self):
        # 100 lakh = 100 Cr × 100 — anything > 10 lakh Cr is suspect.
        with pytest.raises(ValidationError) as exc_info:
            NetPremiumDatapoint(
                symbol="LICI",
                fiscal_period="FY25",
                period_end="2025-03-31",
                net_premium_earned_cr=489626.0 * 100,
            )
        assert "unit error" in str(exc_info.value).lower()

    def test_is_annual_vs_quarterly(self):
        annual = NetPremiumDatapoint(
            symbol="X", fiscal_period="FY25", period_end="2025-03-31",
            net_premium_earned_cr=1.0,
        )
        quarterly = NetPremiumDatapoint(
            symbol="X", fiscal_period="FY25-Q1", period_end="2024-06-30",
            net_premium_earned_cr=1.0,
        )
        assert annual.is_annual and not annual.is_quarterly
        assert quarterly.is_quarterly and not quarterly.is_annual


# ---------------------------------------------------------------------------
# IRDAIClient construction + lookup
# ---------------------------------------------------------------------------


class TestIRDAIClient:
    def test_init_with_explicit_dataset(self, fake_client: IRDAIClient):
        assert fake_client.covered_symbols == ["HDFCLIFE", "SBILIFE"]
        assert fake_client.has_symbol("HDFCLIFE")
        assert fake_client.has_symbol("hdfclife")  # case-insensitive
        assert not fake_client.has_symbol("UNKNOWN")

    def test_load_bundled_dataset(self):
        # Smoke-test: the bundled JSON must load + validate cleanly.
        client = IRDAIClient()
        assert "HDFCLIFE" in client.covered_symbols
        assert "SBILIFE" in client.covered_symbols
        assert "ICICIPRULI" in client.covered_symbols
        assert "LICI" in client.covered_symbols
        # We expect FY24/FY25 annual + FY24-Q1..FY26-Q3 quarterly per insurer = 13.
        for sym in ["HDFCLIFE", "SBILIFE", "ICICIPRULI", "LICI"]:
            rows = client.fetch_all_for_symbol(sym)
            assert len(rows) >= 10, f"{sym} only has {len(rows)} rows"

    def test_fetch_one_returns_datapoint(self, fake_client: IRDAIClient):
        p = fake_client.fetch_net_premium_earned("HDFCLIFE", "FY25")
        assert p is not None
        assert p.net_premium_earned_cr == 70537.0
        assert p.source_url == "https://example.test/hdfclife-fy25"

    def test_fetch_one_unknown_symbol(self, fake_client: IRDAIClient):
        assert fake_client.fetch_net_premium_earned("UNKNOWN", "FY25") is None

    def test_fetch_one_unknown_period(self, fake_client: IRDAIClient):
        assert fake_client.fetch_net_premium_earned("HDFCLIFE", "FY99") is None

    def test_fetch_one_case_insensitive(self, fake_client: IRDAIClient):
        p = fake_client.fetch_net_premium_earned("hdfclife", "fy25")
        assert p is not None
        assert p.net_premium_earned_cr == 70537.0

    def test_annual_lookup_only_annual(self, fake_client: IRDAIClient):
        out = fake_client.annual_lookup("HDFCLIFE")
        # FY25 is annual, FY25-Q4 is quarterly — only annual should appear.
        assert out == {"2025-03-31": 70537.0}

    def test_quarterly_lookup_only_quarterly(self, fake_client: IRDAIClient):
        out = fake_client.quarterly_lookup("HDFCLIFE")
        assert out == {"2025-03-31": 23522.0}

    def test_default_client_is_singleton(self):
        a = default_client()
        b = default_client()
        assert a is b

    def test_malformed_dataset_raises(self):
        with pytest.raises(IRDAIClientError):
            IRDAIClient(dataset={"datapoints": "not a list"})

    def test_malformed_row_raises_validation_error(self):
        with pytest.raises(ValidationError):
            IRDAIClient(
                dataset={
                    "datapoints": [
                        {
                            "symbol": "HDFCLIFE",
                            "fiscal_period": "FY25",
                            "period_end": "31-03-2025",  # bad
                            "net_premium_earned_cr": 100.0,
                        }
                    ]
                }
            )

    def test_missing_bundled_file(self, monkeypatch):
        # Simulate the data file not being shipped — should raise IRDAIClientError.
        from flowtracker import irdai_client as mod

        def boom(*_args, **_kwargs):
            raise FileNotFoundError("simulated missing file")

        monkeypatch.setattr(
            mod.IRDAIClient, "_load_bundled", staticmethod(boom)
        )
        with pytest.raises(IRDAIClientError):
            IRDAIClient()


# ---------------------------------------------------------------------------
# Backfill round-trip — store side
# ---------------------------------------------------------------------------


class TestBackfillSymbol:
    def test_backfill_round_trip_annual(self, store, fake_client):
        store.upsert_annual_financials([
            AnnualFinancials(
                symbol="HDFCLIFE",
                fiscal_year_end="2025-03-31",
                revenue=999.0,
            )
        ])
        stats = backfill_symbol("HDFCLIFE", store, client=fake_client)
        assert stats["annual"] == 1
        # Read back via store accessor.
        rows = store.get_annual_financials("HDFCLIFE", limit=5)
        assert len(rows) == 1
        assert rows[0].net_premium_earned == 70537.0
        # Revenue must be unchanged — this is an additive enrichment.
        assert rows[0].revenue == 999.0

    def test_backfill_round_trip_quarterly(self, store, fake_client):
        store.upsert_quarterly_results([
            QuarterlyResult(
                symbol="HDFCLIFE", quarter_end="2025-03-31", revenue=200.0,
            )
        ])
        stats = backfill_symbol("HDFCLIFE", store, client=fake_client)
        assert stats["quarterly"] == 1
        rows = store.get_quarterly_results("HDFCLIFE", limit=5)
        assert rows[0].net_premium_earned == 23522.0
        assert rows[0].revenue == 200.0

    def test_backfill_missing_row_counted(self, store, fake_client):
        # No annual_financials seeded — every IRDAI row is missing-row.
        stats = backfill_symbol("HDFCLIFE", store, client=fake_client)
        assert stats["annual"] == 0
        assert stats["quarterly"] == 0
        assert stats["missing"] == 2  # one annual + one quarterly in fake_client

    def test_backfill_unknown_symbol_is_noop(self, store, fake_client):
        stats = backfill_symbol("UNKNOWN", store, client=fake_client)
        assert stats == {"annual": 0, "quarterly": 0, "missing": 0}

    def test_backfill_all_covers_every_insurer(self, store, fake_client):
        # Seed one annual row per covered insurer.
        store.upsert_annual_financials([
            AnnualFinancials(symbol="HDFCLIFE", fiscal_year_end="2025-03-31", revenue=1.0),
            AnnualFinancials(symbol="SBILIFE", fiscal_year_end="2025-03-31", revenue=1.0),
        ])
        results = backfill_all(store, client=fake_client)
        assert set(results.keys()) == {"HDFCLIFE", "SBILIFE"}
        assert results["HDFCLIFE"]["annual"] == 1
        assert results["SBILIFE"]["annual"] == 1

    def test_backfill_all_4_listed_insurers_with_bundled_data(self, store):
        """The shipped dataset must cover all 4 listed insurers — the headline
        contract of this work item. Seed annual rows for all 4 then verify
        backfill populates each one."""
        client = IRDAIClient()
        for sym in ["HDFCLIFE", "SBILIFE", "ICICIPRULI", "LICI"]:
            store.upsert_annual_financials([
                AnnualFinancials(symbol=sym, fiscal_year_end="2025-03-31", revenue=1.0)
            ])
        results = backfill_all(store, client=client)
        for sym in ["HDFCLIFE", "SBILIFE", "ICICIPRULI", "LICI"]:
            assert results[sym]["annual"] >= 1, (
                f"{sym} not enriched — bundled dataset missing FY25 row"
            )
            rows = store.get_annual_financials(sym, limit=5)
            assert any(r.net_premium_earned for r in rows), (
                f"{sym} annual_financials row not populated after backfill_all"
            )


# ---------------------------------------------------------------------------
# Integration with ResearchDataAPI._apply_insurance_headline (swap layer)
# ---------------------------------------------------------------------------


class TestSwapLayerIntegration:
    """End-to-end: backfill IRDAI → swap layer flips data_quality_note off."""

    def _seed_insurer_industry(self, store, symbol: str) -> None:
        """Tag the symbol as 'Life Insurance' so ``_is_insurance`` returns True."""
        store._conn.execute(
            "INSERT OR REPLACE INTO company_snapshot "
            "(symbol, industry, updated_at) VALUES (?, ?, datetime('now'))",
            (symbol, "Life Insurance"),
        )
        store._conn.commit()

    def _make_api(self, monkeypatch, tmp_db: Path):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.data_api import ResearchDataAPI
        return ResearchDataAPI()

    def test_before_backfill_data_quality_note_present(self, store, monkeypatch, tmp_db):
        self._seed_insurer_industry(store, "HDFCLIFE")
        store.upsert_annual_financials([
            AnnualFinancials(symbol="HDFCLIFE", fiscal_year_end="2025-03-31", revenue=120000.0)
        ])
        store.close()  # release SQLite handle so ResearchDataAPI can reopen
        api = self._make_api(monkeypatch, tmp_db)
        rows = api.get_annual_financials("HDFCLIFE")
        assert rows
        row = rows[0]
        # No npe → fallback path: headline = revenue, data_quality_note set.
        assert row["net_premium_earned"] is None
        assert row["headline_revenue"] == 120000.0
        assert "data_quality_note" in row
        assert "Net Premium Earned" in row["data_quality_note"]

    def test_after_backfill_swap_layer_uses_npe_no_note(
        self, store, fake_client, monkeypatch, tmp_db
    ):
        self._seed_insurer_industry(store, "HDFCLIFE")
        store.upsert_annual_financials([
            AnnualFinancials(symbol="HDFCLIFE", fiscal_year_end="2025-03-31", revenue=120000.0)
        ])
        backfill_symbol("HDFCLIFE", store, client=fake_client)
        store.close()
        api = self._make_api(monkeypatch, tmp_db)
        rows = api.get_annual_financials("HDFCLIFE")
        assert rows
        row = rows[0]
        assert row["net_premium_earned"] == 70537.0
        # Swap layer flips: headline = NPE; data_quality_note must be gone.
        assert row["headline_revenue"] == 70537.0
        assert row["headline_metric"] == "net_premium_earned"
        assert "data_quality_note" not in row
        assert "notes" in row and "Net Premium Earned" in row["notes"]
        # Original revenue preserved (additive transform).
        assert row["revenue"] == 120000.0

    def test_after_backfill_quarterly_swap_layer(
        self, store, fake_client, monkeypatch, tmp_db
    ):
        self._seed_insurer_industry(store, "HDFCLIFE")
        store.upsert_quarterly_results([
            QuarterlyResult(symbol="HDFCLIFE", quarter_end="2025-03-31", revenue=30000.0)
        ])
        backfill_symbol("HDFCLIFE", store, client=fake_client)
        store.close()
        api = self._make_api(monkeypatch, tmp_db)
        rows = api.get_quarterly_results("HDFCLIFE")
        assert rows
        row = rows[0]
        assert row["net_premium_earned"] == 23522.0
        assert row["headline_revenue"] == 23522.0
        assert "data_quality_note" not in row
