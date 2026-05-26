#!/bin/bash
# Monthly GST collections fetch with retry (3 attempts, 5min backoff).
#
# CBIC publishes the previous month's collection on the 1st of each month
# (e.g. May data drops on Jun 1). This wrapper runs on the 2nd at 12:00 IST
# to give CBIC a buffer; `flowtrack gst fetch` with no --period flag defaults
# to the previous calendar month, which is exactly what we want.
#
# The CLI's resolution order (Playwright live → seed JSON fallback → exit 1)
# is unchanged here — retry only re-runs the same command.
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300

echo "=== $(date) === Monthly GST Fetch ===" >> "$LOG"
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
    if $UV run flowtrack gst fetch >> "$LOG" 2>&1; then
        echo "[OK] Attempt $attempt succeeded at $(date)" >> "$LOG"
        exit 0
    fi
    echo "[RETRY] Attempt $attempt failed at $(date), waiting ${BACKOFF}s..." >> "$LOG"
    [ "$attempt" -lt "$MAX_RETRIES" ] && sleep $BACKOFF
done

echo "[FAIL] All $MAX_RETRIES attempts failed at $(date)" >> "$LOG"
write_alert_marker "gst fetch all $MAX_RETRIES attempts failed"
exit 1
