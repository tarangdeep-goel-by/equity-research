# Test Coverage — Tier 3 + Structural + Agent Logging Plan

**Date:** 2026-04-16
**Starting point:** 68% line coverage, 1,980 tests (1,861 fast + 119 slow), 2 known-flaky tests, agent observability at trace-level only
**Goal:** 80% line coverage, CI-enforced, branch coverage visible, no flakes, **turn-level agent telemetry that unlocks deeper evals**

---

## Current state (baseline)

| Layer | Cov | Missing | Notes |
|---|---:|---:|---|
| `models/*` | 100% | 0 | Done |
| `core/*` (store, utils) | 82% | 317 | Good |
| `research/*` | 79% | 1,725 | Tier 1+2 done; `agent.py` excluded (715) |
| `research/autoeval` | 53% | 239 | Gemini calls; limited further gain |
| `display/*` | 53% | 639 | Low risk, easy wins |
| `client/*` | 63% | 1,212 | Tier 3 target |
| `commands/*` | **26%** | **1,489** | Tier 3 biggest target |
| **TOTAL** | **68.0%** | **5,621** | |

---

## Scope

Three parallel tracks, independent work:
- **Track A — Test additions** (3 waves, ~900 lines of coverage, +12pp)
- **Track B — Structural** (CI, branch cov, flakes, thresholds)
- **Track C — Agent logging/observability** (source-code changes in agent.py, tools.py, briefing.py; unlocks deeper evals)

Tracks A and C both touch the `research/` codebase but at different files — A writes *tests*, C adds *instrumentation* to agent.py, tools.py, briefing.py. Need coordination but not blocking.

---

## Track A — Test additions

### Wave 3A — Commands layer (highest leverage)

**Target:** 26% → 55% (+500 lines covered, +3pp total)

Existing infrastructure: `typer.testing.CliRunner`, `populated_store` fixture with SBIN/INFY seeded, `monkeypatch.setenv("FLOWTRACKER_DB", ...)` to pin DB. Pattern established in `tests/integration/test_command_wiring.py`.

| File | Cov now | Target | New tests | Priority |
|---|---:|---:|---:|---|
| `portfolio_commands.py` (89 stmts) | 30% | 85% | ~12 | **easy / high value** — pure store+display, no mocks needed; `concentration` and `summary` have real aggregation math |
| `mf_commands.py` (119) | 29% | 70% | ~10 | easy — mock `AMFIClient.fetch_monthly`, test date parsing & storage |
| `holding_commands.py` (118) | 29% | 65% | ~10 | medium — mock NSE holding client, 7 subcommands, simple logic |
| `filing_commands.py` (132) | 19% | 55% | ~8 | medium — 6 subcommands; skip `extract` (async) and `open_filing` (subprocess) |
| `fund_commands.py` (331) | 14% | 50% | ~15 | medium — 9 subcommands; `backfill` + `peers` have real orchestration |
| `research_commands.py` (626) | 7% | 30% | ~12 | hard — cherry-pick `data`, `thesis-status`, `compare`, skip async-heavy `run`/`business` |

**Patterns:**
```python
from typer.testing import CliRunner
from flowtracker.main import app
runner = CliRunner()

def test_portfolio_concentration(tmp_db, populated_store, monkeypatch):
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    result = runner.invoke(app, ["portfolio", "concentration"])
    assert result.exit_code == 0
    assert "Sector" in result.output
```

**Client mocking pattern** (fund, holding, mf, filing):
```python
from unittest.mock import patch, MagicMock

def test_fund_backfill(tmp_db, populated_store, monkeypatch):
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    with patch("flowtracker.fund_commands.ScreenerClient") as mock_sc:
        mock_sc.return_value.__enter__.return_value.fetch_company_page.return_value = {...}
        result = runner.invoke(app, ["fund", "backfill", "-s", "SBIN"])
        assert result.exit_code == 0
```

**Skip (document as untested, not worth the mock weight):**
- `research run` / `research business` — async Claude invocations; quality covered by eval loop
- `research fundamentals` — subprocess `open` + browser launch
- `filing extract` — async Claude extraction
- `filing open_filing` — subprocess `open`

