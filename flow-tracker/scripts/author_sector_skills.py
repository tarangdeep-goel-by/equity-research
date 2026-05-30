#!/usr/bin/env python3
"""Author new sector_skills/<sector>/ files via Gemini, grounded on existing exemplars.

Usage:  uv run python scripts/author_sector_skills.py <sector>
        uv run python scripts/author_sector_skills.py --list

Reads metals + real_estate skill files as the format/depth reference, sends them
to Gemini (gemini-3.1-pro-preview) with a per-sector seed, and writes the drafted
_shared.md + sector/valuation/financials/risk .md into sector_skills/<sector>/.
Generic consistency/reconciliation/temporal rules live in SHARED_PREAMBLE — Gemini
is told NOT to restate them (4-layer placement discipline).
"""
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "flowtracker" / "research" / "sector_skills"
sys.path.insert(0, str(ROOT))
from flowtracker.research.autoeval.evaluate import _load_gemini_api_key  # noqa: E402

REF_FILES = [
    "metals/_shared.md", "metals/sector.md", "metals/valuation.md",
    "real_estate/_shared.md", "real_estate/sector.md", "real_estate/financials.md",
]

TOOLS = (
    "get_company_context(section='concall_insights'|'sector_kpis'|'info'|'filings'), "
    "get_fundamentals, get_quality_scores, get_peer_sector(section='peer_table'|'benchmarks'), "
    "get_valuation(section='snapshot'|'sotp'), get_fair_value_analysis(section='projections'), "
    "get_estimates, get_events_actions(section='catalysts'|'corporate_actions'|'dividends'), "
    "get_annual_report(section='mdna'|'segmental'|'notes_to_financials'|'risk_management'|'auditor_report'), "
    "get_deck_insights(sub_section='key_metrics'|'segment_performance'|'outlook_and_guidance'), "
    "get_market_context(section='macro'), render_chart, calculate"
)

