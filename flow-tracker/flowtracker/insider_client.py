"""NSE insider/SAST transaction client — PIT regulation disclosures."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import httpx

from flowtracker.insider_models import InsiderTransaction

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_API_URL = f"{_BASE_URL}/api/corporates-pit"
_PREFLIGHT_URL = f"{_BASE_URL}/companies-listing/corporate-filings-insider-trading"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": _PREFLIGHT_URL,
}

MAX_RETRIES = 3
BACKOFF_BASE = 1


class InsiderError(Exception):
    """Raised when insider transaction fetch permanently fails."""


class InsiderClient:
    """Client for NSE insider/SAST transaction data."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the insider trading page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_recent(self, days: int = 7) -> list[InsiderTransaction]:
        """Fetch insider transactions for the last N days."""
        to_date = date.today()
        from_date = to_date - timedelta(days=days)
        return self._fetch_range(from_date, to_date)

    def fetch_by_symbol(self, symbol: str, days: int = 365) -> list[InsiderTransaction]:
        """Fetch insider transactions for a specific symbol."""
        to_date = date.today()
        from_date = to_date - timedelta(days=days)
        return self._fetch_range(from_date, to_date, symbol=symbol)

    def fetch_year(self, year: int) -> list[InsiderTransaction]:
        """Fetch insider transactions for a full calendar year."""
        from_date = date(year, 1, 1)
        to_date = date(year, 12, 31)
        if to_date > date.today():
            to_date = date.today()
        return self._fetch_range(from_date, to_date)

    def _fetch_range(
        self, from_date: date, to_date: date, symbol: str | None = None,
    ) -> list[InsiderTransaction]:
        """Fetch insider transactions for a date range."""
        params = {
            "from_date": from_date.strftime("%d-%m-%Y"),
            "to_date": to_date.strftime("%d-%m-%Y"),
        }
        if symbol:
            params["symbol"] = symbol.upper()

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(_API_URL, params=params)

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)

            except InsiderError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise InsiderError(f"Failed after {MAX_RETRIES} attempts: {last_error}")

    def _parse_response(self, data: object) -> list[InsiderTransaction]:
        """Parse NSE insider transaction API response."""
        trades: list[InsiderTransaction] = []

        # Response can be a list directly or nested under a key
        items = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []

        for item in items:
            trade = self._parse_trade(item)
            if trade:
                trades.append(trade)

        return trades

    def _parse_trade(self, item: dict) -> InsiderTransaction | None:
        """Parse a single insider trade entry."""
        try:
            symbol = (item.get("symbol") or "").strip()
            if not symbol:
                return None

            # Parse date — try acqfromDt first
            date_str = item.get("acqfromDt") or item.get("intimDt") or ""
            parsed_date = self._parse_date(date_str)
            if not parsed_date:
                return None

            # Determine transaction type
            txn_type = (item.get("tdpTransactionType") or "").strip()
            if not txn_type:
                sec_acq = (item.get("secAcq") or "").strip()
                if "Acquisition" in sec_acq:
                    txn_type = "Buy"
                elif "Disposal" in sec_acq:
                    txn_type = "Sell"
                else:
                    txn_type = sec_acq or "Unknown"

            # Parse quantity and value
            # NSE uses 'secAcq' for quantity (not 'noOfShareAcq')
            quantity = _parse_int_safe(
                item.get("secAcq") or item.get("noOfShareAcq", 0)
            )
            value_raw = _parse_float_safe(item.get("secVal", 0))
            value = value_raw / 1e7 if value_raw else 0  # Convert to crores

            if quantity == 0 and value == 0:
                return None

            # Parse holding percentages
            before_pct = _parse_float_safe(item.get("befAcqSharesPerc"))
            after_pct = _parse_float_safe(item.get("afterAcqSharesPerc"))

            return InsiderTransaction(
                date=parsed_date,
                symbol=symbol,
                person_name=(item.get("acqName") or "Unknown").strip(),
                person_category=(item.get("personCategory") or "Unknown").strip(),
                transaction_type=txn_type,
                quantity=quantity,
                value=value,
                mode=(item.get("acqMode") or "").strip() or None,
                holding_before_pct=before_pct,
                holding_after_pct=after_pct,
            )
        except (ValueError, TypeError) as e:
            logger.debug("Skipping insider entry: %s", e)
            return None

    @staticmethod
    def _parse_date(text: str) -> str | None:
        """Parse date from various NSE formats to YYYY-MM-DD."""
        text = text.strip()
        if not text:
            return None
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> InsiderClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _parse_int_safe(val: object) -> int:
    """Parse int from various types, returning 0 on failure."""
    if val is None:
        return 0
    try:
        return int(float(str(val).strip().replace(",", "")))
    except (ValueError, TypeError):
        return 0


def _parse_float_safe(val: object) -> float | None:
    """Parse float from various types, returning None on failure."""
    if val is None:
        return None
    try:
        result = float(str(val).strip().replace(",", ""))
        return result if result != 0 else None
    except (ValueError, TypeError):
        return None
