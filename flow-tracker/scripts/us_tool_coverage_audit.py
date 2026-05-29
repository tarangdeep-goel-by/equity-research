"""Empirical US tool-coverage audit (Phase 3.5b).

Seeds a US ticker (AAPL) + India regression data (SBIN/INFY) into a throwaway
temp DB, then calls EVERY unique MCP research tool against the US symbol and
classifies each result into one of four buckets:

  ROUTED        — tool ran and returned real (non-empty) US data
  DEGRADED      — tool returned an explicit not_applicable / n/a envelope
  EMPTY_SILENT  — tool returned an empty India-shaped payload with no marker
  ERROR         — tool raised, or returned an {"error": ...} / completeness=error

Section-routed dispatchers (get_fundamentals, get_quality_scores, ...) are
exercised across their full section enum, since the compute-layer gaps
(piotroski, dupont, fair_value, wacc) live in specific sections.

WS-7 exit criterion: for the US symbol, ZERO EMPTY_SILENT and ZERO ERROR.

Offline, no network, no LLM. Prod DB untouched.

Usage:
    uv run python scripts/us_tool_coverage_audit.py            # human table
    uv run python scripts/us_tool_coverage_audit.py --json     # machine JSON
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

US_SYMBOL = "AAPL"
US_MARKET = "NASDAQ"


# --------------------------------------------------------------------------- #
# Seeding (mirrors tests/integration/test_us_consumption.py::_seed_us)
# --------------------------------------------------------------------------- #
def _seed_us(store) -> None:
    store.upsert_symbol_registry(
        US_SYMBOL, US_MARKET, company_name="Apple Inc.",
        sector="Technology", gics="Technology", cik="320193",
    )
    store.upsert_us_annual_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "fiscal_year": 2024, "revenue": 391_035.0, "net_income": 93_736.0,
         "eps": 6.08, "shares_outstanding": 15_000_000_000},
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "fiscal_year": 2023, "revenue": 383_285.0, "net_income": 96_995.0,
         "eps": 6.13, "shares_outstanding": 15_550_000_000},
    ])
    store.upsert_us_quarterly_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "quarter_end": "2024-12-28", "fiscal_year": 2025, "fiscal_period": "Q1",
         "revenue": 124_300.0, "net_income": 36_330.0, "eps": 2.40},
    ])
    store.upsert_us_valuation_snapshot([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "date": "2025-05-29", "price": 207.5, "market_cap": 3_100_000.0,
         "pe_trailing": 32.0, "roe": 150.0},
    ])
    store.upsert_us_consensus_estimates([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "date": "2025-05-29", "target_mean": 230.0, "target_high": 300.0,
         "target_low": 170.0, "num_analysts": 40, "eps_next_year": 7.50},
    ])
    store.upsert_us_insider_transactions([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "filing_date": "2025-05-20", "transaction_date": "2025-05-18",
         "owner_name": "COOK TIMOTHY D", "owner_title": "CEO",
         "transaction_code": "S", "shares": 100_000.0, "price_per_share": 205.0,
         "value": 20_500_000.0, "shares_owned_after": 3_000_000.0,
         "is_director": 1, "is_officer": 1},
    ])
    store.upsert_us_institutional_holdings([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "cusip": "037833100", "manager_name": "VANGUARD GROUP INC",
         "manager_cik": "102909", "quarter_end": "2025-03-31",
         "shares": 1_300_000_000.0, "value_usd": 270_000.0},
    ])
    # A handful of daily prices so technicals/price-perf have something to read.
    rows = []
    base = 180.0
    for i in range(60):
        d = f"2025-{3 + i // 30:02d}-{1 + i % 28:02d}"
        px = base + i * 0.4
        rows.append({"symbol": US_SYMBOL, "market": US_MARKET, "date": d,
                     "open": px, "high": px + 1, "low": px - 1, "close": px,
                     "volume": 50_000_000})
    try:
        store.upsert_us_daily_prices(rows)
    except Exception:
        pass  # table/method optional at this phase


# --------------------------------------------------------------------------- #
# Tool enumeration + arg synthesis
# --------------------------------------------------------------------------- #
def _unique_tools(T) -> list:
    seen: set[int] = set()
    out = []
    for reg in T._ALL_TOOL_REGISTRIES:
        for to in reg:
            if id(to) not in seen:
                seen.add(id(to))
                out.append(to)
    return out


def _enum_values(prop_schema: dict) -> list | None:
    if not isinstance(prop_schema, dict):
        return None
    if "enum" in prop_schema and isinstance(prop_schema["enum"], list):
        return list(prop_schema["enum"])
    return None


def _normalize_schema(schema: dict) -> tuple[dict, set, bool]:
    """Return (props, required, is_shorthand) for either schema form.

    Full JSON-schema:  {"type":"object","properties":{...},"required":[...]}
    Dict-shorthand:    {"field": str, "filters": dict, ...}  (claude_agent_sdk)

    For shorthand, each value is a Python type; we treat object-typed fields
    (e.g. ``filters``) as required, and ``symbol`` as required when present.
    """
    if "properties" in schema:
        return schema.get("properties") or {}, set(schema.get("required") or []), False
    # Shorthand: synthesize props + a best-effort required set.
    props = {k: {"_pytype": v} for k, v in schema.items()}
    required = set()
    for k, v in schema.items():
        if k == "symbol" or v in (dict, list):
            required.add(k)
    return props, required, True


def _build_arg_variants(tool, section_enum_map: dict) -> list[dict]:
    """Synthesize the arg dicts to call a tool with.

    Returns one args dict per section value for section-routed dispatchers,
    else a single best-effort args dict. Always passes symbol=AAPL when the
    tool accepts a symbol.
    """
    schema = tool.input_schema or {}
    props, required, shorthand = _normalize_schema(schema)

    base: dict = {}
    if "symbol" in props:
        base["symbol"] = US_SYMBOL

    # Fill OTHER required fields (besides symbol/section) with a safe default.
    for name in required:
        if name in ("symbol", "section", "sub_section") or name in base:
            continue
        enum = _enum_values(props.get(name, {}))
        if enum:
            base[name] = enum[0]
            continue
        pytype = (props.get(name) or {}).get("_pytype")
        ptype = (props.get(name) or {}).get("type")
        if pytype in (dict,) or ptype == "object":
            base[name] = {}
        elif pytype in (list,) or ptype == "array":
            base[name] = []
        elif pytype in (int, float) or ptype in ("integer", "number"):
            base[name] = 1
        else:
            base[name] = "AAPL" if "symbol" in name else ""

    # Section iteration: only full-schema dispatchers carry a section enum.
    sec_enum = section_enum_map.get(tool.name)
    if sec_enum is None and not shorthand:
        sec_enum = _enum_values(props.get("section", {}))

    if sec_enum:
        return [{**base, "section": s} for s in sec_enum]
    return [base]


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def _is_not_applicable(payload) -> bool:
    if isinstance(payload, dict):
        if str(payload.get("status", "")).lower() == "not_applicable":
            return True
        meta = payload.get("_meta")
        if isinstance(meta, dict) and str(meta.get("status", "")).lower() == "not_applicable":
            return True
        # section-level markers (get_ownership 'all' nests per-section envelopes)
        reason = str(payload.get("reason", "")).lower()
        if "not applicable" in reason or "no us equivalent" in reason:
            return True
    return False


def _classify(payload, classify_completeness) -> str:
    if _is_not_applicable(payload):
        return "DEGRADED"
    if isinstance(payload, dict) and payload.get("error"):
        return "ERROR"
    comp, _ = classify_completeness(payload)
    if comp == "error":
        return "ERROR"
    if comp == "empty":
        return "EMPTY_SILENT"
    return "ROUTED"


async def _run_one(tool, args, classify_completeness) -> dict:
    label = tool.name + (f"[{args['section']}]" if "section" in args else "")
    try:
        result = await tool.handler(args)
        text = result.get("content", [{}])[0].get("text", "")
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            payload = text  # bare string payload
        bucket = _classify(payload, classify_completeness)
        detail = ""
        if bucket in ("ERROR", "EMPTY_SILENT"):
            if isinstance(payload, dict) and payload.get("error"):
                detail = str(payload.get("error"))[:120]
            else:
                detail = json.dumps(payload, default=str)[:120]
        return {"tool": tool.name, "label": label, "bucket": bucket, "detail": detail}
    except Exception as e:  # noqa: BLE001 — the audit must survive crashes
        return {"tool": tool.name, "label": label, "bucket": "ERROR",
                "detail": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=3)}


async def _audit(tools, classify_completeness, section_enum_map) -> list[dict]:
    results = []
    for tool in tools:
        for args in _build_arg_variants(tool, section_enum_map):
            results.append(await _run_one(tool, args, classify_completeness))
    return results


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    import os

    tmpdir = tempfile.mkdtemp(prefix="us_audit_")
    db_path = Path(tmpdir) / "audit.db"
    os.environ["FLOWTRACKER_DB"] = str(db_path)

    from flowtracker.store import FlowStore
    from tests.fixtures.factories import populate_all

    with FlowStore(db_path=db_path) as store:
        populate_all(store)
        _seed_us(store)

    from flowtracker.research import tools as T
    from flowtracker.research.tool_audit import _section_enum_map
    from flowtracker.research.data_api import _run_market

    tools = _unique_tools(T)
    section_enum_map = _section_enum_map()
    # Simulate a US research run so ContextVar-gated tools (macro / FII-derivative
    # flow, which have no symbol arg) resolve their market the way they do in a
    # real US run. Symbol-based guards still resolve AAPL via the registry.
    token = _run_market.set(US_MARKET)
    try:
        results = asyncio.run(_audit(tools, T.classify_completeness, section_enum_map))
    finally:
        _run_market.reset(token)

    counts: dict[str, int] = {"ROUTED": 0, "DEGRADED": 0, "EMPTY_SILENT": 0, "ERROR": 0}
    for r in results:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1

    if "--json" in sys.argv:
        print(json.dumps({"counts": counts, "results": results,
                          "tool_count": len(tools)}, indent=2, default=str))
        return 0

    print(f"\nUS TOOL-COVERAGE AUDIT — symbol={US_SYMBOL} ({US_MARKET})")
    print(f"unique tools: {len(tools)}   probes: {len(results)}")
    print(f"counts: {counts}\n")

    for bucket in ("ERROR", "EMPTY_SILENT", "DEGRADED", "ROUTED"):
        rows = [r for r in results if r["bucket"] == bucket]
        if not rows:
            continue
        print(f"=== {bucket} ({len(rows)}) ===")
        for r in rows:
            detail = f"  — {r['detail']}" if r.get("detail") else ""
            print(f"  {r['label']}{detail}")
        print()

    gaps = counts["EMPTY_SILENT"] + counts["ERROR"]
    print(f"GAP TOTAL (EMPTY_SILENT + ERROR): {gaps}")
    print("WS-7 PASS" if gaps == 0 else "WS-7 NOT YET (gaps remain)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
