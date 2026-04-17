#!/usr/bin/env bash
# eval-rerun-crashes.sh — rerun agents whose reports crashed or came in too small.
# Scan the autoeval results.tsv + the run logs for SDK crashes, then queue reruns.

set -u

MASTER_DIR="$(for d in /tmp/eval-master-*/; do [ -d "$d" ] && echo "$d"; done | sort -r | head -1 | sed 's|/$||')"
FT_DIR="/Users/tarang/Documents/Projects/equity-research/flow-tracker"

if [ -z "$MASTER_DIR" ]; then
  echo "No master dir found"
  exit 1
fi

echo "Scanning $MASTER_DIR for agent crashes..."
echo ""

# Look for "Fatal error in message reader" or small reports
CRASHES=()
for log in "$MASTER_DIR"/*/run/*.log; do
  [ -f "$log" ] || continue
  sector=$(basename "$(dirname "$(dirname "$log")")")
  agent=$(basename "$log" .log)

  # Two crash signals: SDK fatal error, or report too short
  sdk_crash=$(grep -c "Fatal error in message reader" "$log" 2>/dev/null || echo 0)

  stock=$(grep -oE "for '$agent' [A-Z]+" "$log" 2>/dev/null | head -1 | awk '{print $3}' | tr -d "'")
  [ -z "$stock" ] && stock="(unknown)"
  report="$HOME/vault/stocks/$stock/reports/$agent.md"
  report_size=$(wc -c < "$report" 2>/dev/null || echo 0)

  if [ "$sdk_crash" -gt 0 ] || { [ "$report_size" -gt 0 ] && [ "$report_size" -lt 5000 ]; }; then
    printf "  CRASH  %-18s %-12s stock=%-10s sdk_crash=%s report_size=%s\n" \
      "$sector" "$agent" "$stock" "$sdk_crash" "$report_size"
    CRASHES+=("$sector:$stock:$agent")
  fi
done

echo ""
echo "Crashes found: ${#CRASHES[@]}"
if [ ${#CRASHES[@]} -eq 0 ]; then
  echo "Nothing to rerun."
  exit 0
fi

if [ "${1:-}" != "--execute" ]; then
  echo ""
  echo "Dry run. Pass --execute to rerun these."
  exit 0
fi

# Rerun: do each sequentially to avoid compounding rate-limit pressure during recovery
for entry in "${CRASHES[@]}"; do
  IFS=':' read -r sector stock agent <<< "$entry"
  echo ""
  echo "=== RERUN $sector/$stock/$agent ==="
  cd "$FT_DIR"
  uv run flowtrack research run "$agent" -s "$stock"
  # Grade immediately since we're doing one at a time
  uv run flowtrack research autoeval -a "$agent" --sectors "$sector" --skip-run
done

echo ""
echo "Rerun complete."
