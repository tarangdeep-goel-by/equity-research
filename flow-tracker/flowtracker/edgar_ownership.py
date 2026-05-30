"""SEC EDGAR ownership: Form 4 insider + 13F institutional (US add-on, P3.3).

Builds on the reusable HTTP/throttle/CIK plumbing in
:class:`flowtracker.edgar_client.SecEdgarBase` — this module adds the two
ownership pipelines that feed the ``us_insider_transactions`` and
``us_institutional_holdings`` tables. No new HTTP layer is introduced.

Form 4 (insider, issuer-centric)
--------------------------------
EDGAR exposes one Form 4 ``ownershipDocument`` XML per filing. We resolve a
ticker → CIK, list recent ``form == '4'`` accessions from the submissions
index, fetch each filing's primary XML, and map every
``nonDerivativeTransaction`` to a ``us_insider_transactions`` row. Each row
carries the Form 4 transaction code (P=purchase, S=sale, A=grant, M=option
exercise, G=gift, F=tax withholding, ...), shares, price/share, derived
``value = shares × price``, post-transaction shares, and the
director/officer relationship flags.

13F (institutional, manager-centric → stored issuer-centric)
------------------------------------------------------------
13F filings are filed by the MANAGER and list every holding. We parse a
manager's information-table XML into ``us_institutional_holdings`` rows keyed
by ``manager_cik`` + ``quarter_end``. ``symbol`` is the CUSIP→ticker mapping
when resolvable (caller supplies a ``cusip_map``; a small seed for the
validation universe lives in ``_VALIDATION_CUSIP_MAP``), otherwise the CUSIP
string itself — unmapped rows are KEPT, never dropped, with ``cusip`` always
populated.

13F value magnitude convention
-------------------------------
The us_* tables store monetary values in **USD millions** (market
``magnitude_divisor = 1e6``; the ``us_institutional_holdings.value_usd`` bound
in ``_shared.py`` reuses the agnostic/USD handling and is sanity-checked
against that magnitude). 13F ``<value>`` historically reported THOUSANDS of
dollars pre-2023 and whole DOLLARS from 2023+ (SEC Release 33-11070). We
normalize either convention to USD millions:

* period ``quarter_end`` year ≥ 2023 → raw value is dollars → ``/ 1e6``.
* period year ≤ 2022 → raw value is thousands → ``× 1e3 / 1e6 = / 1e3``.

This keeps stored ``value_usd`` comparable across the 2023 boundary and in the
same USD-millions magnitude as every other us_* monetary column.

13F reverse-lookup limitation
-----------------------------
13F is indexed at EDGAR by MANAGER, not by issuer. There is no free, complete
issuer → all-managers reverse index — building one needs a curated fund
universe (iterate every 13F filer, accumulate by CUSIP). That is out of scope
for the validation slice: :func:`fetch_13f_for_manager` proves the
manager → holdings pipeline; full reverse indexing is a documented TODO.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from flowtracker.edgar_client import SecEdgarBase, _USER_AGENT

logger = logging.getLogger(__name__)

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn}"

# CUSIP→ticker seed for the P3.3 validation universe (issuers that turn up in
# the Berkshire/large-cap 13F fixtures). Callers can pass a richer cusip_map;
# anything unmapped falls back to the raw CUSIP string (rows are never dropped).
_VALIDATION_CUSIP_MAP: dict[str, str] = {
    "037833100": "AAPL",   # Apple Inc.
    "594918104": "MSFT",   # Microsoft Corp
    "67066G104": "NVDA",   # NVIDIA Corp
    "46625H100": "JPM",    # JPMorgan Chase
    "30231G102": "XOM",    # Exxon Mobil
    "91324P102": "UNH",    # UnitedHealth Group
    "02079K107": "GOOGL",  # Alphabet Inc. Class C
    "02079K305": "GOOGL",  # Alphabet Inc. Class A
    "025816109": "AXP",    # American Express
    "060505104": "BAC",    # Bank of America
}

# Acquired/disposed → signed convention is preserved via the raw code; we keep
# the transaction_code verbatim so downstream can interpret P/S/A/M/G/F/etc.


def _local(tag: str) -> str:
    """Strip an XML namespace prefix (``{uri}name`` → ``name``)."""
    return tag.rsplit("}", 1)[-1]


def _text(node: ET.Element | None) -> str | None:
    """Return stripped text of a node, or None."""
    if node is None or node.text is None:
        return None
    t = node.text.strip()
    return t or None


def _find_local(parent: ET.Element, *path: str) -> ET.Element | None:
    """Namespace-agnostic descend by local tag names (first match per level)."""
    node: ET.Element | None = parent
    for name in path:
        if node is None:
            return None
        nxt = None
        for child in node:
            if _local(child.tag) == name:
                nxt = child
                break
        node = nxt
    return node


def _val(parent: ET.Element | None, *path: str) -> str | None:
    """Find ``path`` then return the text of its child ``<value>`` (Form 4
    wraps most scalars in a ``<value>`` element), or the node's own text."""
    node = _find_local(parent, *path) if parent is not None else None
    if node is None:
        return None
    value_child = _find_local(node, "value")
    if value_child is not None:
        return _text(value_child)
    return _text(node)


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _to_int(s: str | None) -> int | None:
    f = _to_float(s)
    return None if f is None else int(round(f))


