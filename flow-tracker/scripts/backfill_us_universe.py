"""Backfill the US universe into the us_* tables — PARALLEL.

Universe = all NASDAQ + NYSE/AMEX **common stocks** (NASDAQ Trader symbol
directory, ETF/test/warrant/unit/preferred excluded) ∪ S&P 500. For each ticker,
``refresh_us`` registers the symbol (granular industry), pulls EDGAR fundamentals
+ yfinance prices/valuation/estimates, and builds the us_company_snapshot. Writes
ONLY us_* + symbol_registry (additive — zero India risk).

Parallel: a thread pool (network-bound work releases the GIL). Each WORKER thread
owns its own FlowStore (sqlite check_same_thread + WAL; busy_timeout bumped for
write contention). EDGAR's per-client ≤10 req/s throttle + ~1 companyfacts fetch
per symbol keeps aggregate EDGAR load well under the limit at this worker count;
yfinance is the practical throttle, so keep workers modest (default 8).

Resumable: skips any symbol that already has a us_company_snapshot row.
Best-effort: a failing symbol is logged and skipped.

Run (long; use tmux):
    uv run python scripts/backfill_us_universe.py [--workers N] [--limit N] [--sp500-only]
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import httpx

from flowtracker.research.us_refresh import refresh_us

_UA = {"User-Agent": "flowtracker-research tarangdeepgoel2000@gmail.com"}
_SP500_CSV = ("https://raw.githubusercontent.com/datasets/"
              "s-and-p-500-companies/main/data/constituents.csv")
_NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Security-name keywords that mark non-common-stock issues to drop.
_NONCOMMON = ("warrant", "unit", "preferred", "depositary", "depository",
              " rights", "%", "redeemable", "note due", "subordinated")


def _valid_ticker(s: str) -> bool:
    return bool(s) and len(s) <= 6 and all(c.isalnum() or c == "-" for c in s)


def _norm(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")


def _sp500() -> set[str]:
    try:
        text = httpx.get(_SP500_CSV, headers=_UA, follow_redirects=True, timeout=30).text
        out = {_norm(r["Symbol"]) for r in csv.DictReader(StringIO(text)) if r.get("Symbol")}
        return {s for s in out if _valid_ticker(s)}
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] sp500: {e}", flush=True)
        return set()


def _nasdaq_dir(url: str, sym_col: str) -> set[str]:
    """Parse a NASDAQ Trader pipe-delimited directory → common-stock tickers."""
    out: set[str] = set()
    try:
        text = httpx.get(url, headers=_UA, follow_redirects=True, timeout=45).text
        for row in csv.DictReader(StringIO(text), delimiter="|"):
            sym = row.get(sym_col) or ""
            if not sym or sym.startswith("File Creation"):
                continue
            if (row.get("Test Issue") or "").strip() == "Y":
                continue
            if (row.get("ETF") or "").strip() == "Y":
                continue
            name = (row.get("Security Name") or "").lower()
            if any(k in name for k in _NONCOMMON):
                continue
            s = _norm(sym)
            if _valid_ticker(s):
                out.add(s)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] {url}: {e}", flush=True)
    return out


def get_universe(sp500_only: bool = False) -> list[str]:
    syms: set[str] = set()
    sp = _sp500()
    print(f"  S&P 500: {len(sp)}", flush=True)
    syms |= sp
    if not sp500_only:
        nq = _nasdaq_dir(_NASDAQ_LISTED, "Symbol")
        print(f"  NASDAQ-listed common: {len(nq)}", flush=True)
        syms |= nq
        oth = _nasdaq_dir(_OTHER_LISTED, "ACT Symbol")
        print(f"  NYSE/AMEX-listed common: {len(oth)}", flush=True)
        syms |= oth
    return sorted(syms)


_local = threading.local()
_lock = threading.Lock()
_counts = {"built": 0, "skipped": 0, "failed": 0, "n": 0}


def _store_for_thread():
    """One FlowStore per worker thread (sqlite check_same_thread)."""
    st = getattr(_local, "store", None)
    if st is None:
        from flowtracker.store import FlowStore

        st = FlowStore()
        st._conn.execute("PRAGMA busy_timeout=60000")  # 60s — wait, don't error, on write lock
        _local.store = st
    return st


def _process(symbol: str, total: int) -> None:
    store = _store_for_thread()
    try:
        if (store.get_us_company_snapshot(symbol, "NASDAQ")
                or store.get_us_company_snapshot(symbol, "NYSE")):
            with _lock:
                _counts["skipped"] += 1
                _counts["n"] += 1
            return
        summary = refresh_us(symbol, store=store, skip_insider=True,
                             skip_short_interest=True)
        got = {k: v for k, v in summary.items() if v}
        with _lock:
            _counts["built"] += 1
            _counts["n"] += 1
            i = _counts["n"]
        print(f"[{i}/{total}] {symbol}: {got}", flush=True)
    except Exception as e:  # noqa: BLE001
        with _lock:
            _counts["failed"] += 1
            _counts["n"] += 1
            i = _counts["n"]
        print(f"[{i}/{total}] {symbol}: FAILED {e}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="cap universe (debug)")
    ap.add_argument("--sp500-only", action="store_true")
    args = ap.parse_args()

    print("Fetching US universe…", flush=True)
    universe = get_universe(sp500_only=args.sp500_only)
    if args.limit:
        universe = universe[: args.limit]
    total = len(universe)
    print(f"Universe: {total} tickers | workers={args.workers}\n", flush=True)
    if not universe:
        print("No tickers resolved — aborting.", flush=True)
        return 1

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_process, s, total) for s in universe]
        for _ in as_completed(futs):
            pass

    dt = time.time() - t0
    print(f"\nDONE in {dt/60:.1f} min — built={_counts['built']} "
          f"skipped(existing)={_counts['skipped']} failed={_counts['failed']} "
          f"({dt/max(total,1):.1f}s/sym avg)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
