---
document_id: CAT-OWN-001
title: Service Ownership Matrix
document_type: catalog
service: platform
status: current
supersedes: null
superseded_by: null
owner_team: payments-platform
access_level: operations
version: "8.2"
last_reviewed: 2026-07-15
---

# Service Ownership Matrix

Authoritative record of which team owns each backend service, how to reach them, and what coverage
exists outside business hours. Escalation targets named in runbooks resolve through this document.

## Ownership

| Service | Owning team | Escalation contact | Business hours (UTC) | Out of hours |
|---|---|---|---|---|
| payment-service | payments-platform | `#payments-oncall`, pager rota `pay-primary` | 07:00–19:00, Mon–Fri | Full rota, 24/7 including weekends |
| inventory-service | fulfilment-core | `#fulfilment-oncall`, pager rota `ful-primary` | 08:00–18:00, Mon–Fri | Rota to 22:00 daily; platform on-call thereafter |
| catalog-service | catalog-discovery | `#catalog-support`, pager rota `cat-primary` | 09:00–17:00, Mon–Fri | Best effort only; no guaranteed response |
| auth-service | identity-access | `#identity-oncall`, pager rota `idn-primary` | 07:00–19:00, Mon–Fri | Full rota, 24/7 including weekends |

Platform on-call is reachable at `#platform-oncall` at all times and holds incidents for teams
without coverage. Platform on-call does not remediate on another team's behalf.

## Notes

Catalog-discovery has no guaranteed out-of-hours response. A Sev 1 or Sev 2 affecting
catalog-service outside business hours escalates to platform on-call, who will establish contact
with catalog-discovery on a best-effort basis and hold the incident until it is accepted. Do not
page catalog-discovery repeatedly in the expectation of a response; the rota is unstaffed outside
the hours shown and repeated paging delays the platform on-call handover.

Fulfilment-core coverage ends at 22:00. Incidents opened before 22:00 remain with fulfilment-core;
incidents opened after transfer to platform on-call.

Security escalations do not follow this table. They follow the path in POL-SEV-001 regardless of
which service is affected.

Contact details change more often than this document is reviewed. Where a contact fails, escalate
to platform on-call rather than searching for an alternative route, and report the failure so this
document can be corrected.

## Escalating correctly

Escalate to the owning team named above, not to platform on-call as a first resort. Platform
on-call holds incidents for teams without coverage and does not hold them merely because reaching
the owning team is inconvenient. An escalation routed straight to platform on-call during the
owning team's business hours will be redirected, and the redirection costs time that the incident
does not have.

Where an incident affects more than one service, escalate to each owning team separately and name
the other teams involved in each escalation. Do not assume that escalating to one team notifies
the others; nothing in the paging arrangements does that.

## Related documents

- CAT-DEP-001 — endpoint dependency map
- POL-SEV-001 — incident severity and escalation matrix
- POL-SLO-001 — objectives and alerting policy
