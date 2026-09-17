---
document_id: RB-PAY-001
title: /checkout — Latency and Failure Investigation
document_type: runbook
service: payment-service
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "6.2"
last_reviewed: 2026-07-30
---

# /checkout — Latency and Failure Investigation

Use RB-PAY-000 to establish the class first. This document assumes the class is known and covers
what to look at for this endpoint once it is.

/checkout is a composite operation. One inbound request spans several steps — request validation,
payment authorisation, capture initiation, and handoff of the confirmed order — and the response
is not returned until the last of them resolves. Almost everything awkward about triaging this
endpoint follows from that. The request's time budget is the sum of the steps, so a step that
slows only moderately can exhaust it on its own. The failure surface is the union of the steps, so
a failure rate at the endpoint is an aggregate of several dissimilar things and should not be
reasoned about as though it were one.

## Symptoms

**Class 1, errors elevated.** The most common shape is a rise concentrated in one step while the
others are unaffected. An endpoint-level error rate does not show this and will read as a general
degradation.

**Class 2, latency elevated.** Either one step slowed, or the mix of requests shifted toward the
more expensive path without anything slowing at all. These are different findings.

**Class 3, both elevated.** RB-PAY-000's ordering principle applies here normally, this endpoint's
steps being called with fixed timeouts.

**Class 4, neither elevated.** Usually a partial completion. See the section below.

## Discriminating checks

**Which step.** Before anything else, establish whether the degradation is confined to one step of
the composite or spread evenly across all of them. Confined means the fault sits in that step's
path and triage narrows accordingly. Spread evenly means the composite is not the useful unit of
analysis and the question is a backend-level one, which RB-PAY-000 covers. Do not skip this
because the endpoint-level numbers look clear; they are an aggregate and they look clear either
way.

**Endpoint against backend.** To distinguish an endpoint-confined problem from a backend-wide one,
compare this endpoint's series against the backend's aggregate over the same window, and account
for the share of backend traffic this endpoint contributes. If the backend aggregate moved by
roughly what this endpoint's contribution explains and no more, the problem is endpoint-confined.
If the backend aggregate moved by more than this endpoint can account for, something else on the
backend is also degraded and triage belongs at service level. This is arithmetic on two series and
it is worth doing properly; the conclusion changes which team is paged.

**Request mix.** Composite operations have variable cost by input shape. A shift in the proportion
of requests taking the longer path raises p95 with nothing having slowed and nothing having
failed. Check the distribution of request shapes across the window before treating a p95 rise as a
fault. A mix shift that persists is a capacity question, not a fault, and is handled as one.

**Budget exhaustion.** Where the endpoint times out but no individual step is above its own
expected time, the composite budget is what is exhausted. This presents as class 3 and is easily
misread as a step fault. The tell is that failures cluster at the endpoint's own timeout value
rather than at any step's.

**Refusals against faults.** Not every negative outcome at the authorisation step is an error. An
authorisation that is declined is a legitimate result of the operation and is returned as such; it
is not a 5xx and it does not belong in the failure rate. Two things follow. First, a rise in
declines is not an incident on this endpoint and must not be triaged as one, though it may be
worth telling someone about. Second, if declines are appearing in the 5xx series, that is itself a
finding and is escalated: the endpoint is reporting an ordinary outcome as a failure, and every
rate derived from that series is wrong for as long as it lasts.

**Baseline selection.** This endpoint has a pronounced daily and weekly shape. A baseline drawn
from a window that does not match the comparison window on both will produce an apparent
degradation where there is none, and this is the commonest false positive here by some distance.
Confirm what baseline the verdict used before acting on it. If the baseline window is not stated,
treat the verdict as unclassified rather than negative.

**Evidence floor.** Confirm the failure count clears the minimum in POL-SLO-001 before classifying
at all. This endpoint carries enough volume that the floor is normally cleared; that is not
significance in itself.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Partial completion

Added after the Q1 review. This is not really a triage step and it does not fit the structure
above, but it comes up every time and people kept asking where it was written down, so it is here.

A /checkout request that fails does not necessarily fail cleanly. Because the steps resolve in
sequence, a failure at a late step can leave earlier steps already committed. From the gateway
view a partial completion and a clean failure look the same — both are one 5xx — and there is no
way to tell them apart from the two series. There is no check here that resolves this. What we
ask is that you do not assume a failed request did nothing, and that you say so explicitly in the
handover, because the assumption is easy to make and it has been made.

If a customer report suggests a partial completion, that goes straight to payments-platform. Do
not attempt to reconstruct what happened from the gateway. We do not have the visibility for it
and the reconstruction will be wrong. The same applies to any estimate of how many requests were
affected — the number cannot be derived from the failure count and giving one anyway has caused
more trouble than saying we do not know.

## Escalation

Escalate to payments-platform. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- the degradation cannot be attributed to a step and the backend comparison is inconclusive;
- a partial completion is suspected on any report, at any class;
- a mix shift is confirmed but its origin cannot be established from the gateway view;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class, the step attribution, and the evidence gathered.

Record the class, the step attribution, the backend comparison and the baseline used. Escalations
giving an endpoint-level error rate with no step attribution are sent back, the step attribution
being the part that takes time to reproduce later.

## Related documents

- RB-PAY-000 — payment-service triage and escalation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
