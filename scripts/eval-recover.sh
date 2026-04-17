#!/usr/bin/env bash
# eval-recover.sh — find and recover all eval failures:
#   (1) SDK crashes → agent report too small / "Fatal error in message reader" → rerun agent
#   (2) Gemini ERR grades in results.tsv → report OK but grading failed → regrade via --skip-run
#
# Usage: ./eval-recover.sh               # dry-run
#        ./eval-recover.sh --execute     # actually recover

set -u

FT_DIR="/Users/tarang/Documents/Projects/equity-research/flow-tracker"
RESULTS="$FT_DIR/flowtracker/research/autoeval/results.tsv"
EXECUTE=0
[ "${1:-}" = "--execute" ] && EXECUTE=1

# -----------------------------------------------------------------------------
# (1) Scan results.tsv for ERR (Gemini-failed grades) — latest attempt per (agent, sector)
# -----------------------------------------------------------------------------
echo "=== Gemini ERR grades needing regrade ==="
declare -a ERR_LIST
# Keep only the LATEST line per (agent, sector) — earlier attempts may be ERR, later may be graded
awk -F'\t' 'NR>1 { key=$3"|"$4"|"$5; latest[key]=$0 } END { for (k in latest) print latest[k] }' "$RESULTS" 2>/dev/null \
  | awk -F'\t' '$6 == "ERR" { printf "  ERR   %s (stock=%s, sector=%s) — %s\n", $3, $4, $5, substr($NF, 1, 80) }' \
  | tee /tmp/eval-err-list.txt
ERR_COUNT=$(wc -l < /tmp/eval-err-list.txt | tr -d ' ')
echo "  Total: $ERR_COUNT ERR entries"
echo ""

# -----------------------------------------------------------------------------
# (2) Scan master dir for SDK crashes (agent report too small)
# -----------------------------------------------------------------------------
echo "=== SDK crashes (agent report too small) ==="
MASTER_DIR="$(for d in /tmp/eval-master-*/; do [ -d "$d" ] && echo "$d"; done | sort -r | head -1 | sed 's|/$||')"
declare -a CRASH_LIST
if [ -n "$MASTER_DIR" ]; then
  # For each sector dir in master, examine runs
  for sector_dir in "$MASTER_DIR"/*/; do
    sector=$(basename "$sector_dir")
    [ -d "$sector_dir/run" ] || continue
    for log in "$sector_dir/run/"*.log; do
      [ -f "$log" ] || continue
      agent=$(basename "$log" .log)
      sdk_crash=$(grep -c "Fatal error in message reader" "$log" 2>/dev/null || echo 0)

      # Stock from eval_matrix
      case "$sector" in
        bfsi) stock=SBIN ;;
        private_bank) stock=HDFCBANK ;;
        it_services) stock=TCS ;;
        metals) stock=VEDL ;;
        platform) stock=ETERNAL ;;
        conglomerate) stock=ADANIENT ;;
        telecom) stock=BHARTIARTL ;;
        real_estate) stock=GODREJPROP ;;
        pharma) stock=SUNPHARMA ;;
        regulated_power) stock=NTPC ;;
        insurance) stock=POLICYBZR ;;
        broker) stock=GROWW ;;
        auto) stock=OLAELEC ;;
        chemicals) stock=PIDILITIND ;;
        fmcg) stock=HINDUNILVR ;;
        *) continue ;;
      esac

      report="$HOME/vault/stocks/$stock/reports/$agent.md"
      [ -f "$report" ] || continue
      report_size=$(wc -c < "$report" 2>/dev/null | tr -d ' ')

      if [ "$sdk_crash" -gt 0 ] && [ "$report_size" -lt 5000 ]; then
        printf "  CRASH %s (stock=%s, sector=%s, size=%s bytes)\n" "$agent" "$stock" "$sector" "$report_size"
        echo "$sector|$stock|$agent" >> /tmp/eval-crash-list.txt
      fi
    done
  done
  CRASH_COUNT=$(wc -l < /tmp/eval-crash-list.txt 2>/dev/null | tr -d ' ')
  CRASH_COUNT="${CRASH_COUNT:-0}"
  echo "  Total: $CRASH_COUNT crashes"
else
  echo "  No master dir found."
  CRASH_COUNT=0
fi
echo ""

if [ "$EXECUTE" -ne 1 ]; then
  echo "Dry run. Pass --execute to rerun agents (for crashes) and regrade (for ERRs)."
  rm -f /tmp/eval-crash-list.txt
  exit 0
fi

# -----------------------------------------------------------------------------
# Execute crash reruns (agent + regrade)
# -----------------------------------------------------------------------------
if [ -f /tmp/eval-crash-list.txt ] && [ -s /tmp/eval-crash-list.txt ]; then
  echo "=== RERUNNING CRASHED AGENTS ==="
  while IFS='|' read -r sector stock agent; do
    echo ""
    echo "--- $sector / $stock / $agent ---"
    cd "$FT_DIR"
    uv run flowtrack research run "$agent" -s "$stock"
    uv run flowtrack research autoeval -a "$agent" --sectors "$sector" --skip-run
  done < /tmp/eval-crash-list.txt
  rm -f /tmp/eval-crash-list.txt
fi

# -----------------------------------------------------------------------------
# Execute ERR regrades (--skip-run only, agent not rerun)
# -----------------------------------------------------------------------------
echo ""
echo "=== REGRADING ERR ENTRIES ==="
awk -F'\t' 'NR>1 { key=$3"|"$4"|"$5; latest[key]=$0 } END { for (k in latest) print latest[k] }' "$RESULTS" \
  | awk -F'\t' -v OFS='|' '$6 == "ERR" { print $5, $3 }' \
  | sort -u \
  | while IFS='|' read -r sector agent; do
      echo "--- $sector / $agent (regrade only) ---"
      cd "$FT_DIR"
      uv run flowtrack research autoeval -a "$agent" --sectors "$sector" --skip-run
    done

echo ""
echo "Recovery complete."
