#!/bin/bash
# Daily FII/DII + gold/silver + MF daily fetch with retry (3 attempts, 5min backoff per step)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300  # 5 minutes

echo "=== $(date) === Daily Fetch ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

run_with_retry() {
    local cmd="$1"
    local label="$2"
    for attempt in $(seq 1 $MAX_RETRIES); do
        if $UV run $cmd >> "$LOG" 2>&1; then
            echo "[OK] $label attempt $attempt succeeded at $(date)" >> "$LOG"
            return 0
        fi
        echo "[RETRY] $label attempt $attempt failed at $(date), waiting ${BACKOFF}s..." >> "$LOG"
        [ "$attempt" -lt "$MAX_RETRIES" ] && sleep $BACKOFF
    done
    echo "[FAIL] $label all $MAX_RETRIES attempts failed at $(date)" >> "$LOG"
    return 1
}

run_with_retry "flowtrack fetch" "FII/DII flows"
run_with_retry "flowtrack gold fetch" "Gold/silver prices"
run_with_retry "flowtrack mf daily fetch" "SEBI daily MF flows"

echo "=== $(date) === Daily complete ===" >> "$LOG"