# Per-sector seed: industries folded in, real Indian listed names, KPI backbone,
# the correct valuation frame, and the key structural risk. Gemini elaborates to
# exemplar depth — the seed keeps it grounded in Indian reality.
SECTORS = {
    "textiles": {
        "industries": "Textile Manufacturing, Apparel Manufacturing, Apparel Retail, Footwear & Accessories, Luxury Goods",
        "examples": "Page Industries, KPR Mill, Trident, Welspun Living, Vardhman Textiles, Gokaldas Exports, "
                    "Vedant Fashions (Manyavar), Aditya Birla Fashion, Raymond, Arvind, Trent",
        "kpis": "capacity utilization %, cotton/yarn realization & cotton-yarn spread, EBITDA/kg, "
                "export vs domestic mix, branded vs commodity (greige/yarn) revenue split, "
                "inventory days & working-capital cycle (structurally high), store count & SSSG (for retail/brand), "
                "PLI participation, China+1 / export-incentive (RoDTEP) exposure",
        "valuation": "Commodity spinners/weavers: EV/EBITDA + P/B near cycle trough (cotton-cycle sensitive). "
                     "Branded plays (Page, Vedant): PE / EV/EBITDA justified by ROCE, brand moat, asset-light franchise. "
                     "Do NOT apply branded-retail multiples to commodity spinners.",
        "risk": "cotton price cycle & inventory MTM, export demand (US/EU retail), forex, "
                "channel inventory, debt in capex-heavy spinners, fashion/style risk for brands",
    },
    "building_materials": {
        "industries": "Building Products & Equipment, Building Materials (cement, tiles, pipes, sanitaryware, boards)",
        "examples": "UltraTech, Ambuja, ACC, Shree Cement, Dalmia Bharat, JK Cement (cement); "
                    "Kajaria, Cera, Astral, Supreme Industries, Finolex Industries, Greenpanel (tiles/pipes/boards)",
        "kpis": "cement: realization/tonne, EBITDA/tonne, capacity utilization %, clinker factor, lead distance, "
                "power & fuel cost/tonne, regional price trend; pipes/tiles: volume growth %, organized-vs-unorganized shift, "
                "PVC-crude (or input) spread, brand premium, dealer/retail network, capacity additions",
        "valuation": "Cement: EV/EBITDA + EV/tonne of capacity (replacement-cost anchor). "
                     "Branded building products (pipes/tiles/adhesives): PE on volume-led compounding + ROCE. "
                     "Cement is regional-cyclical — anchor EV/tonne to the cycle and the asset's replacement cost.",
        "risk": "regional cement overcapacity & price wars, energy/pet-coke cost, real-estate & infra demand cycle, "
                "input (PVC/crude) volatility for pipes, monsoon seasonality, freight cost",
    },
    "packaging": {
        "industries": "Packaging & Containers, Paper & Paper Products, Lumber & Wood Production",
        "examples": "UFlex, EPL Ltd (Essel Propack), AGI Greenpac, Huhtamaki India, TCPL Packaging, Cosmo First, "
                    "Polyplex; JK Paper, West Coast Paper, Century Paper, TNPL (paper)",
        "kpis": "volume growth (tonnes), realization, raw-material (polymer/paper/pulp) cost pass-through lag, "
                "value-added vs commodity mix, capacity utilization %, client concentration (FMCG/pharma anchors), "
                "EBITDA/tonne, sustainability/recyclable-mix shift",
        "valuation": "EV/EBITDA primary (asset-heavy, capacity-driven). Value-added/specialty converters earn a premium "
                     "to commodity board/paper mills. Paper is cyclical (pulp cycle) — P/B floor near trough.",
        "risk": "polymer/pulp price volatility & pass-through lag, client concentration, overcapacity in commodity grades, "
                "import competition, plastic-regulation / sustainability transition, working capital",
    },
    "media": {
        "industries": "Entertainment, Broadcasting, Publishing, Advertising Agencies",
        "examples": "Zee Entertainment, PVR Inox, Sun TV Network, Saregama, Tips Music, Nazara, "
                    "Network18 / TV18, Dish TV, D B Corp, Jagran Prakashan, Navneet Education",
        "kpis": "subscription vs advertising revenue mix, ARPU (DTH/broadcast), viewership/TRP share, "
                "multiplex: occupancy %, ATP (avg ticket price), SPH (spend per head), screen count & footfalls, "
                "content library value & amortization, OTT/digital subscribers, ad-spend cyclicality",
        "valuation": "EV/EBITDA primary. Multiplex: EV/screen + EV/EBITDA. Broadcast/print: PE on ad-cycle-normalized "
                     "earnings. Music/content (Saregama/Tips): content-library IP value + EV/EBITDA on licensing annuity. "
                     "Normalize ad revenue over the cycle; don't capitalize a peak ad-year.",
        "risk": "ad-spend cyclicality (GDP-linked), cord-cutting / OTT disruption to linear TV & DTH, "
                "content cost inflation, regulatory (TRAI tariff order), piracy, box-office hit-or-miss volatility",
    },
    "hospitality": {
        "industries": "Lodging, Restaurants, Travel Services",
        "examples": "Indian Hotels (Taj), EIH (Oberoi), Lemon Tree, Chalet Hotels, Jubilant FoodWorks (Domino's), "
                    "Devyani Intl & Sapphire Foods (KFC/Pizza Hut), Westlife Foodworld (McDonald's), Barbeque Nation, "
                    "IRCTC, Easy Trip Planners, Thomas Cook",
        "kpis": "hotels: RevPAR, ARR (avg room rate), occupancy %, management-contract (asset-light) vs owned keys, "
                "new key signings/pipeline; QSR: SSSG (same-store sales growth), dine-in vs delivery mix, "
                "store additions & gross/restaurant margin, AUV (avg unit volume); travel: booking volumes, take-rate",
        "valuation": "Hotels: EV/EBITDA + EV/key (per-room replacement) — operating leverage makes EBITDA cycle-sensitive. "
                     "QSR: EV/EBITDA + PE, priced on SSSG durability & unit-economics (store-level ROCE & payback). "
                     "Asset-light managers (mgmt contracts) deserve a premium to owned-asset hotels.",
        "risk": "demand cyclicality (discretionary/travel), seasonality, RevPAR/ADR downcycles, new-supply gluts, "
                "QSR: same-store deceleration, input (cheese/wheat) inflation, delivery-aggregator dependence & rentals",
    },
    "logistics": {
        "industries": "Integrated Freight & Logistics, Marine Shipping, Railroads, Trucking, Infrastructure Operations",
        "examples": "Container Corp (Concor), Delhivery, Blue Dart, TCI (Transport Corp), Mahindra Logistics, "
                    "VRL Logistics, Allcargo, Gateway Distriparks, GE Shipping, Cochin Shipyard",
        "kpis": "volumes (TEUs/tonnes/shipments), realization per unit, asset-light vs owned-fleet mix, "
                "network density & fill rate, e-commerce/express exposure, fuel-cost pass-through, "
                "originating vs road-share (rail), warehousing sqft & utilization, working-capital cycle",
        "valuation": "EV/EBITDA primary. Asset-light express/3PL (Delhivery, Blue Dart, TCI): PE on volume-led scaling & "
                     "operating leverage. Asset-heavy (Concor, shipping): EV/EBITDA + P/B; shipping is freight-rate cyclical. "
                     "Don't apply asset-light express multiples to freight-rate-cyclical shipping.",
        "risk": "freight-rate cycle (shipping), fuel cost, e-commerce client concentration & pricing pressure, "
                "competition/discounting (express), DFC & infra-execution dependence (rail), working-capital stretch, capex intensity",
    },
}


