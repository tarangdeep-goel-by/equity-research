"""Tests for holding_client.py — NSE XBRL shareholding parsing."""

from __future__ import annotations

from flowtracker.holding_client import NSEHoldingClient, _local_name


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
