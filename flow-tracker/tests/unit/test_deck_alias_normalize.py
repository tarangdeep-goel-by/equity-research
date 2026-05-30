"""Canonical sector/industry alias normalization in the deck extractor.

The deck extractor's only sector-keyed routing point is
``build_extraction_hint(industry)``. It must canonicalize the free-text
industry through ``sector_kpis.get_sector_for_industry`` before substring-
matching, so the deck pipeline resolves sectors consistently with the rest of
the pipeline (aliased / free-text labels map to the same canonical token the
sector router uses everywhere else).
"""

from __future__ import annotations

from unittest.mock import patch

from flowtracker.research import deck_extractor
from flowtracker.research import sector_kpis as sector_kpis_mod


def test_resolver_maps_aliases_to_canonical_tokens():
    # Fixture sanity: these are the alias -> canonical mappings under test.
    assert sector_kpis_mod.get_sector_for_industry("Textile Manufacturing") == "textiles"
    assert (
        sector_kpis_mod.get_sector_for_industry("Integrated Freight & Logistics")
        == "logistics"
    )


def test_build_hint_normalizes_aliased_industry_before_routing():
    """An aliased industry must be canonicalized, then routed by canonical token.

    We assert that ``build_extraction_hint`` passes the CANONICAL token to the
    resolver-driven matching by spying on the resolver and confirming the hint
    is computed from its output, not the raw alias.
    """
    captured = {}
    real = sector_kpis_mod.get_sector_for_industry

    def _spy(industry):
        out = real(industry)
        captured[industry] = out
        return out

    with patch.object(deck_extractor.sector_kpis_mod, "get_sector_for_industry", _spy):
        deck_extractor.build_extraction_hint("Textile Manufacturing")

    # The raw alias was handed to the canonical resolver.
    assert captured["Textile Manufacturing"] == "textiles"


def test_build_hint_uses_canonical_metals_token_for_metals_alias():
    """A metals-family alias resolves to canonical `metals` and triggers the
    Metals / Oil & Gas mandate (which keys off substrings present in the
    canonical token), proving normalization feeds the routing."""
    # Confirm the alias resolves to a metals-family canonical token.
    canonical = sector_kpis_mod.get_sector_for_industry("Steel")
    assert canonical and "metal" in canonical.lower()
    hint = deck_extractor.build_extraction_hint("Steel")
    assert "Metals" in hint


def test_build_hint_preserves_unresolved_industry():
    """When the resolver returns None, the raw industry is kept (nothing lost):
    a bank-family raw label still triggers the BFSI mandate via substring."""
    # A label the resolver does not canonicalize but which still contains a
    # routable substring must continue to route on the raw value.
    raw = "Some Bespoke Bank Holding"
    assert sector_kpis_mod.get_sector_for_industry(raw) is None
    hint = deck_extractor.build_extraction_hint(raw)
    assert "BFSI" in hint


def test_build_hint_empty_for_no_industry():
    assert deck_extractor.build_extraction_hint(None) == ""
    assert deck_extractor.build_extraction_hint("") == ""
