---
document_id: RB-INV-001
title: /cart — Degradation Investigation
document_type: runbook
service: inventory-service
status: current
supersedes: null
superseded_by: null
owner_team: fulfilment-core
access_level: operations
version: "1.4"
last_reviewed: 2026-02-09
---

# /cart — Degradation Investigation

Establish the class with RB-INV-000 first. This document covers what to look at for this endpoint
once the class is known.

/cart is a read path, session-scoped, and fronted by a cache. It is the source side of the
divergence described in RB-INV-000: what this endpoint shows a customer is what they believe their
cart contains, and when that disagrees with what the order path sees, this is the view that formed
the belief.

## Symptoms

**Class 1, errors elevated.** Uncommon here. A cached read has few ways to fail, so an error rise
on this endpoint usually means requests are reaching past the cache, which is itself the finding.

**Class 2, latency elevated.** Read latency on this endpoint should be low and stable. A rise
generally indicates a lower cache hit rate rather than anything having slowed, and those are
different situations with different owners.

**Class 3, both elevated.** Treat as a cache-bypass condition until shown otherwise.

**Class 4, neither elevated.** The important class on this endpoint. Stale cart contents are served
successfully and quickly; neither series moves. Any report of a cart showing the wrong contents
lands here regardless of how clean the telemetry looks.

## Discriminating checks

**Served from cache or not.** Where cache hit information is available at the gateway, establish
whether the degradation coincides with a fall in hit rate. A latency rise with a falling hit rate
is a cache condition. A latency rise with a stable hit rate is not, and is a service-level question
under RB-INV-000. Where hit rate is not available to you, say so rather than assuming either.

**Stale against wrong.** RB-INV-000 has the full procedure and it takes precedence. In summary:
contents that are old but internally coherent indicate the cache is serving a previous state;
contents that are incoherent, or that never corresponded to any state the customer created,
indicate something else and are escalated immediately.

**Session scope.** Reports on this endpoint are frequently scoped to one session or one customer.
A single-session problem will never appear in the aggregate and its absence there is not evidence.
Establish the scope of the report before comparing it against telemetry at all, because for most
reports on this endpoint the comparison is not meaningful. This is worth stating because the
comparison is easy to run and produces a clean-looking answer, which then gets recorded as though
it settled something. It settles nothing about a single session. Where the report cannot be
widened beyond one customer, the aggregate is not the right instrument and no amount of looking at
it will make it one.

**Cart merge.** A session-scoped cart and a cart already associated with a customer are reconciled
when the customer authenticates mid-session. This is the one moment on this endpoint where cart
contents change for a reason that did not originate with the customer, and it is disproportionately
represented in divergence reports for that reason. Where a report describes contents changing
around a sign-in, note it explicitly in the handover — not because there is a check to run from
here, there is not, but because it narrows the question considerably for the owning team and it is
the kind of detail that gets lost when a report is summarised. Do not attempt to establish from
the gateway view which of the two carts was retained.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Escalation

Escalate to fulfilment-core. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- any report of wrong or divergent cart contents is received, at any class;
- a cache-bypass condition is suspected;
- cache hit information is not available and the class turns on it;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class and the evidence gathered.

Record the class, the scope of the report, the cache hit rate where available, and the baseline
used.

## Related documents

- RB-INV-000 — inventory-service triage and escalation
- RB-INV-002 — /orders investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
