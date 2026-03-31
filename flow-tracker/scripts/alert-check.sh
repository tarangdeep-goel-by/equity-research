#!/usr/bin/env bash
# Run alert checks after daily fetch
set -euo pipefail
cd "$(dirname "$0")/.."
uv run flowtrack alert check
