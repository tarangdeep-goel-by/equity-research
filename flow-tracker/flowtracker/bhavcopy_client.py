"""NSE bhavcopy client — daily OHLCV + delivery data from CSV archives."""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, timedelta

import httpx

from flowtracker.bhavcopy_models import DailyStockData

logger = logging.getLogger(__name__)

_BASE_URL = "https://nsearchives.nseindia.com/products/content"
MAX_RETRIES = 3
BACKOFF_BASE = 2


class BhavcopyFetchError(Exception):
    """Raised when bhavcopy fetch permanently fails."""


class BhavcopyClient:
    """Client for NSE daily bhavcopy CSV files."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )

    def fetch_day(self, target_date: date | None = None) -> list[DailyStockData]:
        """Fetch bhavcopy CSV for a single trading day.

        Returns empty list if no data (holiday/weekend/404).
        """
        if target_date is None:
            target_date = date.today()

        date_str = target_date.strftime("%d%m%Y")
        url = f"{_BASE_URL}/sec_bhavdata_full_{date_str}.csv"

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(url)

                if resp.status_code == 404:
                    logger.info("No bhavcopy for %s (holiday/weekend)", target_date)
                    return []

                resp.raise_for_status()
                return self._parse_csv(resp.text, target_date.isoformat())

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return []
                logger.warning("Attempt %d for %s failed: %s", attempt + 1, target_date, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE ** (attempt + 1))
            except Exception as e:
                logger.warning("Attempt %d for %s failed: %s", attempt + 1, target_date, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE ** (attempt + 1))

        logger.error("Failed to fetch bhavcopy for %s after %d attempts", target_date, MAX_RETRIES)
        return []

    def fetch_range(self, start: date, end: date) -> list[DailyStockData]:
        """Fetch bhavcopy for a date range, skipping weekends."""
        all_records: list[DailyStockData] = []
        current = start
        total_days = (end - start).days
        fetched = 0

        while current <= end:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            records = self.fetch_day(current)
            if records:
                all_records.extend(records)
                fetched += 1
                logger.info(
                    "Fetched %s: %d records (total: %d, day %d/%d)",
                    current, len(records), len(all_records),
                    (current - start).days, total_days,
                )

            current += timedelta(days=1)
            time.sleep(0.5)  # Be polite to NSE

        logger.info("Backfill complete: %d trading days, %d records", fetched, len(all_records))
        return all_records

    def _parse_csv(self, text: str, date_iso: str) -> list[DailyStockData]:
        """Parse bhavcopy CSV content into DailyStockData records."""
        records: list[DailyStockData] = []
        reader = csv.DictReader(io.StringIO(text))

        # Strip whitespace from fieldnames
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        for row in reader:
            # Strip whitespace from all values
            row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

            # Only regular equity
            series = row.get("SERIES", "").strip()
            if series != "EQ":
                continue

            symbol = row.get("SYMBOL", "").strip()
            if not symbol:
                continue

            try:
                delivery_qty = _parse_int_or_none(row.get("DELIV_QTY", ""))
                delivery_pct = _parse_float_or_none(row.get("DELIV_PER", ""))

                records.append(DailyStockData(
                    date=date_iso,
                    symbol=symbol,
                    open=_parse_float(row.get("OPEN_PRICE", "0")),
                    high=_parse_float(row.get("HIGH_PRICE", "0")),
                    low=_parse_float(row.get("LOW_PRICE", "0")),
                    close=_parse_float(row.get("CLOSE_PRICE", "0")),
                    prev_close=_parse_float(row.get("PREV_CLOSE", "0")),
                    volume=_parse_int(row.get("TTL_TRD_QNTY", "0")),
                    turnover=_parse_float(row.get("TURNOVER_LACS", "0")),
                    delivery_qty=delivery_qty,
                    delivery_pct=delivery_pct,
                ))
            except (ValueError, KeyError) as e:
                logger.debug("Skipping row for %s: %s", symbol, e)
                continue

        return records

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BhavcopyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _parse_float(val: str) -> float:
    """Parse float, stripping commas and whitespace."""
    val = val.strip().replace(",", "")
    return float(val)


def _parse_int(val: str) -> int:
    """Parse int, stripping commas and whitespace."""
    val = val.strip().replace(",", "")
    return int(float(val))


def _parse_float_or_none(val: str) -> float | None:
    """Parse float or return None for missing values like ' -'."""
    val = val.strip().replace(",", "")
    if not val or val == "-" or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _parse_int_or_none(val: str) -> int | None:
    """Parse int or return None for missing values."""
    val = val.strip().replace(",", "")
    if not val or val == "-" or val == "":
        return None
    try:
        return int(float(val))
    except ValueError:
        return None
