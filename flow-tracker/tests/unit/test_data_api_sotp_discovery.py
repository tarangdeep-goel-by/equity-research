"""SOTP company-name normalization tests.

The promoter-surname auto-discovery heuristic (`_discover_recent_listings`,
`_find_promoter_owned_children`) was removed in the SOTP conglomerate fix —
`listed_subsidiaries` is now driven by a curated YAML map (see
`test_listed_subsidiaries_curated.py`). The only surviving helper is the
full-name normalizer.
"""

from __future__ import annotations

from flowtracker.research.data_api import ResearchDataAPI


def test_company_name_normalization():
    assert (
        ResearchDataAPI._clean_company_name("NTPC LIMITED")
        == ResearchDataAPI._clean_company_name("ntpc Ltd.")
        == "ntpc"
    )
