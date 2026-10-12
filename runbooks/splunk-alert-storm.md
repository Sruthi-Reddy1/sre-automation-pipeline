# Runbook — Splunk alert storm

**Severity:** P2 — operational noise risk  
**Team:** Observability SRE  
**Last updated:** 2024-01-15  

---

## Trigger condition
More than 10 Splunk alerts fire within a 5-minute window
OR PagerDuty shows more than 5 simultaneous pages from
the Splunk integration.

## Impact
On-call engineer overwhelmed with noise. Real P1 incidents
may be missed. Alert fatigue risk. Potential SLO breach if
root cause is a genuine widespread outage.

---

## Triage steps

**Step 1 — Do NOT acknowledge all alerts blindly**
First identify which searches are firing most:
index=_audit action=alert_fired earliest=-10m
| stats count by savedsearch_name
| sort -count

**Step 2 — Identify if one source is causing the storm**
index=<main_index> earliest=-10m
| stats count by host, sourcetype
| sort -count
Look for a single host or sourcetype generating
massive volume.

**Step 3 — Check for Splunk forwarder restart loop**
```bash
# On affected host
systemctl status SplunkForwarder

# Check forwarder logs
tail -100 /opt/splunkforwarder/var/log/splunk/splunkd.log \
  | grep -E "ERROR|WARN|restart"
```

**Step 4 — Check if genuine widespread outage**
Check all three simultaneously:
- AWS status page: status.aws.amazon.com
- Dynatrace problem cards: look for new problems
- CloudWatch dashboards: check error rates

**Step 5 — Suppress noisy searches temporarily**
Splunk UI:
Settings → Searches, reports, and alerts
→ Find noisy search → Edit → Alert throttling
→ Suppress for 30 minutes
Do this only while investigating root cause.

**Step 6 — Open one parent ServiceNow incident**
Short description: Splunk alert storm — [date/time]
Priority: P2
Assignment: Observability SRE
Link all PagerDuty pages to this one ticket.
Do NOT open separate tickets per alert.

**Step 7 — Restart forwarder if root cause**
```bash
sudo systemctl restart SplunkForwarder

# Monitor ingestion recovery
index=_internal source=*metrics.log earliest=-5m
| timechart span=1m sum(kb) by host
```

**Step 8 — Validate storm has cleared**
index=_audit action=alert_fired earliest=-5m
| stats count by savedsearch_name
Count should be back to normal baseline.
Update ServiceNow ticket with resolution steps.

---

## Escalation path
- Storm caused by genuine outage → escalate to
  relevant team based on affected system
- Forwarder restart loop not resolving → escalate
  to Splunk admin team
- Storm lasting more than 20 min → open bridge call

## Post-storm action
Mandatory alert audit within 48 hours:
- Review all triggered alerts
- Identify valid vs noise ratio
- Update thresholds and suppression logic
- Present findings in next SRE team review

## Root cause categories
- Splunk forwarder restart loop flooding index
- Single noisy host generating excessive logs
- Alert thresholds set too low
- Genuine widespread outage triggering all monitors
- Bad deployment pushing error logs at high volume
