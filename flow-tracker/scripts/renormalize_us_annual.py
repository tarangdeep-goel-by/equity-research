"""Re-normalize us_annual_financials for every registered US symbol.

One-shot cleanup: re-fetches EDGAR companyfacts and re-runs ``normalize_annual``
(idempotent upsert) for each US symbol_registry row. Use after a bug fix in the
EDGAR normalizer to correct already-backfilled rows that the resumable universe
backfill skips (it keys on snapshot existence, so it won't re-fetch financials).

Specifically fixes the ~363 symbols backfilled before the num_shares duration fix.
Only touches us_annual_financials — prices/valuation/snapshot are untouched.

Parallel (thread-local FlowStore per worker; EDGAR throttle is fine at this count).
Run (use tmux):
    uv run python scripts/renormalize_us_annual.py [--workers N]
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flowtracker.edgar_client import EdgarClient

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
        if not cik:
            with _lock:
                _n["skip"] += 1
                _n["i"] += 1
            return
        with EdgarClient() as ec:
            facts = ec.fetch_company_facts(cik)
            annual = ec.normalize_annual(facts, symbol, market=market)
        if annual:
            store.upsert_us_annual_financials(annual)
            with _lock:
                _n["done"] += 1
                _n["i"] += 1
                i = _n["i"]
            print(f"[{i}/{total}] {symbol}: {len(annual)} annual rows re-normalized", flush=True)
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
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from flowtracker.store import FlowStore

    with FlowStore() as s:
        rows = [r for m in ("NASDAQ", "NYSE")
                for r in s.get_symbol_registry(market=m)]
    targets = [(r["symbol"], r["market"], r.get("cik")) for r in rows]
    total = len(targets)
    print(f"Re-normalizing annual financials for {total} US symbols | workers={args.workers}\n",
          flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, sym, mkt, cik, total) for sym, mkt, cik in targets]
        for _ in as_completed(futs):
            pass

    print(f"\nDONE in {(time.time()-t0)/60:.1f} min — done={_n['done']} "
          f"skip(no-cik/empty)={_n['skip']} fail={_n['fail']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
