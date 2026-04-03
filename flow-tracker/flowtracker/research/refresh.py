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


def _is_fresh(store, symbol: str, table: str, hours: int = 6) -> bool:
    """Check if data in a table for this symbol was fetched within `hours` hours.

    Uses fetched_at, updated_at, or date columns depending on table schema.
    Returns True if fresh data exists, False if stale or missing.
    """
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    for col in ["fetched_at", "updated_at"]:
        try:
            row = store._conn.execute(
                f"SELECT MAX({col}) FROM {table} WHERE symbol = ?",  # noqa: S608
                (symbol,),
            ).fetchone()
            if row and row[0] and row[0] >= cutoff:
                return True
        except Exception:
            continue

    # Fallback: check date column
    try:
        row = store._conn.execute(
            f"SELECT MAX(date) FROM {table} WHERE symbol = ?",  # noqa: S608
            (symbol,),
        ).fetchone()
        if row and row[0] and row[0] >= cutoff[:10]:  # date only, no time
            return True
    except Exception:
        pass

    return False


def _detect_parent_subsidiary(store, symbol: str, shareholders: list) -> None:
    """Auto-detect if any promoter of this stock is itself a listed company.

    If found, upsert into listed_subsidiaries table (this stock as subsidiary).
    """
    try:
        # Get all listed company names from index_constituents
        all_companies = store._conn.execute(
            "SELECT DISTINCT symbol, company_name FROM index_constituents"
        ).fetchall()
        # Build lookup: lowercase company name fragment → symbol
        name_to_symbol = {}
        for r in all_companies:
            name = r["company_name"].lower()
            sym = r["symbol"]
            if sym == symbol:
                continue  # skip self
            name_to_symbol[name] = sym
            # Also match on just the first word (e.g. "ICICI" from "ICICI Bank Limited")
            first_word = name.split()[0]
            if len(first_word) > 3:
                name_to_symbol[first_word] = sym

        # Check promoter entries
        for sh in shareholders:
            if sh.get("classification", "").lower() != "promoters":
                continue
            pct = sh.get("percentage", 0)
            if pct < 20:
                continue
            holder = sh.get("holder_name", "").lower()

            for company_name, parent_sym in name_to_symbol.items():
                if company_name in holder:
                    # Found a match — this stock is a subsidiary of parent_sym
                    sub_name = store._conn.execute(
                        "SELECT company_name FROM index_constituents WHERE symbol = ? LIMIT 1",
                        (symbol,),
                    ).fetchone()
                    sub_name = sub_name["company_name"] if sub_name else symbol
                    store.upsert_listed_subsidiary(
                        parent_sym, symbol, sub_name, pct,
                        relationship=f"Auto-detected: promoter '{sh.get('holder_name', '')}'",
                    )
                    return  # one match is enough
    except Exception:
        pass  # don't break refresh for detection failures


