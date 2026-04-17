"""Download annual report PDFs from tracked URLs.

URLs live in company_documents table (populated by Screener's documents API
under doc_type='annual_report'). This module resolves them to vault paths
and downloads on-demand.

Vault layout: ~/vault/stocks/{SYMBOL}/filings/FY??/annual_report.pdf
(year-keyed, NOT quarter-keyed — ARs are annual)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)

_VAULT_BASE = Path.home() / "vault" / "stocks"


_FY_RE = re.compile(r"(?:Financial Year|FY|fy)\s*(\d{4})", re.IGNORECASE)


def _period_to_fy_label(period: str) -> str | None:
    """Convert Screener period like 'Financial Year 2025' to 'FY25'.

    Returns None if the period string doesn't contain a parseable year.
    """
    m = _FY_RE.search(period or "")
    if not m:
        return None
    year = int(m.group(1))
    return f"FY{year % 100:02d}"


def _download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF with BSE-friendly browser headers. Returns True on success."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/pdf,application/octet-stream,*/*",
    }
    for attempt in range(2):
        try:
            with httpx.Client(follow_redirects=True, timeout=120, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200 and len(resp.content) > 10_000:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(resp.content)
                    return True
                if resp.status_code in (403, 404, 406):
                    return False
        except httpx.TimeoutException:
            if attempt == 0:
                continue
        except Exception as e:
            logger.warning("AR download failed for %s: %s", url, e)
            return False
    return False


def list_ar_urls(symbol: str, max_years: int = 3) -> list[dict]:
    """Return tracked AR URLs for a symbol, newest first.

    Each dict: {fy_label: 'FY25', period: 'Financial Year 2025', url: '...'}.
    Skips entries with unparseable periods.
    """
    symbol = symbol.upper()
    results: list[dict] = []
    with FlowStore() as store:
        rows = store._conn.execute(
            "SELECT period, url FROM company_documents "
            "WHERE symbol = ? AND doc_type = 'annual_report' "
            "ORDER BY period DESC",
            (symbol,),
        ).fetchall()
    seen: set[str] = set()
    for row in rows:
        fy = _period_to_fy_label(row["period"])
        if not fy or fy in seen:
            continue
        seen.add(fy)
        results.append({"fy_label": fy, "period": row["period"], "url": row["url"]})
        if len(results) >= max_years:
            break
    return results


def ensure_annual_reports(symbol: str, max_years: int = 3) -> int:
    """Download missing AR PDFs for the N most-recent years. Returns count downloaded."""
    symbol = symbol.upper()
    downloaded = 0
    vault_base = Path.home() / "vault" / "stocks"
    for entry in list_ar_urls(symbol, max_years=max_years):
        dest = vault_base / symbol / "filings" / entry["fy_label"] / "annual_report.pdf"
        if dest.exists():
            continue
        if _download_pdf(entry["url"], dest):
            logger.info("[ar] %s: downloaded %s (%s)", symbol, entry["fy_label"], entry["period"])
            downloaded += 1
        else:
            logger.warning("[ar] %s: failed to download %s from %s", symbol, entry["fy_label"], entry["url"])
    return downloaded


def find_ar_pdfs(symbol: str, max_years: int = 2) -> list[Path]:
    """Return the most recent N AR PDF paths in the vault, newest first."""
    symbol = symbol.upper()
    # Resolve vault base at call-time so tests monkeypatching HOME work.
    base = Path.home() / "vault" / "stocks" / symbol / "filings"
    if not base.exists():
        return []
    found: list[tuple[int, Path]] = []
    for year_dir in base.iterdir():
        if not year_dir.is_dir():
            continue
        name = year_dir.name
        # Match FY?? directories, skip FY??-Q? (quarter dirs)
        if not re.fullmatch(r"FY\d{2}", name):
            continue
        ar = year_dir / "annual_report.pdf"
        if not ar.exists():
            continue
        try:
            fy_num = int(name[2:4])
        except ValueError:
            continue
        found.append((fy_num, ar))
    found.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in found[:max_years]]
