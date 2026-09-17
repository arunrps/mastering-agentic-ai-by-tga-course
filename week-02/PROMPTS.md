# Week 2 — Prompt Log

Every prompt recorded verbatim, with a summary of the response. Appended as work proceeds, not
reconstructed afterwards.

**From Prompt 7 onward each entry also carries a DESIGN RATIONALE block.** A verbatim prompt
records what was asked and the code records what was produced; neither records *why*. The
rationale block holds the decisions, the alternatives rejected and the reason, anything found in
the data that changed the approach, and anything fixed in the first attempt. It is written for a
reader three months out with no code in front of them.

Prompt 7's block was written retroactively, at the end of that session rather than during it.
Later entries are written as the work happens.

---

## Prompt 1 — 2026-08-21 — Write RB-PAY-000

### Prompt (verbatim)

```
Standing instruction for this session: append every prompt I send, verbatim, plus a 
one-paragraph summary of your response, to my-work/week-02/PROMPTS.md. Do this as 
we go, not at the end. This is a graded deliverable and cannot be reconstructed 
afterwards.

## Context

I'm building the corpus for a RAG system over incident runbooks. Read 
my-work/week-02/CORPUS_MANIFEST.md in full before doing anything — it is the 
build spec and it explains why the corpus is shaped the way it is. Also read 
my-work/week-02/topology.json, which holds the runbook IDs the corpus joins on.

The system this corpus serves: a deterministic detector examines API gateway 
telemetry and produces a verdict (which endpoint x backend slice is elevated, 
against what baseline, with what evidence). That verdict becomes a structured 
context request which drives retrieval. The retrieved runbook tells an on-call 
engineer what to check next.

Retrieval must connect observed evidence to general procedure. It must never 
retrieve the answer.

## This task

Write ONE document: RB-PAY-000, the payment-service service runbook. Just this one. 
It is the quality benchmark the other fourteen will be measured against, so it is 
worth getting right before generating the rest.

Path: my-work/week-02/corpus/internal/RB-PAY-000.md

## Requirements

Follow the frontmatter schema in manifest §2 exactly — every field, no omissions.
Follow the structure in manifest §6: ## Symptoms, ## Discriminating checks, 
## Escalation, ## Related documents. 400-900 words.

Content requirements specific to this document:

- Cover FOUR symptom classes and keep them genuinely distinct: elevated 5xx alone; 
  elevated latency alone; both together; neither elevated but a report of trouble. 
  Each needs its own discriminating checks.
- The "both together" class should describe latency-preceding-errors as a 
  recognised pattern worth noting — as a general diagnostic principle, with the 
  reasoning for why it happens. NOT as a description of any specific incident.
- Include guidance on what it means when a sibling endpoint on the same backend 
  degrades at the same time, versus when it doesn't. This is the corroboration 
  signal.
- Reference POL-DEPLOY-001 for change-related investigation, but do not reproduce 
  its content — that document is access_level: restricted and the separation 
  matters.
- Cross-reference RB-PAY-001 and RB-PAY-002 by document_id.

## Hard constraints — read manifest §1

This document must contain NO version strings from the dataset, NO incident 
timestamps, NO claim that any particular service or deploy caused anything. It 
describes classes of failure and the checks that discriminate between them.

It must also NOT cover: host metrics, database internals, connection pools, queue 
depth. Those gaps are deliberate and load-bearing — they are what the refusal path 
is tested against. If a check would naturally reference a database, phrase it as 
escalating to the owning team rather than describing what to look at.

## Voice

Flat, procedural, mildly bureaucratic. Real runbooks are not well written. A 
document that reads like polished technical marketing is a tell that it was 
generated. Some sentences should be slightly awkward. Include a review date that 
is a few months old.

## Before you write

Tell me:
1. Your four symptom classes and the discriminating check that separates each pair 
   — I want to see the discrimination logic before the prose
2. Anywhere the manifest is ambiguous or self-contradictory
3. Anything you'd naturally have written that the §1 constraints forbid, so I can 
   confirm the constraint rather than have you silently work around it

Then write it.
```

### Response summary

Read `CORPUS_MANIFEST.md` and `topology.json` in full, then reported the discrimination logic
before writing. Four classes: errors-only, latency-only, both, neither-but-reported. Pairwise
separators: class 1 vs 2 by the time-to-failure of the failing requests themselves (fast returns
mean rejection before expensive work; returns at a timeout ceiling mean misclassified slow work);
1 vs 3 by whether p95 crosses at all and in what order; 2 vs 3 by whether the error count clears
the POL-SLO-001 minimum evidence floor, as a threshold rule rather than a judgement; and 1/2/3 vs
4 by whether the reported scope is narrower than the aggregate (tenant, client build, region) or
concerns correctness rather than availability, which the two series cannot express by
construction. Flagged eight manifest issues, of which four are blocking for later build steps: the
`RB-CAT-001` ID collision between manifest §3 (`/search`) and topology (`/products`); three
topology join keys (`RB-INV-001`, `RB-INV-002`, `RB-CAT-002`) with no document assigned in §3;
"15 documents" actually being 16 once `RB-PAY-000-v2` is counted; and §3's "dependency health
checks" having almost nothing legal to point at given §4.4's gaps plus topology's declaration that
no downstream dependencies exist — resolved by restricting dependency material to in-platform
components and framing dependency confirmation as an escalation. Also flagged the tension between
§4.2's planted partial-answer case and the brief's request for corroboration guidance here,
resolved by keeping this document's treatment at backend-level generality and pointing to
`RB-PAY-002` for endpoint-pair specifics. Named three things the §1 constraints forbade that would
otherwise have been written: a rollback step, inlined SLO numbers, and the entire conventional
second half of a payment runbook (pools, slow queries, restarts, backlog, host metrics) — all
converted to escalation lines. One deliberate deviation from §2's literal example: `supersedes` is
set to `RB-PAY-000-v2` rather than `null`, so the supersession link is bidirectional and the field
is not dead corpus-wide; a one-line revert if not wanted. Wrote
`corpus/internal/RB-PAY-000.md` at 899 words, full frontmatter, the four §6 sections, the
latency-precedes-errors mechanism stated as a general timeout/threshold principle with the reverse
ordering noted separately, the corroboration signal including the caveat that a quiet low-volume
sibling is not exoneration, `POL-DEPLOY-001` referenced without reproduction, and `RB-PAY-001` /
`RB-PAY-002` cross-referenced by ID. Grep-verified clean of dataset version strings, incident
timestamps, causal attribution, and the §4.4 gap topics.

---

## Prompt 2 — 2026-08-21 — Write the other three service runbooks

### Prompt (verbatim)

```
RB-PAY-000 is accepted as the pattern. Now write the other three service runbooks 
in one pass:

- RB-INV-000 — inventory-service
- RB-CAT-000 — catalog-service  
- RB-AUTH-000 — auth-service

Same frontmatter schema, same four-section structure, same voice. All at 
my-work/week-02/corpus/internal/.

## Keep the shared skeleton

Manifest §4.5 is explicit: these documents SHOULD read as near-duplicates of each 
other. Shared structure and shared vocabulary — "elevated 5xx", "escalate to the 
owning team", "verify the evidence floor" — are what make retrieval precision a 
real problem worth solving with metadata filtering. Do not artificially 
differentiate them for readability. If a check is genuinely the same check, phrase 
it the same way.

## Where they must genuinely differ

Each service has a failure signature the others don't:

**RB-INV-000 (inventory-service, /cart and /orders).** Stock lookup timeouts, cache 
staleness, and the divergence case — cart contents disagreeing with what the order 
path sees. Correctness failures that are invisible in 5xx and latency matter more 
here than anywhere else.

**RB-CAT-000 (catalog-service, /products and /search).** Read-heavy, high volume. 
The core discrimination is capacity versus fault: latency that scales with request 
volume is a capacity question, latency that doesn't is a fault question. Also 
search index lag — stale results returned successfully, so no error signal at all.

**RB-AUTH-000 (auth-service, /login).** Fast-fail behaviour: this service can 
produce a strong error signal with p95 on successful requests staying flat, because 
rejection is cheap. State that as a general principle — an incident does not 
require latency and errors to move together. Also the 401-versus-5xx distinction: a 
surge of 401s is usually a client-side or credential problem, not a backend outage, 
and the two must not be conflated.

## Constraints — unchanged

Manifest §1 applies. No dataset version strings, no incident timestamps, no claim 
that anything caused anything. No host metrics, database internals, connection 
pools, or queue depth — escalate to the owning team instead.

400-900 words each. Cross-reference endpoint runbooks and policies by document_id. 
Vary last_reviewed dates across the three; some services get reviewed more often 
than others and staleness is a realistic signal.

## Before you write

For each of the three, tell me the one discriminating check that would be wrong to 
copy from RB-PAY-000 — the place where payment-service logic actively misleads for 
that service. Then write all three.
```

### Response summary

Named the misleading check for each service before writing. For RB-INV-000 it is RB-PAY-000's
class-4 procedure: payment narrows scope first and tests correctness second, but cart/order
divergence is platform-wide rather than scoped to a tenant, build or region, so the scope pass
returns nothing and the report gets closed as invisible-in-aggregate. Inventory therefore checks
correctness first and treats scope-narrowing as the weak follow-up; the same family of error makes
payment's "fast response means cheap rejection" heuristic wrong here, because a fast *successful*
response is the signature of a cache serving stale data. For RB-CAT-000 it is payment's class-2
entry condition — an objective breach read as a latency fault. Catalog cannot classify on latency
at all, only on latency normalised against request volume, so the capacity-versus-fault check runs
before everything else; sibling corroboration is confounded for the same reason, since a traffic
surge degrades both endpoints at once and payment's "both moved, therefore shared backend"
inference produces a false positive as its normal case. For RB-AUTH-000 it is the class-3 ordering
principle applied as a corroboration requirement: payment's mechanism assumes a caller timeout
converts slowness into errors, but auth rejects cheaply, so a severe condition produces errors
with p95 flat and an engineer waiting for the latency curve under-rates severity indefinitely.
Auth also needs a 4xx/5xx split as a pre-classification step, since payment's class definitions
treat "error rate" as a single series and a 401 surge would otherwise enter triage as a backend
incident. Wrote all three at 898, 897 and 897 words, full frontmatter, the four §6 sections, and
the §4.5 shared skeleton preserved deliberately — the scope paragraph, the four class definitions,
the POL-SLO-001 evidence-floor line, the class-1/2/3 pairwise checks, the sibling-corroboration
paragraph, the change-correlation paragraph and the escalation shape are near-identical across all
four documents, with divergence confined to the service-specific check and to explicit
here-it-differs qualifiers inside the shared paragraphs. Varied staleness: RB-AUTH-000 v4.0
reviewed 2026-07-22, RB-INV-000 v2.2 reviewed 2026-04-30, RB-CAT-000 v1.7 reviewed 2025-11-18.
Endpoint cross-references follow topology.json numbering rather than manifest §3, since topology
declares itself the authority on runbook IDs — so RB-CAT-000 points at RB-CAT-001 (/products) and
RB-CAT-002 (/search), and RB-INV-000 points at RB-INV-001 (/cart) and RB-INV-002 (/orders).
Grep-verified all four clean of dataset version strings, incident timestamps, causal attribution
and the §4.4 gap topics.

---

## Prompt 3 — 2026-08-21 — Write all seven endpoint runbooks

### Prompt (verbatim)

