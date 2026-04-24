# autoagent-pilot

Autonomous, hill-climbing agent-engineering loop for the `business` specialist.
Inspired by [kevinrgu/autoagent](https://github.com/kevinrgu/autoagent).

The pattern: human sets a directive in `program.md`, then a meta-agent (Claude
Code, in a tmux session) reads `program.md` and iterates — diagnoses the
latest benchmark results, edits the business agent's L1-L4 prompt stack,
reruns the benchmark, keeps/discards based on `passed` count, repeats.

## Files

- **`program.md`** — meta-agent directive + layer-routing rules. **Edit this
  by hand** to steer the loop; the meta-agent reads it each iteration.
- **`benchmark.json`** — 8 stocks × 4 sector_skill cells (bfsi, private_bank,
  pharma, it_services). Edit only before starting a fresh run.
- **`run_benchmark.sh`** — 4-wide parallel across stocks → Gemini grading →
  aggregate row into `results.tsv`.
- **`score.py`** — parses `eval_history/*.json` archives into aggregate row
  + diagnosis JSON (per-layer PROMPT_FIX issue grouping).
- **`results.tsv`** — the experiment ledger. Columns: `commit / avg_score /
  passed / task_scores / cost_usd / status / description`.
- **`baseline/`** — frozen copy of `prompts.py` + full `sector_skills/` at
  pilot start. If you ever want to nuke all iteration damage and restart
  from scratch, `cp -R baseline/sector_skills/* ../flow-tracker/flowtracker/research/sector_skills/` and replace `prompts.py`.

## Edit surface (the L1-L4 stack)

```
L1  SHARED_PREAMBLE_V2                                (all agents)
    ../flow-tracker/flowtracker/research/prompts.py
    — hash-pinned at prompts.py:2248, regenerate hash after any edit

L2  BUSINESS_SYSTEM_V2 + BUSINESS_INSTRUCTIONS_V2     (business, all sectors)
    ../flow-tracker/flowtracker/research/prompts.py:266–370

L3  {sector}/_shared.md                               (all agents, one sector)
    ../flow-tracker/flowtracker/research/sector_skills/{bfsi,private_bank,pharma,it_services}/_shared.md

L4  {sector}/business.md                              (business, one sector)
    ../flow-tracker/flowtracker/research/sector_skills/{bfsi,private_bank,pharma,it_services}/business.md
```

See `program.md` for layer-selection rules.

## Kickoff

1. **Baseline first.** From this directory:
   ```bash
   ./run_benchmark.sh --description "baseline"
   ```
   Wait ~15-20 minutes. Open `results.tsv` — you should see one row with the
   8 stocks' grades. Set `status=keep` manually.

2. **Start the meta-agent loop.** Open a tmux session and launch Claude Code
   in it with auto-mode on:
   ```bash
   tmux new -s autoagent-business
   cd /path/to/equity-research-autoagent-pilot
   claude  # or however you invoke Claude Code
   ```
   Then in Claude Code, type:
   ```
   Read autoagent-pilot/program.md and kick off a new experiment.
   ```
   The meta-agent will read program.md, diagnose the baseline, pick a layer
   edit, rerun, keep/discard, and repeat until the plateau brake fires.

## Budget / guardrails

- **Plateau brake**: 3 consecutive discards → meta-agent stops and asks the
  human. See `program.md` § Plateau Brake.
- **Cost**: ~$2-5 per iteration (8 stocks × business agent run + Gemini
  grade). Budget ~$40-100 for an overnight run.
- **Overfitting guard**: no stock names in prompts; each layer requires
  evidence at its scope (see `program.md` § Prompt Layer Strategy).
- **L1/L3 regression**: edits to shared layers require a cross-agent spot-
  check before keep/discard (see `program.md` § Keep / Discard Rules).

## Why this scope

v0 restricts the meta-agent to prompt edits only. Tool changes, model swaps,
routing logic, and the `_build_mcap_injection` Python path are out of scope.
If v0 plateaus early with mostly DATA_FIX issues, v1 expands scope.

## Benchmark design note

The benchmark has 2 stocks per sector_skill cell so L3/L4 edits have ≥2
stocks of evidence. The cells mirror the existing 15-sector autoeval matrix
and were chosen because HDFCBANK/SBIN hit different sector_skill dirs
(private_bank vs bfsi) — naively pairing "BFSI: HDFCBANK + SBIN" would
make both L3/L4 edits overfit on N=1.

Added 4 new keys to `eval_matrix.yaml` (`bfsi_bob`, `private_bank_icici`,
`pharma_drl`, `it_services_infy`) so each cell has 2 stocks. Metals dropped
from v0 for tighter scope.
