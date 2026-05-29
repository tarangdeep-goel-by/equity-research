#!/bin/bash
# Weekly UNIVERSE-WIDE light refresh — valuation snapshots, consensus estimates,
# estimate revisions, corporate actions for the FULL liquid NSE universe (~2,000),
# not just the index. yfinance-based (light) → safe weekly. Supersedes the
# index-only weekly jobs (universe is a superset). Heavy Screener data
# (financials/shareholding/charts) stays on the quarterly-universe cadence.
set -o pipefail
LOG="$HOME/.local/share/flowtracker/cron.log"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
echo "=== $(date) === Weekly Universe Light Refresh ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }
for step in valuation estimates estimate_revisions corporate_actions; do
  echo "--- universe $step ---" >> "$LOG"
  "$UV" run python scripts/backfill-nifty250.py --universe --step "$step" >> "$LOG" 2>&1
done
echo "=== $(date) === Weekly Universe Light Refresh done (exit $?) ===" >> "$LOG"
