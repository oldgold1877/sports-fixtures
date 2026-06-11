#!/usr/bin/env python3
"""Debug: dump raw content of LIVE EVENTS"""
import requests, os
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

def main():
    session = make_session()
    login(session)
    session.get(FIXTURES_URL, timeout=30)

    r = session.get(LOADER_URL + "?file=" + quote("LIVE EVENTS.php"), timeout=45)
    print(f"Status: {r.status_code}")
    print("\n=== RAW RESPONSE ===")
    print(r.text[:5000])
    print("\n=== PARSED LINES ===")
    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.find_all(["script","style"]): el.decompose()
    # Show every element with its tag so we can see date separators
    for el in soup.find_all(True):
        text = el.get_text(strip=True)
        if text and el.name in ["h1","h2","h3","h4","strong","b","p","li","br","span","div"]:
            print(f"  <{el.name}> {repr(text)}")

if __name__ == "__main__":
    main()