### Wave 3B — Client layer deep paths

**Target:** 63% → 80% (+550 lines, +3.1pp)

| File | Cov now | Target | New tests | Approach |
|---|---:|---:|---:|---|
| `mfportfolio_client.py` (305) | **23%** | 75% | **~15** | **biggest gain** — new file `test_client_mfportfolio_fetch.py`, mock httpx for each of 5 AMC fetchers (SBI, ICICI, PPFAS, QUANT, UTI); real ZIP/XLSX/XLS fixtures |
| `screener_client.py` (850) | 64% | 80% | ~10 | extend — login flow, 403 re-login, retry exhaustion, warehouse-ID regex fallback, growth-rate parsing edge cases |
| `estimates_client.py` (266) | 59% | 80% | ~5 | extend — cache TTL expiry, earning_history fallback, NaN handling |
| `mf_client.py` (177) | 46% | 75% | ~8 | extend — `fetch_monthly` with respx + golden HTML fixture; retry exhaustion; `_build_summary` aggregation |
| `fund_client.py` (176) | 47% | 75% | ~5 | extend — cache TTL (use `freezegun`), `fetch_historical_pe` full path, extreme PE filter |
| `holding_client.py` (174) | 58% | 80% | ~6 | extend — `fetch_master` JSON parse, retry on cookie failure, DII exclusion logic |

### Wave 3C — Display layer (optional, low risk)

**Target:** 53% → 70% (+225 lines, +1.3pp)

Rich-table rendering tests. Pattern:
```python
from rich.console import Console
console = Console(record=True, width=120)
# invoke display function
text = console.export_text()
assert "Header" in text
```

| File | Cov now | Target | New tests |
|---|---:|---:|---:|
| `fmp_display.py` (214) | 31% | 70% | ~8 |
| `fund_display.py` (122) | 51% | 75% | ~5 |
| `mf_display.py` (97) | 33% | 70% | ~5 |
| `mfportfolio_display.py` (52) | 40% | 75% | ~4 |
| `scan_display.py` (87) | 28% | 65% | ~5 |

**Verdict: defer unless time allows.** Display bugs are visible and low-consequence; the ROI is lower than commands/clients.

### Wave 3D — Store + data_api deeper (optional)

- `store.py` (1,044, 86%, 148 missing) — cover schema migrations + rare methods; +50 lines, +0.3pp
- `research/data_api.py` (3,219, 84%, 503 missing) — dead sector-specific branches; +150 lines, +0.9pp

**Verdict: defer.** Diminishing returns. Skip unless structural Track B reveals specific gaps.

---

## Track B — Structural

### B1. CI workflow (CRITICAL)

**Current state:** No `.github/workflows/` directory exists.

**Create** `.github/workflows/tests.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: flow-tracker
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --extra test
      - name: Fast suite + coverage
        run: |
          uv run pytest -m "not slow" \
            --cov=flowtracker \
            --cov-report=term \
            --cov-report=xml \
            --cov-fail-under=65
      - name: Slow suite
        run: uv run pytest -m "slow"
      - uses: codecov/codecov-action@v4
        with:
          files: flow-tracker/coverage.xml
```

**Threshold: start at 65%** (below current 68% to absorb flake noise), raise to 75% after Track A completes.

### B2. Branch coverage enabled

Add to `flow-tracker/pyproject.toml`:

```toml
[tool.coverage.run]
branch = true
source = ["flowtracker"]

[tool.coverage.report]
precision = 1
show_missing = true
skip_covered = false
```

Expected impact: current 68% line → ~55-60% branch. Reveals untested `if/elif/else` paths. Branch coverage becomes the real number; line becomes a loose proxy.

### B3. Fix flaky concurrency tests

**Two failing:**
- `TestConcurrentWrites::test_concurrent_writes_different_tables`
- `TestConcurrentReadWrite::test_many_concurrent_readers`

**Investigation needed** — the structural recon proposed the failures stem from `date('now')` SQL filters rejecting hardcoded test dates, but inspection of `test_store_concurrent.py:43-44` shows the tests already use `date.today().isoformat()`. Actual cause likely SQLite WAL write contention under parallel threads.

