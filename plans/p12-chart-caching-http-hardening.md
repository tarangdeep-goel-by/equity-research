# P-12: Chart Caching + HTTP Client Hardening

## Context

Gemini standalone review flagged two infrastructure issues:
1. **Chart rendering bottleneck** — 25 chart types rendered synchronously via matplotlib, no caching. Charts are generated during Phase 1 by agents via MCP tools (NOT in Phase 3 assembly). Since agents run max 3 concurrent, this is partially parallel already, but each chart blocks the agent's turn.
2. **HTTP client fragility** — Screener.in and FMP have zero retry logic. Bhavcopy has a broken backoff formula. NSE family is solid (3x retry, exponential backoff, 403 handling).

## Package 1: Chart Caching [S]

**Insight from exploration:** Charts are generated during Phase 1 by agents calling `render_chart()` MCP tool. Assembly (Phase 3) does NOT render charts — it just embeds markdown image references already in agent reports. The bottleneck is per-agent, not per-assembly.

**The fix is NOT async rendering** — it's caching. Charts for a given symbol don't change between the refresh and the agent run (data is in SQLite). If we cache charts after `refresh_for_research()` or check freshness before rendering, we skip redundant matplotlib calls.

### Changes

**File: `flowtracker/research/charts.py`**

Add a freshness check to `render_chart()` (line ~1505). Before rendering, check if the PNG already exists and is recent (< 1 hour old, since refresh just ran):

```python
def render_chart(symbol: str, chart_type: str, data=None) -> dict:
    path = _chart_path(symbol, chart_type)  # ~/vault/stocks/{SYMBOL}/charts/{chart_type}.png
    
    # Cache check: skip rendering if chart file exists and is fresh (< 1 hour)
    if path.exists():
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds < 3600 and data is None:  # only cache when no custom data passed
            return {"path": str(path), "chart_type": chart_type, "symbol": symbol,
                    "embed_markdown": f"![{symbol} {chart_type}]({path})", "cached": True}
    
    # ... existing rendering logic ...
```

This is a ~10-line addition. No structural changes. Agents that call `render_chart` multiple times for the same stock (e.g., if re-run after verification) get instant cache hits.

**Optional: Pre-render common charts in Phase 0.5**

In `_build_baseline_context()` (agent.py), after building the baseline JSON, pre-render the 5 most common chart types (price, pe, shareholding, revenue_profit, composite_radar) synchronously. This takes ~3-5 seconds but means ALL 7 agents get cache hits on their first chart call.

```python
# In _build_baseline_context(), after baseline dict is built:
from flowtracker.research.charts import render_chart as _render
for ct in ["price", "pe", "shareholding", "revenue_profit", "composite_radar"]:
    try:
        _render(symbol, ct)
    except Exception:
        pass  # non-critical
```

---

## Package 2: HTTP Client Hardening [M]

### Current State (from exploration)

| Client | Retries | Backoff | 403 | Status |
|--------|---------|---------|-----|--------|
| NSE family (client, scan, holding, deals, insider) | 3x | Exponential | Yes | **Solid** |
| MF client | 3x | Exponential | N/A | **Solid** |
| **Screener** | None | None | None | **Critical gap** |
| **FMP** | None | None | N/A | **Critical gap** |
| **Bhavcopy** | 3x | **BROKEN** (`1**n = 1`) | N/A | Bug |
| Filing (PDF) | 3x | Linear | None | Minor |
| Commodities/Macro | None | None | None | Low priority |

### 2A. Fix Screener Client (highest priority — 50+ API calls per stock)

**File: `flowtracker/screener_client.py`**

Add a retry wrapper method. The client already uses `httpx.Client` with a session. Add:

```python
def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs) -> httpx.Response:
    """HTTP request with exponential backoff and session recovery."""
    import random
    for attempt in range(max_retries + 1):
        try:
            resp = self._client.request(method, url, **kwargs)
            if resp.status_code == 403:
                # Session expired — re-login
                self._login()
                continue
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if attempt == max_retries:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)  # jitter
            time.sleep(wait)
    raise httpx.HTTPError(f"Failed after {max_retries + 1} attempts: {url}")
```

Then replace direct `self._client.get(...)` calls with `self._request_with_retry("GET", ...)` in the ~11 API methods. Also update timeout from scalar `30` to component: `httpx.Timeout(connect=15, read=45, write=10, pool=10)`.

### 2B. Fix FMP Client

**File: `flowtracker/fmp_client.py`**

Same pattern — add `_request_with_retry()`. FMP returns 403 for exceeded rate limits and 429 for burst limits. Add both handling. Update timeout to component form.

### 2C. Fix Bhavcopy Backoff Bug

**File: `flowtracker/bhavcopy_client.py`**

Find the backoff formula. Currently `BACKOFF_BASE ** (attempt + 1)` where `BACKOFF_BASE = 1`. This evaluates to `1` always.

Fix: change to `BACKOFF_BASE * (2 ** attempt)` to match the NSE client pattern, or set `BACKOFF_BASE = 2`.

### 2D. Add Jitter to NSE Family (optional)

The NSE family already has exponential backoff but no jitter. Add `+ random.uniform(0, 1)` to prevent thundering herd when multiple agents hit NSE simultaneously. Files: `client.py`, `scan_client.py`, `holding_client.py`, `deals_client.py`, `insider_client.py`.

---

## Parallelization

Package 1 and 2 are independent:
```
Package 1 (Chart caching) — charts.py + agent.py
Package 2 (HTTP hardening) — screener_client.py, fmp_client.py, bhavcopy_client.py
```

## Files to Modify

| File | Package | Change |
|------|---------|--------|
| `flowtracker/research/charts.py` | 1 | Add cache check (~10 lines) |
| `flowtracker/research/agent.py` | 1 | Optional: pre-render in _build_baseline_context |
| `flowtracker/screener_client.py` | 2A | Add _request_with_retry, update 11 methods, fix timeout |
| `flowtracker/fmp_client.py` | 2B | Add _request_with_retry, update methods, fix timeout |
| `flowtracker/bhavcopy_client.py` | 2C | Fix backoff formula (1-line) |

## Verification

1. `uv run flowtrack research data chart_data -s SBIN` — renders chart, check file exists
2. Run same command again — should return `cached: true` in output
3. `uv run pytest tests/ -m "not slow" -q` — all tests pass
4. `uv run flowtrack fund fetch -s RELIANCE` — Screener client retry works (check logs for retry on transient failure)
5. `uv run flowtrack fmp fetch -s RELIANCE` — FMP retry works

## Estimated Impact

| Metric | Before | After |
|--------|--------|-------|
| Chart rendering (repeat runs) | ~3-5s per chart | ~0ms (cache hit) |
| Screener transient failures | Silent data loss | 3x retry with backoff |
| FMP transient failures | Silent empty returns | 3x retry with backoff |
| Bhavcopy backoff | Broken (always 1s) | Exponential (1s, 2s, 4s) |
