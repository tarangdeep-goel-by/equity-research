#!/usr/bin/env bash
# eval_parallel.sh — DEFAULT eval process: run a parallel, resumable worker pool.
#
# Seeds a shared work-queue with the given sectors, opens a fresh (uniquely-named)
# tmux session, and starts N self-balancing workers against it. A worker that
# finishes a sector grabs the next pending one, so throughput scales with N and no
# report is ever lost to a kill (claims are atomic + resumable; see eval_queue.sh).
#
# Usage:
#   scripts/eval_parallel.sh <N_workers> <sector1,sector2,...>
#
# Examples:
#   scripts/eval_parallel.sh 3 textiles,building_materials,packaging,media,hospitality,logistics
#   AGENTS=sector,valuation scripts/eval_parallel.sh 2 metals,fmcg     # scope specialists
#   SKIP_RUN=1              scripts/eval_parallel.sh 4 bfsi,telecom    # grade existing reports
#
# Env passthrough (optional): AGENTS, SKIP_RUN, STALE_MIN (see eval_queue.sh).
#
# Monitor:   tmux attach -t <session printed below>   ·   ls <QDIR>/done
set -euo pipefail

N="${1:?usage: eval_parallel.sh <N_workers> <comma_sectors>}"
SECTORS="${2:?usage: eval_parallel.sh <N_workers> <comma_sectors>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # flow-tracker/
cd "$HERE"

TS="$(date +%Y%m%dT%H%M%S)"
QDIR="run_logs/evalq_${TS}"
SESSION="eval_${TS}"                                       # unique → never collides
mkdir -p "$QDIR/pending" flowtracker/research/autoeval/eval_history
IFS=',' read -r -a SECS <<< "$SECTORS"
for s in "${SECS[@]}"; do touch "$QDIR/pending/$s"; done

# cap workers at sector count (more workers than sectors just idle)
[ "$N" -gt "${#SECS[@]}" ] && N="${#SECS[@]}"

# env to carry into each worker
PASS="QDIR=$QDIR${AGENTS:+ AGENTS=$AGENTS}${SKIP_RUN:+ SKIP_RUN=$SKIP_RUN}${STALE_MIN:+ STALE_MIN=$STALE_MIN}"

tmux new-session -d -s "$SESSION" -n w1 "cd $HERE && $PASS WORKER=w1 bash scripts/eval_queue.sh; exec bash"
for ((i=2; i<=N; i++)); do
  tmux new-window -t "$SESSION" -n "w$i" "cd $HERE && $PASS WORKER=w$i bash scripts/eval_queue.sh; exec bash"
done

echo "launched $N workers over ${#SECS[@]} sectors: ${SECS[*]}"
echo "  session : tmux attach -t $SESSION"
echo "  queue   : $QDIR"
echo "  done    : ls $QDIR/done   ·   logs: $QDIR/logs/<sector>.log"