**Options (pick after investigation):**
1. **Fix the race** — likely `BEGIN IMMEDIATE` on writers, or WAL checkpoint timing
2. **Retry decorator** — `@pytest.mark.flaky(reruns=2)` via `pytest-rerunfailures`
3. **Separate marker** — `@pytest.mark.concurrency`, run only on nightly CI, exclude from default

**Recommendation:** Start with option 2 (unblocks CI), open follow-up to diagnose the race. Current known-flaky state has persisted since 2026-04-09 — don't block coverage work on it.

### B4. Coverage threshold in pyproject

After Track A completes, lock it in:

```toml
[tool.coverage.report]
fail_under = 75
```

Prevents regression.

### B5. `--help` snapshot test (cheap, high signal)

Add `tests/contract/test_cli_help_snapshot.py` using `syrupy`:

```python
def test_all_help_outputs_match_snapshot(snapshot):
    from flowtracker.main import app
    runner = CliRunner()
    outputs = {}
    for cmd_path in ALL_COMMANDS:  # reuse list from test_smoke.py
        result = runner.invoke(app, cmd_path + ["--help"])
        outputs[" ".join(cmd_path)] = result.output
    assert outputs == snapshot
```

Catches silent option removal, typo fixes that break muscle memory, help-text regressions. ~30 min to set up.

### B6. hypothesis for parsers (optional)

Add `hypothesis>=6.100` to test extras. Use for:
- `utils._parse_nse_date` — all NSE date formats
- `filing_client._parse_bse_date` — all BSE date variants
- Dividend/split/bonus multiplier parsers (property: round-trip invariant)
- `_screener_period_to_fy_quarter` — every month→quarter

One property test replaces ~20 example tests. Scope: ~4 parsers, ~8 properties, half-day of work.

**Verdict: nice-to-have, not required for 80% goal.**

### B7. Mutation testing (deferred)

`mutmut` on critical math files only (screener_engine scoring, fund_models ratios). Not needed for 80% target; revisit when shipping broadly.

---

## Track C — Agent logging / observability for deeper evals

### Context

**What exists today** (good foundation):
- `~/vault/stocks/{SYMBOL}/traces/{timestamp}.json` — `PipelineTrace` with `PhaseEvent` (per phase) + `AgentTrace` per specialist (tools_available, tool_calls, reasoning blocks, cost, status)
- `briefings/{agent}.json` — `BriefingEnvelope` (confidence, signal, key_findings, mandatory_metrics_status)
- `evidence/{agent}.json` — legacy flat tool-call log
- `ToolEvidence` per call — name, args, result_summary (500 chars), result_hash, is_error, started_at, duration_ms
- `AgentCost` — input/output/cache tokens, total USD, model, duration (aggregated, not per-turn)
- `reports/{agent}.md` — final markdown

**What evals consume today:**
`autoeval/evaluate.py::read_agent_evidence()` prefers `PipelineTrace` → falls back to legacy evidence + briefing. Gemini grading prompt includes tools_available, tool calls, unused tools, errors, cost, model. Graded on 6 dimensions: analytical depth, logical consistency, completeness, actionability, sector framework, data sourcing. Issues classified: PROMPT_FIX / DATA_FIX / COMPUTATION / NOT_OUR_PROBLEM.

**Rule: "Do NOT grade accuracy of specific numbers"** — Gemini's training data is stale, so it can only grade *process quality* (frameworks, completeness, tool use), not *number correctness*.

### What's missing — 10 gaps that limit eval depth

