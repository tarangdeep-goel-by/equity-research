"""Screener.in Excel export client for historical quarterly results backfill."""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

import httpx
import openpyxl

from flowtracker.fund_models import AnnualEPS, QuarterlyResult

_SCREENER_BASE = "https://www.screener.in"
_CRED_PATH = Path.home() / ".config" / "flowtracker" / "screener.env"


class ScreenerError(Exception):
    """Raised on Screener.in fetch failures."""


def _load_credentials() -> tuple[str, str]:
    """Load email and password from ~/.config/flowtracker/screener.env"""
    if not _CRED_PATH.exists():
        raise ScreenerError(
            f"Screener.in credentials not found at {_CRED_PATH}\n"
            "Create the file with:\n"
            "  SCREENER_EMAIL=your@email.com\n"
            "  SCREENER_PASSWORD=yourpassword"
        )
    creds = {}
    for line in _CRED_PATH.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        creds[key.strip()] = val.strip()
    email = creds.get("SCREENER_EMAIL", "")
    password = creds.get("SCREENER_PASSWORD", "")
    if not email or not password:
        raise ScreenerError("SCREENER_EMAIL and SCREENER_PASSWORD must be set in screener.env")
    return email, password


def _parse_screener_date(date_str: str) -> str:
    """Convert Screener.in date header (e.g., 'Dec 2025', 'Mar 2016') to ISO quarter-end date.

    Screener.in uses month abbreviations. Map to quarter-end dates:
    Mar YYYY -> YYYY-03-31
    Jun YYYY -> YYYY-06-30
    Sep YYYY -> YYYY-09-30
    Dec YYYY -> YYYY-12-31
    """
    date_str = date_str.strip()
    try:
        dt = datetime.strptime(date_str, "%b %Y")
    except ValueError:
        # Try other formats
        try:
            dt = datetime.strptime(date_str, "%B %Y")
        except ValueError:
            raise ScreenerError(f"Cannot parse date: {date_str}")

    # Map to quarter-end
    month = dt.month
    year = dt.year
    quarter_ends = {3: "03-31", 6: "06-30", 9: "09-30", 12: "12-31"}
    if month in quarter_ends:
        return f"{year}-{quarter_ends[month]}"
    # Non-quarter month — use last day of that month
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-{last_day:02d}"


