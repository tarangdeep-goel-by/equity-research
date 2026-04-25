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
        # Canonical IAR opener variants. Order matters only inside
        # `_AUDITOR_EXCLUDE_RE` (below) which subtracts Annexure-A headings
        # from the candidate set.
        # `auditor'?s?'?` matches all four possessive variants:
        #   - `Auditor` (no possessive)            — apostrophe and s both absent
        #   - `Auditor's` (singular possessive)    — apostrophe BEFORE s
        #   - `Auditors` (no possessive plural)    — s without apostrophe
        #   - `Auditors'` (plural possessive)      — apostrophe AFTER s
        # The earlier `auditor'?s?` regex missed `Auditors'` (plural-possessive,
        # used by joint-statutory-auditor layouts like SBIN FY25). The
        # alternate fix `auditors?'?` would have missed `Auditor's`. The
        # symmetrical form below covers all four.
        r"independent\s+auditor'?s?'?\s+report",
        r"auditor'?s?'?\s+report",
        r"report\s+of\s+the\s+(independent\s+)?auditor'?s?'?",
        # Indian banks / NBFCs / large issuers: Docling often emits the
        # IAR body without an explicit "Independent Auditor's Report"
        # heading; the actual section opener is "Report on Audit of the
        # [Standalone|Consolidated] Financial Statements" (HDFCBANK FY25,
        # SBIN FY25, etc.). The trailing entity name (e.g. "OF STATE BANK
        # OF INDIA") is fine — `re.search` matches anywhere in the heading.
        r"report\s+on\s+(the\s+)?audit\s+of\s+the\s+(standalone|consolidated)\s+financial\s+statements",
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


# Headings that look like they match `auditor_report` but are actually
# *sub-sections* of the IAR (CARO / Internal Financial Controls report)
# OR an unrelated assurance report (BRSR sustainability assurance).
# These must NOT be picked as the section start — the real IAR body lives
# elsewhere and a sub-section heading would yield a tiny header-only slice
# (HDFCBANK FY25: 239 chars instead of ~40KB).
#
# Patterns:
#   1. "Annexure [A|'A'|1|...] to/of (the) (Independent) Auditor['s|s'] Report"
#      — CARO 2020 / Internal Financial Controls reports. Letter token now
#      accepts quoted variants like 'A' (SBIN FY25 heading).
#   2. "Independent Practitioner's Reasonable Assurance Report ..." —
#      ESG / BRSR sustainability assurance issued by the auditor firm but
#      NOT the statutory IAR. HDFCLIFE FY25 BRSR-only filing has this as
#      the only audit-shaped heading; mistaking it for the IAR would route
#      a sustainability-assurance opinion into auditor_report.
#   3. "Independent Auditor's Report on the Internal Financial Controls" —
#      the IFC sub-report which sometimes appears as a separate top-level
#      heading rather than as "Annexure X" (HINDUNILVR FY25).
_AUDITOR_EXCLUDE_RE = re.compile(
    r"annexure\s+['\"]?[a-z0-9]+['\"]?\s+(to|of)\s+(the\s+)?(independent\s+)?auditor'?s?'?"
    r"|independent\s+practitioner",
    re.IGNORECASE,
)

# Headings that mark the end of the auditor_report section. The IAR body
# is normally followed by the audited financial statements (Balance Sheet,
# Profit and Loss, Cash Flow). The IAR itself contains many L2 sub-headings
# (Opinion, Basis for Opinion, Key Audit Matters, …) so the default
# same-or-higher-level end heuristic over-cuts the section. For
# `auditor_report` we instead end at the next financial-statements anchor
# or the next OTHER canonical-section heading, whichever comes first.
#
# Layout extensions covered:
#   - "Statement of Cash Flow(s)" — both singular and plural (HINDUNILVR
#     FY25 uses the plural form).
#   - "STANDALONE FINANCIALS" / "CONSOLIDATED FINANCIALS" — Indian-bank
#     section divider that introduces the financial schedules block (SBIN
#     FY25). Without this, the IAR slice spans into the schedules pages.
#   - "Schedule N - <name>" / standalone "Schedules" — banking-layout
#     numbered schedule headings that come right after the IAR (SBIN FY25).
#   - "<Bank Name> Schedules forming part of …" — caption that introduces
#     the schedules block in some bank layouts.
_AUDITOR_END_RE = re.compile(
    r"^(\s*)("
    r"(consolidated|standalone)?\s*balance\s+sheet"
    r"|(consolidated|standalone)?\s*statement\s+of\s+(the\s+)?profit\s+(and|&)\s+loss"
    r"|(consolidated|standalone)?\s*profit\s+(and|&)\s+loss\s+(account|statement)"
    r"|(consolidated|standalone)?\s*statement\s+of\s+cash\s+flows?"
    r"|(consolidated|standalone)?\s*cash\s+flow\s+statement"
    r"|statement\s+of\s+changes\s+in\s+equity"
    r"|(standalone|consolidated)\s+financials?\b"
    r"|schedule\s+\d+"
    r")",
    re.IGNORECASE,
)


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
                # Exclude Annexure A / B / etc. sub-sections of the IAR from
                # being picked as the auditor_report section start — they're
                # sub-sections (CARO / Internal Financial Controls report),
                # not the main IAR body.
                if canonical == "auditor_report" and _AUDITOR_EXCLUDE_RE.search(text):
                    matched_heading_ids.add(h["char_offset"])
                    break
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
            end = _find_section_end(md, headings, h, canonical=canonical, all_compiled=compiled)
            scored.append((end - h["char_offset"], h, end))
        if canonical == "auditor_report":
            # IAR-specific scoring: prefer candidates whose body looks like
            # the real IAR (contains Opinion + Basis for Opinion + Key Audit
            # Matters within the first ~3KB) over candidates whose body is
            # an Annexure list of subsidiaries / running-header repeat.
            # Without this rule, SBIN FY25 picks a 88K "Independent Auditors'
            # Report" → "Annexure A: List of entities consolidated" slice
            # (zero KAMs, zero Opinion) over the 12.7K real IAR slice.
            scored.sort(
                key=lambda t: (_iar_substantive_score(md, t[1]["char_offset"], t[2]), t[0]),
                reverse=True,
            )
        else:
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


