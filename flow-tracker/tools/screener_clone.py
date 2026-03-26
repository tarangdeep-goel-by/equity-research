#!/usr/bin/env python3
"""Screener.in Clone — fetch all data and generate standalone HTML report.

Usage:
    python screener_clone.py SYMBOL [--standalone]

Fetches every public data point from Screener.in for a given company
(HTML page, chart API, peers, schedules, shareholders) and renders
a full-page HTML report via Jinja2 template.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag
from jinja2 import Environment, FileSystemLoader

BASE_URL = "https://www.screener.in"


def _get_with_retry(client: httpx.Client, url: str, *, params: dict | None = None, retries: int = 2) -> httpx.Response:
    """GET with retry on 429 Too Many Requests."""
    for attempt in range(retries + 1):
        resp = client.get(url, params=params) if params else client.get(url)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt < retries:
            wait = 3 * (attempt + 1)
            print(f"      429 — waiting {wait}s before retry...")
            time.sleep(wait)
    resp.raise_for_status()
    return resp

# Schedule API: section -> list of expandable parent labels
SCHEDULE_PARENTS = {
    "quarters": ["Sales", "Expenses", "Other Income", "Net Profit"],
    "profit-loss": ["Sales", "Expenses", "Other Income", "Net Profit"],
    "balance-sheet": ["Borrowings", "Other Liabilities", "Fixed Assets", "Other Assets"],
    "cash-flow": [
        "Cash from Operating Activity",
        "Cash from Investing Activity",
        "Cash from Financing Activity",
    ],
}

# Chart API: key -> query string
CHART_QUERIES = {
    "price": "Price-DMA50-DMA200-Volume",
    "pe": "Price+to+Earning-Median+PE-EPS",
    "sales_margin": "GPM-OPM-NPM-Quarter+Sales",
    "ev_ebitda": "EV+Multiple-Median+EV+Multiple-EBITDA",
    "pbv": "Price+to+book+value-Median+PBV-Book+value",
    "mcap_sales": "Market+Cap+to+Sales-Median+Market+Cap+to+Sales-Sales",
}

SHAREHOLDER_CLASSIFICATIONS = [
    "promoters",
    "foreign_institutions",
    "domestic_institutions",
    "public",
]


# ---------------------------------------------------------------------------
# Credentials & session
# ---------------------------------------------------------------------------

def load_credentials() -> dict[str, str]:
    """Read Screener.in credentials from env file."""
    env_file = Path.home() / ".config" / "flowtracker" / "screener.env"
    if not env_file.exists():
        print(f"ERROR: Credential file not found at {env_file}", file=sys.stderr)
        sys.exit(1)
    creds: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            creds[k.strip()] = v.strip()
    return creds


def create_session() -> httpx.Client:
    """Login to Screener.in and return authenticated httpx client."""
    creds = load_credentials()
    client = httpx.Client(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )

    # Get CSRF token from cookie
    resp = client.get(f"{BASE_URL}/login/")
    resp.raise_for_status()
    csrf_token = client.cookies.get("csrftoken", "")
    if not csrf_token:
        # Fallback: extract from form hidden field
        m = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', resp.text)
        csrf_token = m.group(1) if m else ""

    # Login
    resp = client.post(
        f"{BASE_URL}/login/",
        data={
            "csrfmiddlewaretoken": csrf_token,
            "username": creds["SCREENER_EMAIL"],
            "password": creds["SCREENER_PASSWORD"],
        },
        headers={"Referer": f"{BASE_URL}/login/"},
    )
    resp.raise_for_status()

    if "/login/" in str(resp.url):
        print("ERROR: Login failed — check credentials in screener.env", file=sys.stderr)
        sys.exit(1)

    return client


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def parse_summary_ratios(soup: BeautifulSoup) -> list[dict]:
    """Extract top ratios from #top-ratios list."""
    ratios: list[dict] = []
    ul = soup.find(id="top-ratios")
    if not ul:
        return ratios
    for li in ul.find_all("li"):
        spans = li.find_all("span")
        if len(spans) >= 2:
            label = spans[0].get_text(strip=True)
            value = spans[1].get_text(strip=True)
            ratios.append({"label": label, "value": value})
    return ratios


