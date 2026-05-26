"""Tests for ``flowtracker.js_fetch`` — Playwright-based rendered-HTML helper.

These tests must NEVER actually launch Chromium — Playwright cold-start is
~2s and we run >1000 unit tests in <20s. We patch ``sync_playwright`` with a
mock that mimics the call chain ``.start().chromium.launch().new_context()
.new_page().goto()/.content()``. The mock also exercises the resource-block
route handler and the browser-missing error path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from flowtracker import js_fetch as js_fetch_module
from flowtracker.js_fetch import (
    JSFetchError,
    JSFetchSession,
    _route_block_handler,
    fetch_rendered_html,
)


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _build_playwright_mock(
    *,
    rendered_html: str = "<html><body>OK</body></html>",
    title: str = "Test Page",
    launch_error: Exception | None = None,
) -> tuple[MagicMock, dict]:
    """Build a mock for ``sync_playwright()`` that imitates the full chain.

    Returns ``(mock_factory, refs)`` where ``refs`` collects the
    intermediate handles so individual assertions can inspect them
    (e.g. assert ``goto`` was called with the right URL).
    """
    refs: dict = {}

    page = MagicMock(name="page")
    page.content.return_value = rendered_html
    page.title.return_value = title
    refs["page"] = page

    context = MagicMock(name="context")
    context.new_page.return_value = page
    refs["context"] = context

    browser = MagicMock(name="browser")
    if launch_error is None:
        browser.new_context.return_value = context
    refs["browser"] = browser

    chromium = MagicMock(name="chromium")
    if launch_error is None:
        chromium.launch.return_value = browser
    else:
        chromium.launch.side_effect = launch_error
    refs["chromium"] = chromium

    playwright_handle = MagicMock(name="playwright_handle")
    playwright_handle.chromium = chromium
    refs["playwright_handle"] = playwright_handle

    factory = MagicMock(name="sync_playwright")
    started = MagicMock(name="started")
    started.start.return_value = playwright_handle
    factory.return_value = started
    refs["factory"] = factory
    refs["started"] = started

    return factory, refs


# ---------------------------------------------------------------------------
# fetch_rendered_html — happy path
# ---------------------------------------------------------------------------


class TestFetchRenderedHtml:
    def test_calls_goto_and_returns_content(self):
        factory, refs = _build_playwright_mock(
            rendered_html="<html><body>RENDERED</body></html>",
        )
        with patch("playwright.sync_api.sync_playwright", factory):
            html = fetch_rendered_html(
                "https://example.com/page",
                wait_for_network_idle=False,
                timeout_ms=15_000,
            )
        assert html == "<html><body>RENDERED</body></html>"
        # page.goto was called with the URL
        refs["page"].goto.assert_called_once()
        goto_args = refs["page"].goto.call_args
        assert goto_args.args[0] == "https://example.com/page"
        assert goto_args.kwargs.get("timeout") == 15_000

    def test_honours_wait_for_selector(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            fetch_rendered_html(
                "https://example.com/page",
                wait_for_selector="table.data",
                wait_for_network_idle=False,
                timeout_ms=15_000,
            )
        refs["page"].wait_for_selector.assert_called_once()
        args = refs["page"].wait_for_selector.call_args
        assert args.args[0] == "table.data"

    def test_network_idle_wait_invoked_by_default(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            fetch_rendered_html("https://example.com/page", timeout_ms=10_000)
        refs["page"].wait_for_load_state.assert_called_once()
        args = refs["page"].wait_for_load_state.call_args
        assert args.args[0] == "networkidle"

    def test_resource_blocking_route_is_installed(self):
        """The session installs ``context.route('**/*', _route_block_handler)``
        — confirm the route call happened with the right pattern."""
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            fetch_rendered_html(
                "https://example.com/page",
                wait_for_network_idle=False,
            )
        refs["context"].route.assert_called_once()
        args = refs["context"].route.call_args
        assert args.args[0] == "**/*"
        # The handler is our module's _route_block_handler
        assert args.args[1] is js_fetch_module._route_block_handler

    def test_user_agent_passed_to_context(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            fetch_rendered_html(
                "https://example.com/page",
                wait_for_network_idle=False,
                user_agent="my-bot/1.0",
            )
        refs["browser"].new_context.assert_called_once()
        kwargs = refs["browser"].new_context.call_args.kwargs
        assert kwargs.get("user_agent") == "my-bot/1.0"

    def test_cleans_up_on_success(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            fetch_rendered_html(
                "https://example.com/page",
                wait_for_network_idle=False,
            )
        refs["page"].close.assert_called_once()
        refs["context"].close.assert_called_once()
        refs["browser"].close.assert_called_once()
        # ``sync_playwright().start()`` returns the playwright handle; the
        # session stores it as self._playwright and calls .stop() on it.
        refs["playwright_handle"].stop.assert_called_once()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_browser_missing_raises_clear_error(self):
        """When Chromium isn't installed, Playwright raises an error whose
        message contains ``Executable doesn't exist`` — we must rewrap as
        :class:`JSFetchError` with the remediation hint."""
        # Simulate the actual exception shape — Playwright's Error message.
        launch_err = RuntimeError(
            "BrowserType.launch: Executable doesn't exist at "
            "/Users/x/Library/Caches/ms-playwright/chromium/chrome-mac/Chromium.app"
        )
        factory, _ = _build_playwright_mock(launch_error=launch_err)
        with patch("playwright.sync_api.sync_playwright", factory):
            with pytest.raises(JSFetchError) as excinfo:
                fetch_rendered_html("https://example.com")
        assert "playwright install chromium" in str(excinfo.value).lower()

    def test_navigation_error_raises_js_fetch_error(self):
        """A ``page.goto`` failure (timeout / DNS) propagates as JSFetchError."""
        factory, refs = _build_playwright_mock()
        refs["page"].goto.side_effect = RuntimeError("Navigation timeout")
        with patch("playwright.sync_api.sync_playwright", factory):
            with pytest.raises(JSFetchError) as excinfo:
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_network_idle=False,
                )
        assert "Navigation to https://example.com/page failed" in str(excinfo.value)

    def test_selector_timeout_raises_js_fetch_error(self):
        factory, refs = _build_playwright_mock()
        refs["page"].wait_for_selector.side_effect = RuntimeError(
            "Timeout 30000ms exceeded"
        )
        with patch("playwright.sync_api.sync_playwright", factory):
            with pytest.raises(JSFetchError) as excinfo:
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_selector="table",
                    wait_for_network_idle=False,
                )
        assert "did not appear on" in str(excinfo.value)

    def test_session_used_outside_with_block_raises(self):
        session = JSFetchSession()
        # No __enter__ called — context is None
        with pytest.raises(JSFetchError) as excinfo:
            session.fetch("https://example.com")
        assert "outside of `with` block" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Resource-blocking handler
# ---------------------------------------------------------------------------


class TestRouteBlockHandler:
    @pytest.mark.parametrize(
        "resource_type",
        ["image", "font", "media", "stylesheet"],
    )
    def test_blocks_heavy_resources(self, resource_type):
        route = MagicMock(name="route")
        request = MagicMock(name="request")
        request.resource_type = resource_type
        _route_block_handler(route, request)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    @pytest.mark.parametrize(
        "resource_type",
        ["document", "xhr", "fetch", "script"],
    )
    def test_allows_data_resources(self, resource_type):
        route = MagicMock(name="route")
        request = MagicMock(name="request")
        request.resource_type = resource_type
        _route_block_handler(route, request)
        route.continue_.assert_called_once()
        route.abort.assert_not_called()

    def test_swallows_route_handler_errors(self):
        """If route.continue_() throws (page already closed), don't crash."""
        route = MagicMock(name="route")
        route.continue_.side_effect = RuntimeError("page closed")
        request = MagicMock(name="request")
        request.resource_type = "document"
        # Must not raise
        _route_block_handler(route, request)


