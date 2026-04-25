"""Tests for M&A deal parsing in catalyst_client (Wave 4-5 P2 — 2026-04-25).

Covers:
- `parse_ma_deal_from_filing` — headline-only parser for the 4 must-have fields
  (deal_size, target, country, status). Patterns drawn from real BSE M&A
  filings observed in pharma + IT-services + auto cohorts.
- `_extract_filing_events` integration — ensures M&A subcategory filings emit
  CatalystEvent rows with `event_type='m_and_a'` and a populated `ma_details`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from flowtracker.catalyst_client import _extract_filing_events, parse_ma_deal_from_filing
from flowtracker.catalyst_models import CatalystEvent, MADealDetails
from flowtracker.filing_models import CorporateFiling


# ---------------------------------------------------------------------------
# Headline parser — sector-agnostic regex tests
# ---------------------------------------------------------------------------

class TestParseMADeal:
    """Headline-level extraction — accepts a few standard patterns."""

    def test_pharma_acquire_us_company_with_usd_size(self):
        """SUNPHARMA-style: 'Sun Pharma to acquire X for USD 350 million.'"""
        h = "Sun Pharmaceutical to acquire Concert Pharmaceuticals Inc. for USD 576 million in all-cash deal"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_size_currency == "USD"
        assert out.deal_size_native == 576.0
        # USD deals don't populate deal_size_cr (no inline FX conversion)
        assert out.deal_size_cr is None
        # Target name should pick up "Concert Pharmaceuticals Inc."
        assert out.deal_target is not None
        assert "concert" in out.deal_target.lower()
        assert out.deal_status == "announced"

    def test_inr_crore_deal_populates_cr(self):
        """INR deals should populate `deal_size_cr` directly (no FX needed)."""
        h = "Cipla to acquire Sandoz India private limited business for Rs. 350 crore"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_size_currency == "INR"
        assert out.deal_size_cr == 350.0
        assert out.deal_size_native == 350.0
        assert out.deal_target is not None
        assert "sandoz" in out.deal_target.lower()

    def test_inr_billion_deal(self):
        """Billion → millions equivalent for INR; cr conversion straightforward."""
        h = "Reliance Industries announces acquisition of XYZ for ₹2,400 crore"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_size_currency == "INR"
        assert out.deal_size_cr == 2400.0
        assert out.deal_status == "announced"

    def test_pending_regulatory_status(self):
        h = "Aurobindo Pharma's acquisition of Eugia Pharma is subject to CCI approval"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_status == "pending_regulatory"

    def test_closed_status(self):
        h = "Dr Reddy's announces completion of US-based Mayne Pharma acquisition"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_status == "closed"
        assert out.deal_target_country == "US"

    def test_terminated_status(self):
        h = "Lupin terminates proposed acquisition of Symbiomix Therapeutics"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_status == "terminated"

    def test_country_detection_us(self):
        h = "Cipla acquired US-based Endurance Pharma for $200 million"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_target_country == "US"

    def test_country_detection_uk(self):
        h = "Tata Steel to acquire UK-based BlueScope assets"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        assert out.deal_target_country == "UK"

    def test_no_deal_signal_returns_none(self):
        """Filing with no recognizable deal info should return None."""
        h = "Outcome of Board Meeting held on April 15, 2026"
        out = parse_ma_deal_from_filing(h)
        assert out is None

    def test_empty_headline_returns_none(self):
        assert parse_ma_deal_from_filing("") is None

    def test_target_only_no_size(self):
        """If target is present but no size disclosed, still return MADealDetails."""
        h = "Wipro to acquire Capco — definitive agreement signed"
        out = parse_ma_deal_from_filing(h)
        assert out is not None
        # No size disclosed
        assert out.deal_size_native is None
        # Target should still be parsed
        assert out.deal_target is not None
        assert "capco" in out.deal_target.lower()
        assert out.deal_status == "announced"


# ---------------------------------------------------------------------------
# Integration — _extract_filing_events emits structured M&A CatalystEvents
# ---------------------------------------------------------------------------

class TestFilingEventMA:
    def _make_store(self, filings: list[CorporateFiling]):
        store = MagicMock()
        store.get_filings = MagicMock(return_value=filings)
        return store

    def _filing(self, **kwargs) -> CorporateFiling:
        defaults = {
            "symbol": "SUNPHARMA",
            "bse_scrip_code": "524715",
            "filing_date": "2026-04-15",
            "category": "Company Update",
            "subcategory": "Acquisition",
            "headline": "",
            "attachment_name": "test.pdf",
            "pdf_flag": 0,
        }
        defaults.update(kwargs)
        return CorporateFiling(**defaults)

    def test_acquisition_filing_emits_m_and_a_event(self):
        """An Acquisition-subcategory filing should produce a CatalystEvent
        with event_type='m_and_a' and a populated ma_details payload.
        """
        f = self._filing(
            headline="Sun Pharmaceutical to acquire Concert Pharmaceuticals Inc. for USD 576 million",
        )
        store = self._make_store([f])
        events = _extract_filing_events("SUNPHARMA", store)

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "m_and_a"
        assert ev.impact == "high"
        assert ev.ma_details is not None
        assert ev.ma_details.deal_size_native == 576.0
        assert ev.ma_details.deal_size_currency == "USD"

    def test_divestiture_filing_emits_divestiture_event(self):
        """Divestiture / stake-sale headlines route to event_type='divestiture'."""
        f = self._filing(
            subcategory="Diversification / Disinvestment",
            headline="SUNPHARMA divestiture of non-core Organon dermatology business for USD 1.2 billion",
        )
        store = self._make_store([f])
        events = _extract_filing_events("SUNPHARMA", store)

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "divestiture"
        assert ev.ma_details is not None
        assert ev.ma_details.deal_size_currency == "USD"
        # 1.2 billion → 1200 million
        assert ev.ma_details.deal_size_native == 1200.0

    def test_unparseable_ma_filing_still_emits_event(self):
        """If the headline doesn't yield structured details, the CatalystEvent
        is still emitted with ma_details=None — the agent can still see a
        catalyst was filed even if size/target couldn't be parsed.
        """
        f = self._filing(
            headline="Acquisition update",  # too vague
        )
        store = self._make_store([f])
        events = _extract_filing_events("SUNPHARMA", store)

        # Should still emit since 'Acquisition' subcategory triggers event_type=m_and_a
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "m_and_a"
        # ma_details may or may not parse from a vague headline; both are acceptable
        # but the event itself must be present.

    def test_non_ma_filing_unaffected(self):
        """Board meetings + earnings filings continue to work — M&A wiring
        must not regress existing event types.
        """
        f1 = self._filing(
            subcategory="Board Meeting",
            category="Board Meeting",
            headline="Notice of Board Meeting on April 25, 2026",
        )
        f2 = self._filing(
            subcategory="Financial Results",
            category="Result",
            headline="Audited financial results for Q4 FY26",
        )
        store = self._make_store([f1, f2])
        events = _extract_filing_events("SUNPHARMA", store)

        types = sorted(e.event_type for e in events)
        assert types == ["board_meeting", "earnings"]
        # Neither should have ma_details populated.
        for ev in events:
            assert ev.ma_details is None


# ---------------------------------------------------------------------------
# Catalyst event model — backward compat
# ---------------------------------------------------------------------------

class TestCatalystEventModel:
    def test_catalyst_event_default_ma_details_is_none(self):
        """Existing catalyst-event call sites (no ma_details kwarg) must not
        break — the new field defaults to None.
        """
        from datetime import date as _date
        ev = CatalystEvent(
            symbol="INFY",
            event_type="earnings",
            event_date=_date(2026, 7, 15),
            days_until=10,
            description="Q1 FY27 earnings",
            impact="high",
            source="bse_filing",
        )
        assert ev.ma_details is None

    def test_ma_details_populates_when_passed(self):
        from datetime import date as _date
        details = MADealDetails(
            deal_size_native=576.0,
            deal_size_currency="USD",
            deal_target="Concert Pharmaceuticals",
            deal_status="announced",
        )
        ev = CatalystEvent(
            symbol="SUNPHARMA",
            event_type="m_and_a",
            event_date=_date(2026, 4, 15),
            days_until=0,
            description="Acquisition update",
            impact="high",
            source="bse_filing",
            ma_details=details,
        )
        assert ev.ma_details is not None
        assert ev.ma_details.deal_size_native == 576.0
        assert ev.ma_details.deal_status == "announced"
