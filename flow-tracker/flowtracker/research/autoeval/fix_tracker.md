# Fix Tracker — All Recommended Fixes Across Evals

Structured log of every fix recommended by Gemini across all evals. Tracks status: pending, applied, reverted, skipped.

## Format

| ID | Agent | Sector | Stock | Cycle | Type | Section | Issue | Suggestion | Status | Applied In | Result |
|----|-------|--------|-------|-------|------|---------|-------|------------|--------|------------|--------|

## Fixes

<!-- Appended by the orchestrator after each eval. Newest at bottom. -->
| 1 | business | bfsi | SBIN | 1 | PROMPT_FIX | Financial Fingerprint / Peer Benchmarking | The agent failed to use the `render_chart` tool to visualize the dramatic 10-year PAT recovery or peer comparisons, relying entirely on markdown table | Update the system prompt to explicitly mandate the use of `render_chart` for 10-year historical trends (e.g., 'roce_trend', 'revenue_profit') and peer | pending | | |
| 2 | business | bfsi | SBIN | 1 | PROMPT_FIX | Global/Execution | The agent did not call `save_business_profile` to store the generated business model and moat analysis for future use. | Add a strict instruction to always call `save_business_profile` upon completing a business understanding report to ensure knowledge retention. | pending | | |
| 3 | business | it_services | TCS | 1 | PROMPT_FIX | Throughout (Financials, Peer Benchmarking) | The agent completely ignored the `render_chart` tool despite having rich 10-year financial and peer data that would benefit from visualization. | Update the system prompt to explicitly mandate the use of `render_chart` for 10-year financial trends, margin trajectories, and peer comparisons. | pending | | |
| 4 | business | it_services | TCS | 1 | DATA_FIX | Tool Execution / Data Sources | The `calculate` and `save_business_profile` tools failed with a 'Stream closed' error. | Investigate the MCP server connection, timeout settings, or payload size limits causing the 'Stream closed' error for these specific tools. | pending | | |
| 5 | business | it_services | TCS | 1 | DATA_FIX | Data Sources / Open Questions | Concall extraction was not available for TCS, leaving a gap in management commentary regarding AI deal pipelines. | Ensure the concall ingestion pipeline is running and populated for mega-cap stocks like TCS. | pending | | |
| 6 | business | metals | VEDL | 1 | PROMPT_FIX | Data Sources / Throughout | The agent noted that the `calculate` tool failed ('Stream closed') and proceeded to do manual math. While the math was accurate, the agent should be i | Update system prompt: 'If a tool call fails (e.g., Stream closed), you MUST retry the call at least once before falling back to manual work or skippin | pending | | |
| 7 | business | metals | VEDL | 1 | PROMPT_FIX | Visuals / Formatting | The agent did not call the `render_chart` tool to generate visual aids (e.g., 10-year revenue/profit, ROCE trends, or SOTP pie chart), which are highl | Add an explicit instruction in the prompt requiring the use of `render_chart` for financial trend analysis and peer comparisons. | pending | | |
| 8 | business | platform | ETERNAL | 1 | PROMPT_FIX | Throughout | The agent did not call the `render_chart` tool to visualize key trends (e.g., revenue mix, margin inflection, peer comparisons) despite it being avail | Update the system prompt to explicitly require the generation of 2-3 relevant charts using the `render_chart` tool to enhance the visual quality of th | pending | | |
| 9 | business | platform | ETERNAL | 1 | DATA_FIX | Data Sources / Calculations | The `calculate` tool failed with a 'stream closed' error, forcing the agent to do manual arithmetic. | Investigate the MCP tool server connection, timeout settings, or payload limits for the calculate tool to ensure stable execution. | pending | | |
| 10 | business | bfsi | SBIN | 2 | PROMPT_FIX | General / Financial Fingerprint | The agent had access to the 'render_chart' tool but never called it. A report detailing a massive 10-year turnaround (NPA crisis to record profits) he | Update the system prompt to explicitly require the use of 'render_chart' for visualizing long-term P&L trends, asset quality improvements, or DuPont a | pending | | |
| 11 | business | bfsi | SBIN | 2 | DATA_FIX | Note / Throughout | The 'mcp__business__calculate' tool failed repeatedly (stream closed), forcing the agent to perform manual calculations. | Investigate the MCP server hosting the calculate tool for timeout issues, connection stability, or payload size limits that cause stream closures. | pending | | |
