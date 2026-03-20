"""SEBI daily mutual fund flow data client and parser."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import httpx

from flowtracker.mf_models import MFDailyFlow

logger = logging.getLogger(__name__)

_SEBI_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMfd=yes&type=2"
MAX_RETRIES = 3
BACKOFF_BASE = 2


class SEBIFetchError(Exception):
    """Raised when SEBI data fetch fails."""


class SEBIClient:
    """Fetches daily MF purchase/sale data from SEBI website."""

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    def __enter__(self) -> SEBIClient:
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        return self

    def __exit__(self, *args: object) -> None:
        if self._client:
            self._client.close()

    def fetch_daily(self) -> list[MFDailyFlow]:
        """Fetch current month's daily MF flows from SEBI.

        Returns list of MFDailyFlow records (2 per trading day: Equity + Debt).
        """
        assert self._client is not None, "Use as context manager"

        html = self._fetch_page()
        return self._parse_html(html)

    def _fetch_page(self) -> str:
        """Fetch the SEBI MF page with retry logic."""
        assert self._client is not None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.get(_SEBI_URL)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as e:
                logger.warning("SEBI fetch attempt %d failed: %s", attempt, e)
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE ** attempt)
                else:
                    raise SEBIFetchError(f"Failed after {MAX_RETRIES} attempts: {e}") from e
        raise SEBIFetchError("Unreachable")  # satisfy type checker

    def _parse_html(self, html: str) -> list[MFDailyFlow]:
        """Parse the SEBI HTML table into MFDailyFlow records.

        Uses regex parsing (no BeautifulSoup dependency needed).
        The table has a predictable structure with rowspan=2 for dates.
        """
        flows: list[MFDailyFlow] = []

        # Find the tbody content of the main data table
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL)
        if not tbody_match:
            logger.warning("No tbody found in SEBI page")
            return flows

        tbody = tbody_match.group(1)

        # Extract all <tr> blocks
        rows = re.findall(r'<tr>(.*?)</tr>', tbody, re.DOTALL)

        current_date: str | None = None

        for row_html in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
            cells = [c.strip() for c in cells]

            if not cells:
                continue

            # If first cell has rowspan, it's a date row (5 cells)
            if 'rowspan' in row_html and len(cells) >= 5:
                parsed_date = self._parse_date(cells[0])
                if parsed_date is None:
                    # Not a valid date row (e.g. "Total" row) — skip
                    current_date = None
                    continue
                current_date = parsed_date
                category = cells[1].strip()
                purchase = self._parse_amount(cells[2])
                sale = self._parse_amount(cells[3])
                net = self._parse_amount(cells[4])
            elif len(cells) >= 4 and current_date:
                # Continuation row (4 cells, no date)
                category = cells[0].strip()
                purchase = self._parse_amount(cells[1])
                sale = self._parse_amount(cells[2])
                net = self._parse_amount(cells[3])
            else:
                continue

            if current_date and category in ("Equity", "Debt"):
                flows.append(MFDailyFlow(
                    date=current_date,
                    category=category,
                    gross_purchase=purchase,
                    gross_sale=sale,
                    net_investment=net,
                ))

        return flows

    @staticmethod
    def _parse_date(text: str) -> str | None:
        """Parse '02 Mar, 2026' to '2026-03-02'. Returns None if not a valid date."""
        text = text.strip()
        try:
            dt = datetime.strptime(text, "%d %b, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try without comma
            try:
                dt = datetime.strptime(text, "%d %b %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None

    @staticmethod
    def _parse_amount(text: str) -> float:
        """Parse amount string, handling parentheses for negatives.

        '16545.47' -> 16545.47
        '(3135.34)' -> -3135.34
        """
        text = text.strip().replace(",", "")
        if text.startswith("(") and text.endswith(")"):
            return -float(text[1:-1])
        try:
            return float(text)
        except ValueError:
            return 0.0
