#!/usr/bin/env python3
"""Drop legacy stored DII rows from the shareholding table.

DII is now *derived* on read (MF + Insurance + AIF) — see flowtracker.utils.
derive_dii — and no longer stored as its own category. Older quarters still
carry redundant DII rows from before the XBRL client stopped emitting them;
this removes them so stored data matches the 6-bucket canonical model.

Idempotent: deletes WHERE category='DII'. A second run deletes 0 rows.

Usage:
    python scripts/migrate-drop-dii.py            # delete against prod DB
    python scripts/migrate-drop-dii.py --dry-run  # report count only
    python scripts/migrate-drop-dii.py --db /path/to/other.db
"""
import argparse
import os
import sqlite3
import sys

DEFAULT_DB = os.path.expanduser("~/.local/share/flowtracker/flows.db")


def drop_dii_rows(db_path: str, dry_run: bool = False) -> int:
    """Delete stored DII shareholding rows. Returns the number affected."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        count = cur.execute(
            "SELECT COUNT(*) FROM shareholding WHERE category = 'DII'"
        ).fetchone()[0]
        if dry_run:
            print(f"[dry-run] would delete {count} DII rows from {db_path}")
            return count
        cur.execute("DELETE FROM shareholding WHERE category = 'DII'")
        conn.commit()
        print(f"Deleted {count} DII rows from {db_path}")
        return count
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="report count, don't delete")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: DB not found at {args.db}")
        sys.exit(1)

    drop_dii_rows(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
