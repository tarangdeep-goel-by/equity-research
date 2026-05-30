#!/bin/bash
# Quarterly sector-KPI backfill from concall transcripts (BFSI/FMCG/telecom/pharma cohort).
# Drives ensure_concall_data() per symbol with a sector hint, writing the
# extraction to the concall vault — the read path for get_sector_kpis().
# Sector KPIs come from concalls, so this runs on the concall-refresh cadence:
# a few days after quarterly-filings.sh (25th of Feb/May/Aug/Nov) has pulled the
# fresh transcripts into the vault. Runs the script's DEFAULT_COHORT incrementally
# (cached quarters are skipped). Long-running: calls the Claude Agent SDK on live
# concalls — own timestamped log, not the shared cron.log.
# Schedule: 1st of Mar/Jun/Sep/Dec at 10:00 AM IST
set -o pipefail

LOG_DIR="$HOME/.local/share/flowtracker/logs"
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
UV="$HOME/.local/bin/uv"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/quarterly-sector-kpis-$(date +%Y%m%d-%H%M%S).log"

echo "=== $(date) === Quarterly Sector-KPI Backfill ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }

# Default cohort (Nifty-50 BFSI x5 + FMCG x2 + telecom x1 + pharma x3),
# incremental: cached quarters are skipped, so re-runs are cheap.
$UV run python scripts/backfill_sector_kpis.py >> "$LOG" 2>&1

echo "=== $(date) === Sector-KPI backfill complete ===" >> "$LOG"
