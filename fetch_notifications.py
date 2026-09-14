#!/usr/bin/env python3
"""
Daily fetcher for GST (CBIC) and Income Tax (CBDT) notifications/circulars.

Scrapes the official listing pages, diffs against the last saved run, and writes:
  - notifications.json   (full current dataset, machine-readable)
  - new_today.json        (only items new since the last run — useful for alerting)
  - docs/index.html        (static digest page, e.g. for GitHub Pages)

IMPORTANT — read this before relying on it:
  * These are HTML scrapers, not an official API (neither CBIC nor the Income Tax
    Department publish one). Government sites redesign their pages periodically —
    when that happens the CSS selectors below will stop matching and you'll get
    an empty result instead of an error. Check the output after any government
    site redesign and update SOURCES below.
  * Respect the sites' terms of use / robots.txt. This script fetches public
    listing pages at a low frequency (once daily) and does not bypass any
    authentication or rate limiting.
  * This is a best-effort community-style scraper, not a substitute for checking
    the primary source before making a filing or compliance decision.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "notifications.json"
NEW_FILE = BASE_DIR / "new_today.json"
DOCS_DIR = BASE_DIR / "docs"
DOCS_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaxNotificationDigest/1.0; +personal-use-script)"
}
TIMEOUT = 30

# ---------------------------------------------------------------------------
# SOURCES — each entry describes one listing page to scrape.
# `parser` decides how rows are extracted; see parse_table_rows() below.
# Update `url` and `row_selector`/`col_map` here if a site's markup changes.
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "id": "gst_central_tax_notifications",
        "category": "GST",
        "label": "CBIC — Central Tax Notifications",
        "url": "https://cbic-gst.gov.in/central-tax-notifications.html",
        "row_selector": "table tr",
    },
    {
        "id": "gst_circulars",
        "category": "GST",
        "label": "CBIC — GST Circulars",
        "url": "https://cbic-gst.gov.in/circulars.html",
        "row_selector": "table tr",
    },
    {
        "id": "income_tax_notifications",
        "category": "Income Tax",
        "label": "CBDT — Income Tax Notifications",
        "url": "https://incometaxindia.gov.in/pages/communications/notifications.aspx",
        "row_selector": "table tr",
    },
    {
        "id": "income_tax_circulars",
        "category": "Income Tax",
        "label": "CBDT — Income Tax Circulars",
        "url": "https://incometaxindia.gov.in/pages/communications/circulars.aspx",
        "row_selector": "table tr",
    },
]


def fetch_page(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"  [warn] could not fetch {url}: {exc}", file=sys.stderr)
        return None


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_table_rows(html: str, row_selector: str) -> list[dict]:
    """
    Generic parser: walks table rows, keeps rows that have at least 2 non-empty
    cells, and returns each row as a list of cell texts plus any link hrefs found.
    This is deliberately generic because both target sites use plain HTML tables
    with an inconsistent number of columns across pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows_out = []
    for row in soup.select(row_selector):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        texts = [clean_text(c.get_text()) for c in cells]
        if not any(texts):
            continue
        links = [a.get("href") for a in row.find_all("a", href=True)]
        rows_out.append({"cells": texts, "links": links})
    return rows_out


def guess_item_from_row(row: dict, base_url: str) -> dict | None:
    """
    Heuristic extraction: the first cell that looks like a date, the first
    long-ish text cell as the subject, and the first link as the reference URL.
    Government listing tables aren't uniformly structured, so this is a
    best-effort guess rather than a strict column mapping.
    """
    cells = row["cells"]
    date_match = None
    subject = None
    for c in cells:
        if not date_match and re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}", c):
            date_match = c
        elif not subject and len(c) > 15:
            subject = c
    if not subject:
        return None
    ref_url = row["links"][0] if row["links"] else None
    if ref_url and ref_url.startswith("/"):
        from urllib.parse import urljoin
        ref_url = urljoin(base_url, ref_url)
    return {
        "date": date_match or "",
        "subject": subject,
        "url": ref_url,
    }


