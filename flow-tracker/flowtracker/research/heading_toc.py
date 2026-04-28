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
from collections import Counter
from typing import Iterable

logger = logging.getLogger(__name__)


# HTML-entity normalization for heading match. Docling sometimes emits the
# literal entity `&amp;` instead of `&` in headings (ICICIBANK FY25, VEDL FY25
# - "MANAGEMENT DISCUSSION &amp; ANALYSIS"). Aliases below use bare `&`, so
# we pre-normalize heading text before matching. Body text is unaffected.
_HTML_AMP_RE = re.compile(r"&amp;", re.IGNORECASE)


def _norm_html_entities(text: str) -> str:
    """Convert &amp; -> & for matching only. Cheap, safe, idempotent."""
    return _HTML_AMP_RE.sub("&", text)


# Canonical AR sections + alias regexes.
# Order matters when sections nest (e.g. "Notes to Financial Statements" must match
# before "Financial Statements"). Aliases use case-insensitive whole-word matching.
AR_SECTIONS: dict[str, list[str]] = {
    "chairman_letter": [
        r"chairman'?s?\s+(letter|message|statement|speech|address|communique|note|remarks)",
        r"chairperson'?s?\s+(letter|message|speech|address|communique|note|remarks)",
        r"letter\s+from\s+the\s+(chairman|chairperson)",
        # SUNPHARMA FY25: "Chairman and Managing Director's Message" — joint
        # title where the chairman is also the MD. The trailing possessive
        # belongs to "Director's", not "Chairman's", so the simple alias
        # above misses it.
        r"chairman\s+(and|&)\s+(managing\s+director|md|ceo|co-?chair(man|person)?)'?s?\s+(letter|message|statement|speech|address|communique|note|remarks)",
        # ICICIBANK FY25 / DRREDDY FY25 / VEDL FY25 / many integrated-reporting
        # ARs use "Message from the Chairman" rather than "Chairman's Message".
        r"message\s+from\s+(the\s+)?(chairman|chairperson|founders?|chair\b|co-?chair(man|person)?)",
        r"message\s+from\s+(the\s+)?chair(man|person)?\s*(and|&)\s*(co-?chair(man|person)?|md|managing\s+director|ceo)",
        # POLICYBZR FY25 — startup integrated-reports use founder-letter
        # in lieu of a chairman letter. Treat as the canonical opener.
        r"message\s+from\s+(the\s+)?founders?",
        r"from\s+the\s+(chairman'?s?|chairperson'?s?|founder'?s?)\s+desk",
    ],
    "ceo_letter": [
        r"(ceo|managing\s+director|md)'?s?\s+(letter|message|statement|review|speech|address|communique|remarks|speak)",
        r"letter\s+from\s+the\s+(ceo|managing\s+director|md)",
        r"message\s+from\s+(the\s+)?(ceo|managing\s+director|md\b)",
        r"\bceo\s+speak\b",
    ],
    "mdna": [
        r"management'?s?\s+discussion\s+(and|&)\s+analysis",
        r"\bmd\s*&\s*a\b",
        r"\bmd&a\b",
        r"discussion\s+and\s+analysis\s+report",
        # ICICIBANK FY25 banking layout interleaves "OPERATING RESULTS DATA"
        # under MD&A as a parallel sub-heading. Add operating-results variants.
        r"operating\s+results?\s+(review|data|analysis)",
        r"business\s+performance\s+review",
        r"management'?s?\s+discussion\s+of\s+performance",
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
        # Standard "Notes to the [Consolidated|Standalone] Financial Statements"
        # (ETERNAL FY25, DRREDDY FY25, POLICYBZR FY25, SUNPHARMA FY25). Extended
        # with `accounts` because some banks use "Notes to Accounts" as the
        # equivalent heading (HDFCBANK FY25, ICICIBANK FY25 schedule-18).
        r"notes\s+to\s+(the\s+)?(consolidated\s+|standalone\s+)?(financial\s+statements|accounts)",
        # "Notes forming part of [the] [Consolidated|Standalone] [Financial
        # Statements|Accounts]" — NESTLEIND FY25, TCS FY25, ICICIBANK FY25
        # ("NOTES FORMING PART OF THE ACCOUNTS"). Earlier alias only allowed
        # `financial statements`; extend to `accounts` and prefix qualifiers.
        r"notes\s+forming\s+part\s+of\s+(the\s+)?(consolidated\s+|standalone\s+)?(financial\s+statements|accounts)",
        # "Notes on the [Consolidated|Standalone] Financial Statements" —
        # BANKBARODA FY25 ("Schedule-19 : Notes on the Consolidated Financial
        # Statements"). The schedule prefix is captured by the alias below.
        r"notes\s+on\s+(the\s+)?(consolidated\s+|standalone\s+)?financial\s+statements",
        # Schedule-prefixed bank notes: "Schedule 18: Notes to Accounts" (SBIN),
        # "Schedule-19 : Notes on the Consolidated Financial Statements"
        # (BANKBARODA), Schedule-numbered notes blocks (HDFCBANK).
        r"schedule[\s\-]?\d+\s*[:.\s\-]+\s*notes\s+(to|on|forming\s+part\s+of)",
        # NOTE: `significant accounting policies` was previously listed as a
        # notes alias, but it consistently matched the wrong section
        # (BANKBARODA/SBIN/HDFCBANK/ICICIBANK all had < 200-char SAP slices and
        # missed the real notes data). Removed as part of Track B 2026-04-28.
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
        # AS-18 / Ind AS 24 disclosure heading variants used by banks (BANKBARODA
        # FY25 "12.5 Related Party Disclosures (AS-18)", SBIN FY25 "2.4 AS-18
        # Related Party Disclosures") and consolidated-notes sections in
        # corporates (HDFCBANK note 29/47, HINDALCO note 30, NESTLEIND note 41,
        # HINDUNILVR note 44 — all "Related party disclosures").
        r"related\s+party\s+disclosures?",
        # SEBI Listing-Reg / Companies-Act AOC-2 wrapper headings — observed in
        # HDFCBANK ("Particulars of Contracts or Arrangements with Related
        # Parties"), INFY ("Particulars of contracts/arrangements made with
        # related parties"), POLICYBZR ("PARTICULARS OF CONTRACTS OR ARRANGEMENT
        # WITH RELATED PARTIES").
        r"particulars\s+of\s+contracts?\s*"
        r"(or|/|and)?\s*arrangements?\s+(made\s+)?(with|for)\s+related\s+parties?",
        # Schedule III / consolidated-notes lead-with-transactions form: ETERNAL
        # FY25 "ix. Transactions with related parties", TCS FY25 "19.
        # Transactions with related parties".
        r"transactions\s+with\s+related\s+parties?",
        # Form AOC-2 standalone heading — ICICIBANK FY25, HINDUNILVR FY25 both
        # surface "Form No. AOC-2" / "FORM NO. AOC-2" as a top-level heading
        # separate from the wrapping Particulars-of-Contracts heading.
        r"form\s+(no\.?\s+)?aoc[-\s]?2",
    ],
    "esop_disclosure": [
        r"employee\s+stock\s+option\s+(plan|scheme)\s+disclosure",
        r"\besop\b\s+disclosure",
        r"share[\s-]?based\s+payments?\s+disclosure",
    ],
    # Pharma-specific section — Wave 4-5 P2 addition 2026-04-25 to surface
    # USFDA inspection outcomes, warning-letter status, ANDA pipeline, and
    # Drug Master File disclosures. Pharma ARs put this under varied headings
    # ("Regulatory Compliance" — SUNPHARMA / "FDA Inspections" — DRREDDY /
    # standalone sub-section under MD&A in smaller caps). Distinct from
    # `risk_management` which catches generic operational + financial risk;
    # this is specifically the USFDA/EMA disclosure pharma agents need.
    "usfda_compliance": [
        r"(us\s*)?fda\s+inspections?",
        r"regulatory\s+compliance(\s+update|\s+status)?",
        r"quality\s+compliance(\s+update|\s+status)?",
        r"drug\s+master\s+files?",
        r"\banda\s+(filings?|approvals?|pipeline)",
        r"u\.?s\.?\s+fda(\s+update|\s+status)?",
    ],
    # Five/Ten/Decade-of financial highlights table — Schedule III mandates
    # restating prior years when bucketing changes, so the table is internally
    # consistent (canonical restated trend source — see
    # plans/screener-data-discontinuity.md, Strategy 2). Headings vary widely
    # across companies; cover variants observed in HDFCBANK, INFY, TCS,
    # HINDUNILVR, SUNPHARMA, NESTLEIND, ICICIBANK, SBIN cohort.
    "five_year_summary": [
        r"(five|5)\s*[-–]?\s*year\s+(financial\s+)?(highlights?|track\s+record|performance|snapshot)",
        r"(ten|10)\s*[-–]?\s*year\s+(financial\s+)?(highlights?|track\s+record|performance|snapshot)",
        r"decade\s+of\s+(highlights?|performance|growth)",
        r"long[\s-]term\s+track\s+record",
        r"performance\s+trend\s+[-–]\s+\d+\s+years?",
        r"key\s+financial\s+indicators?\s*[:\-–]\s*last\s+\d+\s+years?",
        r"key\s+performance\s+indicators?\s*[-–:]?\s*\d+\s+years?",
        r"financial\s+highlights\s+[-–:]\s+(last\s+)?\d+\s+years?",
    ],
}