def build_prompt(sector: str, seed: dict, refs: str) -> str:
    return f"""You are writing a **sector skill file set** for an Indian-equity multi-agent research system.
These markdown files are injected into specialist LLM agents' system prompts when the
detected sector is `{sector}`. `_shared.md` is loaded for ALL agents; the per-agent files
(sector.md, valuation.md, financials.md, risk.md) are appended only for that agent.

## REFERENCE EXEMPLARS (match this format, depth, and concreteness — these are two existing, eval-tuned sectors)

{refs}

## CRITICAL RULES
1. **Only sector-specific knowledge.** Generic rules — internal-consistency/reconciliation, JSON-prose parity,
   temporal grounding, fallback-tool discipline, open-questions ceiling, "normalize one-offs", "use calculate for
   all math" — ALREADY EXIST in a global SHARED_PREAMBLE injected before your file. Do NOT restate them. If you
   find yourself writing a generic analytical-rigor rule, delete it. Every line must be specific to `{sector}`.
2. **Ground in real Indian listed names and real KPIs.** Use the actual metrics analysts use for this sector.
3. **Reference only these real tools** when you mention tool calls: {TOOLS}
4. **Mandatory KPI backbone.** In `_shared.md`, include a clearly-headed mandatory-metrics list this sector's
   agents must populate (these feed a "Sector Compliance Gate" → `mandatory_metrics_status` briefing field).
5. **The valuation framework must name the RIGHT multiple and what's MISLEADING** for this sector (like the
   metals "cyclical PE trap" section).
6. Indian context: ₹ crores for money, FY (Apr-Mar) periods, NSE/BSE listing, SEBI/regulatory bodies.

## SECTOR TO AUTHOR: `{sector}`
- Industries folded in: {seed['industries']}
- Representative Indian listed companies: {seed['examples']}
- KPI backbone to cover: {seed['kpis']}
- Valuation framing: {seed['valuation']}
- Key structural risks: {seed['risk']}

## OUTPUT FORMAT (exact)
Emit EXACTLY these five files, each fenced by a line `===FILE: <name>===` on its own line, then the raw markdown.
No commentary outside the file blocks.

===FILE: _shared.md===
<sector mode header + valuation framework (right multiple + what misleads) + mandatory KPI backbone +
sector-specific cross-checks + AR/deck high-signal sections — model on metals/_shared.md & real_estate/_shared.md depth>

===FILE: sector.md===
<sector-agent guidance: competitive structure, cycle/demand drivers, the sector KPIs to lead with, peer-set framing>

===FILE: valuation.md===
<valuation-agent guidance: the multiple to anchor, how to normalize, SOTP/segment notes, what NOT to do>

===FILE: financials.md===
<financials-agent guidance: the P&L/BS/CF lines that matter here, margin drivers, working-capital & leverage focus>

===FILE: risk.md===
<risk-agent guidance: the sector's top structural & cyclical risks, what a pre-mortem must cover>
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        print("Sectors:", ", ".join(SECTORS))
        return
    sector = sys.argv[1]
    if sector not in SECTORS:
        print(f"Unknown sector '{sector}'. Known: {', '.join(SECTORS)}", file=sys.stderr)
        sys.exit(1)

    refs = "\n\n".join(
        f"----- REFERENCE FILE: {rf} -----\n{(SKILLS / rf).read_text()}" for rf in REF_FILES
    )
    prompt = build_prompt(sector, SECTORS[sector], refs)

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_load_gemini_api_key())
    print(f"[{sector}] calling gemini-3.1-pro-preview ...", flush=True)
    resp = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4, max_output_tokens=32000),
    )
    text = resp.text or ""
    blocks = re.split(r"^===FILE: (.+?)===$", text, flags=re.MULTILINE)
    # blocks = [pre, name1, body1, name2, body2, ...]
    if len(blocks) < 3:
        print(f"[{sector}] PARSE FAIL — no FILE blocks. Raw head:\n{text[:500]}", file=sys.stderr)
        sys.exit(2)
    outdir = SKILLS / sector
    outdir.mkdir(exist_ok=True)
    (outdir / ".gitkeep").touch()
    written = []
    for i in range(1, len(blocks) - 1, 2):
        name = blocks[i].strip()
        body = blocks[i + 1].strip() + "\n"
        (outdir / name).write_text(body)
        written.append(f"{name} ({len(body)}b)")
    print(f"[{sector}] wrote: {', '.join(written)}")


if __name__ == "__main__":
    main()
