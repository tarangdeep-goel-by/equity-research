## Conglomerate / Multi-Segment Mode (Auto-Detected)

This company operates across multiple distinct business segments. Single-segment valuation frameworks give misleading results because they blend fundamentally different businesses.

**Sum-of-the-Parts (SOTP) Valuation — The Right Framework**
Conglomerates need segment-level valuation because blending all segments into one PE or EV/EBITDA produces a meaningless average:
- Identify each business segment and its revenue/EBIT contribution
- Value each segment using peer multiples from pure-play comparables
- Apply 15-25% holding company discount to aggregate value
- If segment data is unavailable from tools, state explicitly and pose as open question

**Key Risks for Conglomerates:**
- Cross-subsidization between segments (profitable segment funds unprofitable growth)
- Capital allocation opacity (which segment gets capex priority?)
- Consolidated metrics hide segment-level deterioration (aggregate margins may look stable while one segment collapses)

**Metrics that mislead for conglomerates:** Consolidated PE and consolidated EV/EBITDA blend segment multiples and produce averages that don't reflect any individual business's reality.

**Emphasize:** Segment-level EBIT margins, segment growth rates, capital allocation by segment, demerger/listing potential for valuable subsidiaries.

## SOTP Discipline (new)

Any conglomerate report (business or valuation) without a SOTP table is structurally incomplete. `get_valuation(section='sotp')` is mandatory for conglomerate coverage. If it returns empty, manual SOTP per the shared-preamble A1.4 tenet is mandatory — use `get_company_context(section='subsidiaries')` + `get_fundamentals(section='revenue_segments')` per subsidiary or segment.

Subsidiary market cap refresh: auto-SOTP may be stale for recently-listed subsidiaries (e.g., HDB Financial Services listed Jul 2025, NTPCGREEN Energy listed 2025, Adani Green / Adani Power / Adani Ports existing listings). Cross-check `get_valuation(sotp)` output against `get_market_context(section='peer_metrics')` or direct symbol lookup when a subsidiary is publicly listed. If the auto-SOTP is stale or missing a listed subsidiary, annotate and recompute the SOTP line.

## SOTP Verification — Subsidiary vs Promoter-Group Sibling (Cross-Agent, Mandatory)

Before including any listed entity in a SOTP / NAV, confirm the **company itself holds the stake** — i.e. the entity appears in the company's **AOC-1 / consolidated entity list / balance-sheet investments**, NOT merely the promoter group. A listed entity under common family / trust control (a "sister" company) is **NOT a subsidiary** and must **NOT** be summed into NAV. Common family ownership ≠ company ownership: the parent's shareholders have no claim on a sister entity's value unless the parent itself owns equity in it.

If the auto-SOTP tool (`get_valuation(section='sotp')`) lists promoter-group siblings rather than the company's own holdings, **discard those rows and rebuild the SOTP from the company's own segments**: value the company's own operating verticals (segment EBITDA × peer/transaction multiples for unlisted; market cap × stake % only for subsidiaries the company directly holds). Verify each line against `get_company_context(section='filings', sub_section='notes_to_accounts')` (subsidiary / associate schedule, AOC-1) before counting it. State explicitly which entities you included and excluded, and why.