# IAR-substance markers — phrases the real IAR body contains within its
# first few KB but an Annexure-list / running-header-repeat slice does not.
# Used by `_iar_substantive_score` to demote candidates whose body is an
# Annexure list of subsidiaries (SBIN FY25 problem case).
_IAR_SUBSTANCE_RE = re.compile(
    r"\b("
    r"basis\s+for\s+opinion"
    r"|key\s+audit\s+matter"
    r"|emphasis\s+of\s+matter"
    r"|going\s+concern"
    r"|in\s+our\s+opinion"
    r"|we\s+have\s+audited"
    r"|true\s+and\s+fair\s+view"
    r")\b",
    re.IGNORECASE,
)

# Window size for the substance check — first ~6 KB of the candidate slice.
# Large enough that a real IAR's "Basis for Opinion" / "Key Audit Matters"
# headings fall inside (they're typically within 2-4 KB of the start), but
# small enough that the score won't be inflated by stray late-section matches.
_IAR_SUBSTANCE_WINDOW = 6_000


def _iar_substantive_score(md: str, char_start: int, char_end: int) -> int:
    """Return a coarse score of how IAR-substantive a candidate slice is.

    Counts distinct substance markers in the first 6KB of the slice. Real
    IAR bodies hit 3-5 markers (Opinion / Basis for Opinion / KAMs / true
    and fair view); Annexure-list slices hit 0. Used to break ties when
    multiple "Independent Auditor['s|s'] Report" headings exist (running-
    header pollution + actual IAR header).
    """
    window_end = min(char_start + _IAR_SUBSTANCE_WINDOW, char_end)
    window = md[char_start:window_end]
    return len(set(m.group(1).lower() for m in _IAR_SUBSTANCE_RE.finditer(window)))


def _find_section_end(
    md: str,
    headings: list[dict],
    h: dict,
    canonical: str | None = None,
    all_compiled: dict[str, list[re.Pattern]] | None = None,
) -> int:
    """Return char offset where this section ends.

    Default: start of next same-or-higher-level heading (works for most
    sections that nest sub-headings cleanly under their own opener).

    Special case for `auditor_report`: the IAR opener is L2 in most ARs
    but the IAR body itself fans out into many L2 sub-headings (Opinion,
    Basis for Opinion, Key Audit Matters, Other Information, …) so the
    default rule over-cuts the section to the first sub-heading. Instead,
    end at the first downstream heading that EITHER:
      - matches a financial-statements anchor (Balance Sheet, P&L, Cash
        Flow, Statement of Changes in Equity) — this is what follows the
        IAR in every Indian AR, OR
      - matches a DIFFERENT canonical section (BRSR, Corporate Governance,
        etc.) — for layouts where the IAR is followed by another report.
    Falls back to default behaviour if neither anchor is found.
    """
    h_idx = headings.index(h)
    if canonical == "auditor_report":
        for fwd in headings[h_idx + 1:]:
            text = fwd["text"]
            if _AUDITOR_END_RE.search(text):
                return fwd["char_offset"]
            if all_compiled is not None:
                for other, other_rxs in all_compiled.items():
                    if other == canonical:
                        continue
                    if any(rx.search(text) for rx in other_rxs):
                        # Skip Annexure-A-style sub-headings — they're not
                        # "other sections", they're part of the IAR.
                        if other == "auditor_report":
                            continue
                        return fwd["char_offset"]
        return len(md)

    end = len(md)
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
