#!/usr/bin/env python3
"""Backfill quarterly financial results from NSE India API for all scanner stocks.

Fetches consolidated P&L data going back to 2016, converts from lakhs to crores,
and upserts into the quarterly_results table.

NSE API pattern:
  1. GET corporate-financial-results?index=equities&period=Quarterly&symbol=X
     -> returns filing index (array of filings)
  2. GET corporate-financial-results-data?index=equities&params=...&seq_id=...&industry=...&ind=N&format=...
     -> returns actual P&L line items (values in lakhs)

Usage:
    source .venv/bin/activate
    python scripts/backfill_quarterly_nse.py --test 3     # test with 3 symbols
    python scripts/backfill_quarterly_nse.py               # all scanner symbols
    python scripts/backfill_quarterly_nse.py --resume      # skip symbols with >=20 quarters
    python scripts/backfill_quarterly_nse.py --symbol RELIANCE  # single symbol
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

import httpx

sys.path.insert(0, ".")

from flowtracker.fund_models import QuarterlyResult
from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)

# ── NSE API config ──────────────────────────────────────────────────────────

_BASE_URL = "https://www.nseindia.com"
_PREFLIGHT_URL = f"{_BASE_URL}/companies-listing/corporate-filings-financial-results"
_INDEX_URL = f"{_BASE_URL}/api/corporates-financial-results"
_DETAIL_URL = f"{_BASE_URL}/api/corporates-financial-results-data"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": _PREFLIGHT_URL,
}

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds
CUTOFF_YEAR = 2016

# Rotate client every N symbols to get fresh connections
CLIENT_ROTATE_INTERVAL = 20
# Cooldown after rotation (seconds)
CLIENT_ROTATE_COOLDOWN = 5


# ── NSE Client ──────────────────────────────────────────────────────────────

class NSEQuarterlyClient:
    """Client for NSE quarterly financial results API.

    Rotates the underlying httpx client periodically to avoid connection staleness.
    Uses adaptive rate-limiting: increases delay when errors are detected.
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None
        self._has_cookies = False
        self._request_count = 0
        self._adaptive_delay = 0.0  # Extra delay added when errors detected

    def _new_client(self) -> httpx.Client:
        """Create a fresh httpx client."""
        return httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0),
        )

    def _get_client(self) -> httpx.Client:
        """Get client, creating if needed."""
        if self._client is None:
            self._client = self._new_client()
            self._has_cookies = False
        return self._client

    def rotate_client(self) -> None:
        """Close old client and create fresh one. Resets cookies."""
        if self._client is not None:
            self._client.close()
        self._client = self._new_client()
        self._has_cookies = False
        self._request_count = 0

    def _ensure_cookies(self) -> None:
        """Hit the filings page to acquire session cookies."""
        client = self._get_client()
        resp = client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def _get_with_retry(self, url: str, params: dict) -> dict | list:
        """GET with cookie preflight, 403 retry, and adaptive rate-limiting."""
        last_error: Exception | None = None
        client = self._get_client()

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                # Adaptive delay: slow down when errors have been detected
                if self._adaptive_delay > 0:
                    time.sleep(self._adaptive_delay)

                resp = client.get(url, params=params)
                self._request_count += 1

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    self._adaptive_delay = min(self._adaptive_delay + 1.0, 5.0)
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                # Success: decay adaptive delay
                self._adaptive_delay = max(self._adaptive_delay - 0.2, 0.0)
                return resp.json()

            except Exception as e:
                last_error = e
                self._adaptive_delay = min(self._adaptive_delay + 0.5, 5.0)
                logger.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise RuntimeError(f"Failed after {MAX_RETRIES} attempts: {last_error}")

    def fetch_filing_index(self, symbol: str) -> list[dict]:
        """Fetch list of quarterly filings for a symbol."""
        data = self._get_with_retry(_INDEX_URL, {
            "index": "equities",
            "period": "Quarterly",
            "symbol": symbol.upper(),
        })
        if not isinstance(data, list):
            return []
        return data

    def fetch_filing_detail(self, filing: dict) -> dict | None:
        """Fetch P&L detail for a single filing.

        The API returns a wrapper dict with 'resultsData2' containing the actual P&L fields.
        """
        params_val = filing.get("params")
        seq_id = filing.get("seqNumber")
        industry = filing.get("industry", "")
        fmt = filing.get("format", "")

        if not params_val or not seq_id:
            return None

        data = self._get_with_retry(_DETAIL_URL, {
            "index": "equities",
            "params": params_val,
            "seq_id": seq_id,
            "industry": industry,
            "ind": "N",
            "format": fmt,
        })
        if not isinstance(data, dict):
            return None

        # P&L line items are nested in resultsData2
        results_data = data.get("resultsData2")
        if isinstance(results_data, dict):
            return results_data
        # Fallback: maybe the fields are at top level (older format)
        return data

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self) -> NSEQuarterlyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ── Helpers ─────────────────────────────────────────────────────────────────

