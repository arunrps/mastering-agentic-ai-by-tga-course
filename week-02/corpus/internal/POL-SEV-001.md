---
document_id: POL-SEV-001
title: Incident Severity and Escalation Matrix
document_type: policy
service: platform
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "2.3"
last_reviewed: 2025-05-19
---

# Incident Severity and Escalation Matrix

This policy defines incident severity, the thresholds at which each severity applies, paging
obligations, time limits on classification, and communications expectations. Runbooks defer to this
document for severity assignment and shall not define severities of their own.

## 1. Severity definitions

**Sev 1.** A business capability is unavailable, or is degraded to the point of being unusable, for
a substantial proportion of those attempting it. Payment capabilities are Sev 1 at lower thresholds
than other capabilities, per section 2.

**Sev 2.** A business capability is materially degraded but usable. Some proportion of attempts
fail or complete outside objective; the capability as a whole continues to function.

**Sev 3.** A measurable degradation that does not materially affect the ability to complete the
capability. Objective breaches with limited blast radius sit here.

**Sev 4.** An observation that warrants recording but not response. Includes conditions that
recover without intervention and conditions that cannot be assessed.

## 2. Blast-radius thresholds

Severity shall be assigned on blast radius, expressed in **affected requests over the assessment
window**, and not on rate alone. This is deliberate. A rate is a proportion, and the same
proportion represents very different numbers of affected people on slices of different size. A
threshold expressed only as a rate assigns the same severity to a condition affecting tens of
requests and one affecting tens of thousands.

| Severity | Affected requests in window | Or, rate condition |
|---|---|---|
| Sev 1 | 10,000 or more | Rate above 25% on any slice clearing the evidence gate |
| Sev 2 | 1,000 to 9,999 | Rate above 10% on any slice clearing the evidence gate |
| Sev 3 | 100 to 999 | Any confirmed objective breach clearing the evidence gate |
| Sev 4 | Fewer than 100 | Any outcome of NOT EVALUABLE or EVIDENCE INSUFFICIENT |

Where the count threshold and the rate condition disagree, the **higher** severity applies. A
high-volume slice will frequently reach a count threshold at a rate that looks unremarkable; that
is the intended behaviour and the severity is not to be reduced on the grounds that the rate is
small. Conversely a low-volume slice may present an alarming rate while affecting few requests, and
the count threshold prevents that from consuming a Sev 1 response.

Payment capabilities are assigned one severity level higher than the table produces, to a minimum
of Sev 2, on the grounds that a failed payment is not retried by the affected person as readily as
a failed read and the business consequence does not recover when the condition does.

## 3. Time to classification

An incident shall be assigned a severity within the limit below, measured from the first alert or
report. Where the limit is reached without an agreed classification, the incident shall be
escalated to the owning team at the severity currently suspected.

| Suspected severity | Limit |
|---|---|
| Sev 1 | 5 minutes |
| Sev 2 | 15 minutes |
| Sev 3 | 60 minutes |
| Sev 4 | End of shift |

These limits apply to classification, not to resolution. An unclassified incident consumes
responder attention without directing it, and the limits exist to force a decision rather than to
imply that one will be easy. Classifying at the suspected severity and revising later is the
expected behaviour; holding an incident unclassified while gathering further evidence is not.

## 4. Paging

Sev 1 pages the owning team immediately and the platform on-call simultaneously. Sev 2 pages the
owning team. Sev 3 raises a ticket to the owning team within business hours and pages only if it is
still open at the end of the next business day. Sev 4 is recorded and not paged, and shall not be
paged by arrangement between individuals outside this policy.

Out-of-hours arrangements per team are in CAT-OWN-001. Where a team has no out-of-hours coverage,
a Sev 1 or Sev 2 affecting that team escalates to the platform on-call, who shall not attempt
remediation on behalf of the owning team but shall establish contact and hold the incident.

## 5. Security escalations

A degradation attributable to credential abuse, authentication abuse, or any pattern suggesting
deliberate action against the platform is not an operational incident and shall not be triaged as
one. It follows the security escalation path.

Indicators include a failure surge concentrated in credential-related status codes, a surge
distributed across many identities rather than concentrated in one client or integration, and a
surge whose timing or shape does not correspond to any change in traffic.

Where such a pattern is suspected the responder shall escalate immediately, at Sev 2 or higher, and
shall **not** post details of the pattern into a general incident channel. Discussion of a
suspected abuse pattern is restricted to the security escalation channel. This constraint applies
even where the suspicion later proves unfounded.

## 6. Communications

Every incident at Sev 2 or above shall maintain a written record containing the severity, the
affected capability, the slice under assessment, the baseline used, and the evidence outcome. The
record shall be updated on any change of severity.

Statements of cause shall not be made in incident communications while an incident is open.
Correlations may be recorded as correlations. Where a change is suspected of involvement, follow
POL-DEPLOY-001; that document is restricted, and its contents shall not be summarised into a
general channel by a responder who has access on behalf of one who does not.

## 7. Related documents

- POL-SLO-001 — objectives and alerting policy
- POL-DEPLOY-001 — deployment validation and rollback (restricted)
- CAT-OWN-001 — service ownership matrix
