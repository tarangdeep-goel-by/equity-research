#!/usr/bin/env bash
# Resumable, parallel eval work-queue — THE DEFAULT eval process.
#
# Prefer the one-command launcher: `scripts/eval_parallel.sh <N_workers> <sectors>`
# (it seeds the queue + opens a fresh tmux session + starts N workers). This file
# is the per-worker loop it runs; use it directly only to add a worker to a live
# queue or to script a custom setup.
#
# A shared queue dir holds one file per sector. Each WORKER atomically claims an
# unclaimed+unfinished sector (mkdir is atomic), runs the autoeval for it, marks
# it done, and loops. Scale throughput by starting MORE workers against the same
# queue; they self-balance (a worker that finishes early grabs the next pending
# sector instead of idling). Fully resumable: a restart skips `done/` sectors and
# re-claims stale claims (claimed but no done-marker and no live lock).
#
# Env knobs (all optional):
#   AGENTS=sector,valuation   → pass --agents to scope which specialists run
#   SKIP_RUN=1                → grade existing reports (--skip-run), no regeneration
#   STALE_MIN=90              → minutes before a dead worker's claim is reclaimable
#
# Manual setup (if not using eval_parallel.sh):
#   QDIR=run_logs/evalq_$(date +%Y%m%dT%H%M%S)
#   mkdir -p "$QDIR/pending"; for s in pharma fmcg metals; do touch "$QDIR/pending/$s"; done
#   for i in 1 2 3; do tmux new-window -t <session> -n w$i \
#     "cd $(pwd) && QDIR=$QDIR WORKER=w$i bash scripts/eval_queue.sh; exec bash"; done
#
# Add a worker later WITHOUT touching the others — just start another with the same QDIR.
# Progress:  ls $QDIR/done  (completed)  ;  ls $QDIR/claimed  (in-flight)
set -u

QDIR="${QDIR:?set QDIR=<queue dir>}"
WORKER="${WORKER:-w0}"
PEND="$QDIR/pending"; CLAIM="$QDIR/claimed"; DONE="$QDIR/done"; LOGD="$QDIR/logs"
mkdir -p "$PEND" "$CLAIM" "$DONE" "$LOGD"
STALE_MIN="${STALE_MIN:-90}"   # reclaim a claim older than this many minutes with no done-marker

log() { echo "[$WORKER $(date +%H:%M:%S)] $*"; }

claim_one() {
  local f s
  for f in "$PEND"/*; do
    [ -e "$f" ] || continue
    s=$(basename "$f")
    [ -e "$DONE/$s" ] && continue                      # already finished
    if mkdir "$CLAIM/$s" 2>/dev/null; then             # atomic first-claim
      echo "$s"; return 0
    fi
    # claimed by someone — reclaim only if stale (crashed worker) and not done
    if [ -z "$(find "$CLAIM/$s" -maxdepth 0 -mmin -"$STALE_MIN" 2>/dev/null)" ] && [ ! -e "$DONE/$s" ]; then
      touch "$CLAIM/$s"                                # take over the stale claim
      echo "$s"; return 0
    fi
  done
  return 1
}

log "worker up. queue=$QDIR"
while :; do
  sector="$(claim_one)" || { log "no more claimable work — exiting"; break; }
  log ">>> running $sector"
  EXTRA=""
  [ -n "${AGENTS:-}" ] && EXTRA="$EXTRA --agents $AGENTS"
  [ -n "${SKIP_RUN:-}" ] && EXTRA="$EXTRA --skip-run"
  if uv run flowtrack research autoeval -s "$sector" $EXTRA > "$LOGD/${sector}.log" 2>&1; then
    touch "$DONE/$sector"; log "<<< done $sector"
  else
    log "!!! autoeval exited non-zero for $sector — releasing claim for retry"
    rmdir "$CLAIM/$sector" 2>/dev/null || rm -rf "$CLAIM/$sector"
  fi
done
