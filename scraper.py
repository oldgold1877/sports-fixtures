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

LOGIN_URL   = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
BASE_URL    = "https://dashboard.crispfiles.com"

USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("ERROR: CRISPFILES_USERNAME or CRISPFILES_PASSWORD environment variable is not set.")
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
    print(f"[1/4] Fetching login page: {LOGIN_URL}")
    r = session.get(LOGIN_URL, timeout=20)
    print(f"      Status: {r.status_code}  URL: {r.url}")

    soup = BeautifulSoup(r.text, "html.parser")

    # Grab every input in the form so we carry hidden fields (tokens etc.)
    form = soup.find("form")
    payload = {}
    if form:
        for inp in form.find_all("input"):
            n = inp.get("name")
            v = inp.get("value", "")
            if n:
                payload[n] = v
        form_action = form.get("action", "")
        post_url = (BASE_URL + "/" + form_action.lstrip("/")) if form_action else LOGIN_URL
        print(f"      Form action: {form_action!r}  ->  posting to: {post_url}")
        print(f"      Hidden fields found: {[k for k in payload if k not in ('username','password','user','email','pass','pwd')]}")
    else:
        print("      WARNING: No <form> tag found on login page — posting directly to LOGIN_URL")
        post_url = LOGIN_URL

    # Inject credentials — try both common field names
    # We'll set all likely variants; the server ignores unknown fields
    payload["username"] = USERNAME
    payload["password"] = PASSWORD
    payload["user"]     = USERNAME
    payload["pass"]     = PASSWORD
    payload["email"]    = USERNAME
    payload["pwd"]      = PASSWORD

    print(f"[2/4] Posting credentials to: {post_url}")
    r2 = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    print(f"      Status: {r2.status_code}  Final URL: {r2.url}")

    page_lower = r2.text.lower()
    # Signs we're logged in
    logged_in = any(x in page_lower for x in ["logout", "log out", "sign out", "dashboard", "fixtures", "welcome"])
    # Signs we're still on the login page
    still_login = "dashboard login" in page_lower or r2.url.rstrip("/").endswith("index.php")

    if logged_in and not still_login:
        print("      ✓ Login appears successful")
        return True
    else:
        print("      ✗ Login failed — still on login page or credentials rejected")
        # Print a snippet to help debug
        snippet = r2.text[:800].replace("\n", " ")
        print(f"      Page snippet: {snippet}")
        return False


def get_categories(session):
    print(f"[3/4] Fetching fixtures list: {FIXTURES_URL}")
    r = session.get(FIXTURES_URL, timeout=20)
    print(f"      Status: {r.status_code}  URL: {r.url}")

    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected back to login — session cookie didn't persist")
        sys.exit(1)

    soup = BeautifulSoup(r.text, "html.parser")
    categories = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # Category links typically look like view.php?id=X or similar
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        # Build absolute URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = BASE_URL + href
        else:
            full_url = BASE_URL + "/fixtures/" + href

        # Skip links that go back to the main site or login
        if "index.php" in full_url or full_url == FIXTURES_URL:
            continue

        # Only keep links within the fixtures section
        if "fixtures" not in full_url and "view" not in full_url:
            continue

        name = a.get_text(separator=" ", strip=True)
        # Clean up whitespace and skip empty/nav labels
        name = " ".join(name.split())
        if not name or len(name) < 3:
            continue
        skip_words = ["back", "home", "login", "logout", "terms", "privacy", "cookie"]
        if any(w in name.lower() for w in skip_words):
            continue

        if full_url not in seen:
            seen.add(full_url)
            categories.append({"name": name, "url": full_url})
            print(f"      Found category: {name!r:40s}  ->  {full_url}")

    print(f"      Total categories: {len(categories)}")
    return categories


def scrape_category(session, cat):
    r = session.get(cat["url"], timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    last_updated = ""
    for tag in soup.find_all(string=lambda t: t and "last updated" in t.lower()):
        last_updated = tag.strip()
        break

    fixtures = []
    # Try to find the main content container
    body = soup.find("body")
    if not body:
        return {"fixtures": [], "last_updated": ""}

    # Remove nav/header/footer noise
    for el in body.find_all(["nav", "header", "footer", "script", "style"]):
        el.decompose()

    text = body.get_text(separator="\n")
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 15:
            continue
        # Fixture lines contain " v " (match) or timezone markers
        has_match   = " v " in line or " V " in line
        has_time    = any(t in line.lower() for t in ["pm uk", "am uk", "pm et", "am et", "pm pt", "am pt", "pm bst", "am bst", "pm gmt", "am gmt"])
        if not (has_match or has_time):
            continue
        # Skip navigation debris
        skip = ["back to", "last updated", "cookie", "privacy", "terms", "©", "all rights"]
        if any(s in line.lower() for s in skip):
            continue
        fixtures.append(line)

    return {"fixtures": fixtures, "last_updated": last_updated}


def main():
    session = make_session()

    if not login(session):
        sys.exit(1)

    categories = get_categories(session)
    if not categories:
        print("ERROR: No categories found on the fixtures page.")
        print("       The page structure may differ from expected — check the Actions log above.")
        sys.exit(1)

    print(f"[4/4] Scraping {len(categories)} categories...")
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"      Scraping: {cat['name']!r}")
        data = scrape_category(session, cat)
        print(f"        -> {len(data['fixtures'])} fixtures")
        output["categories"].append({
            "name": cat["name"],
            "url":  cat["url"],
            "last_updated": data["last_updated"],
            "fixtures": data["fixtures"]
        })

    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["fixtures"]) for c in output["categories"])
    print(f"\n✓ Done — fixtures.json written ({len(output['categories'])} categories, {total} total fixtures)")


if __name__ == "__main__":
    main()