| # | Gap | Why it matters for evals | Where to add |
|---|---|---|---|
| C1 | **Retry counts + cause** — RateLimitEvent is caught but not persisted; retry after truncation not distinguished from retry after network error | Can't grade "agent resilience" — did it recover? | `agent.py` message loop (~565); new `retry_events: list[RetryEvent]` on `AgentTrace` |
| C2 | **Per-tool latency distribution** (p50, p95, max) | Evals can spot "agent waited 15s on slow tool instead of reordering" | Already have `duration_ms` per call; add aggregation in `AgentTrace` post-processing + expose in eval prompt |
| C3 | **Per-turn token usage + cache hit/miss** | Reveals "agent rebuilt context wastefully" vs "efficient cache reuse" | `agent.py` ~635 `ResultMessage.usage` — capture per-turn, not just aggregate; add `turns: list[TurnEvent]` on `AgentTrace` |
| C4 | **Tool-result completeness signal** — currently just `result_summary[:500]` + is_error; lose "returned empty", "truncated", "N rows" | Evals can't distinguish "agent didn't call right tool" from "tool returned no data" | `tools.py` wrapper layer — add `completeness: Literal["full", "partial", "empty", "truncated", "error"]` + `row_count: int \| None` to `ToolEvidence` |
| C5 | **Reasoning↔tool interleaving** — TextBlocks collected flat, lose which reasoning preceded which tool call | Chain-of-thought is opaque; evals can't see if agent reasoned before acting vs after | `agent.py` ~548 — preserve `turn_index` on each ToolEvidence and TextBlock |
| C6 | **Per-turn model** — only final model logged; if agent falls back (sonnet→haiku on timeout), lost | Grade fallback behavior; attribute quality to model | `agent.py` — capture model from each `AssistantMessage` (if exposed) or config per turn |
| C7 | **Compliance-gate attempt traces** — `mandatory_metrics_status` is prose ("attempted via get_company_context"); not linked to actual tool-call IDs | Can't verify "agent really tried" — the core premise of the compliance gate | `agent.py` post-run — cross-reference `mandatory_metrics_status["attempted"]` with `tool_calls` by tool name+args; annotate with call IDs |
| C8 | **Data-tool extraction quality** — concall_extractor produces partial extractions (missing Q1, Q2 of 4) but this isn't surfaced to the agent or its trace | Low-quality reports may trace back to source-data degradation, not agent; evals conflate the two | `data_api.py` — attach `_meta: {"extraction_status": "partial", "missing_periods": [...]}` to return payloads; propagate to `ToolEvidence` |
| C9 | **Cost per phase** — `total_cost_usd` is per-agent; not split by "data refresh" vs "tool-search" vs "synthesis" | Unit economics: which agents are expensive for low return? | `PhaseEvent` already has start/finish; aggregate token usage *within each phase* by routing `AgentCost.input_tokens` delta per phase |
| C10 | **Time-to-first-token** — overall `duration_seconds` only; can't see if agent "stalled before speaking" | Perceived responsiveness; detects model warm-up issues | `agent.py` query loop — capture timestamp of first `AssistantMessage` vs query start |

### C — Proposed changes

**Phase C-1: Data-model additions** (pure dataclass work, no behavior change)

Extend `flowtracker/research/briefing.py`:

```python
@dataclass
class TurnEvent:
    turn_index: int
    started_at: str
    duration_ms: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_chars: int             # sum of TextBlock content lengths this turn
    tool_call_ids: list[str]         # ToolEvidence.tool_use_id list from this turn

@dataclass
class RetryEvent:
    tool_name: str
    attempt: int                     # 1-indexed
    cause: Literal["truncation", "rate_limit", "network", "validation", "empty_result", "other"]
    wait_ms: int                     # backoff wait before retry
    at: str                          # ISO timestamp

# Extend existing ToolEvidence:
@dataclass
class ToolEvidence:
    # ... existing fields ...
    turn_index: int | None = None                                    # C5
    completeness: Literal["full", "partial", "empty", "truncated", "error"] | None = None  # C4
    row_count: int | None = None                                     # C4
    extraction_meta: dict | None = None                              # C8 — passthrough from data_api._meta

# Extend existing AgentTrace:
@dataclass
class AgentTrace:
    # ... existing fields ...
    turns: list[TurnEvent] = field(default_factory=list)             # C3, C5, C6
    retries: list[RetryEvent] = field(default_factory=list)          # C1
    time_to_first_token_ms: int | None = None                        # C10
    compliance_gate_traces: list[dict] = field(default_factory=list) # C7 — {metric, status, attempted_calls: [tool_use_id]}
    per_phase_cost: dict[str, AgentCost] = field(default_factory=dict)  # C9 — optional; keyed by phase name
```