# Headings that look like they match `corporate_governance` but are actually
# ESG / sustainability-flavoured governance content, NOT the SEBI-mandated
# Corporate Governance Report. Picking these would route ESG governance prose
# (whistleblower channels, ESG-policy summaries) into the CG agent instead of
# the actual board / committees / audit-committee / nomination-remuneration
# disclosure.
#
# ICICIBANK FY25: only "ESG REPORT | 2024-25" matched the bare
# `governance\s+report` alias because the real CORPORATE GOVERNANCE heading
# was followed by a running-header `BOARD'S REPORT` that cut its slice to
# 615 chars and lost the largest-section-wins race against the 439-char ESG
# report (which had no other CG candidates to compete with). The exclude
# rule below removes ESG-governance candidates from the candidate pool.
_CG_EXCLUDE_RE = re.compile(
    r"environmental[,\s]+social\b"
    r"|\besg\b"
    r"|sustainability\s+report"
    # NYSE corporate-governance compliance certificate (DRREDDY FY25 ADR
    # filing) — describes how the company complies with NYSE CG vs SEBI CG.
    # Useful context but NOT the SEBI Corporate Governance Report.
    r"|\bnyse\b.*corporate\s+governance"
    r"|compliance\s+report\s+on\s+the\s+nyse"
    # "Compliance, Ethics, and Corporate governance:" colon-style preamble in
    # DRREDDY FY25 strategic-review section — extends 269K into the directors
    # report and downstream financial statements. Not the CG report itself.
    r"|^compliance,\s+ethics,?\s+and\s+corporate\s+governance",
    re.IGNORECASE,
)