def _bool_flag(s: str | None) -> int:
    """Form 4 booleans appear as 'true'/'1'/'0'/'false'/None → 0/1."""
    if s is None:
        return 0
    return 1 if s.strip().lower() in {"true", "1", "y", "yes"} else 0


# --------------------------------------------------------------------------- #
# Form 4 parsing
# --------------------------------------------------------------------------- #

def parse_form4(
    xml: str | bytes,
    *,
    symbol: str | None = None,
    market: str = "NASDAQ",
    filing_date: str | None = None,
) -> list[dict]:
    """Parse a Form 4 ``ownershipDocument`` XML into insider-transaction rows.

    One row per ``nonDerivativeTransaction``. ``symbol`` defaults to the
    filing's ``issuerTradingSymbol``. ``filing_date`` (the accession's filed
    date) is carried onto every row; when absent we fall back to
    ``periodOfReport``.

    Returns a list of dicts keyed for ``upsert_us_insider_transactions``.
    """
    root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)

    issuer = _find_local(root, "issuer")
    issuer_symbol = _val(issuer, "issuerTradingSymbol")
    sym = (symbol or issuer_symbol or "").upper()

    owner = _find_local(root, "reportingOwner")
    owner_name = _val(owner, "reportingOwnerId", "rptOwnerName")
    rel = _find_local(owner, "reportingOwnerRelationship") if owner is not None else None
    is_director = _bool_flag(_val(rel, "isDirector") if rel is not None else None)
    is_officer = _bool_flag(_val(rel, "isOfficer") if rel is not None else None)
    officer_title = _val(rel, "officerTitle") if rel is not None else None

    period = _val(root, "periodOfReport")
    fdate = filing_date or period

    rows: list[dict] = []
    table = _find_local(root, "nonDerivativeTable")
    if table is None:
        return rows
    for txn in table:
        if _local(txn.tag) != "nonDerivativeTransaction":
            continue
        tdate = _val(txn, "transactionDate")
        code = _val(txn, "transactionCoding", "transactionCode")
        shares = _to_float(_val(txn, "transactionAmounts", "transactionShares"))
        price = _to_float(_val(txn, "transactionAmounts", "transactionPricePerShare"))
        owned_after = _to_float(
            _val(txn, "postTransactionAmounts", "sharesOwnedFollowingTransaction")
        )
        value = (shares * price) if (shares is not None and price is not None) else None
        rows.append({
            "symbol": sym,
            "market": market,
            "currency": "USD",
            "filing_date": fdate,
            "transaction_date": tdate,
            "owner_name": owner_name,
            "owner_title": officer_title,
            "transaction_code": code,
            "shares": shares,
            "price_per_share": price,
            "value": round(value, 2) if value is not None else None,
            "shares_owned_after": owned_after,
            "is_director": is_director,
            "is_officer": is_officer,
        })
    return rows


