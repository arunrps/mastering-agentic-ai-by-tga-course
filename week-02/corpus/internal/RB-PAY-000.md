---
document_id: RB-PAY-000
title: Payment Service — Triage and Escalation
document_type: runbook
service: payment-service
status: current
supersedes: RB-PAY-000-ARCHIVED
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "3.1"
last_reviewed: 2026-06-14
---

# Payment Service — Triage and Escalation

Scope: applies when an alert or an automated verdict names payment-service, or an endpoint served
by payment-service, as elevated against baseline. Classification only, not remediation. Classify
before checking. The four classes do not share a check set; running the wrong set wastes the
opening of an incident.

## Symptoms

**Class 1 — errors elevated, latency at baseline.** The 5xx rate for the affected endpoint and
backend slice is above the declared objective while p95 remains inside it. Requests fail without
first becoming slow.

**Class 2 — latency elevated, errors at baseline.** p95, usually p99 also, is above the declared
objective. The 5xx rate is at or near baseline. Work is completing, but late.

**Class 3 — both elevated.** Both series are over objective in the same window.

**Class 4 — neither elevated, trouble reported.** A report arrives from support, a partner or an
engineer, and neither series crosses the floor for the slice named. This class is not "no
incident". It is "not visible in the aggregate the detector examines", which is different.

Declared objectives and the minimum evidence floor are in POL-SLO-001. Do not re-derive them from
the telemetry being triaged.

## Discriminating checks

**Class 1 against class 2.** Look at how long the failing requests took. Errors that
return quickly indicate the request is rejected before the expensive work is attempted — input
rejection, an upstream refusal, or a deliberate fast-fail path. Errors returning at or close to a
timeout ceiling are slow work that ran out of budget, and are re-classified as class 2 or class 3
rather than treated as a failure mode of their own.

**Class 1 against class 3.** Confirm whether p95 crossed at all, and if so whether before or after
the error rate. If p95 stayed inside the objective for the whole window this is class 1, and the
latency checks below do not apply.

**Class 2 against class 3.** Confirm the error count clears the minimum evidence floor. A small
absolute number of 5xx on a low-volume slice does not promote class 2 to class 3. This is a
threshold rule, not a judgement, for the reasons in POL-SLO-001.

**Ordering within class 3.** Latency rising ahead of errors is a recognised pattern and should be
recorded in the incident channel when observed. The reason is mechanical: a caller holds a fixed
timeout, so a callee that slows gradually produces no errors until time-in-flight crosses that
deadline, after which the error rate rises steeply. The error curve is a lagged, thresholded
function of the latency curve, and the gap between the two onsets is roughly the headroom between
normal response time and the caller's timeout. The reverse ordering — errors first, latency after —
is a different pattern and is noted as such: cheap failures that are retried add load, and the
added load can produce latency as a consequence rather than a cause.

**Any of classes 1 to 3 against class 4.** Establish whether the reported scope is narrower than
the aggregate: a single tenant, client build or region can be degraded without moving a
slice-level series. Establish also whether the complaint concerns correctness rather than
availability — an operation that completed but produced the wrong outcome is not observable in 5xx
or latency at all. Class 4 reports surviving both questions are escalated, not closed.

**Sibling endpoint corroboration, all classes.** Determine whether another endpoint on the same
backend degraded in the same window. If it did, the evidence points at the shared backend rather
than at one endpoint's path, and triage proceeds at service level. If it did not, the endpoint's
own path is the first place to look. The negative case is weaker than the positive and is not
exoneration of the backend: check the sibling's request volume first, because a low-volume sibling
can carry the same fault below the evidence floor and appear healthy. Endpoint-to-backend mappings
are in CAT-DEP-001, which reflects declared topology and may drift from observed traffic.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate to
the owning team rather than proceeding without it. Correlation with a change window is not
attribution and must not be recorded as one.

## Escalation

Escalate to payments-platform. Contacts and business hours are in CAT-OWN-001. Severity
assignment, blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- the checks above are exhausted and the class is still unclear;
- a class 3 condition is sustained past fifteen minutes with no class agreed;
- a class 4 report survives the scope and correctness questions;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  classification and the evidence gathered; do not characterise internals from the gateway view.

Record the class, the slice, the baseline used and the corroboration result at escalation time.
Escalations omitting the baseline are routinely sent back.

## Related documents

- RB-PAY-001 — /checkout investigation
- RB-PAY-002 — /refunds investigation; shared-backend corroboration at endpoint level
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership matrix
- CAT-DEP-001 — endpoint dependency map
