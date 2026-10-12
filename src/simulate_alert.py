import argparse, requests, json

BASE_URL = "http://localhost:8080"
SCENARIOS = {
    "alb": {
        "alert_name": "alb_502_error_spike",
        "severity": "high",
        "ci": "prod-alb-api-gateway",
        "description": "ALB 502 error rate exceeded 5% threshold",
        "results_link": "https://splunk.example.com"
    },
    "oom": {
        "alert_name": "kubernetes_oomkill_detected",
        "severity": "critical",
        "ci": "prod-k8s-cluster-01",
        "description": "Pod OOMKilled restart count exceeded threshold",
        "results_link": "https://splunk.example.com"
    },
    "storm": {
        "alert_name": "splunk_alert_storm_detected",
        "severity": "medium",
        "ci": "prod-splunk-cluster",
        "description": "Alert storm detected — more than 10 alerts in 5 min",
        "results_link": "https://splunk.example.com"
    }
}

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", choices=["alb","oom","storm"], default="alb")
args = parser.parse_args()
payload = SCENARIOS[args.scenario]
print(f"\nSending {args.scenario.upper()} scenario:")
print(json.dumps(payload, indent=2))
try:
    resp = requests.post(
        f"{BASE_URL}/webhook/splunk",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    print(f"\nResponse ({resp.status_code}):")
    print(json.dumps(resp.json(), indent=2))
except requests.RequestException as e:
    print(f"Request failed: {e}")
