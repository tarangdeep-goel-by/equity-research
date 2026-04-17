#!/usr/bin/env bash
# eval-progress.sh — show current state of the autonomous eval pipeline

set -u

MASTER_DIR="$(for d in /tmp/eval-master-*/; do [ -d "$d" ] && echo "$d"; done | sort -r | head -1 | sed 's|/$||')"
if [ -z "$MASTER_DIR" ]; then
  echo "No master dir found in /tmp/eval-master-*"
  exit 1
fi

echo "=================================================="
echo "  EVAL PIPELINE PROGRESS — $MASTER_DIR"
echo "=================================================="
echo ""

# Caffeinate status
if pmset -g assertions 2>/dev/null | grep -q "PreventSystemSleep *1"; then
  echo "  Sleep prevention: ACTIVE"
else
  echo "  Sleep prevention: INACTIVE (laptop may sleep!)"
fi
echo ""

# tmux sessions
echo "  tmux sessions:"
tmux ls 2>/dev/null | sed 's/^/    /'
echo ""

# Currently running processes
echo "  Running agents:"
ps -ef | grep -E 'flowtrack research run|autoeval' | grep -v grep | \
  awk '{for(i=9;i<=NF;i++) printf "%s ", $i; print ""}' | head -5 | sed 's/^/    /'
echo ""

# Master log tail
echo "  Master log (tail 12):"
tail -12 "$MASTER_DIR/master.log" 2>/dev/null | sed 's/^/    /'
echo ""

# Sector completion
echo "  Sector status:"
for sector in bfsi private_bank it_services pharma real_estate regulated_power metals telecom fmcg conglomerate platform insurance auto chemicals broker; do
  sdir="$MASTER_DIR/$sector"
  if [ -d "$sdir" ]; then
    runs_done=$(ls "$sdir/run/"*.log 2>/dev/null | wc -l | tr -d ' ')
    grades_done=$(ls "$sdir/grade/"*.log 2>/dev/null | wc -l | tr -d ' ')
    fb_lines=$(wc -l < "$sdir/feedback/FEEDBACK.md" 2>/dev/null | tr -d ' ')
    printf "    %-18s runs=%s/7 grades=%s/7 fb_lines=%s\n" "$sector" "$runs_done" "$grades_done" "$fb_lines"
  fi
done
echo ""

# Rate-limit detection in recent logs
echo "  Recent rate-limit warnings (last 24h, last 10):"
find "$MASTER_DIR" -name '*.log' -mtime -1 -exec grep -H -l "rate limit" {} \; 2>/dev/null | head -10 | sed 's/^/    /'
echo ""

echo "  Key files:"
echo "    master log:       $MASTER_DIR/master.log"
echo "    aggregate feedback: $MASTER_DIR/ALL_FEEDBACK.md"
echo ""
echo "  Watch live:         tmux attach -t eval-master"
echo "  Watch grades:       tail -f $MASTER_DIR/*/grade/*.log"
