"""
ServiceNow P1/P2 Incident Poller
Polls ServiceNow for open P1/P2 incidents and posts to Slack.
Topic: Python REST API automation / ChatOps
"""

import os
import json
import time
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SNOW_INSTANCE = os.getenv("SNOW_INSTANCE")
SNOW_USER     = os.getenv("SNOW_USER")
SNOW_PASS     = os.getenv("SNOW_PASS")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
DRY_RUN       = os.getenv("DRY_RUN", "true").lower() == "true"

POLL_INTERVAL = 300  # seconds — poll every 5 minutes
SEEN_FILE     = "seen_incidents.json"


def load_seen() -> set:
    """Load previously seen incident numbers from disk."""
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen(seen: set):
    """Persist seen incident numbers to disk."""
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def get_p1_p2_incidents() -> list:
    """
    Poll ServiceNow Table API for open P1 and P2 incidents.
    Returns list of incident dicts.
    """
    url = f"https://{SNOW_INSTANCE}/api/now/table/incident"
    params = {
        "sysparm_query": "priority IN 1,2^stateNOT IN 6,7",
        "sysparm_fields": "number,short_description,priority,"
                          "assigned_to,opened_at,cmdb_ci",
        "sysparm_limit": "50",
        "sysparm_display_value": "true",
    }
    try:
        resp = requests.get(
            url,
            params=params,
            auth=(SNOW_USER, SNOW_PASS),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except requests.RequestException as e:
        print(f"[ERROR] ServiceNow API call failed: {e}")
        return []


def format_slack_message(incident: dict) -> dict:
    """Format incident as a Slack attachment message."""
    priority    = incident.get("priority", "")
    number      = incident.get("number", "")
    description = incident.get("short_description", "")
    assignee    = incident.get("assigned_to", {}).get("display_value", "Unassigned")
    opened_at   = incident.get("opened_at", "")
    ci          = incident.get("cmdb_ci", {}).get("display_value", "Unknown")
    snow_url    = (
        f"https://{SNOW_INSTANCE}/nav_to.do?"
        f"uri=incident.do?sysparm_query=number={number}"
    )
    color = "#E24B4A" if priority == "1 - Critical" else "#EF9F27"

    return {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*:rotating_light: {number} — {priority}*\n"
                            f"*{description}*\n"
                            f"*CI:* {ci}\n"
                            f"*Assignee:* {assignee}\n"
                            f"*Opened:* {opened_at}"
                        )
                    }
                },
                {
                    "type": "actions",
                    "elements": [{
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View in ServiceNow"},
                        "url": snow_url
                    }]
                }
            ]
        }]
    }


def post_to_slack(incident: dict):
    """Post formatted incident alert to Slack webhook."""
    message = format_slack_message(incident)

    if DRY_RUN:
        print(f"[DRY-RUN] Would post to Slack: {incident['number']}")
        print(json.dumps(message, indent=2))
        return

    try:
        resp = requests.post(
            SLACK_WEBHOOK,
            json=message,
            timeout=10
        )
        resp.raise_for_status()
        print(f"[OK] Slack notification sent: {incident['number']}")
    except requests.RequestException as e:
        print(f"[ERROR] Slack post failed: {e}")


def run_once(seen: set) -> set:
    """Run one poll cycle — check for new P1/P2 incidents."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Polling ServiceNow...")
    incidents = get_p1_p2_incidents()
    print(f"Found {len(incidents)} open P1/P2 incidents")

    new_count = 0
    for incident in incidents:
        number = incident.get("number")
        if number not in seen:
            post_to_slack(incident)
            seen.add(number)
            new_count += 1

    print(f"Notified: {new_count} new incidents")
    save_seen(seen)
    return seen


def main():
    parser = argparse.ArgumentParser(
        description="Poll ServiceNow for P1/P2 incidents and alert Slack"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit instead of polling continuously"
    )
    args = parser.parse_args()

    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    print(f"ServiceNow Poller starting — mode: {mode}")

    seen = load_seen()

    if args.once:
        run_once(seen)
    else:
        while True:
            seen = run_once(seen)
            print(f"Next poll in {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
