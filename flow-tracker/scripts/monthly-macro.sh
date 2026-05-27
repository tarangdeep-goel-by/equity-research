#!/bin/bash
# Monthly India macro fetch (CPI / IIP / PMI) with retry (3 attempts, 5min backoff
# per step). Single source per series: CPI from dbnomics (IMF/IFS via db.nomics.world,
# freshest — to 2025-06); IIP from the bundled seed (currently the freshest India IIP
# available, to 2025-04 — dbnomics IIP is staler at 2024-10); PMI from seed (S&P Global
# is proprietary, no free live feed). Each step runs independently —
# one failure must not abort the rest (no `set -e`). All three fetches are
# idempotent (INSERT OR REPLACE on period), so re-runs are safe and a month that
# is not yet published upstream simply leaves the prior latest in place.
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
MAX_RETRIES=3
BACKOFF=300  # 5 minutes

echo "=== $(date) === Monthly Macro Fetch (CPI/IIP/PMI) ===" >> "$LOG"
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

run_with_retry "flowtrack cpi fetch" "CPI inflation (dbnomics)"
run_with_retry "flowtrack iip fetch" "IIP industrial production (seed)"
run_with_retry "flowtrack pmi fetch" "PMI services+manufacturing (seed)"

echo "=== $(date) === Monthly Macro complete ===" >> "$LOG"
