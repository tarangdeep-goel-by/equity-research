"""Backfill ~10yr of daily US prices for the analog cohort (S&P 500 subset).

The US historical-analog cohort (#17) needs multi-year daily prices to compute
PE-percentile + momentum (SMA200/RSI) at each past quarter-end. The bulk universe
backfill only pulled ~1yr of ``us_daily_prices``; this deepens the S&P 500 subset
to ~10yr via yfinance ``period="10y"``.

Parallel thread pool (yfinance is the throttle; keep workers modest). Resumable:
skips any symbol whose stored history already reaches back to the cutoff year.
Writes ONLY us_daily_prices (additive). Run (long; use tmux):

    uv run python scripts/backfill_us_prices_history.py [--workers N] [--period 10y] [--limit N]
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

from flowtracker.market import Market
from flowtracker.us_ingest import fetch_us_daily_prices

_UA = {"User-Agent": "flowtracker-research tarangdeepgoel2000@gmail.com"}
_SP500_CSV = ("https://raw.githubusercontent.com/datasets/"
              "s-and-p-500-companies/main/data/constituents.csv")

_local = threading.local()
_lock = threading.Lock()
_n = {"done": 0, "skip": 0, "fail": 0, "i": 0}


def _norm(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")


def _sp500() -> list[str]:
    text = httpx.get(_SP500_CSV, headers=_UA, follow_redirects=True, timeout=30).text
    out = {_norm(r["Symbol"]) for r in csv.DictReader(StringIO(text)) if r.get("Symbol")}
    return sorted(s for s in out if s and len(s) <= 6 and all(c.isalnum() or c == "-" for c in s))


def _store():
    st = getattr(_local, "store", None)
    if st is None:
        from flowtracker.store import FlowStore

        st = FlowStore()
        st._conn.execute("PRAGMA busy_timeout=60000")
        _local.store = st
    return st


def _market_of(store, symbol: str) -> str:
    for m in ("NASDAQ", "NYSE"):
        if store.get_symbol_registry_entry(symbol, m):
            return m
    return "NASDAQ"


def _one(symbol: str, period: str, cutoff_year: int, total: int) -> None:
    store = _store()
    try:
        market = _market_of(store, symbol)
        row = store._conn.execute(
            "SELECT MIN(date) AS d FROM us_daily_prices WHERE symbol = ? AND market = ?",
            (symbol, market),
        ).fetchone()
        have_min = row["d"] if row else None
        if have_min and have_min[:4].isdigit() and int(have_min[:4]) <= cutoff_year:
            with _lock:
                _n["skip"] += 1
                _n["i"] += 1
            return
        rows = fetch_us_daily_prices(symbol, market=Market(market), period=period)
        if rows:
            store.upsert_us_daily_prices(rows)
            with _lock:
                _n["done"] += 1
                _n["i"] += 1
                i = _n["i"]
            print(f"[{i}/{total}] {symbol} ({market}): {len(rows)} bars "
                  f"(min {rows[0]['date'] if rows else '?'})", flush=True)
        else:
            with _lock:
                _n["fail"] += 1
                _n["i"] += 1
            print(f"[{_n['i']}/{total}] {symbol}: no data", flush=True)
    except Exception as e:  # noqa: BLE001
        with _lock:
            _n["fail"] += 1
            _n["i"] += 1
            i = _n["i"]
        print(f"[{i}/{total}] {symbol}: FAILED {e}", flush=True)
    time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--period", default="10y")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cutoff-year", type=int, default=2017,
                    help="resume skip: symbols with history reaching <= this year are skipped")
    args = ap.parse_args()

    symbols = _sp500()
    if args.limit:
        symbols = symbols[: args.limit]
    total = len(symbols)
    print(f"Deepening US prices to {args.period} for {total} S&P 500 symbols | "
          f"workers={args.workers} cutoff_year={args.cutoff_year}\n", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, s, args.period, args.cutoff_year, total) for s in symbols]
        for _ in as_completed(futs):
            pass

    print(f"\nDONE in {(time.time()-t0)/60:.1f} min — done={_n['done']} "
          f"skip(deep enough)={_n['skip']} fail={_n['fail']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
