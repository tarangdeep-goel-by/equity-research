"""NSE shareholding XBRL client for quarterly institutional ownership data."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET

import httpx

from flowtracker.holding_models import (
    NSEShareholdingMaster,
    PromoterPledge,
    ShareholdingBreakdown,
    ShareholdingRecord,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_MASTER_URL = f"{_BASE_URL}/api/corporate-share-holdings-master"
_PREFLIGHT_URL = f"{_BASE_URL}/companies-listing/corporate-filings-shareholding-pattern"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": _PREFLIGHT_URL,
}

MAX_RETRIES = 3
BACKOFF_BASE = 1

# XBRL context ref mapping: category key -> normalized category
# Newer format: "InstitutionsForeign_ContextI" (suffix _ContextI)
# Older format: "InstitutionsForeignI" (suffix I only)
_XBRL_CATEGORY_MAP = {
    "ShareholdingOfPromoterAndPromoterGroup": "Promoter",
    "InstitutionsForeign": "FII",
    "InstitutionsForeignPortfolioInvestor": "FII",  # older XBRL format
    "MutualFundsOrUTI": "MF",
    "MutualFundsOrUti": "MF",  # older format uses lowercase 'ti'
    "InsuranceCompanies": "Insurance",
    "AlternativeInvestmentFunds": "AIF",
    "NonInstitutions": "Public",
    # NOTE: InstitutionsDomestic (DII) deliberately excluded —
    # it's a parent of MF + Insurance + AIF and would double-count.
}

# The XBRL element name we look for shareholding percentage
_PERCENTAGE_TAG = "ShareholdingAsAPercentageOfTotalNumberOfShares"

# Sub-category context-key map for the granular `shareholding_breakdown` table.
# These do NOT roll into the canonical 7-bucket map — they augment it with the
# extra detail that XBRL exposes but the flat table flattens away (Retail vs HNI
# split inside Public, FPI Cat-I/II inside FII, etc.).
_XBRL_SUB_CATEGORY_MAP = {
    "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh": "retail_pct",
    "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh": "hni_pct",
    "BodiesCorporate": "bodies_corporate_pct",
    "NonResidentIndians": "nri_pct",
    "InstitutionsForeignPortfolioInvestorCategoryOne": "fpi_cat1_pct",
    "InstitutionsForeignPortfolioInvestorCategoryTwo": "fpi_cat2_pct",
    "Banks": "banks_pct",
    "OtherFinancialInstitutions": "other_financial_institutions_pct",
    "NBFCsRegisteredWithRBI": "nbfc_pct",
    "ProvidentFundsOrPensionFunds": "provident_pension_funds_pct",
    "VentureCapitalFunds": "venture_capital_funds_pct",
    "SovereignWealthFundsDomestic": "sovereign_wealth_domestic_pct",
    "SovereignWealthFundsForeign": "sovereign_wealth_foreign_pct",
    "ForeignCompanies": "foreign_companies_pct",
    "ForeignNationals": "foreign_nationals_pct",
    "CustodianOrDRHolder": "foreign_dr_holder_pct",
    "OtherForeignShareholders": "other_foreign_pct",
    "OtherIndianShareholders": "other_indian_pct",
    "EmployeeBenefitsTrusts": "employee_benefit_trust_pct",
    "InvestorEducationAndProtectionFund": "iepf_pct",
}

# ADR/GDR share-count tags that we extract from the `CustodianOrDRHolder`
# context. `NumberOfSharesUnderlyingOutstandingDepositoryReceipts` is the
# definitive count of equity shares represented by ADRs/GDRs — pulled
# straight from the SEBI shareholding XBRL, no need to scrape BNY Mellon.
_DR_UNDERLYING_TAG = "NumberOfSharesUnderlyingOutstandingDepositoryReceipts"
_DR_TOTAL_SHARES_TAG = "NumberOfShares"

# XBRL element names for promoter pledge/encumbrance
# New format (2024+): EncumberedShareUnderPledged..., EncumberedSharesHeld...
# Old format (2018-2023): PledgedOrEncumberedSharesHeld...
_PLEDGE_TAGS = {
    "EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares",
    "PledgedOrEncumberedSharesHeldAsPercentageOfTotalNumberOfShares",
}
_ENCUMBERED_TAGS = {
    "EncumberedSharesHeldAsPercentageOfTotalNumberOfShares",
    "PledgedOrEncumberedSharesHeldAsPercentageOfTotalNumberOfShares",
}
_PROMOTER_CONTEXT = "ShareholdingOfPromoterAndPromoterGroup"


class NSEHoldingError(Exception):
    """Raised when NSE shareholding fetch fails."""


class NSEHoldingClient:
    """Client for NSE India shareholding XBRL data."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=90.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    def _ensure_cookies(self) -> None:
        """Hit the shareholding page to acquire session cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def fetch_master(self, symbol: str) -> list[NSEShareholdingMaster]:
        """Fetch list of quarterly shareholding filings for a symbol.

        Returns list of NSEShareholdingMaster with XBRL URLs.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if not self._has_cookies or attempt > 0:
                    self._ensure_cookies()

                resp = self._client.get(
                    _MASTER_URL,
                    params={"index": "equities", "symbol": symbol.upper()},
                )

                if resp.status_code == 403:
                    logger.warning("Got 403, refreshing cookies (attempt %d)", attempt + 1)
                    self._has_cookies = False
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue

                resp.raise_for_status()
                data = resp.json()

                results: list[NSEShareholdingMaster] = []
                for item in data:
                    # The API returns items with fields like:
                    # symbol, companyName, date (e.g. "31-Dec-2025"), xbrl (URL)
                    try:
                        xbrl_url = item.get("xbrl", "")
                        if not xbrl_url:
                            continue
                        results.append(NSEShareholdingMaster(
                            symbol=item.get("symbol", symbol.upper()),
                            company_name=item.get("companyName", ""),
                            quarter_end=item.get("date", ""),
                            xbrl_url=xbrl_url,
                        ))
                    except Exception:
                        continue

                return results

            except NSEHoldingError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d for %s master failed: %s", attempt + 1, symbol, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))

        raise NSEHoldingError(f"Failed to fetch master for {symbol}: {last_error}")

    def fetch_shareholding(self, xbrl_url: str, symbol: str) -> tuple[list[ShareholdingRecord], PromoterPledge | None]:
        """Download and parse XBRL XML to extract shareholding percentages and pledge data.

        XBRL files at nsearchives.nseindia.com don't need auth — direct download.

        For the granular sub-category breakdown (Retail/HNI/Bodies Corporate,
        FPI Cat-I/II, ADR/GDR custodian holding) call `fetch_shareholding_full`
        instead — this method preserves the legacy 2-tuple shape used by older
        callers and tests.
        """
        records, pledge, _breakdown = self.fetch_shareholding_full(xbrl_url, symbol)
        return records, pledge

    def fetch_shareholding_full(
        self, xbrl_url: str, symbol: str,
    ) -> tuple[list[ShareholdingRecord], PromoterPledge | None, ShareholdingBreakdown | None]:
        """Download and parse XBRL → (records, pledge, granular breakdown).

        The breakdown captures the rich sub-category map (Retail/HNI inside
        Public, FPI Cat-I/II inside FII, CustodianOrDRHolder for ADR/GDR
        holdings) and the raw `NumberOfSharesUnderlyingOutstandingDepositoryReceipts`
        share count — none of which fit in the canonical 7-bucket
        `shareholding` table.
        """
        try:
            # Direct download, no NSE cookies needed for archive files
            resp = self._client.get(xbrl_url)
            resp.raise_for_status()

            return self._parse_xbrl_full(resp.content, symbol)
        except Exception as e:
            raise NSEHoldingError(f"Failed to fetch XBRL from {xbrl_url}: {e}")

    def fetch_latest_quarters(
        self, symbol: str, num_quarters: int = 4,
    ) -> tuple[list[ShareholdingRecord], list[PromoterPledge]]:
        """Convenience: fetch master + parse the N most recent XBRL filings."""
        records, pledges, _breakdowns = self.fetch_latest_quarters_full(symbol, num_quarters)
        return records, pledges

    def fetch_latest_quarters_full(
        self, symbol: str, num_quarters: int = 4,
    ) -> tuple[list[ShareholdingRecord], list[PromoterPledge], list[ShareholdingBreakdown]]:
        """Like `fetch_latest_quarters` but also returns granular per-quarter breakdowns.

        Breakdowns line up 1:1 with quarters that produced any sub-category
        data (older XBRL formats may yield empty breakdowns — those are
        skipped).
        """
        master = self.fetch_master(symbol)
        if not master:
            raise NSEHoldingError(f"No shareholding filings found for {symbol}")

        # Take the most recent N filings
        filings = master[:num_quarters]
        all_records: list[ShareholdingRecord] = []
        all_pledges: list[PromoterPledge] = []
        all_breakdowns: list[ShareholdingBreakdown] = []

        for filing in filings:
            try:
                records, pledge, breakdown = self.fetch_shareholding_full(filing.xbrl_url, symbol.upper())
                all_records.extend(records)
                if pledge:
                    all_pledges.append(pledge)
                if breakdown is not None and self._breakdown_has_data(breakdown):
                    all_breakdowns.append(breakdown)
                logger.info("Parsed %s %s: %d records", symbol, filing.quarter_end, len(records))
                time.sleep(0.5)  # Be polite to NSE
            except NSEHoldingError as e:
                logger.warning("Skipping %s %s: %s", symbol, filing.quarter_end, e)

        return all_records, all_pledges, all_breakdowns

    @staticmethod
    def _breakdown_has_data(b: ShareholdingBreakdown) -> bool:
        """True when at least one sub-category field carries a non-null value.

        Older XBRL filings (pre-SEBI v2 format) lack the granular contexts —
        skip empty breakdowns rather than persist no-op rows.
        """
        d = b.model_dump(exclude={"symbol", "quarter_end", "fetched_at"})
        return any(v is not None for v in d.values())

    def _parse_xbrl(self, content: bytes, symbol: str) -> tuple[list[ShareholdingRecord], PromoterPledge | None]:
        """Parse XBRL → (records, pledge). Legacy 2-tuple wrapper around `_parse_xbrl_full`."""
        records, pledge, _breakdown = self._parse_xbrl_full(content, symbol)
        return records, pledge

    def _parse_xbrl_full(
        self, content: bytes, symbol: str,
    ) -> tuple[list[ShareholdingRecord], PromoterPledge | None, ShareholdingBreakdown | None]:
        """Parse XBRL XML and extract shareholding percentages, pledge data,
        and granular sub-category breakdown (Retail/HNI, FPI Cat-I/II, ADR/GDR).

        Looks for elements with tag containing 'ShareholdingAsAPercentageOfTotalNumberOfShares'
        and context ID ending in '_ContextI' (which represents the "as of date" context).

        The quarter_end date is extracted from the context's instant element.
        """
        root = ET.fromstring(content)

        # Find the namespace — XBRL files have varying namespace prefixes
        # We'll search by local name
        records: list[ShareholdingRecord] = []
        quarter_end: str | None = None

        # First, extract the date from context elements
        for elem in root.iter():
            local = _local_name(elem.tag)
            if local == "context":
                ctx_id = elem.get("id", "")
                if not ctx_id:
                    continue
                # Look for instant date in this context
                for child in elem.iter():
                    if _local_name(child.tag) == "instant" and child.text:
                        # Use the first context with an instant date
                        if quarter_end is None:
                            quarter_end = child.text.strip()
                        break

        if not quarter_end:
            logger.warning("No quarter_end date found in XBRL for %s", symbol)
            return [], None, None

        # Now extract shareholding percentages
        # The tag name is always "ShareholdingAsAPercentageOfTotalNumberOfShares"
        # The category is encoded in the contextRef (e.g. "InstitutionsForeign_ContextI")
        #
        # Detect format: newer XBRL uses decimals (0.5001 = 50.01%), older uses
        # actual percentages (50.07). Check the total (ShareholdingPattern_ContextI)
        # to determine which format.
        is_decimal = False
        raw_values: list[tuple[str, float]] = []
        # Sub-category raw values, keyed by canonical context key (no _ContextI suffix).
        sub_raw: dict[str, float] = {}

        for elem in root.iter():
            local = _local_name(elem.tag)
            if local != _PERCENTAGE_TAG:
                continue

            ctx_ref = elem.get("contextRef", "")

            # Handle both formats:
            # Newer: "InstitutionsForeign_ContextI" -> strip "_ContextI"
            # Older: "InstitutionsForeignI" -> strip trailing "I"
            if ctx_ref.endswith("_ContextI"):
                ctx_key = ctx_ref[: -len("_ContextI")]
            elif ctx_ref.endswith("I") and not ctx_ref.endswith("UTI"):
                ctx_key = ctx_ref[:-1]
            else:
                continue

            try:
                val = float(elem.text.strip()) if elem.text else None
            except (ValueError, AttributeError):
                continue

            if val is None:
                continue

            # Check the total to detect format
            if ctx_key == "ShareholdingPattern":
                is_decimal = val <= 2.0  # ~1.0 for decimal, ~100 for percentage
                continue

            if ctx_key in _XBRL_CATEGORY_MAP:
                raw_values.append((ctx_key, val))

            # Capture sub-category raw values; conversion to percent happens
            # after format detection completes.
            if ctx_key in _XBRL_SUB_CATEGORY_MAP:
                sub_raw[ctx_key] = val

        for ctx_key, val in raw_values:
            category = _XBRL_CATEGORY_MAP[ctx_key]
            pct = round(val * 100, 2) if is_decimal else round(val, 2)
            records.append(ShareholdingRecord(
                symbol=symbol.upper(),
                quarter_end=quarter_end,
                category=category,
                percentage=pct,
            ))

        # Extract promoter pledge/encumbrance data
        pledge_pct_raw: float | None = None
        encumbered_pct_raw: float | None = None

        for elem in root.iter():
            local = _local_name(elem.tag)
            ctx_ref = elem.get("contextRef", "")

            # Only care about promoter-level context
            promoter_ctx = False
            if ctx_ref.endswith("_ContextI"):
                ctx_key = ctx_ref[: -len("_ContextI")]
                promoter_ctx = ctx_key == _PROMOTER_CONTEXT
            elif ctx_ref.endswith("I") and not ctx_ref.endswith("UTI"):
                ctx_key = ctx_ref[:-1]
                promoter_ctx = ctx_key == _PROMOTER_CONTEXT

            if not promoter_ctx:
                continue

            try:
                val = float(elem.text.strip()) if elem.text else None
            except (ValueError, AttributeError):
                continue

            if val is None:
                continue

            if local in _PLEDGE_TAGS:
                pledge_pct_raw = val
            elif local in _ENCUMBERED_TAGS:
                encumbered_pct_raw = val

        pledge: PromoterPledge | None = None
        if pledge_pct_raw is not None or encumbered_pct_raw is not None:
            p_pct = pledge_pct_raw or 0.0
            e_pct = encumbered_pct_raw or 0.0
            # Apply same decimal detection
            if is_decimal:
                p_pct = round(p_pct * 100, 2)
                e_pct = round(e_pct * 100, 2)
            else:
                p_pct = round(p_pct, 2)
                e_pct = round(e_pct, 2)
            pledge = PromoterPledge(
                symbol=symbol.upper(),
                quarter_end=quarter_end,
                pledge_pct=p_pct,
                encumbered_pct=e_pct,
            )

        # ADR/GDR share counts under the CustodianOrDRHolder context.
        # `NumberOfSharesUnderlyingOutstandingDepositoryReceipts` is the
        # definitive count of equity shares represented by ADRs/GDRs — i.e.
        # the foreign-headroom-eligible portion the agent needs to size.
        dr_underlying: int | None = None
        custodian_total: int | None = None
        for elem in root.iter():
            local = _local_name(elem.tag)
            ctx_ref = elem.get("contextRef", "")
            if not ctx_ref:
                continue
            if ctx_ref.endswith("_ContextI"):
                ctx_key = ctx_ref[: -len("_ContextI")]
            elif ctx_ref.endswith("I") and not ctx_ref.endswith("UTI"):
                ctx_key = ctx_ref[:-1]
            else:
                continue
            if ctx_key != "CustodianOrDRHolder":
                continue
            if local == _DR_UNDERLYING_TAG:
                try:
                    dr_underlying = int(float(elem.text.strip()))
                except (ValueError, AttributeError, TypeError):
                    pass
            elif local == _DR_TOTAL_SHARES_TAG and custodian_total is None:
                # First occurrence wins — same XBRL emits multiple shapes;
                # we want the bare NumberOfShares, not voting-rights variant.
                try:
                    custodian_total = int(float(elem.text.strip()))
                except (ValueError, AttributeError, TypeError):
                    pass

        # Build the granular breakdown. Convert raw decimals to pct form
        # using the detected format.
        breakdown_kwargs: dict[str, float | int | None] = {}
        for ctx_key, val in sub_raw.items():
            field = _XBRL_SUB_CATEGORY_MAP[ctx_key]
            pct = round(val * 100, 2) if is_decimal else round(val, 2)
            breakdown_kwargs[field] = pct
        if dr_underlying is not None:
            breakdown_kwargs["dr_underlying_shares"] = dr_underlying
        if custodian_total is not None:
            breakdown_kwargs["custodian_total_shares"] = custodian_total

        breakdown: ShareholdingBreakdown | None = None
        if breakdown_kwargs:
            breakdown = ShareholdingBreakdown(
                symbol=symbol.upper(),
                quarter_end=quarter_end,
                **breakdown_kwargs,
            )

        return records, pledge, breakdown

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NSEHoldingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _local_name(tag: str) -> str:
    """Extract local name from a possibly namespaced XML tag.

    '{http://example.com}ElementName' -> 'ElementName'
    'ElementName' -> 'ElementName'
    """
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
