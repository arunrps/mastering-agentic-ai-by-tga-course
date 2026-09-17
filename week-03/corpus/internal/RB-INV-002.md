---
document_id: RB-INV-002
title: /orders — Failure Investigation
document_type: runbook
service: inventory-service
status: current
supersedes: null
superseded_by: null
owner_team: fulfilment-core
access_level: operations
version: "5.1"
last_reviewed: 2026-06-25
---

# /orders — Failure Investigation

Establish the class with RB-INV-000 first. This document covers what to look at for this endpoint
once the class is known.

/orders is a write path. That single fact accounts for most of what follows and for why this
runbook is longer than its read-path sibling. A failed read leaves nothing behind and can be
repeated freely. A failed write may or may not have left state behind, and the gateway view cannot
tell you which. Every question on this endpoint eventually reduces to that one, and most of the
mistakes made here come from answering it by assumption.

## Symptoms

**Class 1, errors elevated.** Write rejections and write failures both surface as 5xx and they are
not the same thing. A rejection means the write was refused before it was attempted. A failure
means it was attempted and did not complete, which is the case that may have left state.

**Class 2, latency elevated.** Writes that complete late. Note that a late write still completed —
a client that gave up before the response arrived has a different view of the world than the
service does, and that discrepancy is the source side of the divergence RB-INV-000 describes.

**Class 3, both elevated.** Treat as class 1 for the purpose of the retry question below. The
retry question does not care whether latency also moved.

**Class 4, neither elevated.** Order history showing something the cart view does not agree with.
RB-INV-000 covers the divergence procedure and it takes precedence over this document.

## Discriminating checks

**Rejection against failure.** Establish which of the two the 5xx rise consists of. Rejections are
returned early and consistently; failures are returned late, at varying times, or at a timeout
value. If the rise is rejections, the write path was never entered and no state question arises.
If the rise is failures, or if you cannot tell, assume state may have been left and proceed
accordingly.

**Client-side abandonment.** Where latency is elevated, establish whether clients are abandoning
requests before the response returns. An abandoned request is not a failed request and does not
appear in the 5xx series, but the client will report it as one and the customer will experience it
as one. This is a class 4 that arrives dressed as a class 2.

**Multi-item orders.** An order covering several items is one request but not necessarily one
outcome. A response indicating failure does not establish that every item in the order was
rejected, and a response indicating success does not establish that every item was accepted on the
terms requested. From the gateway there is one status code and no way to decompose it. Where a
report concerns a subset of an order rather than the whole of it, that is not a class 1 finding
however the request was recorded, and it is escalated. Do not reason from the status code to the
per-item outcome; the two are less closely related than the interface suggests.

**Divergence.** Any report of order history disagreeing with cart contents goes to RB-INV-000 and
is escalated on confirmation. Do not attempt to decide which view is correct from here.

**Evidence floor.** Confirm the failure count clears the minimum in POL-SLO-001. This endpoint
carries less volume than the read paths, so the floor is not always cleared and a clean verdict is
correspondingly weaker.

**Change correlation.** Where a change window overlaps the onset, follow POL-DEPLOY-001. That
document is access_level restricted and is not reproduced here; if you cannot open it, escalate
rather than proceed without it. Correlation is not attribution.

## Retry decision

The following is the agreed sequence for deciding whether a failed /orders request may be
retried. It is a checklist rather than prose because the previous version was prose and it was
read selectively. Work through it in order and stop where it says to stop. Do not start in the
middle because the earlier steps look obviously satisfied; step 1 in particular is skipped more
often than it is answered.

1. Was the failure a rejection or a failure? Rejection — retry is safe. Failure or unknown —
   continue to 2.
2. Did the request carry an idempotency key? No — stop. Do not retry. Escalate.
3. Is the key still within its validity window? Unknown from the gateway view — treat as no.
   Stop and escalate.
4. Has the same key already been retried? If the retry count is not available to you, treat as
   yes. Stop and escalate.
5. All of 1 to 4 satisfied — retry is permitted, once. A second retry is an escalation regardless
   of the outcome of the first.

Steps 3 and 4 will usually terminate the sequence, because the gateway view does not carry that
information. That is the expected outcome and it is not a failure of the checklist. The checklist
exists to make the stop explicit rather than to produce a retry.

Bulk retries are never authorised from this document, at any class, for any number of requests.
This holds whether the retry would be issued by a person, by a client, or by anything acting on
their behalf, and it holds regardless of how confident anyone is that the requests are identical.

## Escalation

Escalate to fulfilment-core. Contacts and business hours are in CAT-OWN-001. Severity,
blast-radius thresholds and paging rules are in POL-SEV-001.

Escalate rather than continue when:

- the retry sequence above terminates at any step, which is the normal outcome;
- rejections and failures cannot be separated from the gateway view;
- any divergence is confirmed or suspected;
- a bulk retry is being considered or has been requested by anyone;
- the next useful check would require host-level, storage-level, queue-level or datastore-internal
  visibility. This runbook does not cover those. Hand the question to the owning team with the
  class and the evidence gathered.

Record the class, the rejection-against-failure split, the baseline used, and which step of the
retry sequence terminated. Escalations that do not state the retry step are sent back.

## Related documents

- RB-INV-000 — inventory-service triage and escalation
- RB-INV-001 — /cart investigation
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- POL-SEV-001 — severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
- CAT-OWN-001 — service ownership
- CAT-DEP-001 — endpoint dependency map
