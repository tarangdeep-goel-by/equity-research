"""Backfill us_insider_transactions (SEC Form 4) for the registered US universe.

The bulk universe backfill (``backfill_us_universe.py``) runs ``refresh_us`` with
``skip_insider=True`` because Form 4 pulls dozens of archive XMLs per issuer — the
slowest EDGAR source. This one-shot fills the gap: for every registered US symbol
that has NO ``us_insider_transactions`` rows yet, it fetches + parses recent Form 4
filings and upserts them. Symbols already populated (the ~1,930 done before the
speedup) are skipped, so the run is resumable — re-run to resume after an interrupt.

Only touches us_insider_transactions — prices/valuation/snapshot/financials untouched.

Parallel: thread-local FlowStore per worker; EDGAR's per-client ≤10 req/s throttle
keeps aggregate load fine at a modest worker count. Form 4 is the EDGAR-heaviest
source, so keep workers conservative (default 6).

Run (long; use tmux):
    uv run python scripts/backfill_us_insider.py [--workers N] [--limit N]
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flowtracker.edgar_ownership import EdgarOwnershipClient

_local = threading.local()
_lock = threading.Lock()
_n = {"done": 0, "skip": 0, "fail": 0, "i": 0}


def _store():
    st = getattr(_local, "store", None)
    if st is None:
        from flowtracker.store import FlowStore

        st = FlowStore()
        st._conn.execute("PRAGMA busy_timeout=60000")
        _local.store = st
    return st


def _one(symbol: str, market: str, cik: str | None, total: int) -> None:
    store = _store()
    try:
        with EdgarOwnershipClient() as oc:
            trades = oc.fetch_insider_transactions(symbol, cik=cik, market=market)
        if trades:
            store.upsert_us_insider_transactions(trades)
            with _lock:
                _n["done"] += 1
                _n["i"] += 1
                i = _n["i"]
            print(f"[{i}/{total}] {symbol}: {len(trades)} insider rows", flush=True)
        else:
            with _lock:
                _n["skip"] += 1
                _n["i"] += 1
    except Exception as e:  # noqa: BLE001
        with _lock:
            _n["fail"] += 1
            _n["i"] += 1
            i = _n["i"]
        print(f"[{i}/{total}] {symbol}: FAILED {e}", flush=True)
    time.sleep(0.3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="cap targets (smoke test)")
    args = ap.parse_args()

    from flowtracker.store import FlowStore

    with FlowStore() as s:
        rows = [r for m in ("NASDAQ", "NYSE")
                for r in s.get_symbol_registry(market=m)]
        # Resumable: skip symbols that already have any insider rows.
        done = {r[0] for r in s._conn.execute(
            "SELECT DISTINCT symbol FROM us_insider_transactions").fetchall()}

    targets = [(r["symbol"], r["market"], r.get("cik"))
               for r in rows
               if r.get("cik") and r["symbol"] not in done]
    if args.limit:
        targets = targets[: args.limit]
    total = len(targets)
    print(f"Insider backfill: {total} US symbols missing Form 4 "
          f"({len(done)} already populated) | workers={args.workers}\n", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, sym, mkt, cik, total) for sym, mkt, cik in targets]
        for _ in as_completed(futs):
            pass

    print(f"\nDONE in {(time.time()-t0)/60:.1f} min — done={_n['done']} "
          f"skip(no-data)={_n['skip']} fail={_n['fail']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
