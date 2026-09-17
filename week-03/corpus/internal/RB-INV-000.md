---
document_id: RB-INV-000
title: Inventory Service — Triage and Escalation
document_type: runbook
service: inventory-service
status: current
supersedes: null
superseded_by: null
owner_team: fulfilment-core
access_level: operations
version: "2.2"
last_reviewed: 2026-04-30
---

# Inventory Service — Triage and Escalation

Scope: applies when an alert or an automated verdict names inventory-service, or an endpoint
served by inventory-service, as elevated against baseline. Classification only, not remediation.
Classify before checking. The four classes do not share a check set; running the wrong set wastes
the opening of an incident.

One warning first. This service has a failure mode the two series do not detect at all, and it is
not rare. If the report came from a person rather than an alert, read class 4 first. Triage
following the class order will close real incidents.

## Symptoms

**Class 1 — errors elevated, latency at baseline.** The 5xx rate for the affected endpoint and
backend slice is above the declared objective while p95 stays inside it. Requests fail without
first becoming slow.

**Class 2 — latency elevated, errors at baseline.** p95, usually p99 also, is above the declared
objective. The 5xx rate is at or near baseline. Work completes, but late. Stock lookup that runs
long without failing lands here.

**Class 3 — both elevated.** Both series are over objective in the same window. Stock lookups
timing out rather than merely running long land here.

**Class 4 — neither elevated, trouble reported.** A report arrives from support, a partner or an
engineer, and neither series crosses the floor for the slice named. Here class 4 is a leading
class, not a residual one. Cart contents disagreeing with what the order path sees, and a cache
serving values that are old rather than wrong, both present here and produce no signal in either
series.

Declared objectives and the minimum evidence floor are in POL-SLO-001; do not re-derive them from
the telemetry being triaged.

## Discriminating checks

**Class 4 first.** Establish whether the complaint is a divergence — the same customer and item
reported differently by the cart view and by the order path. Divergence is not scoped to a tenant,
client build or region, so narrowing the scope returns nothing, and that must not be read as
absence of an incident. Do not decide which view is correct from the gateway. Escalate on
disagreement.

**Stale against wrong.** A cached response is fast and successful; speed is not health on this
service. Discriminate staleness from a fault by whether the reported value matches a previous
known state: old-but-coherent indicates the read path is serving cache, incoherent indicates
something else and is escalated. Neither moves 5xx or latency.

**Class 1 against class 2.** Look at how long the failing requests took. Errors returning quickly
indicate rejection before the expensive work is attempted. Errors returning at or
close to a timeout ceiling are slow work that ran out of budget, and are re-classified.

**Class 1 against class 3.** Confirm whether p95 crossed at all, and if so whether before or after
the error rate. If p95 stayed inside the objective throughout, this is class 1.

**Class 2 against class 3.** Confirm the error count clears the minimum evidence floor. A small
absolute number of 5xx on a low-volume slice does not promote class 2 to class 3. Threshold rule,
not a judgement.

**Ordering within class 3.** Latency rising ahead of errors is a recognised pattern and is
recorded when observed: a caller holding a fixed timeout sees no errors from a gradually slowing
callee until time-in-flight crosses that deadline.

**Sibling endpoint corroboration, all classes.** Determine whether another endpoint on the same
backend degraded in the same window. If it did, the evidence points at the shared backend rather
than at one endpoint's path, and triage proceeds at service level. If it did not, the endpoint's
own path is the first place to look. The negative case is not exoneration of the backend, and here
it is weaker than usual: the two endpoints exercise substantially different paths, so a fault in
one need not surface in the other. Check the sibling's request volume and path overlap before
treating a quiet sibling as a negative. Mappings are in CAT-DEP-001, which may drift from observed
traffic.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution and must not be recorded as one.

## Escalation

Escalate to fulfilment-core. Contacts and business hours are in CAT-OWN-001. Severity, blast-radius
thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- any divergence between the cart view and the order path is confirmed, at any class;
- staleness is confirmed but the age of the served value cannot be established from the gateway;
- the checks above are exhausted and the class is still unclear;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  classification and the evidence gathered.

Record the class, the slice, the baseline and the corroboration result at escalation time.
Divergence reports also record both observed values and the item identifier.
Escalations omitting the baseline are sent back.

## Related documents

- RB-INV-001 — /cart investigation
- RB-INV-002 — /orders investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