```
All four service runbooks are accepted. topology.json wins on runbook IDs, so the 
corpus is 19 internal documents, not 15 — I'll update the manifest.

Now write all seven endpoint runbooks in one pass, at 
my-work/week-02/corpus/internal/:

- RB-PAY-001 (/checkout) · RB-PAY-002 (/refunds)
- RB-INV-001 (/cart) · RB-INV-002 (/orders)
- RB-CAT-001 (/products) · RB-CAT-002 (/search)
- RB-AUTH-001 (/login)

## Length — change from the last batch

The last three came in at 898, 897 and 897 words. That uniformity is a generation 
artifact and it makes a corpus feel synthetic in a way a reviewer notices without 
being able to name.

Range is now 300 to 1200 words, and I want the spread to be deliberate and 
explainable. A stable endpoint nobody has touched in two years has a short runbook. 
An endpoint that has caused three incidents has a long one that grew by accretion, 
with a section that reads like it was bolted on after a postmortem. Decide which is 
which before writing, and tell me your reasoning.

## What an endpoint runbook is for

It is NOT the service runbook again with a different path in it. If an endpoint 
runbook could be deleted without losing anything, it should not exist. Each one 
carries what is true of that endpoint and not of its siblings: its shape of 
operation, its volume profile, its characteristic failure, what a responder gets 
wrong about it specifically.

The service runbook classifies. The endpoint runbook says what to look at once the 
class is known.

Structure can be lighter than the service runbooks — ## Symptoms / ## Discriminating 
checks / ## Escalation / ## Related documents is available but not mandatory. A 
short one might be two sections. Real runbooks are not uniform.

## Required content per document

**RB-PAY-001 (/checkout).** A composite operation — several steps behind one 
request. Covers single-endpoint degradation thoroughly. **Manifest §4.2: it must 
say NOTHING about what it means when a sibling endpoint on the same backend 
degrades at the same time.** That is deliberately absent here and carried by 
RB-PAY-002. Do not add a cross-reference that patches the gap — the gap is the test.

**RB-PAY-002 (/refunds).** Carries the sibling-corroboration guidance /checkout 
lacks. Lower volume than /checkout, and this is where the evidence-floor problem 
lives: a low-volume endpoint can carry a real fault and still fail to clear the 
minimum failure count, so a clean verdict on /refunds is weaker evidence than a 
clean verdict on /checkout. State that as a general property of low-volume slices.

**RB-INV-001 (/cart).** Read-heavy, session-scoped, cache-fronted. The source side 
of the cart/order divergence in RB-INV-000.

**RB-INV-002 (/orders).** The other side of that divergence. Write path, so a 
failed request may or may not have left state behind — retry safety is a real 
question here and nowhere else in the corpus.

**RB-CAT-001 (/products).** Product detail reads, heavily cached. The stable one, 
probably. Short.

**RB-CAT-002 (/search).** Highest request volume on the platform. The 
characteristic trap: absolute failure counts look alarming while the rate is 
unremarkable, because volume is large. A responder reading raw failure counts on 
this endpoint reaches the wrong conclusion. State it as a general principle about 
rate versus count on high-volume slices.

**RB-AUTH-001 (/login).** Low absolute failure counts are normal here and not by 
themselves actionable — RB-AUTH-000 defers this to you, so carry it properly. Also 
the 4xx/5xx split at endpoint level.

## Constraints — unchanged

Manifest §1: no dataset version strings, no incident timestamps, no causal 
attribution. Manifest §4.4 gaps: no host metrics, database internals, connection 
pools, queue depth — escalate to the owning team instead.

Vary last_reviewed and version realistically. An endpoint that caused incidents 
gets reviewed more often than one that didn't.

## Length — change from the last batch

The last three came in at 898, 897 and 897 words. That uniformity is a generation 
artifact and it makes a corpus feel synthetic in a way a reviewer notices without 
being able to name.

Range is now 700 to 1500 words, and I want the spread across that range to be 
deliberate and explainable. An endpoint that has caused three incidents has a long 
runbook that grew by accretion — including a section that reads like it was bolted 
on after a postmortem, in a slightly different voice from the rest. A stable 
endpoint sits near the floor. Decide which is which before writing, and tell me 
your reasoning.

Do not land three documents within ten words of each other again.
```

### Response summary

Flagged that the prompt carries two incompatible length ranges — 300–1200 in the first Length
section and 700–1500 in the repeated one at the end, with both overriding manifest §6's 400–900 —
and resolved it by targeting the intersection, 700–1200, so that every document satisfies whichever
range was intended and none needs rewriting. Assigned lengths before writing with stated reasoning:
/checkout longest as the composite, highest-impact, incident-generating endpoint; /orders second as
the write path where retry safety has no clean answer; /search medium-long for one well-understood
high-volume trap; /refunds medium carrying two pieces of doctrine; /login medium-short as a
deliberate non-correlation between review cadence and length, since it is reviewed most recently
of the eleven but has only two lessons; /cart shorter than its write-path sibling; /products
shortest, stalest and lowest-versioned as the stable one. Landed at 1194, 1054, 934, 895, 797, 750
and 725 words, closest pair 25 apart. Structure was varied rather than uniform: RB-PAY-001 and
RB-INV-002 carry five sections each with an accreted block — a "Partial completion" section on
/checkout written in a looser first-person-plural voice and explicitly dated to a review, and a
numbered "Retry decision" checklist on /orders that does not match the prose around it and says so
— while RB-CAT-001 replaces Symptoms and Discriminating checks with a single "Symptoms and checks"
section plus a "Known non-issues" list, which is the shape a stale, low-traffic runbook actually
takes. On the §4.2 gap, decided that RB-PAY-001 would not list RB-PAY-002 in Related documents at
all, on the grounds that even a bare cross-reference is followable by the retrieval layer and would
patch the gap; /refunds is not named anywhere in /checkout's runbook, verified by grep. RB-PAY-001
still covers endpoint-versus-backend discrimination as manifest §3 requires, but by two
sibling-free routes: which step of the composite is degraded, and the endpoint's own series
compared against the backend aggregate adjusted for traffic share. RB-PAY-002 does name /checkout
and does link back to RB-PAY-001, which leaves the synthesis test live in the direction that
matters. Endpoint-specific content that could not be deleted without loss: composite step
attribution, budget exhaustion and declines-misreported-as-5xx on /checkout; the low-volume
evidence-floor asymmetry and support-led reporting on /refunds; cache-bypass reasoning, session
scope and the sign-in cart merge on /cart; rejection-against-failure, multi-item partial outcomes
and the retry checklist on /orders; rate-against-count, query mix and non-customer traffic on
/search; retry inflation and 4xx composition on /login; known non-issues on /products. Verified all
eleven internal documents clean of dataset version strings, incident timestamps, causal
attribution and the §4.4 gap topics, with 11/11 frontmatter fields present in each.

---

## Prompt 4 — 2026-08-21 — Three policies and two catalog documents

### Prompt (verbatim)

```
Eleven runbooks are done and committed. Now the three policies and two catalog 
documents. Same directory.

- POL-SLO-001 — objectives and alerting policy
- POL-SEV-001 — incident severity and escalation matrix
- POL-DEPLOY-001 — deployment validation and rollback policy
- CAT-OWN-001 — service ownership matrix
- CAT-DEP-001 — endpoint dependency map

## Critical: POL-SLO-001 must match the detector

Every one of the eleven runbooks defers to POL-SLO-001 for objectives and the 
minimum evidence floor. That floor is not fictional — it is implemented in 
my-work/week-01/detection.py as EVIDENCE_RULES, and the policy must state the same 
numbers:

    minimum_requests: 200
    minimum_failures: 10
    minimum_5xx_rate: 0.01
    minimum_baseline_multiplier: 3.0
    consecutive_buckets_required: 2

Read detection.py to confirm these before writing. If they have drifted, the file 
wins and tell me.

The policy must also explain the reasoning the runbooks keep gesturing at: why a 
floor exists at all (alert fatigue, and low-volume slices producing meaningless 
rates), why it is a threshold rule and not a judgement, and — this is the part the 
runbooks reference but never explain — why a "not elevated" verdict on a 
low-volume slice is weaker evidence than the same verdict on a high-volume one.

Also state per-service SLOs. Read my-work/week-02/topology.json, which declares 
slo_p95_latency_ms and slo_max_5xx_rate_pct per backend, and use those numbers.

One deliberate gap: the runbooks ask for baselines matched on daily and weekly 
shape. The policy should state that requirement without specifying how a baseline 
is computed when insufficient history exists. That gap is real and I want it 
visible.

## POL-SEV-001

Severity definitions, blast-radius thresholds, paging rules, comms expectations. 
RB-CAT-002 says blast-radius thresholds are "expressed in a way that accounts for" 
high-volume endpoints — deliver on that: thresholds in affected-request terms, not 
just rate terms.

RB-AUTH-001 routes credential-abuse patterns here as a security escalation rather 
than an operational one. Cover that path.

RB-PAY-000 has a fifteen-minute rule for sustained class 3; no other runbook has a 
time-based trigger. Either justify that as a policy (payments escalate faster) or 
generalise it. Tell me which you chose.

## POL-DEPLOY-001 — access_level: restricted

This is the authorization test case. Eleven runbooks reference it and none 
reproduces it.

Content: post-deploy validation window, what evidence justifies a rollback, who 
authorises one, and — the important part — why a rollback must never be treated as 
proof of cause. A system that recovers after a rollback has not demonstrated the 
deploy caused the failure; it has demonstrated that the two are consistent with 
each other. Be explicit and give the reasoning.

Manifest §1 still applies: no dataset version strings, no incident timestamps, 
nothing that resolves any specific incident.

## CAT-OWN-001 and CAT-DEP-001

Ownership: service → owning team → escalation contact → business hours → 
out-of-hours arrangement. Teams are payments-platform, fulfilment-core, 
catalog-discovery, identity-access.

Dependency map: endpoint → backend, from topology.json. It must carry the caveat 
the runbooks all repeat — it reflects declared topology and may drift from observed 
traffic — and should say what to do when it does.

CAT-DEP-001 is the natural place for a small realistic error. Include ONE stale 
entry: an endpoint listed with a note that is out of date, or a team name that has 
changed. Mark nothing; the point is that a reader who cross-checks against 
topology.json finds it. Tell me which one you planted.

## Length and voice

400 to 1200 words, varied. Policies read differently from runbooks — more formal, 
more passive, more "must" and "shall". CAT-OWN-001 can be mostly a table and quite 
short. Vary version and last_reviewed; POL-DEPLOY-001 should be the most recently 
reviewed, POL-SEV-001 the stalest.

Frontmatter schema unchanged. document_type: policy or catalog as appropriate.
```

### Response summary

Read detection.py before writing and confirmed no drift: all five named thresholds match the file
exactly. Reported that the supplied list is nonetheless incomplete and structurally flattened — the
implemented gate is two-stage with three outcomes, not one floor with two. Stage 1 preconditions
(minimum_requests 200, evaluable_buckets 2, baseline_minimum_requests 200, baseline_minimum_failures
5) yield NOT EVALUABLE; stage 2 (minimum_failures 10, minimum_5xx_rate 0.01,
minimum_baseline_multiplier 3.0, consecutive_buckets_required 2) yields EVIDENCE INSUFFICIENT; both
cleared yields EVIDENCE SUFFICIENT. minimum_requests is a stage 1 rule rather than part of the
evidence floor proper. Wrote all three outcomes into POL-SLO-001 because NOT EVALUABLE is the
actual mechanism behind the low-volume asymmetry the runbooks gesture at, and it is a stronger claim
than they make: a low-volume slice may yield no verdict at all rather than a weak clean one. Also
surfaced an interaction nothing in the corpus had yet stated — the declared SLO ceiling is 0.5% 5xx
while the evidence rate floor is 1%, so a slice can breach its objective and still fail the floor;
POL-SLO-001 §5 now states that objectives and the floor are different tests and that both halves of
that sentence are simultaneously true. On the baseline gap, reported that it is larger than
described: detection.py derives its baseline from a fixed early window of the dataset's own range,
never sliced by time, which is a different kind of baseline from the shape-matched one the runbooks
ask responders to use. POL-SLO-001 §7 states the shape-matching requirement, notes the
implementation divergence, and declares reconciliation out of scope, leaving the gap visible rather
than papered over. On the fifteen-minute rule, chose to generalise rather than justify: POL-SEV-001
§3 sets time-to-classification limits by severity tier (5/15/60 minutes, end of shift), so
RB-PAY-000's fifteen minutes becomes an instance of a general rule rather than a payments carve-out,
and payments still escalates fastest because §2 raises payment capabilities one severity level. No
edit to RB-PAY-000 was needed. POL-SEV-001 §2 expresses blast radius in affected-request counts with
rate conditions as an alternative trigger, higher severity winning on disagreement, which delivers
what RB-CAT-002 promised; §5 carries the security escalation path including the instruction not to
post suspected abuse patterns into general channels. POL-DEPLOY-001 is access_level restricted,
opens with a no-relay instruction, and its §4 argues at length that a rollback demonstrates only
consistency rather than causation, on the grounds that a rollback is itself a deployment with its
own side effects and is reliably the most recent event before any recovery. Planted stale entry in
CAT-DEP-001: /orders is attributed to order-fulfilment, a superseded name for fulfilment-core, while
/cart beside it is correct — findable both against topology.json and against CAT-OWN-001, and
readable as a half-finished rename. Deliberately avoided planting a wrong endpoint-to-backend
mapping, which would have corrupted the corroboration pair that manifest §4.2 depends on. Word
counts 1089, 946, 795, 519 and 429, none within ten words of another. All sixteen internal
documents now parse as YAML with the full eleven-field schema and remain clean of §1 and §4.4
violations.

---

## Prompt 5 — 2026-08-21 — The two postmortems and the superseded runbook

### Prompt (verbatim)

