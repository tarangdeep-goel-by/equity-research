#!/bin/bash
# Monthly MF fetch with retry (3 attempts, 5min backoff)
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300

echo "=== $(date) === Monthly MF Fetch ===" >> "$LOG"
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

for attempt in $(seq 1 $MAX_RETRIES); do
    if $UV run flowtrack mf fetch >> "$LOG" 2>&1; then
        echo "[OK] Attempt $attempt succeeded at $(date)" >> "$LOG"
        exit 0
    fi
    echo "[RETRY] Attempt $attempt failed at $(date), waiting ${BACKOFF}s..." >> "$LOG"
    [ "$attempt" -lt "$MAX_RETRIES" ] && sleep $BACKOFF
done

echo "[FAIL] All $MAX_RETRIES attempts failed at $(date)" >> "$LOG"
write_alert_marker "mf fetch all $MAX_RETRIES attempts failed"
exit 1
