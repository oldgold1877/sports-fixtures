#!/usr/bin/env python3
"""Debug: dump raw text lines for zero-fixture categories"""
import requests, os, re
from bs4 import BeautifulSoup
from urllib.parse import quote

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
LOADER_URL   = "https://dashboard.crispfiles.com/fixtures/loader.php"
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

def dump_category(session, name, filename):
    r = session.get(LOADER_URL + "?file=" + quote(filename), timeout=45)
    print(f"\n{'='*60}")
    print(f"CATEGORY: {name}  (status {r.status_code})")
    print(f"{'='*60}")
    print("RAW RESPONSE:")
    print(r.text[:3000])
    print("\nEXTRACTED LINES:")
    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.find_all(["script","style"]): el.decompose()
    for line in soup.get_text(separator="\n").splitlines():
        line = line.strip()
        if line: print(f"  {repr(line)}")

def main():
    session = make_session()
    login(session)
    session.get(FIXTURES_URL, timeout=30)
    for name, filename in [
        ("BBC RED BUTTON", "BBC RED BUTTON.php"),
        ("DAZN UK",        "DAZN UK.php"),
        ("ESPN PLUS",      "ESPN PLUS.php"),
    ]:
        dump_category(session, name, filename)

if __name__ == "__main__":
    main()