```
Sixteen documents done. Three remain and they are the hardest in the corpus:
PM-2026-014, PM-2026-009, and RB-PAY-000-ARCHIVED.

## PM-2026-014 — Shared-Backend Degradation Affecting Two Endpoints

Manifest §4 calls this the strongest document in the corpus, and the reason is 
delicate. It must teach the shared-backend pattern — two endpoints on one backend 
degrading together, latency leading errors — WITHOUT being about the incident the 
system will be asked to investigate.

So: different service, different endpoints, different resolution. Use 
catalog-service or inventory-service, not payment-service. The resolution must NOT 
be a deployment rollback. Find a mechanism that produces the same telemetry 
signature from a different cause entirely — something that degrades a backend 
without a change having been deployed.

The value is that the system can reason by analogy: "this shape resembles a 
documented prior incident on a different service." That is a different and better 
retrieval behaviour than fetching the answer.

It must also demonstrate the causal restraint the policies demand. Show the 
investigation reaching a wrong hypothesis first, and what evidence displaced it. A 
postmortem where the first guess was right is not a postmortem, it is a story.

Longest document in the corpus. 1500-2000 words.

## PM-2026-009 — Capacity Saturation During a Traffic Surge

Referenced by RB-CAT-000 and RB-CAT-002 as covering "the capacity shape." Latency 
rose, errors stayed near baseline, no deployment involved. The lesson: not every 
incident has a change to correlate against, and a responder hunting for one wastes 
the opening.

Include the reverse failure too — someone looked for a deploy, found an unrelated 
one, and lost time on it. That is the anchoring trap stated as history rather than 
instruction.

1000-1500 words.

## RB-PAY-000-ARCHIVED

Written last, derived from the current RB-PAY-000. Frontmatter:

    document_id: RB-PAY-000-ARCHIVED
    status: superseded
    supersedes: null
    superseded_by: RB-PAY-000
    version: "2.4"
    last_reviewed: 2025-03-02

Manifest §4.1: it must be semantically close enough to score well on vector 
similarity against the current version — same title shape, same structure, much 
shared vocabulary — while contradicting it in a VERIFIABLE, non-trivial way.

Three contradictions, no more:

1. A different evidence threshold. State an older, looser floor that a responder 
   following it today would apply wrongly. It must be specific and checkable 
   against POL-SLO-001.
2. An obsolete escalation route — a team name or channel that no longer exists. 
   Consider making it order-fulfilment, so it corroborates the stale entry already 
   planted in CAT-DEP-001. Two documents carrying traces of the same reorganisation 
   is what a real corpus looks like.
3. Something the current version says NOT to do, stated here as procedure. The 
   causal-attribution discipline is the obvious candidate: this version can be 
   comfortable saying a deploy caused a degradation, which is exactly what the 
   current version and POL-DEPLOY-001 forbid.

Do NOT mark it as outdated in the body. No warning banner, no "this is superseded" 
note in the prose. The only signal is the frontmatter. If a reader can tell from 
the text alone, the metadata filter has nothing to prove.

It should also be missing things the current version has — the class 4 definition, 
the NOT EVALUABLE concept, the sibling-corroboration nuance. Documents grow; this 
one is what payment-service triage looked like before those lessons.

800-1200 words.

## Constraints

Manifest §1 applies to all three, including the postmortems: no dataset version 
strings, no incident timestamps from the telemetry, nothing that resolves the 
system's live incident. Postmortems describe OTHER incidents.

The §4.4 gaps hold: where a postmortem's resolution would require host, database, 
or queue visibility, the narrative can say the owning team investigated and 
resolved it there — it must not describe what they looked at.

document_type: postmortem for the two PMs, runbook for the archived one.

## Before you write

Tell me the mechanism you chose for PM-2026-014 — how a backend degrades two 
endpoints, with latency leading errors, and no deployment involved. That is the 
crux of the document and I want to see it before the prose.
```

### Response summary

Presented the PM-2026-014 mechanism before writing: synchronised cache expiry on inventory-service
affecting /cart and /orders. Both endpoints consult the same cached inventory state — /cart to
display a basket, /orders to validate against before accepting a write — so the shared thing is
data rather than a code path, which lets the pattern hold even though the two endpoints exercise
substantially different routes, exactly as RB-INV-000 warns. Days before the incident a routine
bulk refresh rewrote a large population of entries in a short span, all receiving identical
lifetimes, so they expired together on a timer. At expiry a large share of requests on both
endpoints stopped being served from cache. Latency stepped immediately; errors lagged, because a
full lookup was slower but initially inside the callers' timeouts and only crossed the deadline as
the miss rate persisted — which reproduces the latency-leads-errors signature via the same timeout
mechanism RB-PAY-000 states as a general principle, with no deployment anywhere near the onset and
the cause having been set in motion days earlier by an operation nobody would call a change.
Resolution was repopulation by fulfilment-core plus a durable fix distributing lifetimes across a
range; no rollback, and POL-DEPLOY-001 never engaged. The wrong first hypothesis is that the write
path was primary and /cart collateral, adopted because /orders failures were louder and because
/orders is the endpoint the team treats as dangerous; it held for twenty-three minutes and was
displaced by onset ordering, /cart latency having stepped measurably before /orders moved at all,
with the cache hit rate falling in the same minute. Added a second recorded failure the brief did
not ask for: at T+0 only /orders cleared the evidence gate while /cart returned EVIDENCE
INSUFFICIENT on its error series, and the first written summary compressed that to "not elevated",
removing a degraded endpoint from the incident — the precise error POL-SLO-001 §6 warns against,
shown costing time rather than asserted. Placed PM-2026-014 on inventory-service and PM-2026-009 on
catalog-service so the two separate cleanly by metadata filter, and deliberately gave PM-2026-014 a
different wrong hypothesis from PM-2026-009's anchoring-on-an-unrelated-deploy trap so the two
postmortems teach distinct failures. PM-2026-009 records twenty-six of forty-eight minutes lost to
a deployment on an unrelated service, with the ordering lesson that the volume check should have
run before the change search and would have resolved it in under a minute, and closes with "no
action taken" as the correct record plus the reasoning that an intervention made shortly before an
unrelated recovery gets credited with it. RB-PAY-000-ARCHIVED derives structurally from the current
version with heavy shared vocabulary and an identical title, carries exactly three contradictions
— a five-failures-in-one-bucket evidence minimum with no baseline multiplier, checkable against
POL-SLO-001's ten failures over two consecutive buckets at 3.0x; an escalation to order-fulfilment
on `#order-fulfilment-oncall`, corroborating the stale CAT-DEP-001 entry and checkable against
CAT-OWN-001; and a change-correlation step instructing responders to record a deployment as the
cause and proceed to rollback, which the current version and POL-DEPLOY-001 both forbid — and omits
class 4, the NOT EVALUABLE concept and the sibling-corroboration negative-case nuance, with no
warning banner or superseded note anywhere in the body. Also corrected RB-PAY-000's supersedes
field, which still pointed at the earlier RB-PAY-000-v2 name and was left dangling by the rename.
Nineteen documents now parse with the full schema: 12 runbook, 3 policy, 2 catalog, 2 postmortem,
word counts 429 to 1745, all clean of §1 and §4.4 violations.

## Prompt 6 — 2026-09-05 — Verification pass on hardened Week 1

Triggered by an external review (ChatGPT) of the PUBLIC repo, which still carries
the 16 Aug submission rather than the hardened version. Four findings raised; two
survived in current code, two were already fixed by the hardening and were
confirmed rather than rewritten.

**Finding 2a — consumer interpretation. Real, fixed.** The brief appended
"...so this looks like traffic share rather than a consumer-specific fault"
whenever both consumer rates existed, with no condition testing what they were.
At 100% vs 0% it printed the same sentence.

The sentence was written when the real numbers were 19.72% vs 16.77%, where it
was defensible. It was never gated, so it outlived its own evidence. This is the
determinism boundary failing from the inside: the rule protects against a model
inventing figures, not against a human hardcoding a conclusion that was true once.
Deterministic means reproducible, not correct — and this failure is worse than a
hallucination because nothing looks wrong. Correct numbers, no exception, wrong
sentence.

Fixed by removing the conclusion and reporting counts alongside rates. No
replacement rule added — that needs a stated, tested threshold.

**Finding 2b — no-successful-request case. Real, fixed.** TypeError when p95 over
2xx returned None and the brief formatted it directly. Now renders an explicit
unavailable message.

**Findings 2c, 2d — already fixed by the hardening.** Three distinct verdict
headlines through the render path, no boolean collapse. All endpoint x backend
slices evaluated against their own baselines before ranking, verified against a
constructed masking case.

**Tests added — 49 passing.** The Streamlit boundary is asserted twice: a
subprocess import check immune to collection order, and a shell script running the
detection tests against an interpreter that cannot import Streamlit at all. The
/login assertion checks failed_rules == ["minimum_failures"] rather than status,
because a status-only assertion would pass even if the rate floor were raised.

---

## Prompt 7 — 2026-09-06 — Ingestion layer: scaffold, frontmatter, section-aware chunking

### Prompt (verbatim)

```
Week 2 build starts. This session is the ingestion layer only — no embeddings, no
retrieval, no LLM calls. Those come next.

Read my-work/week-02/CORPUS_MANIFEST.md and my-work/week-02/EVAL_QUESTIONS.md
first. The corpus is 19 internal documents at my-work/week-02/corpus/internal/.

Standing instruction 1: append every prompt verbatim plus a response summary to
my-work/week-02/PROMPTS.md as we go. Graded, cannot be reconstructed.

Standing instruction 2: make no API calls of any kind without asking me first.
This includes embeddings. I am on a fixed $50 Nebius credit and other people in
the cohort have overrun theirs. Before any run that spends credit, tell me the
estimated token volume and I will approve it. This session should cost nothing.

## Context

Week 2 is a SEPARATE application from Week 1. It shares the fictional platform and
the story, not the codebase. Build it in my-work/week-02/. Do not import from
week-01 — topology.json is already copied in.

The architecture principle from Week 1 holds and is why this project works:
deterministic code produces evidence, the model plans and narrates from what the
code returned. Applied here, retrieval and metadata handling are deterministic;
only the final answer generation is probabilistic, and it comes later.

## Task 1 — Scaffold

my-work/week-02/ needs:

- app.py — Streamlit entry point, minimal for now
- ingestion.py — corpus loading, frontmatter parsing, chunking. Must NOT import
  streamlit. Same boundary as detection.py in Week 1, and I will test it the same
  way.
- requirements.txt — CLEAN, minimal, deploy-only. This deploys to its own Streamlit
  Cloud app. Do not pip freeze. Week 1's public requirements.txt is 3 lines and
  that is the model.
- requirements-dev.txt — test dependencies, separate
- .streamlit/config.toml — theming, see task 4

## Task 2 — Ingestion

Load all 19 documents. For each:

- Parse YAML frontmatter into structured metadata. All eleven fields are present in
  every document: document_id, title, document_type, service, status, supersedes,
  superseded_by, owner_team, access_level, version, last_reviewed.
- Fail loudly on a missing or malformed field. A document that cannot be parsed is
  a build error, not a warning — silent metadata loss is how retrieval quietly
  degrades.
- Validate against topology.json: every document_id referenced as a runbook_id in
  topology should exist, and vice versa. REPORT mismatches, do not fail on them.
  The corpus deliberately contains references to documents that may not exist —
  check whether any dangling references remain.

## Task 3 — Chunking

Section-aware. The internal documents share a consistent structure — ## Symptoms,
## Discriminating checks, ## Escalation, ## Related documents, with some variation.
Split on those boundaries, not on a fixed character count.

Requirements:

- Every chunk carries the full parent document metadata, plus its section heading
  and its position in the document. Metadata filtering is core to this week's
  retrieval, so a chunk without metadata is useless.
- A chunk that exceeds a reasonable size for the embedding model splits further,
  but at paragraph boundaries, never mid-sentence.
- Short sections do not become their own chunks if that would strand them — decide
  a minimum and tell me what you chose.
- The ## Related documents section is metadata, not prose. Decide whether it should
  be indexed at all and justify your choice; my instinct is that it should be
  parsed into structured links rather than embedded as text, but argue with me if
  you disagree.
- Chunking must be deterministic and repeatable. Same input, same chunks. I will
  re-run this and the output must not drift, because re-embedding costs money.

## Task 4 — Theming, minimal for now

.streamlit/config.toml, light neutral operations console:

  backgroundColor #F6F8FB, secondaryBackgroundColor #FFFFFF, textColor #172033
  primaryColor #2563EB, sidebar backgroundColor #0F172A
  base "light", font "sans-serif"

Red (#DC2626) is reserved for genuinely elevated states and must not be the widget
accent. In Week 1 red filter chips made every selection look alarming, which
destroyed red's signal value.

Full page layout comes later. Just get the theme file in place.

## Task 5 — Report, do not guess

After ingestion runs, print:

- documents loaded, and any that failed
- chunks produced, total and per document
- chunk size distribution in CHARACTERS: min, median, max, and the count over your
  split threshold
- chunk size distribution in TOKENS, using a real tokenizer rather than a
  characters-divided-by-four estimate, and the TOTAL token count across all chunks.
  This is my embedding cost estimate — I need the actual number, not an
  approximation.
- the metadata cardinality: how many distinct services, document_types, statuses,
  access_levels
- any topology cross-check mismatches
- any dangling document references found in ## Related documents sections

## Before you write

Tell me:

1. Your chunking strategy in three sentences, including the size target. Name the
   SPECIFIC embedding model you propose, one actually available on Nebius, with its
   context window and output dimension, and explain why your chunk size matches
   that capacity. Do not say "a typical embedding model" — the choice of chunk size
   and embedding model is one decision, not two, and it determines what I spend.
2. What you plan to do with ## Related documents and why
3. Anything in the corpus structure that will make chunking awkward — I would
   rather know now than discover it in retrieval quality

Then build.
```

### Response summary

