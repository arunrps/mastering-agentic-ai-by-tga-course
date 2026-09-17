# Week 2 Corpus Manifest — TriageLens Runbook Retrieval

**Purpose:** the complete specification for the Week 2 RAG corpus. Hand this to Claude Code as
the build spec. Also the record of *why* each document exists, so the planted failure cases are
not accidentally "fixed" later by someone who thinks they are mistakes.

**Location:** `my-work/week-02/corpus/`

---

## 1. The absolute rule

**No document may encode the answer key.**

A runbook that says *"if /checkout slows after payment-service v2.4.1, roll back v2.4.1"*
makes retrieval trivial, makes the Week 4 evaluation meaningless, and turns the agent into a
lookup table. The system must connect *observed evidence* to *general procedure*. It must never
retrieve the solution.

Concretely, no document may mention:
- the version string `v2.4.1` or any specific deployment in the dataset
- the times 13:50, 13:55, 14:05, 14:45, or any incident timestamp
- the phrase "payment-service is the cause" or any variant
- a numbered sequence that resolves the Week 1 incident specifically

Runbooks describe **classes of failure and the checks that discriminate between them.** That is
what real runbooks do.

---

## 2. Frontmatter schema

Every internal document opens with YAML frontmatter. Every field is required.

```yaml
---
document_id: RB-PAY-000
title: Payment Service — Triage and Escalation
document_type: runbook        # runbook | policy | catalog | postmortem
service: payment-service       # or "platform" for cross-cutting docs
status: current                # current | superseded
supersedes: null               # document_id this replaces, or null
superseded_by: null            # document_id replacing this, or null
owner_team: payments-platform
access_level: operations       # operations | restricted
version: "3.1"
last_reviewed: 2026-06-14
---
```

**Why each field earns its place:**

| Field | Used by |
|---|---|
| `document_id` | Join key from `topology.json` — retrieval can be scoped by ID before semantic search |
| `service` | Metadata filter: retrieve payment-service docs when payment-service is the suspect |
| `document_type` | Lets a query prefer procedure over postmortem, or policy over runbook |
| `status` / `superseded_by` | The superseded-document failure case; also the citation must say which it used |
| `access_level` | Week 6 authorization filtering, wired now so it isn't retrofitted |
| `version` / `last_reviewed` | Staleness signal a reviewer will recognise as realistic |

---

## 3. Internal corpus — 19 documents

Originally scoped at 15. `topology.json` declares runbook IDs for all seven
endpoints, so the endpoint runbooks grew from 4 to 7; the superseded document
makes 19. Topology wins on IDs.

IDs follow the topology scheme: `RB-<CODE>-000` = service runbook, `-001+` = endpoint runbooks.
Codes: **PAY** payment-service · **INV** inventory-service · **CAT** catalog-service ·
**AUTH** auth-service.

### Service runbooks (4)

| ID | Title | Contains | Notes |
|---|---|---|---|
| `RB-PAY-000` | Payment Service — Triage and Escalation | Symptom classes (elevated 5xx, elevated latency, both together, neither), discriminating checks, when to escalate, dependency health checks | v3.1, current. The primary retrieval target for the Week 1 incident shape |
| `RB-INV-000` | Inventory Service — Triage and Escalation | Stock-lookup timeouts, cache staleness, cart/order divergence | Current |
| `RB-CAT-000` | Catalog Service — Triage and Escalation | Read-heavy saturation, search index lag, capacity vs fault discrimination | Current. Supports the future capacity-saturation archetype |
| `RB-AUTH-000` | Auth Service — Triage and Escalation | Token validation failures, fast-fail 503s, distinguishing 401 surges (client) from 5xx (backend) | Current. **Deliberately explains that auth failures often show errors without a latency rise** — general principle, not the answer key |

### Endpoint runbooks (4)

| ID | Title | Contains |
|---|---|---|
| `RB-PAY-001` | /checkout — Latency and Failure Investigation | Ordering of checks when checkout degrades; how to tell an endpoint problem from a backend problem |
| `RB-PAY-002` | /refunds — Failure Investigation | Similar shape, plus the note that /refunds shares its backend with /checkout and corroborating both is a backend signal |
| `RB-AUTH-001` | /login — Degradation Investigation | Login-specific checks; **explicitly warns that low absolute failure counts on /login are common and not by themselves actionable** |
| `RB-CAT-001` | /search — Performance Investigation | High-volume endpoint; how to separate volume-driven latency from a fault |

### Policies (3)

| ID | Title | Contains | Notes |
|---|---|---|---|
| `POL-DEPLOY-001` | Deployment Validation and Rollback Policy | Post-deploy validation window, what evidence justifies a rollback, who authorises it, **why a rollback must not be treated as proof of cause** | Current. **`access_level: restricted`** — the authorization test case |
| `POL-SEV-001` | Incident Severity and Escalation Matrix | Sev definitions, blast-radius thresholds, paging rules, comms expectations | Current |
| `POL-SLO-001` | Service Level Objectives and Alerting Policy | Declared SLOs per service, alert thresholds, **the alert-fatigue rationale for minimum evidence floors** | Current. Aligns with the SLO fields in `topology.json` |

### Catalog (2)

| ID | Title | Contains |
|---|---|---|
| `CAT-OWN-001` | Service Ownership Matrix | Service → owning team → escalation contact → business hours |
| `CAT-DEP-001` | Endpoint Dependency Map | Endpoint → backend mapping in prose, with the caveat that it reflects declared topology and may drift from observed traffic |

### Postmortems (2)

