#!/bin/bash
# Symlinked/copied to ~/.local/share/flowtracker/scripts/ on install (see plists).
# Refresh F&O eligible universe. Runs 1st of every month at 10:00 (NSE refreshes quarterly;
# monthly idempotent runs are cheap and simpler than a true quarterly cron).
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300  # 5 minutes

echo "=== $(date) === Quarterly F&O Universe Refresh ===" >> "$LOG"
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

run_with_retry "flowtrack fno universe refresh" "F&O eligible universe"

echo "=== $(date) === Quarterly F&O universe complete ===" >> "$LOG"
