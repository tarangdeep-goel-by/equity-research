"""Pydantic models for IPO + SME pipeline tracker.

Three record types persisted separately:
- ``IPOIssue`` — calendar entry for an upcoming / current issue (NSE mainboard
  or SME, BSE SME). Symbol is often null at the upcoming stage and only
  assigned at listing.
- ``IPOSubscription`` — point-in-time subscription multiple snapshot keyed on
  (issuer, as_of_date). NSE refreshes these every few minutes during the
  issue window.
- ``IPOListing`` — first-day listing record (open + close + listing pop %).

Issuer name is the join key across the three tables — NSE doesn't expose a
stable internal ID and the listed symbol only exists after the listing event.

Use case: Sandeep flagged Jio Platforms (~₹55,000 cr) as an upcoming
ecosystem-repricer event; Baid flagged dubious-IPO oversubscription as a
bull-top indicator. We need both the calendar (who's coming) and the
subscription book (which issues are blowing past 50× retail).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IPOIssue(BaseModel):
    """A single upcoming / current IPO entry (mainboard or SME)."""

    model_config = ConfigDict(extra="ignore")

    issuer_name: str
    symbol: str | None = None        # assigned only at listing
    segment: str                      # "MAIN" | "SME"
    exchange: str                     # "NSE" | "BSE"
    open_date: str | None = None      # YYYY-MM-DD
    close_date: str | None = None     # YYYY-MM-DD
    listing_date: str | None = None   # YYYY-MM-DD
    price_band_low: float | None = None
    price_band_high: float | None = None
    issue_size_cr: float | None = None
    lot_size: int | None = None


class IPOSubscription(BaseModel):
    """Subscription multiple snapshot for one issue at one point in time.

    Each "_times" field is the oversubscription multiple for that investor
    category (e.g. ``qib_times = 12.5`` means QIB book is 12.5× subscribed).
    ``total_times`` is the overall book.
    """

    model_config = ConfigDict(extra="ignore")

    issuer_name: str                  # join key against IPOIssue
    as_of_date: str                   # YYYY-MM-DD when the snapshot was taken
    qib_times: float | None = None
    nii_times: float | None = None
    retail_times: float | None = None
    employee_times: float | None = None
    total_times: float | None = None


class IPOListing(BaseModel):
    """Listing-day record for a newly listed stock.

    ``listing_pop_pct`` is the percentage move from issue price to listing-day
    close — positive means a successful listing, negative means a flop.
    """

    model_config = ConfigDict(extra="ignore")

    symbol: str
    issuer_name: str
    listing_date: str                 # YYYY-MM-DD
    listing_price: float | None = None        # discovered price at listing
    listing_day_close: float | None = None    # close on listing day
    listing_pop_pct: float | None = None      # (close - issue_price) / issue_price * 100
