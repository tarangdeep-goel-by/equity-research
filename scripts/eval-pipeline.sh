#!/usr/bin/env bash
# eval-pipeline.sh — run autoeval for one sector, 2 reports at a time,
# Gemini grading per-report in background (so Gemini latency never blocks generation).
#
# Usage: ./eval-pipeline.sh <sector> <stock> <agent1> <agent2> ...
# Example: ./eval-pipeline.sh bfsi SBIN ownership valuation financials business risk technical sector

set -u

SECTOR="${1:?sector required}"
STOCK="${2:?stock required}"
shift 2
AGENTS=("$@")

TS=$(date +%Y%m%d-%H%M%S)
LOGDIR="${EVAL_LOGDIR:-/tmp/eval-$SECTOR-$TS}"
mkdir -p "$LOGDIR/run" "$LOGDIR/grade" "$LOGDIR/feedback"
FT_DIR="/Users/tarang/Documents/Projects/equity-research/flow-tracker"

STATUS="$LOGDIR/status.log"
FEEDBACK="$LOGDIR/feedback/FEEDBACK.md"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(stamp)] $*" | tee -a "$STATUS"; }

log "Pipeline start"
log "  sector=$SECTOR stock=$STOCK"
log "  agents=${AGENTS[*]}"
log "  logdir=$LOGDIR"

# Pre-commit env
{
  echo "# Eval Feedback — $SECTOR ($STOCK)"
  echo ""
  echo "Started: $(stamp)"
  echo "Agents queued: ${AGENTS[*]}"
  echo ""
} > "$FEEDBACK"

grade_agent() {
  local agent="$1"
  log "START grade  $agent"
  cd "$FT_DIR"
  uv run flowtrack research autoeval -a "$agent" --sectors "$SECTOR" --skip-run \
    > "$LOGDIR/grade/$agent.log" 2>&1
  local rc=$?
  log "DONE  grade  $agent (rc=$rc)"

  # Extract summary from evaluate.py output
  {
    echo ""
    echo "---"
    echo "## Agent: $agent — $(stamp)"
    echo ""
    echo "### Grade Summary"
    # Pull summary lines from autoeval stdout (grade/numeric/parameters)
    grep -E "^(Agent:|Grade:|Stock:|Sector:|Summary:|Issues:|Strengths:)" "$LOGDIR/grade/$agent.log" 2>/dev/null \
      | head -40
    echo ""
    echo "### Issues (PROMPT_FIX / DATA_FIX / COMPUTATION / NOT_OUR_PROBLEM)"
    grep -E "^\s*- \[(PROMPT_FIX|DATA_FIX|COMPUTATION|NOT_OUR_PROBLEM)\]" "$LOGDIR/grade/$agent.log" 2>/dev/null \
      | head -40
    echo ""
    echo "### Parameters"
    grep -E "^\s*[a-z_]+: " "$LOGDIR/grade/$agent.log" 2>/dev/null \
      | grep -vE "^\s*(summary|agent|stock|sector):" \
      | head -30
    echo ""
    echo "Grade-run exit=$rc. Full log: $LOGDIR/grade/$agent.log"
  } >> "$FEEDBACK"
}

run_agent() {
  local agent="$1"
  log "START run    $agent"
  cd "$FT_DIR"
  uv run flowtrack research run "$agent" -s "$STOCK" \
    > "$LOGDIR/run/$agent.log" 2>&1
  local rc=$?
  log "DONE  run    $agent (rc=$rc)"

  if [ $rc -eq 0 ]; then
    # Fire grading in background (do not wait on Gemini)
    grade_agent "$agent" &
  else
    log "SKIP  grade  $agent (run failed, rc=$rc)"
    {
      echo ""
      echo "---"
      echo "## Agent: $agent — $(stamp)"
      echo ""
      echo "AGENT RUN FAILED (rc=$rc). Skipping grade."
      echo "Run log: $LOGDIR/run/$agent.log"
    } >> "$FEEDBACK"
  fi
}

# Run agents 2 at a time
i=0
while [ $i -lt ${#AGENTS[@]} ]; do
  a1="${AGENTS[$i]}"
  a2="${AGENTS[$((i+1))]:-}"

  if [ -n "$a2" ]; then
    log "BATCH        $a1 + $a2"
    run_agent "$a1" &
    PID1=$!
    run_agent "$a2" &
    PID2=$!
    wait $PID1
    wait $PID2
  else
    log "BATCH        $a1 (single)"
    run_agent "$a1"
  fi

  i=$((i+2))
done

log "All agent runs complete — waiting for background grading to finish"
wait
log "PIPELINE COMPLETE"

# Summary tail
{
  echo ""
  echo "---"
  echo "Pipeline complete: $(stamp)"
  echo "Log dir: $LOGDIR"
} >> "$FEEDBACK"

echo ""
echo "=============================================="
echo "PIPELINE DONE — $SECTOR ($STOCK)"
echo "Feedback: $FEEDBACK"
echo "=============================================="
