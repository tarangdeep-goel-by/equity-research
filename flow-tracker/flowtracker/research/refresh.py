"""Fetch fresh data for a stock before the research agent runs."""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

from rich.console import Console


def _extract_ids_from_html(html: str) -> tuple[str, str]:
    """Extract company_id and warehouse_id from already-fetched Screener HTML.

    Returns (company_id, warehouse_id). Either may be empty string on failure.
    """
    company_id = ""
    warehouse_id = ""

    m = re.search(r'data-company-id="(\d+)"', html)
    if m:
        company_id = m.group(1)

    m = re.search(r'formaction="/user/company/export/(\d+)/"', html)
    if not m:
        m = re.search(r"/user/company/export/(\d+)/", html)
    if m:
        warehouse_id = m.group(1)

    return company_id, warehouse_id


def refresh_for_research(symbol: str, console: Console | None = None) -> dict[str, int]:
    """Fetch all fresh data for a stock. Returns {source: record_count} summary.

    Called before the research agent to ensure tools read current data.
    Errors in individual fetches are logged but don't stop the process.
    """
    symbol = symbol.upper()
    summary: dict[str, int] = {}

    def _log(msg: str) -> None:
        if console:
            console.print(msg)

    def _ok(name: str, count: int) -> None:
        summary[name] = count
        _log(f"  [green]\u2713[/] {name}: {count} records")

    def _skip(name: str, err: str) -> None:
        summary[name] = 0
        _log(f"  [yellow]\u2717[/] {name}: {err}")

    from flowtracker.store import FlowStore

    with FlowStore() as store:
        # --- 1. Screener.in ---
        _log("\n[bold]Screener.in[/]")
        company_id = ""
        warehouse_id = ""
        try:
            from flowtracker.screener_client import ScreenerClient

            with ScreenerClient() as sc:
                # Company page + parse
                html = sc.fetch_company_page(symbol)

                quarters = sc.parse_quarterly_from_html(symbol, html)
                if quarters:
                    store.upsert_quarterly_results(quarters)
                    _ok("quarterly_results", len(quarters))
                else:
                    _skip("quarterly_results", "no data parsed")

                ratios = sc.parse_ratios_from_html(symbol, html)
                if ratios:
                    store.upsert_screener_ratios(ratios)
                    _ok("screener_ratios", len(ratios))
                else:
                    _skip("screener_ratios", "no data parsed")

                # Excel export
                try:
                    excel = sc.download_excel(symbol)
                    annual = sc.parse_annual_financials(symbol, excel)
                    if annual:
                        store.upsert_annual_financials(annual)
                        _ok("annual_financials", len(annual))
                    else:
                        _skip("annual_financials", "no data parsed")
                except Exception as e:
                    _skip("annual_financials", str(e))

                # Extract IDs from already-fetched HTML (avoid duplicate fetch)
                company_id, warehouse_id = _extract_ids_from_html(html)
                if company_id or warehouse_id:
                    store.upsert_screener_ids(symbol, company_id, warehouse_id)
                    _ok("screener_ids", 1)
                else:
                    _skip("screener_ids", "could not extract from HTML")

                # Chart API (PE + price)
                if company_id:
                    for chart_type in ("pe", "price"):
                        try:
                            data = sc.fetch_chart_data_by_type(company_id, chart_type)
                            datasets = data.get("datasets", [])
                            count = store.upsert_chart_data(symbol, chart_type, datasets)
                            _ok(f"chart_{chart_type}", count)
                            time.sleep(1)
                        except Exception as e:
                            _skip(f"chart_{chart_type}", str(e))

                # Peers
                if warehouse_id:
                    try:
                        peers = sc.fetch_peers(warehouse_id)
                        count = store.upsert_peers(symbol, peers)
                        _ok("peers", count)
                    except Exception as e:
                        _skip("peers", str(e))

                # Shareholders
                if company_id:
                    try:
                        shareholders = sc.fetch_shareholders(company_id)
                        count = store.upsert_shareholder_details(symbol, shareholders)
                        _ok("shareholders", count)
                    except Exception as e:
                        _skip("shareholders", str(e))

                # Schedules (profit-loss: Sales + Expenses)
                if company_id:
                    for parent in ("Sales", "Expenses"):
                        try:
                            data = sc.fetch_schedules(company_id, "profit-loss", parent)
                            count = store.upsert_schedules(symbol, "profit-loss", parent, data)
                            _ok(f"schedules_{parent.lower()}", count)
                            time.sleep(1)
                        except Exception as e:
                            _skip(f"schedules_{parent.lower()}", str(e))

        except Exception as e:
            _skip("screener", str(e))

        # --- 2. yfinance ---
        _log("\n[bold]yfinance[/]")
        try:
            from flowtracker.fund_client import FundClient

            fc = FundClient()
            snap = fc.fetch_valuation_snapshot(symbol)
            if snap:
                store.upsert_valuation_snapshot(snap)
                _ok("valuation_snapshot", 1)
        except Exception as e:
            _skip("valuation_snapshot", str(e))

        try:
            from flowtracker.estimates_client import EstimatesClient

            ec = EstimatesClient()
            est = ec.fetch_estimates(symbol)
            if est:
                store.upsert_consensus_estimates([est])
                _ok("consensus_estimate", 1)
            surp = ec.fetch_surprises(symbol)
            if surp:
                store.upsert_earnings_surprises(surp)
                _ok("earnings_surprises", len(surp))
        except Exception as e:
            _skip("estimates", str(e))

        # --- 3. NSE data ---
        _log("\n[bold]NSE[/]")
        try:
            from flowtracker.insider_client import InsiderClient

            with InsiderClient() as ic:
                trades = ic.fetch_by_symbol(symbol, days=90)
                if trades:
                    store.upsert_insider_transactions(trades)
                    _ok("insider_transactions", len(trades))
                else:
                    _skip("insider_transactions", "no data")
        except Exception as e:
            _skip("insider_transactions", str(e))

        try:
            from flowtracker.bhavcopy_client import BhavcopyClient

            with BhavcopyClient() as bc:
                today = date.today()
                records = bc.fetch_range(today - timedelta(days=7), today)
                if records:
                    store.upsert_daily_stock_data(records)
                    sym_count = sum(1 for r in records if r.symbol == symbol)
                    _ok("delivery_data", sym_count)
                else:
                    _skip("delivery_data", "no data")
        except Exception as e:
            _skip("delivery_data", str(e))

        try:
            from flowtracker.deals_client import DealsClient

            with DealsClient() as dc:
                deals = dc.fetch_deals()
                if deals:
                    store.upsert_deals(deals)
                    sym_deals = [d for d in deals if d.symbol == symbol]
                    _ok("bulk_block_deals", len(sym_deals))
                else:
                    _skip("bulk_block_deals", "no data")
        except Exception as e:
            _skip("bulk_block_deals", str(e))

        # --- 4. Macro ---
        _log("\n[bold]Macro[/]")
        try:
            from flowtracker.macro_client import MacroClient

            with MacroClient() as mc:
                snaps = mc.fetch_snapshot(days=5)
                if snaps:
                    store.upsert_macro_snapshots(snaps)
                    _ok("macro", len(snaps))
                else:
                    _skip("macro", "no data")
        except Exception as e:
            _skip("macro", str(e))

        try:
            from flowtracker.client import NSEClient

            with NSEClient() as nc:
                flows = nc.fetch_daily()
                if flows:
                    store.upsert_flows(flows)
                    _ok("fii_dii_flows", len(flows))
                else:
                    _skip("fii_dii_flows", "no data")
        except Exception as e:
            _skip("fii_dii_flows", str(e))

        # --- 5. BSE Filings ---
        _log("\n[bold]BSE Filings[/]")
        try:
            from flowtracker.filing_client import FilingClient

            with FilingClient() as fc:
                filings = fc.fetch_filings(symbol)
                if filings:
                    store.upsert_filings(filings)
                    _ok("filings", len(filings))
                else:
                    _skip("filings", "no data")
        except Exception as e:
            _skip("filings", str(e))

    return summary
