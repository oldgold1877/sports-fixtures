#!/usr/bin/env python3
"""
CrispFiles Fixtures Scraper - FINAL v6
Handles all fixture line formats: GAA/LOI, DAZN, ESPN+, BBC Red Button.
"""

import requests
from bs4 import BeautifulSoup
import json, os, re, sys, base64
from datetime import datetime, timezone
from urllib.parse import quote
import time

LOGIN_URL    = "https://dashboard.crispfiles.com/index.php"
FIXTURES_URL = "https://dashboard.crispfiles.com/fixtures/list.php"
LOADER_URL   = "https://dashboard.crispfiles.com/fixtures/loader.php"
AJAX_URL     = "https://dashboard.crispfiles.com/fixtures/pages/get_event_channels_ajax.php"
BASE_URL     = "https://dashboard.crispfiles.com"

USERNAME = os.environ.get("CRISPFILES_USERNAME", "")
PASSWORD = os.environ.get("CRISPFILES_PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("ERROR: credentials not set."); sys.exit(1)


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
    print("[1/4] Logging in...")
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
    r2 = session.post(post_url, data=payload, timeout=30, allow_redirects=True)
    if "dashboard login" in r2.text.lower() and "index.php" in r2.url:
        print("      ✗ Login failed"); sys.exit(1)
    print("      ✓ Login successful")


def get_categories(session):
    print("[2/4] Reading categories...")
    r = session.get(FIXTURES_URL, timeout=30)
    if "dashboard login" in r.text.lower():
        print("      ✗ Redirected to login"); sys.exit(1)
    soup = BeautifulSoup(r.text, "html.parser")
    categories = []
    for el in soup.find_all(onclick=True):
        m = re.search(r"loadFixtureContent\('(.+?)'\)", el["onclick"])
        if m:
            categories.append({"name": el.get_text(strip=True), "filename": m.group(1)})
    print(f"      Found {len(categories)} categories")
    return categories


def extract_plain_fixtures(text):
    last_updated = ""
    fixtures = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 10: continue
        if "last updated" in line.lower():
            last_updated = line; continue
        skip = ["back to","cookie","privacy","terms","©","all rights","logout","loading","error loading","fixture content"]
        if any(s in line.lower() for s in skip): continue
        # Format: GAA/LOI/MLB etc  — "TEAM v TEAM" or "Sat 13/06 4:30pm UK"
        has_v        = bool(re.search(r'\b[Vv]\b', line))
        has_tz_time  = bool(re.search(r'\d+:\d+(am|pm)\s+(UK|ET|PT|BST|GMT|IST|CET|AET|AEDT)', line, re.I))
        # Format: DAZN — "Title vs. Title - HH:MM DD/MM/YYYY"
        has_vs       = ' vs.' in line or ' vs ' in line
        has_time_date= bool(re.search(r'\d{1,2}:\d{2}\s+\d{2}/\d{2}/\d{4}', line))
        # Format: ESPN+ — "HH:MM - HH:MM - Title"
        has_time_range = bool(re.search(r'\d{2}:\d{2}\s+-\s+\d{2}:\d{2}', line))
        # Format: BBC Red Button — "Day DD/MM H:MMam/pm" (no timezone)
        has_day_time = bool(re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{2}/\d{2}\s+\d{1,2}:\d{2}(am|pm)', line, re.I))

        if has_v or has_tz_time or has_vs or has_time_date or has_time_range or has_day_time:
            # Strip non-UK timezones (ET, PT etc.) — keep only the UK time
            line = re.sub(r'\s*//\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{2}/\d{2}.*$', '', line).strip()
            # Remove the trailing " UK" timezone label (now redundant)
            line = re.sub(r'(\d+:\d+(?:am|pm))\s+UK\b', r'\1', line, flags=re.I).strip()
            fixtures.append(line)
    return fixtures, last_updated


def decode_event_data(b64):
    try:
        decoded = base64.b64decode(b64 + "==").decode("utf-8")
        parts = decoded.split("|")
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    except Exception:
        return b64, ""


def get_channels_for_event(session, b64):
    """Returns list of {name, category} dicts — sources line excluded."""
    try:
        r = session.post(
            AJAX_URL,
            data={"event_data": b64},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20
        )
        if r.status_code != 200 or not r.text.strip():
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        channels = []
        for item in soup.find_all(class_="channel-item"):
            name_el = item.find(class_="channel-name")
            cat_el  = item.find(class_="channel-category")
            # Deliberately skip channel-sources
            if name_el:
                channels.append({
                    "name":     name_el.get_text(strip=True),
                    "category": cat_el.get_text(strip=True) if cat_el else ""
                })
        return channels
    except Exception:
        return []


def extract_event_grid(soup, session):
    events = []
    current_sport = "Other"
    for el in soup.find_all(["h2", "div"]):
        if el.name == "h2":
            current_sport = el.get_text(strip=True)
            # Strip leading emoji from sport name for clean storage
            current_sport = re.sub(r'^[\U00010000-\U0010ffff\U00002600-\U000027BF\s]+', '', current_sport).strip()
            continue
        if "event-item" not in el.get("class", []):
            continue
        onclick = el.get("onclick", "")
        m = re.search(r'loadEventChannels\(\s*\d+\s*,\s*["\'](.+?)["\']\s*\)', onclick)
        if not m:
            continue
        b64 = m.group(1)
        event_name, event_dt = decode_event_data(b64)
        display_text = el.get_text(strip=True)
        time_match = re.match(r"(\d{2}:\d{2})\s*-\s*(.*)", display_text)
        event_time  = time_match.group(1) if time_match else ""
        event_label = time_match.group(2).strip() if time_match else display_text

        channels = get_channels_for_event(session, b64)
        time.sleep(0.15)

        events.append({
            "sport":    current_sport,
            "time":     event_time,
            "name":     event_label,
            "datetime": event_dt,
            "channels": channels   # [{name, category}, ...]
        })
    return events



def extract_live_events(soup):
    """
    Parses the le-section-title / le-date-header / le-event-row structure.
    Returns a list of sections, each with a title, and entries that are either
    date headers or fixture rows.
    e.g. [
      { "section": "World Cup", "entries": [
          { "type": "date", "text": "Thursday 11/06/2026" },
          { "type": "fixture", "text": "World Cup 01 - 20:00 UK - Group A: Mexico v South Africa" },
          ...
      ]},
      ...
    ]
    """
    sections = []
    current_section = None

    for el in soup.find_all(["div", "style"]):
        classes = el.get("class", [])

        if "le-section-title" in classes:
            title = el.get_text(strip=True)
            current_section = {"section": title, "entries": []}
            sections.append(current_section)

        elif "le-date-header" in classes:
            if current_section is not None:
                current_section["entries"].append({
                    "type": "date",
                    "text": el.get_text(strip=True)
                })

        elif "le-event-row" in classes:
            if current_section is not None:
                line = el.get_text(strip=True)
                # Strip non-UK times
                line = re.sub(r'\s*//\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{2}/\d{2}.*$', '', line).strip()
                line = re.sub(r'(\d+:\d+(?:am|pm)?)\s+UK\b', r'\1', line, flags=re.I).strip()
                current_section["entries"].append({
                    "type": "fixture",
                    "text": line
                })

    # Filter out sections with no fixture entries
    sections = [s for s in sections if any(e["type"] == "fixture" for e in s["entries"])]
    return sections

def scrape_category(session, cat):
    url = LOADER_URL + "?file=" + quote(cat["filename"])
    try:
        r = session.get(url, timeout=45)
    except requests.exceptions.Timeout:
        return {"type":"plain","fixtures":[],"sections":[],"events":[],"last_updated":"","status":"timeout"}
    except requests.exceptions.RequestException:
        return {"type":"plain","fixtures":[],"sections":[],"events":[],"last_updated":"","status":"error"}

    if r.status_code == 500:
        return {"type":"plain","fixtures":[],"sections":[],"events":[],"last_updated":"","status":"unavailable"}
    if r.status_code != 200:
        return {"type":"plain","fixtures":[],"sections":[],"events":[],"last_updated":"","status":f"http_{r.status_code}"}

    soup = BeautifulSoup(r.text, "html.parser")
    for el in soup.find_all(["script","style"]): el.decompose()

    # Detect live-events format (le-section-title / le-date-header / le-event-row)
    if soup.find("div", class_="le-section-title"):
        sections = extract_live_events(soup)
        total = sum(len([e for e in s["entries"] if e["type"]=="fixture"]) for s in sections)
        print(f" [live-events, {total} fixtures]", end=" ", flush=True)
        return {"type":"live","fixtures":[],"sections":sections,"events":[],"last_updated":"","status":"ok"}

    event_items = [el for el in soup.find_all("div", class_="event-item") if el.get("onclick","")]
    if event_items:
        print(f" [event-grid, {len(event_items)} events]", end=" ", flush=True)
        events = extract_event_grid(soup, session)
        return {"type":"events","fixtures":[],"sections":[],"events":events,"last_updated":"","status":"ok"}

    text = soup.get_text(separator="\n")
    fixtures, last_updated = extract_plain_fixtures(text)
    return {"type":"plain","fixtures":fixtures,"sections":[],"events":[],"last_updated":last_updated,"status":"ok"}


def main():
    session = make_session()
    login(session)
    categories = get_categories(session)
    if not categories:
        print("ERROR: No categories found."); sys.exit(1)

    session.get(FIXTURES_URL, timeout=30)

    print(f"[3/4] Scraping {len(categories)} categories...")
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "categories": []
    }

    for cat in categories:
        print(f"      {cat['name']:<30}", end=" ", flush=True)
        data = scrape_category(session, cat)
        status = data.get("status","ok")
        if status == "ok":
            n = len(data["events"]) if data["type"]=="events" else len(data["fixtures"])
            print(f"{n} {'events' if data['type']=='events' else 'fixtures'}"
                  + (f"  [{data['last_updated']}]" if data["last_updated"] else ""))
        else:
            print({"timeout":"TIMEOUT","unavailable":"UNAVAILABLE (500)","error":"ERROR"}.get(status, status))

        output["categories"].append({
            "name":         cat["name"],
            "type":         data["type"],
            "last_updated": data["last_updated"],
            "status":       status,
            "fixtures":     data["fixtures"],
            "sections":     data.get("sections", []),
            "events":       data["events"],
        })

    print(f"\n[4/4] Writing fixtures.json...")
    with open("fixtures.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_f = sum(len(c["fixtures"]) for c in output["categories"])
    total_l = sum(sum(len([e for e in s["entries"] if e["type"]=="fixture"]) for s in c.get("sections",[])) for c in output["categories"])
    total_e = sum(len(c["events"])   for c in output["categories"])
    print(f"✓ Done — {total_f} plain + {total_l} live-section + {total_e} event-grid fixtures across {len(output['categories'])} categories")


if __name__ == "__main__":
    main()
