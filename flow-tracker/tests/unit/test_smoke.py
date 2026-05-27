"""CLI smoke tests — run --help on every command and subcommand.

Verifies that all commands register correctly and don't crash on import.
"""

from __future__ import annotations

import subprocess

import pytest

# fmt: off
HELP_COMMANDS = [
    # Root
    ["--help"],
    ["fetch", "--help"],
    ["summary", "--help"],
    ["flows", "--help"],
    ["streak", "--help"],
    ["backfill", "--help"],

    # fund
    ["fund", "--help"],
    ["fund", "fetch", "--help"],
    ["fund", "show", "--help"],
    ["fund", "history", "--help"],
    ["fund", "peers", "--help"],
    ["fund", "valuation", "--help"],
    ["fund", "backfill", "--help"],
    ["fund", "irdai-backfill", "--help"],
    ["fund", "charts", "--help"],
    ["fund", "peer", "--help"],
    ["fund", "schedules", "--help"],

    # mf (+ nested daily subgroup)
    ["mf", "--help"],
    ["mf", "fetch", "--help"],
    ["mf", "summary", "--help"],
    ["mf", "flows", "--help"],
    ["mf", "aum", "--help"],
    ["mf", "backfill", "--help"],
    ["mf", "daily", "--help"],
    ["mf", "daily", "fetch", "--help"],
    ["mf", "daily", "summary", "--help"],
    ["mf", "daily", "trend", "--help"],

    # holding
    ["holding", "--help"],
    ["holding", "add", "--help"],
    ["holding", "remove", "--help"],
    ["holding", "list", "--help"],
    ["holding", "fetch", "--help"],
    ["holding", "show", "--help"],
    ["holding", "changes", "--help"],
    ["holding", "shareholders", "--help"],

    # scan
    ["scan", "--help"],
    ["scan", "refresh", "--help"],
    ["scan", "refresh-themes", "--help"],
    ["scan", "constituents", "--help"],
    ["scan", "fetch", "--help"],
    ["scan", "deviations", "--help"],
    ["scan", "pledges", "--help"],
    ["scan", "status", "--help"],

    # gold
    ["gold", "--help"],
    ["gold", "fetch", "--help"],
    ["gold", "prices", "--help"],
    ["gold", "etfs", "--help"],
    ["gold", "correlation", "--help"],

    # macro
    ["macro", "--help"],
    ["macro", "fetch", "--help"],
    ["macro", "summary", "--help"],
    ["macro", "trend", "--help"],
    ["macro", "wss-fetch", "--help"],
    ["macro", "wss-summary", "--help"],

    # bhavcopy
    ["bhavcopy", "--help"],
    ["bhavcopy", "fetch", "--help"],
    ["bhavcopy", "backfill", "--help"],
    ["bhavcopy", "top-delivery", "--help"],
    ["bhavcopy", "delivery", "--help"],

    # deals
    ["deals", "--help"],
    ["deals", "fetch", "--help"],
    ["deals", "backfill", "--help"],
    ["deals", "summary", "--help"],
    ["deals", "stock", "--help"],
    ["deals", "top", "--help"],

    # insider
    ["insider", "--help"],
    ["insider", "fetch", "--help"],
    ["insider", "stock", "--help"],
    ["insider", "promoter-buys", "--help"],
    ["insider", "backfill", "--help"],

    # estimates
    ["estimates", "--help"],
    ["estimates", "fetch", "--help"],
    ["estimates", "stock", "--help"],
    ["estimates", "upside", "--help"],
    ["estimates", "surprises", "--help"],

    # fmp
    ["fmp", "--help"],
    ["fmp", "fetch", "--help"],
    ["fmp", "dcf", "--help"],
    ["fmp", "technicals", "--help"],
    ["fmp", "metrics", "--help"],
    ["fmp", "growth", "--help"],
    ["fmp", "grades", "--help"],
    ["fmp", "targets", "--help"],

    # sector
    ["sector", "--help"],
    ["sector", "overview", "--help"],
    ["sector", "detail", "--help"],
    ["sector", "list", "--help"],

    # mfport
    ["mfport", "--help"],
    ["mfport", "fetch", "--help"],
    ["mfport", "stock", "--help"],
    ["mfport", "top-buys", "--help"],
    ["mfport", "top-exits", "--help"],
    ["mfport", "summary", "--help"],

    # screen
    ["screen", "--help"],
    ["screen", "top", "--help"],
    ["screen", "score", "--help"],

    # filings
    ["filings", "--help"],
    ["filings", "fetch", "--help"],
    ["filings", "download", "--help"],
    ["filings", "list", "--help"],
    ["filings", "annual-reports", "--help"],
    ["filings", "open-filing", "--help"],
    ["filings", "extract", "--help"],
    ["filings", "extract-press-release", "--help"],

    # portfolio
    ["portfolio", "--help"],
    ["portfolio", "add", "--help"],
    ["portfolio", "remove", "--help"],
    ["portfolio", "view", "--help"],
    ["portfolio", "concentration", "--help"],
    ["portfolio", "summary", "--help"],

    # alert
    ["alert", "--help"],
    ["alert", "add", "--help"],
    ["alert", "list", "--help"],
    ["alert", "check", "--help"],
    ["alert", "remove", "--help"],
    ["alert", "history", "--help"],

    # research
    ["research", "--help"],
    ["research", "fundamentals", "--help"],
    ["research", "business", "--help"],
    ["research", "thesis", "--help"],
    ["research", "data", "--help"],
    ["research", "thesis-check", "--help"],
    ["research", "thesis-status", "--help"],
    ["research", "run", "--help"],
    ["research", "verify", "--help"],
    ["research", "autoeval-macro", "--help"],
    ["research", "analog-backtest", "--help"],
    ["research", "tool-audit", "--help"],

    # share_count (added 2026-04-29)
    ["share_count", "--help"],
    ["share_count", "check", "--help"],

    # fda (added 2026-04-29)
    ["fda", "--help"],
    ["fda", "fetch", "--help"],
    ["fda", "list", "--help"],

    # adr (added 2026-04-29)
    ["adr", "--help"],
    ["adr", "refresh", "--help"],
    ["adr", "list", "--help"],

    # breadth (added 2026-05-26)
    ["breadth", "--help"],
    ["breadth", "recompute", "--help"],
    ["breadth", "backfill", "--help"],
    ["breadth", "latest", "--help"],
    ["breadth", "trend", "--help"],

    # indexpe (added 2026-05-26)
    ["indexpe", "--help"],
    ["indexpe", "fetch", "--help"],
    ["indexpe", "backfill", "--help"],
    ["indexpe", "current", "--help"],
    ["indexpe", "trend", "--help"],
    ["indexpe", "percentile", "--help"],

    # surveillance (added 2026-05-26)
    ["surveillance", "--help"],
    ["surveillance", "fetch", "--help"],
    ["surveillance", "list", "--help"],
    ["surveillance", "check", "--help"],

    # ipo (added 2026-05-26)
    ["ipo", "--help"],
    ["ipo", "fetch", "--help"],
    ["ipo", "upcoming", "--help"],
    ["ipo", "subscription", "--help"],
    ["ipo", "listings", "--help"],

    # gst (added 2026-05-26)
    ["gst", "--help"],
    ["gst", "fetch", "--help"],
    ["gst", "backfill", "--help"],
    ["gst", "latest", "--help"],
    ["gst", "trend", "--help"],

    # cpi / iip / pmi / yield-curve (added 2026-05-26, feat/macro-expansion)
    ["cpi", "--help"],
    ["cpi", "fetch", "--help"],
    ["cpi", "backfill", "--help"],
    ["cpi", "latest", "--help"],
    ["cpi", "trend", "--help"],
    ["iip", "--help"],
    ["iip", "fetch", "--help"],
    ["iip", "backfill", "--help"],
    ["iip", "latest", "--help"],
    ["iip", "trend", "--help"],
    ["pmi", "--help"],
    ["pmi", "fetch", "--help"],
    ["pmi", "backfill", "--help"],
    ["pmi", "latest", "--help"],
    ["pmi", "trend", "--help"],
    ["yield-curve", "--help"],
    ["yield-curve", "backfill", "--help"],
    ["yield-curve", "curve", "--help"],
    ["yield-curve", "trend", "--help"],

    # mfnav (daily MF scheme NAVs, mfapi.in)
    ["mfnav", "--help"],
    ["mfnav", "fetch", "--help"],
    ["mfnav", "backfill", "--help"],
    ["mfnav", "latest", "--help"],
    ["mfnav", "trend", "--help"],
]
# fmt: on


@pytest.mark.slow
@pytest.mark.parametrize("args", HELP_COMMANDS, ids=lambda a: " ".join(a))
def test_cli_help(args: list[str]) -> None:
    """Every CLI command should respond to --help without errors."""
    result = subprocess.run(
        ["uv", "run", "flowtrack"] + args,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"Failed: flowtrack {' '.join(args)}\nstderr: {result.stderr}"
    )
