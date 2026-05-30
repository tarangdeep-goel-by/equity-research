"""Backfill the US universe (S&P 500 + Nasdaq 100) into the us_* tables.

For each ticker, runs ``refresh_us`` — which registers the symbol (with its
granular yfinance industry), pulls EDGAR fundamentals + yfinance prices/valuation/
estimates, and builds the us_company_snapshot. Writes ONLY to us_* tables +
symbol_registry (all-new / additive — zero India risk).

Resumable: skips any symbol that already has a us_company_snapshot row. Best-effort:
a failing symbol is logged and skipped (refresh_us is per-source non-fatal anyway).

Run (long; use tmux):
    uv run python scripts/backfill_us_universe.py
"""
from __future__ import annotations

import csv
import sys
import time
from io import StringIO

import httpx

from flowtracker.store import FlowStore
from flowtracker.research.us_refresh import refresh_us

# Clean, maintained constituent CSVs (Symbol column). No HTML parsing.
_SP500_CSV = ("https://raw.githubusercontent.com/datasets/"
              "s-and-p-500-companies/main/data/constituents.csv")
_NDX_CSV = ("https://raw.githubusercontent.com/rreichel3/"
            "US-Stock-Symbols/main/nasdaq/nasdaq_100_tickers.txt")


def _csv_symbols(url: str, column: str | None) -> list[str]:
    """Fetch a CSV (with header + ``column``) or a newline list (column=None)."""
    out: list[str] = []
    try:
        text = httpx.get(url, follow_redirects=True, timeout=30).text
        if column is None:
            out = [ln.strip().upper().replace(".", "-")
                   for ln in text.splitlines() if ln.strip()]
        else:
            for row in csv.DictReader(StringIO(text)):
                s = (row.get(column) or "").strip().upper().replace(".", "-")
                if s:
                    out.append(s)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] {url}: {e}", flush=True)
    return out


def _valid_ticker(s: str) -> bool:
    return bool(s) and len(s) <= 6 and all(c.isalnum() or c == "-" for c in s)


def get_universe() -> list[str]:
    syms: set[str] = set()
    sp = _csv_symbols(_SP500_CSV, "Symbol")
    print(f"  S&P 500: {len(sp)} tickers", flush=True)
    syms.update(s for s in sp if _valid_ticker(s))
    return sorted(syms)


def main() -> int:
    print("Fetching US universe…", flush=True)
    universe = get_universe()
    print(f"Universe: {len(universe)} unique tickers\n", flush=True)
    if not universe:
        print("No tickers resolved — aborting.", flush=True)
        return 1

    done = skipped = failed = 0
    with FlowStore() as store:
        for i, sym in enumerate(universe, 1):
            existing = (store.get_us_company_snapshot(sym, "NASDAQ")
                        or store.get_us_company_snapshot(sym, "NYSE"))
            if existing:
                skipped += 1
                continue
            try:
                summary = refresh_us(sym, store=store)
                got = {k: v for k, v in summary.items() if v}
                done += 1
                print(f"[{i}/{len(universe)}] {sym}: {got}", flush=True)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"[{i}/{len(universe)}] {sym}: FAILED {e}", flush=True)
            time.sleep(0.4)  # polite to EDGAR/yfinance

    print(f"\nDONE — built={done} skipped(existing)={skipped} failed={failed}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
