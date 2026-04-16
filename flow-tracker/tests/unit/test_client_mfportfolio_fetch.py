"""Tests for mfportfolio_client.py — AMC fetcher HTTP + parsing flows.

Covers fetch_amc dispatcher, fetch_all iterator, and per-AMC fetchers
(_fetch_sbi, _fetch_icici, _fetch_ppfas, _fetch_quant, _fetch_uti).
HTTP is mocked with respx; XLSX/ZIP fixtures are constructed in-memory
using openpyxl + zipfile so the parsing path runs end-to-end.
"""

from __future__ import annotations

import io
import zipfile

import httpx
import openpyxl
import pytest
import respx

from flowtracker.mfportfolio_client import MFPortfolioClient


# -- In-memory fixture builders --


def _build_xlsx(
    rows: list[list[object]] | None = None,
    sheet_name: str = "Portfolio",
    sheets: list[tuple[str, list[list[object]]]] | None = None,
) -> bytes:
    """Build an XLSX workbook in memory. Return bytes.

    Either pass a single `rows` list (one sheet named `sheet_name`),
    or pass `sheets=[(name, rows), ...]` for a multi-sheet workbook.
    """
    wb = openpyxl.Workbook()
    # Drop the default sheet
    default = wb.active
    wb.remove(default)

    if sheets is None:
        sheets = [(sheet_name, rows or [])]

    for name, sheet_rows in sheets:
        ws = wb.create_sheet(title=name[:31])  # Excel limit
        for row in sheet_rows:
            ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _standard_equity_rows(
    isin: str = "INE062A01020",
    name: str = "State Bank of India",
    qty: int = 500000,
    value_lakhs: float = 41000000.0,
    pct: float = 5.25,
) -> list[list[object]]:
    """A header row + one valid equity holding row that the parser accepts."""
    return [
        ["Equity & Equity Related Instruments", "", "", "", ""],
        ["ISIN", "Name of the Instrument", "Quantity", "Market/Fair Value (Rs. in Lakhs)", "% to NAV"],
        [isin, name, qty, value_lakhs, pct],
    ]


