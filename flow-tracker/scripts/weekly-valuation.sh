#!/bin/bash
# Weekly valuation snapshot for all watchlist stocks
# Schedule: Every Sunday at 8:00 PM IST (2:30 PM UTC)
cd "$(dirname "$0")/.." && uv run python -m flowtracker fund fetch --valuation-only >> ~/.local/share/flowtracker/cron.log 2>&1
