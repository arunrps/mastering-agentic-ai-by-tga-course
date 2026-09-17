---
document_id: CAT-DEP-001
title: Endpoint Dependency Map
document_type: catalog
service: platform
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "2.9"
last_reviewed: 2026-01-23
---

# Endpoint Dependency Map

Which backend serves which endpoint, in prose, for responders establishing whether two degraded
endpoints share anything. Runbooks refer here for the endpoint-to-backend relationship and for the
caveat in the final section, which applies to every entry below.

## Payment capabilities

**/checkout** is served by payment-service and owned by payments-platform. It carries order
payment. It is a composite operation and its runbook is RB-PAY-001.

**/refunds** is served by payment-service and owned by payments-platform. It carries payment
reversal. It shares its backend with /checkout, which makes the two a corroboration pair: where
both degrade in the same window the shared backend is implicated, subject to the volume caveat in
RB-PAY-002. Its runbook is RB-PAY-002.

## Fulfilment capabilities

**/cart** is served by inventory-service and owned by fulfilment-core. It carries basket
management. Its runbook is RB-INV-001.

**/orders** is served by inventory-service and owned by order-fulfilment. It carries order history.
It shares its backend with /cart, which makes the two a corroboration pair on the same basis as the
payment endpoints, though the two exercise substantially different paths and the negative case is
correspondingly weaker. Its runbook is RB-INV-002.

## Catalog capabilities

**/products** is served by catalog-service and owned by catalog-discovery. It carries product
detail. Its runbook is RB-CAT-001.

**/search** is served by catalog-service and owned by catalog-discovery. It carries product search.
It shares its backend with /products. Corroboration between these two is weaker than elsewhere,
because both are volume-driven and a traffic surge degrades them together without any shared fault;
see RB-CAT-000. Its runbook is RB-CAT-002.

## Authentication capabilities

**/login** is served by auth-service and owned by identity-access. It carries customer
authentication. It is the only endpoint declared against this backend, so no corroboration pair
exists and the absence of a corroborating endpoint carries no information. Its runbook is
RB-AUTH-001.

## Downstream dependencies

No downstream dependencies are declared for any backend above. This is not an assertion that none
exist. It reflects that nothing observable at the API gateway can confirm or refute a dependency
below the backend, and a dependency recorded here on any other basis would be an architecture
diagram rather than an operational fact. Questions about what a backend depends on are escalated to
the owning team.

## Accuracy caveat

This map reflects **declared** topology. It records the intended relationship between endpoints and
backends and it may drift from observed traffic. Drift is not rare and this document is not
reviewed on every change.

Where observed behaviour contradicts an entry here, the observation wins for the purposes of the
incident in progress. Record the discrepancy, proceed on what is observed, and raise a correction
afterwards. Do not resolve the contradiction by assuming the map is right, and equally do not
assume it is wrong — a single window in which two endpoints failed to correlate as expected is not
sufficient grounds to conclude the mapping has changed. Corroboration reasoning depends on these
relationships being correct, so a suspected error here is escalated to the owning team rather than
corrected locally.

## Related documents

- CAT-OWN-001 — service ownership matrix
- POL-SLO-001 — objectives and alerting policy
