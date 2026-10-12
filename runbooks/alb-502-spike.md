# Runbook — ALB 502 error spike

**Severity:** P2 — high  
**Team:** Network SRE  
**Last updated:** 2024-01-15  

---

## Trigger condition
ALB HTTP 502 error rate exceeds 5% over a 5-minute window
OR Splunk alert fires on `alb_502_error_spike` saved search.

## Impact
End users receiving gateway errors. Potential revenue
and SLO impact depending on affected target group.

---

## Triage steps

**Step 1 — Create ServiceNow incident**
CI: ALB name
Priority: P2
Assignment Group: Network SRE
Short description: ALB 502 spike — [target group name]


**Step 2 — Check ALB target group health**
```bash
aws elbv2 describe-target-health \
  --target-group-arn <ARN>
```
Look for targets showing `unhealthy` status.

**Step 3 — Check ALB access logs in Splunk**
index=aws_alb elb_status_code=502
| stats count by backend_ip, request_url
| sort -count
Identify which backend IPs and endpoints are failing.

**Step 4 — Check app process on unhealthy target**
```bash
# For EC2 target
systemctl status <app-name>

# For Kubernetes target
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
```

**Step 5 — Check security group allows ALB traffic**
```bash
aws ec2 describe-security-groups \
  --group-ids <SG-ID>
```
Confirm inbound rule allows ALB on health check port.

**Step 6 — Check app logs for errors**
```bash
journalctl -u <app-name> --since "10 min ago" \
  | grep -E "ERROR|FATAL|OOM"
```

**Step 7 — Restart if app crashed**
```bash
# EC2
systemctl restart <app-name>

# Kubernetes
kubectl rollout restart deployment/<name> -n <namespace>
```
Monitor target health for 2 minutes after restart.

**Step 8 — Validate recovery**
```bash
aws elbv2 describe-target-health --target-group-arn <ARN>
```
All targets show `healthy`. Splunk 502 rate drops to baseline.
Update ServiceNow ticket with resolution steps.

---

## Escalation path
- Targets unhealthy after restart → escalate to App team lead
- Security group root cause → escalate to Cloud Infrastructure
- Unresolved at 15 min mark → open bridge call

## RCA trigger
Incident duration > 30 min OR user-impacting > 5 min
→ mandatory RCA within 24 hours.

## Root cause categories
- App crash or OOM on target instance
- Security group misconfiguration
- Health check path changed without ALB update
- Deployment pushed bad build to targets
