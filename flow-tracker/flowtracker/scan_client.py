"""NSE India API client for fetching index constituents."""

from __future__ import annotations

import time
import logging
from urllib.parse import quote

import httpx

from flowtracker.scan_models import IndexConstituent

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_API_URL = f"{_BASE_URL}/api/equity-stockIndices"
_PREFLIGHT_URL = f"{_BASE_URL}/market-data/live-equity-market"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": f"{_BASE_URL}/market-data/live-equity-market",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds

_NIFTY_INDICES = ["NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]


class NSEIndexError(Exception):
    """Raised when NSE index constituent fetch permanently fails."""


class NSEIndexClient:
    """Client for NSE India index constituents API."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the market data page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_constituents(self, index_name: str) -> list[IndexConstituent]:
        """Fetch constituents of a given index from NSE.

        Args:
            index_name: Index name like "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100".

        Returns list of IndexConstituent for stocks in the index.
        Retries up to 3 times with exponential backoff.
        Refreshes cookies on 403.
        """
        url = f"{_API_URL}?index={quote(index_name)}"
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(url)

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", [])
                constituents: list[IndexConstituent] = []
                for item in items:
                    if item.get("priority") != 0:
                        continue
                    meta = item.get("meta", {})
                    constituents.append(IndexConstituent(
                        symbol=item["symbol"],
                        index_name=index_name,
                        company_name=meta.get("companyName"),
                        industry=meta.get("industry"),
                    ))

                if not constituents:
                    raise NSEIndexError(f"No constituents in API response for {index_name}")

                return constituents

            except NSEIndexError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d failed for %s: %s", attempt + 1, index_name, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise NSEIndexError(f"Failed after {MAX_RETRIES} attempts for {index_name}: {last_error}")

    def fetch_all_nifty250(self) -> list[IndexConstituent]:
        """Fetch constituents of NIFTY 50 + NIFTY NEXT 50 + NIFTY MIDCAP 100.

        Deduplicates by symbol, keeping the first occurrence (from the more
        prestigious index). Sleeps 1s between API calls.
        """
        all_constituents: list[IndexConstituent] = []
        seen: set[str] = set()

        for i, index_name in enumerate(_NIFTY_INDICES):
            if i > 0:
                time.sleep(1)

            batch = self.fetch_constituents(index_name)
            for c in batch:
                if c.symbol not in seen:
                    seen.add(c.symbol)
                    all_constituents.append(c)

        return all_constituents

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> NSEIndexClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
