"""Guards against the fno_positioning-class CLI registry bug (PR #131).

If an agent is wired through agent.py (DEFAULT_MODELS) or scheduled in
the autoeval matrix but missing from VALID_AGENTS in research_commands.py,
`flowtrack research run <agent>` exits 1 with "Unknown agent" — this only
surfaces when the autoeval cron fires the agent against ~20 stocks and
burns API budget on the failed run.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from flowtracker.research.agent import DEFAULT_MODELS
from flowtracker.research_commands import VALID_AGENTS

# Names that live in DEFAULT_MODELS but are NOT specialist agents the CLI
# `research run` accepts. They have their own command paths (synthesis is
# called by `research thesis`; verifier is invoked from agent.py; etc.).
NON_SPECIALIST_MODEL_KEYS = {"synthesis", "verifier", "web_research", "explainer"}

EVAL_MATRIX_PATH = (
    Path(__file__).parent.parent.parent
    / "flowtracker"
    / "research"
    / "autoeval"
    / "eval_matrix.yaml"
)


def test_eval_matrix_agents_in_valid_agents():
    matrix = yaml.safe_load(EVAL_MATRIX_PATH.read_text())
    matrix_agents = set(matrix.get("agents") or [])
    assert matrix_agents, "eval_matrix.yaml has no agents list"
    missing = matrix_agents - VALID_AGENTS
    assert not missing, (
        f"agents in eval_matrix.yaml not in VALID_AGENTS: {sorted(missing)}. "
        "Add them to research_commands.VALID_AGENTS or remove from the matrix."
    )


def test_default_models_specialists_in_valid_agents():
    specialist_keys = set(DEFAULT_MODELS.keys()) - NON_SPECIALIST_MODEL_KEYS
    missing = specialist_keys - VALID_AGENTS
    assert not missing, (
        f"specialist agents in DEFAULT_MODELS not in VALID_AGENTS: {sorted(missing)}. "
        "Add them to research_commands.VALID_AGENTS or move to NON_SPECIALIST_MODEL_KEYS."
    )
