"""Tests for surveillance_client — NSE ASM/GSM + BSE ESM parsing.

Uses ``respx`` to mock NSE preflight + JSON endpoints, with golden JSON
fixtures recorded from real upstream responses on 2026-05-26 stored at
``tests/fixtures/golden/{asm_sample.json, gsm_sample.json, esm_sample.html}``.

BSE ESM is tested two ways: (1) the SPA-shell case (real fixture, expected
to return ``[]`` because no table is present), and (2) a synthetic static
``<table>`` fixture that exercises the parser end-to-end so future BSE
upstream changes that re-introduce a table will be caught.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx

from flowtracker.js_fetch import JSFetchError
from flowtracker.surveillance_client import (
    BSESurveillanceClient,
    NSESurveillanceClient,
    SurveillanceFetchError,
    _parse_bse_esm_html,
    _parse_bse_esm_json,
    _parse_nse_asm,
    _parse_nse_date,
    _parse_nse_gsm,
    fetch_all_flags,
)
from flowtracker.surveillance_models import SurveillanceFlag


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def asm_payload(golden_dir: Path) -> dict:
    return json.loads((golden_dir / "asm_sample.json").read_text())


@pytest.fixture
def gsm_payload(golden_dir: Path) -> list:
    return json.loads((golden_dir / "gsm_sample.json").read_text())


@pytest.fixture
def esm_html(golden_dir: Path) -> str:
    return (golden_dir / "esm_sample.html").read_text()


@pytest.fixture
def esm_table_html() -> str:
    """Synthetic ESM static-table fixture (legacy BSE format).

    Covers the parser end-to-end even though the live SPA does not emit a
    table today — guards against future regressions if BSE re-introduces a
    server-rendered table or a contributor swaps to a JSON endpoint that
    returns equivalent rows.
    """
    return """
    <html><body>
      <h2>ESM List</h2>
      <table id="esm">
        <tr><th>Symbol</th><th>Stage</th><th>Effective Date</th><th>Reason</th></tr>
        <tr><td>ACMECORP</td><td>Stage I</td><td>26-May-2026</td><td>Low volume</td></tr>
        <tr><td>WIDGETSLTD</td><td>Stage II</td><td>26-May-2026</td><td>Price band</td></tr>
      </table>
    </body></html>
    """


# ---------------------------------------------------------------------------
# Date parser
# ---------------------------------------------------------------------------


class TestParseNseDate:
    def test_iso_passthrough(self):
        assert _parse_nse_date("2026-05-26") == "2026-05-26"

    def test_dd_mon_yyyy(self):
        assert _parse_nse_date("26-May-2026") == "2026-05-26"

    def test_dd_mon_yyyy_with_time(self):
        # GSM timestamps include HH:MM:SS — strip it.
        assert _parse_nse_date("26-May-2026 08:07:02") == "2026-05-26"

    def test_dd_slash_mm_slash_yyyy(self):
        assert _parse_nse_date("26/05/2026") == "2026-05-26"

    def test_garbage_falls_back_to_today(self):
        # Parser is forgiving — better to keep a row than drop it on a date wobble.
        import datetime as _dt
        out = _parse_nse_date("not-a-date")
        assert out == _dt.date.today().isoformat()

    def test_none_falls_back_to_today(self):
        import datetime as _dt
        assert _parse_nse_date(None) == _dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# NSE ASM parser
# ---------------------------------------------------------------------------


class TestParseNseAsm:
    def test_parses_golden_fixture(self, asm_payload: dict):
        flags = _parse_nse_asm(asm_payload)
        # Golden fixture had ~180 combined rows; assert it returns a useful chunk.
        assert len(flags) > 10
        assert all(isinstance(f, SurveillanceFlag) for f in flags)
        assert {f.alert_type for f in flags} == {"ASM"}
        assert {f.exchange for f in flags} == {"NSE"}

    def test_first_row_shape(self, asm_payload: dict):
        flags = _parse_nse_asm(asm_payload)
        f = flags[0]
        assert f.symbol == f.symbol.upper()
        assert f.alert_type == "ASM"
        assert f.exchange == "NSE"
        # YYYY-MM-DD
        assert len(f.effective_date) == 10 and f.effective_date[4] == "-"
        # Stage looks like "Stage I" / "Stage II"
        assert f.stage is None or "Stage" in f.stage

    def test_handles_both_buckets(self, asm_payload: dict):
        flags = _parse_nse_asm(asm_payload)
        # Stitch reason text — long-term and short-term both surface.
        reasons = " ".join((f.reason or "") for f in flags)
        assert "Long Term" in reasons
        assert "Short Term" in reasons

    def test_skips_missing_symbol(self):
        payload = {
            "longterm": {"data": [
                {"symbol": "", "asmSurvIndicator": "Stage I"},
                {"symbol": "VALID", "asmSurvIndicator": "Stage I",
                 "survDesc": "Long Term ASM Stage I", "asmTime": "26-May-2026"},
            ]},
            "shortterm": {"data": []},
        }
        flags = _parse_nse_asm(payload)
        assert len(flags) == 1
        assert flags[0].symbol == "VALID"

    def test_empty_payload(self):
        assert _parse_nse_asm({}) == []
        assert _parse_nse_asm([]) == []

    def test_uppercases_symbol(self):
        payload = {"longterm": {"data": [{
            "symbol": "  lowercase  ", "asmSurvIndicator": "Stage I",
            "survDesc": "Long Term ASM Stage I", "asmTime": "26-May-2026",
        }]}, "shortterm": {"data": []}}
        flags = _parse_nse_asm(payload)
        assert flags[0].symbol == "LOWERCASE"


# ---------------------------------------------------------------------------
# NSE GSM parser
# ---------------------------------------------------------------------------


class TestParseNseGsm:
    def test_parses_golden_fixture(self, gsm_payload: list):
        flags = _parse_nse_gsm(gsm_payload)
        assert len(flags) > 5
        assert all(f.alert_type == "GSM" for f in flags)
        assert all(f.exchange == "NSE" for f in flags)
        # Stage format like "LXII" (Roman numerals) or numeric.
        assert any(f.stage for f in flags)

    def test_accepts_wrapped_dict_shape(self):
        """NSE sometimes wraps the list under ``data`` — be tolerant."""
        payload = {"data": [{
            "symbol": "ANKITMETAL", "gsmStage": "LXII",
            "gsmTime": "26-May-2026 08:07:02",
            "survDesc": "IBC - Receipt & GSM 0",
        }]}
        flags = _parse_nse_gsm(payload)
        assert len(flags) == 1
        assert flags[0].symbol == "ANKITMETAL"
        assert flags[0].stage == "LXII"

    def test_empty_payload(self):
        assert _parse_nse_gsm([]) == []
        assert _parse_nse_gsm({}) == []


# ---------------------------------------------------------------------------
# BSE ESM parsers
# ---------------------------------------------------------------------------


class TestParseBseEsmHtml:
    def test_spa_shell_returns_empty(self, esm_html: str):
        """The real BSE ESM page today is an Angular SPA with no table —
        parser must return ``[]`` gracefully, not raise."""
        assert _parse_bse_esm_html(esm_html) == []

    def test_static_table_round_trip(self, esm_table_html: str):
        flags = _parse_bse_esm_html(esm_table_html)
        assert len(flags) == 2
        syms = {f.symbol for f in flags}
        assert syms == {"ACMECORP", "WIDGETSLTD"}
        assert all(f.exchange == "BSE" for f in flags)
        assert all(f.alert_type == "ESM" for f in flags)
        assert {f.stage for f in flags} == {"Stage I", "Stage II"}
        assert all(f.effective_date == "2026-05-26" for f in flags)
        # Reason captured
        assert any("Low volume" in (f.reason or "") for f in flags)

    def test_table_without_symbol_header_ignored(self):
        # Page can contain unrelated tables (header / footer nav) — only
        # tables with a "symbol" or "scrip" header should be treated as ESM.
        html = """
        <table>
          <tr><th>Name</th><th>Value</th></tr>
          <tr><td>foo</td><td>1</td></tr>
        </table>
        """
        assert _parse_bse_esm_html(html) == []

    def test_inline_json_payload(self):
        """Legacy BSE pages occasionally inline a ``window.__ESM_DATA__`` JSON
        array. Parser handles it without needing a table."""
        html = """<html><script>
        window.__ESM_DATA__ = [
          {"Symbol":"INLINEJSON","Stage":"Stage I","EffectiveDate":"26-May-2026",
           "Reason":"Inline test"}
        ];</script></html>"""
        flags = _parse_bse_esm_html(html)
        assert len(flags) == 1
        assert flags[0].symbol == "INLINEJSON"
        assert flags[0].stage == "Stage I"


class TestParseBseEsmJson:
    def test_list_payload(self):
        rows = [{
            "Symbol": "TESTSYM", "Stage": "Stage I",
            "EffectiveDate": "26-May-2026", "Reason": "test",
        }]
        flags = _parse_bse_esm_json(rows)
        assert len(flags) == 1
        assert flags[0].symbol == "TESTSYM"
        assert flags[0].exchange == "BSE"
        assert flags[0].alert_type == "ESM"

    def test_wrapped_Table_key(self):
        # BSE convention: results wrapped in {"Table": [...]}
        payload = {"Table": [{"Symbol": "WRAPPED", "Stage": "Stage II"}]}
        flags = _parse_bse_esm_json(payload)
        assert len(flags) == 1
        assert flags[0].symbol == "WRAPPED"

    def test_alternate_field_names(self):
        # BSE has inconsistent column casing; tolerate variants.
        rows = [{
            "scripcd": "ALTFIELDS", "ESMStage": "Stage I",
            "EffectiveFrom": "2026-05-26",
        }]
        flags = _parse_bse_esm_json(rows)
        assert len(flags) == 1
        assert flags[0].symbol == "ALTFIELDS"
        assert flags[0].stage == "Stage I"

    def test_empty(self):
        assert _parse_bse_esm_json([]) == []
        assert _parse_bse_esm_json({}) == []


# ---------------------------------------------------------------------------
# Client-level fetch (respx-mocked)
# ---------------------------------------------------------------------------


class TestNSESurveillanceClient:
    def test_fetch_asm_with_mock(self, asm_payload: dict):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/asm").respond(
                200, text="OK",
            )
            respx.get(url__regex=r"nseindia\.com/api/reportASM").respond(
                200, json=asm_payload,
            )
            with NSESurveillanceClient() as client:
                flags = client.fetch_asm()
        assert len(flags) > 10
        assert all(f.alert_type == "ASM" for f in flags)

    def test_fetch_gsm_with_mock(self, gsm_payload: list):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/gsm").respond(
                200, text="OK",
            )
            respx.get(url__regex=r"nseindia\.com/api/reportGSM").respond(
                200, json=gsm_payload,
            )
            with NSESurveillanceClient() as client:
                flags = client.fetch_gsm()
        assert len(flags) >= 5
        assert all(f.alert_type == "GSM" for f in flags)

    def test_retries_on_403(self, asm_payload: dict):
        """A 403 on the first JSON call should trigger cookie refresh + retry."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/asm").respond(
                200, text="OK",
            )
            route = respx.get(url__regex=r"nseindia\.com/api/reportASM")
            # First two calls 403, third succeeds.
            route.side_effect = [
                __import__("httpx").Response(403, text="forbidden"),
                __import__("httpx").Response(200, json=asm_payload),
            ]
            with NSESurveillanceClient() as client:
                flags = client.fetch_asm()
        assert len(flags) > 10

    def test_permanent_failure_raises(self):
        """All retries exhausted — should raise ``SurveillanceFetchError``."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/asm").respond(
                200, text="OK",
            )
            respx.get(url__regex=r"nseindia\.com/api/reportASM").mock(
                side_effect=lambda req: __import__("httpx").Response(500, text="boom")
            )
            with NSESurveillanceClient() as client:
                with pytest.raises(SurveillanceFetchError):
                    client.fetch_asm()


class TestBSESurveillanceClient:
    def test_fetch_esm_spa_shell_returns_empty(self, esm_html: str):
        # JS-render fallback patched out — simulate Playwright unavailable.
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html").respond(
                200, text=esm_html,
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                side_effect=JSFetchError("test: no browser"),
            ):
                with BSESurveillanceClient() as client:
                    flags = client.fetch_esm()
        assert flags == []

    def test_fetch_esm_static_table(self, esm_table_html: str):
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html").respond(
                200, text=esm_table_html,
            )
            with BSESurveillanceClient() as client:
                flags = client.fetch_esm()
        assert len(flags) == 2
        assert all(f.exchange == "BSE" for f in flags)

    def test_json_endpoint_preferred_when_configured(self):
        rows = [{"Symbol": "JSONPATH", "Stage": "Stage I",
                 "EffectiveDate": "26-May-2026"}]
        with respx.mock:
            respx.get(url__regex=r"api\.example\.com/esm").respond(
                200, json=rows,
                headers={"content-type": "application/json"},
            )
            with BSESurveillanceClient(
                json_endpoint="https://api.example.com/esm",
            ) as client:
                flags = client.fetch_esm()
        assert len(flags) == 1
        assert flags[0].symbol == "JSONPATH"

    def test_js_fallback_invoked_when_httpx_returns_spa_shell(
        self, esm_html: str, esm_table_html: str,
    ):
        """When httpx returns an SPA shell (no parseable rows), the JS-rendered
        fallback runs and its result is returned."""
        with respx.mock:
            respx.get(
                url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html"
            ).respond(200, text=esm_html)
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                return_value=esm_table_html,
            ) as mock_fetch:
                with BSESurveillanceClient() as client:
                    flags = client.fetch_esm()
        # The JS fetch was called once with the BSE ESM URL
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.args[0] == (
            "https://www.bseindia.com/markets/equity/EQReports/ESM.html"
        )
        # Stealth mode must be enabled for BSE — Akamai bypass requires
        # playwright-stealth + Chrome channel
        assert mock_fetch.call_args.kwargs.get("use_stealth") is True
        # And the synthetic table fixture's two rows came through
        assert len(flags) == 2
        assert {f.symbol for f in flags} == {"ACMECORP", "WIDGETSLTD"}

    def test_js_fallback_access_denied_returns_empty(self, esm_html: str):
        """JS-render returns Akamai's 'Access Denied' shell → still empty,
        no exception. The graceful pre-existing behaviour is preserved."""
        access_denied = (
            "<html><head><title>Access Denied</title></head>"
            "<body><h1>Access Denied</h1></body></html>"
        )
        with respx.mock:
            respx.get(
                url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html"
            ).respond(200, text=esm_html)
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                return_value=access_denied,
            ):
                with BSESurveillanceClient() as client:
                    flags = client.fetch_esm()
        assert flags == []

    def test_js_fallback_unavailable_returns_empty(self, esm_html: str):
        """When js_fetch raises JSFetchError (no browser / nav timeout),
        the SPA-shell httpx path's [] result is returned."""
        with respx.mock:
            respx.get(
                url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html"
            ).respond(200, text=esm_html)
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                side_effect=JSFetchError("browser missing"),
            ):
                with BSESurveillanceClient() as client:
                    flags = client.fetch_esm()
        assert flags == []

    def test_static_table_path_skips_js_fallback(self, esm_table_html: str):
        """If httpx returns a real table, the JS fallback must NOT be
        invoked — we already have the data."""
        with respx.mock:
            respx.get(
                url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html"
            ).respond(200, text=esm_table_html)
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
            ) as mock_fetch:
                with BSESurveillanceClient() as client:
                    flags = client.fetch_esm()
        mock_fetch.assert_not_called()
        assert len(flags) == 2


