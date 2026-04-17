"""Map a flat heading list (from doc_extractor) to a canonical section index.

Annual reports follow a SEBI/Companies-Act-driven structure. Their actual heading
text varies wildly ("MD&A" vs "Management Discussion and Analysis Report" vs
"Management's Discussion And Analysis"), so we match against a canonical-name
dictionary with several aliases per section.

Decks are looser — they just have slide titles. For decks we don't impose a
canonical structure; we simply expose the heading list as the slide topic index.

Public surface:
    AR_SECTIONS                       — canonical section name → list of regex aliases
    build_ar_section_index(md, headings) -> dict[str, dict]
    slice_section(md, section_index, name) -> str
    deck_slide_index(headings) -> list[dict]
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)


# Canonical AR sections + alias regexes.
# Order matters when sections nest (e.g. "Notes to Financial Statements" must match
# before "Financial Statements"). Aliases use case-insensitive whole-word matching.
AR_SECTIONS: dict[str, list[str]] = {
    "chairman_letter": [
        r"chairman'?s?\s+(letter|message|statement)",
        r"letter\s+from\s+the\s+chairman",
        r"chairperson'?s?\s+(letter|message)",
    ],
    "ceo_letter": [
        r"(ceo|managing\s+director|md)'?s?\s+(letter|message|statement|review)",
        r"letter\s+from\s+the\s+(ceo|managing\s+director|md)",
    ],
    "mdna": [
        r"management'?s?\s+discussion\s+(and|&)\s+analysis",
        r"\bmd\s*&\s*a\b",
        r"\bmd&a\b",
        r"discussion\s+and\s+analysis\s+report",
    ],
    "directors_report": [
        r"directors'?\s+report",
        r"board'?s?\s+report",
        r"report\s+of\s+the\s+(board\s+of\s+)?directors",
    ],
    "risk_management": [
        r"risk\s+management(\s+report)?",
        r"risk\s+(factors|review|profile|assessment)",
        r"enterprise\s+risk\s+management",
    ],
    "auditor_report": [
        r"independent\s+auditor'?s?\s+report",
        r"auditor'?s?\s+report",
        r"report\s+of\s+the\s+(independent\s+)?auditor",
    ],
    "corporate_governance": [
        r"corporate\s+governance(\s+report)?",
        r"report\s+on\s+corporate\s+governance",
        r"governance\s+report",
    ],
    "brsr": [
        r"business\s+responsibility\s+(and|&)\s+sustainability\s+report",
        r"\bbrsr\b",
        r"business\s+responsibility\s+report",
    ],
    "notes_to_financials": [
        r"notes\s+to\s+(the\s+)?(consolidated\s+|standalone\s+)?financial\s+statements",
        r"notes\s+forming\s+part\s+of\s+(the\s+)?financial\s+statements",
        r"significant\s+accounting\s+policies",
    ],
    "financial_statements": [
        # Match only when not preceded by "Notes to" — order in this dict already handles nesting.
        r"(consolidated|standalone)?\s*balance\s+sheet",
        r"(consolidated|standalone)?\s*statement\s+of\s+profit\s+(and|&)\s+loss",
        r"(consolidated|standalone)?\s*cash\s+flow\s+statement",
        r"statement\s+of\s+changes\s+in\s+equity",
    ],
    "segmental": [
        r"segment(al)?\s+(reporting|information|reporting\s+and\s+disclosures)",
        r"operating\s+segments",
    ],
    "related_party": [
        r"related\s+party\s+transactions?",
        r"\brpt\b\s+disclosure",
    ],
    "esop_disclosure": [
        r"employee\s+stock\s+option\s+(plan|scheme)\s+disclosure",
        r"\besop\b\s+disclosure",
        r"share[\s-]?based\s+payments?\s+disclosure",
    ],
}


def build_ar_section_index(md: str, headings: list[dict]) -> dict[str, dict]:
    """Return {canonical_name: {char_start, char_end, matched_heading, level}}.

    Strategy:
      1. For each heading, try matching against each canonical section's aliases.
      2. Multiple headings may match the same canonical name (e.g. AR has both a
         forward reference "see MD&A Report" and the actual section header).
         We pick the candidate that produces the LARGEST section — the real one.
      3. char_end is the start of the next heading at the same-or-higher level.
      4. Sections not found are simply absent from the index.
    """
    compiled = {
        canonical: [re.compile(p, re.IGNORECASE) for p in patterns]
        for canonical, patterns in AR_SECTIONS.items()
    }

    # Collect ALL candidate matches per canonical (multiple per name allowed).
    candidates: dict[str, list[dict]] = {}
    matched_heading_ids: set[int] = set()  # heading char_offsets we've matched, to count unmapped

    for h in headings:
        text = h["text"]
        for canonical, regexes in compiled.items():
            if any(rx.search(text) for rx in regexes):
                candidates.setdefault(canonical, []).append(h)
                matched_heading_ids.add(h["char_offset"])
                break  # one canonical per heading

    # For each canonical, score candidates by their section size and pick the largest.
    index: dict[str, dict] = {}
    for canonical, hits in candidates.items():
        scored = []
        for h in hits:
            end = _find_section_end(md, headings, h)
            scored.append((end - h["char_offset"], h, end))
        # Largest section wins (real header has more content than a forward reference).
        scored.sort(key=lambda t: t[0], reverse=True)
        size, h, end = scored[0]
        index[canonical] = {
            "char_start": h["char_offset"],
            "char_end": end,
            "matched_heading": h["text"],
            "level": h["level"],
            "size_chars": size,
        }

    unknown_count = len(headings) - len(matched_heading_ids)
    if unknown_count > 0:
        logger.debug(
            "Section index: matched %d/%d canonical sections; %d unmapped headings",
            len(index), len(AR_SECTIONS), unknown_count,
        )
    return index


def _find_section_end(md: str, headings: list[dict], h: dict) -> int:
    """Return char offset where this section ends — start of next same-or-higher-level heading."""
    end = len(md)
    h_idx = headings.index(h)
    for fwd in headings[h_idx + 1:]:
        if fwd["level"] <= h["level"]:
            end = fwd["char_offset"]
            break
    return end


def slice_section(md: str, section_index: dict[str, dict], name: str) -> str:
    """Return the markdown slice for a canonical section.

    Returns empty string if the section isn't in the index (i.e. not found in the doc).
    """
    entry = section_index.get(name)
    if not entry:
        return ""
    return md[entry["char_start"]:entry["char_end"]]


def deck_slide_index(headings: list[dict]) -> list[dict]:
    """Decks: just expose the heading list as the slide topic index.

    Filters out one-line footers and tiny headings that don't represent slides
    (heuristic: H1-H3 only, text >2 chars).
    """
    return [
        {"slide": h["text"], "level": h["level"], "char_offset": h["char_offset"]}
        for h in headings
        if h["level"] <= 3 and len(h["text"]) > 2
    ]


def section_size_summary(section_index: dict[str, dict]) -> list[dict]:
    """Compact per-section size table for inclusion in TOC responses."""
    return [
        {
            "name": name,
            "size_chars": entry["size_chars"],
            "size_class": _size_class(entry["size_chars"]),
        }
        for name, entry in section_index.items()
    ]


def _size_class(chars: int) -> str:
    if chars < 5_000:
        return "small"
    if chars < 30_000:
        return "med"
    if chars < 100_000:
        return "large"
    return "huge"


def known_sections() -> Iterable[str]:
    return AR_SECTIONS.keys()
