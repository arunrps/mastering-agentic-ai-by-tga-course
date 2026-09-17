---
document_id: RB-AUTH-001
title: /login — Degradation Investigation
document_type: runbook
service: auth-service
status: current
supersedes: null
superseded_by: null
owner_team: identity-access
access_level: operations
version: "2.6"
last_reviewed: 2026-08-05
---

# /login — Degradation Investigation

Establish the class with RB-AUTH-000 first, including the 4xx/5xx split, which is a precondition
for everything below. This document covers what to look at once that is done, and carries the
low-count guidance that RB-AUTH-000 defers here.

## Symptoms

**Class 1, 5xx elevated.** Act on this at any size. Rejection is cheap on this service, so the
error signal is the whole signal and there will be no latency movement to confirm it.

**Class 2, latency elevated.** Uncommon. Successful authentication is fast and its cost does not
vary much by input, so a p95 rise on successful requests is a genuine anomaly and is treated as
one.

**Class 3, both elevated.** Rare. Treat as class 1 and escalate.

**Class 4, neither elevated.** Where a 4xx rise is the reported condition, it lands here, because
4xx is not in the 5xx series. This is the single most common presentation on this endpoint.

## Discriminating checks

**Low absolute counts.** Failed logins are a normal, continuous feature of this endpoint. People
mistype passwords, credentials expire, sessions lapse, and clients retry. There is a persistent
floor of failures here that exists in the absence of any incident at all, and it is not small in
absolute terms. Two rules follow, and they are the reason this section exists.

First, a small absolute number of failures on this endpoint is not by itself actionable. It is the
expected state. Do not open an incident on it, do not page on it, and do not include it in a
summary as though it were evidence of anything, because it will be read as evidence by whoever
receives the summary. The minimum evidence floor in POL-SLO-001 exists precisely to keep this
class of observation out of the alerting path, and reintroducing it by hand defeats the purpose.

Second, and against the first, the floor cuts both ways. Because the baseline failure level is
high, a real increase can hide inside it. A rise that would be obvious on an endpoint with a clean
baseline is proportionally much smaller here. Compare against the baseline rather than against
zero, and against a baseline drawn from a comparable window — login failure rates have a strong
daily shape and a weekly one.

**4xx composition.** Where the rise is 4xx, establish whether it is concentrated. A single client
build, a single partner integration, or a single credential pattern indicates a specific
condition and routes to a specific owner. A rise spread evenly across clients is a different
finding and is escalated to identity-access. Do not treat a 4xx rise as a backend condition in
either case; RB-AUTH-000 covers why.

**Retry inflation.** Failures on this endpoint are not independent events. A person whose login
fails will usually try again immediately, often more than once, and some clients retry on the
person's behalf without being asked. One underlying condition therefore produces several recorded
failures, and the multiplier is not stable — it varies with the client, with how the failure is
presented to the person, and with how patient they are. The practical effect is that failure
counts on this endpoint overstate the number of affected people by an unknown factor, and rate
changes overstate the size of a condition for the same reason. Do not convert a failure count into
a number of affected customers here. If someone asks for that number, the honest answer is that
the gateway view cannot produce it, and an estimate offered anyway will be quoted back later as
though it were measured.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Escalation

Escalate to identity-access. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- any 5xx rise is confirmed, at any size;
- a 4xx rise is spread evenly across clients rather than concentrated;
- a 4xx rise is concentrated in a pattern that suggests credential abuse rather than
  misconfiguration — that is a security escalation and follows POL-SEV-001, not this document;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class and the evidence gathered.

Record the class, the 4xx/5xx split, the baseline used, and whether the rise is concentrated.
An undifferentiated error rate is not accepted on this endpoint.

## Related documents

- RB-AUTH-000 — auth-service triage and escalation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
