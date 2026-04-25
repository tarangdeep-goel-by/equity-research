"""Parse the AR "5/10-year financial highlights" markdown table.

Background: Schedule III mandates that when a company changes its P&L /
Balance Sheet bucketing, prior years are restated to match. The 5/10-year
financial-highlights table at the front of every Indian AR is the
canonical restated trend source — internally consistent across years.
Used as the trusted source by `ResearchDataAPI` for any multi-year compute
(DuPont, F-score, CAGR, margin walk) when AR data is available — see
plans/screener-data-discontinuity.md, Strategy 2.

This module is **pure-Python** (no LLM). Docling renders the table as a
markdown table; we parse the markdown directly.

Layout variance covered (from cohort: HDFCBANK, INFY, TCS, HINDUNILVR,
SUNPHARMA, NESTLEIND, ICICIBANK, SBIN):

  * Standard layout — years as columns, metrics as rows. Most common
    (SUNPHARMA, TCS, NESTLEIND).
  * Multiple stacked tables under one heading — HINDUNILVR splits BS
    and KPI ratios into 3 separate markdown tables.
  * Transposed layout — years as rows, metrics as bottom row of the
    table (ICICIBANK).
  * Mixed unit headers — "(₹ in crores)" prefix in row 0, year labels
    in row 1 or 2.
  * Multiple-FY-tag rows — "FY25", "FY 2025", "2024-25", "March 2025".
  * Image-rendered — the heading exists in the markdown but the actual
    figures are an image (HDFCBANK, INFY, SBIN). Detected by
    sparse-digit signature; flagged `image_rendered` and skipped (no rows).

Output: list of `FiveYearHighlight` Pydantic rows, one per fiscal year.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FiveYearHighlight(BaseModel, extra="ignore"):
    """One row of the AR 5/10-year financial-highlights table.

    All monetary values in **crores** (matches store.py invariant). Per-share
    in rupees. Counts (num_shares) in millions.
    """
    fy_end: str  # canonical "YYYY-03-31" (March-end fiscal-year close)
    revenue: float | None = None
    operating_profit: float | None = None
    pat: float | None = None
    eps: float | None = None
    net_worth: float | None = None
    total_assets: float | None = None
    borrowings: float | None = None
    cfo: float | None = None
    capex: float | None = None
    dividend_per_share: float | None = None
    num_shares: float | None = None  # millions

    # Provenance
    source_ar_fy: str | None = None  # which AR this row was extracted from
    raw_unit: str | None = None  # "crore" / "million" / "lakh" — observed unit


# Canonical metric → ordered list of (alias_substring, kind) tuples.
# `kind` is "exact_phrase" (substring match anywhere in label) or
# "starts_with" (label must begin with the alias — used for short ambiguous
# tokens like "sales" or "turnover" where appearance in the middle of a
# label like "fixed asset turnover" is a false positive).
# First match wins, so order aliases from most specific to least.
_MetricAlias = tuple[str, str]  # (substring, kind)


_METRIC_ALIASES: dict[str, list[_MetricAlias]] = {
    "revenue": [
        ("revenue from operations", "exact_phrase"),
        ("total revenue from operations", "exact_phrase"),
        ("total income", "exact_phrase"),
        ("total revenue", "exact_phrase"),
        ("net sales", "exact_phrase"),
        ("sales", "starts_with"),
        ("turnover", "starts_with"),
        ("net interest income", "exact_phrase"),  # banks fallback
    ],
    "operating_profit": [
        ("profit from operations", "exact_phrase"),
        ("operating profit", "exact_phrase"),
        ("core operating profit", "exact_phrase"),  # banks
        ("ebitda", "starts_with"),
        ("ebit", "starts_with"),  # only when not EBITDA — order handles this
    ],
    "pat": [
        ("profit after tax attributable to shareholders", "exact_phrase"),
        ("profit after tax", "exact_phrase"),
        ("net profit for the year", "exact_phrase"),
        ("net profit", "starts_with"),
        ("profit for the year", "exact_phrase"),
        ("net income", "exact_phrase"),
        ("pat", "starts_with"),
    ],
    "eps": [
        ("earnings per share - basic", "exact_phrase"),
        ("earnings per share (basic)", "exact_phrase"),
        ("earnings per share - as reported", "exact_phrase"),
        ("eps- as reported", "exact_phrase"),
        ("eps - as reported", "exact_phrase"),
        ("basic eps", "exact_phrase"),
        ("eps (basic)", "exact_phrase"),
        # Fallback to any "earnings per share ..." prefix.
        ("earnings per share", "starts_with"),
    ],
    "net_worth": [
        ("shareholders fund", "exact_phrase"),
        ("shareholders' fund", "exact_phrase"),
        ("shareholders funds", "exact_phrase"),
        ("net worth", "exact_phrase"),
        ("shareholders equity", "exact_phrase"),
        ("total equity", "exact_phrase"),
    ],
    "total_assets": [
        ("total assets", "exact_phrase"),
        ("total equity and liabilities", "exact_phrase"),
        ("total liabilities and equity", "exact_phrase"),
    ],
    "borrowings": [
        ("total borrowings", "exact_phrase"),
        ("total debt", "exact_phrase"),
        ("long-term debt", "exact_phrase"),
        ("total deposits", "exact_phrase"),  # banks
        ("borrowings", "starts_with"),
    ],
    "cfo": [
        ("cash from operations", "exact_phrase"),
        ("cash flow from operations", "exact_phrase"),
        ("operating cash flow", "exact_phrase"),
        ("cash generated from operations", "exact_phrase"),
        ("net cash from operations", "exact_phrase"),
    ],
    "capex": [
        ("capital expenditure", "exact_phrase"),
        ("capex", "starts_with"),
        ("additions to property, plant", "exact_phrase"),
    ],
    "dividend_per_share": [
        ("dividend per equity share", "exact_phrase"),
        ("dividend per share", "exact_phrase"),
    ],
    "num_shares": [
        ("number of shares (in million)", "exact_phrase"),
        ("number of shares", "exact_phrase"),
        ("weighted average number of shares", "exact_phrase"),
        ("no. of shares", "exact_phrase"),
    ],
}


# Year-column header → 4-digit year ("YYYY") map. Tries these patterns in
# order; first to fully match (returning a 4-digit year) wins. Returns
# the *fiscal year close* — e.g. "FY25" → "2025", "2024-25" → "2025".
_YEAR_PATTERNS = (
    re.compile(r"^\s*FY\s*[-']?\s*(\d{2})\s*\*?\s*$", re.IGNORECASE),  # FY25, FY 25
    re.compile(r"^\s*FY\s*[-']?\s*(\d{4})\s*\*?\s*$", re.IGNORECASE),  # FY 2025, FY2025
    re.compile(r"^\s*(\d{4})\s*[-/]\s*\d{2,4}\s*[\*\^#]*\s*$"),       # 2024-25, 2024-2025
    re.compile(r"^\s*March\s+(\d{4})\s*\*?\s*$", re.IGNORECASE),       # March 2025
    re.compile(r"^\s*Mar\s*[-']?\s*(\d{2,4})\s*\*?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(\d{4})\s*[\*\^#]*\s*$"),                          # 2025 (ICICIBANK)
)


def _normalize_year(token: str) -> str | None:
    """Map a year-column header to canonical 'YYYY-03-31' (FY close).

    Returns None when the token isn't recognizable as a year. We assume
    Indian fiscal-year close = March 31 throughout.

    Also supports tokens with extra prefix/suffix like "( FY24" or
    "H Million) FY25" — Docling sometimes concatenates a multi-row header
    into a single cell, so we scan for any year-shaped substring.
    """
    t = (token or "").strip()
    if not t:
        return None
    # First try the strict full-string patterns.
    for rx in _YEAR_PATTERNS:
        m = rx.match(t)
        if m:
            return _build_fy_close(m.group(1), rx.pattern)
    # Fallback: find a year-shaped substring inside concatenated headers.
    # Order matters — try most specific (FY-prefix, range) first.
    sub_patterns = (
        (re.compile(r"\bFY\s*[-']?\s*(\d{4})\b", re.IGNORECASE), False),
        (re.compile(r"\bFY\s*[-']?\s*(\d{2})\b", re.IGNORECASE), False),
        (re.compile(r"\b(\d{4})\s*[-/]\s*\d{2,4}\b"), True),  # 2024-25
        (re.compile(r"\bMarch\s+(\d{4})\b", re.IGNORECASE), False),
    )
    for rx, is_range in sub_patterns:
        m = rx.search(t)
        if m:
            yr = m.group(1)
            if len(yr) == 2:
                yr_int = int(yr)
                yr = str(2000 + yr_int) if yr_int < 70 else str(1900 + yr_int)
            if is_range:
                yr = str(int(yr) + 1)
            return f"{yr}-03-31"
    return None


def _build_fy_close(year_grp: str, pattern: str) -> str:
    """Helper: convert regex group + originating pattern to 'YYYY-03-31'."""
    yr = year_grp
    if len(yr) == 2:
        yr_int = int(yr)
        yr = str(2000 + yr_int) if yr_int < 70 else str(1900 + yr_int)
    if pattern.startswith(r"^\s*(\d{4})\s*[-/]"):
        yr = str(int(yr) + 1)
    return f"{yr}-03-31"


def _parse_number(cell: str) -> float | None:
    """Parse a markdown table cell to a float, or None.

    Handles:
      - thousand separators: 1,234,567 / 1,23,456 (Indian numbering)
      - decimals: 12.34
      - parens for negatives: (1,234) → -1234
      - currency / unit prefix tokens: ₹, H, I, Rs, $ (stripped)
      - footnote markers: 12.34* or 12.34^ or 12.34# (stripped)
      - hyphen / dash / "—" / "NA" / blank → None
    """
    if cell is None:
        return None
    s = cell.strip()
    if not s or s in {"-", "–", "—", "NA", "N/A", "n/a", "Nil", "nil"}:
        return None
    # Strip parens around negatives.
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    # Strip currency / unit prefixes — most commonly "₹", but Docling sometimes
    # corrupts ₹ to "H" or "I" (font-substitution artefact). Strip a leading
    # single uppercase letter only when followed by digits.
    s = re.sub(r"^[₹$Rs.]\s*", "", s)
    s = re.sub(r"^[HI]\s+(?=[\d(])", "", s)
    # Footnote markers.
    s = re.sub(r"[\*\^#@†‡]+\s*$", "", s).strip()
    # Now parse with thousands separators.
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _detect_unit(headers: list[str], section_text: str) -> tuple[str, float]:
    """Return (unit_label, multiplier_to_crores).

    Unit annotations appear in:
      - column-0 headers: "(₹ in crores)" / "(in million)"
      - prose right above the table: "` in billion" / "₹ Million" / "H Million"
      - title / heading: "(in lakh)"

    Multiplier converts SOURCE unit to **crores** (project standard):
        - crore: 1.0
        - billion: 100.0 (1 Bn = 100 Cr)
        - million: 0.1 (10 Mn = 1 Cr)
        - lakh: 0.01 (100 Lakh = 1 Cr)
        - thousand: 0.0001
    """
    # Scan headers + full section + (caller-supplied) pre-section context.
    # The unit annotation can appear in the column header, in a one-line
    # caption above the table ("₹ in million"), inside the table footer
    # ("(₹ Million)") — SUNPHARMA FY24 puts it AFTER the table — or in
    # prose right above the heading (ICICIBANK FY25).
    blob = (" ".join(h for h in headers if h) + " " + section_text).lower()
    # Order matters — billion before crore (the phrase "in billion" doesn't
    # collide), but "in crore" before "in million" so a stray "100 million"
    # in prose doesn't override an explicit "₹ in crore" annotation.
    if "in billion" in blob or "₹ billion" in blob or "rs. billion" in blob:
        return ("billion", 100.0)
    if "in crore" in blob or "₹ crore" in blob or "rs. crore" in blob or "(₹crore" in blob or "rs crore" in blob:
        return ("crore", 1.0)
    if "in million" in blob or "₹ million" in blob or "h million" in blob or "rs. million" in blob:
        return ("million", 0.1)
    if "in lakh" in blob or "₹ lakh" in blob:
        return ("lakh", 0.01)
    if "in thousand" in blob or "₹ thousand" in blob or "in '000" in blob or "(₹ in '000)" in blob:
        return ("thousand", 0.0001)
    # Default: crore (most common in modern Indian ARs).
    return ("crore", 1.0)


# Match a markdown table row: starts with "|", at least 2 cells.
_ROW_RE = re.compile(r"^\|.+\|\s*$", re.MULTILINE)


@dataclass
class _MarkdownTable:
    """Lightly typed representation of a parsed markdown table."""
    headers: list[str]  # row 0 (above the |---| separator)
    rows: list[list[str]]  # data rows after separator
    raw_start: int  # offset in section where this table starts


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into cells. Strips leading/trailing pipes."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_separator(cells: list[str]) -> bool:
    """Pipe row that's the markdown column separator (| --- | --- |)."""
    return all(re.match(r"^:?-{3,}:?$", c.strip()) for c in cells if c.strip())


