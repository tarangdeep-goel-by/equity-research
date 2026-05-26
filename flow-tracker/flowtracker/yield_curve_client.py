"""India G-sec yield-curve historical loader (bundled FBIL/CCIL seed).

This client is *seed-only* — live daily updates flow through the existing
``MacroClient._fetch_gsec_curve()`` path which scrapes CCIL's Tenorwise
Indicative Yields page for today's full curve. Historical backfill (so
the macro agent can show slope-vs-history percentiles) is supplied by
this seed: ~45 quarterly snapshots covering 2014-Q1 to 2025-Q1, sourced
from FBIL's public closing-yields archive.

Why a seed instead of a live scrape:
* FBIL exposes daily CSVs but the per-day download URL (``/data/G-Sec/
  Closing-Yields/{YYYY-MM-DD}``) is rate-limited and inconsistent for
  pre-2018 dates.
* CCIL doesn't expose history at all — only today.
* RBI WSS Statement 25 has the data but requires per-week PDF download
  + per-week parser; for the analyst use case (regime/percentile
  context for current curve) quarterly samples back to 2014 are
  sufficient.

The seed format intentionally mirrors what :class:`YieldCurveSnapshot`
expects so backfill is a direct upsert path into ``macro_daily``.
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from typing import Any

from flowtracker.macro_models import MacroSnapshot
from flowtracker.yield_curve_models import YieldCurveSnapshot

logger = logging.getLogger(__name__)

_SEED_PACKAGE = "flowtracker.data"
_SEED_FILE = "yield_curve_seed.json"


class YieldCurveClientError(Exception):
    """Raised when the bundled yield-curve seed is missing or malformed."""


class YieldCurveClient:
    """Loads historical G-sec yield-curve snapshots from the bundled seed."""

    def __init__(self, *, seed: dict[str, Any] | None = None) -> None:
        if seed is None:
            try:
                seed = self._load_bundled_seed()
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise YieldCurveClientError(
                    f"Yield-curve seed dataset not loadable: {exc}",
                ) from exc
        self._meta: dict[str, Any] = seed.get("_meta", {})
        raw_rows = seed.get("snapshots", [])
        if not isinstance(raw_rows, list):
            raise YieldCurveClientError(
                f"Expected 'snapshots' to be a list, got {type(raw_rows).__name__}",
            )
        self._by_date: dict[str, YieldCurveSnapshot] = {}
        for row in raw_rows:
            try:
                rec = YieldCurveSnapshot(**row)
            except Exception:
                logger.warning(
                    "Yield-curve seed row skipped (validation): %r",
                    row, exc_info=True,
                )
                continue
            self._by_date[rec.date] = rec

    @staticmethod
    def _load_bundled_seed() -> dict[str, Any]:
        try:
            text = (
                resources.files(_SEED_PACKAGE)
                .joinpath(_SEED_FILE)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise YieldCurveClientError(
                f"Yield-curve seed dataset {_SEED_PACKAGE}/{_SEED_FILE} not found",
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise YieldCurveClientError(
                f"Yield-curve seed dataset {_SEED_FILE} is not valid JSON: {exc}",
            ) from exc

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def known_dates(self) -> list[str]:
        return sorted(self._by_date)

    def fetch_all(self) -> list[YieldCurveSnapshot]:
        """Return every seed snapshot, ordered by date ascending."""
        return [self._by_date[d] for d in sorted(self._by_date)]

    def fetch_in_range(self, start_date: str, end_date: str) -> list[YieldCurveSnapshot]:
        """Return seed snapshots whose ``date`` falls in ``[start_date, end_date]``.

        Dates are compared lexicographically since both ends use ISO format.
        """
        return [
            self._by_date[d]
            for d in sorted(self._by_date)
            if start_date <= d <= end_date
        ]

    def to_macro_snapshots(
        self,
        snapshots: list[YieldCurveSnapshot] | None = None,
    ) -> list[MacroSnapshot]:
        """Convert yield-curve snapshots to ``MacroSnapshot`` records that
        can be passed directly to ``FlowStore.upsert_macro_snapshots``.

        Non-yield columns (VIX, FX, Brent) are left None — the upsert
        merges with existing rows on (date) but since ``INSERT OR REPLACE``
        rewrites the whole row, the caller MUST run this only for dates
        that don't already have FX/VIX data (use ``--respect-existing``
        in the CLI to filter).
        """
        if snapshots is None:
            snapshots = self.fetch_all()
        return [
            MacroSnapshot(
                date=s.date,
                gsec_1y=s.gsec_1y,
                gsec_5y=s.gsec_5y,
                gsec_10y=s.gsec_10y,
                gsec_30y=s.gsec_30y,
            )
            for s in snapshots
        ]
