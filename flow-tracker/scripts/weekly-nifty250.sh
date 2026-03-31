#!/bin/bash
# Weekly valuation + estimates refresh for Nifty 250
# Schedule: Every Sunday at 9:00 PM IST
# Replaces weekly-valuation.sh (which only covered watchlist)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Weekly Nifty 250 Refresh ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Valuation snapshots for all 250 (yfinance, ~2min)
$UV run python scripts/backfill-nifty250.py --step valuation --sleep 0.3 >> "$LOG" 2>&1

# Consensus estimates + earnings surprises (yfinance, ~5min)
$UV run python scripts/backfill-nifty250.py --step estimates --sleep 0.3 >> "$LOG" 2>&1

echo "=== $(date) === Weekly Nifty 250 complete ===" >> "$LOG"
