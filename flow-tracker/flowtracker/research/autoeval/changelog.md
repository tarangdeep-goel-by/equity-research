# AutoEval Changelog

Structured log of every prompt change and its eval result. Updated by the orchestrator after each experiment.

## Format

Each entry follows:
```
### {agent}/{sector} — Cycle {N} — {grade_before} → {grade_after} — {KEPT|REVERTED}
**Date:** YYYY-MM-DD HH:MM UTC
**Stock:** {SYMBOL}
**Change:** {what was modified — file path + brief description}
**Gemini feedback (key issues):**
- {issue 1}
- {issue 2}
**Fix applied:** {what was added/changed in the skill or prompt}
**Result:** {new grade} — {kept or reverted and why}
**Commit:** {short sha}
```

---

<!-- Entries below, newest first -->
