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

echo "=== $(date) === Quarterly results complete ===" >> "$LOG"
