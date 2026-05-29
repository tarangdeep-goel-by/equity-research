"""WS-7 live smoke — refresh_us(AAPL) against real EDGAR/yfinance, then compute.

Uses a DEDICATED DB (never the 6.4GB prod DB). Verifies the P3.5b compute layer
produces correct numbers on REAL US data: no crashes, sane USD values.

Run: uv run python scripts/ws7_live_smoke.py
"""
from __future__ import annotations

import os
import tempfile

# Dedicated DB — prod India DB untouched.
DB = os.environ.get("WS7_DB") or tempfile.mktemp(prefix="ws7_aapl_", suffix=".db")
os.environ["FLOWTRACKER_DB"] = DB

from rich.console import Console  # noqa: E402

from flowtracker.store import FlowStore  # noqa: E402
from flowtracker.research.us_refresh import refresh_us  # noqa: E402
from flowtracker.research.data_api import ResearchDataAPI  # noqa: E402

console = Console()
SYMBOL = "AAPL"


def main() -> None:
    console.print(f"[bold]WS-7 live smoke — {SYMBOL}[/]  (DB={DB})\n")

    # --- 1. Live refresh into the dedicated DB (skip if already populated) ---
    with FlowStore(db_path=DB) as store:
        already = store.get_us_annual_financials(SYMBOL, "NASDAQ")
        if already:
            console.print(f"[dim]reusing cached refresh: {len(already)} annual rows[/]\n")
            summary = {"cached": len(already)}
        else:
            summary = refresh_us(SYMBOL, store=store, console=console)
    console.print(f"\n[bold]refresh_us summary:[/] {summary}\n")

    # Auto-resolve market via symbol_registry (refresh_us registered AAPL=NASDAQ).
    api = ResearchDataAPI()
    console.print(f"[dim]resolved market for {SYMBOL}: {api._market_of(SYMBOL)} "
                  f"is_us={api._is_us(SYMBOL)}[/]")

    def show(label: str, fn):
        try:
            val = fn()
            console.print(f"[green]OK[/] {label}: {val}")
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]CRASH[/] {label}: {type(e).__name__}: {e}")

    # --- 2. Annual financials (enriched columns populated?) ---
    annuals = api.get_annual_financials(SYMBOL, years=10)
    console.print(f"[bold]annual_financials:[/] {len(annuals)} years")
    if annuals:
        a = annuals[0]
        keys = ["fiscal_year_end", "revenue", "net_income", "operating_profit",
                "interest", "tax", "rnd_expense", "stock_based_comp", "sga",
                "net_block", "num_shares", "cfo", "cfi", "cff",
                "equity_capital", "reserves"]
        console.print("  latest: " + ", ".join(
            f"{k}={a.get(k)}" for k in keys))

    # --- 3. Compute smoke ---
    show("piotroski_score", lambda: f"score={api.get_piotroski_score(SYMBOL).get('score')} "
                                    f"err={api.get_piotroski_score(SYMBOL).get('error')}")

    def _fv():
        fv = api.get_fair_value(SYMBOL)
        r = fv.get("fair_value_range") or {}
        return f"signal={fv.get('signal')} mos%={fv.get('margin_of_safety_pct')} " \
               f"fair={fv.get('combined_fair_value')} range={r.get('bear')}/{r.get('base')}/{r.get('bull')}"
    show("fair_value", _fv)

    def _wacc():
        w = api.get_wacc_params(SYMBOL)
        ke = w.get("ke")
        ce = w.get("cost_of_equity") or {}
        return f"WACC={round((w.get('wacc') or 0)*100,2)}% Ke={round((ke or 0)*100,2)}% " \
               f"rf={ce.get('rf')} beta={ce.get('beta')} flags={w.get('reliability_flags')}"
    show("wacc_params", _wacc)

    def _dupont():
        d = api.get_dupont_decomposition(SYMBOL)
        years = d.get("years") or []
        latest = years[0] if years else {}
        return f"src={d.get('data_source')} years={len(years)} latest_roe={latest.get('roe_dupont')}"
    show("dupont_decomposition", _dupont)

    show("rnd_intensity", lambda: f"latest%={api.get_rnd_intensity(SYMBOL).get('latest_rnd_intensity_pct')} "
                                  f"trend={api.get_rnd_intensity(SYMBOL).get('trend')}")
    show("sbc_dilution", lambda: f"latest_sbc%rev={api.get_sbc_dilution(SYMBOL).get('latest_sbc_pct_revenue')} "
                                 f"share_cagr%={api.get_sbc_dilution(SYMBOL).get('share_count_cagr_pct')}")
    show("technical_indicators", lambda: f"rows={len(api.get_technical_indicators(SYMBOL))}")
    show("price_performance", lambda: f"keys={list((api.get_price_performance(SYMBOL) or {}).keys())[:6]}")

    api.close()
    console.print("\n[bold green]WS-7 live smoke complete.[/]")


if __name__ == "__main__":
    main()
