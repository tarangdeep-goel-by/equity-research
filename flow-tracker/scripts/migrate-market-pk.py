#!/usr/bin/env python3
"""WS5: Fold `market` into the UNIQUE/PK of the proof-set tables.

MANUAL one-shot migration. NOT run automatically from FlowStore.

Prerequisite (WS1): FlowStore now auto-adds a `market TEXT NOT NULL
DEFAULT 'NSE'` column to the proof-set tables on open (via
`_migrate_market_columns`). This script's only job is to rebuild each
proof-set table so that `market` is part of its `UNIQUE(...)` constraint.

`daily_stock_data` (4.5M rows) is explicitly EXCLUDED — never rebuilt here.

Safety contract (data preservation is paramount — prod DB is 6.4GB):
  (a) Backup-first: WAL checkpoint + shutil.copy2 to a timestamped .bak
      (skipped only on --dry-run).
  (b) Per-table transaction: BEGIN ... COMMIT; rollback + re-raise on any
      exception so the original table is left intact.
  (c) Recreate aux objects: capture user-defined indexes/triggers
      (sql IS NOT NULL) before drop, re-execute after rename.
  (d) Explicit named-column copy (no SELECT *), built from
      PRAGMA table_info — preserves `id` values and column order.
  (e) Row-count assertion BEFORE dropping the old table.
  (f) Idempotent: skip any table whose UNIQUE(...) already contains
      `market`.

Usage:
    uv run python scripts/migrate-market-pk.py --help
    uv run python scripts/migrate-market-pk.py --dry-run
    uv run python scripts/migrate-market-pk.py            # destructive (backs up first)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB = os.path.expanduser("~/.local/share/flowtracker/flows.db")

# table -> the new UNIQUE column tuple (must include "market").
# daily_stock_data is intentionally absent.
PROOF_SET: dict[str, tuple[str, ...]] = {
    "shareholding":       ("symbol", "market", "quarter_end", "category"),
    "valuation_snapshot": ("symbol", "market", "date"),
    "quarterly_results":  ("symbol", "market", "quarter_end"),
    "annual_financials":  ("symbol", "market", "fiscal_year_end"),
}

_UNIQUE_RE = re.compile(r"UNIQUE\s*\([^)]*\)", re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────
# Introspection helpers
# ──────────────────────────────────────────────────────────────────────
def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None or row[0] is None:
        raise ValueError(f"table {table!r} not found in sqlite_master")
    return row[0]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Column names in physical order (includes id and the new market col)."""
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _has_market_column(conn: sqlite3.Connection, table: str) -> bool:
    return "market" in _columns(conn, table)


def _extract_unique_cols(sql: str) -> list[str] | None:
    """Return the column names inside the table's UNIQUE(...) clause, or None."""
    m = _UNIQUE_RE.search(sql)
    if not m:
        return None
    inner = m.group(0)[m.group(0).index("(") + 1 : m.group(0).rindex(")")]
    return [c.strip().strip('"').strip("`").strip("[]") for c in inner.split(",")]


def _already_migrated(conn: sqlite3.Connection, table: str) -> bool:
    """True if the table's UNIQUE(...) already contains `market`."""
    cols = _extract_unique_cols(_table_sql(conn, table))
    return bool(cols) and "market" in cols


# ──────────────────────────────────────────────────────────────────────
# DDL rewriting
# ──────────────────────────────────────────────────────────────────────
def _build_new_ddl(old_sql: str, table: str, new_cols: tuple[str, ...]) -> str:
    """Derive {table}_new DDL by string-rewriting the OLD table's sql.

    1. Replace the single UNIQUE(...) clause with the new column set.
    2. Rename the CREATE target from <table> to <table>_new.
    This guarantees the new table has every column the old one has, in
    identical physical order.
    """
    new_sql, n = _UNIQUE_RE.subn(
        f"UNIQUE({', '.join(new_cols)})", old_sql, count=1
    )
    if n != 1:
        raise ValueError(
            f"{table}: expected exactly 1 UNIQUE(...) clause, found {n}"
        )

    create_re = re.compile(
        r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)"
        rf"[\"'`\[]?{re.escape(table)}[\"'`\]]?\b",
        re.IGNORECASE,
    )
    new_sql, n = create_re.subn(rf"\g<1>{table}_new", new_sql, count=1)
    if n != 1:
        raise ValueError(
            f"{table}: could not rewrite CREATE TABLE target (matched {n})"
        )
    return new_sql


