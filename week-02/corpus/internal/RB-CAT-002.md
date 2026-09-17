---
document_id: RB-CAT-002
title: /search — Performance Investigation
document_type: runbook
service: catalog-service
status: current
supersedes: null
superseded_by: null
owner_team: catalog-discovery
access_level: operations
version: "3.3"
last_reviewed: 2026-03-17
---

# /search — Performance Investigation

Establish the class with RB-CAT-000 first, including the capacity-against-fault check, which is
not repeated here. This document covers what to look at for this endpoint once that is done.

/search carries the highest request volume on the platform, by a wide margin and not by a small
one. Every property of this endpoint's telemetry follows from that, and one of them causes more
wrong conclusions than everything else in this document combined.

## Symptoms

**Class 1, errors elevated.** Read the rate. Do not read the count. See below.

**Class 2, latency elevated.** The common case here, and usually a capacity question rather than a
fault. RB-CAT-000 has the discriminator.

**Class 3, both elevated.** Uncommon on this endpoint and worth treating as significant when it
does occur.

**Class 4, neither elevated.** Index lag. Stale results return successfully and fast, so neither
series moves. RB-CAT-000 covers the procedure.

## Discriminating checks

**Rate against count.** This is the characteristic trap on this endpoint and it is worth stating
as a general principle first. On a high-volume slice, the absolute number of failures in any
window is large even when the failure rate is entirely unremarkable, because the count is the rate
multiplied by a large number. A four-figure failure count can be a completely ordinary day. The
consequence is that absolute failure counts on this endpoint carry almost no diagnostic
information on their own, and reading them as though they did produces alarm that the rate does
not support.

This matters more than it sounds, because counts are what people quote. A count is a concrete
number that fits in a message and it sounds serious; a rate needs a denominator and an objective to
mean anything. On this endpoint the count will sound serious every single time. Before escalating,
before paging, and before writing anything into an incident channel, convert to a rate and compare
that against the declared objective in POL-SLO-001. If the rate is within objective, the count is
not a finding no matter how large it is.

The reverse also holds and is less often noticed. A rate rise that is small in proportional terms
represents a very large number of affected requests here, so a modest-looking rate change on this
endpoint can have a wider blast radius than a dramatic one elsewhere. Blast-radius thresholds are
in POL-SEV-001 and are expressed in a way that accounts for this; use them rather than judgement.

**Query mix.** Search cost varies by query shape, and the spread between the cheapest and the most
expensive shapes is wide. A shift in the mix toward the expensive end raises p95 with no fault and
no volume change, which the capacity check in RB-CAT-000 will not catch, because that check keys
on volume and volume is flat. Where the capacity check comes back inconclusive, mix is the next
thing to look at, and it is inconclusive more often on this endpoint than on /products.

**Non-customer traffic.** A material share of the volume on this endpoint is not customer traffic
— crawlers, monitoring, partner integrations polling on a schedule. The share is not constant. A
change in it moves total volume, and usually the query mix along with it, without any change in
customer-facing demand and without anything being wrong. Two failure modes follow. Reading a
volume rise as customer demand overstates the capacity problem and can lead to the wrong response
entirely. Reading a volume fall as a demand drop understates a customer-facing outage that is
being masked in the aggregate by steady automated traffic. Where the capacity check turns on a
volume change, establish what kind of volume changed before acting on it. If that cannot be
established from the gateway view, say so in the handover rather than assuming the traffic was
customers.

**Result quality against availability.** A search that returns quickly and successfully with poor
or stale results is a class 4 and is invisible in both series. Establish whether the complaint is
about results being absent, wrong, or merely old — old goes to the index lag procedure in
RB-CAT-000, the other two are escalated.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Escalation

Escalate to catalog-discovery. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- a rate rise is confirmed against objective, given the blast radius at this volume;
- the capacity check and the query mix check are both inconclusive;
- results are absent or wrong rather than stale;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class and the evidence gathered.

Record the class, the failure rate, the capacity-check result and the baseline used. Do not record
a raw failure count without the rate beside it. Escalations that lead with a count are sent back,
not because the count is wrong but because it will be repeated by everyone downstream who reads it
and correcting that afterwards takes longer than getting it right once.

## Related documents

- RB-CAT-000 — catalog-service triage and escalation
- RB-CAT-001 — /products investigation
- PM-2026-009 — capacity saturation during a traffic surge
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
