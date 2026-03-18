"""NSE India API client for FII/DII daily flow data."""

from __future__ import annotations

import time
import logging

import httpx

from flowtracker.models import DailyFlow, NSEApiResponse
from flowtracker.utils import normalize_category, parse_nse_date

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_API_URL = f"{_BASE_URL}/api/fiidiiTradeReact"
_PREFLIGHT_URL = f"{_BASE_URL}/reports/fii-dii"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": f"{_BASE_URL}/reports/fii-dii",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds


class NSEFetchError(Exception):
    """Raised when NSE API fetch permanently fails."""


class NSEClient:
    """Client for NSE India FII/DII trade data API."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the reports page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_daily(self) -> list[DailyFlow]:
        """Fetch today's FII/DII flow data from NSE.

        Returns list of DailyFlow (typically 2: one FII, one DII).
        Retries up to 3 times with exponential backoff.
        Refreshes cookies on 403.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(_API_URL)

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()

                flows: list[DailyFlow] = []
                for item in data:
                    raw = NSEApiResponse.model_validate(item)
                    category = normalize_category(raw.category)
                    if category not in ("FII", "DII"):
                        continue
                    flows.append(DailyFlow(
                        date=parse_nse_date(raw.date),
                        category=category,
                        buy_value=_parse_value(raw.buyValue),
                        sell_value=_parse_value(raw.sellValue),
                        net_value=_parse_value(raw.netValue),
                    ))

                if not flows:
                    raise NSEFetchError("No FII/DII data in API response")

                return flows

            except NSEFetchError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise NSEFetchError(f"Failed after {MAX_RETRIES} attempts: {last_error}")

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> NSEClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _parse_value(raw: str) -> float:
    """Parse a string value like '1,234.56' or '-567.89' to float."""
    return float(raw.replace(",", "").strip())
