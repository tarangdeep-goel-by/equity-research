# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A CLI tool for stock screening, research, and comparison across US and Indian markets. Built on yfinance (no API key needed). Outputs Rich tables to the terminal.

## Commands

```bash
# Run any CLI command (uses uv, no activation needed)
./stock <command> [args]
# or equivalently:
uv run stock <command> [args]

# Examples
./stock info AAPL
./stock fundamentals RELIANCE.NS -p annual -y 6
./stock compare AAPL MSFT GOOGL
./stock screen -e NSE -s Technology --market-cap-gt 1000000000
./stock gainers -l 20
./stock losers
./stock actives

# Install/sync dependencies
uv sync
```

No test suite exists yet. No linter configured.

## Architecture

**Layered CLI app** — 4 modules with clear separation:

```
main.py    → Typer CLI commands (entry point, wiring only)
client.py  → YFinanceClient: all yfinance API calls, 5-min in-memory cache
models.py  → Pydantic models for every data shape (profile, ratios, financials, screener)
display.py → Rich table rendering (one display_* function per command)
utils.py   → Number formatting (fmt_large, fmt_pct, fmt_price) + symbol normalization
```

**Data flow:** `main.py` command → `client.py` fetches data → returns Pydantic models → `display.py` renders Rich tables.

**Key patterns:**
- All Pydantic models use `extra="ignore"` — safe to pass raw API dicts
- `YFinanceClient` caches both `Ticker` objects and `.info` dicts (5-min TTL)
- `_safe_get(df, row, col)` in client.py safely extracts values from yfinance DataFrames
- Indian stocks use `.NS` (NSE) or `.BO` (BSE) suffix — `normalize_symbol()` just uppercases, user must provide suffix
- Screener uses `yf.EquityQuery` for composable filter queries; falls back to predefined screen keys like `"most_actives"`

**deepdives/** — Markdown research notes on individual stocks (e.g., `HAL.NS.md`). Not code.

## Adding a New Command

1. Add Pydantic model(s) in `models.py`
2. Add client method(s) in `client.py` that return the model(s)
3. Add `display_*` function in `display.py`
4. Add `@app.command()` in `main.py` that wires client → display
