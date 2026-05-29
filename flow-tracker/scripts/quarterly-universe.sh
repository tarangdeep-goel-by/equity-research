#!/bin/bash
# Quarterly universe fundamentals/data refresh for the FULL liquid NSE universe
# (~2,000 stocks beyond the index set). Keeps the long tail's financials,
# shareholding, charts, BS/CF, estimates fresh — the recurring companion to the
# one-time backfill_universe_* catch-ups. Screener-heavy → quarterly + overnight.
# Both scripts skip already-current symbols (resume-safe), so a partial/aborted
# run just resumes next time.
set -o pipefail
LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
echo "=== $(date) === Quarterly Universe Refresh ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }
echo "--- universe fundamentals (quarterly/annual/ratios) ---" >> "$LOG"
"$UV" run python scripts/backfill_universe_fundamentals.py >> "$LOG" 2>&1
echo "--- universe v2 (shareholding/pledge/charts/BS/CF/estimates) ---" >> "$LOG"
"$UV" run python scripts/backfill_universe_v2.py >> "$LOG" 2>&1
echo "=== $(date) === Quarterly Universe Refresh done (exit $?) ===" >> "$LOG"
