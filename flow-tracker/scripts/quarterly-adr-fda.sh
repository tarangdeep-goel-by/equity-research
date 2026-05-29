#!/bin/bash
# Symlinked/copied to ~/.local/share/flowtracker/scripts/ on install (see plists).
# Refresh the ADR/GDR program directory + pull USFDA enforcement records for the
# pharma universe. Runs 1st of every month at 10:30 (ADR seed changes rarely and
# FDA records are idempotent INSERT OR REPLACE, so monthly runs are cheap and
# simpler than a true quarterly cron). Wires the previously-unscheduled feeds
# for adr_programs + fda_inspections. Issue #176.
set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
FIRMS_JSON="$PROJECT/flowtracker/data/pharma_fda_firms.json"
MAX_RETRIES=3
BACKOFF=300  # 5 minutes

echo "=== $(date) === ADR refresh + FDA inspections ===" >> "$LOG"
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

# 1. ADR/GDR program directory (bundled seed; idempotent).
run_with_retry "flowtrack adr refresh" "ADR/GDR program directory"

# 2. USFDA enforcement records per pharma firm. Best-effort per symbol — one
#    bad firm string or empty result must not fail the whole cron.
echo "--- $(date) --- FDA inspections (pharma universe) ---" >> "$LOG"
if [ -f "$FIRMS_JSON" ]; then
    while IFS=$'\t' read -r sym firm; do
        [ -z "$sym" ] && continue
        if $UV run flowtrack fda fetch -s "$sym" --firm "$firm" --limit 100 >> "$LOG" 2>&1; then
            echo "[OK] FDA $sym ($firm)" >> "$LOG"
        else
            echo "[SKIP] FDA $sym ($firm) — fetch failed" >> "$LOG"
        fi
    done < <($UV run python -c "
import json, sys
with open('$FIRMS_JSON') as f:
    data = json.load(f)
for row in data.get('firms', []):
    sym = (row.get('symbol') or '').strip()
    firm = (row.get('firm') or '').strip()
    if sym and firm:
        print(f'{sym}\t{firm}')
")
else
    echo "[WARN] $FIRMS_JSON not found — skipping FDA inspections" >> "$LOG"
fi

echo "=== $(date) === ADR/FDA refresh complete ===" >> "$LOG"
