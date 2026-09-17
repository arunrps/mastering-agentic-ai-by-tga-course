---
document_id: RB-CAT-001
title: /products — Performance Investigation
document_type: runbook
service: catalog-service
status: current
supersedes: null
superseded_by: null
owner_team: catalog-discovery
access_level: operations
version: "1.1"
last_reviewed: 2025-08-04
---

# /products — Performance Investigation

Establish the class with RB-CAT-000 first, including the capacity-against-fault check. This
endpoint has needed little beyond that, and this document is short for that reason rather than by
oversight.

## Symptoms and checks

/products serves product detail reads. The responses are heavily cached, the request shape varies
little, and the cost per request is close to uniform. In practice this endpoint degrades in only
two ways worth documenting.

**Volume-driven latency.** Product detail traffic rises and falls with overall site traffic and
the endpoint slows under load in the ordinary way. RB-CAT-000's capacity check applies unchanged
and resolves most alerts on this endpoint. Nothing here modifies it.

**Cache hit rate.** A latency rise without a corresponding volume rise usually indicates that a
larger share of requests is reaching past the cache. Where hit rate information is available at
the gateway, check it before treating a p95 rise as a fault. Where it is not, this is a
service-level question and goes to RB-CAT-000. A falling hit rate is not itself a fault — it can
follow from a change in what is being requested rather than from anything being wrong with the
cache — so establish the direction before naming it as one.

Errors on this endpoint are rare and there is no endpoint-specific guidance for them. A 5xx rise
on /products is treated as a service-level finding under RB-CAT-000 and escalated. Do not look for
a /products-specific explanation first; there is not usually one, and looking for one has cost more
time than it has saved. The rarity is itself informative — because errors here are unusual, a
confirmed rise deserves more weight than the same rise would carry on an endpoint where errors are
routine, and it should not be discounted merely because the count is small.

Stale product detail is the /products equivalent of the index lag case in RB-CAT-000, and follows
the same procedure. It presents as class 4, produces no movement in either series, and is
distinguished from a fault by whether the served content is old but coherent or is missing or
malformed.

## Known non-issues

Recurring reports on this endpoint that have been investigated before and are not incidents. This
list exists so the same investigation is not repeated. It is not exhaustive and it has not been
revisited in some time, so confirm rather than assume.

- A brief latency rise coinciding with the scheduled catalogue refresh. The refresh changes the
  content being served and the mix of requests briefly shifts with it. This resolves on its own
  and is expected. If it does not resolve within the refresh window, that is a finding.
- Elevated request volume attributable to a partner integration polling on a schedule. Volume
  moves, customer-facing demand does not. RB-CAT-002 has more on separating the two; the same
  reasoning applies here at smaller scale.
- Requests for product detail on items that are subsequently discarded by the client. This inflates
  volume without inflating anything a customer experiences. It is a client behaviour, not a
  service condition, and it is not raised with catalog-discovery.
- Occasional single-item reports of detail that does not match what is shown elsewhere. Almost
  always staleness, handled as class 4 above. Escalate only if the content is missing or malformed.

None of the above justifies opening an incident on its own. If one of them coincides with a
genuine class 1 or class 3 finding, the finding is what matters and the coincidence is noted but
not reasoned from.

## Escalation

Escalate to catalog-discovery. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when the capacity check is inconclusive, when any 5xx rise is
confirmed, when content is reported missing or malformed rather than stale, or when the next
useful check would require host-level, storage-level, queue-level or datastore-internal
visibility, which this document does not cover.

Record the class, the capacity-check result and the baseline used. Where a known non-issue above
appears to account for the observation, record which one and why, so that the next person does not
start over.

## Related documents

- RB-CAT-000 — catalog-service triage and escalation
- RB-CAT-002 — /search investigation
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
