#!/bin/bash
# Quarterly results fetch from Screener.in (authoritative source for Indian GAAP financials)
# Schedule: 20th of Feb/May/Aug/Nov at 9:00 AM IST
# Source: Screener.in (quarterly P&L + annual financials + historical P/E)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Quarterly Results (Screener.in) ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Backfill uses Screener.in for quarterly results + annual financials
# Then computes historical P/E from yfinance weekly prices
$UV run python -m flowtracker fund backfill >> "$LOG" 2>&1

# Screener ratios (debtor days, inventory days, CCC, ROCE%) for all index stocks
echo "--- $(date) --- Screener ratios ---" >> "$LOG"
$UV run python -c "
from flowtracker.screener_client import ScreenerClient
from flowtracker.store import FlowStore
import time, sys

with ScreenerClient() as sc, FlowStore() as store:
    symbols = [c.symbol for c in store.get_index_constituents()]
    total = len(symbols)
    for i, sym in enumerate(symbols):
        try:
            html = sc.fetch_company_page(sym)
            ratios = sc.parse_ratios_from_html(sym, html)
            if ratios:
                store.upsert_screener_ratios(ratios)
            if (i + 1) % 50 == 0:
                print(f'  Ratios: {i+1}/{total}', file=sys.stderr)
            time.sleep(1)
        except Exception as e:
            print(f'  SKIP {sym}: {e}', file=sys.stderr)
" >> "$LOG" 2>&1

# Filings fetch for watchlist stocks (concalls, results, investor decks)
echo "--- $(date) --- Filings fetch (watchlist) ---" >> "$LOG"
$UV run python -c "
from flowtracker.store import FlowStore
import subprocess, sys

with FlowStore() as store:
    watchlist = store.get_watchlist()
    for sym in watchlist:
        try:
            subprocess.run(
                ['$UV', 'run', 'flowtrack', 'filings', 'fetch', sym, '--download', '-y', '1'],
                capture_output=True, timeout=120
            )
            print(f'  Filings: {sym} OK', file=sys.stderr)
        except Exception as e:
            print(f'  Filings SKIP {sym}: {e}', file=sys.stderr)
" >> "$LOG" 2>&1

echo "=== $(date) === Quarterly results complete ===" >> "$LOG"