# Headings that mark the end of mdna / corporate_governance sections. Mirrors
# `_AUDITOR_END_RE`: both sections (like the IAR) contain dozens of L2
# sub-headings (Industry Overview, Operating Performance, Risks, Outlook for
# MD&A; Audit Committee, Nomination & Remuneration, CSR for CG). The default
# same-or-higher-level end heuristic over-cuts the section to its first
# sub-heading. Instead, end at the next financial-statement anchor or a
# non-self canonical-section heading — whichever comes first.
_MDNA_CG_END_RE = re.compile(
    r"^(\s*)("
    r"(consolidated|standalone)?\s*balance\s+sheet"
    r"|(consolidated|standalone)?\s*statement\s+of\s+(the\s+)?profit\s+(and|&)\s+loss"
    r"|(consolidated|standalone)?\s*profit\s+(and|&)\s+loss\s+(account|statement)"
    r"|(consolidated|standalone)?\s*statement\s+of\s+cash\s+flows?"
    r"|(consolidated|standalone)?\s*cash\s+flow\s+statement"
    r"|(standalone|consolidated)\s+financials?\b"
    r")",
    re.IGNORECASE,
)


# End-anchors for chairman_letter / ceo_letter sections — when the letter is
# embedded in an integrated-reporting layout, the next big-section divider is
# typically another personalized letter (CFO message, founders message, CEO
# of subsidiary), or an integrated-report section header (Performance Review,
# Strategic Review, Approach to Reporting, Board of Directors). Without this
# the chairman_letter slice can run 100K+ into Governance content (DRREDDY
# FY25 problem).
_LETTER_END_RE = re.compile(
    r"^(\s*)("
    r"message\s+from\s+(the\s+)?cfo"
    r"|cfo'?s?\s+(message|letter|statement|review|note)"
    r"|message\s+from\s+(the\s+)?coo"
    r"|board\s+of\s+directors\b"
    r"|management\s+council\b"
    r"|approach\s+to\s+reporting"
    r"|(our\s+)?strategic\s+review\b"
    r"|(our\s+)?performance\s+review\b"
    r"|key\s+performance\s+indicators\b"
    r"|(our\s+)?value\s+creation\s+model\b"
    r"|stakeholder\s+engagement\b"
    r")",
    re.IGNORECASE,
)


