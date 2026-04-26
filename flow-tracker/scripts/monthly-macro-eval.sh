#!/bin/bash
# Monthly macro autoeval — rolling window over last 3 dates in
# eval_matrix_macro.yaml. Logs to monthly-macro-eval-YYYY-MM.log
# (one per month, append-newest). Alert marker on non-zero exit.
set -o pipefail
PROJECT="$HOME/Documents/Projects/equity-research/flow-tracker"
LOG_DIR="$HOME/.local/share/flowtracker/logs"
ALERT_DIR="$HOME/.local/share/flowtracker/alerts"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
UV="$HOME/.local/bin/uv"
MATRIX="flowtracker/research/autoeval/eval_matrix_macro.yaml"
mkdir -p "$LOG_DIR" "$ALERT_DIR"
LOG="$LOG_DIR/monthly-macro-eval-$(date +%Y-%m).log"
cleanup() {
    rc=$?
    if [ $rc -ne 0 ]; then
        { date -u +"%Y-%m-%dT%H:%M:%SZ"; echo "$SCRIPT_NAME: exit=$rc";
          echo "--- last 20 lines of $LOG ---"; tail -n 20 "$LOG" 2>/dev/null || true;
        } > "$ALERT_DIR/${SCRIPT_NAME%.sh}.failed"
    fi
}
trap cleanup EXIT
echo "=== $(date) === Monthly Macro Eval ===" >> "$LOG"
cd "$PROJECT" || { echo "FAIL: cd $PROJECT" >> "$LOG"; exit 1; }
DATES=$(python3 -c "import yaml; d=yaml.safe_load(open('$MATRIX'))['eval_dates']; print(','.join(e['date'] for e in d[-3:]))") \
    || { echo "FAIL: resolve dates" >> "$LOG"; exit 1; }
echo "Rolling window: $DATES" >> "$LOG"
$UV run flowtrack research autoeval-macro --dates "$DATES" >> "$LOG" 2>&1
echo "=== $(date) === Macro eval complete ===" >> "$LOG"
