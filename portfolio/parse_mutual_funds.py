"""Parse Groww Mutual Funds XLSX export and output holdings as JSON."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_XLSX = Path.home() / "Downloads" / "Mutual Funds Oct 2 2026.xlsx"
OUTPUT_FILE = Path(__file__).parent / "mutual_funds.json"


def parse_mf(xlsx_path: Path) -> dict:
    df = pd.read_excel(xlsx_path, header=None)

    # Find summary row (row after "Total Investments" header)
    summary = {}
    for i, row in df.iterrows():
        if str(row.iloc[0]).strip() == "Total Investments":
            next_row = df.iloc[i + 1]
            summary = {
                "total_invested": float(next_row.iloc[0]),
                "total_current_value": float(next_row.iloc[1]),
                "total_pnl": float(next_row.iloc[2]),
                "total_pnl_percent": str(next_row.iloc[3]),
                "xirr": str(next_row.iloc[4]),
            }
            break

    # Find holdings header row
    header_idx = None
    for i, row in df.iterrows():
        if str(row.iloc[0]).strip() == "Scheme Name":
            header_idx = i
            break

    if header_idx is None:
        print("Could not find holdings header row")
        sys.exit(1)

    holdings_df = df.iloc[header_idx + 1:].copy()
    holdings_df.columns = [
        "scheme_name", "amc", "category", "sub_category", "folio_no",
        "source", "units", "invested_value", "current_value", "returns", "xirr",
    ]
    holdings_df = holdings_df.dropna(subset=["scheme_name"])

    holdings = []
    for _, row in holdings_df.iterrows():
        holdings.append({
            "scheme_name": str(row["scheme_name"]).strip(),
            "amc": str(row["amc"]).strip(),
            "category": str(row["category"]).strip(),
            "sub_category": str(row["sub_category"]).strip(),
            "units": round(float(row["units"]), 3),
            "invested_value": round(float(row["invested_value"]), 2),
            "current_value": round(float(row["current_value"]), 2),
            "pnl": round(float(row["returns"]), 2),
            "xirr": str(row["xirr"]).strip(),
        })

    return {
        "source": "groww",
        "currency": "INR",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(xlsx_path),
        "summary": summary,
        "holdings_count": len(holdings),
        "holdings": sorted(holdings, key=lambda x: x["current_value"], reverse=True),
    }


def main():
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX

    if not xlsx_path.exists():
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    output = parse_mf(xlsx_path)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    print(f"Wrote {output['holdings_count']} mutual funds to {OUTPUT_FILE}")
    print(f"Total Invested: ₹{output['summary']['total_invested']:,.2f}")
    print(f"Current Value:  ₹{output['summary']['total_current_value']:,.2f}")
    print(f"P&L:            ₹{output['summary']['total_pnl']:,.2f} ({output['summary']['total_pnl_percent']})")
    print()
    for h in output["holdings"]:
        print(f"  {h['scheme_name'][:45]:<47} {h['sub_category']:<15} ₹{h['current_value']:>10,.2f}")


if __name__ == "__main__":
    main()