def _parse_tables(section_text: str) -> list[_MarkdownTable]:
    """Walk section_text and return all markdown tables found.

    A table is a contiguous run of pipe-rows separated by an optional
    header-separator (the |---| row). Tables are split when a non-pipe
    line interrupts the run.
    """
    tables: list[_MarkdownTable] = []
    lines = section_text.split("\n")
    i = 0
    n = len(lines)
    cumulative_offset = 0
    while i < n:
        if not lines[i].strip().startswith("|"):
            cumulative_offset += len(lines[i]) + 1
            i += 1
            continue
        # Start of a pipe-block.
        block_start_offset = cumulative_offset
        block_lines: list[str] = []
        while i < n and lines[i].strip().startswith("|"):
            block_lines.append(lines[i])
            cumulative_offset += len(lines[i]) + 1
            i += 1
        # Process the block.
        rows = [_split_row(bl) for bl in block_lines]
        # Find the |---| separator row (any row of all-dashes cells).
        sep_idx = next(
            (idx for idx, r in enumerate(rows) if _is_separator(r)),
            None,
        )
        if sep_idx is None:
            # No header — treat first row as headers, rest as data.
            if len(rows) >= 2:
                tables.append(_MarkdownTable(headers=rows[0], rows=rows[1:], raw_start=block_start_offset))
            continue
        headers = rows[sep_idx - 1] if sep_idx >= 1 else rows[0]
        data = rows[sep_idx + 1:]
        if data:
            tables.append(_MarkdownTable(headers=headers, rows=data, raw_start=block_start_offset))
    return tables


