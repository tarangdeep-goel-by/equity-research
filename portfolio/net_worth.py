"""Consolidated net worth tracker across all accounts.

Sources:
  - groww_holdings.json    (Indian stocks + ETFs — refresh via Groww MCP)
  - us_holdings.json       (US stocks — refresh via parse_us_trades.py)
  - mutual_funds.json      (Mutual funds — refresh via parse_mutual_funds.py)
  - manual_assets.json     (FDs, PPF, ULIP — update manually)

Usage:
  python3 net_worth.py              # print summary
  python3 net_worth.py --json       # write net_worth_snapshot.json
  python3 net_worth.py --detail     # print detailed breakdown
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).parent
USDINR_FALLBACK = 90.72

YFINANCE_SYMBOL_MAP = {"BRK.B": "BRK-B"}


def load_json(filename: str) -> dict:
    path = DIR / filename
    if not path.exists():
        print(f"  [SKIP] {filename} not found")
        return {}
    return json.loads(path.read_text())


def get_usdinr() -> float:
    try:
        import yfinance as yf
        return round(yf.Ticker("USDINR=X").fast_info.last_price, 2)
    except Exception:
        return USDINR_FALLBACK


def get_us_live_prices(symbols: list[str]) -> dict[str, float]:
    try:
        import yfinance as yf
        yf_symbols = [YFINANCE_SYMBOL_MAP.get(s, s) for s in symbols]
        tickers = yf.Tickers(" ".join(yf_symbols))
        prices = {}
        for sym, yf_sym in zip(symbols, yf_symbols):
            try:
                prices[sym] = round(tickers.tickers[yf_sym].fast_info.last_price, 2)
            except Exception:
                prices[sym] = None
        return prices
    except Exception:
        return {}


def build_portfolio() -> dict:
    usdinr = get_usdinr()
    buckets = {
        "Indian Equity - Index ETFs": [],
        "Indian Equity - Stocks": [],
        "Indian Equity - MF": [],
        "US Equity": [],
        "Gold": [],
        "Silver": [],
        "Debt": [],
        "Liquid": [],
        "Insurance": [],
    }

    # --- Groww holdings ---
    groww = load_json("groww_holdings.json")
    for h in groww.get("holdings", []):
        val = h["current_value"]
        entry = {"name": h["symbol"], "source": "groww", "value_inr": val}

        if h["type"] == "stock":
            buckets["Indian Equity - Stocks"].append(entry)
        elif h["type"] == "etf":
            st = h.get("sub_type", "")
            if st == "gold":
                buckets["Gold"].append(entry)
            elif st == "silver":
                buckets["Silver"].append(entry)
            elif st == "liquid":
                buckets["Liquid"].append(entry)
            elif st == "debt":
                buckets["Debt"].append(entry)
            elif st == "index":
                buckets["Indian Equity - Index ETFs"].append(entry)

    # --- US holdings ---
    us = load_json("us_holdings.json")
    us_holdings = us.get("holdings", [])
    if us_holdings:
        symbols = [h["symbol"] for h in us_holdings]
        print("Fetching US live prices...")
        prices = get_us_live_prices(symbols)
        for h in us_holdings:
            ltp = prices.get(h["symbol"])
            val_usd = round(h["quantity"] * ltp, 2) if ltp else h["total_cost_usd"]
            val_inr = round(val_usd * usdinr)
            buckets["US Equity"].append({
                "name": h["symbol"],
                "source": "indmoney",
                "value_usd": val_usd,
                "value_inr": val_inr,
                "ltp_usd": ltp,
            })

    # --- Mutual Funds ---
    mf = load_json("mutual_funds.json")
    for h in mf.get("holdings", []):
        cat = h.get("sub_category", "")
        entry = {"name": h["scheme_name"][:50], "source": "groww", "value_inr": h["current_value"], "sub_category": cat}
        if cat == "Gold":
            buckets["Gold"].append(entry)
        else:
            buckets["Indian Equity - MF"].append(entry)

    # --- Manual assets ---
    manual = load_json("manual_assets.json")
    for a in manual.get("assets", []):
        entry = {"name": a["name"], "source": "manual", "value_inr": a["value"]}
        if a["category"] == "Debt":
            buckets["Debt"].append(entry)
        elif a["category"] == "Insurance":
            buckets["Insurance"].append(entry)
        else:
            buckets["Liquid"].append(entry)

    # --- Aggregate ---
    summary = {}
    total = 0
    for bucket, items in buckets.items():
        bucket_total = sum(i["value_inr"] for i in items)
        summary[bucket] = {"value_inr": round(bucket_total), "count": len(items), "items": items}
        total += bucket_total

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usdinr": usdinr,
        "total_net_worth_inr": round(total),
        "buckets": summary,
    }


def print_summary(portfolio: dict):
    total = portfolio["total_net_worth_inr"]
    usdinr = portfolio["usdinr"]

    print(f"\n{'=' * 65}")
    print(f"  CONSOLIDATED NET WORTH — ₹{total:,.0f} (${total / usdinr:,.0f})")
    print(f"  USD/INR: {usdinr} | As of: {portfolio['generated_at'][:19]}")
    print(f"{'=' * 65}\n")

    print(f"  {'Asset Class':<30} {'Value (₹)':>12} {'%':>7}  {'#':>3}")
    print(f"  {'-' * 55}")

    equity_total = 0
    for bucket, data in portfolio["buckets"].items():
        val = data["value_inr"]
        pct = (val / total * 100) if total > 0 else 0
        if "Equity" in bucket:
            equity_total += val
        print(f"  {bucket:<30} {val:>12,.0f} {pct:>6.1f}%  {data['count']:>3}")

    print(f"  {'-' * 55}")
    print(f"  {'TOTAL':<30} {total:>12,.0f} {'100.0%':>7}")
    print()

    # Macro allocation
    debt_total = portfolio["buckets"]["Debt"]["value_inr"] + portfolio["buckets"]["Liquid"]["value_inr"]
    gold_total = portfolio["buckets"]["Gold"]["value_inr"]
    silver_total = portfolio["buckets"]["Silver"]["value_inr"]
    insurance_total = portfolio["buckets"]["Insurance"]["value_inr"]

    print(f"  {'MACRO ALLOCATION':^55}")
    print(f"  {'-' * 55}")
    print(f"  {'Equity':<20} ₹{equity_total:>10,.0f}  ({equity_total / total * 100:.1f}%)")
    print(f"  {'Debt + Liquid':<20} ₹{debt_total:>10,.0f}  ({debt_total / total * 100:.1f}%)")
    print(f"  {'Gold':<20} ₹{gold_total:>10,.0f}  ({gold_total / total * 100:.1f}%)")
    print(f"  {'Silver':<20} ₹{silver_total:>10,.0f}  ({silver_total / total * 100:.1f}%)")
    print(f"  {'Insurance (ULIP)':<20} ₹{insurance_total:>10,.0f}  ({insurance_total / total * 100:.1f}%)")
    print(f"  {'-' * 55}")
    print(f"  {'Total':<20} ₹{total:>10,.0f}\n")


def print_detail(portfolio: dict):
    print_summary(portfolio)
    total = portfolio["total_net_worth_inr"]
    for bucket, data in portfolio["buckets"].items():
        if data["count"] == 0:
            continue
        print(f"\n  [{bucket}] — ₹{data['value_inr']:,.0f} ({data['value_inr'] / total * 100:.1f}%)")
        for item in sorted(data["items"], key=lambda x: x["value_inr"], reverse=True):
            usd_str = f" (${item['value_usd']:,.0f})" if "value_usd" in item else ""
            print(f"    {item['name']:<50} ₹{item['value_inr']:>10,.0f}{usd_str}")


def main():
    parser = argparse.ArgumentParser(description="Consolidated net worth tracker")
    parser.add_argument("--json", action="store_true", help="Write snapshot to JSON")
    parser.add_argument("--detail", action="store_true", help="Print detailed breakdown")
    args = parser.parse_args()

    portfolio = build_portfolio()

    if args.detail:
        print_detail(portfolio)
    else:
        print_summary(portfolio)

    if args.json:
        out = DIR / "net_worth_snapshot.json"
        out.write_text(json.dumps(portfolio, indent=2, default=str))
        print(f"  Snapshot saved to {out}")


if __name__ == "__main__":
    main()