# CG-substance markers — phrases the real CG section contains but tangential
# governance-flavoured candidates (ESG governance, board-of-directors photo
# captions, NYSE-compliance certificates) do not. Used to break ties when
# multiple `corporate_governance` candidates exist.
#
# DRREDDY FY25 ranks "Compliance, Ethics, and Corporate governance:" (270K of
# adjacent CSR + HR content) as the largest candidate — but the real CG section
# is a 58K block headed "CORPORATE GOVERNANCE REPORT" containing the audit
# committee, NRC, risk management committee, and director DINs. Substance
# scoring promotes the right candidate even when its size loses the largest
# heuristic.
_CG_SUBSTANCE_RE = re.compile(
    r"\b("
    r"audit\s+committee"
    r"|nomination\s+(and|&)\s+remuneration\s+committee"
    r"|stakeholders?\s+relationship\s+committee"
    r"|risk\s+management\s+committee"
    r"|csr\s+committee"
    r"|board\s+evaluation"
    r"|independent\s+director"
    r"|composition\s+of\s+the\s+board"
    r"|familiarisation\s+programme"
    r"|whistle\s*blower"
    r"|related\s+party\s+transaction"
    r")\b",
    re.IGNORECASE,
)
_CG_SUBSTANCE_WINDOW = 30_000


# MD&A-substance markers — phrases real MD&A bodies contain but a TOC entry
# or running-header repeat does not. Distinguishes the substantive 30K MDA
# from a 200-char forward-reference heading.
_MDNA_SUBSTANCE_RE = re.compile(
    r"\b("
    r"industry\s+overview"
    r"|industry\s+structure"
    r"|opportunities\s+and\s+threats"
    r"|business\s+performance"
    r"|operating\s+performance"
    r"|operational\s+performance"
    r"|outlook"
    r"|risks?\s+and\s+concerns?"
    r"|internal\s+control\s+systems?"
    r"|material\s+developments?\s+in\s+human\s+resource"
    r"|key\s+financial\s+ratios?"
    r"|economic\s+overview"
    r"|segment\s+(performance|results?|review)"
    r")\b",
    re.IGNORECASE,
)
_MDNA_SUBSTANCE_WINDOW = 30_000