def is_consolidated(filing: dict) -> bool:
    """Check if a filing is consolidated (vs standalone).

    The 'consolidated' field is "Consolidated" or "Non-Consolidated".
    Must match exactly -- "Non-Consolidated" should NOT count.
    """
    con_field = str(filing.get("consolidated", "")).strip().lower()
    if con_field == "consolidated":
        return True
    # Also check other fields (reDesc, relatingTo) for the word
    for key in ("reDesc", "relatingTo"):
        val = str(filing.get(key, "")).lower()
        if "consolidated" in val and "non-consolidated" not in val:
            return True
    return False


def is_standalone(filing: dict) -> bool:
    """Check if a filing is explicitly standalone / non-consolidated."""
    con_field = str(filing.get("consolidated", "")).strip().lower()
    if con_field == "non-consolidated":
        return True
    for key in ("reDesc", "relatingTo"):
        val = str(filing.get(key, "")).lower()
        if "standalone" in val or "non-consolidated" in val:
            return True
    return False


def parse_quarter_end(filing: dict) -> str | None:
    """Extract quarter_end date as YYYY-MM-DD from filing metadata.

    The filing may have toDate, reDate, or broadcastDate fields.
    """
    # Try toDate first (most reliable -- it's the period end date)
    for key in ("toDate", "reDate", "broadcastDate"):
        raw = filing.get(key)
        if not raw:
            continue
        try:
            # Try various date formats
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    dt = datetime.strptime(raw.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        except Exception:
            continue
    return None


def safe_float(val) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None or val == "" or val == "-":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def lakhs_to_crores(val: float | None) -> float | None:
    """Convert lakhs to crores (divide by 100)."""
    if val is None:
        return None
    return round(val / 100, 4)


def filing_to_quarterly_result(symbol: str, quarter_end: str, detail: dict) -> QuarterlyResult:
    """Map NSE P&L detail fields to QuarterlyResult model.

    NSE values are in lakhs -> convert to crores.
    EPS is already per-share, no conversion needed.
    """
    revenue_lakhs = safe_float(detail.get("re_net_sale"))
    net_income_lakhs = safe_float(detail.get("re_con_pro_loss"))
    pbt_lakhs = safe_float(detail.get("re_pro_loss_bef_tax"))
    depreciation_lakhs = (
        safe_float(detail.get("re_dep"))
        or safe_float(detail.get("re_depr_und_exp"))
        or safe_float(detail.get("re_depreciation"))
    )
    eps_basic = safe_float(detail.get("re_basic_eps_for_cont_dic_opr"))

    revenue = lakhs_to_crores(revenue_lakhs)
    net_income = lakhs_to_crores(net_income_lakhs)
    pbt = lakhs_to_crores(pbt_lakhs)
    depreciation = lakhs_to_crores(depreciation_lakhs)

    # Operating income ~ PBT (no interest breakout in this API easily)
    operating_income = pbt

    # EBITDA ~ PBT + depreciation (rough, but best we have from this endpoint)
    ebitda = None
    if pbt is not None and depreciation is not None:
        ebitda = round(pbt + depreciation, 4)

    # Margins
    operating_margin = None
    if operating_income is not None and revenue and revenue != 0:
        operating_margin = operating_income / revenue

    net_margin = None
    if net_income is not None and revenue and revenue != 0:
        net_margin = net_income / revenue

    return QuarterlyResult(
        symbol=symbol,
        quarter_end=quarter_end,
        revenue=revenue,
        gross_profit=None,  # Not available from this endpoint
        operating_income=operating_income,
        net_income=net_income,
        ebitda=ebitda,
        eps=eps_basic,
        eps_diluted=None,  # Not easily available
        operating_margin=operating_margin,
        net_margin=net_margin,
    )


def filter_consolidated_filings(filings: list[dict]) -> list[dict]:
    """Filter filings to prefer consolidated, falling back to standalone.

    Strategy:
    1. If any filings are explicitly consolidated, use only those.
    2. Otherwise, use all filings (likely standalone-only companies).
    """
    consolidated = [f for f in filings if is_consolidated(f)]
    if consolidated:
        return consolidated

    # No consolidated found -- use all (likely standalone company)
    return filings


def quarter_end_after_cutoff(quarter_end: str) -> bool:
    """Check if quarter_end >= 2016-01-01."""
    try:
        return quarter_end >= f"{CUTOFF_YEAR}-01-01"
    except Exception:
        return True  # If we can't parse, include it


# ── Main ────────────────────────────────────────────────────────────────────

def backfill_symbol(
    nse: NSEQuarterlyClient,
    symbol: str,
    quarter_delay: float = 0.5,
) -> tuple[int, list[str]]:
    """Backfill all quarterly results for a single symbol.

    Returns (num_upserted, errors).
    """
    errors: list[str] = []

    # Step 1: Fetch filing index
    try:
        filings = nse.fetch_filing_index(symbol)
    except Exception as e:
        return 0, [f"index fetch: {e}"]

    if not filings:
        return 0, ["no filings found"]

    # Step 2: Filter for consolidated
    filings = filter_consolidated_filings(filings)

    # Step 3: For each filing, fetch detail and convert
    results: list[QuarterlyResult] = []
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 3  # Bail on symbol if 3 quarters fail in a row

    for filing in filings:
        quarter_end = parse_quarter_end(filing)
        if not quarter_end:
            errors.append("could not parse date from filing")
            continue

        # Skip filings before cutoff
        if not quarter_end_after_cutoff(quarter_end):
            continue

        try:
            detail = nse.fetch_filing_detail(filing)
            if not detail:
                errors.append(f"{quarter_end}: empty detail")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    errors.append("aborting: too many consecutive failures")
                    break
                continue

            qr = filing_to_quarterly_result(symbol, quarter_end, detail)
            results.append(qr)
            consecutive_failures = 0  # Reset on success

        except Exception as e:
            errors.append(f"{quarter_end}: {e}")
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                errors.append("aborting: too many consecutive failures")
                break

        time.sleep(quarter_delay)

    # Step 4: Upsert
    if results:
        with FlowStore() as store:
            store.upsert_quarterly_results(results)

    return len(results), errors


def main():
    parser = argparse.ArgumentParser(
        description="Backfill quarterly results from NSE India API"
    )
    parser.add_argument("--test", type=int, default=0, help="Test with N symbols")
    parser.add_argument("--resume", action="store_true",
                        help="Skip symbols with >= 20 quarterly records")
    parser.add_argument("--symbol", type=str, default="",
                        help="Run for a single symbol")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between symbols (seconds)")
    parser.add_argument("--quarter-delay", type=float, default=0.5,
                        help="Delay between quarter detail fetches (seconds)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Get symbols
    if args.symbol:
        all_symbols = [args.symbol.upper()]
    else:
        with FlowStore() as store:
            all_symbols = store.get_all_scanner_symbols()

    if not all_symbols:
        print("ERROR: No scanner symbols found. Run 'flowtrack scan fetch' first.")
        sys.exit(1)

    # Resume mode: skip symbols with sufficient data
    if args.resume:
        with FlowStore() as store:
            rich_symbols = set()
            for sym in all_symbols:
                count = store._conn.execute(
                    "SELECT COUNT(*) as cnt FROM quarterly_results WHERE symbol = ?",
                    (sym,),
                ).fetchone()["cnt"]
                if count >= 20:
                    rich_symbols.add(sym)
        before = len(all_symbols)
        all_symbols = [s for s in all_symbols if s not in rich_symbols]
        print(f"Resume: skipping {before - len(all_symbols)} symbols with >= 20 quarters")

    if args.test > 0:
        all_symbols = all_symbols[:args.test]

    total = len(all_symbols)
    print(f"\nNSE Quarterly Backfill: {total} symbols (back to {CUTOFF_YEAR})")
    print(f"  Delay: {args.delay}s between symbols, {args.quarter_delay}s between quarters")
    print()

    stats = {"upserted": 0, "errors": 0, "skipped": 0, "symbols_ok": 0}

    with NSEQuarterlyClient() as nse:
        for i, sym in enumerate(all_symbols, 1):
            pct = (i / total) * 100
            print(f"[{i:3d}/{total}] ({pct:5.1f}%) {sym:20s} ", end="", flush=True)

            # Rotate client periodically to get fresh connections
            if i > 1 and (i - 1) % CLIENT_ROTATE_INTERVAL == 0:
                print("[rotating client] ", end="", flush=True)
                nse.rotate_client()
                time.sleep(CLIENT_ROTATE_COOLDOWN)

            try:
                count, errors = backfill_symbol(nse, sym, args.quarter_delay)

                if count > 0:
                    stats["upserted"] += count
                    stats["symbols_ok"] += 1
                    print(f"Q:{count}", end="")
                else:
                    print("Q:0", end="")
                    stats["skipped"] += 1

                if errors:
                    stats["errors"] += len(errors)
                    print(f"  err:{len(errors)}", end="")

                print()

            except Exception as e:
                print(f"FAIL ({e})")
                stats["errors"] += 1

            # Rate limit between symbols
            if i < total:
                time.sleep(args.delay)

    # Summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"  Symbols processed:  {total}")
    print(f"  Symbols with data:  {stats['symbols_ok']}")
    print(f"  Quarters upserted:  {stats['upserted']}")
    print(f"  Symbols skipped:    {stats['skipped']}")
    print(f"  Errors:             {stats['errors']}")


if __name__ == "__main__":
    main()
