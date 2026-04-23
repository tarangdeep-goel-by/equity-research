#!/bin/bash
# Nightly universe-wide adj_close recompute + drift sweep.
#
# Safety net behind the sync-hook in upsert_corporate_actions: if a sync
# fires but later gets reverted, if a corporate_actions correction lands
# outside the normal fetch path, or if adj_close ever drifts from the
# computed helper — this catches it.
#
# Exit non-zero on drift; logs every run.

set -o pipefail

LOG="$HOME/.local/share/flowtracker/cron.log"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Nightly adj_close recompute ===" >> "$LOG"
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

# Full universe backfill (idempotent — only updates rows where adjustment factor changed)
if $UV run python scripts/backfill_adj_close.py --samples 100 >> "$LOG" 2>&1; then
    echo "[OK] adj_close recompute + drift sweep passed at $(date)" >> "$LOG"
    exit 0
else
    echo "[FAIL] adj_close recompute or drift sweep failed at $(date)" >> "$LOG"
    write_alert_marker "adj_close recompute or drift sweep failed"
    exit 1
fi
