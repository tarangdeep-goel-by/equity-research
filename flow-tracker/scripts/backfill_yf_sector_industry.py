#!/usr/bin/env python3
"""Universe yfinance SECTOR + INDUSTRY backfill into company_snapshot.

The classification layer reads company_snapshot.sector/industry, but prior
universe backfills only filled Screener financials — sector was populated for
~63 symbols. This fills the coarse yfinance GICS-like sector + industry for the
full liquid NSE universe so the sector resolver has a label to work with.

- Universe: distinct symbols traded in the last 60 days (liquid/active).
- Surgical upsert: writes ONLY sector + industry (never wipes other columns).
- Resume-safe: skips symbols that already have a non-null sector.
- yfinance only (no Screener) → does NOT contend with a running autoeval.

Run:  uv run python scripts/backfill_yf_sector_industry.py
      uv run python scripts/backfill_yf_sector_industry.py --test 5
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flowtracker.store import FlowStore

PROG = Path("/tmp/yf_sector_backfill.log")


def universe(store, days: int) -> list[str]:
    rows = store._conn.execute(
        "SELECT DISTINCT symbol FROM daily_stock_data "
        "WHERE date >= DATE('now','-' || ? || ' day') ORDER BY symbol", (days,)
    ).fetchall()
    have = {r[0] for r in store._conn.execute(
        "SELECT symbol FROM company_snapshot WHERE sector IS NOT NULL").fetchall()}
    return [r[0] for r in rows if r[0] not in have]


def upsert(store, sym: str, sector: str | None, industry: str | None) -> None:
    store._conn.execute(
        "INSERT INTO company_snapshot (symbol, sector, industry, updated_at) "
        "VALUES (?,?,?,datetime('now')) "
        "ON CONFLICT(symbol) DO UPDATE SET "
        "sector=COALESCE(excluded.sector, company_snapshot.sector), "
        "industry=COALESCE(excluded.industry, company_snapshot.industry), "
        "updated_at=datetime('now')",
        (sym, sector, industry),
    )
    store._conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", type=int, default=0)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--sleep", type=float, default=0.4)
    a = ap.parse_args()
    import yfinance as yf

    with FlowStore() as store:
        syms = universe(store, a.days)
        if a.test:
            syms = syms[: a.test]
        total = len(syms)
        print(f"yfinance sector/industry backfill: {total} symbols missing a sector")
        ok = err = 0
        for i, sym in enumerate(syms, 1):
            try:
                info = yf.Ticker(f"{sym}.NS").info or {}
                sec, ind = info.get("sector"), info.get("industry")
                if sec or ind:
                    upsert(store, sym, sec, ind); ok += 1
                else:
                    err += 1
                status = f"{sec} / {ind}" if (sec or ind) else "no-data"
            except Exception as e:  # noqa: BLE001
                err += 1; status = f"ERR {type(e).__name__}"
            with PROG.open("a") as fp:
                fp.write(f"{i}/{total} {sym} {status}\n")
            if i % 50 == 0 or i == total:
                print(f"  [{i}/{total}] ok={ok} miss/err={err}  last={sym} ({status})", flush=True)
            time.sleep(a.sleep)
        print(f"DONE: {ok} filled, {err} no-data/err, of {total}")


if __name__ == "__main__":
    main()