def _match_metric(label: str) -> str | None:
    """Map a row's first-cell label to a canonical metric, or None.

    Two alias kinds:
      - "exact_phrase": substring match anywhere in the label.
      - "starts_with":  label must begin with the alias (after normalization).
                        Used for short ambiguous tokens like "sales" or
                        "turnover" so "fixed asset turnover" doesn't match
                        revenue, "net profit margin" doesn't match pat, etc.
    """
    raw = re.sub(r"\s+", " ", label).strip().lower()
    if not raw:
        return None
    # Reject explicit ratio / percent rows BEFORE stripping suffixes —
    # otherwise "PAT/Turnover (%)" → "pat/turnover" still hits "pat" alias.
    # Use word-boundary checks for "ratio" so that "operations" (which
    # contains the substring "ratio") isn't rejected.
    if (
        "%" in raw
        or "(no. of times)" in raw
        or "no. of times" in raw
        or re.search(r"\bratio\b", raw)
        or "/" in raw  # PAT/Turnover, Asset/Equity etc are ratios
    ):
        return None
    if raw.startswith((
        "return on", "fixed asset", "net profit margin",
        "operating margin", "ebitda margin", "ebit margin",
        "as %", "as a %",
    )):
        return None
    # Now safe to strip footnote markers and parenthetical suffixes.
    norm = re.sub(r"\s*[\*\^#@†‡]+\s*$", "", raw)
    norm = re.sub(r"\s*\(.*?\)\s*$", "", norm).strip()
    for canonical, aliases in _METRIC_ALIASES.items():
        for alias_text, kind in aliases:
            if kind == "starts_with":
                if norm.startswith(alias_text):
                    return canonical
            else:  # exact_phrase
                if alias_text in norm:
                    return canonical
    return None


