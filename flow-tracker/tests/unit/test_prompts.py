"""Regression tests for specialist prompt wiring.

PR-9 — Every specialist prompt that tells the agent to call
`get_financial_projections` (directly or via the `get_fair_value_analysis`
projections section) must also tell the agent to resolve the company's
industry via `get_company_context` and pass it as an `industry=` hint.

Background: `data_api.py::get_financial_projections` auto-resolves an
industry token internally, but when an agent is left to default silently
without naming the industry in prose, the reader cannot distinguish a
correct platform/BFSI routing from a silent 2% D&A fallback. This test
guards against specialist prompts regressing to a projection call without
the explicit industry-hint guidance.
"""
from flowtracker.research.prompts import (
    AGENT_PROMPTS_V2,
)


# Every specialist (system, instructions) pair lives in AGENT_PROMPTS_V2.
# We check the concatenated prompt body for each entry.
_SPECIALIST_KEYS = [
    "business",
    "financials",
    "ownership",
    "valuation",
    "risk",
    "technical",
    "sector",
    "news",
    "macro",
]


def _prompt_body(key: str) -> str:
    system, instructions = AGENT_PROMPTS_V2[key]
    return system + "\n" + instructions


class TestSpecialistProjectionsIndustryHint:
    def test_specialists_calling_projections_mention_industry_hint(self):
        """Any specialist prompt referencing `get_financial_projections` must
        also tell the agent to resolve and pass the industry hint.

        The rule: if a specialist prompt names the projections tool, it must
        also contain (a) `get_company_context` as the resolution source and
        (b) an `industry=` / `industry hint` directive so the agent does not
        silently default to the generic 2% D&A fallback.
        """
        offenders = []
        for key in _SPECIALIST_KEYS:
            body = _prompt_body(key)
            if "get_financial_projections" not in body:
                continue
            mentions_context = "get_company_context" in body
            mentions_industry = "industry=" in body or "industry hint" in body
            if not (mentions_context and mentions_industry):
                offenders.append(
                    f"{key}: context={mentions_context}, industry_token={mentions_industry}"
                )
        assert not offenders, (
            "Specialists referencing `get_financial_projections` must also "
            "reference `get_company_context` and an `industry=` hint "
            "directive. Offenders: " + "; ".join(offenders)
        )

    def test_valuation_wires_industry_hint_for_projections(self):
        """Valuation is the primary consumer of projections (via
        `get_fair_value_analysis`). It must spell out the industry hint
        workflow — this is PR-9's main surface and the highest-risk
        regression target."""
        body = _prompt_body("valuation")
        assert "get_financial_projections" in body, (
            "Valuation prompt must reference `get_financial_projections` "
            "explicitly so agents know the industry-hint rule applies to "
            "both the direct tool and the `get_fair_value_analysis` section."
        )
        assert "get_company_context" in body
        assert "industry=" in body
        # The fallback-risk explanation should be present so the agent
        # understands WHY skipping the hint is a downgrade, not just WHAT
        # to type.
        assert "industry=unknown" in body, (
            "Valuation prompt must tell the agent to emit `industry=unknown` "
            "when context returns no industry — never silently default."
        )
