---
document_id: POL-SLO-001
title: Service Level Objectives and Alerting Policy
document_type: policy
service: platform
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "3.4"
last_reviewed: 2026-06-02
---

# Service Level Objectives and Alerting Policy

This policy declares the service level objectives for platform backends and defines the minimum
evidence required before a slice may be reported as elevated. Runbooks defer to this document for
both. Where a runbook and this policy disagree on a threshold, this policy governs.

## 1. Declared objectives

| Backend | p95 latency objective | Maximum 5xx rate |
|---|---|---|
| payment-service | 300 ms | 0.5% |
| inventory-service | 250 ms | 0.5% |
| catalog-service | 450 ms | 0.5% |
| auth-service | 250 ms | 0.5% |

These objectives are declared. They are not consumed by any automated calculation: no error budget
is computed from them and no burn rate is derived from them. A figure presented as a burn rate
must not be attributed to this policy.

## 2. The evidence gate

Evidence is assessed in two stages, producing one of three outcomes. Responders shall use the
outcome names as written. They are not interchangeable and shall not be compressed to a binary.

**Stage 1 — preconditions.** A slice that fails any of these is **NOT EVALUABLE**.

| Rule | Threshold |
|---|---|
| Requests in the window | 200 |
| 5-minute buckets containing requests | 2 |
| Requests in the matching baseline | 200 |
| Failures in the matching baseline | 5 |

**Stage 2 — the evidence bar.** A slice that clears stage 1 but fails any of these is **EVIDENCE
INSUFFICIENT**.

| Rule | Threshold |
|---|---|
| Failed requests | 10 |
| 5xx rate | 1% |
| 5xx rate relative to its matching baseline | 3.0× |
| Consecutive 5-minute buckets over the rate floor | 2 |

A slice clearing both stages is **EVIDENCE SUFFICIENT**. Buckets are five minutes.

## 3. Why a floor exists

Two reasons, and they are separate.

The first is alert fatigue. A platform that alerts on every excursion trains its responders to
disregard alerts, and a disregarded alert is worse than no alert because it consumes attention
while conveying nothing. The floor exists so that what does fire is worth reading.

The second is that a rate computed over a small number of requests is not a meaningful quantity. On
a slice carrying forty requests, one failure is a 2.5% rate and two failures are 5%. Neither number
describes the service; both describe the arithmetic of small denominators. Reporting such a rate
gives a spurious impression of precision, and rates of this kind are more misleading than an
acknowledged absence of information.

## 4. The floor is a threshold rule

The thresholds in section 2 shall be applied as stated. They are not a starting point for
judgement and responders shall not lower them for a slice that looks concerning, nor raise them for
one that does not.

The reason is reproducibility. Two responders assessing the same slice must reach the same outcome,
and they must reach it at three in the morning, under time pressure, having been woken. Judgement
does not survive those conditions consistently and it does not audit afterwards: a decision to
treat eight failures as sufficient cannot be distinguished later from a decision made carelessly.
A threshold can be checked by anyone, including the person who disagrees with it. Where a threshold
is believed to be wrong, the remedy is to change this policy, not to depart from it during an
incident.

## 5. Objectives and the floor are different tests

An objective breach and a floor breach are not the same event and shall not be reported as though
they were. The maximum 5xx rate declared in section 1 is 0.5%. The rate floor in section 2 is 1%.
A slice may therefore exceed its declared objective and still fall below the evidence floor.

This is intended. The objective describes the standard the service is held to over time. The floor
describes the minimum evidence required before an individual observation is acted upon during an
incident. A slice sitting between the two is failing its objective and does not warrant an
incident response, and both halves of that sentence are true simultaneously.

## 6. The asymmetry of a clean verdict

A verdict of not-elevated does not carry the same weight on every slice, and this is the property
the runbooks refer to most often.

The evidence thresholds are absolute counts — 200 requests, 10 failures, 5 baseline failures. A
fault, by contrast, presents as a rate, and a rate is proportional. A fault affecting one request
in fifty produces well over the failure minimum on a high-volume slice within a single window, and
may never produce ten failures at all on a low-volume one. The same underlying condition therefore
clears the bar on one slice and not on another, and the difference is volume, not health.

It follows that a not-elevated verdict on a high-volume slice is a substantive statement, while the
same verdict on a low-volume slice is close to uninformative. The NOT EVALUABLE outcome exists to
make this visible rather than to hide it: a slice that could not be assessed shall be reported as
unassessed and never as healthy. Responders shall not summarise a NOT EVALUABLE or EVIDENCE
INSUFFICIENT outcome as "clean", and where a report from a person contradicts a clean verdict on a
low-volume slice, the report shall be investigated rather than closed against the verdict.

## 7. Baselines

A baseline shall be drawn from a period comparable to the window under assessment. Comparability
requires matching on daily shape and on weekly shape, since platform traffic varies substantially
by hour of day and by day of week, and a mismatch on either produces an apparent change where none
occurred. The baseline window used shall be stated alongside any verdict derived from it. A verdict
presented without its baseline window is incomplete and shall be treated as unclassified.

This policy does not specify how a baseline is to be constructed when insufficient history exists
to satisfy the matching requirement above. The current detection implementation derives its
baseline from a fixed early portion of available history rather than from a shape-matched
comparison period; the two approaches are not equivalent, and reconciling them is outside the scope
of this document. Until that is resolved, responders shall confirm what baseline a verdict actually
used rather than assuming it satisfies this section.

## 8. Related documents

- POL-SEV-001 — incident severity and escalation matrix
- CAT-DEP-001 — endpoint dependency map
- CAT-OWN-001 — service ownership matrix
