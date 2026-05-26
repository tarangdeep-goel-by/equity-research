"""Playwright-based rendered-HTML fetch helper.

A small synchronous wrapper around Playwright's ``sync_playwright`` API used
as a *fallback* by clients whose upstream sources are JS-rendered SPAs
(Angular / React shells that return only an empty container to plain
``httpx``). Today this powers:

- :mod:`flowtracker.gst_client` — live CBIC / PIB monthly press releases
- :mod:`flowtracker.surveillance_client` — BSE ESM
- :mod:`flowtracker.ipo_client` — BSE SME IPO upcoming

Usage
-----

One-off fetch::

    from flowtracker.js_fetch import fetch_rendered_html, JSFetchError

    try:
        html = fetch_rendered_html(
            "https://www.bseindia.com/markets/equity/EQReports/ESM.html",
            wait_for_selector="table",
            timeout_ms=20_000,
        )
    except JSFetchError as exc:
        logger.warning("BSE ESM JS fetch failed: %s", exc)
        html = None

Batch fetch (reuses one browser context, much faster for >1 URL)::

    with JSFetchSession() as session:
        html_a = session.fetch(url_a, wait_for_selector="table")
        html_b = session.fetch(url_b)

Browser binary requirement
--------------------------

Playwright needs Chromium installed separately::

    uv run playwright install chromium

If the binary is missing, this module raises a clear
:class:`JSFetchError` pointing the user at that command rather than
surfacing Playwright's raw "Executable doesn't exist" traceback.

Design notes
------------

- Sync, not async. Every caller in this codebase is sync (Typer commands,
  ``httpx.Client``); a sync API avoids a global event-loop refactor.
- Heavyweight resource loads (images, fonts, media, stylesheets) are
  blocked by default — the data lives in HTML / JSON, not pixels, so the
  fetch is much faster.
- ``wait_for_selector`` is the supported "table is present" hook; combined
  with ``wait_for_network_idle`` it covers both the "render finished" and
  "data XHR finished" cases.
- Logging: INFO on entry (URL + wait condition), DEBUG on success (page
  title + content size). No prints.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class JSFetchError(Exception):
    """Raised when a JS-rendered fetch fails permanently.

    Includes the missing-browser-binary case (with a remediation hint) and
    navigation/timeout failures the caller can decide to swallow.
    """


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Resource types we block to keep fetches fast. The data we want is always
# in the HTML or JSON XHRs the page issues, never in images/fonts/media.
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "font", "media", "stylesheet"})


# ---------------------------------------------------------------------------
# Session (batch-friendly)
# ---------------------------------------------------------------------------


if TYPE_CHECKING:
    # Imported lazily at runtime; keep the type hint precise for IDE/mypy.
    from playwright.sync_api import Browser, BrowserContext, Playwright


class JSFetchSession:
    """A reusable Playwright browser + context.

    Spinning up Chromium takes ~1-2 seconds; doing it once per URL is
    wasteful when a caller has multiple fetches to do. Use this context
    manager for any batch operation::

        with JSFetchSession() as session:
            for url in urls:
                html = session.fetch(url, wait_for_selector="table")

    The one-shot :func:`fetch_rendered_html` is implemented in terms of
    this same session — there is no behavioural difference for a single
    URL, only the cost of teardown.
    """

    def __init__(self, *, user_agent: str | None = None) -> None:
        self._user_agent = user_agent or _DEFAULT_USER_AGENT
        self._playwright: "Playwright | None" = None
        self._browser: "Browser | None" = None
        self._context: "BrowserContext | None" = None

    # -- lifecycle -----------------------------------------------------

    def __enter__(self) -> "JSFetchSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover — playwright is a hard dep
            raise JSFetchError(
                "Playwright is not installed. Add `playwright>=1.40.0` to "
                "dependencies and run `uv sync`."
            ) from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 — surface every launch error
            self._cleanup()
            msg = str(exc)
            if "Executable doesn't exist" in msg or "BrowserType.launch" in msg:
                raise JSFetchError(
                    "Playwright browser missing. "
                    "Run: uv run playwright install chromium"
                ) from exc
            raise JSFetchError(f"Failed to launch Chromium: {exc}") from exc

        self._context = self._browser.new_context(user_agent=self._user_agent)
        # Block heavy resource types at the routing layer — applied to every
        # page created from this context.
        self._context.route("**/*", _route_block_handler)
        return self

    def __exit__(self, *args: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        # Best-effort tear-down; closing in reverse order. Each step is
        # wrapped because a partial-init failure during __enter__ could
        # leave any combination of these as ``None``.
        if self._context is not None:
            try:
                self._context.close()
            except Exception:  # noqa: BLE001
                logger.debug("JSFetchSession: context close failed", exc_info=True)
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                logger.debug("JSFetchSession: browser close failed", exc_info=True)
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                logger.debug("JSFetchSession: playwright stop failed", exc_info=True)
            self._playwright = None

    # -- fetch ---------------------------------------------------------

    def fetch(
        self,
        url: str,
        *,
        wait_for_selector: str | None = None,
        wait_for_network_idle: bool = True,
        timeout_ms: int = 30_000,
    ) -> str:
        """Navigate to ``url`` and return the fully-rendered HTML body.

        Parameters
        ----------
        url:
            Absolute URL to fetch.
        wait_for_selector:
            CSS selector to wait for after navigation completes. Use this
            for SPAs where the data table is injected after an XHR returns.
            ``None`` skips the explicit wait (rely on network-idle).
        wait_for_network_idle:
            If ``True`` (default), waits for network activity to settle
            before grabbing the HTML. Set ``False`` for pages that hold
            long-lived websockets / polling XHRs open.
        timeout_ms:
            Hard cap on the navigation + wait time. A timeout raises
            :class:`JSFetchError`.

        Returns
        -------
        str
            ``page.content()`` — the full rendered HTML including
            ``<html>`` / ``<head>`` / ``<body>``.
        """
        if self._context is None:
            raise JSFetchError(
                "JSFetchSession used outside of `with` block — "
                "browser context is not initialised."
            )
        logger.info(
            "JS fetch: %s (wait_for_selector=%r, network_idle=%s)",
            url, wait_for_selector, wait_for_network_idle,
        )
        page = self._context.new_page()
        try:
            try:
                # ``domcontentloaded`` returns as soon as the DOM exists;
                # we then layer the explicit selector / network-idle waits
                # to ensure the *data* (not just the shell) is present.
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception as exc:  # noqa: BLE001 — timeout / navigation
                raise JSFetchError(f"Navigation to {url} failed: {exc}") from exc

            if wait_for_network_idle:
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    # Network-idle timeouts are common on pages with long-poll
                    # XHRs — log but don't abort if a selector wait will
                    # still validate the data is present.
                    if wait_for_selector is None:
                        raise JSFetchError(
                            f"Network-idle timeout for {url}: {exc}",
                        ) from exc
                    logger.debug(
                        "Network-idle wait timed out for %s; "
                        "continuing because wait_for_selector=%r is set",
                        url, wait_for_selector,
                    )

            if wait_for_selector is not None:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    raise JSFetchError(
                        f"Selector {wait_for_selector!r} did not appear on {url}: {exc}"
                    ) from exc

            html = page.content()
            logger.debug(
                "JS fetch ok: %s (title=%r, %d bytes)",
                url, page.title(), len(html),
            )
            return html
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                logger.debug("JSFetchSession: page close failed", exc_info=True)


def _route_block_handler(route, request) -> None:  # pragma: no cover — Playwright internal cb
    """Abort heavyweight resource loads to keep fetches fast.

    Called by Playwright for every request the page issues. We accept HTML,
    JSON XHRs (the data we want), and document subresources by default; we
    abort images, fonts, media, and stylesheets.
    """
    try:
        if request.resource_type in _BLOCKED_RESOURCE_TYPES:
            route.abort()
        else:
            route.continue_()
    except Exception:  # noqa: BLE001 — never let a route error escape
        # If the route is already handled or the page closed mid-flight,
        # Playwright raises; swallow silently because there's nothing we
        # can do at this point.
        logger.debug("route handler caught error", exc_info=True)


# ---------------------------------------------------------------------------
# One-shot helper
# ---------------------------------------------------------------------------


def fetch_rendered_html(
    url: str,
    *,
    wait_for_selector: str | None = None,
    wait_for_network_idle: bool = True,
    timeout_ms: int = 30_000,
    user_agent: str | None = None,
) -> str:
    """Fetch ``url`` once, render it with Chromium, return the HTML.

    Thin convenience wrapper around :class:`JSFetchSession` for the common
    case of a single URL. Spins up + tears down Chromium each call —
    callers doing >1 fetch should use :class:`JSFetchSession` directly.

    Raises
    ------
    JSFetchError
        On missing browser binary, navigation failure, or selector timeout.
    """
    with JSFetchSession(user_agent=user_agent) as session:
        return session.fetch(
            url,
            wait_for_selector=wait_for_selector,
            wait_for_network_idle=wait_for_network_idle,
            timeout_ms=timeout_ms,
        )


# ---------------------------------------------------------------------------
# Test seam
# ---------------------------------------------------------------------------


@contextmanager
def _test_session_override(session: JSFetchSession) -> Iterator[None]:
    """Internal: override the session class with a test double.

    Tests should ``unittest.mock.patch`` the symbol ``js_fetch.JSFetchSession``
    directly rather than use this helper; it exists only to document the
    intended seam.
    """
    yield  # pragma: no cover
