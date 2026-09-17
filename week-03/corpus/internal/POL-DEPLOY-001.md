---
document_id: POL-DEPLOY-001
title: Deployment Validation and Rollback Policy
document_type: policy
service: platform
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: restricted
version: "4.1"
last_reviewed: 2026-08-12
---

# Deployment Validation and Rollback Policy

Restricted. This document is available at restricted access level only. It shall not be
summarised, quoted, or paraphrased into a general incident channel, and a responder holding access
shall not relay its contents on behalf of one who does not. Where guidance from this policy is
required by someone without access, the request is escalated to the owning team.

## 1. Post-deployment validation window

Every deployment enters a validation window beginning when the change is fully applied. The window
is 60 minutes for changes to payment capabilities and 30 minutes for all others.

Within the window the deploying team shall confirm that the affected slices clear the evidence gate
in POL-SLO-001 at their declared objectives, and shall record that confirmation. A window that
elapses without recorded confirmation is treated as unvalidated, which is a distinct state from
validated and from failed, and shall be recorded as such.

The window is not a quiet period. Normal alerting applies throughout it and an incident arising
during a validation window is triaged under the ordinary runbooks, not under this policy.

## 2. Evidence justifying a rollback

A rollback may be authorised where all of the following hold:

1. A slice affected by the change is EVIDENCE SUFFICIENT under POL-SLO-001, against a baseline
   predating the change.
2. The onset of the degradation falls within the validation window, or within one hour of its
   close.
3. The degradation is not accounted for by a change in traffic volume or request mix.
4. The rollback is expected to restore the prior behaviour without leaving the system in a state
   neither the previous nor the current version anticipates.

Condition 4 is the one most often overlooked. Where a change is not cleanly reversible, rollback is
not the appropriate response and the incident proceeds under the ordinary runbooks with the change
in place.

Correlation with a validation window is a necessary condition and not a sufficient one. Where
conditions 1 to 3 hold but the responder cannot articulate a mechanism by which the change could
produce the observed degradation, that shall be recorded alongside the authorisation rather than
omitted from it.

## 3. Authorisation

A rollback affecting a single service is authorised by the owning team's on-call engineer. A
rollback affecting payment capabilities, or more than one service, is authorised by the owning
team's on-call engineer together with the platform on-call. Authorisation shall be recorded before
the rollback is executed, naming both the authoriser and the evidence relied upon.

Nobody may authorise a rollback of a change they deployed, at any severity, including their own
change during their own validation window. This is not a statement about anyone's judgement; it is
that the person who deployed a change has the least useful prior about whether it is responsible.

## 4. A rollback is not proof of cause

This section is the reason this policy exists in its current form, and it is the part most
frequently disregarded.

Where a system recovers following a rollback, it is tempting and very common to record that the
rolled-back change caused the failure. That inference is not available. What has been demonstrated
is that the change and the failure are **consistent with each other** — the failure was present
with the change applied and absent with it removed. That is compatible with the change having
caused the failure. It is equally compatible with several other situations.

A rollback is not an isolated intervention. It is itself a deployment: it restarts processes,
resets in-memory state, re-establishes connections, and clears whatever had accumulated in the
running system since the original change. Any of those side effects can resolve a condition the
change did not create. A condition arising independently and resolving on its own timescale will
also appear to have been fixed by whatever happened most recently, and a rollback performed during
an incident is reliably the most recent thing to have happened.

Two consequences follow, and both are binding.

First, a post-incident record shall state what was observed — the change, the degradation, the
rollback, the recovery, and their ordering — and shall not assert causation on that basis alone.
Establishing cause requires evidence about mechanism, which a rollback does not supply.

Second, a successful rollback does not close the investigation. Where the mechanism has not been
established, the change shall not be redeployed until it has been, and the possibility that the
change was not responsible shall remain open in the record. A rollback that resolved an incident
whose cause was elsewhere leaves that cause in place and removes the evidence that would have
found it.

## 5. Related documents

- POL-SLO-001 — objectives and alerting policy
- POL-SEV-001 — incident severity and escalation matrix
- CAT-OWN-001 — service ownership matrix
