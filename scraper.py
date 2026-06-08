#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper
Logs into dashboard.crispfiles.com, scrapes all fixture categories,
and saves the data to fixtures.json
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone
import sys

LOGIN_URL = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
BASE_URL = "https://dashboard.crispfiles.com"

# Reads from environment variables (set as GitHub Secrets, or export locally)
# To run locally:  export CRISPFILES_USERNAME=you@example.com  (then run the script)
USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("✗ Credentials missing — set CRISPFILES_USERNAME and CRISPFILES_PASSWORD environment variables")
    sys.exit(1)

def login(session):
    """Log into the dashboard and return True if successful."""
    # First GET the login page to grab any hidden fields / tokens
    r = session.get(LOGIN_URL)
    soup = BeautifulSoup(r.text, "html.parser")

    # Build the login payload from the form
    form = soup.find("form")
    payload = {}
    if form:
        for inp in form.find_all("input"):
            name = inp.get("name")
            value = inp.get("value", "")
            if name:
                payload[name] = value

    # Override with real credentials
    # Try common field name patterns
    for field in ["username", "user", "email", "login"]:
        if field in payload:
            payload[field] = USERNAME
            break
    else:
        payload["username"] = USERNAME

    for field in ["password", "pass", "pwd"]:
        if field in payload:
            payload[field] = PASSWORD
            break
    else:
        payload["password"] = PASSWORD

    r = session.post(LOGIN_URL, data=payload, allow_redirects=True)

    # Check we're logged in by looking for something only logged-in users see
    if "fixtures" in r.text.lower() or "logout" in r.text.lower() or "dashboard" in r.text.lower():
        print("✓ Login successful")
        return True
    else:
        print("✗ Login failed — check your USERNAME and PASSWORD in scraper.py")
        print(f"  Response URL: {r.url}")
        return False


def get_categories(session):
    """Scrape the fixtures list page and return all category links."""
    r = session.get(FIXTURES_URL)
    soup = BeautifulSoup(r.text, "html.parser")

    categories = []
    # Categories appear as clickable cards/links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "fixture" in href.lower() or "list" in href.lower() or "view" in href.lower():
            name = a.get_text(strip=True)
            if name and len(name) > 2:
                full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                categories.append({"name": name, "url": full_url})

    # Deduplicate
    seen = set()
    unique = []
    for c in categories:
        key = c["url"]
        if key not in seen:
            seen.add(key)
            unique.append(c)

    print(f"✓ Found {len(unique)} categories")
    return unique


def get_fixtures_for_category(session, category):
    """Scrape the fixture list for a single category."""
    r = session.get(category["url"])
    soup = BeautifulSoup(r.text, "html.parser")

    fixtures = []
    last_updated = ""

    # Look for "Last Updated" text
    for tag in soup.find_all(string=lambda t: t and "last updated" in t.lower()):
        last_updated = tag.strip()
        break

    # Fixtures are plain text lines — look for the main content area
    # Try common content containers
    content = None
    for selector in ["main", "article", ".content", "#content", ".fixtures", "#fixtures", "body"]:
        content = soup.select_one(selector)
        if content:
            break

    if content:
        # Get all text lines that look like fixture entries
        text = content.get_text(separator="\n")
        for line in text.splitlines():
            line = line.strip()
            # Fixture lines typically contain " v " or have a time pattern
            if line and len(line) > 20 and (" v " in line or " V " in line or "pm" in line.lower() or "am" in line.lower()):
                # Skip navigation/header lines
                if not any(skip in line.lower() for skip in ["back to", "last updated", "cookie", "privacy"]):
                    fixtures.append(line)

    return {"fixtures": fixtures, "last_updated": last_updated}


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    if not login(session):
        sys.exit(1)

    categories = get_categories(session)

    if not categories:
        print("✗ No categories found — the page structure may have changed")
        sys.exit(1)

    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"  Scraping: {cat['name']} ...")
        data = get_fixtures_for_category(session, cat)
        output["categories"].append({
            "name": cat["name"],
            "url": cat["url"],
            "last_updated": data["last_updated"],
            "fixtures": data["fixtures"]
        })

    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(c["fixtures"]) for c in output["categories"])
    print(f"\n✓ Saved fixtures.json — {len(output['categories'])} categories, {total} fixtures")


if __name__ == "__main__":
    main()
