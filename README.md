# SRE Automation Pipeline

> Splunk → Python → ServiceNow triage automation for Automation & Triage Engineers.

---

## About
This repo automates incident triage — Splunk detects anomalies, Python processes alerts, ServiceNow creates incidents automatically.

## Tech stack
| Tool | Purpose |
|---|---|
| Splunk | Alert detection via SPL saved searches |
| Python | Triage automation engine |
| ServiceNow | Incident creation via REST API |
| Slack | On-call notification |
| GitHub Actions | CI/CD and auto-deploy |

## Setup
1. Clone the repo
2. Copy `.env.example` to `.env` and fill in credentials
3. Run `pip install -r requirements.txt`
4. Set `DRY_RUN=true` for safe testing


## Project structure
src/           Python automation scripts
tests/         Unit tests  
runbooks/      Triage runbooks
splunk_queries/ SPL alert searches

## Author
zero-toil — Senior DevOps / SRE Engineer