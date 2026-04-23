#!/usr/bin/env bash
# Render flowtracker LaunchAgent plist templates and install them.
#
# Each *.plist.tmpl under scripts/plists/ contains __HOME__ placeholders
# that are substituted with the current user's $HOME, then the rendered
# plist is written to ~/Library/LaunchAgents/ and loaded via launchctl.
#
# Re-running is safe: existing plists are unloaded before reload.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMPL_DIR="$SCRIPT_DIR/plists"
DEST_DIR="$HOME/Library/LaunchAgents"

if [ ! -d "$TMPL_DIR" ]; then
    echo "ERROR: template directory not found: $TMPL_DIR" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

shopt -s nullglob
templates=("$TMPL_DIR"/*.plist.tmpl)
shopt -u nullglob

if [ "${#templates[@]}" -eq 0 ]; then
    echo "ERROR: no *.plist.tmpl files found under $TMPL_DIR" >&2
    exit 1
fi

for tmpl in "${templates[@]}"; do
    base="$(basename "$tmpl" .tmpl)"
    dest="$DEST_DIR/$base"

    # Render: substitute __HOME__ with the runtime $HOME.
    sed "s|__HOME__|$HOME|g" "$tmpl" > "$dest"
    echo "Rendered: $dest"

    # Unload if already registered (ignore errors if not loaded), then load.
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load "$dest"
    echo "Loaded:   $base"
done

echo ""
echo "Registered flowtracker jobs:"
launchctl list | grep flowtracker || echo "  (none — check $DEST_DIR and logs at $HOME/.local/share/flowtracker/cron.log)"
