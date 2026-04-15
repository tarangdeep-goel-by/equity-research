"""Tests for holding_client.py — NSE XBRL shareholding parsing."""

from __future__ import annotations

import httpx
import pytest
import respx

from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError, _local_name


# -- Fixture XBRL content --

# Newer format: category_ContextI suffix, percentage format (values ~50.0)
_XBRL_NEWER = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-shp="http://www.example.com/shareholding">
  <xbrli:context id="ShareholdingPattern_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="ShareholdingOfPromoterAndPromoterGroup_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="InstitutionsForeign_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="MutualFundsOrUTI_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="NonInstitutions_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>

  <!-- Total (for format detection) -->
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingPattern_ContextI">100.00</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">50.01</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeign_ContextI">18.50</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_ContextI">12.30</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="NonInstitutions_ContextI">19.19</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <!-- Pledge data -->
  <in-shp:EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">2.50</in-shp:EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares>
  <in-shp:EncumberedSharesHeldAsPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">3.10</in-shp:EncumberedSharesHeldAsPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
"""

# Decimal format: values ~0.50 (need *100)
_XBRL_DECIMAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-shp="http://www.example.com/shareholding">
  <xbrli:context id="ShareholdingPattern_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE456</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-09-30</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="ShareholdingOfPromoterAndPromoterGroup_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE456</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-09-30</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="InstitutionsForeign_ContextI">
    <xbrli:entity><xbrli:identifier scheme="http://www.example.com">INE456</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-09-30</xbrli:instant></xbrli:period>
  </xbrli:context>

  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingPattern_ContextI">1.0000</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">0.5001</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeign_ContextI">0.2050</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
"""

