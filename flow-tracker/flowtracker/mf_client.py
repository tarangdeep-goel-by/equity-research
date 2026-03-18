"""AMFI monthly mutual fund flow data client and parser."""

from __future__ import annotations

import io
import logging
import time

import httpx

from flowtracker.mf_models import AMFIReportRow, MFAUMSummary

logger = logging.getLogger(__name__)

# Month abbreviation mapping for URL construction
_MONTH_ABBR = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "oct", 11: "nov", 12: "dec",
}

_BASE_URL = "https://portal.amfiindia.com/spages"
MAX_RETRIES = 3
BACKOFF_BASE = 2

# Roman numeral to category mapping for hierarchical parsing
_CATEGORY_MAP = {
    "I": "Debt",
    "II": "Equity",
    "III": "Hybrid",
    "IV": "Solution",
    "V": "Other",
}


class AMFIFetchError(Exception):
    """Raised when AMFI data fetch fails."""


class AMFIClient:
    """Client for downloading and parsing AMFI monthly mutual fund reports."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
            headers={"User-Agent": "Mozilla/5.0"},
        )

    def fetch_monthly(self, year: int, month: int) -> tuple[list[AMFIReportRow], MFAUMSummary]:
        """Fetch and parse a single month's AMFI report.

        Returns (detail_rows, aum_summary).
        """
        url = self._build_url(year, month)
        month_str = f"{year}-{month:02d}"

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()

                content = resp.content
                rows = self._parse_report(content, month_str)

                if not rows:
                    raise AMFIFetchError(f"No data parsed from {url}")

                summary = self._build_summary(rows, month_str)
                return rows, summary

            except AMFIFetchError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d for %s failed: %s", attempt + 1, month_str, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise AMFIFetchError(f"Failed to fetch {month_str} after {MAX_RETRIES} attempts: {last_error}")

    def fetch_range(
        self, start_year: int, start_month: int, end_year: int, end_month: int,
    ) -> list[tuple[list[AMFIReportRow], MFAUMSummary]]:
        """Fetch reports for a range of months. Returns list of (rows, summary) tuples."""
        results = []
        y, m = start_year, start_month
        while (y, m) <= (end_year, end_month):
            try:
                result = self.fetch_monthly(y, m)
                results.append(result)
                logger.info("Fetched %d-%02d: %d rows", y, m, len(result[0]))
            except AMFIFetchError as e:
                logger.warning("Skipping %d-%02d: %s", y, m, e)

            # Advance to next month
            m += 1
            if m > 12:
                m = 1
                y += 1

        return results

    def _build_url(self, year: int, month: int) -> str:
        """Build AMFI report URL for given year/month."""
        abbr = _MONTH_ABBR[month]
        return f"{_BASE_URL}/am{abbr}{year}repo.xls"

    def _parse_report(self, content: bytes, month_str: str) -> list[AMFIReportRow]:
        """Parse XLS/XLSX content into AMFIReportRow list.

        Detects format by checking file header bytes:
        - PK\\x03\\x04 = XLSX (ZIP-based)
        - Otherwise = XLS (BIFF format)
        """
        is_xlsx = content[:4] == b"PK\x03\x04"

        if is_xlsx:
            return self._parse_xlsx(content, month_str)
        else:
            return self._parse_xls(content, month_str)

    def _parse_xls(self, content: bytes, month_str: str) -> list[AMFIReportRow]:
        """Parse old-format .xls (BIFF) using xlrd."""
        import xlrd

        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)

        rows: list[AMFIReportRow] = []
        current_category: str | None = None

        for i in range(ws.nrows):
            row_values = [ws.cell_value(i, j) for j in range(ws.ncols)]
            parsed = self._process_row(row_values, current_category)

            if parsed is None:
                # Check if this row sets a new category
                first_cell = str(row_values[0]).strip() if row_values else ""
                cat = self._detect_category(first_cell)
                if cat:
                    current_category = cat
                continue

            if isinstance(parsed, str):
                # Category change
                current_category = parsed
                continue

            rows.append(parsed)

        return rows

    def _parse_xlsx(self, content: bytes, month_str: str) -> list[AMFIReportRow]:
        """Parse .xlsx using openpyxl."""
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active

        rows: list[AMFIReportRow] = []
        current_category: str | None = None

        for row in ws.iter_rows(values_only=True):
            row_values = list(row)
            parsed = self._process_row(row_values, current_category)

            if parsed is None:
                first_cell = str(row_values[0]).strip() if row_values else ""
                cat = self._detect_category(first_cell)
                if cat:
                    current_category = cat
                continue

            if isinstance(parsed, str):
                current_category = parsed
                continue

            rows.append(parsed)

        wb.close()
        return rows

    def _detect_category(self, cell_text: str) -> str | None:
        """Check if a cell contains a Roman numeral category header.

        Looks for patterns like "I -", "II -", "III -" etc. at start of text,
        or standalone Roman numerals.
        """
        text = cell_text.strip()
        for roman, category in _CATEGORY_MAP.items():
            # Match "II - Equity Schemes" or "II- Equity" or just "II"
            if text.startswith(f"{roman} -") or text.startswith(f"{roman}-") or text.startswith(f"{roman}."):
                return category
            # Exact match for standalone Roman numeral
            if text == roman:
                return category
        return None

    def _process_row(
        self, row_values: list, current_category: str | None,
    ) -> AMFIReportRow | str | None:
        """Process a single spreadsheet row.

        XLS layout: col 0 = serial/Roman numeral, col 1 = scheme name,
        col 2 = num schemes, col 3 = num folios, col 4 = funds mobilized,
        col 5 = redemption, col 6 = net flow, col 7 = AUM.

        Returns:
        - AMFIReportRow if it's a data row
        - str if it's a category header (the category name)
        - None if it should be skipped (header, empty, etc.)
        """
        if not row_values or len(row_values) < 8:
            return None

        col0 = str(row_values[0]).strip() if row_values[0] else ""
        col1 = str(row_values[1]).strip() if len(row_values) > 1 and row_values[1] else ""

        # Check for category header in column 0 (standalone Roman numerals: I, II, III, IV, V)
        if col0:
            cat = self._detect_category(col0)
            if cat:
                return cat

        # Skip fully empty rows
        if not col0 and not col1:
            return None

        # The sub_category name is in column 1
        sub_category = col1

        # Skip header/metadata rows
        lower1 = sub_category.lower()
        if any(skip in lower1 for skip in ["scheme name", "grand total", "note:", "source:", "open ended", "close ended", "interval"]):
            return None

        if current_category is None:
            return None

        # Try to parse as data row
        try:
            num_schemes = self._safe_int(row_values[2]) if len(row_values) > 2 else None
            funds_mobilized = self._safe_float(row_values[4]) if len(row_values) > 4 else None
            redemption = self._safe_float(row_values[5]) if len(row_values) > 5 else None
            net_flow = self._safe_float(row_values[6]) if len(row_values) > 6 else None
            aum = self._safe_float(row_values[7]) if len(row_values) > 7 else None

            # Must have at least net_flow to be valid
            if net_flow is None:
                return None

            return AMFIReportRow(
                category=current_category,
                sub_category=sub_category,
                num_schemes=num_schemes,
                funds_mobilized=funds_mobilized,
                redemption=redemption,
                net_flow=net_flow,
                aum=aum,
            )
        except (ValueError, TypeError, IndexError):
            return None

    def _build_summary(self, rows: list[AMFIReportRow], month_str: str) -> MFAUMSummary:
        """Build MFAUMSummary from parsed rows by aggregating Sub Total rows or all rows per category."""
        cat_aum: dict[str, float] = {}
        cat_flow: dict[str, float] = {}

        # Prefer "Sub Total" rows for aggregation; fall back to summing all rows
        subtotal_rows = [r for r in rows if "sub total" in r.sub_category.lower() or "sub-total" in r.sub_category.lower()]
        source_rows = subtotal_rows if subtotal_rows else rows

        for r in source_rows:
            if r.aum is not None:
                cat_aum[r.category] = cat_aum.get(r.category, 0) + r.aum
            cat_flow[r.category] = cat_flow.get(r.category, 0) + r.net_flow

        total_aum = sum(cat_aum.values())

        return MFAUMSummary(
            month=month_str,
            total_aum=total_aum,
            equity_aum=cat_aum.get("Equity", 0),
            debt_aum=cat_aum.get("Debt", 0),
            hybrid_aum=cat_aum.get("Hybrid", 0),
            other_aum=cat_aum.get("Solution", 0) + cat_aum.get("Other", 0),
            equity_net_flow=cat_flow.get("Equity", 0),
            debt_net_flow=cat_flow.get("Debt", 0),
            hybrid_net_flow=cat_flow.get("Hybrid", 0),
        )

    @staticmethod
    def _safe_float(val: object) -> float | None:
        """Try to parse a float from various types."""
        if val is None or val == "" or val == "-":
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val: object) -> int | None:
        """Try to parse an int from various types."""
        if val is None or val == "" or val == "-":
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        try:
            return int(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AMFIClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
