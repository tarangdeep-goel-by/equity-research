"""Data quality tests using populated_store.

Validates logical consistency of fixture data: shareholding sums,
revenue positivity, valuation ranges, and alert-to-data coherence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.store import FlowStore


class TestShareholdingConsistency:
    def test_shareholding_sums_to_approximately_100(self, populated_store: FlowStore):
        """For each symbol+quarter, category percentages should sum to ~100%."""
        for symbol in ("SBIN", "INFY"):
            records = populated_store.get_shareholding(symbol, limit=100)
            if not records:
                continue

            # Group by quarter
            quarters: dict[str, float] = {}
            for r in records:
                quarters.setdefault(r.quarter_end, 0.0)
                quarters[r.quarter_end] += r.percentage

            for qtr, total in quarters.items():
                assert 95.0 <= total <= 105.0, (
                    f"{symbol} {qtr}: shareholding sums to {total:.1f}%, expected ~100%"
                )


class TestRevenuePositivity:
    def test_quarterly_revenue_positive(self, populated_store: FlowStore):
        """All quarterly results should have positive revenue."""
        for symbol in ("SBIN", "INFY"):
            rows = populated_store._conn.execute(
                "SELECT revenue, quarter_end FROM quarterly_results WHERE symbol = ?",
                (symbol,),
            ).fetchall()
            assert len(rows) > 0, f"No quarterly results for {symbol}"
            for row in rows:
                assert row["revenue"] > 0, (
                    f"{symbol} {row['quarter_end']}: revenue is {row['revenue']}"
                )


class TestValuationRange:
    def test_price_within_52w_range(self, populated_store: FlowStore):
        """Current price should be between 52-week low and high."""
        for symbol in ("SBIN", "INFY"):
            rows = populated_store._conn.execute(
                "SELECT price, fifty_two_week_high, fifty_two_week_low "
                "FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchall()
            if not rows:
                continue
            row = rows[0]
            low = row["fifty_two_week_low"]
            high = row["fifty_two_week_high"]
            price = row["price"]
            assert low <= price <= high, (
                f"{symbol}: price {price} outside 52w range [{low}, {high}]"
            )


class TestAlertDataCoherence:
    def test_alert_symbols_have_relevant_data(self, populated_store: FlowStore):
        """Each alert's symbol must have data in the table the condition queries."""
        alerts = populated_store.get_active_alerts()
        assert len(alerts) > 0, "No alerts in populated store"

        for alert in alerts:
            sym = alert.symbol
            ct = alert.condition_type

            if ct in ("price_above", "price_below", "pe_above", "pe_below"):
                row = populated_store._conn.execute(
                    "SELECT COUNT(*) as cnt FROM valuation_snapshot WHERE symbol = ?",
                    (sym,),
                ).fetchone()
                assert row["cnt"] > 0, f"{sym} has {ct} alert but no valuation data"

            elif ct == "pledge_above":
                row = populated_store._conn.execute(
                    "SELECT COUNT(*) as cnt FROM promoter_pledge WHERE symbol = ?",
                    (sym,),
                ).fetchone()
                assert row["cnt"] > 0, f"{sym} has {ct} alert but no pledge data"

            elif ct in ("rsi_below", "rsi_above"):
                row = populated_store._conn.execute(
                    "SELECT COUNT(*) as cnt FROM fmp_technical_indicators "
                    "WHERE symbol = ? AND indicator = 'rsi'",
                    (sym,),
                ).fetchone()
                assert row["cnt"] > 0, f"{sym} has {ct} alert but no RSI data"

            elif ct == "dcf_upside_above":
                row = populated_store._conn.execute(
                    "SELECT COUNT(*) as cnt FROM fmp_dcf WHERE symbol = ?",
                    (sym,),
                ).fetchone()
                assert row["cnt"] > 0, f"{sym} has {ct} alert but no DCF data"
