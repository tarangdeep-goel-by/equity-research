#!/usr/bin/env bash
# eval-restart.sh — restart the master pipeline from a specific sector.
# Use after a crash, reboot, or rate-limit exhaustion.
#
# Usage: ./eval-restart.sh <sector>
# Example: ./eval-restart.sh telecom    # resume from telecom onwards

set -u

START_SECTOR="${1:?sector to restart from required}"

# Kill any stale pipeline processes + old tmux
tmux kill-session -t eval-master 2>/dev/null
pkill -f 'flowtrack research run' 2>/dev/null
pkill -f 'flowtrack research autoeval' 2>/dev/null
sleep 2

# Ensure caffeinate still running
if ! pmset -g assertions 2>/dev/null | grep -q "PreventSystemSleep *1"; then
  echo "[restart] caffeinate inactive — restarting"
  tmux kill-session -t caffeinate 2>/dev/null
  tmux new-session -d -s caffeinate 'caffeinate -i -s -d'
fi

# Start fresh master from specified sector
cd /Users/tarang/Documents/Projects/equity-research
tmux new-session -d -s eval-master -c "$PWD"
tmux send-keys -t eval-master "bash scripts/eval-all-sectors.sh $START_SECTOR 2>&1 | tee /tmp/eval-master-tmux.log" C-m

sleep 3
echo "[restart] master pipeline restarted from $START_SECTOR"
echo ""
tmux capture-pane -t eval-master -p | tail -15