# ---------------------------------------------------------------------------
# Top-level helper
# ---------------------------------------------------------------------------


class TestFetchAllFlags:
    def test_aggregates_three_sources(self, asm_payload, gsm_payload, esm_table_html):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/asm").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/reportASM").respond(200, json=asm_payload)
            respx.get(url__regex=r"nseindia\.com/reports/gsm").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/reportGSM").respond(200, json=gsm_payload)
            respx.get(url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html").respond(
                200, text=esm_table_html,
            )
            flags = fetch_all_flags()
        types = {f.alert_type for f in flags}
        assert types == {"ASM", "GSM", "ESM"}
        # ASM + GSM rows >> ESM (2 in the synthetic fixture)
        esm = [f for f in flags if f.alert_type == "ESM"]
        assert len(esm) == 2

    def test_partial_outage_does_not_block_others(self, asm_payload, esm_table_html):
        """If one exchange errors, the others still return."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports/asm").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/reportASM").respond(200, json=asm_payload)
            # GSM permanently 500s
            respx.get(url__regex=r"nseindia\.com/reports/gsm").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/reportGSM").respond(500, text="boom")
            respx.get(url__regex=r"bseindia\.com/markets/equity/EQReports/ESM\.html").respond(
                200, text=esm_table_html,
            )
            flags = fetch_all_flags()
        # ASM + ESM survive, GSM contributes nothing
        types = {f.alert_type for f in flags}
        assert "ASM" in types
        assert "ESM" in types
        assert "GSM" not in types
