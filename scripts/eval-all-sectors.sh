#!/opt/homebrew/bin/bash
# eval-all-sectors.sh — run full 15-sector × 7-agent matrix sequentially.
# Each sector uses eval-pipeline.sh (2 reports in parallel, Gemini grading async).
# Tested agents (ownership, valuation) are first in each sector's queue.
#
# Usage: ./eval-all-sectors.sh [start_sector]
# Example: ./eval-all-sectors.sh bfsi         # start from bfsi (default)
#          ./eval-all-sectors.sh pharma       # start from pharma, do pharma + remaining

set -u

START_SECTOR="${1:-bfsi}"

# Sector order — tested first, then by complexity
SECTORS=(
  bfsi          # SBIN — PSU bank, baseline BFSI (pilot)
  private_bank  # HDFCBANK — tested in BFSI pilot, validates ADR/GDR discipline
  it_services   # TCS — ownership/valuation tested; FCF yield + attrition
  pharma        # SUNPHARMA — tested; segment SOTP + FDA pipeline
  real_estate   # GODREJPROP — tested; realization per sqft + NAV
  regulated_power # NTPC — tested; regulated ROE + SOTP
  metals        # VEDL — tested; through-cycle EBITDA + CBAM
  telecom       # BHARTIARTL — tested; Target MCap not EV per-share (Pattern C3)
  fmcg          # HINDUNILVR — tested; mgmt-guidance anchoring
  conglomerate  # ADANIENT — tested; SOTP + holdco discount
  platform      # ETERNAL — tested; EV/GMV + take-rate normalization
  insurance     # POLICYBZR — tested; insurtech framework
  auto          # OLAELEC — tested; EV pure-play + cash runway
  chemicals     # PIDILITIND — tested; EV/EBITDA primary
  broker        # GROWW — tested; discount-broker flat-fee F&O
)

# Queue order per sector — tested agents first, then rest
AGENTS=(ownership valuation financials business risk technical sector)

TS=$(date +%Y%m%d-%H%M%S)
MASTER_DIR="/tmp/eval-master-$TS"
mkdir -p "$MASTER_DIR"
MASTER_LOG="$MASTER_DIR/master.log"
MASTER_FEEDBACK="$MASTER_DIR/ALL_FEEDBACK.md"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(stamp)] $*" | tee -a "$MASTER_LOG"; }

log "MASTER start — $TS"
log "  master_dir=$MASTER_DIR"
log "  start_sector=$START_SECTOR"
log "  sectors=${SECTORS[*]}"
log "  agents per sector=${AGENTS[*]}"

{
  echo "# Master Eval Feedback — $TS"
  echo ""
  echo "Started: $(stamp)"
  echo "Start sector: $START_SECTOR"
  echo ""
} > "$MASTER_FEEDBACK"

# Stock mapping via case (portable across bash 3+/4+)
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
    broker) echo GROWW ;;
    auto) echo OLAELEC ;;
    chemicals) echo PIDILITIND ;;
    fmcg) echo HINDUNILVR ;;
    *) echo "" ;;
  esac
}

# Determine start position
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

  sector_logdir="$MASTER_DIR/$sector"
  mkdir -p "$sector_logdir"

  log "SECTOR START $sector ($stock)"

  EVAL_LOGDIR="$sector_logdir" bash "$SCRIPT_DIR/eval-pipeline.sh" \
    "$sector" "$stock" "${AGENTS[@]}" \
    >> "$sector_logdir/pipeline.out" 2>&1
  rc=$?
  log "SECTOR END   $sector ($stock) (rc=$rc)"

  # Append sector feedback to master feedback
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
echo "MASTER PIPELINE DONE"
echo "Master feedback: $MASTER_FEEDBACK"
echo "Per-sector dirs: $MASTER_DIR/<sector>/"
echo "=============================================="