# Chairman / CEO letter substance markers — phrases that distinguish a real
# chairman speech / CEO message from a TOC entry, glossary, or investor-
# relations admin section (e.g. "Chairman Communique" in VEDL FY25 is the
# IR-correspondence label, not the actual speech). Real letters open with
# "Dear Shareholders" / "Dear Stakeholders", reference the FY, narrate the
# year ahead / behind, and close with the signatory.
_CHAIRMAN_SUBSTANCE_RE = re.compile(
    r"\b("
    r"dear\s+(shareholder|stakeholder|investor|member)"
    r"|the\s+year\s+(under\s+review|ahead|gone\s+by)"
    r"|i\s+am\s+(pleased|delighted|honoured)"
    r"|looking\s+ahead"
    r"|during\s+the\s+(year|fiscal|financial\s+year)"
    r"|yours\s+(sincerely|faithfully|truly)"
    r"|on\s+behalf\s+of\s+the\s+(board|management)"
    r"|fy\s*20\d{2}"
    r"|fy\s*\d{2}"
    r")\b",
    re.IGNORECASE,
)
_CHAIRMAN_SUBSTANCE_WINDOW = 12_000


# Track B 2026-04-28: data-density score for problem sections (segmental,
# related_party, notes_to_financials, financial_statements). When multiple
# candidates exist, prefer the one whose body actually contains a numerical
# table (high digit-run count) over candidates that are policy descriptions
# or forward-references. Used as primary sort key with section-size as
# tie-breaker.
#
# Why: HDFCBANK FY25 has TWO headings matching `related_party`: a 1633ch
# policy block ("Related Party Transactions" — Director's-Report flag) and a
# data-rich block under "29. Related party disclosures" (note 29). Without
# density scoring, size-sort picks the policy block. The data block has
# ~50× more numeric content. Same pattern observed for VEDL segmental,
# ICICIBANK segmental, NESTLEIND segmental — heading-only candidates lose to
# data-table candidates once we score by density.
_DATA_DIGIT_RUN_RE = re.compile(r"[\d,]{4,}")


def _data_density_score(md: str, char_start: int, char_end: int) -> int:
    """Count digit runs (4+ consecutive digit/comma chars) in the candidate
    body. Capped at 200 to avoid one giant table dominating tie-breaks. Used
    by Track B problem-section tie-breakers.
    """
    body = md[char_start:char_end]
    return min(len(_DATA_DIGIT_RUN_RE.findall(body)), 200)


def _running_header_set(headings: list[dict], threshold: int = 5) -> set[str]:
    """Return the set of normalized heading texts that appear `threshold`+
    times in the heading list — these are page-running headers (e.g. ICICIBANK
    FY25 has BOARD'S REPORT 48x as a page header). When computing section-end
    boundaries we must skip these so a single repeated header doesn't truncate
    the real section to a few hundred chars.

    Normalization: lowercase + html-entity normalize + collapse whitespace.
    """
    norm = lambda s: re.sub(r"\s+", " ", _norm_html_entities(s).strip().lower())
    counter = Counter(norm(h["text"]) for h in headings)
    return {text for text, count in counter.items() if count >= threshold}


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

# Track B exclusion patterns (added 2026-04-28). These reject heading
# candidates that match canonical aliases but represent a related policy/
# notice/AGM-resolution rather than the actual data section. Without these,
# heading_toc consistently mis-routes to the wrong section even though the
# alias technically fits.
#
# `_SEGMENTAL_POLICY_EXCLUDE_RE`: ETERNAL FY25 heading
# "n) Segment reporting" is the lettered accounting-policy entry inside the
# Significant Accounting Policies sub-section, NOT the segment data. The
# real data heading is "35 Segment information" hundreds of pages later.
# Pattern: lower-case-letter + closing-paren + space (a/b/c/.../n/etc.).
# Same applies to `notes_to_financials` matches that hit a policy entry
# letter inside SAP.
_POLICY_LETTER_PREFIX_RE = re.compile(
    r"^\s*[a-z]\)\s+",
    re.IGNORECASE,
)