Answered the three questions from measurement rather than assumption, then built. **The
premise in Task 3 that the corpus shares a consistent Symptoms/Discriminating checks/
Escalation structure is only true for 11 of 19 documents**, and a splitter written against
those four headings would produce garbage for the other 8: the three policies use numbered
headings `## 1.` to `## 8.`, the two catalog documents use capability headings plus
`## Accuracy caveat`, and the two postmortems are narrative with 9 and 10 sections. Even
inside the 11, RB-CAT-001 collapses to `## Symptoms and checks` and adds `## Known
non-issues`, RB-INV-002 adds `## Retry decision`, RB-PAY-001 adds `## Partial completion`.

**Three structural hazards found by inspection.** First and worst: every document carries
untitled text between `# Title` and the first `##`, 170 to 1,181 characters, and the obvious
implementation — iterate `##` sections — discards it silently. RB-AUTH-000's 1,181-character
preamble carries the "rejection is cheap, so a severe condition raises errors while p95 stays
flat" principle and the 4xx/5xx split warning, which is what evaluation Q5 needs; the corpus
would have lost its answer to a graded question with nothing looking wrong. It is now an
`(overview)` section. Second: the `Related documents` heading is numbered in the three
policies, so an exact-string match misses them, leaving their links unparsed AND their link
lists embedded as prose. Matching is on a normalised heading. Third: `## Discriminating
checks` is systematically the largest section — all 11 runbooks, 2,063 to 3,439 characters,
every one over any sane cap — and it is the section retrieval most needs. Mitigated by its
own structure: each is a series of `**Class 1 against class 2.**` bold-led paragraphs, so
splitting on paragraph boundaries cuts between checks rather than through one.

**Agreed on `## Related documents` — parsed into structured links, never embedded.** The
reasons are measured, not stylistic: each section is 87 to 271 characters of document IDs and
titles that appear verbatim elsewhere, making them the highest-similarity lowest-information
chunks in the corpus; POL-SLO-001 is referenced by 18 of 19 documents, so embedding all
nineteen lists would manufacture nineteen near-identical vectors, a distractor set on top of
the near-duplicates the manifest plants deliberately. The gloss text is kept rather than
discarded, because several runbooks mark the target `(restricted)` and that is the corpus
stating a document exists but is not reproduced.

**On the embedding model, pushed back on the framing.** Proposed `BAAI/bge-en-icl` on Nebius
(4,096 dimensions, 32,768-token context) but stated plainly that chunk size does not and
should not "match that capacity": 32,768 tokens is about 130,000 characters and the entire
corpus is 114,540, so the whole thing fits in one context window and every chunk is roughly
1.5% of what the model accepts. Sizing to capacity would produce one chunk per document and
destroy retrieval precision. The binding constraint is that a chunk must be one idea. Chose
target 1,200 characters, hard cap 2,000, minimum section 350.

**A measurement that turned a best-effort promise into a structural one:** the largest atomic
blank-line-delimited block anywhere in the corpus is 1,397 characters (PM-2026-014's numbered
lesson). Under a 2,000-character cap no block is ever forced to split, so "never mid-sentence"
holds by construction and the module contains no sentence-splitter fallback because nothing
can reach one. RB-INV-002's retry checklist (557 chars, must not split) and all three tables
(largest 711) are each single blocks and survive intact.

**Two defects found and fixed in my own first output.** Greedy packing stranded five tails of
168 to 289 characters — the same stranding the 350-character section minimum prevents, one
level down between pieces of a section — and RB-INV-002's "Bulk retries are never authorised"
rule was landing alone, separated from the checklist it qualifies. Tails now fold back when
the join fits under the cap. Separately, the topology cross-check reported
RB-PAY-000-ARCHIVED as a mismatch; it is superseded, and a catalog still pointing at it would
be the actual defect, so only current runbooks are expected to be declared. Reporting a
by-design state as a mismatch trains the reader to ignore the one line that would show real
drift.

**Result: 19 documents, 106 chunks**, min 358 / median 881 / max 1,855 characters, none over
the hard cap and none under the minimum. No topology mismatches, no dangling references across
104 parsed links. Verified: `import ingestion` leaves `streamlit` out of `sys.modules`;
chunking is byte-identical across three runs (sha256 over all chunk text and IDs); every chunk
carries all eleven metadata fields; no `Related documents` text reaches any chunk; chunk IDs
derive from `document_id` not title, because RB-PAY-000 and RB-PAY-000-ARCHIVED share a title
by design and title-derived IDs would collide.

**Token counts deliberately NOT produced.** No tokenizer is installed and no HuggingFace cache
exists, and printing a characters-divided-by-four figure was refused: an estimate presented as
a token count is a guess that looks like a measurement, which is precisely the Week 1
consumer-sentence failure in a new place. The report says the number is unavailable and how to
get it. Downloading the tokenizer spends no API credit but is a network fetch, so it was left
for approval under standing instruction 2.

### Design rationale

*Written retroactively at the end of the session. Everything below is a decision that is not
visible in the code, or is visible only as a constant whose value looks arbitrary.*

**What exists after this session.** A module, `ingestion.py`, that reads the 19 corpus documents
off disk and turns them into 106 chunks, each carrying its parent document's full frontmatter.
It parses `## Related documents` sections into a link graph instead of text, cross-checks the
corpus against `topology.json`, and prints a report. Nothing is embedded, nothing is indexed,
nothing is retrieved, and no API call of any kind was made. The module does not import Streamlit
and never will.

---

#### 1. Why chunk size is set in characters by section structure, and not by the embedding model

The received advice is to size chunks to the embedding model's context window. Here that advice
is not just unhelpful, it is actively wrong, and the numbers say so plainly.

| | |
|---|---|
| Whole corpus on disk | **114,540 characters** (19 files, frontmatter included) |
| Corpus body, frontmatter stripped | **108,917 characters** |
| `BAAI/bge-en-icl` context window | **32,768 tokens ≈ 130,000 characters** |

**The entire corpus fits inside one context window with room left over.** Not one document — all
nineteen. A 1,200-character chunk is roughly 300 tokens, which is about 0.9% of what the model
will accept.

The "match chunk size to model capacity" heuristic comes from an era of 512-token encoders, where
capacity genuinely was the binding constraint and a long passage had to be cut to fit. That
constraint is gone here by two orders of magnitude. Following the heuristic literally would mean
one chunk per document: 19 vectors averaging 5,700 characters each. Retrieval would then return
whole documents, which is the same as having no retrieval — and the planted partial-answer test
(`RB-PAY-001` covers single-endpoint degradation, `RB-PAY-002` carries the sibling-corroboration
half) becomes untestable, because both halves would arrive inside single monolithic chunks
regardless of what the question asked.

**What actually binds is that a chunk must be one idea.** A vector is an average of everything in
the text it encodes. Put a symptom list and an escalation procedure in one chunk and you get a
vector that sits between the two and matches neither strongly. Retrieval precision — not model
capacity — is the constraint, and precision is a property of the corpus's own structure.

So the sizing was derived by measuring the corpus rather than by reading a model card. After
`## Related documents` is removed, the corpus holds **100 sections**: minimum 167 characters,
median 804, maximum 3,439. Eleven sections exceed 2,000 characters and ten fall under 350. That
distribution produced three constants:

- **Target 1,200 characters** — above the median section, so most sections emit as a single chunk
  and are never cut at all.
- **Hard cap 2,000 characters** — the eleven oversized sections split; nothing else does.
- **Minimum 350 characters** — below this a chunk is one or two sentences, and in this corpus
  that means a vector dominated by the vocabulary every document shares ("elevated 5xx",
  "escalate to the owning team", "classification only, not remediation"). It would match
  everything weakly, nothing strongly, and crowd the result list. Sections under the minimum are
  merged forward into the next section instead.

**The embedding model's job in this decision is much smaller than the framing suggested.** Its
window only has to be *big enough*, and every candidate is, by a wide margin. It was chosen for
English retrieval quality, for behaving predictably in a hybrid BM25 + dense setup, and for
having a published tokenizer so the token count can be exact rather than estimated.

**A consequence worth remembering:** because chunk sizes are expressed in characters and driven
by section structure, **the model can change without re-chunking.** Switching from `bge-en-icl`
to `bge-multilingual-gemma2` or `e5-mistral-7b-instruct` alters three constants and the token
report and produces the identical 106 chunks. That matters because re-embedding costs money, and
it means the model decision — still open at the end of this session, pending confirmation of what
is actually live on the Nebius account — cannot invalidate the work already done.

---

#### 2. Why `## Related documents` became structured links instead of embedded text

Every one of the 19 documents ends with a `## Related documents` list, between **87 and 369
characters**, in the form `- POL-SLO-001 — objectives and alerting policy`. Across the corpus
there are **104 such references**.

They point at a very small number of targets:

| Target | Referenced by |
|---|---|
| `POL-SLO-001` | **18 of 19 documents** |
| `POL-SEV-001` | 17 of 19 |
| `CAT-OWN-001` | 16 of 19 |
| `POL-DEPLOY-001` | 12 of 19 |

**Embedded, these would be the highest-similarity and lowest-information chunks in the corpus.**
Nineteen short passages, each built from the same handful of document IDs and the same short
glosses, differing mainly in which two or three lines they add. They would score well against any
query naming a service or a policy — because the IDs and titles are literally in the text — and
return no procedure whatsoever. The engineer asking "checkout is throwing 503s, where do I start"
would get back a list of filenames.

Worse, they would be a **distractor set I manufactured**, sitting on top of the near-duplicate
distractors the corpus plants deliberately (manifest §4.5: the four service runbooks share their
scope paragraph, class definitions and escalation shape on purpose, to test whether metadata
filtering rescues precision where pure similarity cannot). Adding nineteen accidental
near-duplicates would contaminate the measurement of the deliberate ones. The corpus is an
instrument; this would have miscalibrated it.

**As structured links they are worth strictly more than as text.** They give a followable graph
for the sibling-document case, and they are the only mechanism by which a dangling reference is
detectable at all — the check that this session ran, finding zero.

