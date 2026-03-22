#!/bin/bash
# Monthly MF scheme portfolio fetch from all AMCs
# Schedule: 12th of each month (portfolios available by 10th-15th)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Monthly MF Portfolio ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Fetch previous month's portfolio (default behavior of mfport fetch)
$UV run flowtrack mfport fetch >> "$LOG" 2>&1

echo "=== $(date) === Monthly MF portfolio complete ===" >> "$LOG"
