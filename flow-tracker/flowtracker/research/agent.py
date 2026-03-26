"""Multi-turn research agent using Claude Agent SDK with MCP tools."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    create_sdk_mcp_server,
    query,
)


_VAULT_BASE = Path.home() / "vault" / "stocks"
_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


async def _run_agent(symbol: str, model: str | None = None) -> str:
    """Run the research agent and return the Markdown report."""
    from flowtracker.research.prompts import RESEARCH_SYSTEM_PROMPT
    from flowtracker.research.tools import RESEARCH_TOOLS

    server = create_sdk_mcp_server("research-data", tools=RESEARCH_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        mcp_servers={"research": server},
        max_turns=30,
        permission_mode="bypassPermissions",
        model=model,
    )

    report = ""
    async for message in query(
        prompt=f"Generate a comprehensive equity research thesis for {symbol}. Pull all available data, cross-reference signals, and produce the full Markdown report.",
        options=options,
    ):
        if isinstance(message, ResultMessage):
            report = message.result or ""

    return report


def generate_thesis(symbol: str, model: str | None = None) -> Path:
    """Generate a research thesis for a stock symbol. Returns path to .md file."""
    symbol = symbol.upper()
    today = date.today().isoformat()

    report = asyncio.run(_run_agent(symbol, model))

    if not report.strip():
        raise RuntimeError(f"Agent returned empty report for {symbol}")

    # Save to vault
    vault_dir = _VAULT_BASE / symbol / "thesis"
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / f"{today}.md"
    vault_path.write_text(report)

    # Save to reports/
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports_path = _REPORTS_DIR / f"{symbol.lower()}-thesis.md"
    reports_path.write_text(report)

    return vault_path