# No context instant — should return empty
_XBRL_NO_DATE = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
</xbrli:xbrl>
"""


class TestLocalName:
    """Test _local_name namespace stripping."""

    def test_with_namespace(self):
        assert _local_name("{http://www.xbrl.org/2003/instance}context") == "context"

    def test_without_namespace(self):
        assert _local_name("context") == "context"

    def test_complex_namespace(self):
        assert _local_name("{http://www.example.com/shareholding}ShareholdingAsAPercentageOfTotalNumberOfShares") == "ShareholdingAsAPercentageOfTotalNumberOfShares"


class TestParseXbrl:
    """Test NSEHoldingClient._parse_xbrl with fixture XML."""

    def test_newer_format_percentage(self):
        client = NSEHoldingClient()
        records, pledge = client._parse_xbrl(_XBRL_NEWER, "SBIN")

        assert len(records) == 4
        categories = {r.category for r in records}
        assert categories == {"Promoter", "FII", "MF", "Public"}

        # Check values (percentage format — not multiplied by 100)
        promoter = next(r for r in records if r.category == "Promoter")
        assert promoter.percentage == 50.01
        assert promoter.quarter_end == "2025-12-31"
        assert promoter.symbol == "SBIN"

        fii = next(r for r in records if r.category == "FII")
        assert fii.percentage == 18.50

        mf = next(r for r in records if r.category == "MF")
        assert mf.percentage == 12.30

        client.close()

    def test_newer_format_pledge(self):
        client = NSEHoldingClient()
        records, pledge = client._parse_xbrl(_XBRL_NEWER, "SBIN")

        assert pledge is not None
        assert pledge.symbol == "SBIN"
        assert pledge.quarter_end == "2025-12-31"
        assert pledge.pledge_pct == 2.50
        assert pledge.encumbered_pct == 3.10

        client.close()

    def test_decimal_format(self):
        """When total is ~1.0 (decimal format), values are multiplied by 100."""
        client = NSEHoldingClient()
        records, pledge = client._parse_xbrl(_XBRL_DECIMAL, "RELIANCE")

        assert len(records) == 2
        promoter = next(r for r in records if r.category == "Promoter")
        assert promoter.percentage == 50.01  # 0.5001 * 100

        fii = next(r for r in records if r.category == "FII")
        assert fii.percentage == 20.50  # 0.2050 * 100

        client.close()

    def test_no_date_returns_empty(self):
        client = NSEHoldingClient()
        records, pledge = client._parse_xbrl(_XBRL_NO_DATE, "SBIN")
        assert records == []
        assert pledge is None
        client.close()

    def test_symbol_uppercased(self):
        client = NSEHoldingClient()
        records, _ = client._parse_xbrl(_XBRL_NEWER, "sbin")
        assert all(r.symbol == "SBIN" for r in records)
        client.close()


# -- API mocks for fetch_master / fetch_shareholding --

_PREFLIGHT_RE = r"nseindia\.com/companies-listing/corporate-filings-shareholding-pattern"
_MASTER_RE = r"nseindia\.com/api/corporate-share-holdings-master"

_MASTER_ITEM = {
    "symbol": "SBIN",
    "companyName": "State Bank of India",
    "date": "31-Dec-2025",
    "xbrl": "https://nsearchives.nseindia.com/corporate/shareholding_pattern_SBIN_2025.xml",
}


class TestEnsureCookies:
    """Test _ensure_cookies preflight behavior."""

    def test_preflight_marks_cookies_present(self):
        """Successful preflight call sets _has_cookies True."""
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            with NSEHoldingClient() as client:
                assert client._has_cookies is False
                client._ensure_cookies()
                assert client._has_cookies is True

    def test_preflight_failure_raises(self):
        """When preflight returns 5xx, raise_for_status should propagate."""
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(500, text="server error")
            with NSEHoldingClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    client._ensure_cookies()
                assert client._has_cookies is False


class TestFetchMaster:
    """Test fetch_master with mocked NSE API responses."""

    def test_fetch_master_parses_items(self):
        """Master endpoint returning JSON list yields NSEShareholdingMaster objects."""
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[_MASTER_ITEM])
            with NSEHoldingClient() as client:
                results = client.fetch_master("sbin")

            assert len(results) == 1
            item = results[0]
            assert item.symbol == "SBIN"
            assert item.company_name == "State Bank of India"
            assert item.quarter_end == "31-Dec-2025"
            assert item.xbrl_url.endswith(".xml")

    def test_fetch_master_skips_items_without_xbrl(self):
        """Items missing xbrl URL are filtered out."""
        bad_item = {
            "symbol": "SBIN",
            "companyName": "SBI",
            "date": "31-Dec-2025",
            "xbrl": "",
        }
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[bad_item, _MASTER_ITEM])
            with NSEHoldingClient() as client:
                results = client.fetch_master("SBIN")

            assert len(results) == 1
            assert results[0].symbol == "SBIN"

    def test_fetch_master_empty_list(self):
        """Empty JSON array yields empty result list (no error)."""
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[])
            with NSEHoldingClient() as client:
                results = client.fetch_master("SBIN")
            assert results == []

    def test_fetch_master_retries_on_failure(self, monkeypatch):
        """On exception, retries until MAX_RETRIES then raises NSEHoldingError."""
        # Patch sleep so retries don't actually wait.
        monkeypatch.setattr("flowtracker.holding_client.time.sleep", lambda _s: None)

        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            # 500 triggers raise_for_status -> exception -> retry loop
            respx.get(url__regex=_MASTER_RE).respond(500, text="boom")
            with NSEHoldingClient() as client:
                with pytest.raises(NSEHoldingError, match="Failed to fetch master"):
                    client.fetch_master("SBIN")

    def test_fetch_master_403_refreshes_cookies(self, monkeypatch):
        """A 403 response triggers cookie refresh; after MAX_RETRIES, raises."""
        monkeypatch.setattr("flowtracker.holding_client.time.sleep", lambda _s: None)

        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(403, text="forbidden")
            with NSEHoldingClient() as client:
                with pytest.raises(NSEHoldingError):
                    client.fetch_master("SBIN")
                # After 403 path, cookies were invalidated
                assert client._has_cookies is False


class TestFetchShareholding:
    """Test fetch_shareholding which fetches XBRL and delegates to _parse_xbrl."""

    def test_fetch_shareholding_happy_path(self):
        """Direct XBRL download is parsed into records + pledge."""
        xbrl_url = "https://nsearchives.nseindia.com/corporate/sbin_q3_2025.xml"
        with respx.mock:
            respx.get(xbrl_url).respond(200, content=_XBRL_NEWER)
            with NSEHoldingClient() as client:
                records, pledge = client.fetch_shareholding(xbrl_url, "SBIN")

            assert len(records) == 4
            assert {r.category for r in records} == {"Promoter", "FII", "MF", "Public"}
            assert pledge is not None
            assert pledge.pledge_pct == 2.50

    def test_fetch_shareholding_http_error_raises(self):
        """HTTP errors during XBRL fetch are wrapped in NSEHoldingError."""
        xbrl_url = "https://nsearchives.nseindia.com/corporate/missing.xml"
        with respx.mock:
            respx.get(xbrl_url).respond(404, text="not found")
            with NSEHoldingClient() as client:
                with pytest.raises(NSEHoldingError, match="Failed to fetch XBRL"):
                    client.fetch_shareholding(xbrl_url, "SBIN")


class TestFetchLatestQuarters:
    """Test fetch_latest_quarters convenience method."""

    def test_no_filings_raises(self, monkeypatch):
        """Empty master list raises NSEHoldingError."""
        monkeypatch.setattr("flowtracker.holding_client.time.sleep", lambda _s: None)
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[])
            with NSEHoldingClient() as client:
                with pytest.raises(NSEHoldingError, match="No shareholding filings"):
                    client.fetch_latest_quarters("SBIN")

    def test_aggregates_records_and_pledges(self, monkeypatch):
        """Master + per-filing XBRL fetch yields combined records and pledges."""
        monkeypatch.setattr("flowtracker.holding_client.time.sleep", lambda _s: None)

        xbrl_url = _MASTER_ITEM["xbrl"]
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[_MASTER_ITEM])
            respx.get(xbrl_url).respond(200, content=_XBRL_NEWER)

            with NSEHoldingClient() as client:
                records, pledges = client.fetch_latest_quarters("SBIN", num_quarters=1)

            assert len(records) == 4
            assert len(pledges) == 1
            assert pledges[0].pledge_pct == 2.50

    def test_skips_failing_xbrl(self, monkeypatch):
        """When XBRL fetch fails, that filing is skipped without raising."""
        monkeypatch.setattr("flowtracker.holding_client.time.sleep", lambda _s: None)

        xbrl_url = _MASTER_ITEM["xbrl"]
        with respx.mock:
            respx.get(url__regex=_PREFLIGHT_RE).respond(200, text="OK")
            respx.get(url__regex=_MASTER_RE).respond(200, json=[_MASTER_ITEM])
            respx.get(xbrl_url).respond(500, text="boom")

            with NSEHoldingClient() as client:
                records, pledges = client.fetch_latest_quarters("SBIN", num_quarters=1)

            # Failure was swallowed and logged; nothing aggregated
            assert records == []
            assert pledges == []


class TestContextManager:
    """Test NSEHoldingClient context manager protocol."""

    def test_enter_returns_self(self):
        client = NSEHoldingClient()
        with client as c:
            assert c is client
        # After exit, underlying httpx client is closed
        assert client._client.is_closed


class TestDIIExclusion:
    """DII (InstitutionsDomestic) is intentionally NOT in the category map.

    Per the comment in holding_client.py, it would double-count MF/Insurance/AIF,
    so DII rows in XBRL are skipped during parsing.
    """

    _XBRL_WITH_DII = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-shp="http://www.example.com/shareholding">
  <xbrli:context id="ShareholdingPattern_ContextI">
    <xbrli:entity><xbrli:identifier scheme="x">A</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="InstitutionsForeign_ContextI">
    <xbrli:entity><xbrli:identifier scheme="x">A</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="InstitutionsDomestic_ContextI">
    <xbrli:entity><xbrli:identifier scheme="x">A</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>

  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingPattern_ContextI">100.00</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeign_ContextI">18.0</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsDomestic_ContextI">22.0</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
"""

    def test_dii_category_filtered_out(self):
        """InstitutionsDomestic context is not present in _XBRL_CATEGORY_MAP and is dropped."""
        client = NSEHoldingClient()
        records, _ = client._parse_xbrl(self._XBRL_WITH_DII, "SBIN")
        categories = {r.category for r in records}
        assert "DII" not in categories
        # FII still gets through
        assert "FII" in categories
        client.close()
