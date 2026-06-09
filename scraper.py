#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper - FINAL v2
- Handles HTTP 500s and timeouts gracefully (skips broken categories)
- Increased timeout to 45s for slow responses
- Dumps text lines for zero-fixture 200-response categories to diagnose format
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

# Categories that consistently 500 or timeout — skip silently
SKIP_CATEGORIES = set()

# For debugging zero-fixture 200-response pages, dump first one we find
DEBUG_ZERO = True
DEBUG_ZERO_DONE = False


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": FIXTURES_URL,
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def login(session):
    print("[1/4] Logging in...")
    r = session.get(LOGIN_URL, timeout=30)
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
    r2 = session.post(post_url, data=payload, timeout=30, allow_redirects=True)
    if "dashboard login" in r2.text.lower() and "index.php" in r2.url:
        print("      ✗ Login failed")
        sys.exit(1)
    print("      ✓ Login successful")


def get_categories(session):
    print("[2/4] Reading fixture categories...")
    r = session.get(FIXTURES_URL, timeout=30)
    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected to login")
        sys.exit(1)
    soup = BeautifulSoup(r.text, "html.parser")
    categories = []
    for el in soup.find_all(onclick=True):
        m = re.search(r"loadFixtureContent\('(.+?)'\)", el["onclick"])
        if m:
            filename = m.group(1)
            name = el.get_text(strip=True)
            categories.append({"name": name, "filename": filename})
    print(f"      Found {len(categories)} categories")
    return categories


def extract_fixtures(text, cat_name):
    """Extract fixture lines from plain text. Returns (fixtures, last_updated)."""
    global DEBUG_ZERO, DEBUG_ZERO_DONE

    last_updated = ""
    fixtures = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        if "last updated" in line.lower():
            last_updated = line
            continue
        skip = ["back to", "cookie", "privacy", "terms", "©", "all rights",
                "logout", "loading", "error loading", "fixture content"]
        if any(s in line.lower() for s in skip):
            continue
        if len(line) < 10:
            continue

        has_match = " v " in line or " V " in line
        has_time  = any(t in line.lower() for t in [
            "pm uk", "am uk", "pm et", "am et", "pm pt", "am pt",
            "pm bst", "am bst", "pm gmt", "am gmt", "pm ist", "am ist",
            "pm cet", "am cet", "pm aet", "am aet", "pm aedt", "am aedt"
        ])

        if has_match or has_time:
            fixtures.append(line)

    # If we got a 200 but 0 fixtures, dump lines to help diagnose format
    if not fixtures and DEBUG_ZERO and not DEBUG_ZERO_DONE and lines:
        print(f"\n      DEBUG zero-fixture dump for '{cat_name}':")
        for l in lines[:40]:
            print(f"        {repr(l)}")
        DEBUG_ZERO_DONE = True

    return fixtures, last_updated


def scrape_category(session, cat):
    url = LOADER_URL + "?file=" + quote(cat["filename"])
    try:
        r = session.get(url, timeout=45)
    except requests.exceptions.Timeout:
        print(f"TIMEOUT (skipping)")
        return {"fixtures": [], "last_updated": "", "status": "timeout"}
    except requests.exceptions.RequestException as e:
        print(f"ERROR {e} (skipping)")
        return {"fixtures": [], "last_updated": "", "status": "error"}

    if r.status_code == 500:
        print(f"HTTP 500 — category unavailable (skipping)")
        return {"fixtures": [], "last_updated": "", "status": "unavailable"}

    if r.status_code != 200:
        print(f"HTTP {r.status_code} (skipping)")
        return {"fixtures": [], "last_updated": "", "status": f"http_{r.status_code}"}

    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.find_all(["script", "style"]):
        el.decompose()
    text = soup.get_text(separator="\n")

    fixtures, last_updated = extract_fixtures(text, cat["name"])
    return {"fixtures": fixtures, "last_updated": last_updated, "status": "ok"}


def main():
    session = make_session()
    login(session)
    categories = get_categories(session)

    if not categories:
        print("ERROR: No categories found.")
        sys.exit(1)

    # Prime the session with a visit to the fixtures page
    session.get(FIXTURES_URL, timeout=30)

    print(f"[3/4] Scraping {len(categories)} categories...")
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"      {cat['name']:<30}", end=" ", flush=True)
        data = scrape_category(session, cat)
        n = len(data["fixtures"])
        status = data.get("status", "ok")
        if status == "ok":
            print(f"{n} fixtures" + (f"  [{data['last_updated']}]" if data["last_updated"] else ""))
        # Only include categories that actually have content
        if n > 0:
            output["categories"].append({
                "name":         cat["name"],
                "last_updated": data["last_updated"],
                "fixtures":     data["fixtures"]
            })

    print(f"\n[4/4] Writing fixtures.json...")
    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["fixtures"]) for c in output["categories"])
    print(f"✓ Done — {len(output['categories'])} categories with fixtures, {total} total fixtures")


if __name__ == "__main__":
    main()
