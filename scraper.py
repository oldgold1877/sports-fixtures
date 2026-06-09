#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper - FINAL
Fetches each category via:
  GET https://dashboard.crispfiles.com/fixtures/loader.php?file=GAA+PLUS.php
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

LOGIN_URL     = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL  = "https://dashboard.crispfiles.com/fixtures/list.php"
LOADER_URL    = "https://dashboard.crispfiles.com/fixtures/loader.php"
BASE_URL      = "https://dashboard.crispfiles.com"

USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("ERROR: CRISPFILES_USERNAME or CRISPFILES_PASSWORD not set.")
    sys.exit(1)


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": FIXTURES_URL,
    })
    return s


def login(session):
    print("[1/4] Logging in...")
    r = session.get(LOGIN_URL, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    payload = {}
    post_url = LOGIN_URL
    if form:
        for inp in form.find_all("input"):
            n = inp.get("name")
            if n:
                payload[n] = inp.get("value", "")
        if form.get("action"):
            post_url = BASE_URL + "/" + form["action"].lstrip("/")
    payload["username"] = USERNAME
    payload["password"] = PASSWORD
    r2 = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    if "dashboard login" in r2.text.lower() and "index.php" in r2.url:
        print("      ✗ Login failed — check secrets")
        sys.exit(1)
    print("      ✓ Login successful")


def get_categories(session):
    print("[2/4] Reading fixture categories...")
    r = session.get(FIXTURES_URL, timeout=20)
    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected to login")
        sys.exit(1)
    soup = BeautifulSoup(r.text, "html.parser")
    categories = []
    for el in soup.find_all(onclick=True):
        m = re.search(r"loadFixtureContent\('(.+?)'\)", el["onclick"])
        if m:
            filename = m.group(1)          # e.g. "GAA PLUS.php"
            name = el.get_text(strip=True)
            categories.append({"name": name, "filename": filename})
            print(f"      {name}")
    print(f"      Total: {len(categories)} categories")
    return categories


def scrape_category(session, cat):
    url = LOADER_URL + "?file=" + quote(cat["filename"])
    r = session.get(url, timeout=20)

    if r.status_code != 200:
        print(f"        WARNING: HTTP {r.status_code} for {url}")
        return {"fixtures": [], "last_updated": ""}

    # Response is an HTML fragment
    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.find_all(["script", "style"]):
        el.decompose()

    last_updated = ""
    fixtures = []

    # Check for "Last Updated" anywhere in the text
    full_text = soup.get_text(separator="\n")
    for line in full_text.splitlines():
        line = line.strip()
        if "last updated" in line.lower():
            last_updated = line
            break

    # Fixture lines: grab every non-empty text line that looks like a fixture
    for line in full_text.splitlines():
        line = line.strip()
        if not line or len(line) < 15:
            continue
        if "last updated" in line.lower():
            continue
        skip = ["back to", "cookie", "privacy", "terms", "©", "all rights", "logout",
                "loading", "error loading"]
        if any(s in line.lower() for s in skip):
            continue

        # Must contain a match pattern OR time zones
        has_match = " v " in line or " V " in line
        has_time  = any(t in line.lower() for t in [
            "pm uk", "am uk", "pm et", "am et", "pm pt", "am pt",
            "pm bst", "am bst", "pm gmt", "am gmt", "pm ist", "am ist",
            "pm cet", "am cet", "pm aet", "am aet"
        ])

        if has_match or has_time:
            fixtures.append(line)

    return {"fixtures": fixtures, "last_updated": last_updated}


def main():
    session = make_session()
    login(session)
    categories = get_categories(session)

    if not categories:
        print("ERROR: No categories found.")
        sys.exit(1)

    # Visit fixtures page first so the Referer and session are primed
    session.get(FIXTURES_URL, timeout=20)

    print(f"[3/4] Scraping {len(categories)} categories via loader.php...")
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"      {cat['name']}...", end=" ", flush=True)
        data = scrape_category(session, cat)
        print(f"{len(data['fixtures'])} fixtures"
              + (f"  [{data['last_updated']}]" if data["last_updated"] else ""))
        output["categories"].append({
            "name":         cat["name"],
            "last_updated": data["last_updated"],
            "fixtures":     data["fixtures"]
        })

    print("[4/4] Writing fixtures.json...")
    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["fixtures"]) for c in output["categories"])
    print(f"\n✓ Done — {len(output['categories'])} categories, {total} total fixtures")


if __name__ == "__main__":
    main()
