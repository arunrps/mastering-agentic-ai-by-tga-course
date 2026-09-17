---
document_id: RB-PAY-002
title: /refunds — Failure Investigation
document_type: runbook
service: payment-service
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "2.0"
last_reviewed: 2026-05-11
---

# /refunds — Failure Investigation

Establish the class with RB-PAY-000 first. This document covers what to look at for this endpoint
once the class is known, and two general properties that happen to be documented here because this
is the endpoint where they bite hardest.

/refunds carries substantially less traffic than the other endpoint on this backend. It is not a
minor endpoint — the operations behind it matter and the people affected by a failure notice — but
the volume is low enough that the statistical properties of its telemetry differ from everything
else in this corpus, and most errors made on this endpoint come from forgetting that.

## Symptoms

**Class 1, errors elevated.** Given the volume, a rate rise here can be produced by a small number
of failures. Check the count as well as the rate before treating the rise as a finding.

**Class 2, latency elevated.** p95 on a low-volume slice is a noisier estimator than p95 on a
high-volume one. A p95 rise over a short window may be a handful of slow requests rather than a
shift in the distribution.

**Class 3, both elevated.** RB-PAY-000's ordering principle applies normally.

**Class 4, neither elevated.** More significant here than elsewhere on this backend — see the
evidence floor note below, which explains why the aggregate can look clean while something real is
happening.

## Discriminating checks

**Sibling corroboration.** Determine whether /checkout, the other endpoint served by this backend,
degraded in the same window. If it did, the evidence points at the shared backend rather than at either
endpoint's own path, and triage moves to service level under RB-PAY-000. Simultaneous degradation
of two endpoints that share a backend is one of the stronger signals available from gateway
telemetry, because the endpoints have separate request paths and separate client populations and
there are few reasons for both to move together other than the thing they share.

The negative case is much weaker and is routinely over-read. If the other endpoint did not
degrade, that is not evidence the backend is healthy. Check its volume first: a backend fault that
affects both endpoints equally in rate terms will show clearly on the high-volume one and may
stay below the evidence floor on the low-volume one. A quiet low-volume sibling is consistent with
a backend fault and with a backend that is fine, and it does not distinguish between them.

**The evidence floor on low-volume slices.** This is a general property and it applies wherever
volume is low, but it is written here because /refunds is where it matters most. The minimum
failure count in POL-SLO-001 exists so that alerting does not fire on noise, and that is the right
trade for a high-volume slice. On a low-volume slice the same floor means a real fault can be
present at any rate and still not produce enough absolute failures to clear it. The consequence is
asymmetric and worth stating plainly: a verdict of "not elevated" on a low-volume slice is weaker
evidence of health than the same verdict on a high-volume slice, and the two must not be treated
as interchangeable in a summary or a handover. Where a low-volume slice reads clean and a report
says otherwise, believe the report.

**Volume attribution.** Where a rate rise is driven by a small count, establish whether the
failures share anything — one client, one request shape, one time cluster. Concentration suggests
a specific condition rather than a general degradation, and is escalated as such.

**Reporting channel.** Trouble on this endpoint reaches us through support more often than through
alerting, which is a direct consequence of the volume: the floor is cleared late or not at all,
while the people affected notice immediately and have a reason to say so. Treat a support-led
report on /refunds as carrying more weight than the same report would carry on a high-volume
endpoint. It is not corroboration and it does not substitute for evidence, but it is a reasonable
basis for looking further when the telemetry says there is nothing to look at.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Escalation

Escalate to payments-platform. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- corroboration is positive, in which case triage moves to service level immediately;
- a report contradicts a clean verdict on this endpoint, per the evidence floor note;
- failures are concentrated in one client or request shape;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class and the evidence gathered.

Record the class, the failure count alongside the rate, the corroboration result, and the baseline
used. The count is required, not optional; a rate on its own is not interpretable on this endpoint.

## Related documents

- RB-PAY-000 — payment-service triage and escalation
- RB-PAY-001 — /checkout latency and failure investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
