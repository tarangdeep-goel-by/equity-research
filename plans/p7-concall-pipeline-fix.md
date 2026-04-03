# P-7: Concall Pipeline Fix — Use Screener Transcript URLs

## Problem

We have two sources of concall transcripts that aren't connected:

1. **BSE filing downloads** → saved to `~/vault/stocks/{SYM}/filings/FY26-Q3/concall.pdf`
   - Unreliable: 404/406 errors, KOTAKBANK got 3/11 quarters
   - Filed under generic categories, hard to identify concall vs results vs investor deck

2. **Screener document URLs** → stored in `company_documents` table as `concall_transcript`
   - Reliable: direct links to company IR sites (kotak.com, icicibank.com, S3)
   - KOTAKBANK has 36 transcript URLs, ICICIBANK has 39
   - Already fetched during refresh — just not downloaded as PDFs

The concall extractor (`_find_concall_pdfs`) only looks for BSE-downloaded files in the vault, ignoring the Screener URLs entirely.

## Goal

Make transcript PDFs reliably available for extraction by using Screener URLs as the primary source, with BSE as fallback. KOTAKBANK should go from 3 concalls → 6+.

---

## Changes

### 1. Add period→FY quarter mapping utility

**File:** `flowtracker/research/concall_extractor.py`

Screener stores periods as "Jan 2026", "Oct 2025", etc. We need to map these to FY quarters:

```
Jan 2026 → FY26-Q3  (Oct-Dec quarter, results announced in Jan)
Oct 2025 → FY26-Q2  (Jul-Sep quarter, results announced in Oct)
Jul 2025 → FY26-Q1  (Apr-Jun quarter, results announced in Jul)
Apr 2025 → FY25-Q4  (Jan-Mar quarter, results announced in Apr)
```

Mapping logic:
```python
def _screener_period_to_fy_quarter(period: str) -> str:
    """Convert 'Jan 2026' to 'FY26-Q3'."""
    month_str, year_str = period.split()
    month = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
             "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[month_str[:3]]
    year = int(year_str)
    
    # Results month → which quarter's results
    # Jan-Mar announcement → Q3 (Oct-Dec) or Q4 (Jan-Mar) of prev FY
    if month in (1, 2, 3):    # Jan-Mar → Q3 results (Oct-Dec)
        fy = year % 100        # FY26 for Jan 2026
        return f"FY{fy:02d}-Q3"
    elif month in (4, 5, 6):  # Apr-Jun → Q4 results (Jan-Mar)
        fy = year % 100        # FY25 for Apr 2025
        return f"FY{fy:02d}-Q4"
    elif month in (7, 8, 9):  # Jul-Sep → Q1 results (Apr-Jun)
        fy = (year + 1) % 100  # FY26 for Jul 2025
        return f"FY{fy:02d}-Q1"
    else:                     # Oct-Dec → Q2 results (Jul-Sep)
        fy = (year + 1) % 100  # FY26 for Oct 2025
        return f"FY{fy:02d}-Q2"
```

**Edge case:** Some companies have two entries for the same month (e.g., ICICIBANK has two "Jan 2026" entries — likely standalone + consolidated, or an analyst meet). Take the first/most recent one.

**Verify:** Map all KOTAKBANK periods and confirm they align with known quarterly filing dates.

### 2. Add transcript download function

**File:** `flowtracker/research/concall_extractor.py`

```python
def _download_transcript_from_url(url: str, dest_path: Path) -> bool:
    """Download a transcript PDF from a Screener-sourced URL."""
    import httpx
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(resp.content)
                return True
    except Exception:
        pass
    return False
```

URLs are hosted on:
- Company IR sites (icicibank.com, kotak.com) — stable
- S3 (stockdiscovery.s3.amazonaws.com) — stable  
- BSE (bseindia.com) — same flaky source, skip if BSE URL

### 3. Update `_find_concall_pdfs` to use Screener URLs as fallback

**File:** `flowtracker/research/concall_extractor.py`

Current flow:
1. Scan vault `filings/FY??-Q?/concall.pdf` → return what exists

New flow:
1. Scan vault `filings/FY??-Q?/concall.pdf` → collect what exists
2. If fewer than `quarters` found, query `company_documents` table for `concall_transcript` URLs
3. Map each URL's period to FY quarter using `_screener_period_to_fy_quarter`
4. For quarters not already in vault, download the PDF from the Screener URL
5. Save to vault as `filings/FY??-Q?/concall.pdf` (same location, cached for next time)
6. Apply the recency filter (within ~2 FY years)
7. Return up to `quarters` paths

