"""One-off: re-fetch richer trimmed EDGAR companyfacts fixtures (Phase 3.5b WS-2).

Fetches live companyfacts for AAPL/MSFT/JPM, trims facts.us-gaap to the UNION
of (tags already in the existing fixture) + (all new Phase 3.5b target tags),
preserves cik/entityName/facts.dei, and overwrites the three fixture JSONs.

Run: uv run python scripts/refetch_edgar_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

_FIX = Path(__file__).parent.parent / "tests" / "fixtures" / "edgar"
_UA = "flowtracker-research test@example.com"

CIKS = {"AAPL": 320193, "MSFT": 789019, "JPM": 19617}

# New Phase 3.5b target tags (duration + instant + equity-capital components).
NEW_TAGS = [
    # duration
    "InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense",
    "OperatingIncomeLoss", "IncomeTaxExpenseBenefit",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
    "DepreciationAndAmortization", "ResearchAndDevelopmentExpense", "ShareBasedCompensation",
    "SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    "NetCashProvidedByUsedInFinancingActivities",
    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    # instant
    "RetainedEarningsAccumulatedDeficit", "PropertyPlantAndEquipmentNet",
    "ConstructionInProgressGross", "AccountsReceivableNetCurrent", "InventoryNet",
    "OtherLiabilitiesNoncurrent", "OtherLiabilities", "CommonStockValue",
    "AdditionalPaidInCapital",
]

KEEP_FORMS = {"10-K", "20-F", "10-Q"}


def trim_units(units: dict) -> dict:
    """Keep only 10-K/20-F/10-Q rows per unit (drops 8-K and other noise)."""
    out: dict = {}
    for unit, entries in units.items():
        kept = [e for e in entries if e.get("form") in KEEP_FORMS]
        if kept:
            out[unit] = kept
    return out


def main() -> None:
    with httpx.Client(headers={"User-Agent": _UA}, timeout=60.0,
                      follow_redirects=True) as client:
        for sym, cik in CIKS.items():
            fixture_path = _FIX / f"companyfacts_{sym}.json"
            existing = json.loads(fixture_path.read_text())
            existing_tags = set(existing["facts"].get("us-gaap", {}).keys())
            target_tags = existing_tags | set(NEW_TAGS)

            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
            resp = client.get(url)
            resp.raise_for_status()
            live = resp.json()
            live_gaap = live.get("facts", {}).get("us-gaap", {})

            trimmed_gaap: dict = {}
            present = []
            for tag in sorted(target_tags):
                if tag in live_gaap:
                    node = dict(live_gaap[tag])
                    node["units"] = trim_units(node.get("units", {}))
                    if node["units"]:
                        trimmed_gaap[tag] = node
                        present.append(tag)

            out = {
                "cik": live.get("cik", cik),
                "entityName": live.get("entityName", existing.get("entityName")),
                "facts": {"us-gaap": trimmed_gaap},
            }
            if "dei" in live.get("facts", {}):
                out["facts"]["dei"] = live["facts"]["dei"]

            fixture_path.write_text(json.dumps(out, separators=(",", ":")))
            size = fixture_path.stat().st_size
            absent = sorted(set(NEW_TAGS) - set(present))
            print(f"{sym}: {len(present)} tags, {size/1024:.0f}KB; "
                  f"new tags absent: {absent}")


if __name__ == "__main__":
    main()
