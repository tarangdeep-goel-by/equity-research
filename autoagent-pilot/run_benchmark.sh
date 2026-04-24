#!/usr/bin/env bash
# run_benchmark.sh — run <agent> on all benchmark stocks, aggregate scores
#
# Usage:
#   ./run_benchmark.sh [--agent business|financials|...] [--description "text"]
#
# Invoked by the meta-agent after each harness edit. Writes one row to
# results.tsv (via score.py) plus per-stock logs under /tmp/autoagent-pilot-<ts>/.

set -u

usage() {
  cat <<'EOF'
Usage: run_benchmark.sh [--agent <name>] [--description "<text>"]
       run_benchmark.sh --help

Runs <agent> (default: business) on all 16 benchmark stocks (4-wide parallel),
aggregates via score.py, and appends one row to results.tsv.

Valid agents: business financials ownership valuation risk technical sector macro

Cost: ~$6-10 per run. Duration: ~25-35 minutes.
EOF
}

PILOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$PILOT_DIR/.." && pwd)"
EVAL="$WORKSPACE/scripts/eval-pipeline.sh"
BENCH="$PILOT_DIR/benchmark.json"

AGENT="business"
DESC=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --agent) AGENT="${2:?--agent needs a value}"; shift 2 ;;
    --description) DESC="${2:-}"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; usage; exit 2 ;;
  esac
done

TS=$(date +%Y%m%d-%H%M%S)
SINCE_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOGDIR="/tmp/autoagent-pilot-$TS"
mkdir -p "$LOGDIR"

COMMIT=$(git -C "$WORKSPACE" rev-parse --short HEAD)

echo "[$(date '+%H:%M:%S')] benchmark start  agent=$AGENT  commit=$COMMIT  since=$SINCE_TS  logdir=$LOGDIR"

# Parse benchmark.json into "matrix_key stock sector_skill" triples
PAIRS=$(python3 -c "
import json, sys
b = json.load(open('$BENCH'))
for cell in b['cells']:
    for p in cell['pairs']:
        print(f\"{p['eval_matrix_key']} {p['stock']} {cell['sector_skill']}\")
")

# Run 4-wide parallel across stocks. Each invocation runs business agent +
# Gemini grading (eval-pipeline.sh internals), writing to eval_history/.
export PILOT_LOGDIR="$LOGDIR"
export EVAL

# 4-wide concurrency via xargs -P (portable to bash 3.2 on macOS — `wait -n`
# was added in bash 4.3 and is not available on /bin/bash here).
# Each xargs worker gets one line "matrix_key stock sector_skill" and invokes
# eval-pipeline.sh for that stock. stderr/stdout lands in per-stock logs.
export PILOT_LOGDIR EVAL AGENT
echo "$PAIRS" | xargs -n 3 -P 4 bash -c '
  set -u
  matrix_key="$1"
  stock="$2"
  sector_skill="$3"
  outlog="$PILOT_LOGDIR/$stock.log"
  echo "[$(date "+%H:%M:%S")] START  $stock ($matrix_key) agent=$AGENT"
  EVAL_LOGDIR="$PILOT_LOGDIR/evalpipe-$stock" "$EVAL" "$matrix_key" "$stock" "$AGENT" >"$outlog" 2>&1
  echo "[$(date "+%H:%M:%S")] DONE   $stock (rc=$?)"
' _

echo "[$(date '+%H:%M:%S')] all stocks complete — aggregating"

# Aggregate: append results.tsv row + emit diagnosis JSON
python3 "$PILOT_DIR/score.py" \
  --benchmark "$BENCH" \
  --since-ts "$SINCE_TS" \
  --commit "$COMMIT" \
  --agent "$AGENT" \
  --description "$DESC" \
  --tsv "$PILOT_DIR/results.tsv" \
  --diagnose-json "$LOGDIR/diagnosis.json"

echo "[$(date '+%H:%M:%S')] benchmark complete"
echo "  diagnosis: $LOGDIR/diagnosis.json"
echo "  per-stock logs: $LOGDIR/*.log"
echo "  results.tsv: $PILOT_DIR/results.tsv"
