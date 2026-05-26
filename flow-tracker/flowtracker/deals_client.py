"""NSE bulk/block deals client — large institutional transactions."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from flowtracker.deals_models import BulkBlockDeal

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_API_URL = f"{_BASE_URL}/api/snapshot-capital-market-largedeal"
_PREFLIGHT_URL = f"{_BASE_URL}/market-data/live-equity-market"
# Historical archive endpoint — paged by date window, ~70 row cap per call.
# We iterate one day at a time to stay under the cap on busy days.
_HISTORICAL_URL = f"{_BASE_URL}/api/historicalOR/bulk-block-short-deals"
_HISTORICAL_PREFLIGHT_URL = f"{_BASE_URL}/report-detail/display-bulk-and-block-deals"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": f"{_BASE_URL}/market-data/live-equity-market",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1


class DealsError(Exception):
    """Raised when deals fetch permanently fails."""


class DealsClient:
    """Client for NSE bulk/block deals API."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the bulk deals page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_deals(self) -> list[BulkBlockDeal]:
        """Fetch today's bulk/block deals from NSE.

        Returns list of BulkBlockDeal for all deal types.
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
                return self._parse_response(data)

            except DealsError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise DealsError(f"Failed after {MAX_RETRIES} attempts: {last_error}")

    def fetch_historical_deals(
        self,
        from_date: str,
        to_date: str,
        option_types: tuple[str, ...] = ("bulk_deals", "block_deals", "short_deals"),
    ) -> list[BulkBlockDeal]:
        """Fetch historical bulk/block/short deals for the (from..to) range.

        The NSE historical archive caps responses at ~70 rows. Caller is
        responsible for paging by day; this method only issues a single
        request per ``option_type``. Dates must be ``YYYY-MM-DD``.

        Returns a flat list of parsed BulkBlockDeal records (deduped by the
        upstream store's UNIQUE constraint, not here).
        """
        deals: list[BulkBlockDeal] = []
        from_dmy = self._to_ddmmyyyy(from_date)
        to_dmy = self._to_ddmmyyyy(to_date)

        for opt in option_types:
            deal_type = {
                "bulk_deals": "BULK",
                "block_deals": "BLOCK",
                "short_deals": "SHORT",
            }.get(opt, "BULK")

            last_error: Exception | None = None
            success = False
            for attempt in range(MAX_RETRIES):
                try:
                    if not self._has_cookies or attempt > 0:
                        self._ensure_historical_cookies()
                    resp = self._client.get(
                        _HISTORICAL_URL,
                        params={
                            "from": from_dmy,
                            "to": to_dmy,
                            "optionType": opt,
                        },
                    )
                    if resp.status_code == 403:
                        logger.warning(
                            "Got 403 for %s %s..%s, refreshing cookies (attempt %d)",
                            opt, from_dmy, to_dmy, attempt + 1,
                        )
                        self._has_cookies = False
                        time.sleep(BACKOFF_BASE * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                    rows = payload.get("data", []) if isinstance(payload, dict) else []
                    for item in rows:
                        d = self._parse_deal(item, deal_type)
                        if d:
                            deals.append(d)
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Historical fetch attempt %d for %s %s..%s failed: %s",
                        attempt + 1, opt, from_dmy, to_dmy, e,
                    )
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(BACKOFF_BASE * (2 ** attempt))
            if not success:
                logger.warning(
                    "Historical fetch permanently failed for %s %s..%s: %s",
                    opt, from_dmy, to_dmy, last_error,
                )

        return deals

    def _ensure_historical_cookies(self) -> None:
        """Hit the historical bulk/block deals report page for session cookies."""
        resp = self._client.get(_HISTORICAL_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    @staticmethod
    def _to_ddmmyyyy(text: str) -> str:
        """Convert ``YYYY-MM-DD`` to NSE's ``DD-MM-YYYY``. Pass-through if already in target form."""
        text = text.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
            except ValueError:
                continue
        return text

    def _parse_response(self, data: dict) -> list[BulkBlockDeal]:
        """Parse the NSE large deal API response."""
        deals: list[BulkBlockDeal] = []

        # Block deals
        for item in data.get("BLOCK_DEALS_DATA", []):
            deal = self._parse_deal(item, "BLOCK")
            if deal:
                deals.append(deal)

        # Bulk deals
        for item in data.get("BULK_DEALS_DATA", []):
            deal = self._parse_deal(item, "BULK")
            if deal:
                deals.append(deal)

        # Short selling (if present)
        for item in data.get("SHORT_SELLING_DATA", []):
            deal = self._parse_deal(item, "SHORT")
            if deal:
                deals.append(deal)

        return deals

    def _parse_deal(self, item: dict, deal_type: str) -> BulkBlockDeal | None:
        """Parse a single deal entry."""
        try:
            # Support both old (BD_*) and new API field names
            symbol = (item.get("symbol") or item.get("BD_SYMBOL", "")).strip()
            if not symbol:
                return None

            date_str = item.get("date") or item.get("BD_DT_DATE", "")
            parsed_date = self._parse_date(date_str)

            quantity = int(item.get("qty") or item.get("BD_QTY_TRD", 0))
            price_raw = item.get("watp") or item.get("BD_TP_WATP")
            price = float(price_raw) if price_raw else None

            client = (item.get("clientName") or item.get("BD_CLIENT_NAME", "")).strip() or None
            buy_sell = (item.get("buySell") or item.get("BD_BUY_SELL", "")).strip().upper() or None

            return BulkBlockDeal(
                date=parsed_date,
                deal_type=deal_type,
                symbol=symbol,
                client_name=client,
                buy_sell=buy_sell,
                quantity=quantity,
                price=price,
            )
        except (ValueError, TypeError) as e:
            logger.debug("Skipping deal entry: %s", e)
            return None

    @staticmethod
    def _parse_date(text: str) -> str:
        """Parse deal date from various formats to YYYY-MM-DD."""
        text = text.strip()
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return text  # Return as-is if parsing fails

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DealsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
