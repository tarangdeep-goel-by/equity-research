"""Parse IndMoney US Stocks trade report XLS and output net holdings as JSON."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_XLS = Path.home() / "Downloads" / "US Stocks Trade Report Jan 1 2019 to Feb 9 2026.xls"
OUTPUT_FILE = Path(__file__).parent / "us_holdings.json"


def parse_trades(xls_path: Path) -> list[dict]:
    df = pd.read_excel(xls_path, header=10)
    df = df.dropna(subset=["Stock Symbol"])

    holdings: dict[str, dict] = {}

    for _, row in df.iterrows():
        sym = str(row["Stock Symbol"]).strip()
        name = str(row["Stock Name"]).strip()
        qty = float(row["Quantity"])
        price = float(row["Price ($)"])
        amount = float(row["Order Amount ($)"])
        txn = row["Transaction Type"]
        date = str(row["Order Execution Time"]).strip()

        if sym not in holdings:
            holdings[sym] = {"symbol": sym, "name": name, "quantity": 0.0, "total_cost": 0.0, "trades": []}

        trade = {"type": txn, "quantity": qty, "price": price, "amount": amount, "date": date}
        holdings[sym]["trades"].append(trade)

        if txn == "BUY":
            holdings[sym]["quantity"] += qty
            holdings[sym]["total_cost"] += amount
        elif txn == "SELL":
            # Reduce cost basis proportionally
            if holdings[sym]["quantity"] > 0:
                cost_per_share = holdings[sym]["total_cost"] / holdings[sym]["quantity"]
                holdings[sym]["quantity"] -= qty
                holdings[sym]["total_cost"] = max(0, holdings[sym]["quantity"] * cost_per_share)

    # Filter to active holdings and round
    active = []
    for h in holdings.values():
        if h["quantity"] > 0.001:
            avg_price = h["total_cost"] / h["quantity"] if h["quantity"] > 0 else 0
            active.append({
                "symbol": h["symbol"],
                "name": h["name"],
                "quantity": round(h["quantity"], 6),
                "total_cost_usd": round(h["total_cost"], 2),
                "avg_price_usd": round(avg_price, 2),
                "trades": h["trades"],
            })

    return sorted(active, key=lambda x: x["total_cost_usd"], reverse=True)


def main():
    xls_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLS

    if not xls_path.exists():
        print(f"File not found: {xls_path}")
        sys.exit(1)

    holdings = parse_trades(xls_path)

    output = {
        "source": "indmoney",
        "broker": "Alpaca",
        "currency": "USD",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(xls_path),
        "total_invested_usd": round(sum(h["total_cost_usd"] for h in holdings), 2),
        "holdings_count": len(holdings),
        "holdings": holdings,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    print(f"Wrote {len(holdings)} holdings to {OUTPUT_FILE}")
    for h in holdings:
        print(f"  {h['symbol']:<8} qty={h['quantity']:<12} cost=${h['total_cost_usd']:<10} avg=${h['avg_price_usd']}")


if __name__ == "__main__":
    main()