class ScreenerClient:
    """Screener.in client for downloading Excel exports with 10yr quarterly data."""

    def __init__(self) -> None:
        email, password = _load_credentials()
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        self._login(email, password)

    def _login(self, email: str, password: str) -> None:
        """Login to Screener.in and establish session cookies."""
        # Step 1: GET login page to get CSRF token
        resp = self._client.get(f"{_SCREENER_BASE}/login/")
        resp.raise_for_status()
        csrf = self._client.cookies.get("csrftoken")
        if not csrf:
            raise ScreenerError("Failed to get CSRF token from login page")

        # Step 2: POST login
        resp = self._client.post(
            f"{_SCREENER_BASE}/login/",
            data={
                "csrfmiddlewaretoken": csrf,
                "username": email,
                "password": password,
            },
            headers={"Referer": f"{_SCREENER_BASE}/login/"},
        )
        resp.raise_for_status()

        # Check if login succeeded (Django redirects to / on success, back to /login/ on failure)
        if "/login/" in str(resp.url):
            raise ScreenerError("Login failed — check credentials in screener.env")

    def _get_warehouse_id(self, symbol: str) -> str:
        """Fetch company page and extract the Excel export warehouse ID."""
        # Try consolidated first, fall back to standalone
        for suffix in ["/consolidated/", "/"]:
            url = f"{_SCREENER_BASE}/company/{symbol}{suffix}"
            resp = self._client.get(url)
            if resp.status_code == 200:
                break
        else:
            raise ScreenerError(f"Company page not found for {symbol}")

        # Extract warehouse ID from export form action
        match = re.search(r'formaction="/user/company/export/(\d+)/"', resp.text)
        if not match:
            # Try alternate pattern
            match = re.search(r"/user/company/export/(\d+)/", resp.text)
        if not match:
            raise ScreenerError(f"Could not find export warehouse ID for {symbol}")
        return match.group(1)

    def download_excel(self, symbol: str) -> bytes:
        """Download the Excel export for a symbol."""
        warehouse_id = self._get_warehouse_id(symbol)
        csrf = self._client.cookies.get("csrftoken")

        resp = self._client.post(
            f"{_SCREENER_BASE}/user/company/export/{warehouse_id}/",
            data={"csrfmiddlewaretoken": csrf},
            headers={"Referer": f"{_SCREENER_BASE}/company/{symbol}/consolidated/"},
        )
        resp.raise_for_status()

        if resp.headers.get("content-type", "").startswith("text/html"):
            raise ScreenerError(f"Export failed for {symbol} — got HTML instead of Excel")

        return resp.content

    def parse_quarterly_results(
        self, symbol: str, excel_bytes: bytes
    ) -> list[QuarterlyResult]:
        """Parse quarterly data from the 'Data Sheet' in a Screener.in Excel export.

        The 'Quarters' sheet uses formulas referencing 'Data Sheet', so we read
        the raw data directly from 'Data Sheet' where the Quarters section starts
        with a row containing ('Quarters', None, ...) followed by 'Report Date'
        and metric rows (Sales, Expenses, Operating Profit, etc.).
        """
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=False)

        if "Data Sheet" not in wb.sheetnames:
            wb.close()
            raise ScreenerError(f"No 'Data Sheet' found in export for {symbol}")

        ws = wb["Data Sheet"]
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        # Find the Quarters section: row where first cell == "Quarters"
        q_start = None
        for i, row in enumerate(all_rows):
            if row and isinstance(row[0], str) and row[0].strip().lower() == "quarters":
                q_start = i
                break
        if q_start is None:
            raise ScreenerError(f"No 'Quarters' section found in Data Sheet for {symbol}")

        # Next row should be Report Date with datetime objects
        date_row = all_rows[q_start + 1] if q_start + 1 < len(all_rows) else None
        if not date_row or str(date_row[0]).strip().lower() != "report date":
            raise ScreenerError(f"Expected 'Report Date' row after Quarters header for {symbol}")

        # Extract quarter-end dates from date columns
        date_cols: list[tuple[int, str]] = []  # (col_index, ISO date string)
        for col_idx in range(1, len(date_row)):
            val = date_row[col_idx]
            if val is None:
                continue
            if isinstance(val, datetime):
                date_cols.append((col_idx, val.strftime("%Y-%m-%d")))
            elif isinstance(val, str):
                try:
                    date_cols.append((col_idx, _parse_screener_date(val)))
                except ScreenerError:
                    continue

        if not date_cols:
            return []

        # Collect metric rows until we hit an empty row or a new section header
        metrics: dict[str, list[float | None]] = {}
        for row in all_rows[q_start + 2 :]:
            if not row or row[0] is None:
                break  # End of Quarters section
            label = str(row[0]).strip().lower()
            if not label:
                break
            values: list[float | None] = []
            for col_idx, _ in date_cols:
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = None
                values.append(val)
            metrics[label] = values

        # Helper to look up a metric by possible label names
        def _get(keys: list[str]) -> list[float | None]:
            for key in keys:
                if key in metrics:
                    return metrics[key]
            return [None] * len(date_cols)

        revenue_vals = _get(["sales", "revenue", "total revenue"])
        op_income_vals = _get(["operating profit"])
        net_income_vals = _get(["net profit", "profit after tax", "pat"])
        depreciation_vals = _get(["depreciation"])

        # Build QuarterlyResult for each quarter
        results = []
        for i, (_, quarter_end) in enumerate(date_cols):
            revenue = revenue_vals[i] if i < len(revenue_vals) else None
            operating_income = op_income_vals[i] if i < len(op_income_vals) else None
            net_income = net_income_vals[i] if i < len(net_income_vals) else None
            depreciation = depreciation_vals[i] if i < len(depreciation_vals) else None

            # EBITDA = operating_income + depreciation
            ebitda = None
            if operating_income is not None and depreciation is not None:
                ebitda = operating_income + depreciation

            # Margins
            operating_margin = None
            if operating_income is not None and revenue and revenue != 0:
                operating_margin = operating_income / revenue

            net_margin = None
            if net_income is not None and revenue and revenue != 0:
                net_margin = net_income / revenue

            results.append(
                QuarterlyResult(
                    symbol=symbol,
                    quarter_end=quarter_end,
                    revenue=revenue,
                    operating_income=operating_income,
                    net_income=net_income,
                    ebitda=ebitda,
                    eps=None,  # Not directly available; compute externally if needed
                    eps_diluted=None,
                    operating_margin=operating_margin,
                    net_margin=net_margin,
                )
            )

        # Sort by quarter_end ascending (oldest first)
        results.sort(key=lambda r: r.quarter_end)
        return results

    def parse_annual_eps(self, symbol: str, excel_bytes: bytes) -> list[AnnualEPS]:
        """Parse annual EPS from the P&L section of the Data Sheet.

        Returns ~10 years of annual EPS for historical P/E computation.
        """
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=False)

        if "Data Sheet" not in wb.sheetnames:
            wb.close()
            raise ScreenerError(f"No 'Data Sheet' found in export for {symbol}")

        ws = wb["Data Sheet"]
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        # Find PROFIT & LOSS section
        pl_start = None
        for i, row in enumerate(all_rows):
            if row and isinstance(row[0], str) and row[0].strip().upper() == "PROFIT & LOSS":
                pl_start = i
                break
        if pl_start is None:
            return []

        # Next row should be Report Date
        date_row = all_rows[pl_start + 1] if pl_start + 1 < len(all_rows) else None
        if not date_row:
            return []

        # Extract fiscal year end dates
        date_cols: list[tuple[int, str]] = []
        for col_idx in range(1, len(date_row)):
            val = date_row[col_idx]
            if val is None:
                continue
            if isinstance(val, datetime):
                date_cols.append((col_idx, val.strftime("%Y-%m-%d")))
            elif isinstance(val, str):
                val_str = val.strip()
                if not val_str or val_str.lower() in ("ttm", "report date"):
                    continue
                try:
                    date_cols.append((col_idx, _parse_screener_date(val_str)))
                except ScreenerError:
                    continue

        if not date_cols:
            return []

        # Find the Quarters section start to know where P&L ends
        q_start = None
        for i, row in enumerate(all_rows):
            if row and isinstance(row[0], str) and row[0].strip().lower() == "quarters":
                q_start = i
                break
        pl_end = q_start if q_start else len(all_rows)

        # Collect metric rows from P&L section
        metrics: dict[str, list[float | None]] = {}
        for row in all_rows[pl_start + 2 : pl_end]:
            if not row or row[0] is None:
                continue
            label = str(row[0]).strip().lower()
            if not label:
                continue
            values: list[float | None] = []
            for col_idx, _ in date_cols:
                val = row[col_idx] if col_idx < len(row) else None
                if val is not None:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = None
                values.append(val)
            metrics[label] = values

        def _get(keys: list[str]) -> list[float | None]:
            for key in keys:
                if key in metrics:
                    return metrics[key]
            return [None] * len(date_cols)

        revenue_vals = _get(["sales", "revenue", "total revenue"])
        net_income_vals = _get(["net profit", "profit after tax", "pat"])

        # EPS not directly in P&L section; find shares row after P&L section
        # Row labeled "Adjusted Equity Shares in Cr" is typically near end of Data Sheet
        shares_vals: list[float | None] = [None] * len(date_cols)
        for row in all_rows:
            if row and isinstance(row[0], str) and "adjusted equity shares" in row[0].strip().lower():
                for j, (col_idx, _) in enumerate(date_cols):
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is not None:
                        try:
                            shares_vals[j] = float(val)
                        except (ValueError, TypeError):
                            pass
                break

        results = []
        for i, (_, fy_end) in enumerate(date_cols):
            net_income = net_income_vals[i] if i < len(net_income_vals) else None
            shares = shares_vals[i] if i < len(shares_vals) else None

            # Compute EPS = Net Profit (Cr) / Adjusted Shares (Cr)
            eps = None
            if net_income is not None and shares and shares > 0:
                eps = net_income / shares

            if eps is None:
                continue  # Skip years without computable EPS
            results.append(AnnualEPS(
                symbol=symbol,
                fiscal_year_end=fy_end,
                eps=eps,
                revenue=revenue_vals[i] if i < len(revenue_vals) else None,
                net_income=net_income,
            ))

        results.sort(key=lambda r: r.fiscal_year_end)
        return results

    def fetch_all(self, symbol: str) -> list[QuarterlyResult]:
        """Download Excel and parse quarterly results in one call."""
        excel_bytes = self.download_excel(symbol)
        return self.parse_quarterly_results(symbol, excel_bytes)

    def fetch_annual_eps(self, symbol: str) -> list[AnnualEPS]:
        """Download Excel and parse annual EPS in one call."""
        excel_bytes = self.download_excel(symbol)
        return self.parse_annual_eps(symbol, excel_bytes)

    def fetch_all_with_annual(self, symbol: str) -> tuple[list[QuarterlyResult], list[AnnualEPS]]:
        """Download once, parse both quarterly results and annual EPS."""
        excel_bytes = self.download_excel(symbol)
        quarters = self.parse_quarterly_results(symbol, excel_bytes)
        annual = self.parse_annual_eps(symbol, excel_bytes)
        return quarters, annual

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ScreenerClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