# ---------------------------------------------------------------------------
# JSFetchSession (batch)
# ---------------------------------------------------------------------------


class TestStealthMode:
    """playwright-stealth integration — verify the right knobs flip when
    ``use_stealth=True`` is passed."""

    def test_default_does_not_invoke_stealth(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            with patch("playwright_stealth.Stealth") as MockStealth:
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_network_idle=False,
                )
        # Stealth class must NOT be instantiated when use_stealth=False
        MockStealth.assert_not_called()
        # No special launch args / channel either
        kwargs = refs["chromium"].launch.call_args.kwargs
        assert "channel" not in kwargs
        assert "args" not in kwargs

    def test_stealth_passes_chrome_channel_and_args_to_launch(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            with patch("playwright_stealth.Stealth") as MockStealth:
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_network_idle=False,
                    use_stealth=True,
                )
        kwargs = refs["chromium"].launch.call_args.kwargs
        assert kwargs.get("channel") == "chrome"
        args = kwargs.get("args") or []
        assert any("AutomationControlled" in a for a in args)

    def test_stealth_applies_to_context(self):
        factory, refs = _build_playwright_mock()
        instance = MagicMock(name="stealth_instance")
        with patch("playwright.sync_api.sync_playwright", factory):
            with patch(
                "playwright_stealth.Stealth", return_value=instance,
            ) as MockStealth:
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_network_idle=False,
                    use_stealth=True,
                )
        MockStealth.assert_called_once()
        instance.apply_stealth_sync.assert_called_once_with(refs["context"])

    def test_stealth_sets_realistic_context_options(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            with patch("playwright_stealth.Stealth"):
                fetch_rendered_html(
                    "https://example.com/page",
                    wait_for_network_idle=False,
                    use_stealth=True,
                )
        ctx_kwargs = refs["browser"].new_context.call_args.kwargs
        # IN locale + Asia/Kolkata timezone + 1920x1080 viewport + Chrome UA
        assert ctx_kwargs.get("locale") == "en-IN"
        assert ctx_kwargs.get("timezone_id") == "Asia/Kolkata"
        assert ctx_kwargs.get("viewport") == {"width": 1920, "height": 1080}
        ua = ctx_kwargs.get("user_agent") or ""
        assert "Chrome/131" in ua
        # sec-ch-ua extra headers
        extras = ctx_kwargs.get("extra_http_headers") or {}
        assert "sec-ch-ua" in extras
        assert "Google Chrome" in extras["sec-ch-ua"]


class TestJSFetchSession:
    def test_batch_fetches_reuse_one_browser(self):
        factory, refs = _build_playwright_mock()
        with patch("playwright.sync_api.sync_playwright", factory):
            with JSFetchSession() as session:
                session.fetch("https://a.test", wait_for_network_idle=False)
                session.fetch("https://b.test", wait_for_network_idle=False)
                session.fetch("https://c.test", wait_for_network_idle=False)
        # Browser launched exactly once across 3 fetches
        refs["chromium"].launch.assert_called_once()
        refs["browser"].new_context.assert_called_once()
        # Three pages, three goto's, three closes
        assert refs["context"].new_page.call_count == 3
        assert refs["page"].goto.call_count == 3
        assert refs["page"].close.call_count == 3

    def test_session_cleanup_on_exception_during_fetch(self):
        """Even if .fetch() raises, the browser/context still close on
        __exit__ — guards against resource leaks."""
        factory, refs = _build_playwright_mock()
        refs["page"].goto.side_effect = RuntimeError("nav fail")
        with patch("playwright.sync_api.sync_playwright", factory):
            with pytest.raises(JSFetchError):
                with JSFetchSession() as session:
                    session.fetch("https://a.test", wait_for_network_idle=False)
        refs["browser"].close.assert_called_once()
        refs["context"].close.assert_called_once()
