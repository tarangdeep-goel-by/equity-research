"""Unit tests for ar_downloader sanity gates.

Track D from plans/ar-extraction-quality-fixes.md — `_validate_ar_pdf`
rejects suspiciously short PDFs (<80 pages) that get mis-indexed as
annual reports under doc_type='annual_report'. HDFCLIFE FY25 was the
canary: BSE-tracked URL pointed to a 42-page partial-BRSR filing that
passed the prior size-only gate.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from flowtracker.research import ar_downloader
from flowtracker.research.ar_downloader import _MIN_AR_PAGES, _validate_ar_pdf


def _fake_pdfium_with_pages(n_pages: int):
    """Build a fake pypdfium2 module + PdfDocument that reports n_pages."""
    fake_doc = MagicMock()
    fake_doc.__len__.return_value = n_pages
    fake_doc.close = MagicMock()

    fake_pdfium = MagicMock()
    fake_pdfium.PdfDocument = MagicMock(return_value=fake_doc)
    return fake_pdfium


@contextmanager
def _patched_pdfium(fake_pdfium):
    with patch.dict("sys.modules", {"pypdfium2": fake_pdfium}):
        yield


def test_validate_rejects_under_size_threshold() -> None:
    """Anything <= 10KB is rejected outright (HTTP error page cached as PDF)."""
    ok, reason = _validate_ar_pdf(b"%PDF-tiny" * 100)  # ~900 bytes
    assert ok is False
    assert reason == "too_small"


def test_validate_rejects_partial_ar_under_min_pages() -> None:
    """A 42-page download is rejected — the HDFCLIFE FY25 canary case.
    Prior code accepted any size > 10KB; partial-BRSR cover letters got
    cached and broke downstream extraction across 8 sections.
    """
    big_content = b"x" * 50_000  # passes size gate
    fake = _fake_pdfium_with_pages(42)
    with _patched_pdfium(fake):
        ok, reason = _validate_ar_pdf(big_content)
    assert ok is False
    assert "too_few_pages=42" in reason


def test_validate_accepts_full_ar() -> None:
    """A 360-page download passes both gates."""
    big_content = b"x" * 50_000
    fake = _fake_pdfium_with_pages(360)
    with _patched_pdfium(fake):
        ok, reason = _validate_ar_pdf(big_content)
    assert ok is True
    assert "pages=360" in reason


def test_validate_accepts_at_minimum_threshold() -> None:
    """Exactly _MIN_AR_PAGES passes — fence-post check."""
    big_content = b"x" * 50_000
    fake = _fake_pdfium_with_pages(_MIN_AR_PAGES)
    with _patched_pdfium(fake):
        ok, reason = _validate_ar_pdf(big_content)
    assert ok is True


def test_validate_rejects_one_below_minimum() -> None:
    """One page below _MIN_AR_PAGES fails — fence-post check."""
    big_content = b"x" * 50_000
    fake = _fake_pdfium_with_pages(_MIN_AR_PAGES - 1)
    with _patched_pdfium(fake):
        ok, reason = _validate_ar_pdf(big_content)
    assert ok is False
    assert f"too_few_pages={_MIN_AR_PAGES - 1}" in reason


def test_validate_falls_back_to_size_only_on_pdfium_failure() -> None:
    """If pypdfium2 raises while parsing, accept on size — a transient
    parser bug must not permanently reject a valid AR. (Defensive: real
    AR PDFs should never trigger this in practice.)
    """
    big_content = b"x" * 50_000
    fake = MagicMock()
    fake.PdfDocument = MagicMock(side_effect=RuntimeError("parse error"))
    with _patched_pdfium(fake):
        ok, reason = _validate_ar_pdf(big_content)
    assert ok is True
    assert reason == "size_only_check"


def test_validate_falls_back_when_pypdfium2_unavailable() -> None:
    """If pypdfium2 isn't importable, fall back to size-only check.
    Same defensive contract — a missing optional dep must not block AR
    downloads."""
    big_content = b"x" * 50_000
    # Force ImportError by clearing the module from sys.modules and adding
    # a meta-path finder that refuses pypdfium2.
    import sys
    saved = sys.modules.get("pypdfium2")
    if "pypdfium2" in sys.modules:
        del sys.modules["pypdfium2"]
    try:
        with patch.dict("sys.modules", {"pypdfium2": None}):
            # `import pypdfium2` raises when sys.modules[...] is None
            ok, reason = _validate_ar_pdf(big_content)
            assert ok is True
            assert reason == "size_only_check"
    finally:
        if saved is not None:
            sys.modules["pypdfium2"] = saved