def refresh_for_research(
    symbol: str, console: Console | None = None, max_age_hours: int = 6,
) -> dict[str, int]:
    """Fetch fresh data for a stock. Skips sources with data < max_age_hours old.

    Returns {source: record_count} summary.
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
        # --- Freshness gate: skip if data is recent ---
        key_tables = ["quarterly_results", "valuation_snapshot", "company_profiles"]
        fresh_count = sum(1 for t in key_tables if _is_fresh(store, symbol, t, hours=max_age_hours))
        if fresh_count >= 2:
            _log(f"\n[dim]Data for {symbol} is fresh (<{max_age_hours}h old across {fresh_count}/{len(key_tables)} key tables). Skipping refresh.[/]")
            _log("[dim]Use --force-refresh or wait for data to age to re-fetch.[/]")
            # Return existing counts so caller knows data exists
            for t in key_tables:
                row = store._conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE symbol = ?", (symbol,),  # noqa: S608
                ).fetchone()
                summary[t] = row[0] if row else 0
            return summary

        # --- 1. Screener.in ---
        _log("\n[bold]Screener.in[/]")
        company_id = ""
        warehouse_id = ""
        try:
            from flowtracker.screener_client import ScreenerClient

            with ScreenerClient() as sc:
                # Company page + parse
                html = sc.fetch_company_page(symbol)

                # Company profile (about text + key points)
                try:
                    profile = sc.parse_about_from_html(symbol, html)
                    if profile.get("about_text"):
                        store.upsert_company_profile(symbol, profile)
                        _ok("company_profile", 1)
                    else:
                        _skip("company_profile", "no about text found")
                except Exception as e:
                    _skip("company_profile", str(e))

                # Company documents (concalls + annual reports)
                try:
                    docs = sc.parse_documents_from_html(html)
                    doc_count = store.upsert_documents(symbol, docs)
                    if doc_count:
                        _ok("company_documents", doc_count)
                    else:
                        _skip("company_documents", "no documents found")
                except Exception as e:
                    _skip("company_documents", str(e))

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

                        # Auto-detect parent company from promoter holdings
                        _detect_parent_subsidiary(store, symbol, shareholders)
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

        # --- 6. FMP (Financial Modeling Prep) ---
        _log("\n[bold]FMP[/]")
        try:
            from flowtracker.fmp_client import FMPClient

            fmp = FMPClient()

            try:
                dcf = fmp.fetch_dcf(symbol)
                if dcf:
                    store.upsert_fmp_dcf([dcf])
                    _ok("fmp_dcf", 1)
                else:
                    _skip("fmp_dcf", "no data")
            except Exception as e:
                _skip("fmp_dcf", str(e))

            try:
                techs = fmp.fetch_technicals_all(symbol)
                if techs:
                    store.upsert_fmp_technical_indicators(techs)
                    _ok("fmp_technicals", len(techs))
                else:
                    _skip("fmp_technicals", "no data")
            except Exception as e:
                _skip("fmp_technicals", str(e))

            try:
                metrics = fmp.fetch_key_metrics(symbol)
                if metrics:
                    store.upsert_fmp_key_metrics(metrics)
                    _ok("fmp_key_metrics", len(metrics))
                else:
                    _skip("fmp_key_metrics", "no data")
            except Exception as e:
                _skip("fmp_key_metrics", str(e))

            try:
                growth = fmp.fetch_financial_growth(symbol)
                if growth:
                    store.upsert_fmp_financial_growth(growth)
                    _ok("fmp_growth", len(growth))
                else:
                    _skip("fmp_growth", "no data")
            except Exception as e:
                _skip("fmp_growth", str(e))

            try:
                grades = fmp.fetch_analyst_grades(symbol)
                if grades:
                    store.upsert_fmp_analyst_grades(grades)
                    _ok("fmp_grades", len(grades))
                else:
                    _skip("fmp_grades", "no data")
            except Exception as e:
                _skip("fmp_grades", str(e))

            try:
                targets = fmp.fetch_price_targets(symbol)
                if targets:
                    store.upsert_fmp_price_targets(targets)
                    _ok("fmp_targets", len(targets))
                else:
                    _skip("fmp_targets", "no data")
            except Exception as e:
                _skip("fmp_targets", str(e))

        except FileNotFoundError:
            _skip("fmp", "no API key — create ~/.config/flowtracker/fmp.env")
        except Exception as e:
            _skip("fmp", str(e))

    return summary


def refresh_for_business(symbol: str, console: Console | None = None) -> dict[str, int]:
    """Light refresh for business profile — only Screener page data (about, docs, peers).

    Much faster than refresh_for_research — ~5 API calls vs ~50.
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
        # Freshness gate
        if _is_fresh(store, symbol, "company_profiles", hours=6):
            _log(f"\n[dim]Business data for {symbol} is fresh (<6h). Skipping refresh.[/]")
            return summary

        _log("\n[bold]Screener.in (business data only)[/]")
        try:
            from flowtracker.screener_client import ScreenerClient

            with ScreenerClient() as sc:
                html = sc.fetch_company_page(symbol)

                # Company profile (about + key points)
                try:
                    profile = sc.parse_about_from_html(symbol, html)
                    if profile.get("about_text"):
                        store.upsert_company_profile(symbol, profile)
                        _ok("company_profile", 1)
                    else:
                        _skip("company_profile", "no about text")
                except Exception as e:
                    _skip("company_profile", str(e))

                # Company documents (concalls + annual reports)
                try:
                    docs = sc.parse_documents_from_html(html)
                    doc_count = store.upsert_documents(symbol, docs)
                    if doc_count:
                        _ok("company_documents", doc_count)
                    else:
                        _skip("company_documents", "no documents")
                except Exception as e:
                    _skip("company_documents", str(e))

                # Peers (for competitive context)
                company_id, warehouse_id = _extract_ids_from_html(html)
                if warehouse_id:
                    try:
                        peers = sc.fetch_peers(warehouse_id)
                        count = store.upsert_peers(symbol, peers)
                        _ok("peers", count)
                    except Exception as e:
                        _skip("peers", str(e))

                # Expense breakdown (cost structure insight)
                if company_id:
                    for parent in ("Sales", "Expenses"):
                        try:
                            data = sc.fetch_schedules(company_id, "profit-loss", parent)
                            count = store.upsert_schedules(symbol, "profit-loss", parent, data)
                            _ok(f"schedules_{parent.lower()}", count)
                        except Exception as e:
                            _skip(f"schedules_{parent.lower()}", str(e))

        except Exception as e:
            _skip("screener", str(e))

    return summary