def _build_zip(files: dict[str, bytes]) -> bytes:
    """Build a ZIP archive in memory from {filename: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


# -- Fetcher tests --


class TestFetchAmcDispatcher:
    """Test the fetch_amc(amc, month) dispatcher routing logic."""

    def test_unknown_amc_returns_empty(self):
        """Unknown AMC string short-circuits to empty list (logs warning)."""
        client = MFPortfolioClient()
        result = client.fetch_amc("BLACKROCK", "2026-02")
        assert result == []
        client.close()

    def test_unknown_amc_case_insensitive(self):
        """Dispatcher uppercases input — verify unknown stays unknown."""
        client = MFPortfolioClient()
        result = client.fetch_amc("definitely-not-an-amc", "2026-02")
        assert result == []
        client.close()

    def test_dispatcher_swallows_fetcher_exceptions(self):
        """If the underlying fetcher raises, fetch_amc returns []."""
        client = MFPortfolioClient()
        with respx.mock:
            # No route registered → respx raises, dispatcher swallows
            respx.get(url__regex=r"sbimf\.com").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            result = client.fetch_amc("SBI", "2026-02")
        assert result == []
        client.close()


class TestFetchSbi:
    """Test _fetch_sbi — XLSX over HTTPS, multi-sheet."""

    def test_sbi_happy_path(self):
        """SBI returns multi-sheet XLSX → parse equity holdings."""
        xlsx_bytes = _build_xlsx(
            sheets=[
                ("SBI Blue Chip Fund", _standard_equity_rows()),
                ("SBI Small Cap Fund", _standard_equity_rows(
                    isin="INE009A01021", name="Infosys Ltd",
                    qty=100000, value_lakhs=1500000.0, pct=3.10,
                )),
            ],
        )
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"sbimf\.com.*\.xlsx").respond(
                200, content=xlsx_bytes,
            )
            holdings = client.fetch_amc("SBI", "2026-02")

        assert len(holdings) == 2
        isins = {h.isin for h in holdings}
        assert isins == {"INE062A01020", "INE009A01021"}
        for h in holdings:
            assert h.amc == "SBI"
            assert h.month == "2026-02"
        client.close()

    def test_sbi_http_404_returns_empty(self):
        """HTTP 404 → raise_for_status → dispatcher swallows → []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"sbimf\.com").respond(404)
            holdings = client.fetch_amc("SBI", "2026-02")
        assert holdings == []
        client.close()

    def test_sbi_http_500_returns_empty(self):
        """HTTP 500 → raise_for_status → dispatcher swallows → []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"sbimf\.com").respond(500)
            holdings = client.fetch_amc("SBI", "2026-02")
        assert holdings == []
        client.close()


class TestFetchIcici:
    """Test _fetch_icici — ZIP containing per-scheme XLSX files."""

    def test_icici_happy_path(self):
        """ICICI returns ZIP with two scheme XLSX files."""
        xlsx_a = _build_xlsx(_standard_equity_rows())
        xlsx_b = _build_xlsx(_standard_equity_rows(
            isin="INE040A01034", name="HDFC Bank Ltd",
            qty=200000, value_lakhs=3200000.0, pct=4.50,
        ))
        zip_bytes = _build_zip({
            "ICICI Prudential Bluechip Fund.xlsx": xlsx_a,
            "ICICI Prudential Smallcap Fund.xlsx": xlsx_b,
            "README.txt": b"ignored - not xlsx",
        })

        client = MFPortfolioClient()
        with respx.mock:
            # First URL pattern uses month abbreviation "Feb"
            respx.get(url__regex=r"icicipruamc\.com.*Feb.*\.zip").respond(
                200, content=zip_bytes,
            )
            holdings = client.fetch_amc("ICICI", "2026-02")

        assert len(holdings) == 2
        for h in holdings:
            assert h.amc == "ICICI"
            # _parse_single_xlsx strips "ICICI Prudential " prefix
            assert "ICICI Prudential" not in h.scheme_name
        client.close()

    def test_icici_falls_back_to_full_month_dir(self):
        """If abbreviated month dir 404s, full month dir is tried next."""
        xlsx = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({"ICICI Prudential Test.xlsx": xlsx})

        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"icicipruamc\.com.*/Feb/.*\.zip").respond(404)
            respx.get(url__regex=r"icicipruamc\.com.*/February/.*\.zip").respond(
                200, content=zip_bytes,
            )
            holdings = client.fetch_amc("ICICI", "2026-02")
        assert len(holdings) == 1
        assert holdings[0].amc == "ICICI"
        client.close()

    def test_icici_all_404_returns_empty(self):
        """Both abbreviated and full month URLs 404 → []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"icicipruamc\.com").respond(404)
            holdings = client.fetch_amc("ICICI", "2026-02")
        assert holdings == []
        client.close()

    def test_icici_zip_skips_corrupt_member(self):
        """A corrupt member XLSX is logged & skipped; valid ones still return."""
        good = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "scheme_a.xlsx": good,
            "scheme_b.xlsx": b"NOT_REALLY_XLSX_DATA",
        })
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"icicipruamc\.com.*Feb.*\.zip").respond(
                200, content=zip_bytes,
            )
            holdings = client.fetch_amc("ICICI", "2026-02")
        # Only the valid file should yield a holding
        assert len(holdings) == 1
        client.close()


class TestFetchPpfas:
    """Test _fetch_ppfas — XLS (legacy) URL, multi-sheet."""

    def test_ppfas_xls_url_forces_xlrd_path(self):
        """PPFAS URL ends in .xls — code routes to _parse_xls_file (xlrd).
        Feeding XLSX (PK-zipped) bytes makes xlrd raise, which the dispatcher
        swallows. Verifies graceful failure rather than a crash.
        """
        xlsx_bytes = _build_xlsx(_standard_equity_rows())
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"amc\.ppfas\.com.*\.xls").respond(
                200, content=xlsx_bytes,
            )
            holdings = client.fetch_amc("PPFAS", "2026-02")
        assert holdings == []
        client.close()

    def test_ppfas_url_contains_expected_pattern(self):
        """Verify the constructed URL matches the published PPFAS pattern."""
        client = MFPortfolioClient()
        captured: list[str] = []
        with respx.mock:
            route = respx.get(url__regex=r"amc\.ppfas\.com").mock(
                side_effect=lambda req: (captured.append(str(req.url)) or httpx.Response(404)),
            )
            client.fetch_amc("PPFAS", "2026-02")
            assert route.called
        assert captured, "PPFAS URL was never requested"
        url = captured[0]
        assert "PPFAS_Monthly_Portfolio_Report_February_28_2026.xls" in url
        client.close()

    def test_ppfas_404_returns_empty(self):
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"amc\.ppfas\.com").respond(404)
            assert client.fetch_amc("PPFAS", "2026-02") == []
        client.close()


