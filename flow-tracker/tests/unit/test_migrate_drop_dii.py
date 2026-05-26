"""Tests for scripts/migrate-drop-dii.py — legacy DII row purge."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from flowtracker.store import FlowStore
from flowtracker.holding_models import ShareholdingRecord

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate-drop-dii.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migrate_drop_dii", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed(db_path: Path) -> None:
    with FlowStore(db_path=str(db_path)) as store:
        store.upsert_shareholding([
            ShareholdingRecord(symbol="SBIN", quarter_end="2025-12-31", category="FII", percentage=10.0),
            ShareholdingRecord(symbol="SBIN", quarter_end="2025-12-31", category="MF", percentage=8.0),
            ShareholdingRecord(symbol="SBIN", quarter_end="2025-12-31", category="DII", percentage=20.0),
            ShareholdingRecord(symbol="INFY", quarter_end="2025-12-31", category="DII", percentage=15.0),
        ])


def _categories(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT category FROM shareholding ORDER BY category")]
    finally:
        conn.close()


def test_dry_run_reports_but_keeps_rows(tmp_db):
    _seed(tmp_db)
    mod = _load_migration()
    count = mod.drop_dii_rows(str(tmp_db), dry_run=True)
    assert count == 2
    assert _categories(tmp_db).count("DII") == 2  # nothing deleted


def test_deletes_only_dii(tmp_db):
    _seed(tmp_db)
    mod = _load_migration()
    count = mod.drop_dii_rows(str(tmp_db))
    assert count == 2
    cats = _categories(tmp_db)
    assert "DII" not in cats
    assert cats == ["FII", "MF"]  # non-DII rows preserved


def test_idempotent(tmp_db):
    _seed(tmp_db)
    mod = _load_migration()
    mod.drop_dii_rows(str(tmp_db))
    assert mod.drop_dii_rows(str(tmp_db)) == 0  # re-run is a no-op
