#!/bin/bash
# Quarterly holdings + scanner with retry (3 attempts per step, 5min backoff)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300

echo "=== $(date) === Quarterly Holdings + Scanner ===" >> "$LOG"
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

# Each step retries independently — a scan refresh failure shouldn't block holding fetch
run_with_retry "flowtrack holding fetch" "Watchlist holdings"
run_with_retry "flowtrack scan refresh" "Scanner refresh"
run_with_retry "flowtrack scan fetch" "Scanner batch fetch"

echo "=== $(date) === Quarterly complete ===" >> "$LOG"