class TestFetchQuant:
    """Test _fetch_quant — POST AJAX, regex-extract XLSX link, then GET."""

    def test_quant_happy_path(self):
        """AJAX returns HTML with a Feb XLSX link → fetch & parse."""
        xlsx_bytes = _build_xlsx(_standard_equity_rows())
        ajax_html = (
            '<a href="https://quantmutual.com/Admin/disclouser/'
            'Quant_MF_Feb_2026_Portfolio.xlsx">Feb 2026</a>'
            '<a href="https://quantmutual.com/Admin/disclouser/'
            'Quant_MF_Jan_2026_Portfolio.xlsx">Jan 2026</a>'
        )
        client = MFPortfolioClient()
        with respx.mock:
            respx.post(url__regex=r"quantmutual\.com.*displaydisclouser").respond(
                200, json={"d": ajax_html},
            )
            respx.get(url__regex=r"Quant_MF_Feb_2026_Portfolio\.xlsx").respond(
                200, content=xlsx_bytes,
            )
            holdings = client.fetch_amc("QUANT", "2026-02")
        assert len(holdings) == 1
        assert holdings[0].amc == "QUANT"
        client.close()

    def test_quant_relative_link_resolved(self):
        """Relative link starting with "/" gets prefixed with quantmutual.com host."""
        xlsx_bytes = _build_xlsx(_standard_equity_rows())
        ajax_html = '<a href="/Admin/disclouser/Quant_Feb_2026.xlsx">link</a>'
        client = MFPortfolioClient()
        with respx.mock:
            respx.post(url__regex=r"quantmutual\.com.*displaydisclouser").respond(
                200, json={"d": ajax_html},
            )
            respx.get("https://quantmutual.com/Admin/disclouser/Quant_Feb_2026.xlsx").respond(
                200, content=xlsx_bytes,
            )
            holdings = client.fetch_amc("QUANT", "2026-02")
        assert len(holdings) == 1
        client.close()

    def test_quant_no_links_returns_empty(self):
        """AJAX returns HTML with no XLSX links → []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.post(url__regex=r"quantmutual\.com").respond(
                200, json={"d": "<p>No portfolios published</p>"},
            )
            holdings = client.fetch_amc("QUANT", "2026-02")
        assert holdings == []
        client.close()

    def test_quant_ajax_500_returns_empty(self):
        """If AJAX errors out, fetcher catches and returns []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.post(url__regex=r"quantmutual\.com").respond(500)
            holdings = client.fetch_amc("QUANT", "2026-02")
        assert holdings == []
        client.close()

    def test_quant_falls_back_to_first_link(self):
        """If no link matches the target month, the first link is used."""
        xlsx_bytes = _build_xlsx(_standard_equity_rows())
        # Single link, doesn't mention feb/february — should still be picked
        ajax_html = '<a href="https://quantmutual.com/Admin/disclouser/random_name.xlsx">x</a>'
        client = MFPortfolioClient()
        with respx.mock:
            respx.post(url__regex=r"quantmutual\.com.*displaydisclouser").respond(
                200, json={"d": ajax_html},
            )
            respx.get("https://quantmutual.com/Admin/disclouser/random_name.xlsx").respond(
                200, content=xlsx_bytes,
            )
            holdings = client.fetch_amc("QUANT", "2026-02")
        assert len(holdings) == 1
        client.close()


