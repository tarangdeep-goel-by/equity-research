#!/usr/bin/env python3
"""Backfill FII/DII daily flow data from Trendlyne (July 2023 - March 2026).

Trendlyne embeds daily FII/DII data in HTML data-jsondata attributes.
URL pattern: /macro-data/fii-dii/latest/cash-pastmonth/{YYYY-MM-DD}/
where the date is the last day of the month. Each page returns ~20-23
trading days of daily data.

Data format per row:
  [date, FII_Gross_Purchase, FII_Gross_Sales, FII_Net,
   DII_Net, DII_Gross_Sales, DII_Gross_Purchase, 'caret']

All values are in crores (INR).
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from datetime import date, timedelta
from calendar import monthrange

import httpx

# Add project root to path so we can import flowtracker
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from flowtracker.models import DailyFlow
from flowtracker.store import FlowStore

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://trendlyne.com/macro-data/fii-dii/latest/cash-pastmonth"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# The data we need is in the second data-jsondata attribute (index 1).
# It has headers: [date, FII_Gross_Purchase, FII_Gross_Sales, FII_Net,
#                  DII_Net, DII_Gross_Sales, DII_Gross_Purchase, details]
DATA_TABLE_INDEX = 1

# Rate limiting
REQUEST_DELAY = 2.0  # seconds between requests
MAX_RETRIES = 3
RETRY_DELAY = 5.0

# Date range for backfill
DEFAULT_START = date(2023, 7, 18)  # day after last existing data
DEFAULT_END = date(2026, 3, 16)    # day before first recent data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def last_day_of_month(year: int, month: int) -> date:
    """Return the last day of the given month."""
    _, day = monthrange(year, month)
    return date(year, month, day)


def generate_month_ends(start: date, end: date) -> list[date]:
    """Generate list of month-end dates covering the start-end range."""
    month_ends: list[date] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        eom = last_day_of_month(current.year, current.month)
        month_ends.append(eom)
        # Advance to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return month_ends


def fetch_month_data(
    client: httpx.Client,
    month_end: date,
) -> list[DailyFlow]:
    """Fetch daily FII/DII data for a month from Trendlyne.

    Returns list of DailyFlow objects for all trading days in the month.
    """
    url = f"{BASE_URL}/{month_end.isoformat()}/"

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url)
            if resp.status_code == 404:
                print(f"    404 for {month_end} — skipping")
                return []
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"    HTTP {e.response.status_code}, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    Failed after {MAX_RETRIES} attempts: {e}")
                return []
        except httpx.RequestError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"    Request error: {e}, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    Failed after {MAX_RETRIES} attempts: {e}")
                return []

    html_text = resp.text

    # Extract all data-jsondata attributes
    matches = re.findall(r'data-jsondata="([^"]*)"', html_text)
    if len(matches) <= DATA_TABLE_INDEX:
        print(f"    No data table found for {month_end}")
        return []

    decoded = html.unescape(matches[DATA_TABLE_INDEX])
    try:
        table = json.loads(decoded)
    except json.JSONDecodeError as e:
        print(f"    JSON decode error for {month_end}: {e}")
        return []

    rows = table.get("data", [])
    flows: list[DailyFlow] = []

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for row in rows:
        # Skip summary rows (e.g., "Last 30 Days", "Last 2 Weeks")
        if not isinstance(row[0], str) or not date_pattern.match(row[0]):
            continue

        try:
            d = date.fromisoformat(row[0])

            fii_buy = float(row[1])
            fii_sell = float(row[2])
            fii_net = float(row[3])
            dii_net = float(row[4])
            dii_sell = float(row[5])
            dii_buy = float(row[6])

            flows.append(DailyFlow(
                date=d,
                category="FII",
                buy_value=fii_buy,
                sell_value=fii_sell,
                net_value=fii_net,
            ))
            flows.append(DailyFlow(
                date=d,
                category="DII",
                buy_value=dii_buy,
                sell_value=dii_sell,
                net_value=dii_net,
            ))
        except (ValueError, IndexError, TypeError) as e:
            print(f"    Parse error for row {row[:3]}: {e}")
            continue

    return flows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(
    start_date: date = DEFAULT_START,
    end_date: date = DEFAULT_END,
    dry_run: bool = False,
) -> None:
    """Backfill FII/DII data from Trendlyne month by month."""

    month_ends = generate_month_ends(start_date, end_date)
    total_months = len(month_ends)

    print(f"Backfilling FII/DII data: {start_date} to {end_date}")
    print(f"Months to fetch: {total_months}")
    print(f"Dry run: {dry_run}")
    print()

    client = httpx.Client(
        headers=HEADERS,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
    )

    all_flows: list[DailyFlow] = []
    total_days = 0

    try:
        for i, month_end in enumerate(month_ends, 1):
            label = month_end.strftime("%b %Y")
            print(f"[{i}/{total_months}] Fetching {label}...", end=" ", flush=True)

            flows = fetch_month_data(client, month_end)

            # Filter to only include dates within our target range
            filtered = [
                f for f in flows
                if start_date <= f.date <= end_date
            ]

            days = len(filtered) // 2  # 2 entries per day (FII + DII)
            total_days += days
            all_flows.extend(filtered)

            print(f"{days} trading days")

            if i < total_months:
                time.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:
        print(f"\n\nInterrupted! Saving {len(all_flows)} flows collected so far...")
    finally:
        client.close()

    if not all_flows:
        print("No data collected.")
        return

    # Deduplicate by (date, category) — keep last occurrence
    seen: dict[tuple[date, str], DailyFlow] = {}
    for f in all_flows:
        seen[(f.date, f.category)] = f
    all_flows = list(seen.values())

    dates = sorted({f.date for f in all_flows})
    print(f"\nTotal: {len(dates)} unique trading days, {len(all_flows)} flow records")
    print(f"Date range: {dates[0]} to {dates[-1]}")

    if dry_run:
        print("\nDry run — not saving to database.")
        # Show sample data
        sample = sorted(all_flows, key=lambda f: (f.date, f.category))[:10]
        for f in sample:
            print(f"  {f.date} {f.category}: buy={f.buy_value:,.1f} sell={f.sell_value:,.1f} net={f.net_value:,.1f}")
        return

    print("\nSaving to FlowStore...")
    with FlowStore() as store:
        count = store.upsert_flows(all_flows)

    print(f"Done! Upserted {count} records ({len(dates)} trading days)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill FII/DII daily data from Trendlyne")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        default=DEFAULT_START,
        help=f"Start date (default: {DEFAULT_START})",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=DEFAULT_END,
        help=f"End date (default: {DEFAULT_END})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but don't save to database",
    )
    args = parser.parse_args()

    main(start_date=args.start, end_date=args.end, dry_run=args.dry_run)
