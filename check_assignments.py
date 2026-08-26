#!/usr/bin/env python3
"""
Enago Hub assignment watcher.

Logs into hub.enago.com/experts, checks the assignments listing, and sends a
push notification (via ntfy.io) whenever a NEW assignment appears that wasn't
seen on the previous run.

State (the list of assignment IDs/titles already seen) is stored in
seen_assignments.json, which this script updates on every run. The GitHub
Actions workflow commits that file back to the repo so state persists
between scheduled runs.

REQUIRED SETUP (see README.md for full details):
  1. Fill in LOGIN_URL / ASSIGNMENTS_URL if they differ from the defaults.
  2. Fill in the login form field names (see LOGIN FORM section below).
  3. Fill in how to parse individual assignments from the page (see
     PARSE ASSIGNMENTS section below) - this is the one part you need to
     customize by inspecting the real page in your browser, since it's
     behind a login I can't see.
  4. Set these as GitHub Actions secrets in your repo:
       ENAGO_EMAIL       - your login email
       ENAGO_PASSWORD    - your login password
       NTFY_TOPIC        - a secret topic name for ntfy.io (see README)
"""

import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LOGIN_URL = "https://hub.enago.com/experts/login"
ASSIGNMENTS_URL = "https://hub.enago.com/experts"  # update if assignments live at a different path once logged in

STATE_FILE = Path(__file__).parent / "seen_assignments.json"

EMAIL = os.environ.get("ENAGO_EMAIL")
PASSWORD = os.environ.get("ENAGO_PASSWORD")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; AssignmentWatcher/1.0)"})


def log_in():
    """Log into the Enago freelancer portal."""
    resp = session.get(LOGIN_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # --- LOGIN FORM: this site looks like an Odoo portal, which usually
    # includes a hidden CSRF token field on the login form. Adjust the
    # field names below to match what you see in the page source
    # (right-click the login form -> Inspect -> look at <input> names).
    csrf_input = soup.find("input", {"name": "csrf_token"})
    csrf_token = csrf_input["value"] if csrf_input else None

    payload = {
        "login": EMAIL,       # confirmed: matches the real form's field name
        "password": PASSWORD,  # not yet confirmed - if login fails, check this field's actual name via Inspect
        "redirect": "/experts",  # hidden field present on the real login form
    }
    if csrf_token:
        payload["csrf_token"] = csrf_token

    login_resp = session.post(
        LOGIN_URL,
        data=payload,
        headers={
            "Referer": LOGIN_URL,
            "Origin": "https://hub.enago.com",
        },
        timeout=30,
    )
    login_resp.raise_for_status()

    # Safe diagnostics - no credentials are printed, just status/URL info
    # to help pinpoint the cause if login still fails.
    print(f"[debug] login POST status: {login_resp.status_code}")
    print(f"[debug] final URL after login: {login_resp.url}")

    if "login" in login_resp.url.lower():
        page_text = login_resp.text.lower()
        if "wrong login" in page_text or "invalid" in page_text or "incorrect" in page_text:
            raise RuntimeError(
                "Login failed: the site reported invalid credentials. "
                "Double-check the ENAGO_EMAIL / ENAGO_PASSWORD secrets for typos "
                "or accidental extra spaces/newlines when they were pasted in."
            )
        raise RuntimeError(
            "Login appears to have failed, but no 'invalid credentials' message "
            "was detected on the returned page - this may be a CSRF/session issue "
            "rather than wrong credentials. Share the next run's debug output."
        )


NO_ASSIGNMENTS_TEXT = "No Assignment Found"  # literal text the dashboard shows when the New ASN tab is empty
HEADER_MARKER = "ASN Code"  # text that identifies the New ASN table's header row


def fetch_assignments():
    """Fetch and parse the current list of 'New ASN' assignments."""
    resp = session.get(ASSIGNMENTS_URL, timeout=30)
    resp.raise_for_status()
    page_text = resp.text
    soup = BeautifulSoup(page_text, "html.parser")

    # Find the "New ASN" table by its header text rather than a CSS class,
    # since headers ("ASN Code", "Service", "Subject Area", ...) are much
    # less likely to change than internal class names.
    target_table = None
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True)
        if HEADER_MARKER in header_text:
            target_table = table
            break

    if target_table is None:
        # This most likely means the assignments table is loaded via
        # JavaScript after the initial page load, so a plain HTTP request
        # never sees it. If you hit this, tell Claude - the fix is to swap
        # this script's fetching step for a headless browser (Playwright)
        # that waits for the table to render before reading the page.
        raise RuntimeError(
            "Could not find the New ASN table in the page. The assignments "
            "list may be loaded via JavaScript rather than present in the "
            "raw HTML - a headless-browser fetch step would be needed instead."
        )

    body_text = target_table.get_text(" ", strip=True)
    assignments = {}

    if NO_ASSIGNMENTS_TEXT in body_text:
        return assignments  # empty - nothing currently posted

    # Pull header column names so each row's cells can be labeled correctly
    # even if the column order ever changes.
    header_cells = [th.get_text(strip=True) for th in target_table.find_all("th")]

    rows = target_table.find_all("tr")[1:]  # skip header row
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells or NO_ASSIGNMENTS_TEXT in " ".join(cells):
            continue

        row_data = dict(zip(header_cells, cells)) if header_cells else {"raw": " | ".join(cells)}
        asn_code = row_data.get("ASN Code") or cells[0]
        summary = ", ".join(f"{k}: {v}" for k, v in row_data.items() if v)

        assignments[asn_code] = summary

    return assignments


def load_seen():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_seen(assignments):
    STATE_FILE.write_text(json.dumps(assignments, indent=2, ensure_ascii=False))


def notify(title, message):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set - skipping notification. Message was:")
        print(f"  {title}: {message}")
        return
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "high",
            "Tags": "bell",
        },
        timeout=15,
    )


def main():
    if not EMAIL or not PASSWORD:
        print("ERROR: ENAGO_EMAIL / ENAGO_PASSWORD environment variables not set.", file=sys.stderr)
        sys.exit(1)

    log_in()
    current = fetch_assignments()
    seen = load_seen()

    new_ids = [aid for aid in current if aid not in seen]

    if new_ids:
        for aid in new_ids:
            notify("New Enago assignment", current[aid])
        print(f"Sent {len(new_ids)} notification(s) for new assignment(s).")
    else:
        print("No new assignments.")

    save_seen(current)


if __name__ == "__main__":
    main()