class TestFetchUti:
    """Test _fetch_uti — ZIP from CloudFront, with multiple URL patterns."""

    def test_uti_happy_path_first_pattern(self):
        """First URL pattern hits → ZIP parsed for SEBI Exposure file."""
        xlsx = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "UTI_SEBI_Exposure_Statement_Feb_2026.xlsx": xlsx,
            "other_unrelated_file.xlsx": _build_xlsx([["ignored"]]),
        })
        # UTI ZIP must be > 1000 bytes — pad if necessary
        if len(zip_bytes) <= 1000:
            zip_bytes = _build_zip({
                "UTI_SEBI_Exposure_Statement_Feb_2026.xlsx": xlsx,
                "padding.bin": b"x" * 2000,
            })

        client = MFPortfolioClient()
        with respx.mock:
            respx.get(
                url__regex=r"d3ce1o48hc5oli\.cloudfront\.net/static/generic-zip.*\.zip",
            ).respond(200, content=zip_bytes)
            holdings = client.fetch_amc("UTI", "2026-02")
        assert len(holdings) == 1
        assert holdings[0].amc == "UTI"
        client.close()

    def test_uti_falls_back_to_later_pattern(self):
        """First pattern 404 → tries s3fs-public patterns until one matches."""
        xlsx = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "fw_uti_sebi_exposure_feb_2026.xlsx": xlsx,
            "padding.bin": b"x" * 2000,
        })

        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"static/generic-zip").respond(404)
            respx.get(url__regex=r"fw_uti_mf_scheme_portfolios.*_1\.zip").respond(404)
            respx.get(url__regex=r"fw_uti_mf_scheme_portfolios.*_0\.zip").respond(
                200, content=zip_bytes,
            )
            holdings = client.fetch_amc("UTI", "2026-02")
        assert len(holdings) == 1
        client.close()

    def test_uti_tiny_response_skipped(self):
        """Response ≤ 1000 bytes is rejected (defensive vs error pages)."""
        client = MFPortfolioClient()
        with respx.mock:
            # Every pattern returns 200 but with a tiny body → skipped
            respx.get(url__regex=r"d3ce1o48hc5oli\.cloudfront\.net").respond(
                200, content=b"<html>error</html>",
            )
            holdings = client.fetch_amc("UTI", "2026-02")
        assert holdings == []
        client.close()

    def test_uti_no_sebi_exposure_in_zip_returns_empty(self):
        """ZIP contains files but none match 'sebi'+'exposure' → []."""
        xlsx = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "Random_Portfolio.xlsx": xlsx,
            "padding.bin": b"x" * 2000,
        })
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"static/generic-zip").respond(
                200, content=zip_bytes,
            )
            holdings = client.fetch_amc("UTI", "2026-02")
        assert holdings == []
        client.close()


class TestFetchAll:
    """Test fetch_all — iterates all 5 AMCs and concatenates results."""

    def test_fetch_all_combines_results(self):
        """fetch_all delegates to fetch_amc for each AMC and merges output."""
        xlsx_bytes = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "ICICI Prudential Test.xlsx": xlsx_bytes,
        })
        uti_zip = _build_zip({
            "UTI_SEBI_Exposure_Feb.xlsx": xlsx_bytes,
            "padding.bin": b"x" * 2000,
        })
        ajax_html = '<a href="https://quantmutual.com/Admin/disclouser/Q_Feb_2026.xlsx">x</a>'

        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r"sbimf\.com").respond(200, content=xlsx_bytes)
            respx.get(url__regex=r"icicipruamc\.com.*Feb.*\.zip").respond(
                200, content=zip_bytes,
            )
            respx.get(url__regex=r"amc\.ppfas\.com").respond(404)
            respx.post(url__regex=r"quantmutual\.com.*displaydisclouser").respond(
                200, json={"d": ajax_html},
            )
            respx.get("https://quantmutual.com/Admin/disclouser/Q_Feb_2026.xlsx").respond(
                200, content=xlsx_bytes,
            )
            respx.get(url__regex=r"d3ce1o48hc5oli\.cloudfront\.net/static/generic-zip").respond(
                200, content=uti_zip,
            )

            all_holdings = client.fetch_all("2026-02")

        # SBI(1) + ICICI(1) + PPFAS(0) + QUANT(1) + UTI(1) = 4
        amcs = sorted({h.amc for h in all_holdings})
        assert amcs == ["ICICI", "QUANT", "SBI", "UTI"]
        assert len(all_holdings) == 4
        client.close()

    def test_fetch_all_handles_all_failures(self):
        """All AMCs fail → fetch_all returns []."""
        client = MFPortfolioClient()
        with respx.mock:
            respx.get(url__regex=r".*").respond(500)
            respx.post(url__regex=r".*").respond(500)
            all_holdings = client.fetch_all("2026-02")
        assert all_holdings == []
        client.close()


