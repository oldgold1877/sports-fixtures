#!/usr/bin/env python3
"""Debug: dump raw content of TODAYS EVENTS page"""

import requests
from bs4 import BeautifulSoup
import os, sys, re
from urllib.parse import quote

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
LOADER_URL   = "https://dashboard.crispfiles.com/fixtures/loader.php"
AJAX_URL     = "https://dashboard.crispfiles.com/fixtures/pages/get_event_channels_ajax.php"
BASE_URL     = "https://dashboard.crispfiles.com"

USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": FIXTURES_URL,
        "X-Requested-With": "XMLHttpRequest",
    })
    return s

def login(session):
    r = session.get(LOGIN_URL, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    payload = {}
    post_url = LOGIN_URL
    if form:
        for inp in form.find_all("input"):
            n = inp.get("name")
            if n: payload[n] = inp.get("value", "")
        if form.get("action"):
            post_url = BASE_URL + "/" + form["action"].lstrip("/")
    payload["username"] = USERNAME
    payload["password"] = PASSWORD
    session.post(post_url, data=payload, timeout=30, allow_redirects=True)
    print("✓ Logged in")

def main():
    session = make_session()
    login(session)
    session.get(FIXTURES_URL, timeout=30)

    # Fetch TODAYS EVENTS via loader
    print("\n=== TODAYS EVENTS raw HTML ===")
    r = session.get(LOADER_URL + "?file=" + quote("TODAYS EVENTS.php"), timeout=45)
    print(f"Status: {r.status_code}")
    print(r.text[:8000])

    # Parse it and find onclick/data attributes to understand event structure
    soup = BeautifulSoup(r.text, "html.parser")
    print("\n=== onclick elements ===")
    for el in soup.find_all(onclick=True):
        print(f"  tag={el.name}  onclick={el['onclick']!r}  text={el.get_text(strip=True)[:80]!r}")

    print("\n=== data-* attributes ===")
    for el in soup.find_all(True):
        data_attrs = {k:v for k,v in el.attrs.items() if k.startswith("data-")}
        if data_attrs:
            print(f"  tag={el.name}  attrs={data_attrs}  text={el.get_text(strip=True)[:80]!r}")

    # Try calling the AJAX endpoint with the first event_data we find
    print("\n=== Trying AJAX call for first event ===")
    # Look for event_data in onclick attributes
    event_datas = []
    for el in soup.find_all(onclick=True):
        m = re.search(r"loadEventChannels\(\s*\d+\s*,\s*'(.+?)'\s*\)", el["onclick"])
        if m:
            event_datas.append(m.group(1))

    if event_datas:
        print(f"  Found {len(event_datas)} events with event_data")
        print(f"  First event_data: {event_datas[0]!r}")
        # Call the AJAX endpoint
        ajax_r = session.post(AJAX_URL, 
            data={"event_data": event_datas[0]},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30)
        print(f"  AJAX status: {ajax_r.status_code}")
        print(f"  AJAX response:\n{ajax_r.text[:2000]}")
    else:
        print("  No loadEventChannels() calls found — event data may be in data-* attributes")
        print("  Looking for any event items...")
        for el in soup.find_all(class_=True):
            classes = el.get("class", [])
            if any("event" in c.lower() for c in classes):
                print(f"  class={classes}  text={el.get_text(strip=True)[:100]!r}")

if __name__ == "__main__":
    main()
