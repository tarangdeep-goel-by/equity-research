#!/usr/bin/env python3
"""Purge false `listed_subsidiaries` rows written by the deleted promoter-surname heuristic.

The old `_detect_parent_subsidiary` auto-detection (now removed in the SOTP
conglomerate fix) matched a stock's promoter to listed companies by shared
surname/first-word and wrote rows with `relationship` like
"Auto-detected: promoter '<name>'". This mislabelled promoter-group SIBLINGS
(e.g. ADANIPORTS/ADANIPOWER under ADANIENT) as subsidiaries — they are held by
the family trusts at the GROUP level, not by the flagship company.

`listed_subsidiaries` is now driven by the authoritative AOC-1 statement. This
script DELETEs every row that heuristic ever wrote (relationship LIKE
'Auto-detected:%') from the production DB.

Usage:
    uv run python scripts/purge_false_subsidiaries.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from flowtracker.store import FlowStore


def main() -> int:
    with FlowStore() as store:
        conn = store._conn
        rows = conn.execute(
            "SELECT id, parent_symbol, sub_symbol, sub_name, parent_ownership_pct, "
            "relationship FROM listed_subsidiaries "
            "WHERE relationship LIKE 'Auto-detected:%' "
            "ORDER BY parent_symbol, sub_symbol"
        ).fetchall()

        if not rows:
            print("No auto-detected listed_subsidiaries rows found — nothing to purge.")
            return 0

        print(f"Found {len(rows)} auto-detected listed_subsidiaries row(s) to delete:\n")
        for r in rows:
            print(
                f"  [{r['id']}] parent={r['parent_symbol']} "
                f"sub={r['sub_symbol']} ({r['sub_name']}) "
                f"pct={r['parent_ownership_pct']} :: {r['relationship']}"
            )

        cur = conn.execute(
            "DELETE FROM listed_subsidiaries WHERE relationship LIKE 'Auto-detected:%'"
        )
        conn.commit()
        print(f"\nDeleted {cur.rowcount} row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
