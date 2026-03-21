#!/bin/bash
# Weekly valuation snapshot + consensus estimates for all watchlist stocks
# Schedule: Every Sunday at 8:00 PM IST (2:30 PM UTC)
LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Weekly Valuation ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

$UV run python -m flowtracker fund fetch --valuation-only >> "$LOG" 2>&1
$UV run flowtrack estimates fetch >> "$LOG" 2>&1

echo "=== $(date) === Weekly valuation complete ===" >> "$LOG"
