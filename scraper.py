#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper
1. POSTs login credentials to index.php
2. Navigates to /fixtures/list.php and reads onclick="loadFixtureContent('NAME.php')"
3. Fetches each category URL directly
4. Saves output to fixtures.json
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
from datetime import datetime, timezone

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
FIXTURES_BASE = "https://dashboard.crispfiles.com/fixtures/"

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
    })
    return s


def login(session):
    print("[1/4] Fetching login page...")
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
            post_url = "https://dashboard.crispfiles.com/" + form["action"].lstrip("/")

    payload["username"] = USERNAME
    payload["password"] = PASSWORD

    print("[2/4] Logging in...")
    r2 = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    print(f"      Final URL: {r2.url}")

    if "dashboard login" in r2.text.lower() and "index.php" in r2.url:
        print("      ✗ Login failed — check secrets")
        sys.exit(1)

    print("      ✓ Login successful")


def get_categories(session):
    print("[3/4] Reading fixture categories...")
    r = session.get(FIXTURES_URL, timeout=20)

    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected to login — session not persisting")
        sys.exit(1)

    soup = BeautifulSoup(r.text, "html.parser")
    categories = []

    # Categories are divs with onclick="loadFixtureContent('NAME.php')"
    for el in soup.find_all(onclick=True):
        match = re.search(r"loadFixtureContent\('(.+?)'\)", el["onclick"])
        if match:
            filename = match.group(1)          # e.g. "GAA PLUS.php"
            name     = el.get_text(strip=True) # e.g. "GAA PLUS"
            url      = FIXTURES_BASE + requests.utils.quote(filename)
            categories.append({"name": name, "url": url, "filename": filename})
            print(f"      {name}")

    print(f"      Total: {len(categories)} categories")
    return categories


def scrape_category(session, cat):
    r = session.get(cat["url"], timeout=20)

    # The category pages may return plain text or HTML
    content_type = r.headers.get("Content-Type", "")
    if "html" in content_type:
        soup = BeautifulSoup(r.text, "html.parser")
        # Remove nav noise
        for el in soup.find_all(["nav", "header", "footer", "script", "style"]):
            el.decompose()
        text = soup.get_text(separator="\n")
    else:
        text = r.text

    last_updated = ""
    fixtures = []

    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 10:
            continue

        # Capture "Last Updated" line
        if "last updated" in line.lower():
            last_updated = line
            continue

        # Fixture lines contain a match (" v ") or timezone time markers
        has_match = " v " in line or " V " in line
        has_time  = any(t in line.lower() for t in [
            "pm uk", "am uk", "pm et", "am et", "pm pt", "am pt",
            "pm bst", "am bst", "pm gmt", "am gmt", "pm ist", "am ist"
        ])

        if not (has_match or has_time):
            continue

        skip = ["back to", "cookie", "privacy", "terms", "©", "all rights", "logout"]
        if any(s in line.lower() for s in skip):
            continue

        fixtures.append(line)

    return {"fixtures": fixtures, "last_updated": last_updated}


def main():
    session = make_session()
    login(session)
    categories = get_categories(session)

    if not categories:
        print("ERROR: No categories found.")
        sys.exit(1)

    print(f"[4/4] Scraping {len(categories)} categories...")
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"      {cat['name']}...", end=" ", flush=True)
        data = scrape_category(session, cat)
        print(f"{len(data['fixtures'])} fixtures")
        output["categories"].append({
            "name":         cat["name"],
            "last_updated": data["last_updated"],
            "fixtures":     data["fixtures"]
        })

    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["fixtures"]) for c in output["categories"])
    print(f"\n✓ fixtures.json written — {len(output['categories'])} categories, {total} total fixtures")


if __name__ == "__main__":
    main()
