"""IRDAI Net Premium Earned ingestion client.

Loads curated IRDAI Public Disclosure data (Form L-1-A-RA Revenue Account,
"Premium earned (Net)" line) for the four publicly-listed Indian life insurers
and exposes it via a tiny client interface that the fundamentals backfill
path consumes.

Why a curated dataset and not live scraping
-------------------------------------------
yfinance does NOT expose Net Premium Earned for HDFCLIFE, SBILIFE, ICICIPRULI,
or LICI (verified across ``info``, ``income_stmt``, ``quarterly_income_stmt``,
``balance_sheet``, ``cashflow``). Screener's Excel collapses the insurer
top line to a single "Sales" row that bundles MTM on policyholder funds.
The IRDAI Public Disclosure portal is the regulatory canonical source, but
its document-detail URLs use opaque numeric IDs that change per filing and
the docs themselves are scanned PDFs without a queryable API.

The pragmatic path is to ship a small JSON fixture (``data/irdai_net_premium.json``)
populated from those public disclosures and cross-checked against each insurer's
investor decks and annual reports. The client's surface (``fetch_net_premium_earned``,
``fetch_all_for_symbol``) is the same shape a future live IRDAI scraper would use
— so when IRDAI provides a stable API, only the loader changes; the call sites
in ``fund_commands`` stay put.

Symbol coverage today: HDFCLIFE, SBILIFE, ICICIPRULI, LICI. To add a new
insurer, append rows to the JSON fixture; no code change needed.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from importlib import resources
from typing import Any

from flowtracker.irdai_models import NetPremiumDatapoint

logger = logging.getLogger(__name__)


_DATASET_PACKAGE = "flowtracker.data"
_DATASET_FILE = "irdai_net_premium.json"


class IRDAIClientError(Exception):
    """Raised when the IRDAI dataset is missing or malformed."""


class IRDAIClient:
    """Read curated IRDAI Net Premium data and expose it as datapoints.

    Construction is cheap (loads + validates the bundled JSON once, ~50 rows).
    Callers should reuse one instance per process; the client is read-only and
    thread-safe.
    """

    def __init__(self, dataset: dict[str, Any] | None = None) -> None:
        if dataset is None:
            try:
                dataset = self._load_bundled()
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise IRDAIClientError(
                    f"IRDAI dataset not loadable: {exc}"
                ) from exc
        self._meta: dict[str, Any] = dataset.get("_meta", {})
        raw_points = dataset.get("datapoints", [])
        if not isinstance(raw_points, list):
            raise IRDAIClientError(
                f"Expected 'datapoints' to be a list, got {type(raw_points).__name__}"
            )
        # Validate every row up front — better to fail at startup than mid-backfill.
        self._points: list[NetPremiumDatapoint] = [
            NetPremiumDatapoint(**row) for row in raw_points
        ]
        # Index by (symbol, fiscal_period) for O(1) lookups.
        self._by_key: dict[tuple[str, str], NetPremiumDatapoint] = {
            (p.symbol, p.fiscal_period): p for p in self._points
        }
        # Index by symbol for bulk fetch.
        self._by_symbol: dict[str, list[NetPremiumDatapoint]] = defaultdict(list)
        for p in self._points:
            self._by_symbol[p.symbol].append(p)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_bundled() -> dict[str, Any]:
        """Load the JSON fixture shipped inside the ``flowtracker.data`` package."""
        try:
            text = (
                resources.files(_DATASET_PACKAGE)
                .joinpath(_DATASET_FILE)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise IRDAIClientError(
                f"IRDAI dataset {_DATASET_PACKAGE}/{_DATASET_FILE} not found"
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise IRDAIClientError(
                f"IRDAI dataset {_DATASET_FILE} is not valid JSON: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def covered_symbols(self) -> list[str]:
        """Insurers with at least one datapoint in the bundled dataset."""
        return sorted(self._by_symbol.keys())

    def has_symbol(self, symbol: str) -> bool:
        return symbol.upper() in self._by_symbol

    def fetch_net_premium_earned(
        self, symbol: str, period: str
    ) -> NetPremiumDatapoint | None:
        """Return one datapoint for one (symbol, fiscal_period) or None.

        ``period`` is the human-friendly label (``FY25`` or ``FY26-Q3``).
        """
        key = (symbol.upper().strip(), period.strip().upper())
        return self._by_key.get(key)

    def fetch_all_for_symbol(self, symbol: str) -> list[NetPremiumDatapoint]:
        """Return every datapoint for one insurer, in fiscal-period order."""
        rows = list(self._by_symbol.get(symbol.upper(), []))
        rows.sort(key=lambda p: (p.period_end, p.fiscal_period))
        return rows

    def annual_lookup(self, symbol: str) -> dict[str, float]:
        """Return ``{fiscal_year_end_iso: net_premium_earned_cr}`` for annual rows.

        Shape mirrors ``FundClient.fetch_annual_net_premium_earned`` so the
        fund_commands enrichment loop can swap loaders transparently.
        """
        return {
            p.period_end: p.net_premium_earned_cr
            for p in self._by_symbol.get(symbol.upper(), [])
            if p.is_annual
        }

    def quarterly_lookup(self, symbol: str) -> dict[str, float]:
        """Return ``{quarter_end_iso: net_premium_earned_cr}`` for quarterly rows."""
        return {
            p.period_end: p.net_premium_earned_cr
            for p in self._by_symbol.get(symbol.upper(), [])
            if p.is_quarterly
        }


# Module-level singleton — cheap to keep around.
_default_client: IRDAIClient | None = None


def default_client() -> IRDAIClient:
    """Return a process-wide IRDAIClient, instantiated lazily."""
    global _default_client
    if _default_client is None:
        _default_client = IRDAIClient()
    return _default_client


# ----------------------------------------------------------------------
# Backfill helpers — used by the CLI command and by integration tests
# ----------------------------------------------------------------------


def backfill_symbol(symbol: str, store: Any, client: IRDAIClient | None = None) -> dict[str, int]:
    """Populate ``net_premium_earned`` on annual + quarterly rows for one insurer.

    Returns ``{"annual": <updated>, "quarterly": <updated>, "missing": <skipped>}``.

    The function only WRITES to existing rows that lack ``net_premium_earned``
    or have a stale value — it does not create new rows. Callers that want to
    seed empty histories should run ``flowtrack fund backfill`` first to
    populate the Screener side, then run this to enrich the insurer column.

    Implementation note: we do a targeted UPDATE rather than a full row
    upsert because (a) we don't have the other ~30 fields and (b) the
    main upsert path normalizes/validates everything else; a column
    update is the smallest safe change.
    """
    client = client or default_client()
    sym = symbol.upper()
    annual = client.annual_lookup(sym)
    quarterly = client.quarterly_lookup(sym)
    missing = 0
    annual_updated = 0
    quarterly_updated = 0

    cur = store._conn.cursor()
    for fy_end, npe in annual.items():
        result = cur.execute(
            "UPDATE annual_financials SET net_premium_earned = ? "
            "WHERE symbol = ? AND fiscal_year_end = ?",
            (npe, sym, fy_end),
        )
        if result.rowcount > 0:
            annual_updated += result.rowcount
        else:
            missing += 1
            logger.debug(
                "IRDAI annual %s %s=%s Cr — no annual_financials row to update",
                sym,
                fy_end,
                npe,
            )
    for q_end, npe in quarterly.items():
        result = cur.execute(
            "UPDATE quarterly_results SET net_premium_earned = ? "
            "WHERE symbol = ? AND quarter_end = ?",
            (npe, sym, q_end),
        )
        if result.rowcount > 0:
            quarterly_updated += result.rowcount
        else:
            missing += 1
            logger.debug(
                "IRDAI quarterly %s %s=%s Cr — no quarterly_results row to update",
                sym,
                q_end,
                npe,
            )
    store._conn.commit()
    return {
        "annual": annual_updated,
        "quarterly": quarterly_updated,
        "missing": missing,
    }


def backfill_all(store: Any, client: IRDAIClient | None = None) -> dict[str, dict[str, int]]:
    """Run ``backfill_symbol`` for every insurer in the bundled dataset.

    Returns ``{symbol: {"annual": n, "quarterly": n, "missing": n}}``.
    """
    client = client or default_client()
    out: dict[str, dict[str, int]] = {}
    for sym in client.covered_symbols:
        out[sym] = backfill_symbol(sym, store, client=client)
    return out