class TestParserEdgeCases:
    """Direct tests on parser branches not exercised by the AMC fetchers."""

    def test_parse_single_xlsx_empty_content(self):
        """Empty bytes → openpyxl raises → xlrd raises → returns []."""
        client = MFPortfolioClient()
        holdings = client._parse_single_xlsx(b"", "SBI", "2026-02", "scheme.xlsx")
        assert holdings == []
        client.close()

    def test_parse_single_xlsx_no_isin_header(self):
        """Workbook with no ISIN header row → no holdings extracted."""
        xlsx_bytes = _build_xlsx([
            ["Random", "Headers", "That", "Do", "Not", "Match"],
            ["A", "B", "C", "D", "E", "F"],
        ])
        client = MFPortfolioClient()
        holdings = client._parse_single_xlsx(
            xlsx_bytes, "SBI", "2026-02", "scheme.xlsx",
        )
        assert holdings == []
        client.close()

    def test_parse_single_xlsx_header_variation(self):
        """Header detection requires exact 'ISIN' cell. Other columns may vary
        ('Name of Instrument', 'Quantity (Nos)', 'Fair Value', '% to Net Assets')
        and still parse correctly.
        """
        rows = [
            ["ISIN", "Name of Instrument", "Quantity (Nos)", "Fair Value", "% to Net Assets"],
            ["INE062A01020", "SBI", "100000", "10000000", "2.5"],
        ]
        xlsx_bytes = _build_xlsx(rows)
        client = MFPortfolioClient()
        holdings = client._parse_single_xlsx(
            xlsx_bytes, "SBI", "2026-02", "scheme.xlsx",
        )
        assert len(holdings) == 1
        assert holdings[0].isin == "INE062A01020"
        assert holdings[0].quantity == 100000
        # "% to Net Assets" maps to pct via "% TO" + "NET" branch
        assert holdings[0].pct_of_nav == 2.5
        client.close()

    def test_parse_multi_sheet_xlsx_per_sheet(self):
        """Multi-sheet workbook yields holdings per sheet."""
        xlsx_bytes = _build_xlsx(
            sheets=[
                ("Scheme A", _standard_equity_rows()),
                ("Scheme B", _standard_equity_rows(
                    isin="INE040A01034", name="HDFC Bank",
                )),
                ("Empty Sheet", [["nothing here"]]),
            ],
        )
        client = MFPortfolioClient()
        holdings = client._parse_multi_sheet_xlsx(xlsx_bytes, "SBI", "2026-02")
        assert len(holdings) == 2
        scheme_names = {h.scheme_name for h in holdings}
        assert scheme_names == {"Scheme A", "Scheme B"}
        client.close()

    def test_parse_icici_zip_ignores_non_xlsx(self):
        """ZIP entries that aren't .xlsx/.xls are skipped."""
        xlsx = _build_xlsx(_standard_equity_rows())
        zip_bytes = _build_zip({
            "scheme.xlsx": xlsx,
            "readme.txt": b"hello",
            "logo.png": b"\x89PNG\r\n\x1a\n",
        })
        client = MFPortfolioClient()
        holdings = client._parse_icici_zip(zip_bytes, "2026-02")
        assert len(holdings) == 1
        assert holdings[0].amc == "ICICI"
        client.close()

    def test_context_manager(self):
        """Client supports `with ... as` and closes cleanly."""
        with MFPortfolioClient() as client:
            assert isinstance(client, MFPortfolioClient)
        # Re-entering close() is safe (httpx Client.close is idempotent)
