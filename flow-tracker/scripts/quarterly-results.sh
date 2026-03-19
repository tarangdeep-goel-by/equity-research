#!/bin/bash
# Quarterly results fetch for all watchlist stocks
# Schedule: 20th of Feb/May/Aug/Nov at 9:00 AM IST (3:30 AM UTC)
cd "$(dirname "$0")/.." && uv run python -m flowtracker fund fetch --quarters-only >> ~/.local/share/flowtracker/cron.log 2>&1
