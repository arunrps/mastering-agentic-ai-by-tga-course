---
document_id: RB-CAT-000
title: Catalog Service — Triage and Escalation
document_type: runbook
service: catalog-service
status: current
supersedes: null
superseded_by: null
owner_team: catalog-discovery
access_level: operations
version: "1.7"
last_reviewed: 2025-11-18
---

# Catalog Service — Triage and Escalation

Scope: applies when an alert or an automated verdict names catalog-service, or an endpoint served
by catalog-service, as elevated against baseline. Classification only, not remediation. Classify
before checking. The four classes do not share a check set; running the wrong set wastes the
opening of an incident.

One warning first. This service is read-heavy and carries the highest request volume on the
platform. Latency here moves with volume as normal operation. An objective breach is therefore not
by itself evidence of a fault, and triage treating it as one spends the incident looking for
something that is not there.

## Symptoms

**Class 1 — errors elevated, latency at baseline.** The 5xx rate for the affected endpoint and
backend slice is above the declared objective while p95 stays inside it. Requests fail without
first becoming slow.

**Class 2 — latency elevated, errors at baseline.** p95, usually p99 also, is above the declared
objective. The 5xx rate is at or near baseline. Work completes, but late. Most alerts on this
service land here and most are capacity, not fault.

**Class 3 — both elevated.** Both series are over objective in the same window.

**Class 4 — neither elevated, trouble reported.** A report arrives from support, a partner or an
engineer, and neither series crosses the floor for the slice named. Search index lag presents
here: stale results return successfully and fast, so neither series moves.

Declared objectives and the minimum evidence floor are in POL-SLO-001; do not re-derive them from
the telemetry being triaged.

## Discriminating checks

**Capacity against fault, before anything else.** Compare request volume for the slice over the
same window as the latency rise. If latency scales with volume — rising as volume rises, receding
as it recedes — the question is capacity. If latency rose while volume stayed flat or fell, it is
a fault. This runs first because it changes which checks below are worth running: the same p95
breach means different things on either side of it. PM-2026-009 covers the capacity shape.

**Class 4, index lag.** Establish whether the complaint is about results being old rather than
missing or malformed. Old-but-coherent results indicate the served index is behind; missing or
malformed indicates something else and is escalated. Neither moves 5xx or latency, so a clean
aggregate is expected here and is not evidence against the report.

**Class 1 against class 2.** Look at how long the failing requests took. Errors returning quickly
indicate rejection before the expensive work is attempted. Errors returning near a timeout ceiling
are slow work that ran out of budget, and are re-classified.

**Class 1 against class 3.** Confirm whether p95 crossed at all, and if so whether before or after
the error rate. If p95 stayed inside the objective throughout, this is class 1 — the unusual case
here, and more likely a genuine fault than the far commoner class 2.

**Class 2 against class 3.** Confirm the error count clears the minimum evidence floor. A small
absolute number of 5xx on a low-volume slice does not promote class 2 to class 3. Threshold rule,
not a judgement. Volume is high here so the floor clears easily; that is not significance.

**Ordering within class 3.** Latency rising ahead of errors is a recognised pattern and is
recorded when observed: a caller holding a fixed timeout sees no errors from a slowing callee
until time-in-flight crosses that deadline.

**Sibling endpoint corroboration, all classes.** Determine whether another endpoint on the same
backend degraded in the same window. If it did, the evidence points at the shared backend rather
than at one endpoint's path, and triage proceeds at service level. If it did not, the endpoint's
own path is the first place to look. Here the positive case is weaker than elsewhere: a traffic
surge raises volume across both endpoints at once, so simultaneous degradation is the expected
shape of a capacity event, not a shared-fault signal. Run the capacity check before reading
corroboration as evidence. Mappings are in CAT-DEP-001, which may drift from observed traffic.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution and is not recorded as one.

## Escalation

Escalate to catalog-discovery. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- the capacity check is inconclusive because volume data for the slice is unavailable;
- index lag is confirmed but the index age cannot be established from the gateway;
- the checks above are exhausted and the class is still unclear;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  classification and evidence gathered.

Record the class, the slice, the baseline and the capacity-check result at escalation time.
Escalations omitting the capacity result are sent back.


## Related documents

- RB-CAT-001 — /products investigation
- RB-CAT-002 — /search investigation
- PM-2026-009 — capacity saturation during a traffic surge
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
