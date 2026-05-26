"""NSE bhavcopy client — daily OHLCV + delivery data from CSV archives.

Two URL formats are supported:

- **Modern** (2020+): ``products/content/sec_bhavdata_full_{DDMMYYYY}.csv`` — plain CSV
  with delivery columns (DELIV_QTY, DELIV_PER).
- **Legacy** (pre-2020): ``content/historical/EQUITIES/{YYYY}/{MMM}/cm{DDMMMYYYY}bhav.csv.zip``
  — zipped CSV with the older column set (no delivery data; delivery began circa 2014
  on a separate file). Persists ``delivery_qty=None`` / ``delivery_pct=None`` for those
  rows.

``fetch_day`` auto-detects: tries modern first, falls back to legacy on 404. Callers
can force the legacy path with ``fetch_day(..., legacy=True)``.
"""

from __future__ import annotations

import csv
import io
import logging
import time
import zipfile
from datetime import date, timedelta

import httpx

from flowtracker.bhavcopy_models import DailyStockData

logger = logging.getLogger(__name__)

_BASE_URL = "https://nsearchives.nseindia.com/products/content"
_LEGACY_BASE_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES"
_PREFLIGHT_URL = "https://www.nseindia.com/"
MAX_RETRIES = 3
BACKOFF_BASE = 1


class BhavcopyFetchError(Exception):
    """Raised when bhavcopy fetch permanently fails."""


class BhavcopyClient:
    """Client for NSE daily bhavcopy CSV files (modern + legacy)."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/csv,application/zip,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.nseindia.com/",
            },
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit NSE homepage to acquire session cookies (needed for legacy archive URLs)."""
        try:
            resp = self._client.get(_PREFLIGHT_URL, timeout=15.0)
            if resp.status_code == 200:
                self._has_cookies = True
        except Exception as e:  # pragma: no cover — preflight failures fall through to fetch
            logger.debug("Cookie preflight failed: %s", e)

    def fetch_day(
        self,
        target_date: date | None = None,
        *,
        legacy: bool = False,
    ) -> list[DailyStockData]:
        """Fetch bhavcopy CSV for a single trading day.

        Returns empty list if no data (holiday/weekend/404 on both URL formats).

        Args:
            target_date: trading day to fetch (default: today).
            legacy: if True, skip the modern URL and go straight to the legacy
                archive URL. Useful for pre-2020 dates where the modern URL
                doesn't exist.
        """
        if target_date is None:
            target_date = date.today()

        if not legacy:
            records = self._fetch_modern(target_date)
            if records is not None:
                return records
            # Modern returned 404 — try legacy
            logger.info(
                "Modern bhavcopy URL 404 for %s — falling back to legacy archive",
                target_date,
            )

        legacy_records = self._fetch_legacy(target_date)
        return legacy_records if legacy_records is not None else []

    def _fetch_modern(self, target_date: date) -> list[DailyStockData] | None:
        """Try the modern (2020+) URL. Returns None on 404 (caller should fall back)."""
        date_str = target_date.strftime("%d%m%Y")
        url = f"{_BASE_URL}/sec_bhavdata_full_{date_str}.csv"

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(url)

                if resp.status_code == 404:
                    return None  # signal "try legacy"

                resp.raise_for_status()
                return self._parse_csv(resp.text, target_date.isoformat())

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                logger.warning("Modern attempt %d for %s failed: %s", attempt + 1, target_date, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
            except Exception as e:
                logger.warning("Modern attempt %d for %s failed: %s", attempt + 1, target_date, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        logger.error(
            "Failed to fetch modern bhavcopy for %s after %d attempts",
            target_date, MAX_RETRIES,
        )
        return []

    def _fetch_legacy(self, target_date: date) -> list[DailyStockData] | None:
        """Try the legacy (pre-2020) archive URL.

        URL pattern: ``content/historical/EQUITIES/{YYYY}/{MMM}/cm{DDMMMYYYY}bhav.csv.zip``
        Returns ``[]`` if the day genuinely has no bhavcopy (holiday on both
        URL formats); returns None only on internal logic error (never raised
        in practice).
        """
        year = target_date.year
        mon = target_date.strftime("%b").upper()  # e.g. JAN
        ddmmm = target_date.strftime("%d%b%Y").upper()  # e.g. 02JAN2008
        url = f"{_LEGACY_BASE_URL}/{year}/{mon}/cm{ddmmm}bhav.csv.zip"

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(url)

                if resp.status_code == 404:
                    logger.info(
                        "No legacy bhavcopy for %s (holiday/weekend or no archive)",
                        target_date,
                    )
                    return []

                resp.raise_for_status()
                return self._parse_legacy_zip(resp.content, target_date.isoformat())

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return []
                logger.warning(
                    "Legacy attempt %d for %s failed: %s", attempt + 1, target_date, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
            except Exception as e:
                logger.warning(
                    "Legacy attempt %d for %s failed: %s", attempt + 1, target_date, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        logger.error(
            "Failed to fetch legacy bhavcopy for %s after %d attempts",
            target_date, MAX_RETRIES,
        )
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
        """Parse modern bhavcopy CSV content into DailyStockData records."""
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

    def _parse_legacy_zip(self, zip_bytes: bytes, date_iso: str) -> list[DailyStockData]:
        """Unzip in-memory legacy bhavcopy archive, parse the contained CSV."""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # Legacy archives contain a single file like cm02JAN2008bhav.csv
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                logger.warning("Legacy zip for %s has no CSV inside", date_iso)
                return []
            with zf.open(csv_names[0]) as fh:
                text = fh.read().decode("utf-8", errors="replace")
        return self._parse_legacy_csv(text, date_iso)

    def _parse_legacy_csv(self, text: str, date_iso: str) -> list[DailyStockData]:
        """Parse legacy (pre-2020) bhavcopy CSV.

        Legacy columns (no delivery data):
            SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,
            TOTTRDQTY,TOTTRDVAL,TIMESTAMP[,TOTALTRADES,ISIN]

        Legacy turnover (``TOTTRDVAL``) is in rupees; modern turnover
        (``TURNOVER_LACS``) is in lakhs (₹1L = 100,000). Divide by 1e5 to
        align units so downstream consumers don't have to special-case.
        """
        records: list[DailyStockData] = []
        reader = csv.DictReader(io.StringIO(text))

        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        for row in reader:
            row = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

            series = row.get("SERIES", "").strip()
            if series != "EQ":
                continue

            symbol = row.get("SYMBOL", "").strip()
            if not symbol:
                continue

            try:
                # TOTTRDVAL is in rupees; convert to lakhs to match modern CSV
                turnover_rupees = _parse_float(row.get("TOTTRDVAL", "0"))
                turnover_lakhs = turnover_rupees / 1e5

                records.append(DailyStockData(
                    date=date_iso,
                    symbol=symbol,
                    open=_parse_float(row.get("OPEN", "0")),
                    high=_parse_float(row.get("HIGH", "0")),
                    low=_parse_float(row.get("LOW", "0")),
                    close=_parse_float(row.get("CLOSE", "0")),
                    prev_close=_parse_float(row.get("PREVCLOSE", "0")),
                    volume=_parse_int(row.get("TOTTRDQTY", "0")),
                    turnover=turnover_lakhs,
                    delivery_qty=None,   # not published in legacy CSV
                    delivery_pct=None,
                ))
            except (ValueError, KeyError) as e:
                logger.debug("Skipping legacy row for %s: %s", symbol, e)
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