def _capture_aux(conn: sqlite3.Connection, table: str) -> list[tuple[str, str, str]]:
    """User-defined indexes/triggers on the table (sql IS NOT NULL).

    sql IS NULL means an auto-index backing the old UNIQUE — that is
    recreated automatically by the new constraint, so we skip it.
    """
    return conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",
        (table,),
    ).fetchall()


# ──────────────────────────────────────────────────────────────────────
# Per-table rebuild
# ──────────────────────────────────────────────────────────────────────
def rebuild_table(
    conn: sqlite3.Connection,
    table: str,
    new_cols: tuple[str, ...],
    *,
    dry_run: bool = False,
) -> bool:
    """Rebuild one proof-set table so UNIQUE(...) includes `market`.

    Returns True if a rebuild was performed, False if skipped (already
    migrated). Raises on any failure, after rolling back, leaving the
    original table intact.
    """
    if _already_migrated(conn, table):
        print(f"[skip] {table}: UNIQUE already includes `market`")
        return False

    if not _has_market_column(conn, table):
        raise RuntimeError(
            f"{table}: no `market` column present. Open the app once so "
            f"WS1's `_migrate_market_columns` adds it, then re-run."
        )

    old_sql = _table_sql(conn, table)
    new_sql = _build_new_ddl(old_sql, table, new_cols)
    cols = _columns(conn, table)
    col_list = ", ".join(cols)
    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    aux = _capture_aux(conn, table)

    if dry_run:
        print(f"[plan] {table}: rows={before}, "
              f"UNIQUE -> ({', '.join(new_cols)}), "
              f"cols={len(cols)}, aux_objects={len(aux)}")
        return False

    try:
        conn.execute("BEGIN")
        conn.execute(new_sql)
        conn.execute(
            f"INSERT INTO {table}_new ({col_list}) SELECT {col_list} FROM {table}"
        )
        after = conn.execute(f"SELECT COUNT(*) FROM {table}_new").fetchone()[0]
        if after != before:
            # Assert BEFORE the DROP — old table still intact.
            raise RuntimeError(
                f"{table}: row-count mismatch (before={before}, after={after}); "
                f"aborting, original table untouched"
            )
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
        for _type, _name, sql in aux:
            conn.execute(sql)
        conn.execute("COMMIT")
    except Exception:
        conn.rollback()
        raise

    print(f"[done] {table}: rebuilt {before} rows, "
          f"UNIQUE now ({', '.join(new_cols)}), "
          f"recreated {len(aux)} aux object(s)")
    return True


# ──────────────────────────────────────────────────────────────────────
# Backup
# ──────────────────────────────────────────────────────────────────────
def backup_db(db_path: str) -> str:
    """Checkpoint the WAL then copy the DB to a timestamped .bak. Returns path."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = f"{db_path}.pre-market-pk.{ts}.bak"
    shutil.copy2(db_path, dest)
    print(f"[backup] {db_path} -> {dest}")
    return dest


# ──────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────
def run_migration(db_path: str, *, dry_run: bool = False) -> None:
    if not os.path.exists(db_path):
        raise SystemExit(f"[FAIL] DB not found at {db_path}")

    if not dry_run:
        backup_db(db_path)
    else:
        print("[plan] dry-run: no backup, no writes")

    conn = sqlite3.connect(db_path)
    # Defensive: codebase declares no FKs, but rebuilds are safer with these off.
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        for table, new_cols in PROOF_SET.items():
            try:
                rebuild_table(conn, table, new_cols, dry_run=dry_run)
            except Exception as exc:  # noqa: BLE001 - report + abort
                print(f"[FAIL] {table}: {exc}")
                raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.close()

    if not dry_run:
        conn = sqlite3.connect(db_path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        print(f"[done] integrity_check: {result}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fold `market` into the UNIQUE/PK of the proof-set tables "
                    "(manual one-shot, backup-first, transactional, idempotent)."
    )
    parser.add_argument("--db", default=DEFAULT_DB,
                        help=f"path to flows.db (default: {DEFAULT_DB})")
    parser.add_argument("--dry-run", action="store_true",
                        help="report plan + counts, make no changes")
    args = parser.parse_args(argv)
    run_migration(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
