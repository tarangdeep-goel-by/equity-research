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

# Pre-flight: autoeval deps must be installed, else every grade silently
# errors with "google-genai not installed" (happened once when a sibling
# `uv sync --extra test` evicted the autoeval extra).
if ! (cd "$FT_DIR" && uv run python -c "import google.genai" 2>/dev/null); then
  log "ABORT — autoeval deps missing (google-genai). Run: cd $FT_DIR && uv sync --extra autoeval"
  exit 2
fi

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
  uv run flowtrack research autoeval -a "$agent" --sectors "$SECTOR" --skip-run 2>&1 \
    | tee "$LOGDIR/grade/$agent.log" \
    | awk -v p="[$SECTOR/grade/$agent]" '{print p" "$0; fflush()}'
  local rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ] || grep -qE "^ERROR:|Traceback|ModuleNotFoundError" "$LOGDIR/grade/$agent.log" 2>/dev/null; then
    log "FAIL  grade  $agent (rc=$rc) — head of log below"
    head -5 "$LOGDIR/grade/$agent.log" 2>/dev/null | sed "s/^/    [grade-fail $agent] /" | tee -a "$STATUS"
  else
    log "DONE  grade  $agent (rc=$rc)"
  fi

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
  uv run flowtrack research run "$agent" -s "$STOCK" 2>&1 \
    | tee "$LOGDIR/run/$agent.log" \
    | awk -v p="[$SECTOR/run/$agent]" '{print p" "$0; fflush()}'
  local rc=${PIPESTATUS[0]}
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

# First agent runs alone to populate the Phase 0b docling cache
# (_docling.md + _heading_index.json next to each PDF). Running two agents in
# parallel on a fresh stock duplicates 15-25 min of PDF OCR work; serialising
# the first run lets all subsequent agents hit the cache in Phase 0b.
if [ ${#AGENTS[@]} -gt 0 ]; then
  first="${AGENTS[0]}"
  log "WARM-UP      $first (serial — populates docling cache)"
  run_agent "$first"
fi

# Remaining agents run 2 at a time with warm cache.
i=1
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
