#!/usr/bin/env bash
# Alert engine sweep — chained after daily-fetch.sh.
set -euo pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Alert Check ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }
$UV run flowtrack alert check >> "$LOG" 2>&1
echo "=== $(date) === Alert check complete ===" >> "$LOG"
