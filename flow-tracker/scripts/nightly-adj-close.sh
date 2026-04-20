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
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"

echo "=== $(date) === Nightly adj_close recompute ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Full universe backfill (idempotent — only updates rows where adjustment factor changed)
if $UV run python scripts/backfill_adj_close.py --samples 100 >> "$LOG" 2>&1; then
    echo "[OK] adj_close recompute + drift sweep passed at $(date)" >> "$LOG"
    exit 0
else
    echo "[FAIL] adj_close recompute or drift sweep failed at $(date)" >> "$LOG"
    exit 1
fi
