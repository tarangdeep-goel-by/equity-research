#!/usr/bin/env python3
"""Bulk backfill fundamentals data for all scanner symbols using yfinance.

Fetches:
  - Quarterly income statements
  - Current valuation snapshot
  - Annual financials (P&L + Balance Sheet + Cash Flow)

Usage:
    source .venv/bin/activate
    python scripts/backfill_fundamentals.py              # all 500 symbols
    python scripts/backfill_fundamentals.py --test 3     # test with 3 symbols
    python scripts/backfill_fundamentals.py --resume     # skip symbols already in DB
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date

import yfinance as yf

# Add project root to path
sys.path.insert(0, ".")

from flowtracker.fund_client import FundClient, YFinanceError, nse_symbol, _safe_get
from flowtracker.fund_models import AnnualFinancials, QuarterlyResult, ValuationSnapshot
from flowtracker.store import FlowStore


def fetch_annual_financials(symbol: str, ticker: yf.Ticker) -> list[AnnualFinancials]:
    """Fetch annual financials from yfinance (P&L + Balance Sheet + Cash Flow)."""
    inc = ticker.get_income_stmt()
    bs = ticker.get_balance_sheet()
    cf = ticker.get_cash_flow()

    if inc is None or inc.empty:
        return []

    results = []
    for col in inc.columns:
        fy_end = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)

        # P&L
        revenue = _safe_get(inc, "TotalRevenue", col)
        operating_income = _safe_get(inc, "OperatingIncome", col)
        other_income = _safe_get(inc, "InterestIncomeNonOperating", col)
        depreciation = _safe_get(inc, "ReconciledDepreciation", col)
        interest = _safe_get(inc, "InterestExpenseNonOperating", col) or _safe_get(inc, "InterestExpense", col)
        profit_before_tax = _safe_get(inc, "PretaxIncome", col)
        tax = _safe_get(inc, "TaxProvision", col)
        net_income = _safe_get(inc, "NetIncome", col)
        eps = _safe_get(inc, "BasicEPS", col)
        ebitda = _safe_get(inc, "EBITDA", col)

        # Employee cost — yfinance doesn't split this out directly
        employee_cost = None

        # Balance Sheet (if available for this date)
        equity_capital = None
        reserves = None
        borrowings = None
        other_liabilities = None
        total_assets = None
        net_block = None
        cwip = None
        investments = None
        other_assets = None
        receivables = None
        inventory = None
        cash_and_bank = None
        num_shares = None
        dividend_amount = None

        if bs is not None and not bs.empty and col in bs.columns:
            equity_capital = _safe_get(bs, "CommonStock", col) or _safe_get(bs, "CapitalStock", col)
            reserves = _safe_get(bs, "RetainedEarnings", col)
            borrowings = _safe_get(bs, "TotalDebt", col)
            other_liabilities = _safe_get(bs, "OtherCurrentLiabilities", col)
            total_assets = _safe_get(bs, "TotalAssets", col)
            net_block = _safe_get(bs, "NetPPE", col)
            cwip = _safe_get(bs, "ConstructionInProgress", col)
            investments = _safe_get(bs, "InvestmentinFinancialAssets", col)
            receivables = _safe_get(bs, "AccountsReceivable", col)
            inventory = _safe_get(bs, "Inventory", col)
            cash_and_bank = _safe_get(bs, "CashAndCashEquivalents", col)
            num_shares_val = _safe_get(bs, "OrdinarySharesNumber", col) or _safe_get(bs, "ShareIssued", col)
            num_shares = num_shares_val

        # Cash Flow (if available for this date)
        cfo = None
        cfi = None
        cff = None
        net_cash_flow = None

        if cf is not None and not cf.empty and col in cf.columns:
            cfo = _safe_get(cf, "OperatingCashFlow", col)
            cfi = _safe_get(cf, "InvestingCashFlow", col)
            cff = _safe_get(cf, "FinancingCashFlow", col)
            net_cash_flow = _safe_get(cf, "ChangesInCash", col)

        # Dividend from cash flow
        if cf is not None and not cf.empty and col in cf.columns:
            dividend_amount = _safe_get(cf, "CashDividendsPaid", col)
            if dividend_amount is not None:
                dividend_amount = abs(dividend_amount)  # dividends paid are negative

        results.append(AnnualFinancials(
            symbol=symbol,
            fiscal_year_end=fy_end,
            revenue=revenue,
            employee_cost=employee_cost,
            other_income=other_income,
            depreciation=depreciation,
            interest=interest,
            profit_before_tax=profit_before_tax,
            tax=tax,
            net_income=net_income,
            eps=eps,
            dividend_amount=dividend_amount,
            equity_capital=equity_capital,
            reserves=reserves,
            borrowings=borrowings,
            other_liabilities=other_liabilities,
            total_assets=total_assets,
            net_block=net_block,
            cwip=cwip,
            investments=investments,
            other_assets=other_assets,
            receivables=receivables,
            inventory=inventory,
            cash_and_bank=cash_and_bank,
            num_shares=num_shares,
            cfo=cfo,
            cfi=cfi,
            cff=cff,
            net_cash_flow=net_cash_flow,
        ))

    return results


def get_symbols_with_data(store: FlowStore) -> set[str]:
    """Get symbols that already have all three types of data."""
    q_syms = {r["symbol"] for r in store._conn.execute(
        "SELECT DISTINCT symbol FROM quarterly_results"
    ).fetchall()}
    v_syms = {r["symbol"] for r in store._conn.execute(
        "SELECT DISTINCT symbol FROM valuation_snapshot WHERE date = ?",
        (date.today().isoformat(),),
    ).fetchall()}
    a_syms = {r["symbol"] for r in store._conn.execute(
        "SELECT DISTINCT symbol FROM annual_financials"
    ).fetchall()}
    return q_syms & v_syms & a_syms


def main():
    parser = argparse.ArgumentParser(description="Backfill fundamentals from yfinance")
    parser.add_argument("--test", type=int, default=0, help="Test with N symbols first")
    parser.add_argument("--resume", action="store_true", help="Skip symbols already in DB")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between stocks (seconds)")
    parser.add_argument("--valuation-only", action="store_true", help="Only fetch valuation snapshots")
    parser.add_argument("--quarters-only", action="store_true", help="Only fetch quarterly results")
    parser.add_argument("--annual-only", action="store_true", help="Only fetch annual financials")
    args = parser.parse_args()

    # Determine what to fetch
    fetch_all = not (args.valuation_only or args.quarters_only or args.annual_only)
    do_quarters = fetch_all or args.quarters_only
    do_valuation = fetch_all or args.valuation_only
    do_annual = fetch_all or args.annual_only

    with FlowStore() as store:
        all_symbols = store.get_all_scanner_symbols()

    if not all_symbols:
        print("ERROR: No scanner symbols found. Run 'flowtrack scan fetch' first.")
        sys.exit(1)

    # Resume mode: skip symbols with existing data
    if args.resume:
        with FlowStore() as store:
            existing = get_symbols_with_data(store)
        before = len(all_symbols)
        all_symbols = [s for s in all_symbols if s not in existing]
        print(f"Resume mode: skipping {before - len(all_symbols)} symbols with existing data")

    if args.test > 0:
        all_symbols = all_symbols[:args.test]

    total = len(all_symbols)
    print(f"\nBackfill fundamentals for {total} symbols")
    print(f"  Quarterly results: {'YES' if do_quarters else 'no'}")
    print(f"  Valuation snapshot: {'YES' if do_valuation else 'no'}")
    print(f"  Annual financials: {'YES' if do_annual else 'no'}")
    print(f"  Delay: {args.delay}s between stocks")
    print()

    client = FundClient()
    stats = {
        "quarters": 0,
        "valuations": 0,
        "annual": 0,
        "errors": [],
        "skipped": 0,
    }

    for i, sym in enumerate(all_symbols, 1):
        pct = (i / total) * 100
        print(f"[{i:3d}/{total}] ({pct:5.1f}%) {sym:20s} ", end="", flush=True)

        try:
            ticker = yf.Ticker(nse_symbol(sym))
            parts = []

            # 1. Quarterly results
            if do_quarters:
                try:
                    results = client.fetch_quarterly_results(sym)
                    if results:
                        with FlowStore() as store:
                            store.upsert_quarterly_results(results)
                        stats["quarters"] += len(results)
                        parts.append(f"Q:{len(results)}")
                    else:
                        parts.append("Q:0")
                except Exception as e:
                    parts.append(f"Q:ERR")
                    stats["errors"].append(f"{sym} quarterly: {e}")

            # 2. Valuation snapshot
            if do_valuation:
                try:
                    snap = client.fetch_valuation_snapshot(sym)
                    if snap.price is not None:
                        with FlowStore() as store:
                            store.upsert_valuation_snapshot(snap)
                        stats["valuations"] += 1
                        parts.append("V:ok")
                    else:
                        parts.append("V:no-price")
                except Exception as e:
                    parts.append("V:ERR")
                    stats["errors"].append(f"{sym} valuation: {e}")

            # 3. Annual financials
            if do_annual:
                try:
                    annual = fetch_annual_financials(sym, ticker)
                    if annual:
                        with FlowStore() as store:
                            store.upsert_annual_financials(annual)
                        stats["annual"] += len(annual)
                        parts.append(f"A:{len(annual)}")
                    else:
                        parts.append("A:0")
                except Exception as e:
                    parts.append("A:ERR")
                    stats["errors"].append(f"{sym} annual: {e}")

            print("  ".join(parts))

        except Exception as e:
            print(f"SKIP ({e})")
            stats["errors"].append(f"{sym}: {e}")
            stats["skipped"] += 1

        # Rate limit
        if i < total:
            time.sleep(args.delay)

    # Summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"  Quarterly results:  {stats['quarters']:6d} records")
    print(f"  Valuation snapshots:{stats['valuations']:6d} records")
    print(f"  Annual financials:  {stats['annual']:6d} records")
    print(f"  Skipped:            {stats['skipped']:6d}")
    print(f"  Errors:             {len(stats['errors']):6d}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for e in stats["errors"][:20]:
            print(f"  - {e}")
        if len(stats["errors"]) > 20:
            print(f"  ... and {len(stats['errors']) - 20} more")


if __name__ == "__main__":
    main()
