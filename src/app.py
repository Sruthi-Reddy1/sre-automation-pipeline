"""
Triage Automation Engine
Topic: SRE Automation / AIOps / Event-Driven Incident Response
Stack: Python Flask, ServiceNow REST API, Slack Webhooks
"""

import os
import json
import hmac
import hashlib
import logging
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)
app = Flask(__name__)

SNOW_INSTANCE = os.getenv("SNOW_INSTANCE")
SNOW_USER     = os.getenv("SNOW_USER")
SNOW_PASS     = os.getenv("SNOW_PASS")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
SPLUNK_SECRET = os.getenv("SPLUNK_WEBHOOK_SECRET", "")
DRY_RUN       = os.getenv("DRY_RUN", "true").lower() == "true"

STORM_LIMIT     = 5
STORM_WINDOW    = 600
_incident_times = []

SEVERITY_MAP = {
    "critical": {"priority": "1", "urgency": "1", "impact": "1"},
    "high":     {"priority": "2", "urgency": "1", "impact": "2"},
    "medium":   {"priority": "3", "urgency": "2", "impact": "2"},
    "low":      {"priority": "4", "urgency": "3", "impact": "3"},
}

ASSIGNMENT_MAP = {
    "alb":        "Network SRE",
    "kubernetes": "Platform SRE",
    "splunk":     "Observability SRE",
    "database":   "Database SRE",
    "default":    "SRE On-Call",
}


def validate_splunk_signature(payload: bytes, signature: str) -> bool:
    if not SPLUNK_SECRET:
        return True
    expected = hmac.new(
        SPLUNK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.replace("sha256=", ""))


def is_storm_active() -> bool:
    global _incident_times
    now = time.time()
    _incident_times = [t for t in _incident_times if now - t < STORM_WINDOW]
    return len(_incident_times) >= STORM_LIMIT


def get_assignment_group(alert_name: str) -> str:
    name_lower = alert_name.lower()
    for keyword, group in ASSIGNMENT_MAP.items():
        if keyword in name_lower:
            return group
    return ASSIGNMENT_MAP["default"]


def check_duplicate_incident(ci_name: str, alert_name: str):
    url = f"https://{SNOW_INSTANCE}/api/now/table/incident"
    params = {
        "sysparm_query": (
            f"cmdb_ci.name={ci_name}"
            f"^short_descriptionCONTAINS{alert_name}"
            f"^stateNOT IN6,7"
        ),
        "sysparm_fields": "number,sys_id,opened_at",
        "sysparm_limit": "1",
    }
    try:
        resp = requests.get(
            url, params=params,
            auth=(SNOW_USER, SNOW_PASS),
            timeout=10
        )
        resp.raise_for_status()
        results = resp.json().get("result", [])
        if results:
            return results[0]["number"]
    except requests.RequestException as e:
        log.error("ServiceNow duplicate check failed: %s", e)
    return None


def create_snow_incident(payload: dict) -> dict:
    alert_name   = payload.get("alert_name", "Unknown Alert")
    severity     = payload.get("severity", "medium").lower()
    ci_name      = payload.get("ci", "Unknown CI")
    description  = payload.get("description", "Automated alert from Splunk")
    search_url   = payload.get("results_link", "")
    sev_fields   = SEVERITY_MAP.get(severity, SEVERITY_MAP["medium"])
    assign_group = get_assignment_group(alert_name)

    incident_body = {
        "short_description": f"[AUTO] {alert_name} -- {ci_name}",
        "description": (
            f"{description}\n\n"
            f"Splunk results: {search_url}\n"
            f"Auto-created: {datetime.now(timezone.utc).isoformat()}"
        ),
        "priority":         sev_fields["priority"],
        "urgency":          sev_fields["urgency"],
        "impact":           sev_fields["impact"],
        "assignment_group": assign_group,
        "cmdb_ci":          ci_name,
        "category":         "Software",
        "subcategory":      "Monitoring Alert",
        "caller_id":        "sre-automation",
    }

    if DRY_RUN:
        log.info("[DRY-RUN] Would create: %s", json.dumps(incident_body, indent=2))
        return {"number": "INC-DRYRUN", "sys_id": "dry-run-id", **incident_body}

    url = f"https://{SNOW_INSTANCE}/api/now/table/incident"
    resp = requests.post(
        url, json=incident_body,
        auth=(SNOW_USER, SNOW_PASS),
        headers={"Content-Type": "application/json"},
        timeout=15
    )
    resp.raise_for_status()
    result = resp.json()["result"]
    _incident_times.append(time.time())
    log.info("Created incident: %s", result["number"])
    return result


def post_slack_notification(incident: dict, payload: dict):
    if not SLACK_WEBHOOK:
        return
    severity  = payload.get("severity", "medium").lower()
    color_map = {
        "critical": "#E24B4A",
        "high":     "#EF9F27",
        "medium":   "#378ADD",
        "low":      "#639922"
    }
    color    = color_map.get(severity, "#888780")
    snow_url = (
        f"https://{SNOW_INSTANCE}/nav_to.do?"
        f"uri=incident.do?sysparm_query=number={incident['number']}"
    )
    message = {
        "attachments": [{
            "color": color,
            "text": (
                f"*Incident auto-created:* {incident['number']} | "
                f"{payload.get('alert_name')} | "
                f"CI: {payload.get('ci')} | "
                f"Severity: {severity.upper()} | "
                f"<{snow_url}|View in ServiceNow>"
            )
        }]
    }
    if DRY_RUN:
        log.info("[DRY-RUN] Would post Slack: %s", json.dumps(message))
        return
    try:
        requests.post(SLACK_WEBHOOK, json=message, timeout=10).raise_for_status()
        log.info("Slack sent for %s", incident["number"])
    except requests.RequestException as e:
        log.error("Slack failed: %s", e)


@app.route("/webhook/splunk", methods=["POST"])
def splunk_webhook():
    sig = request.headers.get("X-Splunk-Signature", "")
    if not validate_splunk_signature(request.data, sig):
        return jsonify({"error": "Invalid signature"}), 401

    try:
        payload = request.get_json(force=True)
        if not payload:
            raise ValueError("Empty payload")
    except Exception as e:
        return jsonify({"error": "Invalid JSON"}), 400

    alert_name = payload.get("alert_name", "")
    ci_name    = payload.get("ci", "")
    log.info("Alert: %s | CI: %s | Severity: %s",
             alert_name, ci_name, payload.get("severity"))

    if is_storm_active():
        return jsonify({"status": "suppressed", "reason": "storm_protection"}), 429

    existing = check_duplicate_incident(ci_name, alert_name)
    if existing:
        return jsonify({"status": "duplicate", "existing_incident": existing}), 200

    try:
        incident = create_snow_incident(payload)
    except requests.RequestException as e:
        return jsonify({"error": "ServiceNow failure", "detail": str(e)}), 502

    post_slack_notification(incident, payload)
    return jsonify({
        "status": "created",
        "incident_number": incident["number"],
        "dry_run": DRY_RUN
    }), 201


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "dry_run": DRY_RUN, "version": "1.0.0"}), 200


if __name__ == "__main__":
    log.info("Starting — mode: %s", "DRY-RUN" if DRY_RUN else "LIVE")
    app.run(host="0.0.0.0", port=8080)