def _extract_year_columns(headers: list[str]) -> list[tuple[int, str]]:
    """Return [(column_index, fy_end_iso), ...] for header cells that
    parse as a year. Column 0 is reserved for the row-label and skipped."""
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    for idx, h in enumerate(headers):
        if idx == 0:
            continue
        fy = _normalize_year(h)
        if fy is None:
            continue
        # Some ARs duplicate years (e.g. TCS has two FY 2024 columns —
        # restated and as-reported). Take the FIRST occurrence (typically
        # the most recent restated presentation).
        if fy in seen:
            continue
        seen.add(fy)
        out.append((idx, fy))
    return out


def _looks_image_rendered(section_text: str) -> bool:
    """Detect a section that's text-located but image-rendered.

    Heuristic: section is found (has the heading) but contains <500 chars
    OR no markdown tables OR markdown tables but very few number cells.
    """
    if len(section_text) < 500:
        return True
    tables = _parse_tables(section_text)
    if not tables:
        return True
    # Count cells that look like numbers across all tables.
    digit_cells = 0
    for t in tables:
        for row in t.rows:
            for c in row:
                if _parse_number(c) is not None:
                    digit_cells += 1
    return digit_cells < 30  # ~5 metrics × 5+ years


def parse_five_year_summary(
    section_text: str,
    source_ar_fy: str | None = None,
    pre_section_context: str | None = None,
) -> list[FiveYearHighlight]:
    """Parse the AR five/ten-year highlights section to canonical rows.

    Returns one FiveYearHighlight per fiscal year detected in the table
    columns. If the section is image-rendered (no parseable tables, or
    too sparse), returns an empty list — caller checks `_looks_image_rendered`
    separately to differentiate empty from image-rendered.

    Multiple tables under one section are merged: each year's row is built
    by accumulating values across all tables (HINDUNILVR splits BS, KPI
    ratios, and 'others' into 3 stacked tables under one heading).

    pre_section_context: optional 1-3KB of markdown immediately preceding
    the section heading. Used to find unit annotations that ICICI-style ARs
    place in prose above the heading (e.g., "` in billion") rather than in
    column headers. Pass None when the caller doesn't have access to it.
    """
    tables = _parse_tables(section_text)
    if not tables:
        return []
    blob_for_unit = (pre_section_context or "") + " " + section_text
    unit_label, unit_mult = _detect_unit(
        [c for t in tables for c in t.headers], blob_for_unit,
    )

    # Map fy_end → dict[metric → value]. Build incrementally across tables.
    by_year: dict[str, dict[str, float | None]] = {}

    for tbl in tables:
        # Some tables have year headers in row 0 (post-separator data row 0),
        # if the actual headers row above |--- | is just unit labels (HINDUNILVR
        # has IGAAP/INDAS labels in row 0, year labels in row 1).
        # Scan candidate rows for the row with the most parseable years.
        year_cols_h = _extract_year_columns(tbl.headers)
        candidates: list[tuple[int, list[tuple[int, str]]]] = [(-1, year_cols_h)]
        for ri in range(min(3, len(tbl.rows))):
            candidates.append((ri, _extract_year_columns(tbl.rows[ri])))
        # Pick the row with the most year columns. On tie, prefer earlier row
        # (headers > rows[0] > rows[1] > rows[2]).
        best_idx, year_cols = max(
            candidates, key=lambda c: (len(c[1]), -c[0]),
        )
        if len(year_cols) < 3:
            # Probably not a years-as-columns table — try transposed.
            transposed_rows = _try_transposed(tbl, unit_mult)
            for fy_end, metrics in transposed_rows.items():
                bucket = by_year.setdefault(fy_end, {})
                for k, v in metrics.items():
                    if bucket.get(k) is None and v is not None:
                        bucket[k] = v
            continue

        # Data starts after the picked year row.
        # best_idx == -1 means year row is in headers; data begins at rows[0].
        # Else data begins at rows[best_idx + 1].
        if best_idx == -1:
            data_rows = tbl.rows
        else:
            data_rows = tbl.rows[best_idx + 1:]

        for row in data_rows:
            if not row:
                continue
            label = row[0]
            metric = _match_metric(label)
            if metric is None:
                continue
            for col_idx, fy_end in year_cols:
                if col_idx >= len(row):
                    continue
                val = _parse_number(row[col_idx])
                if val is None:
                    continue
                # Convert units for monetary columns (skip pure ratios).
                # Exclude per-share + counts from unit conversion — they're
                # already in their natural unit (rupees, millions of shares).
                if metric not in {"eps", "dividend_per_share", "num_shares"}:
                    val = val * unit_mult
                bucket = by_year.setdefault(fy_end, {})
                # First-write wins per metric per year (don't overwrite from
                # ratio/sub-tables that might have similar labels).
                if bucket.get(metric) is None:
                    bucket[metric] = val

    # Build typed rows.
    out: list[FiveYearHighlight] = []
    for fy_end in sorted(by_year.keys(), reverse=True):
        bucket = by_year[fy_end]
        # Skip rows where we got literally nothing — pure ratio-only
        # year that didn't match any of our canonical metrics.
        if not any(v is not None for v in bucket.values()):
            continue
        out.append(FiveYearHighlight(
            fy_end=fy_end,
            revenue=bucket.get("revenue"),
            operating_profit=bucket.get("operating_profit"),
            pat=bucket.get("pat"),
            eps=bucket.get("eps"),
            net_worth=bucket.get("net_worth"),
            total_assets=bucket.get("total_assets"),
            borrowings=bucket.get("borrowings"),
            cfo=bucket.get("cfo"),
            capex=bucket.get("capex"),
            dividend_per_share=bucket.get("dividend_per_share"),
            num_shares=bucket.get("num_shares"),
            source_ar_fy=source_ar_fy,
            raw_unit=unit_label,
        ))
    return out


