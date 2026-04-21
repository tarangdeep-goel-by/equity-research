#!/usr/bin/env bash
# eval-failing-pairs.sh — re-run autoeval only for the (agent, sector) pairs
# that did NOT reach A- in the 2026-04-17 baseline.
#
# Mirrors eval-all-sectors.sh output layout so monitoring/recovery scripts
# keep working. Calls eval-pipeline.sh once per sector with only the failing
# agent subset for that sector.
#
# Usage: ./eval-failing-pairs.sh [start_sector]

set -u

START_SECTOR="${1:-bfsi}"

# Per-sector failing agents from results.tsv (2026-04-17 baseline).
# Ordered tested-first where possible (ownership/valuation/financials first).
failing_agents_for() {
  case "$1" in
    bfsi)            echo "valuation financials business" ;;
    private_bank)    echo "ownership valuation financials business technical sector" ;;
    it_services)     echo "business risk" ;;
    pharma)          echo "ownership valuation financials business risk technical sector" ;;
    real_estate)     echo "valuation financials business risk technical sector" ;;
    regulated_power) echo "valuation financials business technical" ;;
    metals)          echo "valuation business sector" ;;
    telecom)         echo "ownership financials business sector" ;;
    fmcg)            echo "valuation financials business sector" ;;
    conglomerate)    echo "valuation business technical" ;;
    platform)        echo "ownership valuation financials business risk" ;;
    insurance)       echo "ownership valuation financials business risk sector" ;;
    *)               echo "" ;;
  esac
}

# Same sector order as eval-all-sectors.sh (for resume compatibility).
SECTORS=(
  bfsi
  private_bank
  it_services
  pharma
  real_estate
  regulated_power
  metals
  telecom
  fmcg
  conglomerate
  platform
  insurance
)

stock_for() {
  case "$1" in
    bfsi) echo SBIN ;;
    private_bank) echo HDFCBANK ;;
    it_services) echo TCS ;;
    metals) echo VEDL ;;
    platform) echo ETERNAL ;;
    conglomerate) echo ADANIENT ;;
    telecom) echo BHARTIARTL ;;
    real_estate) echo GODREJPROP ;;
    pharma) echo SUNPHARMA ;;
    regulated_power) echo NTPC ;;
    insurance) echo POLICYBZR ;;
    fmcg) echo HINDUNILVR ;;
    *) echo "" ;;
  esac
}

TS=$(date +%Y%m%d-%H%M%S)
MASTER_DIR="/tmp/eval-master-$TS"
mkdir -p "$MASTER_DIR"
MASTER_LOG="$MASTER_DIR/master.log"
MASTER_FEEDBACK="$MASTER_DIR/ALL_FEEDBACK.md"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(stamp)] $*" | tee -a "$MASTER_LOG"; }

log "MASTER start (failing-pairs only) — $TS"
log "  master_dir=$MASTER_DIR"
log "  start_sector=$START_SECTOR"
log "  sectors=${SECTORS[*]}"

{
  echo "# Master Eval Feedback (failing-pairs re-run) — $TS"
  echo ""
  echo "Started: $(stamp)"
  echo "Start sector: $START_SECTOR"
  echo "Baseline: 2026-04-17 autoeval; re-running only pairs that scored below A-."
  echo ""
} > "$MASTER_FEEDBACK"

started=0
for sector in "${SECTORS[@]}"; do
  if [ "$sector" = "$START_SECTOR" ]; then
    started=1
  fi
  if [ $started -eq 0 ]; then
    log "SKIP  $sector (before start)"
    continue
  fi

  stock="$(stock_for "$sector")"
  if [ -z "$stock" ]; then
    log "WARN  $sector — no stock mapping, skipping"
    continue
  fi

  agents_str="$(failing_agents_for "$sector")"
  if [ -z "$agents_str" ]; then
    log "SKIP  $sector — no failing agents in baseline"
    continue
  fi
  read -r -a agents <<<"$agents_str"

  sector_logdir="$MASTER_DIR/$sector"
  mkdir -p "$sector_logdir"

  log "SECTOR START $sector ($stock) — agents: ${agents[*]}"

  EVAL_LOGDIR="$sector_logdir" bash "$SCRIPT_DIR/eval-pipeline.sh" \
    "$sector" "$stock" "${agents[@]}" 2>&1 \
    | tee -a "$sector_logdir/pipeline.out"
  rc=${PIPESTATUS[0]}
  log "SECTOR END   $sector ($stock) (rc=$rc)"

  if [ -f "$sector_logdir/feedback/FEEDBACK.md" ]; then
    {
      echo ""
      echo "=============================================="
      echo ""
      cat "$sector_logdir/feedback/FEEDBACK.md"
    } >> "$MASTER_FEEDBACK"
  fi
done

log "MASTER COMPLETE"
{
  echo ""
  echo "---"
  echo "MASTER COMPLETE: $(stamp)"
} >> "$MASTER_FEEDBACK"

echo ""
echo "=============================================="
echo "MASTER PIPELINE DONE (failing-pairs)"
echo "Master feedback: $MASTER_FEEDBACK"
echo "Per-sector dirs: $MASTER_DIR/<sector>/"
echo "=============================================="