One deliberate refinement rather than a straight discard: **the gloss text is kept.** Several
runbooks write `POL-DEPLOY-001 — deployment validation and rollback (restricted)`. That
parenthetical is the corpus stating that a document *exists* but is *not reproduced here* — which
is exactly the distinction the restricted-refusal path has to make later ("relevant guidance
exists but is above your access level", as opposed to "the corpus contains nothing on this"). It
would have been thrown away by a parser that kept only the IDs.

---

#### 3. The five structural problems found in the corpus

The prompt described the corpus as sharing a consistent `## Symptoms` / `## Discriminating
checks` / `## Escalation` / `## Related documents` structure. **That is true for 11 of the 19
documents.** Everything below was found by reading the actual files before writing the splitter.

**(1) The corpus is not uniformly structured, and a naive splitter breaks eight documents.**
The three policies number their headings, `## 1. Declared objectives` through `## 8. Related
documents`. The two catalog documents use capability headings — `## Payment capabilities`,
`## Fulfilment capabilities` — plus `## Accuracy caveat` and `## Notes`. The two postmortems are
narrative, with 9 and 10 sections each (`## Timeline`, `## The hypothesis that was wrong`,
`## Mechanism`). And even inside the 11 runbooks there are three one-offs: `RB-CAT-001` collapses
symptoms and checks into a single `## Symptoms and checks` and adds `## Known non-issues`;
`RB-INV-002` adds `## Retry decision`; `RB-PAY-001` adds `## Partial completion`. A splitter
written against the four expected headings would have produced garbage for eight documents and
silently mangled three more.

**(2) The untitled preamble — the most dangerous thing in the corpus, and the one that would have
failed silently.** Every document carries text between its `# Title` line and its first `##`
heading, ranging from **167 to 1,174 characters**. The obvious implementation — iterate the `##`
sections — discards all of it.

`RB-AUTH-000`'s preamble is **1,174 characters** and it is not boilerplate. It contains the
scope note, and then two warnings that the rest of the document depends on:

- **Rejection on auth-service is cheap.** Token validation that fails does so without doing the
  work a success requires, so a severe condition can produce a large error signal while p95 on
  successful requests does not move. The general principle stated there: *an incident does not
  require latency and errors to move together; a flat latency curve is not corroboration of
  health.*
- **4xx and 5xx must be split before classifying.** A surge of 401s is usually client-side — a
  bad client build, a misconfigured partner integration, credential stuffing — while a surge of
  5xx is the backend failing. Conflating them produces the wrong class, the wrong team and the
  wrong severity.

Evaluation question **Q5** is *"a few login 401s — actual incident or people getting passwords
wrong?"* **That preamble is the answer.** Had it been dropped, the corpus would have been unable
to answer a graded question, retrieval would have returned something plausible from the checks
section instead, and nothing anywhere would have looked wrong. The failure would have surfaced
weeks later as "the model missed it" — a model problem that was never a model problem.

It is now carried as an `(overview)` section and is subject to the same rules as any other.

**(3) The `Related documents` heading is numbered in the three policies.** Sixteen documents use
`## Related documents`; `POL-DEPLOY-001` uses `## 5. Related documents`, `POL-SEV-001` uses
`## 7.`, `POL-SLO-001` uses `## 8.`. An exact string match misses all three, and misses them in
*both directions at once*: their links go unparsed, so the graph is incomplete, **and** their
link lists get embedded as prose, so exactly the low-information chunks decision 2 exists to
prevent get created anyway — for the three most-referenced documents in the corpus. Matching is
now done on a heading normalised to strip the ordinal.

**(4) `## Discriminating checks` is systematically the largest section and always splits.**
Twelve sections of this class across the runbooks, ranging **1,878 to 3,439 characters** — every
one of them over the cap. This is the section retrieval most needs, and it is the one guaranteed
to be cut. What rescues it is its internal structure, which had to be read to be discovered: each
is a series of bold-led paragraphs — `**Class 1 against class 2.**`, `**Sibling endpoint
corroboration, all classes.**`, `**Change correlation.**` — and each is a self-contained
discriminating check. Splitting on paragraph boundaries therefore cuts *between* checks rather
than through one. The cut is invisible to a reader of the results.

**(5) Section-aware chunking concentrates the deliberate near-duplicates.** The four service
runbooks share a scope preamble by design, and chunking by section turns those into four
near-identical vectors. This is correct and it is not being fixed — manifest §4.5 is explicit
that they must not be artificially differentiated, because they are the test of whether metadata
filtering rescues precision. What it means practically is that **the metadata pre-filter on
`service` is load-bearing from the very first retrieval call**, not an optimisation to add later.
If the first retrieval is built without it, results will look broken and the cause will be
mistaken for a bad embedding model.

**One more, smaller:** `RB-PAY-000` and `RB-PAY-000-ARCHIVED` carry an identical `title` by
design — the archived copy is meant to be near-indistinguishable except through frontmatter. Any
chunk ID derived from the title would collide between them. IDs are derived from `document_id`
and an integer index instead.

**And one piece of good news, checked rather than assumed.** The requirement was to split at
paragraph boundaries and never mid-sentence. The largest atomic blank-line-delimited block
anywhere in the corpus is **1,397 characters** (a numbered lesson in `PM-2026-014`), across 340
blocks. Under a 2,000-character cap, **no block is ever forced to split.** "Never mid-sentence"
therefore holds by construction rather than by best effort, and `ingestion.py` contains no
sentence-splitter fallback because nothing can reach one. The same measurement confirms that
`RB-INV-002`'s five-step retry checklist (557 characters, and catastrophic to split) and all
three markdown tables (largest 711 characters, in `CAT-OWN-001`) are each a single block and
survive intact.

---

#### 4. Two defects in my own first output, and why each mattered

**(a) Greedy packing stranded five chunk tails, one of them dangerously.**

The first implementation packed paragraph blocks left to right until the target was reached, then
started a new chunk. When a section divided badly this left a small final piece. Five chunks came
out between **168 and 289 characters** — below the 350-character minimum that exists precisely to
prevent stranded fragments. The minimum was being enforced between sections and then quietly
violated between the pieces of a single section. **The same bug, one level down, in code written
to prevent it.**

The worst instance was `RB-INV-002`. Its `## Retry decision` section is a five-step checklist
determining whether a failed `/orders` request may be retried, and it closes with:

> *Bulk retries are never authorised from this document, at any class, for any number of
> requests. This holds whether the retry would be issued by a person, by a client, or by anything
> acting on their behalf.*

That prohibition was landing in its own 289-character chunk, separated from the checklist it
qualifies. A retrieval hit on the checklist would have returned the procedure **without the
prohibition attached** — a system answering "how do I retry a failed order" with the steps and
not the limit. On a corpus whose entire design principle is that the model narrates only from
what the tools returned, handing it a procedure with its constraint removed is the worst
available failure. Tails now fold back into the preceding chunk when the join fits under the cap;
when it would not fit, the tail stays as it is and the report prints it, because exceeding a real
constraint to tidy a distribution is not a trade worth making.

**(b) The topology cross-check reported a by-design state as a mismatch.**

The first version listed every corpus runbook not declared in `topology.json` as a mismatch,
which flagged `RB-PAY-000-ARCHIVED`. But that document is superseded, and **a service catalog
still pointing at a superseded runbook would be the actual defect** — it would route a responder
to a document carrying an obsolete escalation path and a change-correlation step that
`POL-DEPLOY-001` forbids. Its absence from topology is the correct state.

This mattered for a reason beyond correctness. The topology cross-check exists to surface drift
between the declared catalog and reality. A report that raises a warning about a state that is
working as intended teaches its reader to skip that line — and that line is the only place a
genuine drift would ever appear. **A check that cries wolf is worse than no check**, because it
consumes the attention that the real signal needs. Only *current* runbooks are now expected to be
declared, and the superseded one is listed under "not declared by design" with the reason stated.

**Both defects belong to the same family as the Week 1 consumer-sentence bug** found on 5
September: output that looks right. Nothing threw, nothing was obviously broken, and both would
have survived any review that read the report rather than the corpus. That is now three instances
of the same class of error in this project, which is worth naming as a pattern rather than
treating as three separate mistakes.

---

#### 5. The ingestion report as shipped

```
DOCUMENTS LOADED: 19        (failures raise, so a clean run means all of them)
  corpus body:              108,917 characters

CHUNKS PRODUCED: 106
  CAT-DEP-001      catalog     platform             5     3,205
  CAT-OWN-001      catalog     platform             3     2,690
  PM-2026-009      postmortem  catalog-service      9     6,414
  PM-2026-014      postmortem  inventory-service    9    10,398
  POL-DEPLOY-001   policy      platform             6     4,631
  POL-SEV-001      policy      platform             6     5,444
  POL-SLO-001      policy      platform             7     5,981
  RB-AUTH-000      runbook     auth-service         5     5,250
  RB-AUTH-001      runbook     auth-service         4     4,562
  RB-CAT-000       runbook     catalog-service      5     5,180
  RB-CAT-001       runbook     catalog-service      4     4,180
  RB-CAT-002       runbook     catalog-service      6     5,342
  RB-INV-000       runbook     inventory-service    5     5,168
  RB-INV-001       runbook     inventory-service    5     4,304
  RB-INV-002       runbook     inventory-service    6     5,900
  RB-PAY-000       runbook     payment-service      4     5,164
  RB-PAY-000-ARCHIVED runbook  payment-service      5     4,980
  RB-PAY-001       runbook     payment-service      7     6,858
  RB-PAY-002       runbook     payment-service      5     5,094

CHUNK SIZE — CHARACTERS
  min 358   median 881   mean 950   max 1,855   total 100,745
  over target (1,200): 28        over hard cap (2,000): 0

CHUNK SIZE — TOKENS
  UNAVAILABLE — see §6

METADATA CARDINALITY
  service        5   auth-service, catalog-service, inventory-service,
                     payment-service, platform
  document_type  4   catalog, policy, postmortem, runbook
  status         2   current, superseded
  access_level   2   operations, restricted
  owner_team     4   catalog-discovery, fulfilment-core, identity-access,
                     payments-platform

TOPOLOGY CROSS-CHECK
  no mismatches — every declared runbook_id exists, every current runbook is declared
  not declared by design (8): the 3 policies, 2 catalog documents, 2 postmortems,
  and RB-PAY-000-ARCHIVED

DOCUMENT REFERENCES
  104 references across 19 documents, parsed as links, never embedded
  no dangling references — every referenced document_id exists on disk
  no document links to a superseded document
  referenced by nothing: RB-PAY-000-ARCHIVED
```

`RB-PAY-000-ARCHIVED` being referenced by nothing is the correct and intended state: its only
signal is its frontmatter, there is no warning in its body, and nothing in the corpus points a
reader toward it. Whether retrieval surfaces it anyway — on vector similarity to its
near-identical current twin — is one of the things Week 2 is built to find out.

**Verified rather than asserted:** importing `ingestion` leaves `streamlit` out of `sys.modules`
(checked in a subprocess); chunking is byte-identical across three consecutive runs, compared by
SHA-256 over every chunk ID and body; all eleven metadata fields are present on all 106 chunks;
no `Related documents` text reaches any chunk; there are no duplicate chunk IDs.

---

#### 6. What was deliberately not done

**Token counts were not produced, and no estimate was printed in their place.** No tokenizer is
installed and there is no HuggingFace cache on this machine. The obvious move — divide characters
by four — was rejected: an estimate presented as a token count is a guess wearing the clothes of
a measurement, and the number's whole purpose is to be the pre-approval figure for a run that
spends real credit. That is the Week 1 consumer sentence in a new place. The report states the
number is unavailable and gives the command to obtain it.

Fetching the tokenizer spends no API credit — it is a vocabulary file download, not an inference
call — but it is still a network fetch, so it was left for explicit approval. The decision taken
was to **confirm which embedding model is actually live on the Nebius account first**, then fetch
that model's tokenizer, rather than assume `bge-en-icl` is in the catalogue. Per §1, whichever
model is chosen, the 106 chunks do not change.

**Also not done, deliberately:** no tests yet (the Streamlit boundary was verified by hand this
session and should be pinned in a committed suite the way Week 1's is); the vendor layer
(`corpus/vendor/` is still empty); and nothing at all touching embeddings, indexing, retrieval or
generation.

---

## Prompt 8 — 2026-09-11 — Embed the corpus, build the index, wire hybrid retrieval

### Prompt (verbatim)

```
Model confirmed: BAAI/bge-en-icl on Nebius Token Factory. Provider BAAI, modality
Embedding, 32K context, public. Output dimension [read it off the model card, or
confirm empirically from len(response.data[0].embedding) on one test string and
tell me the number].

Billing confirmed: $50 account balance, with a $1.00 trial credit that burns
first. No hard cap between the two, so standing instruction 2 stays in force —
before any run that calls the API, tell me the estimated token volume and cost.
Log actual spend in PROMPTS.md as it happens.

Fetch the tokenizer and give me the exact token count for the 106 chunks.

Then continue straight through without stopping to inspect or refactor: embed the
106 chunks, build the index, wire hybrid retrieval (BM25 + dense + rerank) with
the metadata pre-filter on service and status, and return cited passages for one
real question from EVAL_QUESTIONS.md. I want a working retrieval call this
session.
```

### Response summary

Fetched the tokenizer, found the confirmed model does not exist on the account, switched to the
one that does, embedded the corpus, built the index and returned cited passages for evaluation
question Q1. Working retrieval call achieved. Total spend for the session: **23,539 tokens,
$0.000235**.

`BAAI/bge-en-icl` returns 404 on both `api.studio.nebius.com` and
`api.tokenfactory.nebius.com`. The `/models` endpoint on both hosts returns 24 models and
exactly one embedding model: `Qwen/Qwen3-Embedding-8B`. Its output dimension is **4096**,
measured from `len(response.data[0].embedding)` on a live call rather than read off a card.
Switched to it. The 106 chunks did not change, which was the property last session's
character-based sizing was chosen to guarantee.

The token count had to be redone, because 26,178 was bge-en-icl's tokenizer counting text that
was never going to be sent to bge-en-icl. Under Qwen3's tokenizer the corpus is **23,309
tokens** (min 85, median 211, mean 219, max 410). The API then billed exactly 23,309 — estimate
and invoice agree to the token.

Built `embedding.py` (Nebius client, content-hashed vector cache, spend log), `retrieval.py`
(metadata pre-filter, BM25, dense, RRF fusion, deterministic rerank) and `query.py` (CLI).
Index: 106 vectors x 4096 dimensions, committed to the repo at 1.7MB so Streamlit Cloud serves
from it rather than re-embedding at every cold start.

Q1, *"checkout throwing 503s, where do i start?"*, scoped to payment-service: 37 of 106 chunks
passed the pre-filter; POL-DEPLOY-001 was withheld as restricted and named; RB-PAY-000-ARCHIVED
was excluded as superseded. Six passages returned from RB-PAY-001, CAT-DEP-001, RB-PAY-002 and
RB-PAY-000 — both documents the evaluation set expects, plus the sibling-corroboration passage.

Two findings that need decisions, both detailed below: the sub-3-second latency ceiling is
missed by the query embedding alone, and Q1 ranks RB-PAY-001 above RB-PAY-000 when the corpus
itself says classify first.

### Design rationale

**What exists after this session.** Three new modules, none of which import Streamlit. The
corpus is embedded and the vectors are on disk. A question plus a service scope goes in;
ranked, cited passages come out, with the reason each passage was selected attached to it. No
answer is generated yet — that is the next session, and it is the first place a model will be
allowed to write a sentence.

---

#### 1. The confirmed model did not exist, and this is why the check was worth making

Last session ended with a specific request: confirm the embedding model against the live
account before spending anything, because the catalogue cannot be queried without an API call.
The model came back confirmed as `BAAI/bge-en-icl` — provider, modality, context window and
visibility all quoted.

It 404s. On both hosts:

```
FAIL https://api.studio.nebius.com/v1/       BAAI/bge-en-icl: 404 does not exist
FAIL https://api.tokenfactory.nebius.com/v1/ BAAI/bge-en-icl: 404 does not exist
OK   https://api.studio.nebius.com/v1/       Qwen/Qwen3-Embedding-8B: dim=4096
```

A public catalogue page and a deployed account are different things, and the gap between them
is invisible until something calls the API. Had the index been built on an assumption, the
failure would have arrived mid-run with a half-populated cache.

**Output dimension: 4096**, from `len(response.data[0].embedding)`. That is a measurement, not
a documented figure, which is what was asked for and is the right instinct — a model card can
describe a variant that is not the one being served.

**The cost of finding out: 18 tokens.** Two probe calls of nine tokens each.

**What did not have to change: the chunks.** Last session's promise was that model choice
could not invalidate chunking, because chunk sizes are expressed in characters and driven by
section structure. That held exactly — same 106 chunks, same fingerprint, no re-chunk. Had
chunk size been tied to the model's context window as the conventional advice says, this
switch would have forced a full re-chunk and the manifest, the report and every number written
down last session would have gone stale.

---

#### 2. Why the token count had to be recomputed, and what it proved

The 26,178-token figure reported at the top of this session was produced by bge-en-icl's
tokenizer. That number was never wrong as arithmetic — it was wrong as a fact, because the
text it counted was never going to be sent to bge-en-icl. Different model, different tokenizer,
different count.

Recounted under Qwen3's tokenizer: **23,309 tokens**, min 85, median 211, mean 219, max 410.

Then the API billed **23,309 tokens**. Exactly.

That agreement is the payoff for refusing the characters-divided-by-four shortcut last session.
A ratio estimate would have produced roughly 25,000 — close enough to look fine, wrong enough
that nobody could ever tell whether the pricing model was understood or merely approximated. An
estimate that matches the invoice to the token is a different kind of object from one that
lands nearby: it means the next estimate, for a corpus ten times the size, can be trusted
without checking.

Largest chunk: 410 tokens against a 32,768-token window. **1.3% of capacity** — the measured
version of last session's argument that context window is not the binding constraint here.

---

#### 3. The asymmetric encoder, and the invisible way it goes wrong

Qwen3-Embedding is instruction-tuned and asymmetric: **queries carry a task instruction,
documents do not.**

```
query:    "Instruct: Given an incident symptom or an on-call question, retrieve
           the runbook, policy or postmortem passage that says what to check
           Query: checkout throwing 503s, where do i start?"
document: the chunk text, with its title and section heading prepended
```

Skipping the instruction is the kind of mistake that never announces itself. Retrieval still
runs, still returns passages, still looks plausible. It is simply worse, and there is no error
anywhere to notice. The same failure shape as the Week 1 consumer sentence and the two
ingestion defects — output that looks right.

**The instruction string is recorded in the index manifest**, because it is part of the index
contract rather than a runtime preference. Documents were embedded under one convention;
change the query convention later and queries quietly stop matching the documents they were
built against. Writing it into the manifest means a future mismatch is discoverable instead of
mysterious.

---

#### 4. Why retrieval is deterministic, and where the one model call sits

The project principle is that deterministic code produces the evidence and the model narrates
only from what the code returned. Applied to retrieval, that means the path from question to
cited passage contains no decision made by a model.

It does not. The only model call in the pipeline is the query embedding, which is a fixed
function of the query text. BM25, the metadata pre-filter, the fusion and the rerank involve no
model at all. Same index and same request produce the same passages in the same order — checked
across three runs, identical.

One detail that makes that true rather than nearly true: **ties break on corpus position, not
on list order.** Two chunks with equal BM25 scores would otherwise be ordered by however the
candidate list happened to be assembled, which is stable in practice and not guaranteed. Sorting
on `(-score, position)` makes reproducibility a property of the code instead of an accident.

---

#### 5. Reciprocal rank fusion instead of a weighted score blend

The two arms produce incomparable numbers. BM25 scores are unbounded and depend on corpus
statistics — a term's score shifts when documents are added. Cosine similarity sits in [-1, 1].

Any `alpha * bm25 + (1 - alpha) * cosine` therefore needs a normalisation constant before the
weights mean anything, and that constant is a tuning parameter wearing a disguise. It would
need re-deriving whenever the corpus changed, and with 24 evaluation questions there is not
enough signal to fit it without fitting noise.

**RRF uses only the ranks:** `score = sum over arms of 1/(k + rank)`. One parameter, `k = 60`,
taken from the original paper and deliberately left alone. Ranks are already comparable across
arms by construction, so nothing needs normalising and nothing needs retuning when the corpus
grows.

---

#### 6. The rerank stage, and the thing it is honestly not

The brief asked for BM25 + dense + rerank. **There is no cross-encoder reranker on this
account** — the `/models` endpoint returns one embedding model and no rerank model. The two
routes to a real one each cost something this project is not ready to pay:

- **A local cross-encoder** (bge-reranker, ms-marco MiniLM) requires torch: a ~900MB dependency
  in an app whose deploy `requirements.txt` is five lines and which has to install on Streamlit
  Community Cloud.
- **An LLM-as-reranker** makes *retrieval* probabilistic. That breaks the principle the entire
  project rests on, and it adds a second network round trip against a latency ceiling that
  §7 below shows is already missed.

So stage 5 is a **deterministic rerank**, and it is named as such rather than dressed up. Two
rules, each aimed at a failure this corpus plants deliberately:

**Cap chunks per document (default 2).** PM-2026-014 is 9 chunks, RB-PAY-001 is 7. Without a
cap one verbose document fills the result list — and the planted partial-answer case is exactly
the situation where that is fatal: RB-PAY-001 covers single-endpoint degradation and says
nothing about sibling corroboration, which lives only in RB-PAY-002. Six chunks of RB-PAY-001 is
one document being counted as six results, and the second document the answer needs never
appears. In the Q1 run the cap is visibly doing its job: RB-PAY-001 contributes two passages,
and RB-PAY-002 appears at position 4 carrying precisely the sibling-corroboration paragraph.

**Demote superseded documents rather than only filtering them.** RB-PAY-000-ARCHIVED is
near-identical to RB-PAY-000 by construction, so on similarity alone it can outrank its own
replacement. It is normally excluded outright by the status filter; when a caller deliberately
includes it, it ranks below equivalent current documents instead of competing on similarity.

Whether a real cross-encoder is needed is a question for measurement against the 24 evaluation
questions, not for guessing now. The deck's own advice is not to add machinery until vanilla
retrieval is measurably failing.

---

#### 7. FINDING — the sub-3-second latency ceiling is missed, and not by the part that was suspect

The ceiling was declared before building, which was the right way round. The measurement:

| Stage | Time |
|---|---|
| BM25 index build (once per process) | 30 ms |
| **Local retrieval** — filter, BM25, dense, fusion, rerank | **0.6 – 2.7 ms** |
| **Query embedding round trip to Nebius** | **3.6 – 8.7 s** |

All the local work is free. Everything in the pipeline that was designed, tuned or worried
about costs under three milliseconds over 106 chunks. **The entire latency budget is consumed by
one network call to an 8-billion-parameter embedding model**, and it consumes between 120% and
290% of the ceiling on its own — before a single token of answer generation, which is still to
come and which will add several seconds more.

This is not tunable from inside the code. The options are:

1. **A smaller embedding model.** Not available — Qwen3-Embedding-8B is the only one on the
   account. This is the real constraint and it is external.
2. **Cache query embeddings.** Helps demo reruns and repeated questions; does nothing for a
   first-time question, which is the case that matters.
3. **Re-declare the ceiling honestly** at a measured number, and say why. A stated ceiling that
   is missed and explained is a stronger artefact than a quiet one that was never checked.
4. **Drop the dense arm for a fast path.** BM25 alone is sub-millisecond, but loses the
   paraphrase matching that is half the reason for hybrid retrieval.
5. **Embed locally.** Needs torch, and the same 900MB objection as the cross-encoder.

Recommendation is 3 with 2 alongside: measure, state the real number, cache what can be cached,
and treat the 3-second figure as a target that the available infrastructure does not support
rather than as a requirement that was met. The measurement is the deliverable here — it is the
kind of thing a reviewer will ask about and most projects cannot answer.

---

#### 8. FINDING — Q1 retrieves both expected documents but ranks them in the wrong order

`EVAL_QUESTIONS.md` on Q1: *"RB-PAY-000 for classification, RB-PAY-001 for the composite-step
attribution. Two documents, ordered."*

What came back, in order: **RB-PAY-001, RB-PAY-001, CAT-DEP-001, RB-PAY-002, RB-PAY-000,
RB-PAY-000.**

Both expected documents are present, which is the recall result and it is good. But the
ordering is inverted against the expectation, and the corpus itself states the correct order
in the text of the passages that were returned. RB-PAY-001's own overview opens: *"Use
RB-PAY-000 to establish the class first. This document assumes the class is known."* The
system retrieved a document that says "read the other one first" and ranked it first.

The mechanism is visible in the score trace, which is why the trace is carried on every result:
RB-PAY-001 wins on lexical rank (#1 and #3) because the question's strongest tokens are
`checkout` and `503s`, and `/checkout` is RB-PAY-001's subject. RB-PAY-000 is the
service-level document, so it names the endpoint far less often. **BM25 is doing exactly what
BM25 does, and the corpus's own precedence relation is not a lexical signal.**

Three candidate fixes, none applied this session and none to be applied without measuring
across all 24 questions first:

- **Use the link graph.** The parsed `Related documents` structure already knows RB-PAY-001
  points at RB-PAY-000. A precedence edge derived from the corpus is deterministic and is the
  option most in keeping with the architecture.
- **Rank service runbooks above endpoint runbooks** when the question is a "where do I start"
  shape. Cheap, and hand-tuned to one question shape, which is the objection.
- **Let generation order the citations.** Push the problem downstream, where a model reading
  "establish the class first" can present them correctly. Plausible, but it makes presentation
  order probabilistic.

Flagging rather than fixing, deliberately. One question is not evidence, and the honest next
step is to run all 24 and see whether this is a pattern or a single case.

---

#### 9. A mistake made and corrected during this session

The retrieval commit was staged with a directory-wide `git add my-work/week-02`. `PROMPTS.md`
had reverted on disk to its pre-rationale state — most likely an editor undo between sessions —
and the blanket add swept that 340-line deletion into a commit whose message was entirely about
retrieval. `git status` showed the file as modified and it was committed without the diff being
read.

Restored from `b981eae` and re-applied. The lesson is narrow and worth keeping: **a file that
appears modified when it was not deliberately edited is a signal to read the diff, not to
stage the directory.** In a repository where the prompt log is itself a graded deliverable,
a blanket `git add` is a real hazard rather than a convenience.

---

#### 10. Spend, actual

Read from the API's own usage block and appended to `.index/spend.jsonl` on every call.

| Operation | Tokens | USD |
|---|---|---|
| Model probes (2 calls x 9 tokens) | 18 | $0.00000018 |
| Corpus embedding, 106 chunks | 23,309 | $0.00023309 |
| Query embeddings (5 calls x 46 tokens) | 230 | $0.0000023 |
| **Session total** | **23,557** | **~$0.000236** |

Against a $50 balance with a $1.00 trial credit burning first, the entire index cost roughly
**0.02% of the trial credit alone.** Embedding is not where this budget will go — generation
is, and that is the next session's estimate to produce.

Re-running costs nothing. The vector cache is keyed on a content hash of the exact texts sent
plus the model name, so a cache miss happens only when the chunks or the model genuinely
changed, and the manifest records which fingerprint produced the vectors on disk.

---

## Prompt 9 — 2026-09-11 — Evaluation across 24, generation layer, UI, clean-venv proof

### Prompt (verbatim)

```
Two decisions from the last session, then the rest of Week 2 in one go.

1. Latency ceiling: re-declared. Local retrieval under 50ms; end-to-end bounded by
   Nebius query-embedding latency, measured 3.6-8.7s, single-model constraint, not
   tunable from application code. Record the original 3s target, the measurement,
   and why it was missed. Do not optimise for it.
2. Q1 ranking: apply none of the three fixes yet. Run all 24 questions first.

Then continue straight through:

- Run the full EVAL_QUESTIONS.md set, all 24. Report per question: retrieved
  passages, whether the expected document surfaced and at what rank, and which of
  the four outcomes it produced (answered / partial / restricted-refusal /
  not-in-corpus refusal).
- Build the generation layer. Cited answers only, from retrieved passages, nothing
  else. All three refusal types must be distinguishable in the output: not in the
  corpus; exists but above your access level; referenced but absent. Estimate the
  generation token cost before the first call and tell me.
- Wire the Streamlit UI: deterministic incident state on top, chat below it, never
  above.
- Read the API key via st.secrets with an environment-variable fallback so the
  same code runs locally and on Streamlit Cloud.
- Tell me whether .index/ ships with the deploy or the app embeds on first run. I
  want that to be a decision, not a surprise at deploy time.

At the END of the session, not the start: there is no venv for this repo — week-02
has been running inside ~/llm-class/venv, so requirements.txt has never been proven
sufficient. Create a clean venv, install ONLY from requirements.txt, and run the app
and a retrieval query in it. Whatever breaks tells us what the file is missing.
Report what you had to add.

Standing rules unchanged: no blanket git add, one explicit path per stage; every
prompt and spend logged to PROMPTS.md as it happens; ask before any API call with
the token estimate first.
```

### Response summary

Both decisions recorded. Ran all 24 questions through retrieval, then built the generation layer
and ran all 24 through it, wired the UI, made the deploy decision explicit, and proved
`requirements.txt` sufficient in a clean virtual environment. **Session spend: 107,709 tokens,
$0.001077.**

**The headline result is a negative one.** The refusal gate was going to be a similarity
threshold, mirroring Week 1's numeric evidence gate. Measured across the 24 questions, the score
distributions for answerable and unanswerable questions **overlap**, so no threshold separates
them. The gate was redesigned around that measurement instead of shipped in spite of it.

Retrieval: **21 of 27 expected documents found (78%)**, all expected documents present on 10 of
16 questions, at least one on 14 of 16, median rank 2. Generation: **outcome agreement 16/24**,
and **zero fabricated citations across all 24** — the deterministic citation validator found
nothing to reject.

`requirements.txt` needed **nothing added**. Five lines, 49 resolved packages, every test passing
in a fresh venv including a genuinely cold end-to-end question.

### Design rationale

**What exists after this session.** The full Week 2 path is wired: question in, scoped retrieval,
a four-outcome gate, a grounded answer with validated citations, rendered in a Streamlit page
whose deterministic state sits above its chat. Plus a measurement harness over the golden set, and
a clean-room proof that the deploy manifest is real.

---

#### 1. THE MAIN RESULT — the score-based refusal gate does not work, and the measurement says so

The plan was Week 1's shape again: deterministic numeric rules in front of a narrative. A
similarity floor decides whether the corpus can answer; below it, refuse. It is the obvious
design and it is what most RAG systems do.

Top dense cosine per question, by the class the golden set says it is:

| Expected class | n | min | median | max |
|---|---|---|---|---|
| answered | 8 | **0.515** | 0.607 | 0.755 |
| partial | 7 | 0.506 | 0.541 | 0.660 |
| restricted | 1 | 0.546 | 0.546 | 0.546 |
| not_in_corpus | 8 | 0.442 | 0.506 | **0.553** |

**The answerable floor is 0.515. The not-in-corpus ceiling is 0.553.** They overlap, and not
marginally — three answerable questions sit below the highest-scoring unanswerable one:

```
0.553  Q16  failures across unrelated endpoints, how do i check gateway vs dns?   <- NOTHING in corpus
0.543  Q1   checkout throwing 503s, where do i start?                             <- answerable
0.530  Q17  could the external payment provider be down...                        <- nothing in corpus
0.515  Q12  two payment runbooks say different things, which one is current?       <- answerable
```

A threshold at 0.52 refuses Q12. At 0.56 it refuses Q1 and Q12 both. Anywhere in between it
answers Q16 and Q17. **There is no value that is right.**

**This is not a tuning failure, and that distinction matters.** Cosine similarity measures
topical proximity. An unanswerable question about *this* platform is topically adjacent to the
corpus — it names the same services, uses the same vocabulary, concerns the same systems.
*"Where are the rate limits documented"* looks exactly like a corpus question. It simply has no
answer in one. Similarity cannot see the difference between "this text is about your subject" and
"this text contains your answer", because those are different properties and it only measures the
first.

More tuning would not have helped. More evaluation questions would not have helped. The signal is
the wrong signal.

**So the boundary was redrawn rather than forced:**

*Deterministic, decided in code before the model is called:*
- access-level refusal — metadata plus a shadow retrieval that proves relevance (§3)
- superseded handling — metadata, filtered and demoted by rule
- which passages the model may see — retrieval, unchanged
- **what counts as a valid citation** — checked after generation, §4

*Model-judged, because it is reading comprehension and not policy:*
- whether the supplied passages actually answer the question

The project principle is that *policy* lives outside the model. Thresholds and permissions are
policy. "Does this paragraph contain the procedure being asked for" is not policy — it is reading,
and making it deterministic would need a labelled corpus that does not exist.

**The alternative was available and was rejected.** A threshold could have been picked, shipped,
and described in the writeup as a deterministic gate. It would have looked principled and
measured. It would also have misclassified in both directions on known questions, and nobody
reading the code would have known. That is precisely the Week 1 consumer sentence: a number that
looks measured, chosen because it was available rather than because it was right. Three instances
of that pattern are now recorded in this project; this is the first one caught *before* shipping
rather than after.

---

#### 2. Retrieval across all 24 — what surfaced and what did not

| | |
|---|---|
| Expected documents found | **21/27 (78%)** |
| Questions where ALL expected documents surfaced | 10/16 |
| Questions where at least one surfaced | 14/16 |
| Rank of found documents | median 2, best 1, worst 6 |
| Found at rank 1 | 7/21 |

The six misses are worth separating by cause rather than counted as one number. `POL-DEPLOY-001`
on Q4 is not a miss at all — it was withheld correctly, which is the test passing. The rest are
genuine precision gaps where a third or fourth expected document fell outside the top six.

**Two things the ingestion decisions bought, visible here for the first time.** Q5 ("a few login
401s") is answered citing `RB-AUTH-001` and `RB-AUTH-000`, and the `RB-AUTH-000` passage is its
`(overview)` section — the untitled preamble that a `##`-iterating splitter drops. Had that
decision gone the other way, this question would have had no answer in the index and the failure
would have looked like a retrieval problem. And Q2 surfaces `RB-PAY-002` carrying the
sibling-corroboration paragraph, which the per-document cap is what makes room for: without it
`RB-PAY-001` fills the list.

**The Q1 ordering problem from last session persists, as expected.** No fix was applied, per the
instruction. Across 24 questions it is not an isolated case — only 7 of 21 found documents land at
rank 1 — but neither is it a single pattern with a single cause. Deferred with data now rather
than with one example.

---

#### 3. The restricted refusal is precise, not blanket — and the first version was noise

The first implementation reported every restricted exclusion. Since `POL-DEPLOY-001` is the only
restricted document and is excluded from *every* query, the report said "withheld as restricted:
POL-DEPLOY-001" on all 24 questions — including ones about DNS, logging and regional fallback
where it is entirely irrelevant.

That is the same defect as the topology cross-check flagging `RB-PAY-000-ARCHIVED` two sessions
ago: **a warning that fires unconditionally trains its reader to skip the line, and that line is
the only place the real signal can appear.**

The fix is a **shadow retrieval**: run the same query again with the access filter lifted, reusing
the same query vector, and check whether a restricted document would actually have *ranked*. Same
vector means no extra tokens and no extra round trip — it is free. Only a document that would
have been returned gets named.

On Q4 ("can i roll it back or do i need approval") that produces the correct, specific output:
`POL-DEPLOY-001` would have ranked, so the answer is *"relevant guidance exists but is above your
access level"*. On Q18 ("no recent logs") it stays silent, because the restricted document has
nothing to do with the question.

A related leak was fixed in the same place: the refusal's "what the corpus does hold for this
scope" list was including `POL-DEPLOY-001`. Offering an operations-level caller a document they
cannot open both wastes their time and collapses the two refusal types back into one. Restricted
documents are now excluded from that list, and the access notice says it once, precisely.

**The third refusal type — referenced but absent — is wired and currently returns empty**, because
all 104 parsed references resolve. It is implemented rather than described because a refusal type
that has never been exercised is a claim, not a feature; the check runs on every answer and the UI
has a branch for it.

---

#### 4. Citation validity is enforced by code, not by the instruction that requested it

The system prompt forbids inventing a `document_id`. That instruction is necessary and it is not
sufficient — a prompt is a request, not a guarantee.

So after generation, every cited `document_id` is checked against the set of passages that were
actually supplied. Anything else is stripped from the citation list and reported separately as a
rejected citation, in the CLI output and as a red error block in the UI.

**Across 24 questions: zero invalid citations.** The validator found nothing to reject.

That is a genuine result and it should be stated carefully. It does not prove the model cannot
fabricate a citation; it proves that on this corpus, with these passages, it did not — and that if
it ever does, the system catches it rather than printing it. The check is cheap, it is
deterministic, and it converts "we asked it not to" into "we verified it didn't".

---

#### 5. Generation outcomes — 16/24, and the disagreements are the interesting part

```
   answered      -> answered        7   Q1, Q5, Q6, Q7, Q9, Q12, Q15
 * answered      -> partial         1   Q2
 * not_in_corpus -> answered        1   Q11
   not_in_corpus -> not_in_corpus   3   Q10, Q18, Q24
 * not_in_corpus -> partial         3   Q16, Q17, Q22
 * not_in_corpus -> restricted      1   Q13
 * partial       -> answered        2   Q19, Q20
   partial       -> partial         5   Q3, Q8, Q14, Q21, Q23
   restricted    -> restricted      1   Q4
```

**Q11 is the one genuine failure, and it is the worst available kind.** *"admin-portal blank but
web-app fine, frontend issue or something behind it?"* — the corpus has nothing on frontends,
clients or CDN behaviour. It answered, citing `RB-PAY-000` and `RB-PAY-001`, by applying the
sibling-endpoint corroboration pattern: compare the failing endpoint against another endpoint on
the same backend.

`admin-portal` and `web-app` are **consumers**, not endpoints. They share no backend because they
are not endpoints at all. The model found a structurally similar pattern — two named things, one
healthy, one not — and transferred it across a distinction the corpus does make and the question
does not signal. A confident, cited, fluent answer to a question with no answer in the corpus.
This is the failure mode the refusal path exists for, and it got through.

**Q13 may be the golden label being wrong rather than the system.** *"payment restart procedure"*
was expected to be `not_in_corpus`. The model correctly said no restart procedure exists; the
deterministic gate then added `restricted`, because `POL-DEPLOY-001` would have ranked. The
resulting answer is *"no restart procedure exists, and there is deployment/rollback guidance above
your access level"* — which is more informative than a flat refusal and is true. Rollback is
genuinely adjacent to restart. Worth re-examining the label before counting this as a miss.

**Q17 half-worked, and it was supposed to be the best refusal in the set.** The corpus refuses
itself there: `CAT-DEP-001` explicitly states that no downstream dependencies are declared, that
this is *not* an assertion that none exist, and that such questions escalate. Retrieval put
`CAT-DEP-001` at rank 5 — it was in the context. The answer hedged correctly and named what was
not covered, but cited `RB-PAY-001` and `RB-PAY-000` instead of the passage that says the corpus
cannot answer. The right material was retrieved and the wrong material was cited.

**Q19 and Q20 over-claim.** Both returned `answered` where `partial` was expected. Q19's content
is actually correct — class 4, escalate, do not reconstruct from the gateway view — it simply did
not flag that no tracing procedure exists. Q20 answered a deliberately vague question instead of
asking for narrowing.

**The error distribution is asymmetric, and in the safer direction.** Four of eight disagreements
are refusal-to-partial — hedging, which costs the reader a little confidence and nothing else.
Three over-claim (Q11, Q19, Q20) and one under-claims (Q2). The dangerous direction is the
minority, but Q11 shows it is not empty, and one confident wrong answer does more damage to trust
than four unnecessary hedges.

---

#### 6. The UI contract, and where the secret crosses the boundary

**Deterministic state above, chat below, enforced by layout order.** Corpus state, the topology
cross-check, the dangling-reference check and the index fingerprint render first. The chat is
underneath. Within each answer the same order repeats: the outcome badge and the access notice
come before the prose, and the retrieval trace is one expander away.

The reasoning is not aesthetic. A page that puts generated prose on top and the evidence
underneath has inverted what this project argues — that the deterministic part is the product and
the narration is a convenience. Putting the chat first would undercut the thesis visually no
matter what the writeup said.

**The secret crosses the Streamlit boundary in exactly one direction, in `app.py`, before
`embedding` is imported.** `st.secrets` is read and lifted into `os.environ`; `embedding.py` then
finds it there. The module never imports Streamlit, and the one channel both deployment targets
share is the environment. Locally `st.secrets` raises rather than returning empty when there is no
`secrets.toml` — that is the normal local path, not an error — and the dotfile fallback handles it.
The sidebar displays which of the three sources supplied the key, so a deploy that silently picks
up the wrong one is visible rather than mysterious.

---

#### 7. `.index/` ships with the deploy — a decision, with the property that makes it safe

**The index is committed. The deployed app never embeds.**

Streamlit Community Cloud sleeps idle apps and restarts them on demand. An app that embedded at
startup would spend 23,309 tokens *and* 30-plus seconds on every cold start, repeatedly, for a
corpus that has not changed. Shipping 1.7 MB removes a recurring cost and a recurring delay.

**What makes this sound rather than merely convenient:** `load_index()` recomputes the content
fingerprint of the chunks on disk and compares it against the manifest. A mismatch **raises with
an explicit message** instead of silently re-embedding. So a stale index is a loud failure, never
a quiet charge, and rebuilding is always a deliberate act: `python embedding.py --embed`.

The operational cost is real and accepted: a corpus edit now requires a re-embed and a re-commit
of `.index/` before deploy. That is the right trade, because it makes spending money explicit.

`query_vectors.npz` is gitignored — it is a runtime cache that grows with every question asked and
would be correct for nobody else.

**One deploy hazard found and fixed while making this decision.** Both the spend log and the query
cache wrote to disk unconditionally. On a read-only container filesystem that would raise *after*
a successful API call, turning a served answer into an error — losing the thing the user paid for
in order to fail at bookkeeping. Both writes now swallow `OSError`. The API's usage block is the
real record; the local log is a build-loop convenience.

---

#### 8. The clean venv — `requirements.txt` needed nothing added

Week 2 had been running inside `~/llm-class/venv`, which has months of accumulated packages. The
five-line deploy manifest had never been tested.

Fresh `python3 -m venv`, `pip install -r requirements.txt` only — 49 resolved packages from five
declared ones:

| Test | Result |
|---|---|
| Import `ingestion`, `embedding`, `retrieval`, `generation` | pass — and `streamlit` still not in `sys.modules` |
| `python ingestion.py` | pass — 19 documents, 106 chunks |
| `python query.py` with a service scope | pass — cited passages returned |
| `app.py` via `AppTest` | pass — no exception, all four metrics render |
| `python evaluation.py` | pass — full 24-question retrieval report |
| **Cold end-to-end**: no query cache, embed + generate | **pass — 21.6 s, answered, 0 invalid citations** |

**Nothing had to be added.** The one thing that does not work is `generation.estimate_generation`,
which needs `transformers` and raises a clear message saying so. That is correct and deliberate:
the deployed app never prices a run, so the tokenizer belongs in `requirements-dev.txt` and the
failure is explicit rather than silent.

The cold test is the one that mattered. The earlier passes were partly reading a warm query cache;
moving the cache aside and forcing a real embedding call plus a real generation call is what
actually proves the manifest. It also produced the honest latency number — **21.6 seconds**, worse
than the 8–20 s I had estimated — which is now recorded in the handoff as the figure to quote.

---

#### 9. Spend, actual

Read from each API response's usage block, appended to `.index/spend.jsonl`.

| Operation | Tokens | USD |
|---|---|---|
| Carried in from previous sessions | 23,557 | ~$0.000236 |
| Retrieval eval, 24 query embeddings | 1,116 | $0.0000112 |
| Generation, 24 questions (55,359 in + 14,558 out) | 69,917 | ~$0.001 |
| Single-question probes and the cold venv test | ~13,100 | ~$0.0002 |
| **Session total (cumulative)** | **107,709** | **$0.001077** |

Against $50 with a $1.00 trial credit burning first: the entire build so far has used **about
0.1% of the trial credit**. The estimate given before the generation run was 54,559 input tokens;
the actual was 55,359 — **1.5% over**, the gap being the shadow-retrieval prompts not modelled in
the estimate.

Output ran higher than assumed (14,558 against 7,200 assumed) because `gpt-oss-120b` spends output
tokens on reasoning before emitting JSON. That also caused the one bug in this layer:
`max_tokens=900` truncated the JSON mid-object and the parse failed, which presented as a format
problem and was a budget problem. Raised to 2,500, `response_format=json_object` added, and the
error message now says to look at the token budget when a reply ends mid-object.

---

## Prompt 10 — 2026-09-11 — Is the prompt log actually serving the learning goal?

### Prompt (verbatim)

```
As we discussed previously are we capturing the prompt request and prompt response with learning method that might helpful for me later?
```

### Response summary

A review of this file against its own stated purpose, with no code written. Assessment: **it is a
good record and not yet a good study aid**, and the gap is structural rather than a matter of
writing more words.

Audited the actual state: 15 logged exchanges across both weeks, 991 lines in
`week-01/PROMPTS.md` and 1,927 here. Verbatim prompts present throughout. Rationale blocks
present on **3 of 15** entries — week-02 Prompts 7, 8 and 9 only.

Named six gaps, recommended building two of three proposed artefacts, and flagged that building
any of them right now is the pattern `WEEK2_BUILD_HANDOFF.md` §1 asked to be called out. Nothing
was built; the choice of scope is still open.

### Design rationale

*No code this entry. The reasoning below is the assessment itself, which is the only deliverable
the prompt asked for.*

#### 1. The distinction that the answer turns on

A **record** preserves what happened. A **study aid** is organised so a reader can find and reuse
what happened. This file is the first and not the second, and no amount of additional prose
converts one into the other — the missing things are indexes, names and cross-references, which
are structural.

That distinction is worth stating plainly because the file *looks* complete. It is long, it is
detailed, and every session is in it. The failure is not visible from inside it.

#### 2. The six gaps, in the order they cost something

**Coverage is 3 of 15.** Week 1's entire log has no rationale at all, and week-02 Prompts 1–6 —
the whole corpus build, including every decision about the planted failure cases — have none
either. The practice started at Prompt 7.

**~2,900 lines with no way in.** No index, no contents, no cross-references. "What did we decide
about chunking and why" currently requires reading linearly. In three months that means it will
not be read.

**The recurring patterns are never named.** This is the largest gap. A single failure mode has now
occurred at least five times across both weeks:

| Instance | Where |
|---|---|
| The ungated consumer sentence, printing a conclusion at 100% vs 0% | Week 1, found by external review |
| p95 over 2xx returning `None` and being formatted directly | Week 1, same review |
| The stranded `RB-INV-002` tail, separating the bulk-retry prohibition from its checklist | week-02 Prompt 7 |
| The topology cross-check flagging a by-design state as a mismatch | week-02 Prompt 7 |
| The restricted notice firing on all 24 questions including ones about DNS | week-02 Prompt 9 |
| Q11 answering a frontend question by transferring the sibling-endpoint pattern | week-02 Prompt 9 |

**Output that looks right.** Nothing throws, nothing appears broken, and every one of these
survives a review that reads the report instead of the data. That is a transferable engineering
lesson and it currently exists only as six passing asides inside six unrelated entries. It is the
single most valuable thing in the log and it has no name and no home.

**The prompt craft is not captured** — arguably the worst omission for a course whose deliverable
is being an AI-native professional. The prompts are preserved verbatim as artefacts, but nothing
anywhere says why they worked. Specific techniques that recur and are doing real work:

- *"Tell me X before you write"* — forces the reasoning out where it can be challenged, before
  any code exists to defend.
- *"Report, do not guess"* and *"I need the actual number, not an approximation"* — the instruction
  that produced the refusal to print a characters/4 token count, which then matched the invoice to
  the token.
- *"If it survives, fix it. If you propose a rule, show me the threshold before implementing"* —
  separates detection from remediation and keeps the threshold decision with the person who owns
  the consequences.
- The standing cost instruction with a pre-run estimate — turns spending into a deliberate act.
- *"Create a clean venv, install ONLY from requirements.txt... whatever breaks tells us what the
  file is missing"* — an experiment rather than an audit request. Designing a test whose failure
  mode is the answer is a different and better move than asking for a review, and it is the
  sharpest single prompt in either week.

None of that is analysed. The log holds the evidence and draws none of the conclusions.

**No "what I would do differently."** Each rationale block defends the path taken. None names the
cheaper path that was available.

**Reference data is trapped in prose.** Spend figures, the score distributions, the thresholds and
their justifications are all narrative. None of it is extractable into a table for the writeup.

#### 3. What was recommended, and what was recommended against

Proposed a single cross-week `LEARNING_LOG.md` at the repository root with three sections: a
**pattern catalogue** (named failure modes, their instances, and the detection method that now
catches each), a **prompt-craft catalogue** (the techniques above, with the verbatim example and
what each produced), and a **decision index** (a pointer table from decision to the entry holding
its reasoning, making ~2,900 lines navigable without rewriting them).

**Recommended against backfilling** rationale for Week 1 and week-02 Prompts 1–6. Week 1 is closed
and graded. The corpus decisions are already recorded in `CORPUS_MANIFEST.md`, which is
better-structured for the purpose than a retroactive narrative would be. Backfilling is hours of
work for little return, and the indexing gap is the one that actually blocks reuse.

#### 4. Why the timing was flagged rather than the work just started

It is 11 September. Demo Days are 15–16 — four days. Week 2 still needs the one-liner, the
framework fields, the Google Doc, a video under five minutes, and submission. Weeks 3 through 6 do
not exist.

`WEEK2_BUILD_HANDOFF.md` §1 contains a standing instruction to redirect toward shipping when
opinions start accumulating instead of output, and `STATUS.md` records that same pattern costing a
day in August and thirteen more after it. **Building learning infrastructure at this point is that
pattern** — defensible, genuinely useful, and not Week 2 shipping.

The recommendation was therefore the narrow version: pattern catalogue and decision index only,
roughly twenty minutes, on the grounds that both double as Google Doc material that has to be
written anyway. The pattern catalogue is also the strongest single thing to put in front of a
reviewer — *the same failure class appeared five times, and here is the detection method that now
catches it* — which makes it the one piece of this that is not a detour.

The prompt-craft catalogue is the richest section and the one most clearly about learning rather
than about shipping. It was recommended for after submission.

#### 5. State at the end of this entry

Nothing built. Three options put to the user — the twenty-minute version now, all three sections
now, or defer entirely until Week 2 ships — and the decision is open.

---

## Prompt 11 — 2026-09-12 — Architecture diagram and a factual inventory for the submission

### Prompt (verbatim)

```
Building is done. Deliverables only from here — if I ask you to improve code, push
back.

Two things for the Week 2 submission, in this order:

1. A Mermaid architecture diagram of the Week 2 RAG pipeline: corpus → ingestion
   (frontmatter parse and validate, section-aware chunk, Related-documents extracted
   to structured links) → embedding (Nebius Qwen/Qwen3-Embedding-8B, 4096-dim, local
   .index cache keyed on content hash) → hybrid retrieval (metadata pre-filter on
   service and status → BM25 + dense → deterministic rerank) → generation with
   citation validation → three distinguishable refusal paths. Name the file and
   module behind each stage. Save it to my-work/week-02/ARCHITECTURE.md.

2. Then read PROMPTS.md and give me a factual inventory for the submission doc:
   every measured number with its source, every design decision with its reason, and
   every defect found and fixed, in the order they happened. Facts only — I am
   writing the prose myself.

Do not touch any .py file.
```

### Response summary

Two deliverables, no `.py` file touched.

**`ARCHITECTURE.md`** — a Mermaid flowchart of the full pipeline with every stage labelled by file
and function, plus a stage-by-stage table and a constants table. Four node classes carry the
argument visually: blue for deterministic code, orange for a model call, dashed for storage, red for
a refusal path. Three model calls in the whole diagram (corpus embedding, query embedding,
generation); everything else is blue.

**`SUBMISSION_FACTS.md`** — a chronological inventory, every item tagged **[M]** measured number with
source, **[D]** decision with reason, or **[X]** defect found and fixed. Facts only, no prose.

Every constant and figure in both files was re-verified against the code, `.index/manifest.json` and
`.index/spend.jsonl` today rather than recalled from the log. Items so verified are marked.

One correction surfaced by that check: `PROMPTS.md` Prompt 9 records a session spend of 107,709
tokens / $0.001077, which was a point-in-time snapshot. The ledger now reads **60 calls, 110,981
tokens, $0.001110**. `SUBMISSION_FACTS.md` uses the ledger and flags the discrepancy so the older
number is not quoted by mistake.

### Design rationale

#### 1. Why the diagram is drawn around the deterministic/probabilistic split

The pipeline could be drawn as seven boxes in a row and be accurate and say nothing. The argument
this project actually makes is about *where* the model is allowed to act, so the colour classes carry
the thesis: three orange nodes against nineteen blue ones, and the reader sees the claim before
reading a label.

Three edges are drawn deliberately rather than for layout:

- **`parse_links()` → `referenced_but_absent()` is dashed and bypasses the vector store entirely.**
  That is the "Related documents becomes a link graph, not text" decision made visible — the path
  exists and it does not go through embedding.
- **`restricted_would_have_ranked()` → the access-level refusal is the heavy edge**, and it enters
  the outcome from outside the generation box. The model never sees a restricted passage, so it
  cannot know one was withheld; only the filter knows, so only code can say it. Drawing that arrow
  from inside `answer_question()` would have misrepresented who decides.
- **The cache check is a decision diamond with both branches labelled** (`miss: spends credit` /
  `hit: free`), because the money is in that branch and a diagram that hides it is less useful than
  one that does not.

#### 2. Why the inventory is tagged rather than sectioned by type

The instruction was "in the order they happened", which conflicts with grouping by measured-number /
decision / defect. Tagging resolves it: chronology is the structure, and `[M]` / `[D]` / `[X]` make
each stream filterable by eye. A submission doc that needs all the numbers can read the `[M]` lines;
a narrative about judgement can read the `[D]` lines.

#### 3. Why every figure was re-verified instead of copied

The log is the record and the code is the system, and they can drift — which is exactly what the
spend discrepancy turned out to be. A submission document quoting a number that was true three days
ago is the same failure class as the rest of this project's catalogue: correct-looking output whose
defect is in what produced it. Re-reading `.index/manifest.json` and `.index/spend.jsonl` cost
nothing and caught one real error.

Nothing was repaired in `PROMPTS.md`. The old figure stays where it is, with the new one flagged
beside it, because the log records what was true at the time and rewriting it would make it less
useful as a record.

#### 4. What is NOT in either file

- **No targets presented as results.** The 3-second latency ceiling appears as a declared target and
  a measured miss, not as a number achieved.
- **No claim of a test suite for Week 2.** Recorded as absent in §7.
- **No prose.** The instruction was facts only.
- **Nothing about Week 3.** Both files are Week 2 scoped; the only cross-week item is §8, the
  six-instance failure pattern, because two of its instances are Week 1's and the pattern is the most
  reusable thing in the log.

