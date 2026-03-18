"""Fetch live US stock prices via yfinance and enrich holdings with current valuation."""

import json
from pathlib import Path

import yfinance as yf

HOLDINGS_FILE = Path(__file__).parent / "us_holdings.json"


YFINANCE_SYMBOL_MAP = {
    "BRK.B": "BRK-B",
}


def fetch_prices(symbols: list[str]) -> dict[str, dict]:
    """Fetch last price, day change, and currency for a list of US tickers."""
    yf_symbols = [YFINANCE_SYMBOL_MAP.get(s, s) for s in symbols]
    tickers = yf.Tickers(" ".join(yf_symbols))
    prices = {}
    for sym, yf_sym in zip(symbols, yf_symbols):
        try:
            info = tickers.tickers[yf_sym].fast_info
            prices[sym] = {
                "last_price": round(info.last_price, 2),
                "currency": info.currency,
            }
        except Exception as e:
            prices[sym] = {"last_price": None, "error": str(e)}
    return prices


def main():
    if not HOLDINGS_FILE.exists():
        print(f"Holdings file not found: {HOLDINGS_FILE}")
        print("Run parse_us_trades.py first.")
        return

    data = json.loads(HOLDINGS_FILE.read_text())
    holdings = data["holdings"]
    symbols = [h["symbol"] for h in holdings]

    print("Fetching live prices...")
    prices = fetch_prices(symbols)

    total_invested = 0.0
    total_current = 0.0

    print(f"\n{'Symbol':<8} {'Qty':>10} {'Avg ($)':>10} {'LTP ($)':>10} {'Value ($)':>12} {'P&L ($)':>10} {'P&L %':>8}")
    print("-" * 72)

    for h in holdings:
        sym = h["symbol"]
        qty = h["quantity"]
        cost = h["total_cost_usd"]
        avg = h["avg_price_usd"]
        total_invested += cost

        p = prices.get(sym, {})
        ltp = p.get("last_price")

        if ltp:
            value = round(qty * ltp, 2)
            pnl = round(value - cost, 2)
            pnl_pct = round((pnl / cost) * 100, 2) if cost > 0 else 0
            total_current += value
            print(f"{sym:<8} {qty:>10.4f} {avg:>10.2f} {ltp:>10.2f} {value:>12.2f} {pnl:>+10.2f} {pnl_pct:>+7.1f}%")
        else:
            print(f"{sym:<8} {qty:>10.4f} {avg:>10.2f} {'N/A':>10} {'N/A':>12} {'N/A':>10} {'N/A':>8}")

    total_pnl = round(total_current - total_invested, 2)
    total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0
    print("-" * 72)
    print(f"{'TOTAL':<8} {'':>10} {'':>10} {'':>10} {total_current:>12.2f} {total_pnl:>+10.2f} {total_pnl_pct:>+7.1f}%")
    print(f"\nInvested: ${total_invested:,.2f}  |  Current: ${total_current:,.2f}  |  P&L: ${total_pnl:+,.2f} ({total_pnl_pct:+.1f}%)")


if __name__ == "__main__":
    main()
