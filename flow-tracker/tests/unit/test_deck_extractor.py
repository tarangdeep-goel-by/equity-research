"""Unit tests for deck_extractor.ensure_deck_data cache behavior.

Sibling to test_deck_insights.py (which exercises ResearchDataAPI.get_deck_insights).
This file targets the extractor pipeline directly — verifying that fully-cached
quarters short-circuit the expensive Claude/Docling path.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_deck_cache(vault_root: Path, symbol: str, quarters: list[str]) -> None:
    """Write a synthetic deck_extraction.json with N quarters all marked complete.

    `vault_root` is the directory that contains `stocks/` (e.g. ``~/vault``).
    """
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "quarters_analyzed": len(quarters),
        "extraction_date": "2026-04-17",
        "quarters": [
            {
                "fy_quarter": q,
                "extraction_status": "complete",
                "highlights": [f"{q} highlight"],
            }
            for q in quarters
        ],
    }
    (fdir / "deck_extraction.json").write_text(json.dumps(payload))


def _write_deck_pdfs(vault_root: Path, symbol: str, quarters: list[str]) -> None:
    """Lay down stub investor_deck.pdf files so _find_deck_pdfs returns them."""
    base = vault_root / "stocks" / symbol / "filings"
    for q in quarters:
        d = base / q
        d.mkdir(parents=True, exist_ok=True)
        (d / "investor_deck.pdf").write_bytes(b"fake pdf")


class TestEnsureDeckDataCacheSkip:
    def test_ensure_deck_data_cached_returns_zero_new(self, vault_home, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod

        symbol = "TESTCO"
        quarters = ["FY26-Q3", "FY26-Q2"]

        # Module-level _VAULT_BASE was bound at import via Path.home() — repoint
        # it at the tmp vault so cache reads/writes land in the right place.
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")

        _write_deck_pdfs(vault_root, symbol, quarters)
        _write_deck_cache(vault_root, symbol, quarters)

        # Any Claude call must blow up — point of the test is cache-skip.
        async def boom(*args, **kwargs):
            raise AssertionError("Claude called for cached quarter")

        monkeypatch.setattr(deck_mod, "_call_claude", boom)

        result = asyncio.run(deck_mod.ensure_deck_data(symbol, quarters=2))

        assert result is not None
        assert result["_new_quarters_extracted"] == 0
        assert result["quarters_analyzed"] == 2
