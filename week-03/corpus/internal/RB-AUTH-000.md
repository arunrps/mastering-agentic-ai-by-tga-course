---
document_id: RB-AUTH-000
title: Auth Service — Triage and Escalation
document_type: runbook
service: auth-service
status: current
supersedes: null
superseded_by: null
owner_team: identity-access
access_level: operations
version: "4.0"
last_reviewed: 2026-07-22
---

# Auth Service — Triage and Escalation

Scope: applies when an alert or an automated verdict names auth-service, or an endpoint served by
auth-service, as elevated against baseline. Classification only, not remediation. Classify before
checking. The four classes do not share a check set; running the wrong set wastes the opening of
an incident.

Two warnings first, both changing how the classes are read.

Rejection on this service is cheap. Token validation that fails does so without doing the work a
success requires, so a severe condition can produce a large error signal while p95 on successful
requests does not move. The general principle: an incident does not require latency and errors to
move together. A flat latency curve is not corroboration of health.

Status classes are not interchangeable here. Split 4xx from 5xx before classifying anything. A
surge of 401s is usually a client-side or credential-side condition — a client build sending
malformed or expired credentials, a misconfigured partner integration, a credential-stuffing
pattern — not a backend outage. A surge of 5xx is the backend failing to answer. Conflating the
two produces the wrong class, the wrong team and the wrong severity.

## Symptoms

**Class 1 — errors elevated, latency at baseline.** The 5xx rate for the affected endpoint and
backend slice is above the declared objective while p95 stays inside it. This is the commonest
class here and is not a mild one; see the first warning.

**Class 2 — latency elevated, errors at baseline.** p95, usually p99 also, is above the declared
objective. The 5xx rate is at or near baseline. Work completes, but late.

**Class 3 — both elevated.** Both series are over objective in the same window.

**Class 4 — neither elevated, trouble reported.** A report arrives from support, a partner or an
engineer, and neither series crosses the floor for the slice named. A 401 surge presents here,
4xx not being counted in the 5xx series.

Declared objectives and the minimum evidence floor are in POL-SLO-001; do not re-derive them from
the telemetry being triaged.

## Discriminating checks

**4xx against 5xx, before anything else.** Separate the two status classes for the slice. If the
rise is 4xx, this is not class 1 however large it is; establish whether it is concentrated in one
client build, partner or credential pattern and route accordingly. If the rise is 5xx, classify
normally. Mixed rises are two findings, not one.

**Class 1 against class 2.** Do not use the latency of failing requests to decide this. On other
services a fast failure indicates rejection before the expensive work; here every failure is fast,
benign and severe alike, so the check does not discriminate. Use the 5xx rate against the
objective and nothing else.

**Class 1 against class 3.** Confirm whether p95 crossed at all. If it did not, this is class 1
and that is a complete classification — do not hold the incident open for latency to corroborate.

**Class 2 against class 3.** Confirm the error count clears the minimum evidence floor. A small
absolute number of 5xx on a low-volume slice does not promote class 2 to class 3. Threshold rule,
not a judgement. Low absolute failure counts are common here; RB-AUTH-001 covers why they are not
by themselves actionable.

**Ordering within class 3.** Latency rising ahead of errors is a recognised pattern elsewhere on
the platform and is recorded when observed: a caller holding a fixed timeout sees no errors from a
slowing callee until time-in-flight crosses that deadline. That mechanism largely does not apply
here, failures being returned rather than timed out. Its absence is not evidence.

**Sibling endpoint corroboration, all classes.** Determine whether another endpoint on the same
backend degraded in the same window. If it did, the evidence points at the shared backend rather
than at one endpoint's path. If it did not, the endpoint's own path is the first place to look.
This service currently serves one declared endpoint, so corroboration is usually unavailable and
its absence carries no information. Where an auth condition is suspected to affect other services,
that is a dependency question and is escalated rather than checked from here. Mappings are in
CAT-DEP-001, which may drift from observed traffic.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Escalation

Escalate to identity-access. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- a 5xx rise is confirmed at any size, given the first warning;
- a 4xx rise cannot be attributed to a client build, partner or credential pattern;
- another service reports auth-related failures it cannot classify itself;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  classification and evidence.

Record the class, the slice, the baseline and the 4xx/5xx split at escalation time. Escalations
reporting an undifferentiated error rate are sent back.

## Related documents

- RB-AUTH-001 — /login investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
