"""ADR/GDR program directory ingestion client.

Loads the bundled curated directory of Indian Depositary Receipt programs and
exposes it via the same shape a future live scrape would use. The data layer
above this (``flowtracker.adr_commands.refresh``) calls
``fetch_indian_dr_programs()`` to get a list of ``AdrProgram`` records and
upserts them into ``adr_programs``.

Why a curated dataset and not a live scrape
-------------------------------------------
The natural source of truth — BNY Mellon's public DR directory at
``adrbny.com/directory/dr-directory.html`` — is JavaScript-rendered and loads
its content via XHR after page load. ``BeautifulSoup`` against the raw HTML
yields only the search-form chrome, no actual program rows. The same is true
of the Citi and JPMorgan equivalent directories. Pulling the data therefore
needs either (a) a headless browser like Playwright or (b) reverse-engineering
the JSON XHR endpoint and risking a brittle private API.

Neither pays off for ~30 mostly-stable program records. Instead we ship a
curated JSON fixture (``data/adr_programs_seed.json``) cross-referenced from
each issuer's most recent 20-F filing, depositary press releases, and
investor-relations DR fact sheets. New programs are rare; analysts can
extend the JSON in-place. The client surface is the same shape a live scrape
would use, so swapping in a Playwright-based loader later is an isolated
change.
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from typing import Any

from flowtracker.adr_models import AdrProgram

logger = logging.getLogger(__name__)


_DATASET_PACKAGE = "flowtracker.data"
_DATASET_FILE = "adr_programs_seed.json"


class AdrClientError(Exception):
    """Raised when the bundled DR programs dataset is missing or malformed."""


class AdrClient:
    """Read curated DR program directory entries.

    Construction is cheap (loads + validates the bundled JSON once, ~30 rows).
    Pass an explicit ``dataset`` dict in tests to avoid touching the real file.
    """

    def __init__(self, dataset: dict[str, Any] | None = None) -> None:
        if dataset is None:
            try:
                dataset = self._load_bundled()
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise AdrClientError(
                    f"ADR seed dataset not loadable: {exc}"
                ) from exc
        self._meta: dict[str, Any] = dataset.get("_meta", {})
        raw_programs = dataset.get("programs", [])
        if not isinstance(raw_programs, list):
            raise AdrClientError(
                f"Expected 'programs' to be a list, got {type(raw_programs).__name__}"
            )
        # Validate every row up front — better to fail at startup than mid-refresh.
        self._programs: list[AdrProgram] = [
            AdrProgram(**row) for row in raw_programs
        ]

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
            raise AdrClientError(
                f"ADR seed dataset {_DATASET_PACKAGE}/{_DATASET_FILE} not found"
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AdrClientError(
                f"ADR seed dataset {_DATASET_FILE} is not valid JSON: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_indian_dr_programs(self) -> list[AdrProgram]:
        """Return all Indian DR programs as ``AdrProgram`` records.

        Async despite the seed-JSON path being purely synchronous so the
        signature matches what a future live (httpx-based) scrape would use.
        Callers should not assume any particular ordering.
        """
        return list(self._programs)

    @property
    def meta(self) -> dict[str, Any]:
        """Dataset metadata (source authority, last_updated, format notes)."""
        return dict(self._meta)