# --------------------------------------------------------------------------- #
# 13F parsing
# --------------------------------------------------------------------------- #

def parse_13f_infotable(
    xml: str | bytes,
    manager_cik: str,
    manager_name: str,
    quarter_end: str,
    *,
    market: str = "NASDAQ",
    cusip_map: dict[str, str] | None = None,
) -> list[dict]:
    """Parse a 13F information-table XML into institutional-holding rows.

    One row per ``<infoTable>``. ``value_usd`` is normalized to USD millions
    (see module docstring: 2023+ filings report dollars, pre-2023 thousands —
    detected from the ``quarter_end`` year). ``symbol`` is resolved from
    ``cusip_map`` (defaulting to the validation seed); unmapped CUSIPs keep the
    CUSIP string as the symbol and are NEVER dropped.

    Returns a list of dicts keyed for ``upsert_us_institutional_holdings``.
    """
    cmap = {**_VALIDATION_CUSIP_MAP, **(cusip_map or {})}
    in_thousands = _value_in_thousands(quarter_end)
    root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)

    rows: list[dict] = []
    for info in root:
        if _local(info.tag) != "infoTable":
            continue
        cusip = (_val(info, "cusip") or "").strip().upper()
        raw_value = _to_float(_val(info, "value"))
        shares = _to_float(_val(info, "shrsOrPrnAmt", "sshPrnamt"))
        discretion = _val(info, "investmentDiscretion")
        put_call = _val(info, "putCall") or ""
        value_usd = _normalize_13f_value(raw_value, in_thousands)
        symbol = cmap.get(cusip, cusip)
        rows.append({
            "symbol": symbol,
            "market": market,
            "currency": "USD",
            "cusip": cusip,
            "manager_name": manager_name,
            "manager_cik": str(manager_cik),
            "quarter_end": quarter_end,
            "shares": shares,
            "value_usd": value_usd,
            "investment_discretion": discretion,
            "put_call": put_call,
        })
    return rows


def _value_in_thousands(quarter_end: str | None) -> bool:
    """13F ``<value>`` is in THOUSANDS for periods through 2022, DOLLARS from
    2023 (SEC Release 33-11070). Year is read from ``quarter_end`` (YYYY-...)."""
    if not quarter_end:
        return False  # assume modern (dollars) when period unknown
    try:
        year = int(str(quarter_end)[:4])
    except ValueError:
        return False
    return year <= 2022


def _normalize_13f_value(raw: float | None, in_thousands: bool) -> float | None:
    """Normalize a raw 13F ``<value>`` to USD millions."""
    if raw is None:
        return None
    dollars = raw * 1_000.0 if in_thousands else raw
    return round(dollars / 1_000_000.0, 4)


# --------------------------------------------------------------------------- #
# Schedule 13D / 13G parsing (beneficial-ownership / activist stakes)
# --------------------------------------------------------------------------- #
# Since 2024 the SEC requires Schedule 13D/13G filings in a structured
# ``primary_doc.xml`` (schemas ``schedule13d`` / ``schedule13g``). A 13D signals
# an ACTIVIST >5% holder (intent to influence control); a 13G is a PASSIVE >5%
# holder. Each filing carries one or more reporting persons on the cover page.

def _iso_date(val: str | None) -> str | None:
    """``MM/DD/YYYY`` → ``YYYY-MM-DD``; pass through ISO/unparseable/None."""
    if not val:
        return None
    parts = val.strip().split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        mm, dd, yyyy = parts
        return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return val.strip()


