"""NSE India index constituents fetcher.

Historically this hit NSE's ``/api/equity-stockIndices?index=<NAME>`` endpoint
with a cookie preflight. As of 2026-05-26 NSE returned that route 404 from
their Apache origin (no Akamai signature — a genuine application 404), so the
fetcher was migrated to **niftyindices.com**'s public CSV files at
``/IndexConstituent/ind_<slug>list.csv``. These are stable, no-cookie,
no-rate-limit downloads that are also the canonical files NSE links from
the index pages.

The client exposes the same ``fetch_constituents(index_name)`` surface as
before — callers (`scan refresh`, `scan refresh-sectoral`) don't need to know
the underlying endpoint changed.
"""

from __future__ import annotations

import csv
import io
import logging
import time

import httpx

from flowtracker.scan_models import IndexConstituent

logger = logging.getLogger(__name__)

_BASE_URL = "https://niftyindices.com"
_CSV_URL_TEMPLATE = f"{_BASE_URL}/IndexConstituent/{{slug}}.csv"

# Map our internal index display names → niftyindices CSV slug. Verified
# 2026-05-26 — all 15 entries return 200 with valid CSV bodies.
_INDEX_TO_SLUG: dict[str, str] = {
    # Broad market
    "NIFTY 50": "ind_nifty50list",
    "NIFTY NEXT 50": "ind_niftynext50list",
    "NIFTY MIDCAP 100": "ind_niftymidcap100list",
    "NIFTY MIDCAP 150": "ind_niftymidcap150list",
    "NIFTY SMALLCAP 250": "ind_niftysmallcap250list",
    # Sectoral (10)
    "NIFTY BANK": "ind_niftybanklist",
    "NIFTY IT": "ind_niftyitlist",
    "NIFTY PHARMA": "ind_niftypharmalist",
    "NIFTY AUTO": "ind_niftyautolist",
    "NIFTY FMCG": "ind_niftyfmcglist",
    "NIFTY METAL": "ind_niftymetallist",
    "NIFTY ENERGY": "ind_niftyenergylist",
    "NIFTY REALTY": "ind_niftyrealtylist",
    "NIFTY PSU BANK": "ind_niftypsubanklist",
    "NIFTY FINANCIAL SERVICES": "ind_niftyfinancelist",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/csv,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds

# Used by `scan refresh` (the Nifty 250 universe — NIFTY 50 + NEXT 50 + MIDCAP 150).
_NIFTY_INDICES = ["NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]

# Used by `scan refresh-sectoral` — 11 indices the breadth module needs but
# which aren't part of the Nifty 250 ownership scanner universe.
_SECTORAL_INDICES = [
    # Broad-market (not already in _NIFTY_INDICES)
    "NIFTY MIDCAP 100",
    # Sectoral (10)
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY REALTY",
    "NIFTY PSU BANK",
    "NIFTY FINANCIAL SERVICES",
]

# 12 sectoral + thematic indices added for sector-rotation tracking
# (PR feat/breadth-themes, 2026-05-26). NSE's JSON API
# `/api/equity-stockIndices?index=<name>` returned 404 for ALL indices
# (including NIFTY 50) when probed 2026-05-26 — Akamai 404 page.
# The reliable source is the CSV archives at
# `nsearchives.nseindia.com/content/indices/ind_<slug>list.csv` (or
# `ind_<slug>_list.csv` for some thematics). Slugs are NOT a uniform
# transformation of the display name — we hard-code them here from
# probing each URL. Display name == the canonical key written into
# `index_constituents.index_name`; cross-listed with
# `breadth_compute.THEME_INDICES`.
_THEME_INDEX_CSV_FILES: list[tuple[str, str]] = [
    # -- Sectoral (6) --
    # Alok's underweight call: private banks vs PSU + financial services
    ("NIFTY PRIVATE BANK", "ind_nifty_privatebanklist.csv"),
    # Sandeep's HOO hospitals/diagnostics + Baid's CDMO — broader than Pharma
    ("NIFTY HEALTHCARE INDEX", "ind_niftyhealthcarelist.csv"),
    # Energy split: pure oil & gas (separate from broad Energy index)
    ("NIFTY OIL & GAS", "ind_niftyoilgaslist.csv"),
    # Robin / Equitree explicit negative
    ("NIFTY MEDIA", "ind_niftymedialist.csv"),
    # Consumption-discretionary play
    ("NIFTY CONSUMER DURABLES", "ind_niftyconsumerdurableslist.csv"),
    # Government-owned PSU theme
    ("NIFTY CPSE", "ind_niftycpselist.csv"),
    # -- Thematic (6) --
    # Equitree's defense-exports 35% CAGR thesis
    ("NIFTY INDIA DEFENCE", "ind_niftyindiadefence_list.csv"),
    # Baid's triple-cut consumption boom
    ("NIFTY INDIA CONSUMPTION", "ind_niftyconsumptionlist.csv"),
    # Equitree's Europe+1 + Baid's precision-engineering thesis
    ("NIFTY INDIA MANUFACTURING", "ind_niftyindiamanufacturing_list.csv"),
    # Sandeep's HOO infrastructure
    ("NIFTY INFRASTRUCTURE", "ind_niftyinfralist.csv"),
    # Sandeep's HOO #1 hotels thesis
    ("NIFTY INDIA TOURISM", "ind_niftyindiatourism_list.csv"),
    # Multinational subsidiaries (export beneficiaries)
    ("NIFTY MNC", "ind_niftymnclist.csv"),
]

_ARCHIVES_BASE = "https://nsearchives.nseindia.com/content/indices"



class NSEIndexError(Exception):
    """Raised when an index constituent fetch permanently fails."""


def _parse_csv(text: str, index_name: str) -> list[IndexConstituent]:
    """Parse niftyindices.com CSV body into IndexConstituent rows.

    Expected columns: ``Company Name, Industry, Symbol, Series, ISIN Code``.
    Rows where ``Symbol`` is empty or where ``Series`` is not ``EQ`` are
    skipped (some indices include preference shares / DVRs in non-EQ series
    that we don't want to track as constituents).
    """
    reader = csv.DictReader(io.StringIO(text))
    out: list[IndexConstituent] = []
    for row in reader:
        symbol = (row.get("Symbol") or "").strip()
        if not symbol:
            continue
        series = (row.get("Series") or "EQ").strip().upper()
        if series and series != "EQ":
            continue
        out.append(IndexConstituent(
            symbol=symbol,
            index_name=index_name,
            company_name=(row.get("Company Name") or "").strip() or None,
            industry=(row.get("Industry") or "").strip() or None,
        ))
    return out


class NSEIndexClient:
    """Client for NSE / niftyindices.com index constituents."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=10.0),
        )

    def fetch_constituents(self, index_name: str) -> list[IndexConstituent]:
        """Fetch constituents of a named index from niftyindices.com.

        Args:
            index_name: Index display name (e.g. "NIFTY 50", "NIFTY BANK").
                Must be a key of ``_INDEX_TO_SLUG``.

        Returns the list of EQ-series constituents.

        Raises:
            NSEIndexError: on unknown index_name, repeated HTTP failure, or
                an empty CSV body.
        """
        slug = _INDEX_TO_SLUG.get(index_name)
        if slug is None:
            raise NSEIndexError(
                f"Unknown index '{index_name}'. Add to _INDEX_TO_SLUG "
                f"in scan_client.py if it's a real NSE index."
            )
        url = _CSV_URL_TEMPLATE.format(slug=slug)

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                constituents = _parse_csv(resp.text, index_name)
                if not constituents:
                    raise NSEIndexError(
                        f"CSV at {url} parsed to 0 constituents — "
                        f"either niftyindices changed schema or the index "
                        f"is empty."
                    )
                return constituents
            except NSEIndexError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "Attempt %d failed for %s: %s", attempt + 1, index_name, e
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise NSEIndexError(
            f"Failed after {MAX_RETRIES} attempts for {index_name}: {last_error}"
        )

    def fetch_all_nifty250(self) -> list[IndexConstituent]:
        """Fetch constituents of the four broad indices that compose Nifty 250.

        Deduplicates by symbol, keeping the first occurrence (from the more
        prestigious index). Sleeps 0.5s between calls to be polite.
        """
        all_constituents: list[IndexConstituent] = []
        seen: set[str] = set()

        for i, index_name in enumerate(_NIFTY_INDICES):
            if i > 0:
                time.sleep(0.5)

            batch = self.fetch_constituents(index_name)
            for c in batch:
                if c.symbol not in seen:
                    seen.add(c.symbol)
                    all_constituents.append(c)

        return all_constituents

    def fetch_sectoral_indices(
        self,
        index_names: list[str] | None = None,
    ) -> dict[str, list[IndexConstituent]]:
        """Fetch constituents for each sectoral / extra broad-market index.

        Returns a ``{index_name: constituents}`` mapping. Symbols are NOT
        deduplicated across indices — each sectoral index keeps its own
        membership (stocks can legitimately appear in multiple, e.g. HDFCBANK
        in NIFTY BANK + NIFTY FINANCIAL SERVICES + NIFTY 50).

        Failures for a single index are caught + logged (returned as an empty
        list for that key) so a partial niftyindices.com outage doesn't kill
        the whole refresh.

        Args:
            index_names: Optional override. Defaults to ``_SECTORAL_INDICES``.
        """
        targets = index_names if index_names is not None else _SECTORAL_INDICES
        out: dict[str, list[IndexConstituent]] = {}
        for i, name in enumerate(targets):
            if i > 0:
                time.sleep(0.5)
            try:
                out[name] = self.fetch_constituents(name)
            except NSEIndexError as e:
                logger.warning("Sectoral fetch failed for %s: %s", name, e)
                out[name] = []
        return out

    def fetch_constituents_from_archives(
        self, display_name: str, csv_filename: str,
    ) -> list[IndexConstituent]:
        """Fetch index constituents from the NSE archives CSV.

        The JSON `/api/equity-stockIndices` endpoint returned 404 for
        all indices when probed 2026-05-26; the CSV at
        ``nsearchives.nseindia.com/content/indices/<csv_filename>`` is
        the reliable lightweight source. Each CSV has columns:
        ``Company Name, Industry, Symbol, Series, ISIN Code``.

        Raises ``NSEIndexError`` on HTTP failure or empty CSV.
        """
        url = f"{_ARCHIVES_BASE}/{csv_filename}"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
        except Exception as e:
            raise NSEIndexError(
                f"Archives fetch failed for {display_name} "
                f"({csv_filename}): {e}"
            )

        reader = csv.DictReader(io.StringIO(resp.text))
        constituents: list[IndexConstituent] = []
        for row in reader:
            sym = (row.get("Symbol") or "").strip()
            if not sym:
                continue
            constituents.append(IndexConstituent(
                symbol=sym,
                index_name=display_name,
                company_name=(row.get("Company Name") or "").strip() or None,
                industry=(row.get("Industry") or "").strip() or None,
            ))

        if not constituents:
            raise NSEIndexError(
                f"Empty constituent list for {display_name} ({csv_filename})"
            )
        return constituents

    def fetch_theme_indices(
        self,
    ) -> tuple[list[IndexConstituent], list[str]]:
        """Fetch the 12 sectoral + thematic indices defined in ``_THEME_INDEX_CSV_FILES``.

        Uses the NSE archives CSV path (not the `/api/equity-stockIndices`
        JSON endpoint, which 404s for all indices as of 2026-05-26).
        Sleeps 1s between fetches to match ``fetch_all_nifty250`` pacing.
        Returns ``(all_constituents, failed_display_names)`` — per-index
        fetch errors are logged and the failed display name is added to
        the second tuple element so one bad CSV doesn't block the rest.
        """
        all_constituents: list[IndexConstituent] = []
        failed: list[str] = []

        for i, (display_name, csv_filename) in enumerate(_THEME_INDEX_CSV_FILES):
            if i > 0:
                time.sleep(1)
            try:
                batch = self.fetch_constituents_from_archives(
                    display_name, csv_filename,
                )
            except NSEIndexError as e:
                logger.warning(
                    "Skipping '%s' — %s", display_name, e,
                )
                failed.append(display_name)
                continue
            except Exception as e:  # noqa: BLE001 — log+continue per spec
                logger.warning(
                    "Skipping '%s' — unexpected: %s", display_name, e,
                )
                failed.append(display_name)
                continue
            logger.info(
                "Fetched %d constituents for '%s'",
                len(batch), display_name,
            )
            all_constituents.extend(batch)

        return all_constituents, failed

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> NSEIndexClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