**Phase C-2: Instrumentation at natural seams**

- `agent.py` message loop: add `turn_counter`, record `TurnEvent` on each `ResultMessage`, stamp each `ToolEvidence` + TextBlock with `turn_index`, detect first-token timestamp
- `agent.py` retry handler: when `RateLimitEvent` fires or a tool is re-called with same args within same agent run, append `RetryEvent`
- `tools.py` wrapper: classify `completeness` via simple heuristics (empty list → "empty", result with `_truncated: True` marker → "truncated", exception → "error", `is_error=False` with content → "full"); capture `row_count` from common return shapes
- `data_api.py`: attach `_meta: {"extraction_status", "missing_periods", "degraded_quality": bool}` to payloads where extraction can be partial (concall_insights, sector_kpis, quarterly_results when coverage < N quarters)
- Post-run cross-ref: after agent finishes, walk `briefing.mandatory_metrics_status["attempted"]` against `tool_calls` and annotate with `tool_use_id`s (C7)

**Phase C-3: Evaluation prompt richer context**

Update `autoeval/evaluate.py::format_agent_evidence()` (or whatever builds the "Agent Execution Log" section of the Gemini prompt) to surface new fields:

```
Agent Execution Log — {agent} on {symbol}
- Turns: 12 (p50 turn: 8.2s, max: 22.1s)
- Tokens: 45k in / 12k out / 180k cache-read / 8k cache-write → $0.41
- Time to first token: 1.3s
- Retries: 2 (tool=get_fundamentals cause=truncation; tool=get_events_actions cause=rate_limit)
- Tool completeness: 23/25 full, 1 empty (get_dividend_history), 1 truncated (get_concall_insights)
- Compliance gate: 8/10 metrics extracted, 2 attempted-but-empty (GNPA: tried concall_insights + get_company_context, both empty → logged as open question)
- Source data quality: concall Q1-FY26 missing (extraction_status=partial)
Tool calls (interleaved with reasoning):
  Turn 1: [reasoning 420 chars] → get_fundamentals(SBIN, section=overview)
  Turn 2: [reasoning 210 chars] → get_concall_insights(SBIN, page=1)
  ...
```

This transforms grading from "did the agent produce the right sections" to "did the agent do the right WORK to produce those sections". Adds 5-8 new graded signals without new Gemini dimensions:

- **Efficiency** — turns × avg-turn-cost vs report quality
- **Resilience** — retries handled vs abandoned
- **Source-data awareness** — did agent flag partial extraction?
- **Compliance honesty** — are "attempted" claims backed by actual tool calls?

### Adding new eval dimensions (optional, P2)

Once C-1..C-3 land, add two **new graded dimensions** to `autoeval/evaluate.py` grading rubric:

| Dimension | Rubric |
|---|---|
| **Tool-use discipline** | A: retried on truncation, chose right tool first time, no wasted calls. F: gave up on first empty result, called same tool 5x without changing args. |
| **Cost efficiency** | A: <$0.30 and <8 turns for full report. F: >$1.00 with similar depth. |

(Non-blocking — evaluate after C-1..C-3 prove telemetry works.)

### C work breakdown (tasks)

| # | Task | Files | Est complexity |
|---|---|---|---|
| C-1 | Add `TurnEvent`, `RetryEvent`, extend `ToolEvidence` + `AgentTrace` dataclasses | `briefing.py` | small |
| C-2a | Turn-indexing + `TurnEvent` capture in message loop | `agent.py` | medium |
| C-2b | Retry detection + `RetryEvent` emission | `agent.py` | small-medium |
| C-2c | Completeness/row-count heuristics in tool wrapper | `tools.py` | small (one decorator or shared helper) |
| C-2d | `_meta` extraction_status on data_api returns | `data_api.py` (concall_insights, sector_kpis, quarterly_results) | small-medium |
| C-2e | Compliance-gate ↔ tool_call cross-reference | `agent.py` post-run | small |
| C-2f | Time-to-first-token capture | `agent.py` query loop | trivial |
| C-3 | Richer eval prompt formatting | `autoeval/evaluate.py::format_agent_evidence()` | small-medium |
| C-4 | Tests for new dataclasses + instrumentation helpers | new `tests/unit/test_turn_events.py`, extend `test_briefing_extended.py` | small |
| C-5 (optional) | Add Tool-Use-Discipline + Cost-Efficiency dimensions to grading rubric | `autoeval/evaluate.py` grading prompt | small; requires 1 eval cycle to validate |

