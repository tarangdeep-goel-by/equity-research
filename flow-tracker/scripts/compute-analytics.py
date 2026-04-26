"""Pre-compute analytical snapshots for all Nifty index stocks.

Runs all 19 analytical metrics for each stock and stores results in
the analytical_snapshot table. Designed for weekly cron execution
after data refresh.

Usage:
    uv run python scripts/compute-analytics.py              # all stocks
    uv run python scripts/compute-analytics.py --symbol RELIANCE  # single stock
    uv run python scripts/compute-analytics.py --limit 10   # first 10 stocks
    uv run python scripts/compute-analytics.py --skip-perf  # skip yfinance calls
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn


def _safe_compute(fn, *args, **kwargs) -> tuple[dict | None, str | None]:
    """Call a compute function, return (result, error_string)."""
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, dict):
            if result.get("error"):
                return None, result["error"]
            if result.get("skipped"):
                return result, None  # skipped is not an error
        return result, None
    except Exception as e:
        return None, str(e)


def prefetch_index_prices() -> dict[str, dict[str, float]]:
    """Fetch Nifty 50 + sector indexes ONCE. Returns {ticker: {date: close}}."""
    import yfinance as yf

    indexes = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXPHARMA", "^CNXFMCG",
               "NIFTY_AUTO.NS", "NIFTY_REALTY.NS"]
    cache: dict[str, dict[str, float]] = {}

    print(f"Pre-fetching {len(indexes)} index price histories...")
    for idx in indexes:
        try:
            ticker = yf.Ticker(idx)
            hist = ticker.history(period="2y")
            if not hist.empty:
                cache[idx] = {str(d.date()): float(row["Close"]) for d, row in hist.iterrows()}
                print(f"  {idx}: {len(cache[idx])} days")
        except Exception as e:
            print(f"  {idx}: FAILED ({e})")
        time.sleep(0.5)

    print(f"Index cache: {len(cache)}/{len(indexes)} fetched")
    return cache


def compute_stock(api, engine, symbol: str, index_cache: dict | None, skip_perf: bool) -> dict:
    """Compute all analytical metrics for a single stock."""
    today = date.today().isoformat()
    row: dict = {"symbol": symbol, "computed_date": today}
    errors: dict = {}

    # Industry classification
    info = api.get_company_info(symbol)
    row["industry"] = info.get("industry", "Unknown")
    row["is_bfsi"] = 1 if api._is_bfsi(symbol) else 0
    row["is_insurance"] = 1 if api._is_insurance(symbol) else 0

    # 1. Composite Score (returns Pydantic StockScore, not dict)
    try:
        cs = engine.score_stock(symbol)
        if cs:
            d = cs.model_dump()
            row["composite_score"] = d.get("composite_score")
            # factors is a list of FactorScore dicts
            if d.get("factors"):
                factor_dict = {f["factor"]: f["score"] for f in d["factors"]}
                row["composite_factors"] = json.dumps(factor_dict)

    except Exception as e:
        errors["composite_score"] = str(e)

    # 2. F-Score
    fs, err = _safe_compute(api.get_piotroski_score, symbol)
    if fs and "error" not in fs and not fs.get("skipped"):
        row["f_score"] = fs.get("score")
        row["f_score_max"] = fs.get("max_score")
        row["f_score_signal"] = fs.get("signal")
        row["f_score_criteria"] = json.dumps(fs.get("criteria", []))
    elif err:
        errors["f_score"] = err

    # 3. M-Score
    ms, err = _safe_compute(api.get_beneish_score, symbol)
    if ms:
        if ms.get("skipped"):
            row["m_score_signal"] = "skipped"
        elif ms.get("m_score") is not None:
            row["m_score"] = ms["m_score"]
            row["m_score_signal"] = ms.get("signal")
            row["m_score_variables"] = json.dumps(ms.get("variables", {}))
        elif ms.get("score") is None and ms.get("error"):
            errors["m_score"] = ms["error"]
    elif err:
        errors["m_score"] = err

    # 4. Earnings Quality
    eq, err = _safe_compute(api.get_earnings_quality, symbol)
    if eq:
        if eq.get("skipped"):
            row["eq_signal"] = "skipped"
        elif eq.get("signal"):
            row["eq_signal"] = eq["signal"]
            row["eq_cfo_pat_3y"] = eq.get("avg_3y_cfo_pat")
            row["eq_cfo_pat_5y"] = eq.get("avg_5y_cfo_pat")
            row["eq_accruals_3y"] = eq.get("avg_3y_accruals")
    elif err:
        errors["earnings_quality"] = err

    # 5. Reverse DCF (Bernstein)
    rdcf, err = _safe_compute(api.get_reverse_dcf, symbol)
    if rdcf and "error" not in rdcf:
        row["rdcf_implied_growth"] = rdcf.get("implied_growth_rate")
        row["rdcf_implied_margin"] = rdcf.get("implied_margin")
        row["rdcf_model"] = rdcf.get("model")
        row["rdcf_base_cf"] = rdcf.get("base_cf_used")
        row["rdcf_market_cap"] = rdcf.get("market_cap")
        row["rdcf_3y_cagr"] = rdcf.get("historical_3y_cagr")
        row["rdcf_5y_cagr"] = rdcf.get("historical_5y_cagr")
        row["rdcf_assessment"] = rdcf.get("assessment")
        if rdcf.get("sensitivity"):
            row["rdcf_sensitivity"] = json.dumps(rdcf["sensitivity"])
    elif err:
        errors["reverse_dcf"] = err

    # 6. Capex Cycle
    cc, err = _safe_compute(api.get_capex_cycle, symbol)
    if cc:
        if cc.get("skipped"):
            row["capex_phase"] = "skipped"
        elif cc.get("phase"):
            row["capex_phase"] = cc["phase"]
            years = cc.get("years", [])
            if years:
                latest = years[0]
                row["capex_cwip_to_nb"] = latest.get("cwip_to_netblock")
                row["capex_intensity"] = latest.get("capex_intensity")
                row["capex_asset_turnover"] = latest.get("fixed_asset_turnover")
    elif err:
        errors["capex_cycle"] = err

    # 7. Common Size P&L (latest year only)
    cs_pl, err = _safe_compute(api.get_common_size_pl, symbol)
    if cs_pl and cs_pl.get("years"):
        latest = cs_pl["years"][0]
        row["cs_biggest_cost"] = cs_pl.get("biggest_cost")
        row["cs_fastest_growing_cost"] = cs_pl.get("fastest_growing_cost")
        row["cs_raw_material_pct"] = latest.get("raw_material_pct")
        row["cs_employee_pct"] = latest.get("employee_pct")
        row["cs_depreciation_pct"] = latest.get("depreciation_pct")
        row["cs_interest_pct"] = latest.get("interest_pct")
        row["cs_net_margin_pct"] = latest.get("net_margin_pct")
        row["cs_ebit_pct"] = latest.get("ebit_pct")
        row["cs_denominator"] = latest.get("denominator")
    elif err:
        errors["common_size"] = err

    # 8. BFSI Metrics (latest year only)
    bfsi, err = _safe_compute(api.get_bfsi_metrics, symbol)
    if bfsi and bfsi.get("is_bfsi") and bfsi.get("years"):
        latest = bfsi["years"][0]
        row["bfsi_nim_pct"] = latest.get("nim_pct")
        row["bfsi_roa_pct"] = latest.get("roa_pct")
        row["bfsi_cost_to_income_pct"] = latest.get("cost_to_income_pct")
        row["bfsi_equity_multiplier"] = latest.get("equity_multiplier")
        row["bfsi_book_value_per_share"] = latest.get("book_value_per_share")
        row["bfsi_pb_ratio"] = latest.get("pb_ratio")

    # 9. Price Performance
    if not skip_perf:
        perf, err = _safe_compute(api.get_price_performance, symbol, index_cache=index_cache)
        if perf and perf.get("periods"):
            for p in perf["periods"]:
                period = p["period"].lower()
                row[f"perf_{period}_stock"] = p.get("stock_return")
                row[f"perf_{period}_excess"] = p.get("excess_return")
            row["perf_outperformer"] = 1 if perf.get("outperformer") else 0
            row["perf_sector_index"] = perf.get("sector_index")
        elif err:
            errors["price_performance"] = err

    # 10. Forensic Checks (Batch 1)
    fc, err = _safe_compute(api.get_forensic_checks, symbol)
    if fc and not fc.get("skipped"):
        row["forensic_cfo_ebitda_5y"] = fc.get("cfo_ebitda_5y_avg")
        row["forensic_cfo_ebitda_signal"] = fc.get("cfo_ebitda_signal")
        row["forensic_dep_volatility"] = fc.get("depreciation_volatility")
        row["forensic_dep_signal"] = fc.get("depreciation_signal")
        row["forensic_cash_yield_pct"] = fc.get("cash_yield_latest_pct")
        row["forensic_cash_yield_signal"] = fc.get("cash_yield_signal")
        row["forensic_cwip_3y_avg"] = fc.get("cwip_3y_avg")
        row["forensic_cwip_signal"] = fc.get("cwip_signal")
    elif err:
        errors["forensic_checks"] = err

    # 11. Improvement Metrics (Batch 1)
    im, err = _safe_compute(api.get_improvement_metrics, symbol)
    if im and not im.get("error"):
        g = im.get("greatness") or {}
        row["improvement_greatness_pct"] = g.get("score_pct")
        row["improvement_greatness_class"] = g.get("classification")
        cp = im.get("capex_productivity") or {}
        row["improvement_capex_prod_ratio"] = cp.get("ratio")
    elif err:
        errors["improvement_metrics"] = err

    # 12. Capital Discipline (Batch 1)
    cd, err = _safe_compute(api.get_capital_discipline, symbol)
    if cd and not cd.get("skipped"):
        rr = cd.get("roce_reinvestment") or {}
        row["capital_roce_reinvest_signal"] = rr.get("latest_signal")
        row["capital_sustainable_growth_3y"] = rr.get("avg_sustainable_growth_3y")
        ed = cd.get("equity_dilution") or {}
        row["capital_equity_dilution_pct"] = ed.get("cagr_3y_pct")
        row["capital_equity_dilution_signal"] = ed.get("signal")
    elif err:
        errors["capital_discipline"] = err

    # 13. Incremental ROCE (Batch 2)
    ir, err = _safe_compute(api.get_incremental_roce, symbol)
    if ir and not ir.get("skipped"):
        r3 = ir.get("incremental_roce_3y") or {}
        row["incremental_roce_3y"] = r3.get("pct")
        row["incremental_roce_3y_signal"] = r3.get("signal")
        r5 = ir.get("incremental_roce_5y") or {}
        row["incremental_roce_5y"] = r5.get("pct")
    elif err:
        errors["incremental_roce"] = err

    # 14. Altman Z-Score (Batch 2)
    az, err = _safe_compute(api.get_altman_zscore, symbol)
    if az and not az.get("skipped"):
        row["altman_zscore"] = az.get("latest_z_score")
        row["altman_zone"] = az.get("latest_zone")
    elif err:
        errors["altman_zscore"] = err

    # 15. Working Capital Deterioration (Batch 2)
    wc, err = _safe_compute(api.get_working_capital_deterioration, symbol)
    if wc and not wc.get("skipped"):
        ccc = wc.get("ccc_trend") or {}
        row["wc_ccc_direction"] = ccc.get("direction")
        row["wc_signal"] = wc.get("signal")
    elif err:
        errors["working_capital"] = err

    # 16. Operating Leverage (Batch 2)
    ol, err = _safe_compute(api.get_operating_leverage, symbol)
    if ol and not ol.get("error"):
        row["dol_avg_3y"] = ol.get("avg_3y_dol")
        row["dol_signal"] = ol.get("signal")
    elif err:
        errors["operating_leverage"] = err

    # 17. FCF Yield (Batch 2)
    fy, err = _safe_compute(api.get_fcf_yield, symbol)
    if fy and not fy.get("error"):
        row["fcf_yield_pct"] = fy.get("fcf_yield_pct")
        row["fcf_yield_signal"] = fy.get("signal")
        row["fcf_pat_ratio"] = fy.get("fcf_pat_ratio")
    elif err:
        errors["fcf_yield"] = err

    # 18. Tax Rate Analysis (Batch 2)
    tr, err = _safe_compute(api.get_tax_rate_analysis, symbol)
    if tr and not tr.get("error"):
        row["tax_avg_3y_etr"] = tr.get("avg_3y_etr")
        row["tax_signal"] = tr.get("signal")
    elif err:
        errors["tax_rate"] = err

    # 19. Receivables Quality (Batch 2)
    rq, err = _safe_compute(api.get_receivables_quality, symbol)
    if rq and not rq.get("skipped"):
        row["recv_quality_signal"] = rq.get("signal")
    elif err:
        errors["receivables_quality"] = err

    # 20. WACC parameters
    try:
        wacc_data = api.get_wacc_params(symbol)
        if "wacc" in wacc_data:
            row["wacc"] = wacc_data["wacc"]
        if "ke" in wacc_data:
            row["ke"] = wacc_data["ke"]
        # cost_of_debt is explicitly None for BFSI/insurance (build_wacc_params
        # skips CoD for those sectors). Default-via-`get` with a fallback only
        # fires for missing keys; an explicit None still returns None and
        # blowing up here used to clear beta_blume / beta_raw / beta_r_squared
        # for every banking & insurance stock (HDFCLIFE, SBIN, HDFCBANK, etc.).
        cod = wacc_data.get("cost_of_debt") or {}
        if cod.get("kd_pretax"):
            row["kd_pretax"] = cod["kd_pretax"]
        beta = wacc_data.get("beta", {})
        if isinstance(beta, dict):
            row["beta_blume"] = beta.get("blume_beta")
            row["beta_raw"] = beta.get("raw_beta")
            row["beta_r_squared"] = beta.get("r_squared")
        row["terminal_growth"] = wacc_data.get("terminal_growth")
        flags = wacc_data.get("reliability_flags", [])
        if flags:
            row["wacc_flags"] = ",".join(flags)
    except Exception as e:
        row["wacc_flags"] = f"error:{e}"

    row["errors"] = json.dumps(errors) if errors else None
    return row


def main():
    parser = argparse.ArgumentParser(description="Pre-compute analytical snapshots")
    parser.add_argument("--symbol", type=str, default=None, help="Single symbol to compute")
    parser.add_argument("--limit", type=int, default=0, help="Limit to first N stocks (0=all)")
    parser.add_argument("--skip-perf", action="store_true", help="Skip price_performance (no yfinance)")
    args = parser.parse_args()

    from flowtracker.research.data_api import ResearchDataAPI
    from flowtracker.screener_engine import ScreenerEngine
    from flowtracker.store import FlowStore

    store = FlowStore()
    store.__enter__()
    api = ResearchDataAPI()
    engine = ScreenerEngine(store)

    # Get stock universe
    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = [r[0] for r in store._conn.execute(
            "SELECT DISTINCT symbol FROM index_constituents ORDER BY symbol"
        ).fetchall()]
        if args.limit > 0:
            symbols = symbols[:args.limit]

    print(f"Computing analytics for {len(symbols)} stocks...")

    # Pre-fetch index prices (unless skipping perf)
    index_cache = None
    if not args.skip_perf:
        index_cache = prefetch_index_prices()

    # Compute
    ok = 0
    fail = 0
    start_time = time.time()
    error_counts: dict[str, int] = {}

    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Computing...", total=len(symbols))

        for symbol in symbols:
            progress.update(task, description=symbol)
            try:
                t0 = time.time()
                row = compute_stock(api, engine, symbol, index_cache, args.skip_perf)
                row["compute_duration_ms"] = int((time.time() - t0) * 1000)
                store.upsert_analytical_snapshot(row)
                ok += 1

                # Track error distribution
                if row.get("errors"):
                    for metric in json.loads(row["errors"]).keys():
                        error_counts[metric] = error_counts.get(metric, 0) + 1
            except Exception as e:
                fail += 1
                print(f"  FAIL {symbol}: {e}")

            progress.advance(task)

    elapsed = time.time() - start_time
    print(f"\nDone: {ok}/{len(symbols)} computed, {fail} failed ({elapsed:.1f}s)")
    if error_counts:
        print("Metric errors:")
        for metric, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            print(f"  {metric}: {count} stocks")

    api.close()
    store.__exit__(None, None, None)


if __name__ == "__main__":
    main()
