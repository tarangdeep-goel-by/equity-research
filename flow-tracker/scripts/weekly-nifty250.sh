#!/bin/bash
# Weekly valuation + estimates refresh for all Nifty index stocks
# Schedule: Every Sunday at 9:00 PM IST
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Weekly Nifty Refresh ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Valuation snapshots (yfinance, ~5min)
$UV run python scripts/backfill-nifty250.py --step valuation --sleep 0.3 >> "$LOG" 2>&1

# Consensus estimates + earnings surprises (yfinance, ~10min)
$UV run python scripts/backfill-nifty250.py --step estimates --sleep 0.3 >> "$LOG" 2>&1

# Estimate revision trends (yfinance, ~5min)
$UV run python scripts/backfill-nifty250.py --step estimate_revisions --sleep 0.3 >> "$LOG" 2>&1

# Quarterly balance sheet + cash flow (yfinance, ~5min)
$UV run python scripts/backfill-nifty250.py --step quarterly_bs_cf --sleep 0.3 >> "$LOG" 2>&1

echo "=== $(date) === Weekly Nifty Refresh complete ===" >> "$LOG"
