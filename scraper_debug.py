#!/usr/bin/env python3
"""Debug: dump raw AJAX response for one event"""
import requests, os, sys, re, base64
from bs4 import BeautifulSoup
from urllib.parse import quote

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
LOADER_URL   = "https://dashboard.crispfiles.com/fixtures/loader.php"
AJAX_URL     = "https://dashboard.crispfiles.com/fixtures/pages/get_event_channels_ajax.php"
BASE_URL     = "https://dashboard.crispfiles.com"
USERNAME = os.environ.get("CRISPFILES_USERNAME","")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD","")

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0","Referer":FIXTURES_URL,"X-Requested-With":"XMLHttpRequest"})
    return s

def login(session):
    r = session.get(LOGIN_URL, timeout=30)
    soup = BeautifulSoup(r.text,"html.parser")
    form = soup.find("form")
    payload = {}
    post_url = LOGIN_URL
    if form:
        for inp in form.find_all("input"):
            n = inp.get("name")
            if n: payload[n] = inp.get("value","")
        if form.get("action"): post_url = BASE_URL+"/"+form["action"].lstrip("/")
    payload["username"] = USERNAME
    payload["password"] = PASSWORD
    session.post(post_url, data=payload, timeout=30, allow_redirects=True)
    print("✓ Logged in")

def main():
    session = make_session()
    login(session)
    session.get(FIXTURES_URL, timeout=30)

    # Get TODAYS EVENTS and grab first event's b64
    r = session.get(LOADER_URL + "?file=" + quote("TODAYS EVENTS.php"), timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    b64 = None
    for el in soup.find_all(onclick=True):
        m = re.search(r'loadEventChannels\(\s*\d+\s*,\s*["\'](.+?)["\']\s*\)', el["onclick"])
        if m:
            b64 = m.group(1)
            print(f"Event: {el.get_text(strip=True)}")
            print(f"b64:   {b64}")
            print(f"decoded: {base64.b64decode(b64+'==').decode('utf-8')}")
            break

    if not b64:
        print("No events found"); return

    print("\n=== RAW AJAX RESPONSE ===")
    r2 = session.post(AJAX_URL,
        data={"event_data": b64},
        headers={"Content-Type":"application/x-www-form-urlencoded"},
        timeout=30)
    print(f"Status: {r2.status_code}")
    print(r2.text)

if __name__ == "__main__":
    main()