```python
def _find_concall_pdfs(symbol: str, quarters: int = 6) -> list[Path]:
    # ... existing vault scan ...
    
    # If we have fewer than desired, try Screener URLs
    if len(results) < quarters:
        from flowtracker.store import FlowStore
        with FlowStore() as store:
            docs = store._conn.execute(
                "SELECT period, url FROM company_documents "
                "WHERE symbol = ? AND doc_type = 'concall_transcript' "
                "ORDER BY period DESC",
                (symbol.upper(),)
            ).fetchall()
        
        for doc in docs:
            fy_q = _screener_period_to_fy_quarter(doc["period"])
            dest = _VAULT_BASE / symbol.upper() / "filings" / fy_q / "concall.pdf"
            if dest.exists():
                continue  # already have it
            if _fy_sort_key_from_str(fy_q) < min_key:
                continue  # too old
            if _download_transcript_from_url(doc["url"], dest):
                results.append(dest)
            if len(results) >= quarters:
                break
        
        # Re-sort by recency
        results.sort(key=lambda p: _fy_sort_key(p.parent), reverse=True)
    
    return results[:quarters]
```

### 4. Add transcript download to refresh pipeline

**File:** `flowtracker/research/refresh.py`

After the `company_documents` fetch in `refresh_for_research`, download the latest 6 transcript PDFs:

```python
# After company_documents fetch
try:
    from flowtracker.research.concall_extractor import (
        _screener_period_to_fy_quarter, _download_transcript_from_url
    )
    transcript_docs = store._conn.execute(
        "SELECT period, url FROM company_documents "
        "WHERE symbol = ? AND doc_type = 'concall_transcript' "
        "ORDER BY period DESC LIMIT 6",
        (symbol,)
    ).fetchall()
    downloaded = 0
    for doc in transcript_docs:
        fy_q = _screener_period_to_fy_quarter(doc["period"])
        dest = vault_base / symbol / "filings" / fy_q / "concall.pdf"
        if dest.exists():
            continue
        if _download_transcript_from_url(doc["url"], dest):
            downloaded += 1
    if downloaded:
        _ok("transcript_downloads", downloaded)
except Exception as e:
    _skip("transcript_downloads", str(e))
```

This runs BEFORE the BSE filing download, so Screener transcripts are primary and BSE fills gaps.

### 5. Handle duplicate periods

Screener sometimes has two entries for the same month (e.g., two "Jan 2026" for ICICIBANK). These could be:
- Standalone + consolidated concall
- Analyst/investor meet + earnings call
- Updated transcript

**Rule:** Take the first URL for each unique FY quarter. If we already have a concall.pdf for that quarter (from any source), skip.

---

## Files Modified

| File | Changes |
|------|---------|
| `research/concall_extractor.py` | Period mapping, URL download, updated `_find_concall_pdfs` |
| `research/refresh.py` | Download transcripts from Screener URLs during refresh |

## Verification

1. **KOTAKBANK coverage:** Should go from 3 concalls → 6+ after running refresh
2. **ICICIBANK coverage:** Should stay at 4+ (already had good BSE coverage)  
3. **URL reliability:** Download success rate from Screener URLs should be >90% (vs BSE ~30%)
4. **Extraction quality:** Run concall extraction on newly-downloaded transcripts — verify JSON output
5. **No regressions:** Existing BSE-downloaded concalls still found and used
6. **Period mapping accuracy:** Verify Jan 2026 → FY26-Q3, Oct 2025 → FY26-Q2, etc.

## Expected Impact

| Stock | Before (BSE only) | After (Screener + BSE) |
|-------|-------------------|----------------------|
| KOTAKBANK | 3 concalls | 6+ concalls |
| ICICIBANK | 4 concalls | 6+ concalls |
| Any new stock | Depends on BSE reliability | 6 concalls on first run |

## Estimated Effort

~1 hour. All changes are in 2 files. No new dependencies. No new tables. Downloads cached in vault.

## Dependencies

- Screener.in login credentials (already configured)
- `company_documents` table populated (already done during refresh)
- httpx for downloading (already a dependency)
