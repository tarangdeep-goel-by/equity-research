#!/usr/bin/env python3
"""One-time backfill: 3 years of Nifty 500 (^CRSLDX) and Nifty 50 (^NSEI) daily prices."""

from flowtracker.macro_client import MacroClient
from flowtracker.store import FlowStore


def main() -> None:
    with MacroClient() as client, FlowStore() as store:
        records = client.fetch_index_prices(
            tickers=["^CRSLDX", "^NSEI"],
            period="3y",
        )
        if records:
            count = store.upsert_index_daily_prices(records)
            print(f"Backfilled {count} index price records")
            # Show date range
            dates = sorted(set(r["date"] for r in records))
            print(f"Date range: {dates[0]} to {dates[-1]}")
            for ticker in ["^CRSLDX", "^NSEI"]:
                n = sum(1 for r in records if r["index_ticker"] == ticker)
                print(f"  {ticker}: {n} days")
        else:
            print("No data fetched — check network/yfinance")


if __name__ == "__main__":
    main()