def parse_company_header(soup: BeautifulSoup) -> dict:
    """Extract company name, price, change%, BSE code, NSE symbol, website."""
    info: dict = {}

    # Company name from <h1>
    h1 = soup.find("h1")
    info["company_name"] = h1.get_text(strip=True) if h1 else ""

    # Price and change from the price header area
    price_el = soup.find("span", id="number")
    if not price_el:
        # Fallback: look in the top section
        price_el = soup.select_one(".current-price .number")
    info["price"] = price_el.get_text(strip=True) if price_el else ""

    # Change percent
    change_el = soup.select_one(".current-price .change")
    if not change_el:
        change_el = soup.select_one(".percentage")
    info["change_pct"] = change_el.get_text(strip=True).strip("%+") if change_el else ""

    # BSE code, NSE symbol, website from company-links area
    info["bse_code"] = ""
    info["nse_symbol"] = ""
    info["website"] = ""
    links_section = soup.select_one(".company-links")
    if links_section:
        for a in links_section.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if "bseindia" in href:
                # Extract BSE code from text or URL
                code_match = re.search(r"(\d{6})", text) or re.search(r"(\d{6})", href)
                if code_match:
                    info["bse_code"] = code_match.group(1)
            elif "nseindia" in href:
                info["nse_symbol"] = text
            elif href.startswith("http") and "screener" not in href and "bse" not in href and "nse" not in href:
                info["website"] = href

    return info


def parse_about(soup: BeautifulSoup) -> str:
    """Extract the 'About' text from the company description."""
    about_section = soup.find("div", class_="about")
    if not about_section:
        # Try finding by heading text
        for h2 in soup.find_all("h2"):
            if "about" in h2.get_text(strip=True).lower():
                p = h2.find_next("p")
                return p.get_text(strip=True) if p else ""
    if about_section:
        p = about_section.find("p")
        return p.get_text(strip=True) if p else about_section.get_text(strip=True)
    return ""


