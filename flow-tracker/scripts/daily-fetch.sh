#!/bin/bash
# Daily FII/DII + gold/silver + MF daily fetch with retry (3 attempts, 5min backoff per step)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300  # 5 minutes

echo "=== $(date) === Daily Fetch ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

write_alert_marker() {
    local reason="$1"
    mkdir -p "$ALERT_DIR"
    {
        date -u +"%Y-%m-%dT%H:%M:%SZ"
        echo "$SCRIPT_NAME: $reason"
        echo "--- last 20 lines of $LOG ---"
        tail -n 20 "$LOG" 2>/dev/null || true
    } > "$ALERT_DIR/${SCRIPT_NAME%.sh}.failed"
}

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
    write_alert_marker "$label all $MAX_RETRIES attempts failed"
    return 1
}

run_with_retry "flowtrack fetch" "FII/DII flows"
run_with_retry "flowtrack gold fetch" "Gold/silver prices"
run_with_retry "flowtrack gold metals" "Industrial metals prices (Al/Cu)"
run_with_retry "flowtrack mf daily fetch" "SEBI daily MF flows"
run_with_retry "flowtrack macro fetch" "Macro indicators"
run_with_retry "flowtrack macro fetch-index" "Index daily prices"
# RBI WSS publishes Friday but daily idempotent fetches keep cron simple
# (re-fetching the same release_date is a no-op INSERT OR REPLACE).
run_with_retry "flowtrack macro wss-fetch" "RBI WSS system credit/deposit"
run_with_retry "flowtrack bhavcopy fetch" "Bhavcopy + delivery"
run_with_retry "flowtrack fno fetch" "F&O bhavcopy + participant OI"
run_with_retry "flowtrack deals fetch" "Bulk/block deals"
run_with_retry "flowtrack insider fetch" "Insider transactions"
run_with_retry "python -m flowtracker fund fetch --valuation-only" "Valuation snapshots"

echo "=== $(date) === Daily complete ===" >> "$LOG"