# All Schedule 13D/13G form-type variants as they appear in EDGAR submissions.
SC13_FORM_TYPES = frozenset({
    "SCHEDULE 13D", "SCHEDULE 13D/A", "SC 13D", "SC 13D/A",
    "SCHEDULE 13G", "SCHEDULE 13G/A", "SC 13G", "SC 13G/A",
})


def parse_schedule_13dg(
    xml: str | bytes,
    *,
    symbol: str | None = None,
    market: str = "NASDAQ",
    filing_date: str | None = None,
    accession: str | None = None,
) -> list[dict]:
    """Parse a structured Schedule 13D/13G ``primary_doc.xml`` into rows.

    One row per ``coverPageHeaderReportingPersonDetails`` block (group filings
    list several reporting persons). Returns ``[]`` for any non-13D/G XML
    (e.g. a legacy free-text filing or unrelated document) so callers can skip
    gracefully. ``filing_date``/``accession`` (from the submissions index) are
    carried onto every row. ``is_activist`` is 1 for 13D, 0 for 13G.

    Returns a list of dicts keyed for ``upsert_us_activist_holdings``.
    """
    try:
        root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    except ET.ParseError:
        return []
    if _local(root.tag) != "edgarSubmission":
        return []

    header = _find_local(root, "headerData")
    submission_type = (_text(_find_local(header, "submissionType")) or "").strip()
    if "13D" not in submission_type.upper() and "13G" not in submission_type.upper():
        return []
    filer_cik = _text(_find_local(
        header, "filerInfo", "filer", "filerCredentials", "cik"))
    is_activist = 1 if "13D" in submission_type.upper() else 0

    form_data = _find_local(root, "formData")
    cover = _find_local(form_data, "coverPageHeader") if form_data is not None else None
    event_date = _iso_date(_text(_find_local(cover, "eventDateRequiresFilingThisStatement")))

    rows: list[dict] = []
    if form_data is None:
        return rows
    for rp in form_data:
        if _local(rp.tag) != "coverPageHeaderReportingPersonDetails":
            continue
        powers = _find_local(rp, "reportingPersonBeneficiallyOwnedNumberOfShares")
        rows.append({
            "symbol": (symbol or "").upper(),
            "market": market,
            "currency": "USD",
            "filing_type": submission_type,
            "accession": accession,
            "filing_date": filing_date,
            "event_date": event_date,
            "filer_cik": str(filer_cik) if filer_cik else None,
            "reporting_person": _text(_find_local(rp, "reportingPersonName")),
            "type_of_reporting_person": _text(_find_local(rp, "typeOfReportingPerson")),
            "shares": _to_float(_text(_find_local(
                rp, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"))),
            "percent_of_class": _to_float(_text(_find_local(rp, "classPercent"))),
            "sole_voting": _to_float(_text(_find_local(powers, "soleVotingPower"))),
            "shared_voting": _to_float(_text(_find_local(powers, "sharedVotingPower"))),
            "sole_dispositive": _to_float(_text(_find_local(powers, "soleDispositivePower"))),
            "shared_dispositive": _to_float(_text(_find_local(powers, "sharedDispositivePower"))),
            "is_activist": is_activist,
        })
    return rows


# --------------------------------------------------------------------------- #
# Fetch helpers (live EDGAR)
# --------------------------------------------------------------------------- #

class EdgarOwnershipClient(SecEdgarBase):
    """Fetch + parse Form 4 / 13F filings, reusing the SecEdgarBase HTTP layer."""

    def __init__(self, *, user_agent: str = _USER_AGENT) -> None:
        super().__init__(user_agent=user_agent)
        self._ticker_map: dict[str, str] | None = None

    # -- CIK resolution (lazy company_tickers, same source as EdgarClient) --

    def cik_for(self, ticker: str) -> str | None:
        """Resolve a ticker → padded CIK via the company_tickers map."""
        if self._ticker_map is None:
            from flowtracker.edgar_client import _TICKERS_URL
            raw = self._get_json(_TICKERS_URL)
            self._ticker_map = {
                str(v["ticker"]).upper(): self.pad_cik(v["cik_str"])
                for v in raw.values()
                if v.get("ticker") and v.get("cik_str") is not None
            }
        return self._ticker_map.get(ticker.strip().upper())

    def _submissions(self, cik10: str) -> dict:
        return self._get_json(_SUBMISSIONS_URL.format(cik10=cik10))

    def _list_filings(self, cik10: str, forms: set[str], limit: int) -> list[dict]:
        """Return [{accession, primaryDocument, filingDate, reportDate}, ...]
        for recent filings whose form is in ``forms`` (most recent first)."""
        sub = self._submissions(cik10)
        recent = sub.get("filings", {}).get("recent", {})
        forms_arr = recent.get("form", [])
        accn = recent.get("accessionNumber", [])
        prim = recent.get("primaryDocument", [])
        fdate = recent.get("filingDate", [])
        rdate = recent.get("reportDate", [""] * len(forms_arr))
        out: list[dict] = []
        for i, f in enumerate(forms_arr):
            if f in forms:
                out.append({
                    "accession": accn[i],
                    "primaryDocument": prim[i] if i < len(prim) else "",
                    "filingDate": fdate[i] if i < len(fdate) else None,
                    "reportDate": rdate[i] if i < len(rdate) else None,
                })
                if len(out) >= limit:
                    break
        return out

    def _filing_dir(self, cik10: str, accession: str) -> str:
        cik_int = int(cik10)
        accn = accession.replace("-", "")
        return _ARCHIVES.format(cik_int=cik_int, accn=accn)

    def _get_text(self, url: str) -> str:
        """GET ``url`` as text (XML), throttled + retried like ``_get_json``."""
        import time

        import httpx

        from flowtracker.edgar_client import BACKOFF_BASE, EdgarError, MAX_RETRIES
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = self._client.get(url)
                self._last_request = time.monotonic()
                if resp.status_code == 429 or resp.status_code >= 500:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError:
                raise
            except Exception as e:  # network/decode → retry
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
        raise EdgarError(f"Failed after {MAX_RETRIES} attempts: {url}: {last_error}")

    def _primary_xml_name(self, primary_document: str) -> str:
        """The submissions ``primaryDocument`` for Form 4 is often the XSLT
        wrapper path ``xslF345X0?/form4.xml``; the raw XML is the basename."""
        return primary_document.rsplit("/", 1)[-1]

    def fetch_insider_transactions(
        self,
        symbol: str,
        cik: str | None = None,
        limit: int = 40,
        *,
        market: str = "NASDAQ",
    ) -> list[dict]:
        """Fetch + parse recent Form 4 filings for an issuer ticker.

        Resolves ticker → CIK (unless ``cik`` given), lists recent ``form=='4'``
        accessions, fetches each filing's primary XML and parses it. Returns the
        flattened list of ``us_insider_transactions`` rows.
        """
        cik10 = self.pad_cik(cik) if cik else self.cik_for(symbol)
        if not cik10:
            logger.warning("EDGAR: no CIK for ticker %s", symbol)
            return []
        filings = self._list_filings(cik10, {"4"}, limit)
        all_rows: list[dict] = []
        for f in filings:
            xml_name = self._primary_xml_name(f["primaryDocument"])
            url = f"{self._filing_dir(cik10, f['accession'])}/{xml_name}"
            try:
                xml = self._get_text(url)
                rows = parse_form4(
                    xml, symbol=symbol, market=market, filing_date=f["filingDate"],
                )
                all_rows.extend(rows)
            except Exception as e:  # one bad filing shouldn't sink the batch
                logger.warning("EDGAR Form 4 parse failed for %s: %s", url, e)
        return all_rows

    def _13f_infotable_url(self, cik10: str, accession: str) -> str | None:
        """Find the information-table XML in a 13F filing via its index.json.

        The infotable is the ``*.xml`` that is NOT ``primary_doc.xml`` (the
        cover page) — usually a numeric-named file.
        """
        dir_url = self._filing_dir(cik10, accession)
        index = self._get_json(f"{dir_url}/index.json")
        items = index.get("directory", {}).get("item", [])
        candidates = [
            it["name"] for it in items
            if it.get("name", "").lower().endswith(".xml")
            and it["name"].lower() != "primary_doc.xml"
            and not it["name"].lower().startswith("xsl")
        ]
        if not candidates:
            return None
        return f"{dir_url}/{candidates[0]}"

    def fetch_13f_for_manager(
        self,
        manager_cik: str,
        limit: int = 1,
        *,
        market: str = "NASDAQ",
        cusip_map: dict[str, str] | None = None,
    ) -> list[dict]:
        """Fetch + parse a manager's most recent 13F holdings.

        Lists recent ``13F-HR``/``13F-HR/A`` filings, locates the infotable XML,
        parses it into ``us_institutional_holdings`` rows. ``limit`` caps the
        number of filings (default 1 = latest). Proves the manager→holdings
        pipeline; issuer→all-managers reverse indexing is a documented TODO
        (13F is manager-indexed; reverse lookup needs a fund universe).
        """
        cik10 = self.pad_cik(manager_cik)
        sub = self._submissions(cik10)
        manager_name = sub.get("name", str(manager_cik))
        filings = self._list_filings(cik10, {"13F-HR", "13F-HR/A"}, limit)
        all_rows: list[dict] = []
        for f in filings:
            quarter_end = f.get("reportDate") or ""
            url = self._13f_infotable_url(cik10, f["accession"])
            if not url:
                logger.warning("EDGAR 13F: no infotable in %s", f["accession"])
                continue
            try:
                xml = self._get_text(url)
                rows = parse_13f_infotable(
                    xml, manager_cik=cik10, manager_name=manager_name,
                    quarter_end=quarter_end, market=market, cusip_map=cusip_map,
                )
                all_rows.extend(rows)
            except Exception as e:
                logger.warning("EDGAR 13F parse failed for %s: %s", url, e)
        return all_rows

    def fetch_beneficial_ownership(
        self,
        symbol: str,
        cik: str | None = None,
        limit: int = 20,
        *,
        market: str = "NASDAQ",
    ) -> list[dict]:
        """Fetch + parse an issuer's Schedule 13D/13G beneficial-ownership filings.

        Unlike 13F (manager-indexed), 13D/13G are ISSUER-indexed: EDGAR lists
        them under the subject company's CIK. Lists recent 13D/13G filings
        (+ amendments), fetches each structured ``primary_doc.xml``, and parses
        the reporting persons. ``limit`` caps filings (default 20, newest first).

        Legacy free-text filings (pre-2024, no ``primary_doc.xml``) are skipped
        gracefully — only the structured filings are parsed.

        Returns rows keyed for ``upsert_us_activist_holdings``.
        """
        cik10 = self.pad_cik(cik) if cik else self.cik_for(symbol)
        if not cik10:
            logger.warning("EDGAR 13D/G: no CIK for ticker %s", symbol)
            return []
        filings = self._list_filings(cik10, set(SC13_FORM_TYPES), limit)
        all_rows: list[dict] = []
        for f in filings:
            primary = f.get("primaryDocument") or ""
            # Only structured filings carry primary_doc.xml; skip legacy docs.
            if "primary_doc.xml" not in primary and "SCHEDULE_13" not in primary:
                continue
            xml_name = self._primary_xml_name(primary)
            url = f"{self._filing_dir(cik10, f['accession'])}/{xml_name}"
            try:
                xml = self._get_text(url)
                rows = parse_schedule_13dg(
                    xml, symbol=symbol, market=market,
                    filing_date=f.get("filingDate"), accession=f.get("accession"),
                )
                all_rows.extend(rows)
            except Exception as e:  # noqa: BLE001 — best-effort source
                logger.warning("EDGAR 13D/G parse failed for %s: %s", url, e)
        return all_rows
