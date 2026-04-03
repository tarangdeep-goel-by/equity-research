"""Briefing envelope model for multi-agent research system."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


_VAULT_BASE = Path.home() / "vault" / "stocks"


class ToolEvidence(BaseModel, extra="ignore"):
    """Record of a single tool call made by a specialist agent."""

    tool: str
    args: dict = Field(default_factory=dict)
    result_summary: str = ""
    result_hash: str = ""  # sha256 of full result JSON
    is_error: bool = False


class AgentCost(BaseModel, extra="ignore"):
    """Cost and token tracking for a single agent run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    model: str = ""


class BriefingEnvelope(BaseModel, extra="ignore"):
    """Complete output from a specialist agent run."""

    agent: str  # "business", "financials", etc.
    symbol: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "success"  # "success" | "failed" | "empty"
    failure_reason: str = ""  # populated when status != "success"
    report: str = ""  # full markdown report section
    briefing: dict = Field(default_factory=dict)  # structured JSON for synthesis
    evidence: list[ToolEvidence] = Field(default_factory=list)
    cost: AgentCost = Field(default_factory=AgentCost)


class VerificationResult(BaseModel, extra="ignore"):
    """Output from a verification agent run."""

    agent_verified: str
    symbol: str
    verdict: str = "pass"  # "pass", "pass_with_notes", "fail"
    spot_checks_performed: int = 0
    issues: list[dict] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    overall_data_quality: str = ""


def save_envelope(envelope: BriefingEnvelope) -> dict[str, Path]:
    """Save a BriefingEnvelope to vault. Returns dict of saved file paths."""
    symbol = envelope.symbol.upper()
    base = _VAULT_BASE / symbol

    # Save report markdown
    reports_dir = base / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{envelope.agent}.md"
    report_path.write_text(envelope.report, encoding="utf-8")

    # Save briefing JSON
    briefings_dir = base / "briefings"
    briefings_dir.mkdir(parents=True, exist_ok=True)
    briefing_path = briefings_dir / f"{envelope.agent}.json"
    briefing_path.write_text(
        json.dumps(envelope.briefing, indent=2, default=str), encoding="utf-8"
    )

    # Save evidence JSON
    evidence_dir = base / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{envelope.agent}.json"
    evidence_data = [e.model_dump() for e in envelope.evidence]
    evidence_path.write_text(
        json.dumps(evidence_data, indent=2, default=str), encoding="utf-8"
    )

    return {"report": report_path, "briefing": briefing_path, "evidence": evidence_path}


def load_envelope(symbol: str, agent: str) -> BriefingEnvelope | None:
    """Load a BriefingEnvelope from vault. Returns None if not found."""
    symbol = symbol.upper()
    base = _VAULT_BASE / symbol

    report_path = base / "reports" / f"{agent}.md"
    briefing_path = base / "briefings" / f"{agent}.json"
    evidence_path = base / "evidence" / f"{agent}.json"

    if not report_path.exists() or not briefing_path.exists():
        return None

    report = report_path.read_text(encoding="utf-8")
    briefing = json.loads(briefing_path.read_text(encoding="utf-8"))

    evidence: list[ToolEvidence] = []
    if evidence_path.exists():
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence = [ToolEvidence(**e) for e in raw]

    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        report=report,
        briefing=briefing,
        evidence=evidence,
    )


def load_all_briefings(symbol: str) -> dict[str, dict]:
    """Load all briefing JSONs for synthesis. Returns {agent_name: briefing_dict}."""
    symbol = symbol.upper()
    briefings_dir = _VAULT_BASE / symbol / "briefings"

    if not briefings_dir.exists():
        return {}

    result: dict[str, dict] = {}
    for path in sorted(briefings_dir.glob("*.json")):
        agent_name = path.stem
        try:
            result[agent_name] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

    return result


def parse_briefing_from_markdown(text: str) -> dict:
    """Parse a JSON briefing block from the end of an agent's markdown output.

    Expects the agent to end its response with a fenced JSON code block:
    ```json
    { ... briefing ... }
    ```

    Returns the parsed dict, or empty dict if parsing fails.
    """
    # Match the last JSON fenced code block
    pattern = r"```json\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return {}

    try:
        return json.loads(matches[-1].strip())
    except json.JSONDecodeError:
        return {}
