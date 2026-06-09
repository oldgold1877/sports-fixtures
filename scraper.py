#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper - DEBUG v2
Dumps raw content of first category to diagnose fixture line format
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
from datetime import datetime, timezone

LOGIN_URL     = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL  = "https://dashboard.crispfiles.com/fixtures/list.php"
FIXTURES_BASE = "https://dashboard.crispfiles.com/fixtures/"

USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("ERROR: credentials not set.")
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
    r2 = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    if "dashboard login" in r2.text.lower() and "index.php" in r2.url:
        print("✗ Login failed")
        sys.exit(1)
    print("✓ Login successful")


def main():
    session = make_session()
    login(session)

    # Get category list
    r = session.get(FIXTURES_URL, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    categories = []
    for el in soup.find_all(onclick=True):
        match = re.search(r"loadFixtureContent\('(.+?)'\)", el["onclick"])
        if match:
            filename = match.group(1)
            name = el.get_text(strip=True)
            url = FIXTURES_BASE + requests.utils.quote(filename)
            categories.append({"name": name, "url": url})

    print(f"Found {len(categories)} categories\n")

    # Debug: dump raw response for GAA PLUS (we know it has content from your screenshot)
    # and also LIVE EVENTS
    for debug_cat in ["GAA PLUS", "LIVE EVENTS"]:
        cat = next((c for c in categories if c["name"] == debug_cat), None)
        if not cat:
            continue

        print(f"{'='*60}")
        print(f"DEBUG: {cat['name']}")
        print(f"URL: {cat['url']}")
        print(f"{'='*60}")

        r = session.get(cat["url"], timeout=20)
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type','')}")
        print(f"Response length: {len(r.text)} chars")
        print(f"\n--- RAW RESPONSE (first 3000 chars) ---")
        print(r.text[:3000])
        print(f"\n--- END RAW ---\n")

        # Also show it as extracted text lines
        soup2 = BeautifulSoup(r.text, "html.parser")
        for el in soup2.find_all(["nav","header","footer","script","style"]):
            el.decompose()
        lines = [l.strip() for l in soup2.get_text(separator="\n").splitlines() if l.strip()]
        print(f"--- EXTRACTED TEXT LINES ({len(lines)} lines) ---")
        for line in lines:
            print(f"  {repr(line)}")
        print(f"--- END LINES ---\n")

    print("DEBUG COMPLETE")


if __name__ == "__main__":
    main()
