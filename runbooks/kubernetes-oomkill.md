# Runbook — Kubernetes OOMKill

**Severity:** P2/P3 — depends on pod criticality  
**Team:** Platform SRE  
**Last updated:** 2024-01-15  

---

## Trigger condition
Pod restart count > 3 in 10 minutes with reason OOMKilled
OR Dynatrace problem card fires for service availability
drop on a Kubernetes-hosted service.

## Impact
Service degradation or intermittent errors for users of
the affected microservice. Risk of cascading failures if
pod is part of a critical path.

---

## Triage steps

**Step 1 — Identify affected pod**
```bash
kubectl get pods -n <namespace> \
  --sort-by='.status.containerStatuses[0].restartCount'
```
Find pods with highest restart count.

**Step 2 — Confirm OOMKill**
```bash
kubectl describe pod <pod-name> -n <namespace>
```
Look for:
Last State: Terminated
Reason: OOMKilled
Exit Code: 137

**Step 3 — Check memory limits vs requests**
```bash
kubectl get pod <pod-name> -n <namespace> \
  -o jsonpath='{.spec.containers[*].resources}'
```
Compare limits to actual usage.

**Step 4 — Check node memory pressure**
```bash
kubectl describe node <node-name> | grep -A5 "Conditions"
```
Look for `MemoryPressure=True`.

**Step 5 — Pull memory usage from Splunk**
index=kubernetes_metrics earliest=-30m
metric_name=container.memory.usage
pod_name=<pod-name>
| timechart avg(value) by pod_name
Identify gradual leak vs sudden spike pattern.

**Step 6 — Immediate mitigation**
```bash
# Increase memory limit temporarily
# Confirm with App team first
kubectl set resources deployment <name> \
  -n <namespace> \
  --limits=memory=<new-value>
```

**Step 7 — If node under pressure**
```bash
# Cordon node — stop new pods scheduling here
kubectl cordon <node-name>

# Drain node — move existing pods elsewhere
kubectl drain <node-name> --ignore-daemonsets
```

**Step 8 — Validate pod is stable**
```bash
kubectl get pods -n <namespace> -w
```
Watch for 5 minutes. No new restarts = stable.
Update ServiceNow ticket with resolution steps.

---

## Escalation path
- Memory leak suspected → escalate to App team for heap dump
- All nodes under pressure → escalate to Platform lead
- Unresolved at 20 min mark → open bridge call

## RCA trigger
Pod restarted > 5 times OR service unavailable > 10 min
→ mandatory RCA within 24 hours.

## Root cause categories
- Memory leak in application code
- Memory limits set too low for actual usage
- Traffic spike beyond expected load
- Node resource contention from noisy neighbour pod

## Long term fix
App team to review heap dumps and set proper memory
limits based on actual p99 usage plus 20% headroom.
Add VPA (Vertical Pod Autoscaler) recommendation.