def _try_transposed(tbl: _MarkdownTable, unit_mult: float) -> dict[str, dict[str, float | None]]:
    """Handle ICICIBANK-style transposed table.

    Layout: column 0 = year, columns 1..N = metric values, last row = metric
    labels. Detect when:
      - column 0 of every data row parses as a year, AND
      - the last row's column 0 is *not* a year but the rest are metric
        labels matching our aliases.

    Special case: when Docling places the FIRST year in the headers row
    (because it's the first data row above the |---| separator), prepend
    those headers as a synthetic data row so the latest year isn't missed
    (ICICIBANK FY25 — year 2025 appears in headers).
    """
    if len(tbl.rows) < 3:
        return {}

    # Promote header row to data row when it leads with a year token.
    rows: list[list[str]] = list(tbl.rows)
    fy_in_headers = _normalize_year(tbl.headers[0]) if tbl.headers else None
    if fy_in_headers and len(tbl.headers) >= 4:
        rows.insert(0, list(tbl.headers))

    # Last data row carries the metric labels.
    label_row = rows[-1]
    data_rows = rows[:-1]
    # Year-of-column-0 check on every data row.
    fy_per_row: list[tuple[int, str]] = []
    for ri, r in enumerate(data_rows):
        if not r:
            continue
        fy = _normalize_year(r[0])
        if fy is None:
            return {}  # not transposed
        fy_per_row.append((ri, fy))
    if len(fy_per_row) < 3:
        return {}
    # Map each remaining column to a canonical metric via the label_row.
    col_to_metric: dict[int, str] = {}
    for ci in range(1, len(label_row)):
        m = _match_metric(label_row[ci]) if ci < len(label_row) else None
        if m:
            col_to_metric[ci] = m

    out: dict[str, dict[str, float | None]] = {}
    for ri, fy in fy_per_row:
        row = data_rows[ri]
        bucket: dict[str, float | None] = {}
        for ci, metric in col_to_metric.items():
            if ci >= len(row):
                continue
            val = _parse_number(row[ci])
            if val is None:
                continue
            if metric not in {"eps", "dividend_per_share", "num_shares"}:
                val = val * unit_mult
            bucket.setdefault(metric, val)
        if bucket:
            out[fy] = bucket
    return out