# `_RELATED_PARTY_AGM_EXCLUDE_RE`: TCS FY25 picked an 82KB AGM-notice block
# led by "To approve material related party transactions with Tata Capital
# Limited"; INFY FY25 picked "Item no. 5 - Material related party
# transactions of Infosys Limited and ...". Both are agenda items in the
# AGM notice, not the AS-18 disclosure. Pattern: imperative "To approve"
# OR "Item no.\s*\d+" prefix.
_RELATED_PARTY_AGM_EXCLUDE_RE = re.compile(
    r"^\s*("
    r"to\s+approve\s+(material\s+)?related\s+party"
    r"|item\s+no\.?\s*\d+\s*[-–:]\s*material\s+related\s+party"
    r")",
    re.IGNORECASE,
)

# `_NOTES_POLICY_EXCLUDE_RE`: Significant Accounting Policies headings
# (sometimes prefixed by "Schedule 17"). These were previously matched as
# `notes_to_financials` causing 4 cohort stocks to land < 200-char SAP
# slices. Removed from the alias list in Track B.5 but also reject here as
# defense-in-depth in case the alias re-appears.
_NOTES_POLICY_EXCLUDE_RE = re.compile(
    r"^\s*(schedule[\s\-]?\d+\s*[:.\s\-]+\s*)?significant\s+accounting\s+policies",
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

    # Detect repeated page running-headers (e.g. ICICIBANK FY25's 48x
    # "BOARD'S REPORT" page header). These pollute end-detection: the next
    # heading after the real CG section is a running-header repeat that
    # matches the directors_report alias and prematurely truncates the slice.
    running_headers = _running_header_set(headings)

    # Collect ALL candidate matches per canonical (multiple per name allowed).
    candidates: dict[str, list[dict]] = {}
    matched_heading_ids: set[int] = set()  # heading char_offsets we've matched, to count unmapped

    for h in headings:
        # Normalize HTML entities (&amp; -> &) so headings like
        # "MANAGEMENT DISCUSSION &amp; ANALYSIS" still match the bare-`&` aliases.
        text = _norm_html_entities(h["text"])
        for canonical, regexes in compiled.items():
            if any(rx.search(text) for rx in regexes):
                # Exclude Annexure A / B / etc. sub-sections of the IAR from
                # being picked as the auditor_report section start — they're
                # sub-sections (CARO / Internal Financial Controls report),
                # not the main IAR body.
                if canonical == "auditor_report" and _AUDITOR_EXCLUDE_RE.search(text):
                    matched_heading_ids.add(h["char_offset"])
                    break
                # Exclude ESG / sustainability "governance report" headings
                # from being picked as the corporate_governance start.
                if canonical == "corporate_governance" and _CG_EXCLUDE_RE.search(text):
                    matched_heading_ids.add(h["char_offset"])
                    break
                # Track B 2026-04-28: reject lettered accounting-policy entries
                # ("n) Segment reporting" — ETERNAL FY25) when matching
                # `segmental` or `notes_to_financials`. Real data tables don't
                # have this prefix.
                if canonical in ("segmental", "notes_to_financials") \
                        and _POLICY_LETTER_PREFIX_RE.match(text):
                    matched_heading_ids.add(h["char_offset"])
                    break
                # Track B 2026-04-28: reject AGM-notice resolution agenda items
                # (TCS "To approve material RPT with Tata Capital", INFY
                # "Item no. 5 - Material related party transactions of Infosys
                # Limited and ..."). These are board agenda proposals, not the
                # AS-18 disclosure.
                if canonical == "related_party" \
                        and _RELATED_PARTY_AGM_EXCLUDE_RE.match(text):
                    matched_heading_ids.add(h["char_offset"])
                    break
                # Track B 2026-04-28: reject SAP headings even if they sneak
                # past the alias list (defense-in-depth — alias removed in B.5
                # but old aliases or new heading variants might re-introduce
                # the issue).
                if canonical == "notes_to_financials" \
                        and _NOTES_POLICY_EXCLUDE_RE.match(text):
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
            end = _find_section_end(
                md, headings, h, canonical=canonical, all_compiled=compiled,
                running_headers=running_headers,
            )
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
        elif canonical == "corporate_governance":
            # CG-specific tie-break: prefer candidates whose body contains
            # the SEBI-mandated CG markers (Audit Committee, NRC, RMC, CSR,
            # board evaluation, independent directors, DIN listings).
            # DRREDDY FY25 problem: a 270K "Compliance, Ethics, and Corporate
            # governance:" candidate would beat the real 58K CG report; the
            # substantive score promotes the real one.
            scored.sort(
                key=lambda t: (_cg_substantive_score(md, t[1]["char_offset"], t[2]), t[0]),
                reverse=True,
            )
        elif canonical == "mdna":
            # MD&A-specific tie-break: prefer candidates whose body actually
            # contains MD&A subject matter (Industry Overview, Operating
            # Performance, Outlook, Segment Performance) over forward-reference
            # blurbs and TOC entries. POLICYBZR FY25 has the real 27K MD&A
            # block first; substantive scoring + largest-wins both pick it.
            scored.sort(
                key=lambda t: (_mdna_substantive_score(md, t[1]["char_offset"], t[2]), t[0]),
                reverse=True,
            )
        elif canonical in ("chairman_letter", "ceo_letter"):
            # Chairman/CEO-specific tie-break: prefer candidates whose body
            # contains real letter prose (Dear Shareholders, the year under
            # review, signatory clauses) over IR-correspondence sections
            # labelled "Chairman Communique" (VEDL FY25) or glossary/TOC
            # entries that happen to share keywords.
            scored.sort(
                key=lambda t: (
                    _chairman_substantive_score(md, t[1]["char_offset"], t[2]),
                    t[0],
                ),
                reverse=True,
            )
        elif canonical in ("segmental", "related_party",
                           "notes_to_financials", "financial_statements"):
            # Track B 2026-04-28: data-density tie-break for problem sections.
            # Prefer candidates whose body actually contains numerical tables
            # over policy descriptions or forward-references.
            #   - HDFCBANK FY25 related_party: 1633ch policy block vs richer
            #     "29. Related party disclosures" block — density picks the
            #     latter.
            #   - VEDL FY25 segmental: "5 Segment Information" header (26ch)
            #     loses to a candidate further down with the actual table.
            #   - ICICIBANK FY25 segmental: "SEGMENT INFORMATION" 578ch vs a
            #     numbered note candidate with the data.
            #   - NESTLEIND FY25 segmental: TOC entry (370ch) loses to the
            #     data block.
            scored.sort(
                key=lambda t: (_data_density_score(md, t[1]["char_offset"], t[2]), t[0]),
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


def _cg_substantive_score(md: str, char_start: int, char_end: int) -> int:
    """Distinct CG-substance markers within the first 30KB of the slice.

    Real Corporate Governance Report sections contain 4-7 of: Audit Committee,
    Nomination & Remuneration, Stakeholders Relationship, Risk Management
    Committee, CSR Committee, Board Evaluation, Independent Director,
    Composition of the Board, Familiarisation Programme, Whistle Blower,
    Related Party Transaction. Tangential candidates (ESG-governance prose,
    NYSE compliance certificate, photo captions) hit 0-1.
    """
    window_end = min(char_start + _CG_SUBSTANCE_WINDOW, char_end)
    window = md[char_start:window_end]
    return len(set(m.group(1).lower() for m in _CG_SUBSTANCE_RE.finditer(window)))


def _mdna_substantive_score(md: str, char_start: int, char_end: int) -> int:
    """Distinct MD&A-substance markers within the first 30KB of the slice.

    Real MD&A bodies contain 3+ of: Industry Overview / Structure, Operating
    Performance, Outlook, Risks and Concerns, Internal Control Systems, Key
    Financial Ratios, Segment Performance. TOC entries and forward-reference
    blurbs hit 0.
    """
    window_end = min(char_start + _MDNA_SUBSTANCE_WINDOW, char_end)
    window = md[char_start:window_end]
    return len(set(m.group(1).lower() for m in _MDNA_SUBSTANCE_RE.finditer(window)))


def _chairman_substantive_score(md: str, char_start: int, char_end: int) -> int:
    """Distinct chairman-letter substance markers within the first 12KB.

    Real chairman / CEO letters contain 2-4 of: 'Dear Shareholders',
    'the year under review', 'I am pleased', 'looking ahead', 'during the
    year', 'yours sincerely', signatory clauses. IR-correspondence sections
    labelled 'Chairman Communique' (VEDL FY25) hit 0.
    """
    window_end = min(char_start + _CHAIRMAN_SUBSTANCE_WINDOW, char_end)
    window = md[char_start:window_end]
    return len(set(m.group(1).lower() for m in _CHAIRMAN_SUBSTANCE_RE.finditer(window)))


def _find_section_end(
    md: str,
    headings: list[dict],
    h: dict,
    canonical: str | None = None,
    all_compiled: dict[str, list[re.Pattern]] | None = None,
    running_headers: set[str] | None = None,
) -> int:
    """Return char offset where this section ends.

    Default: start of next same-or-higher-level heading (works for most
    sections that nest sub-headings cleanly under their own opener).

    Special cases for `auditor_report`, `mdna`, `corporate_governance`:
    these sections each contain many L2 sub-headings of their own (the IAR
    has Opinion / KAMs; MD&A has Industry Overview / Outlook; CG has Audit
    Committee / NRC) so the default rule over-cuts to the first sub-heading.
    Instead, end at the first downstream heading that EITHER:
      - matches a financial-statements anchor (Balance Sheet, P&L, Cash
        Flow, Statement of Changes in Equity) — what typically follows
        these reports, OR
      - matches a DIFFERENT canonical section (skipping running-header
        repeats — ICICIBANK FY25 has BOARD'S REPORT 48x as a page running
        header which would otherwise truncate CG to 615 chars).
    Falls back to default behaviour if neither anchor is found.
    """
    h_idx = headings.index(h)
    running_headers = running_headers or set()

    def _is_running_header(text: str) -> bool:
        norm = re.sub(r"\s+", " ", _norm_html_entities(text).strip().lower())
        return norm in running_headers

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

    if canonical in ("mdna", "corporate_governance", "chairman_letter", "ceo_letter"):
        is_letter = canonical in ("chairman_letter", "ceo_letter")
        for fwd in headings[h_idx + 1:]:
            text = _norm_html_entities(fwd["text"])
            if _MDNA_CG_END_RE.search(text):
                return fwd["char_offset"]
            if is_letter and _LETTER_END_RE.search(text):
                return fwd["char_offset"]
            if all_compiled is not None:
                hit = None
                for other, other_rxs in all_compiled.items():
                    if other == canonical:
                        continue
                    if any(rx.search(text) for rx in other_rxs):
                        hit = other
                        break
                if hit is not None:
                    # Skip page-running-header repeats (ICICIBANK BOARD'S
                    # REPORT 48x). A single repeat would otherwise prematurely
                    # truncate the section.
                    if _is_running_header(fwd["text"]):
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
