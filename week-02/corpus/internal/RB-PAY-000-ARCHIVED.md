---
document_id: RB-PAY-000-ARCHIVED
title: Payment Service — Triage and Escalation
document_type: runbook
service: payment-service
status: superseded
supersedes: null
superseded_by: RB-PAY-000
owner_team: payments-platform
access_level: operations
version: "2.4"
last_reviewed: 2025-03-02
---

# Payment Service — Triage and Escalation

Scope: applies when an alert names payment-service, or an endpoint served by payment-service, as
elevated against baseline. Classification only, not remediation. Classify before checking. The
three classes do not share a check set; running the wrong set wastes the opening of an incident.

Declared objectives are in POL-SLO-001. The evidence minimum below governs whether a slice is
assessed at all and takes precedence over anything stated elsewhere.

## Symptoms

**Class 1 — errors elevated, latency at baseline.** The 5xx rate for the affected endpoint and
backend slice is above the declared objective while p95 stays inside it. Requests fail without
first becoming slow.

**Class 2 — latency elevated, errors at baseline.** p95, usually p99 also, is above the declared
objective. The 5xx rate is at or near baseline. Work completes, but late.

**Class 3 — both elevated.** Both series are over objective in the same window.

A slice that does not reach the minimum below is not elevated and requires no further action.

## Discriminating checks

**Evidence minimum.** Confirm the slice has produced at least five failed requests within a single
five-minute bucket before classifying. A slice below that minimum is recorded as not elevated. No
comparison against a baseline multiplier is required at this stage; the failure count is
sufficient on its own and the baseline is used only for reporting.

**Class 1 against class 2.** Look at how long the failing requests took. Errors returning quickly
indicate rejection before the expensive work is attempted — input rejection, an upstream refusal,
or a deliberate fast-fail path. Errors returning at or close to a timeout ceiling are slow work
that ran out of budget, and are re-classified as class 2 or class 3 rather than treated as a
failure mode of their own.

**Class 1 against class 3.** Confirm whether p95 crossed at all, and if so whether before or after
the error rate. If p95 stayed inside the objective for the whole window this is class 1, and the
latency checks do not apply.

**Class 2 against class 3.** Confirm the failure count clears the minimum above. A small absolute
number of 5xx on a low-volume slice does not promote class 2 to class 3.

**Ordering within class 3.** Latency rising ahead of errors is a recognised pattern and should be
recorded in the incident channel when observed. The reason is mechanical: a caller holds a fixed
timeout, so a callee that slows gradually produces no errors until time-in-flight crosses that
deadline, after which the error rate rises steeply.

**Sibling endpoint corroboration.** Determine whether another endpoint on the same backend
degraded in the same window. If it did, the evidence points at the shared backend rather than at
one endpoint's path, and triage proceeds at service level. Endpoint-to-backend mappings are in
CAT-DEP-001.

**Dependency health.** Where the class is established and the endpoint's own path has been ruled
out, verify the health of the shared platform components the backend depends on — the gateway path
and the authentication path — before escalating further. Neither is owned by payments-platform and
a degradation in either will present at this backend as though it originated here. Where a shared
component is implicated, the escalation goes to that component's owning team and not to
payments-platform, and CAT-OWN-001 has the routing.

**Change correlation.** Establish whether a deployment to payment-service falls within the thirty
minutes preceding the onset. Where one does, record the deployment as the cause of the degradation
and proceed to rollback under POL-DEPLOY-001. Where no deployment falls within that window,
continue with the checks above.

The thirty-minute window is generous deliberately. A deployment slightly outside it that remains
the only candidate may still be recorded as the cause, at the responder's discretion, provided the
reasoning is noted.

## Escalation

Escalate to payments-platform. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Where the degradation appears at the order handoff step of a checkout operation, escalate instead
to order-fulfilment on `#order-fulfilment-oncall`. Order handoff failures are not payment failures
and routing them to payments-platform delays them by a full handover.

Escalate rather than continue when:

- the checks above are exhausted and the class is still unclear;
- a class 3 condition is sustained past fifteen minutes with no class agreed;
- a rollback has been performed and the degradation has not receded within ten minutes;
- the next useful check would require host-level, storage-level or datastore-internal visibility.
  This runbook does not cover those. Hand the question to the owning team with the classification
  and the evidence gathered.

Record the class, the slice, the baseline used and, where a deployment was identified, the
deployment recorded as the cause. Escalations omitting the baseline are routinely sent back.

## Related documents

- RB-PAY-001 — /checkout latency and failure investigation
- RB-PAY-002 — /refunds investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