def parse_pros_cons(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Extract Pros and Cons lists."""
    pros: list[str] = []
    cons: list[str] = []

    for div in soup.find_all("div", class_="pros-cons"):
        heading = div.find(["h2", "h3", "p", "strong"])
        heading_text = heading.get_text(strip=True).lower() if heading else ""
        items = [li.get_text(strip=True) for li in div.find_all("li")]
        if "pro" in heading_text:
            pros = items
        elif "con" in heading_text:
            cons = items

    # Fallback: search by text content
    if not pros and not cons:
        for el in soup.find_all(["h2", "h3", "strong"]):
            text = el.get_text(strip=True).lower()
            if text.startswith("pros"):
                ul = el.find_next("ul")
                if ul:
                    pros = [li.get_text(strip=True) for li in ul.find_all("li")]
            elif text.startswith("cons"):
                ul = el.find_next("ul")
                if ul:
                    cons = [li.get_text(strip=True) for li in ul.find_all("li")]

    return pros, cons


def parse_financial_table(soup: BeautifulSoup, section_id: str) -> dict | None:
    """Parse a financial table from a <section id="..."> element.

    Returns: {"headers": [...], "rows": [{"label": str, "values": [...], "expandable": bool, "sub_rows": []}]}
    """
    section = soup.find("section", id=section_id)
    if not section:
        return None

    table = section.find("table")
    if not table:
        return None

    # Headers
    headers: list[str] = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all("th"):
            headers.append(th.get_text(strip=True))

    # Rows
    rows: list[dict] = []
    tbody = table.find("tbody")
    if not tbody:
        return {"headers": headers, "rows": rows}

    for tr in tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td")
        if not tds:
            continue

        # First cell is the label — may contain a <button> for expandable rows
        label_cell = tds[0]
        button = label_cell.find("button")
        expandable = button is not None

        # Strip button and other tags to get clean label
        label = label_cell.get_text(strip=True)
        # Button text includes trailing "+" as expand indicator — strip it
        if expandable:
            label = re.sub(r"\s*\+\s*$", "", label)

        # Remaining cells are values
        values = [td.get_text(strip=True) for td in tds[1:]]

        rows.append({
            "label": label,
            "values": values,
            "expandable": expandable,
            "sub_rows": [],
        })

    return {"headers": headers, "rows": rows}


def parse_growth_rates(soup: BeautifulSoup) -> list[dict]:
    """Parse growth rate tables (Compounded Sales Growth, Profit Growth, etc.).

    These appear after the #ratios section as small standalone tables with
    grouped thead (category name) and tbody (period/value rows).
    """
    growth_rates: list[dict] = []

    # Growth rates are in a section after ratios, often within a div with specific structure
    # Look for the characteristic small tables with growth data
    ratios_section = soup.find("section", id="ratios")
    if not ratios_section:
        return growth_rates

    # The growth tables come after the main ratios table, typically in sibling elements
    # They can be in the same section or a following container
    # Look for tables with the growth rate pattern within/after the ratios section
    growth_container = ratios_section.find_next_sibling()
    search_areas = [ratios_section]
    if growth_container:
        search_areas.append(growth_container)

    # Also check parent of ratios section for growth tables
    parent = ratios_section.parent
    if parent:
        search_areas.append(parent)

    seen_labels: set[str] = set()
    for area in search_areas:
        for table in area.find_all("table"):
            # Skip the main ratios table (it has many columns)
            thead = table.find("thead")
            if not thead:
                continue
            header_text = thead.get_text(strip=True)

            # Growth rate tables have category names like "Compounded Sales Growth"
            growth_keywords = [
                "Compounded Sales Growth",
                "Compounded Profit Growth",
                "Stock Price CAGR",
                "Return on Equity",
            ]

            for keyword in growth_keywords:
                if keyword in header_text and keyword not in seen_labels:
                    seen_labels.add(keyword)
                    tbody = table.find("tbody")
                    rows_data: list[dict] = []
                    if tbody:
                        for tr in tbody.find_all("tr"):
                            tds = tr.find_all("td")
                            if len(tds) >= 2:
                                rows_data.append({
                                    "period": tds[0].get_text(strip=True),
                                    "value": tds[1].get_text(strip=True),
                                })
                    growth_rates.append({"label": keyword, "rows": rows_data})

    return growth_rates


def parse_shareholding_table(soup: BeautifulSoup) -> dict | None:
    """Parse shareholding pattern table from #shareholding section."""
    return parse_financial_table(soup, "shareholding")


def parse_documents(soup: BeautifulSoup) -> list[dict]:
    """Parse document links from #documents section."""
    docs: list[dict] = []
    section = soup.find("section", id="documents")
    if not section:
        return docs

    for li in section.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = a.get("href", "")
        if url and not url.startswith("http"):
            url = BASE_URL + url

        # Meta text (date, source) — text after the link
        meta = ""
        for sibling in a.next_siblings:
            if isinstance(sibling, str):
                meta += sibling
            elif isinstance(sibling, Tag):
                meta += sibling.get_text()
        meta = meta.strip().strip("-").strip()

        docs.append({"title": title, "url": url, "meta": meta})

    return docs


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------

def fetch_charts(client: httpx.Client, company_id: str) -> dict:
    """Fetch all 6 chart datasets."""
    charts: dict = {}
    for key, query in CHART_QUERIES.items():
        # Build URL manually — httpx params encodes + as %2B which breaks the API
        url = f"{BASE_URL}/api/company/{company_id}/chart/?q={query}&days=10000&consolidated=true"
        try:
            resp = _get_with_retry(client, url)
            charts[key] = resp.json()
        except Exception as e:
            print(f"    WARN: chart/{key} failed: {e}")
            charts[key] = {"datasets": []}
        time.sleep(1)
    return charts


def fetch_peers(client: httpx.Client, warehouse_id: str) -> str:
    """Fetch peers comparison table (returns raw HTML)."""
    url = f"{BASE_URL}/api/company/{warehouse_id}/peers/"
    try:
        resp = _get_with_retry(client, url)
        return resp.text
    except Exception as e:
        print(f"    WARN: peers failed: {e}")
        return ""


def fetch_schedules(client: httpx.Client, company_id: str) -> dict[str, dict[str, dict]]:
    """Fetch schedule (sub-item) breakdowns for all expandable rows.

    Returns: {section: {parent_label: {sub_item: {period: value, ...}}}}
    """
    schedules: dict[str, dict[str, dict]] = {}
    for section, parents in SCHEDULE_PARENTS.items():
        schedules[section] = {}
        for parent in parents:
            url = f"{BASE_URL}/api/company/{company_id}/schedules/"
            params = {"parent": parent, "section": section, "consolidated": ""}
            try:
                resp = _get_with_retry(client, url, params=params)
                data = resp.json()
                schedules[section][parent] = data if isinstance(data, dict) else {}
            except Exception as e:
                print(f"    WARN: schedule/{section}/{parent} failed: {e}")
                schedules[section][parent] = {}
            time.sleep(1)
    return schedules


def fetch_shareholders(client: httpx.Client, company_id: str) -> dict[str, list[dict]]:
    """Fetch detailed shareholder data for each classification.

    Returns: {classification: [{name, values: {quarter: pct}, url}, ...]}
    """
    shareholders: dict[str, list[dict]] = {}
    for classification in SHAREHOLDER_CLASSIFICATIONS:
        url = f"{BASE_URL}/api/3/{company_id}/investors/{classification}/quarterly/"
        try:
            resp = _get_with_retry(client, url)
            raw = resp.json()
            # raw is a dict: {shareholder_name: {quarter: pct_value, ...}, ...}
            # or may include metadata like 'data-person-url'
            holders: list[dict] = []
            if isinstance(raw, dict):
                for name, data in raw.items():
                    if isinstance(data, dict):
                        # Separate URL from values
                        person_url = data.pop("data-person-url", "")
                        holders.append({
                            "name": name,
                            "values": data,
                            "url": person_url,
                        })
                    elif isinstance(data, list):
                        # Some responses may be list-based
                        holders.append({"name": name, "values": {}, "url": ""})
            shareholders[classification] = holders
        except Exception as e:
            print(f"    WARN: shareholders/{classification} failed: {e}")
            shareholders[classification] = []
        time.sleep(1)
    return shareholders


# ---------------------------------------------------------------------------
# Merge schedules into table rows
# ---------------------------------------------------------------------------

def merge_schedules_into_tables(
    tables: dict[str, dict | None],
    schedules: dict[str, dict[str, dict]],
) -> None:
    """Merge schedule API sub-rows into the parsed financial table rows in-place.

    For each table section, match schedule parent labels to row labels
    and populate sub_rows.
    """
    # Map section_id (used in tables dict) to schedule section key
    section_map = {
        "quarters": "quarters",
        "profit_loss": "profit-loss",
        "balance_sheet": "balance-sheet",
        "cash_flow": "cash-flow",
    }

    for table_key, schedule_key in section_map.items():
        table = tables.get(table_key)
        if not table:
            continue
        section_schedules = schedules.get(schedule_key, {})
        if not section_schedules:
            continue

        # Alias map: HTML label → schedule API parent key
        _label_aliases = {"Revenue": "Sales", "Sales": "Revenue"}

        for row in table["rows"]:
            parent_label = row["label"]
            sub_data = section_schedules.get(parent_label, {})
            if not sub_data:
                sub_data = section_schedules.get(_label_aliases.get(parent_label, ""), {})
            if not sub_data:
                continue

            # sub_data: {sub_item_name: {period: value, ...}, ...}
            sub_rows: list[dict] = []
            for sub_name, period_values in sub_data.items():
                if not isinstance(period_values, dict):
                    continue
                # Build values list aligned with table headers
                headers = table.get("headers", [])
                values: list[str] = []
                for h in headers[1:]:  # skip first empty header
                    values.append(str(period_values.get(h, "")))
                sub_rows.append({"label": sub_name, "values": values})

            row["sub_rows"] = sub_rows
            if sub_rows:
                row["expandable"] = True


def merge_shareholders_into_table(
    shareholding: dict | None,
    shareholders_detail: dict[str, list[dict]],
) -> None:
    """Merge individual shareholder names into shareholding table rows as sub_rows."""
    if not shareholding:
        return

    # Map table row labels → API classification keys
    label_to_classification = {
        "Promoters": "promoters",
        "FIIs": "foreign_institutions",
        "DIIs": "domestic_institutions",
        "Public": "public",
    }

    headers = shareholding.get("headers", [])

    for row in shareholding["rows"]:
        classification = label_to_classification.get(row["label"])
        if not classification:
            continue

        holders = shareholders_detail.get(classification, [])
        if not holders:
            continue

        sub_rows: list[dict] = []
        for holder in holders:
            holder_values = holder.get("values", {})
            if not holder_values:
                continue
            # Align values to table headers
            values: list[str] = []
            for h in headers[1:]:  # skip first empty header
                val = holder_values.get(h, "")
                values.append(f"{val}%" if val else "")
            sub_rows.append({"label": holder["name"], "values": values})

        row["sub_rows"] = sub_rows
        if sub_rows:
            row["expandable"] = True


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def fetch_all(symbol: str, consolidated: bool = True) -> dict:
    """Fetch all Screener.in data for a symbol and return the full data dict."""
    print(f"Fetching {symbol}...")
    client = create_session()
    print("  Logged in")

    # 1. Fetch main company page
    suffix = "/consolidated/" if consolidated else "/"
    resp = client.get(f"{BASE_URL}/company/{symbol}{suffix}")
    if resp.status_code != 200:
        # Fallback to standalone
        resp = client.get(f"{BASE_URL}/company/{symbol}/")
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    print("  Fetched company page")

    # 2. Extract IDs from #company-info
    info_el = soup.find(id="company-info")
    if not info_el:
        print("ERROR: Could not find #company-info element", file=sys.stderr)
        sys.exit(1)

    company_id = info_el.get("data-company-id", "")
    warehouse_id = info_el.get("data-warehouse-id", "")
    print(f"  IDs: company={company_id}, warehouse={warehouse_id}")

    # 3. Parse HTML sections
    header = parse_company_header(soup)
    summary_ratios = parse_summary_ratios(soup)
    about = parse_about(soup)
    pros, cons = parse_pros_cons(soup)
    print("  Parsed header, ratios, about, pros/cons")

    # Financial tables
    tables: dict[str, dict | None] = {}
    for section_id, key in [
        ("quarters", "quarters"),
        ("profit-loss", "profit_loss"),
        ("balance-sheet", "balance_sheet"),
        ("cash-flow", "cash_flow"),
        ("ratios", "ratios"),
    ]:
        tables[key] = parse_financial_table(soup, section_id)
    print("  Parsed financial tables")

    growth_rates = parse_growth_rates(soup)
    shareholding = parse_shareholding_table(soup)
    documents = parse_documents(soup)
    print("  Parsed growth, shareholding, documents")

    # 4. Fetch API data
    print("  Fetching charts (6 calls)...")
    charts = fetch_charts(client, company_id)
    print("  Fetched charts")

    print("  Fetching peers...")
    peers_html = fetch_peers(client, warehouse_id)
    print("  Fetched peers")

    print("  Fetching schedules...")
    schedules = fetch_schedules(client, company_id)
    print("  Fetched schedules")

    print("  Fetching shareholders...")
    shareholders_detail = fetch_shareholders(client, company_id)
    print("  Fetched shareholders")

    # 5. Merge schedule sub-rows into financial tables
    merge_schedules_into_tables(tables, schedules)
    merge_shareholders_into_table(shareholding, shareholders_detail)
    print("  Merged schedule + shareholder sub-rows")

    # 6. Build output data dict
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    data = {
        "symbol": symbol,
        "company_name": header.get("company_name", symbol),
        "price": header.get("price", ""),
        "change_pct": header.get("change_pct", ""),
        "bse_code": header.get("bse_code", ""),
        "nse_symbol": header.get("nse_symbol", symbol),
        "website": header.get("website", ""),
        "summary_ratios": summary_ratios,
        "about": about,
        "pros": pros,
        "cons": cons,
        "charts": charts,
        "peers_html": peers_html,
        "tables": {k: v for k, v in tables.items() if v is not None},
        "growth_rates": growth_rates,
        "shareholding": shareholding if shareholding else {"headers": [], "rows": []},
        "shareholders_detail": shareholders_detail,
        "documents": documents,
        "generated_at": now.strftime("%Y-%m-%d %H:%M IST"),
    }

    client.close()
    return data


def render_report(data: dict) -> str:
    """Render data dict to HTML using Jinja2 template."""
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("screener_clone.html.j2")
    return template.render(**data)


def main() -> None:
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "INDIAMART"

    data = fetch_all(symbol)

    # Render template
    output_html = render_report(data)

    # Write output
    output_dir = Path(__file__).parent.parent / "reports"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{symbol}_screener_clone.html"
    output_file.write_text(output_html)
    print(f"\nDone! Open: {output_file}")


if __name__ == "__main__":
    main()