def scrape_source(source: dict) -> list[dict]:
    print(f"Fetching {source['label']} ...")
    html = fetch_page(source["url"])
    if not html:
        return []
    rows = parse_table_rows(html, source["row_selector"])
    items = []
    for row in rows:
        item = guess_item_from_row(row, source["url"])
        if item:
            item["source_id"] = source["id"]
            item["category"] = source["category"]
            item["source_label"] = source["label"]
            items.append(item)
    print(f"  -> {len(items)} row(s) parsed")
    return items


def load_previous() -> list[dict]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def item_key(item: dict) -> str:
    return f"{item['source_id']}::{item['subject'][:120]}"


def render_html(all_items: list[dict], new_items: list[dict]) -> str:
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    by_category: dict[str, list[dict]] = {}
    for it in all_items:
        by_category.setdefault(it["category"], []).append(it)

    def card(it: dict, is_new: bool) -> str:
        badge = '<span class="new-badge">NEW</span>' if is_new else ""
        link = f'<a href="{it["url"]}" target="_blank">source</a>' if it.get("url") else ""
        return f"""
        <div class="card">
          <div class="meta">{it.get('date','')} · {it['source_label']} {badge}</div>
          <div class="subject">{it['subject']}</div>
          <div class="link">{link}</div>
        </div>"""

    sections = []
    for cat, items in by_category.items():
        new_keys = {item_key(i) for i in new_items}
        cards = "".join(card(it, item_key(it) in new_keys) for it in items[:60])
        sections.append(f'<h2>{cat}</h2><div class="card-list">{cards}</div>')

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>GST & Income Tax Notification Digest</title>
<style>
body{{font-family:Georgia,serif;background:#F6F2E9;color:#262220;margin:0;}}
.wrap{{max-width:900px;margin:0 auto;padding:36px 24px;}}
h1{{font-weight:400;}}
.generated{{font-family:'Segoe UI',sans-serif;color:#5B554C;font-size:13px;margin-bottom:24px;}}
h2{{font-family:'Segoe UI',sans-serif;font-size:14px;background:#1F4B43;color:#fff;display:inline-block;
   padding:5px 12px;border-radius:3px;}}
.card-list{{display:flex;flex-direction:column;gap:10px;margin:14px 0 30px;}}
.card{{background:#FFFEFB;border:1px solid #DAD2C0;border-radius:3px;padding:12px 16px;font-family:'Segoe UI',sans-serif;font-size:13.5px;}}
.meta{{color:#5B554C;font-size:12px;margin-bottom:4px;}}
.new-badge{{background:#95601C;color:#fff;font-size:10.5px;padding:1px 6px;border-radius:8px;margin-left:6px;}}
.link a{{color:#1F4B43;}}
</style></head>
<body><div class="wrap">
<h1>GST &amp; Income Tax — Notification Digest</h1>
<div class="generated">Auto-generated {generated} · {len(new_items)} new item(s) since last run</div>
{"".join(sections)}
</div></body></html>"""


def main():
    all_items = []
    for source in SOURCES:
        all_items.extend(scrape_source(source))

    previous = load_previous()
    previous_keys = {item_key(i) for i in previous}
    new_items = [it for it in all_items if item_key(it) not in previous_keys]

    DATA_FILE.write_text(json.dumps(all_items, indent=2, ensure_ascii=False))
    NEW_FILE.write_text(json.dumps(new_items, indent=2, ensure_ascii=False))
    (DOCS_DIR / "index.html").write_text(render_html(all_items, new_items), encoding="utf-8")

    print(f"\nTotal items: {len(all_items)} | New since last run: {len(new_items)}")
    if not all_items:
        print("[warn] Zero items scraped from every source — the sites likely changed their "
              "markup, or blocked the request. Check SOURCES selectors and run again manually.")


if __name__ == "__main__":
    main()
