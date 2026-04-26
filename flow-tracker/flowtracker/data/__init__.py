"""Curated public-disclosure datasets shipped with flowtracker.

These are static reference datasets derived from regulatory or public sources
that don't have a clean programmatic API. Each file documents its source and
collection method in a header comment or sibling README.

Currently:
- ``irdai_net_premium.json`` — Net Premium Earned (₹ Cr) for the four
  publicly-listed life insurers, sourced from IRDAI quarterly Public
  Disclosures (Form L-1-A-RA Revenue Account, line "Premium earned (Net)").
  Used by ``flowtracker.irdai_client.IRDAIClient`` to populate the
  ``net_premium_earned`` column where yfinance has no data.
"""
