#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper
1. POSTs login credentials to index.php
2. Navigates to /fixtures/list.php to get category links
3. Scrapes each category page for fixture lines
4. Saves output to fixtures.json
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
from datetime import datetime, timezone

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
BASE_URL     = "https://dashboard.crispfiles.com"

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
    print(f"[1/4] Fetching login page...")
    r = session.get(LOGIN_URL, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    form = soup.find("form")
    payload = {}
    if form:
        for inp in form.find_all("input"):
            n = inp.get("name")
            if n:
                payload[n] = inp.get("value", "")
        post_url = LOGIN_URL
        form_action = form.get("action", "")
        if form_action:
            post_url = BASE_URL + "/" + form_action.lstrip("/")
    else:
        post_url = LOGIN_URL

    payload["username"] = USERNAME
    payload["password"] = PASSWORD

    print(f"[2/4] Logging in...")
    r2 = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    print(f"      Final URL after login: {r2.url}")

    if "dashboard login" in r2.text.lower() and r2.url.endswith("index.php"):
        print("      ✗ Login failed")
        sys.exit(1)

    print("      ✓ Login successful")
    return True


def get_categories(session):
    print(f"[3/4] Fetching fixtures page...")
    r = session.get(FIXTURES_URL, timeout=20)

    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected to login — session not persisting")
        sys.exit(1)

    # --- DEBUG: dump ALL links on the page so we can see exactly what's there ---
    soup = BeautifulSoup(r.text, "html.parser")
    print("      All <a> tags found on fixtures page:")
    for a in soup.find_all("a", href=True):
        print(f"        href={a['href']!r:60s}  text={a.get_text(strip=True)!r}")

    # Also dump any onclick attributes that might contain links
    print("      Elements with onclick:")
    for el in soup.find_all(onclick=True):
        print(f"        tag={el.name!r}  onclick={el['onclick']!r}  text={el.get_text(strip=True)!r}")

    # And check for any data attributes pointing to URLs
    print("      Elements with data-url / data-href / data-link:")
    for el in soup.find_all(True):
        for attr in ("data-url", "data-href", "data-link", "data-src"):
            if el.get(attr):
                print(f"        tag={el.name!r}  {attr}={el[attr]!r}  text={el.get_text(strip=True)!r}")

    return []   # return empty for now — we'll populate once we see the link structure


def main():
    session = make_session()
    login(session)
    get_categories(session)
    print("\nDEBUG RUN COMPLETE — check the link dump above to identify category link structure")


if __name__ == "__main__":
    main()
