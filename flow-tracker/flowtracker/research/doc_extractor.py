"""PDF → markdown extraction via Docling, with mtime-based caching and pdfplumber fallback.

Used by deck_extractor and annual_report_extractor. Concalls keep their own pdfplumber
path because Docling formats transcripts as wide speaker-turn tables (worse for prose).

Cache layout (per source PDF):
    {cache_dir}/_docling.md          # extracted markdown
    {cache_dir}/_heading_index.json  # raw heading list: [{level, text, char_offset}, ...]

The heading index is a *flat* list of every markdown heading. Higher-level grouping
into canonical sections (mdna, risk, auditor, ...) lives in heading_toc.py — this
module just gets the markdown out and records where the headings are.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


def _docling_heartbeat(pdf_name: str, stop: threading.Event, interval: float = 30.0) -> None:
    """Emit a progress line every `interval` seconds while docling is running.

    Docling's layout / table-structure stages are silent, which makes long AR
    extractions look frozen in eval tmux panes. This thread keeps the stream
    flowing so operators can distinguish healthy-slow from genuinely stuck.
    """
    t0 = time.time()
    while not stop.wait(interval):
        logger.info("[docling] still extracting %s — %.0fs elapsed", pdf_name, time.time() - t0)


class ExtractionResult(NamedTuple):
    markdown: str
    headings: list[dict]  # [{level: int, text: str, char_offset: int}, ...]
    backend: str          # "docling" | "pdfplumber"
    degraded: bool        # True when Docling failed and fallback ran
    elapsed_s: float
    from_cache: bool


def extract_to_markdown(pdf_path: Path | str, cache_dir: Path | str) -> ExtractionResult:
    """Convert PDF to markdown, caching the result by source mtime.

    Returns markdown + flat heading list. Heading-to-canonical-section mapping
    happens in heading_toc.py.

    On Docling failure (corrupt PDF, OOM, etc.) falls back to pdfplumber and
    sets degraded=True so callers can warn downstream consumers.
    """
    pdf_path = Path(pdf_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    md_cache = cache_dir / "_docling.md"
    idx_cache = cache_dir / "_heading_index.json"

    if md_cache.exists() and idx_cache.exists() and md_cache.stat().st_mtime >= pdf_path.stat().st_mtime:
        md = md_cache.read_text(encoding="utf-8")
        meta = json.loads(idx_cache.read_text(encoding="utf-8"))
        return ExtractionResult(
            markdown=md,
            headings=meta["headings"],
            backend=meta.get("backend", "docling"),
            degraded=meta.get("degraded", False),
            elapsed_s=0.0,
            from_cache=True,
        )

    size_mb = pdf_path.stat().st_size / 1e6
    logger.info("[docling] starting extraction of %s (%.1f MB)", pdf_path.name, size_mb)
    t0 = time.time()
    stop_hb = threading.Event()
    hb_thread = threading.Thread(
        target=_docling_heartbeat, args=(pdf_path.name, stop_hb), daemon=True
    )
    hb_thread.start()
    try:
        try:
            from docling.document_converter import DocumentConverter
            conv = DocumentConverter()
            result = conv.convert(str(pdf_path))
            md = result.document.export_to_markdown()
            backend = "docling"
            degraded = False
        except Exception as e:
            logger.warning(
                "Docling failed on %s (%s: %s) — falling back to pdfplumber",
                pdf_path.name, type(e).__name__, e,
            )
            md = _pdfplumber_fallback(pdf_path)
            backend = "pdfplumber"
            degraded = True
    finally:
        stop_hb.set()
        hb_thread.join(timeout=1.0)
    logger.info(
        "[docling] finished %s via %s in %.1fs (degraded=%s)",
        pdf_path.name, backend, time.time() - t0, degraded,
    )

    headings = _scan_headings(md)
    elapsed = time.time() - t0

    md_cache.write_text(md, encoding="utf-8")
    idx_cache.write_text(json.dumps({
        "source_pdf": str(pdf_path),
        "backend": backend,
        "degraded": degraded,
        "elapsed_s": round(elapsed, 1),
        "headings": headings,
    }), encoding="utf-8")

    return ExtractionResult(md, headings, backend, degraded, elapsed, from_cache=False)


def _pdfplumber_fallback(pdf_path: Path) -> str:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return "\n\n".join(pages)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _scan_headings(md: str) -> list[dict]:
    """Flat list of every markdown heading with byte offset.

    Page hints are not extracted — Docling's markdown doesn't preserve page numbers
    inline. If we need page hints later, we'd need to re-walk the source via Docling's
    document tree (separate concern, not needed for section-level navigation).
    """
    out = []
    for m in _HEADING_RE.finditer(md):
        out.append({
            "level": len(m.group(1)),
            "text": m.group(2).strip(),
            "char_offset": m.start(),
        })
    return out
