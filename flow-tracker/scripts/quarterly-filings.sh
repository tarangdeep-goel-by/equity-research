#!/bin/bash
# Quarterly concall + investor deck download for Nifty 250
# Schedule: 25th of Feb/May/Aug/Nov at 10:00 AM IST (after most results are filed)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Quarterly Filings Download ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Download concalls + investor decks for all Nifty 250
# --resume skips stocks that already have >=4 concalls
$UV run python scripts/batch-download-filings.py --resume >> "$LOG" 2>&1

echo "=== $(date) === Quarterly filings complete ===" >> "$LOG"
