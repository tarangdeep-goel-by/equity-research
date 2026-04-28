"""Tests for the ADR/GDR program directory client.

Covers:
- ``AdrProgram`` model construction (happy + optional-None + extra-field-ignored).
- ``AdrClient`` loading the bundled seed JSON and rejecting malformed input.
- ``AdrClient.fetch_indian_dr_programs`` returning typed records.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from flowtracker.adr_client import AdrClient, AdrClientError
from flowtracker.adr_models import AdrProgram


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_dataset() -> dict:
    """A minimal in-memory dataset covering both ADS and GDR shapes."""
    return {
        "_meta": {"description": "test fixture"},
        "programs": [
            {
                "nse_symbol": "INFY",
                "company_name": "Infosys Limited",
                "us_ticker": "INFY",
                "program_type": "ADS",
                "sponsorship": "sponsored",
                "depositary": "Deutsche Bank",
                "ratio": "1 ADS = 1 equity share",
            },
            {
                # NSE-unmapped ADS — exercises nse_symbol = None path.
                "nse_symbol": None,
                "company_name": "Sify Technologies Limited",
                "us_ticker": "SIFY",
                "program_type": "ADS",
                "sponsorship": "sponsored",
                "depositary": "Citi",
                "ratio": "1 ADS = 1 equity share",
            },
            {
                # Only the two strictly-required fields — exercises optional-None.
                "company_name": "Mystery Holdings Limited",
                "program_type": "GDR",
            },
        ],
    }


# ---------------------------------------------------------------------------
# AdrProgram model
# ---------------------------------------------------------------------------


class TestAdrProgramModel:
    """Construction, optional fields, extra-field handling."""

    def test_minimal_construction(self):
        """Only company_name and program_type are required."""
        p = AdrProgram(company_name="Acme Corp", program_type="ADR")
        assert p.company_name == "Acme Corp"
        assert p.program_type == "ADR"
        # Defaults
        assert p.country == "India"
        # Optionals all default to None
        assert p.nse_symbol is None
        assert p.us_ticker is None
        assert p.sponsorship is None
        assert p.depositary is None
        assert p.ratio is None

    def test_full_construction(self):
        p = AdrProgram(
            nse_symbol="INFY",
            company_name="Infosys Limited",
            us_ticker="INFY",
            program_type="ADS",
            sponsorship="sponsored",
            depositary="Deutsche Bank",
            ratio="1 ADS = 1 equity share",
        )
        assert p.nse_symbol == "INFY"
        assert p.depositary == "Deutsche Bank"

    def test_extra_fields_ignored(self):
        """``extra='ignore'`` means unknown keys don't blow up — important for
        forward-compat with seed-JSON additions."""
        p = AdrProgram(
            company_name="Foo",
            program_type="GDR",
            future_field="should not raise",
        )
        assert p.company_name == "Foo"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            AdrProgram(program_type="ADR")  # missing company_name
        with pytest.raises(ValidationError):
            AdrProgram(company_name="Foo")  # missing program_type


# ---------------------------------------------------------------------------
# AdrClient — bundled-seed loading
# ---------------------------------------------------------------------------


class TestAdrClientLoading:
    """Loading the bundled JSON and surfacing parse errors."""

    def test_loads_bundled_dataset(self):
        """The shipped seed JSON parses cleanly and yields >= 1 program."""
        client = AdrClient()
        # Sanity: the seed file we ship has dozens of programs.
        assert len(client._programs) >= 10
        # Every entry round-trips through the Pydantic model.
        for p in client._programs:
            assert isinstance(p, AdrProgram)

    def test_construction_with_explicit_dataset(self, fake_dataset: dict):
        """Tests can pass a dataset dict to avoid touching the real file."""
        client = AdrClient(dataset=fake_dataset)
        assert len(client._programs) == 3

    def test_meta_property_exposed(self, fake_dataset: dict):
        client = AdrClient(dataset=fake_dataset)
        assert client.meta == {"description": "test fixture"}

    def test_malformed_programs_field_raises(self):
        """``programs`` must be a list — a dict should raise AdrClientError."""
        with pytest.raises(AdrClientError, match="Expected 'programs' to be a list"):
            AdrClient(dataset={"_meta": {}, "programs": {"not": "a list"}})

    def test_invalid_program_row_raises(self):
        """A row missing both required fields should raise during validation."""
        with pytest.raises(ValidationError):
            AdrClient(
                dataset={
                    "_meta": {},
                    "programs": [{"sponsorship": "sponsored"}],  # no company_name, no program_type
                }
            )

    def test_empty_dataset_is_ok(self):
        """Empty programs list is valid (just yields no records)."""
        client = AdrClient(dataset={"_meta": {}, "programs": []})
        assert client._programs == []


# ---------------------------------------------------------------------------
# AdrClient — public fetch API
# ---------------------------------------------------------------------------


class TestFetchIndianDrPrograms:
    """The async fetch surface that mirrors what a future live scrape would use."""

    def test_returns_all_programs(self, fake_dataset: dict):
        client = AdrClient(dataset=fake_dataset)
        result = asyncio.run(client.fetch_indian_dr_programs())
        assert len(result) == 3
        names = {p.company_name for p in result}
        assert "Infosys Limited" in names
        assert "Sify Technologies Limited" in names

    def test_returns_typed_models(self, fake_dataset: dict):
        client = AdrClient(dataset=fake_dataset)
        result = asyncio.run(client.fetch_indian_dr_programs())
        assert all(isinstance(p, AdrProgram) for p in result)

    def test_returns_copy_not_internal_list(self, fake_dataset: dict):
        """Mutating the returned list must not corrupt the client's state."""
        client = AdrClient(dataset=fake_dataset)
        result = asyncio.run(client.fetch_indian_dr_programs())
        result.clear()
        # Internal list is unchanged
        assert len(client._programs) == 3

    def test_bundled_path_returns_indian_programs(self):
        """End-to-end against the real seed: every program defaults to India."""
        client = AdrClient()
        result = asyncio.run(client.fetch_indian_dr_programs())
        assert len(result) >= 10
        assert all(p.country == "India" for p in result)
        # Spot-check a few well-known tickers.
        tickers = {p.us_ticker for p in result if p.us_ticker}
        assert "INFY" in tickers
        assert "WIT" in tickers
        assert "HDB" in tickers
        assert "IBN" in tickers
