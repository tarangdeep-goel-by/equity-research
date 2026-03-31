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


async def _run_business_agent(symbol: str, model: str | None = None) -> str:
    """Run the business profile agent — lightweight, qualitative only."""
    from flowtracker.research.prompts import BUSINESS_SYSTEM_PROMPT
    from flowtracker.research.tools import BUSINESS_TOOLS

    server = create_sdk_mcp_server("business-data", tools=BUSINESS_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=BUSINESS_SYSTEM_PROMPT,
        mcp_servers={"business": server},
        max_turns=25,
        permission_mode="bypassPermissions",
        model=model,
    )

    report = ""
    async for message in query(
        prompt=f"Research and write a business profile for {symbol}. Explain what the company does, how it makes money, its competitive position, and key risks. Use web search if the stored data is thin.",
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


def _render_mermaid_to_html(markdown: str, output_dir: Path) -> str:
    """Convert markdown to HTML with mermaid.js CDN for diagram rendering."""
    return _wrap_html_with_mermaid_js(markdown)


def _md_to_html(md_content: str) -> str:
    """Convert markdown to HTML using the markdown library. Handles tables, code blocks, etc."""
    import markdown as _md
    return _md.markdown(md_content, extensions=["tables", "fenced_code", "codehilite"])


def _wrap_html(content: str) -> str:
    """Wrap markdown+SVG content in a styled HTML document.

    Content may contain a mix of raw SVG (from mmdc) and markdown.
    We split on SVGs, convert markdown parts, then reassemble.
    """
    import re
    # Split content into markdown chunks and SVG chunks
    parts = re.split(r"(<svg[\s\S]*?</svg>)", content)
    html_parts = []
    for part in parts:
        if part.strip().startswith("<svg"):
            html_parts.append(f'<div class="diagram">{part}</div>')
        else:
            html_parts.append(_md_to_html(part))
    return _HTML_TEMPLATE.replace("{{CONTENT}}", "\n".join(html_parts))


def _wrap_html_with_mermaid_js(markdown: str) -> str:
    """Wrap markdown in HTML with mermaid.js CDN for client-side rendering."""
    import re
    # Extract mermaid blocks before markdown conversion (fenced_code would escape them)
    mermaid_placeholder = []
    def _replace_mermaid(m):
        idx = len(mermaid_placeholder)
        mermaid_placeholder.append(m.group(1))
        return f"MERMAID_PLACEHOLDER_{idx}"

    md = re.sub(r"```mermaid\n(.*?)```", _replace_mermaid, markdown, flags=re.DOTALL)
    html = _md_to_html(md)

    # Replace placeholders with mermaid divs
    for idx, code in enumerate(mermaid_placeholder):
        html = html.replace(
            f"MERMAID_PLACEHOLDER_{idx}",
            f'<pre class="mermaid">{code}</pre>',
        )

    template = _HTML_TEMPLATE.replace("</head>",
        '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>\n'
        '<script>mermaid.initialize({startOnLoad:true, theme:"dark"});</script>\n</head>')
    return template.replace("{{CONTENT}}", html)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Business Profile</title>
<style>
  :root { --bg: #1a1a2e; --surface: #16213e; --text: #e8e8e8; --muted: #8b8b9e;
          --accent: #e94560; --accent2: #0f3460; --green: #4ecca3; --border: #2a2a4a; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, system-ui, sans-serif; background: var(--bg);
         color: var(--text); line-height: 1.7; padding: 2rem; max-width: 900px; margin: 0 auto; }
  h1 { font-size: 2rem; color: #fff; margin: 1.5rem 0 0.5rem; border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; }
  h2 { font-size: 1.5rem; color: var(--green); margin: 2rem 0 0.8rem; }
  h3 { font-size: 1.15rem; color: var(--accent); margin: 1.2rem 0 0.5rem; }
  p, li { margin-bottom: 0.5rem; }
  strong { color: #fff; }
  blockquote { border-left: 4px solid var(--accent); padding: 0.5rem 1rem; margin: 1rem 0;
               background: var(--surface); border-radius: 0 8px 8px 0; color: var(--muted); font-style: italic; }
  li { margin-left: 1.5rem; }
  svg { max-width: 100%; height: auto; margin: 1.5rem 0; display: block;
        background: var(--surface); border-radius: 12px; padding: 1rem; border: 1px solid var(--border); }
  pre.mermaid { background: var(--surface); border-radius: 12px; padding: 1.5rem; border: 1px solid var(--border); margin: 1.5rem 0; }
  table { width: 100%; border-collapse: collapse; margin: 1.2rem 0; }
  th { background: var(--accent2); color: #fff; text-align: left; padding: 0.6rem 1rem; border: 1px solid var(--border); }
  td { padding: 0.5rem 1rem; border: 1px solid var(--border); }
  tr:nth-child(even) { background: rgba(255,255,255,0.03); }
  code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  pre { background: var(--surface); padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 1rem 0; border: 1px solid var(--border); }
  .diagram { margin: 1.5rem 0; text-align: center; }
  .container { background: var(--surface); border-radius: 16px; padding: 2.5rem; margin-top: 1rem;
               border: 1px solid var(--border); box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
</style>
</head>
<body>
<div class="container">
{{CONTENT}}
</div>
</body>
</html>
"""


def generate_business_profile(symbol: str, model: str | None = None) -> Path:
    """Generate a business profile for a stock. Returns path to HTML report."""
    symbol = symbol.upper()

    report = asyncio.run(_run_business_agent(symbol, model))

    if not report.strip():
        raise RuntimeError(f"Agent returned empty business profile for {symbol}")

    # Save raw markdown to vault
    profile_dir = _VAULT_BASE / symbol
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.md"
    profile_path.write_text(report)

    # Render HTML with mermaid diagrams
    html = _render_mermaid_to_html(report, profile_dir)
    html_path = _REPORTS_DIR / f"{symbol.lower()}-business.html"
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)

    return html_path
