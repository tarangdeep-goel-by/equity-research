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


# Minimum size for a heading-based section match to be trusted without fallback.
# Below this, we try a body-text fallback (see _body_text_fallback) — Docling
# sometimes renders the real section header as plain paragraph text (e.g.
# SUNPHARMA FY25 MD&A) and the only `##` heading in the TOC hands back a
# forward-reference blurb.
_MIN_HEADING_SECTION_CHARS = 2000

# Body-text fallback requires the synthetic section to be at least this many
# times bigger than the tiny heading-based section before we substitute it —
# guards against accidentally picking up stray mentions of the canonical name.
_BODY_FALLBACK_IMPROVEMENT_RATIO = 5


def build_ar_section_index(md: str, headings: list[dict]) -> dict[str, dict]:
    """Return {canonical_name: {char_start, char_end, matched_heading, level}}.

    Strategy:
      1. For each heading, try matching against each canonical section's aliases.
      2. Multiple headings may match the same canonical name (e.g. AR has both a
         forward reference "see MD&A Report" and the actual section header).
         We pick the candidate that produces the LARGEST section — the real one.
      3. char_end is the start of the next heading at the same-or-higher level.
      4. If the largest heading-based candidate is still tiny (< 2KB), fall
         back to plain-text occurrences of the aliases in the markdown body —
         Docling sometimes flattens the real section header to a paragraph
         (e.g. SUNPHARMA FY25 MD&A lives as repeating running-header text,
         not as a `##` heading).
      5. Sections not found are simply absent from the index.
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

    # Ranges that correspond to actual heading lines — used to exclude
    # occurrences inside an already-matched heading from the body-text fallback.
    heading_ranges = [
        (h["char_offset"], h["char_offset"] + h["level"] + 2 + len(h["text"]))
        for h in headings
    ]

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
        entry = {
            "char_start": h["char_offset"],
            "char_end": end,
            "matched_heading": h["text"],
            "level": h["level"],
            "size_chars": size,
            "match_source": "heading",
        }

        # Size-gated body-text fallback: when the best heading slice is tiny,
        # scan the markdown for plain-text occurrences of the alias patterns
        # and synthesize a section using the next different-canonical heading
        # as the end boundary.
        if size < _MIN_HEADING_SECTION_CHARS:
            fallback = _body_text_fallback(
                md, canonical, compiled[canonical], compiled, headings, heading_ranges,
            )
            if fallback and fallback["size_chars"] >= size * _BODY_FALLBACK_IMPROVEMENT_RATIO:
                logger.info(
                    "Section '%s': heading-based slice tiny (%d chars); "
                    "body-text fallback gives %d chars at offset %d — using fallback",
                    canonical, size, fallback["size_chars"], fallback["char_start"],
                )
                entry = fallback

        index[canonical] = entry

    unknown_count = len(headings) - len(matched_heading_ids)
    if unknown_count > 0:
        logger.debug(
            "Section index: matched %d/%d canonical sections; %d unmapped headings",
            len(index), len(AR_SECTIONS), unknown_count,
        )
    return index


def _body_text_fallback(
    md: str,
    canonical: str,
    regexes: list[re.Pattern],
    all_compiled: dict[str, list[re.Pattern]],
    headings: list[dict],
    heading_ranges: list[tuple[int, int]],
) -> dict | None:
    """Synthetic section anchor from plain-text body occurrences.

    For each non-heading-range occurrence of a canonical's alias regexes in
    `md`, compute a synthetic section body ending at the next heading that
    matches a DIFFERENT canonical section. Pick the occurrence with the
    largest synthetic body.

    Returns a dict matching `build_ar_section_index` entry shape with
    `match_source="body_text"`, or None if no usable body hit is found.
    """
    # Gather all raw-text match positions for this canonical.
    hits: list[int] = []
    for rx in regexes:
        for m in rx.finditer(md):
            hits.append(m.start())
    if not hits:
        return None
    # Dedup + sort (different aliases may match at the same position).
    hits = sorted(set(hits))

    def _inside_heading(off: int) -> bool:
        for s, e in heading_ranges:
            if s <= off < e:
                return True
        return False

    def _looks_like_title_line(off: int) -> bool:
        """Filter: the match should start a short line that reads like a
        section title, not mid-paragraph prose or a TOC bullet.

        Rules:
          - Must be at start of line (preceded by newline or beginning of doc).
          - The containing line must be <= 120 chars (long lines = prose).
          - The line must not start with a TOC-bullet character sequence
            like "- N Title" or "N Title" (integer page numbers).
        """
        # Must be at the start of a line.
        if off > 0 and md[off - 1] != "\n":
            return False
        # Find the line's end (newline or EOF).
        line_end = md.find("\n", off)
        if line_end < 0:
            line_end = len(md)
        line = md[off:line_end]
        # Reject very long lines — those are prose, not titles.
        if len(line) > 120:
            return False
        return True

    def _next_other_canonical_heading(start_off: int) -> int:
        """First heading after start_off whose text matches a canonical
        section OTHER than `canonical`. Used as the synthetic end boundary."""
        for h in headings:
            if h["char_offset"] <= start_off:
                continue
            text = h["text"]
            for other, other_rxs in all_compiled.items():
                if other == canonical:
                    continue
                if any(rx.search(text) for rx in other_rxs):
                    return h["char_offset"]
        return len(md)

    best: dict | None = None
    for off in hits:
        if _inside_heading(off):
            continue
        if not _looks_like_title_line(off):
            continue
        end = _next_other_canonical_heading(off)
        synthetic_size = end - off
        if best is None or synthetic_size > best["size_chars"]:
            # Capture the actual matching text span for the `matched_heading`
            # field so callers can tell it was a body-text match.
            # Use a short excerpt from the offset (strip to first line).
            line_end = md.find("\n", off)
            line_end = off + 80 if line_end < 0 else min(line_end, off + 120)
            best = {
                "char_start": off,
                "char_end": end,
                "matched_heading": md[off:line_end].strip(),
                "level": 0,  # synthetic — no explicit heading level
                "size_chars": synthetic_size,
                "match_source": "body_text",
            }
    return best


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
