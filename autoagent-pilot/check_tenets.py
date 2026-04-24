#!/usr/bin/env python3
"""Verify no load-bearing preamble rule or specialist Key Rule was deleted.

Exit 0 if the current `prompts.py` preserves every L1 section header and
every L2 agent Key Rule bullet that existed in baseline/prompts.py.
Exit 1 (with a diff) otherwise.

Usage:
    check_tenets.py                    # default: guards business agent L2
    check_tenets.py --agent financials # guards financials L2 Key Rules

Meta-agent runs this BEFORE every commit of an L1 or L2 edit. If it exits
non-zero the edit is abandoned via `git revert HEAD` and the next iteration
tries a different shape of fix.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "baseline" / "prompts.py"
CURRENT = HERE.parent / "flow-tracker" / "flowtracker" / "research" / "prompts.py"

# Agent name → L2 system-prompt variable name in prompts.py
_AGENT_L2_VAR = {
    "business":    "BUSINESS_SYSTEM_V2",
    "financials":  "FINANCIAL_SYSTEM_V2",
    "ownership":   "OWNERSHIP_SYSTEM_V2",
    "valuation":   "VALUATION_SYSTEM_V2",
    "risk":        "RISK_SYSTEM_V2",
    "technical":   "TECHNICAL_SYSTEM_V2",
    "sector":      "SECTOR_SYSTEM_V2",
    "macro":       "MACRO_SYSTEM_V2",
}


def extract_block(src: str, var_name: str) -> str:
    m = re.search(rf'{re.escape(var_name)} = """(.*?)"""', src, re.DOTALL)
    if not m:
        raise SystemExit(f"FATAL: could not locate {var_name} in prompts.py")
    return m.group(1)


def l1_sections(preamble: str) -> list[str]:
    """27 named sections in SHARED_PREAMBLE_V2 — each is a load-bearing rule."""
    return re.findall(r"^## (.+)$", preamble, re.MULTILINE)


def l2_key_rules(system_block: str) -> list[str]:
    """Agent L2 Key Rules — bullets inside the '## Key Rules' or
    '## Key Rules (Core Tenets)' section of the agent's system prompt.
    """
    m = re.search(
        r"^## Key Rules(?:\s*\([^)]+\))?\s*\n(.*?)(?=^## |\Z)",
        system_block, re.DOTALL | re.MULTILINE,
    )
    if not m:
        return []
    block = m.group(1)
    # Match bullets — either `- Text` or `- **Bold title** — text`
    bullets = []
    for line in block.splitlines():
        if line.startswith("- "):
            # Normalize: take either the bold prefix or the first N words as the rule id
            bold = re.match(r"- \*\*([^*]+)\*\*", line)
            bullets.append(bold.group(1).strip() if bold else line[2:80].strip())
    return bullets


def numbered_tenet_refs(src: str) -> set[int]:
    """Any `Tenet N` reference anywhere in the prompts source.
    The meta-agent must not delete tenets that other agents / sector skills
    reference by number — renumbering would break cross-refs.
    """
    return set(int(m) for m in re.findall(r"Tenet (\d+)", src))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="business", choices=list(_AGENT_L2_VAR),
                    help="Agent whose L2 system prompt to guard (default: business)")
    args = ap.parse_args()

    l2_var = _AGENT_L2_VAR[args.agent]

    baseline_src = BASELINE.read_text()
    current_src = CURRENT.read_text()

    # ---- L1 check ---------------------------------------------------------
    b_l1 = l1_sections(extract_block(baseline_src, "SHARED_PREAMBLE_V2"))
    c_l1 = l1_sections(extract_block(current_src, "SHARED_PREAMBLE_V2"))
    deleted_l1 = [s for s in b_l1 if s not in c_l1]

    # ---- L2 agent Key Rules check -----------------------------------------
    try:
        b_l2 = l2_key_rules(extract_block(baseline_src, l2_var))
        c_l2 = l2_key_rules(extract_block(current_src, l2_var))
    except SystemExit as exc:
        # If the L2 var doesn't exist in prompts.py, treat L2 as empty — the
        # L1 + numbered-tenet guards still provide protection.
        print(f"[warn] {exc} — skipping L2 guard for --agent={args.agent}", file=sys.stderr)
        b_l2, c_l2 = [], []
    deleted_l2 = [r for r in b_l2 if r not in c_l2]

    # ---- Cross-referenced numbered Tenets ---------------------------------
    b_tenets = numbered_tenet_refs(baseline_src)
    c_tenets = numbered_tenet_refs(current_src)
    deleted_tenets = b_tenets - c_tenets

    ok = True
    if deleted_l1:
        ok = False
        print("TENET GUARD VIOLATION — L1 SHARED_PREAMBLE_V2 sections deleted:")
        for s in deleted_l1:
            print(f"  - {s}")
    if deleted_l2:
        ok = False
        print(f"TENET GUARD VIOLATION — L2 {l2_var} Key Rules deleted:")
        for r in deleted_l2:
            print(f"  - {r}")
    if deleted_tenets:
        ok = False
        print("TENET GUARD VIOLATION — cross-referenced numbered Tenets no longer appear:")
        for n in sorted(deleted_tenets):
            print(f"  - Tenet {n}")

    if not ok:
        print()
        print("Rule: load-bearing preamble sections and agent Key Rules may be")
        print("STRENGTHENED, split into sub-rules, or have worked examples added —")
        print("but NEVER deleted or renumbered. These rules represent accumulated")
        print("evidence from prior eval cycles (iter3, Phase 1, L1-L5 post-eval fixes).")
        print()
        print("Revert the edit: git revert HEAD")
        return 1

    print(f"OK — L1 sections: {len(c_l1)}/{len(b_l1)} preserved, "
          f"L2 {l2_var} Key Rules: {len(c_l2)}/{len(b_l2)} preserved, "
          f"cross-ref Tenets: {len(c_tenets & b_tenets)}/{len(b_tenets)} preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
