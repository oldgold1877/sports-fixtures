#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper - DEBUG v3
Dumps the full HTML/JS of the fixtures list page to find the AJAX handler
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys

LOGIN_URL     = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL  = "https://dashboard.crispfiles.com/fixtures/list.php"
BASE_URL      = "https://dashboard.crispfiles.com"

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
            post_url = BASE_URL + "/" + form["action"].lstrip("/")
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

    r = session.get(FIXTURES_URL, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    # Print ALL script tag contents so we can see loadFixtureContent() definition
    print("=== ALL <script> BLOCKS ===")
    for i, script in enumerate(soup.find_all("script")):
        src = script.get("src")
        if src:
            # External script — fetch it
            full_src = src if src.startswith("http") else BASE_URL + "/" + src.lstrip("/")
            print(f"\n--- External script {i}: {full_src} ---")
            try:
                rs = session.get(full_src, timeout=20)
                print(rs.text[:5000])
            except Exception as e:
                print(f"  Could not fetch: {e}")
        else:
            print(f"\n--- Inline script {i} ---")
            print(script.string or "(empty)")

    print("\n=== END SCRIPTS ===")


if __name__ == "__main__":
    main()
