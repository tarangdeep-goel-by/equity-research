#!/bin/bash
set -e

PLIST_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/.local/share/flowtracker"

PLISTS=(
    "com.flowtracker.daily-fetch"
    "com.flowtracker.mf-monthly"
    "com.flowtracker.holdings-quarterly"
    "com.flowtracker.fund-weekly"
    "com.flowtracker.fund-quarterly"
)

echo "Setting up flowtracker scheduled jobs..."

# 1. Create log directory
mkdir -p "$LOG_DIR"
echo "Log directory: $LOG_DIR"

# 2. Unload existing jobs (ignore errors if not loaded)
for plist in "${PLISTS[@]}"; do
    launchctl unload "$PLIST_DIR/$plist.plist" 2>/dev/null || true
done

# 3. Load all plists
for plist in "${PLISTS[@]}"; do
    if [ ! -f "$PLIST_DIR/$plist.plist" ]; then
        echo "ERROR: $PLIST_DIR/$plist.plist not found"
        exit 1
    fi
    launchctl load "$PLIST_DIR/$plist.plist"
    echo "Loaded: $plist"
done

# 4. Verify
echo ""
echo "Registered jobs:"
launchctl list | grep flowtracker

echo ""
echo "Setup complete. Logs will be written to: $LOG_DIR/cron.log"
echo ""
echo "Schedules:"
echo "  daily-fetch           — Weekdays at 7:00 PM IST"
echo "  mf-monthly            — 6th of every month at 9:00 AM IST"
echo "  holdings-quarterly    — 15th of Jan/Apr/Jul/Oct at 9:00 AM IST"
echo "  fund-weekly          — Sundays at 8:00 PM IST"
echo "  fund-quarterly       — 20th of each month at 9:00 AM IST"