| ID | Title | Contains | Notes |
|---|---|---|---|
| `PM-2026-014` | Shared-Backend Degradation Affecting Two Endpoints | A *different* past incident with the same shape — two endpoints on one backend degrading together, latency leading errors. **Different service, different endpoints, different resolution.** Teaches the pattern without giving the answer | The strongest doc in the corpus. A reviewer sees the system reasoning by analogy |
| `PM-2026-009` | Capacity Saturation During a Traffic Surge | Latency rise with errors staying near baseline; no deployment involved | Supports the "not every incident has a deploy" lesson |

---

## 4. The planted failure cases

Each of these exists to make retrieval *fail in a specific, diagnosable way*. They are the
point of the corpus, not defects in it.

### 4.1 The superseded document

`RB-PAY-000-ARCHIVED` — `status: superseded`, `superseded_by: RB-PAY-000`, `version: "2.4"`,
`last_reviewed: 2025-03-02`.

Same title, similar wording, semantically close enough to score well on vector similarity. It
contradicts the current version in a **verifiable, non-trivial** way — for example, an older
escalation threshold and an obsolete dependency name.

**Tests:** does retrieval prefer `status: current`? Does the citation name which version it
used? Does the answer change if the filter is removed? This is a live demo moment: show it
retrieving the wrong doc without the filter, then right with it.

### 4.2 The partial answer

`RB-PAY-001` (/checkout) covers **single-endpoint** degradation thoroughly but says nothing
about what it means when a **sibling endpoint on the same backend degrades simultaneously.**
`RB-PAY-002` (/refunds) carries that part.

**Tests:** does the system retrieve both and synthesise, or stop at the first good hit and
answer incompletely? Does it say what it *doesn't* cover?

### 4.3 The restricted document

`POL-DEPLOY-001` is `access_level: restricted`.

**Tests:** in Week 2, does the citation surface the restriction? In Week 6, is it filtered out
entirely for an operations-level identity — and does the system say "relevant guidance exists
but is not available at your access level" rather than pretending it doesn't exist?

### 4.4 Questions with no answer — the refusal set

The corpus deliberately contains **nothing** about:

- host-level metrics (CPU, memory, disk)
- database internals, connection pools, lock contention
- message queue depth, consumer lag, dead letter queues
- CDN or edge behaviour
- cost or billing

Write **at least six evaluation questions** that fall in these gaps. Example:
*"payment-service latency is elevated — what should I check on the database?"*

Correct behaviour: **"The corpus contains no guidance on database-level checks for
payment-service. The available payment-service runbook covers X and Y."** Naming what *is*
available while refusing what isn't is the difference between a useful refusal and a dead end.

### 4.5 Near-duplicate distractors

The four service runbooks share structure and much vocabulary — "elevated 5xx", "escalate to
the owning team", "verify dependency health". This is realistic and it makes retrieval work.
Do not artificially differentiate them.

**Tests:** does metadata filtering by `service` rescue precision where pure semantic similarity
would return all four?

---

## 5. Vendor layer — 4 real public documents

Real, publicly fetchable, cited by URL. They give authentic messy ingestion a reviewer can
verify, and they are the honest source for questions the internal runbooks route *to* rather
than answer.

| Source | Topic | Why this one |
|---|---|---|
| AWS | API Gateway / ALB 5xx and 504 behaviour — integration timeouts, what the gateway reports vs what the backend did | Directly relevant to the "is this the gateway or the backend?" question |
| Kubernetes | Liveness and readiness probes, connection handling | The general mechanism behind "the service restarted mid-incident" |
| PostgreSQL | Connection limits and `max_connections` behaviour | The classic saturation failure mode |
| Apache Kafka | Consumer lag — what it means, how it manifests | Integration-flavoured; supports the future retry-storm work |

**Handling rules:**

- Store fetched content under `corpus/vendor/`, with a `source_url` and `fetched_at` in
  frontmatter, `document_type: vendor`, `service: external`
- **Do not clean them up.** Navigation cruft, inconsistent heading depth, and code blocks are
  the point — this is what real ingestion looks like
- They are the *only* place the corpus discusses database connections or consumer lag, so a
  question in that space should retrieve vendor guidance and be explicit that it is
  general vendor documentation, not an internal approved procedure
- Respect the copyright boundary: store for local retrieval, cite by URL, never reproduce
  substantial passages in the writeup or the demo

---

## 6. Writing standards

- **Length:** 400–900 words per internal document. Long enough to chunk meaningfully, short
  enough that 15 of them are writable.
- **Structure:** `## Symptoms` · `## Discriminating checks` · `## Escalation` ·
  `## Related documents`. Consistent structure makes chunking predictable and gives the
  citation something to point at.
- **Voice:** flat, procedural, mildly bureaucratic. Real runbooks are not well written. A
  corpus that reads like polished marketing copy is a tell.
- **Cross-references by `document_id`**, so the retrieval layer can follow them later.
- **Dates and versions vary.** Some docs reviewed recently, some over a year ago. Staleness is
  realistic and it is a signal the system can later surface.

---

## 7. Build order

1. `RB-PAY-000` first, complete, as the quality benchmark for the rest
2. The other three service runbooks
3. The four endpoint runbooks
4. Policies and catalog
5. The two postmortems
6. `RB-PAY-000-ARCHIVED`, the superseded version — written **last**, derived from the current one, so
   the contradictions are deliberate rather than accidental
7. Vendor layer fetch
8. The evaluation question set: ~20 questions spanning answerable, partially answerable,
   restricted, and unanswerable

**Item 8 is not optional and not an afterthought.** The refusal path is designed first, and
you cannot design it without knowing what the system will be asked to refuse.

---

## 8. What this corpus is not

- Not a documentation site. No index page, no getting-started guide.
- Not comprehensive. The gaps are deliberate and load-bearing.
- Not tuned to make retrieval look good. Near-duplicates stay near-duplicate.
- Not a place to record the Week 1 incident. Postmortems describe *other* incidents.
