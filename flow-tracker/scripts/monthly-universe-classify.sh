#!/bin/bash
# Monthly universe classification refresh — yfinance sector/industry for the
# full liquid NSE universe. Keeps company_snapshot.sector/industry fresh so the
# sector resolver (skills / KPIs / peers / D&A) covers the long tail, not just
# the index set. yfinance-only (no Screener) → safe to run anytime. Resume-safe.
set -o pipefail
LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
echo "=== $(date) === Monthly Universe Classify (yf sector/industry) ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }
"$UV" run python scripts/backfill_yf_sector_industry.py >> "$LOG" 2>&1
echo "=== $(date) === Monthly Universe Classify done (exit $?) ===" >> "$LOG"