### C dependencies & ordering

- C-1 blocks C-2 (dataclasses first)
- C-2a..f all independent of each other after C-1 — dispatch in parallel
- C-3 requires C-2 done (prompt can't reference fields that aren't there)
- C-4 can run in parallel with C-2 (test the dataclasses as they land)
- C-5 is post-merge, validated by running full financials eval matrix

### Out of scope for C

- **Log rotation / retention** — already handled by `PipelineTrace` per-timestamp filenames
- **Separate telemetry backend** (Prometheus, DataDog) — overkill for single-user tool; JSON files are fine
- **Live dashboard** — out of scope; `autoeval/progress.py` already summarizes; could extend later if demand
- **Per-tool cost attribution** — each `AssistantMessage` doesn't have token breakdown by tool; Anthropic API doesn't expose per-block tokenization; not worth the proxy estimation

---

## Execution plan

### Orchestration

Medium-tier task per CLAUDE.md. Orchestrator-dispatch pattern.

**Dependency graph:**
- Wave 3A (6 files) — all independent, parallel dispatch
- Wave 3B (6 files) — all independent, parallel dispatch
- B1 (CI), B2 (branch cov config), B3 (flake fix), B5 (snapshot) — all independent
- 3A and 3B can run in parallel with each other; no shared files
- **Wait on 3A+3B** before B1 enables strict threshold

**Dispatch batches:**

1. **Batch 1 (6 subagents, parallel)** — Wave 3A commands layer (one per file)
2. **Batch 2 (6 subagents, parallel)** — Wave 3B client layer (one per file)
3. **Batch 3 (3 subagents, parallel)** — B1 CI, B3 flake fix, B5 help-snapshot
4. **Self (no subagent)** — B2 pyproject branch config, B4 threshold lock
5. **Verify batch** — full pytest + coverage delta report

### Task tracking

Create 15 tasks (one per file in 3A+3B, one per structural item). Mark `in_progress` on dispatch, `completed` on verification.

### Expected outcome

| Milestone | Line cov | Branch cov (est) | Tests |
|---|---:|---:|---:|
| Now | 68.0% | ~55% | 1,980 |
| After Wave 3A | 71% | 58% | ~2,050 |
| After Wave 3B | **77%** | **63%** | ~2,100 |
| After Wave 3C (if done) | 78.5% | 64% | ~2,130 |
| CI gates + branch cov visible | same | same | same (infrastructure) |

### Out of scope (document decision)

- `research/agent.py` (761 stmts, 6%) — Claude SDK orchestration. Quality covered by eval loop; unit tests are low-value and brittle.
- `research/autoeval/evaluate.py` remaining 58% — Gemini API orchestration; mocking is high-cost.
- Full mutation testing — defer.
- `research_commands.py` deep (above 30%) — async orchestration + Claude SDK; same rationale as agent.py.

---

## Success criteria

1. **≥ 77% line coverage, ≥ 63% branch coverage** on the fast suite.
2. **GitHub Actions workflow runs** fast+slow suites on every push and PR.
3. **Coverage regression gate** active (fail CI if line cov drops below 75%).
4. **Two known flakes** either fixed or isolated behind a marker — default `pytest` run is green.
5. **Branch coverage is visible** in every coverage report (`--cov-branch`).
6. **`--help` snapshot test** in place.
7. **Zero source code changes** except targeted flake fix (if chosen) and test-harness adjustments.

---

## Worktree

Continue in existing worktree `feat/test-coverage-tier1-2` (rename to `feat/test-coverage-tier3` on merge), OR create fresh `feat/test-coverage-tier3` from main after committing Tier 1+2.

Recommendation: **commit Tier 1+2 now**, then branch fresh `feat/test-coverage-tier3` to keep PRs reviewable.
