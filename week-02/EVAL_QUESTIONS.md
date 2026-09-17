# Week 2 — Evaluation Question Set

**Generated:** 5 Sep 2026 · **Source:** ChatGPT, given the fictional platform description only,
with **no access to the corpus**.

## Why a different model wrote these

The corpus was written by Claude Code. If the same model had written the questions used to
test retrieval against it, the questions would inherit the corpus's vocabulary and retrieval
would score well for the wrong reason — matching phrasing rather than meaning. That is the
synthetic-circularity problem in miniature, and it is the failure mode most likely to pass
unnoticed because nothing looks wrong.

ChatGPT was given the endpoints, backends, consumers and region, and asked what an on-call
engineer would actually type at 2 AM. It did not see a single document.

**Two questions found gaps that were not planted** — see §4. Those are more honest than the
gaps that were designed in, because they were not authored to fit.

---

## 1. Distribution

| Class | Count | Meaning |
|---|---|---|
| Answerable | 8 | The corpus supports a complete, cited answer |
| Partial | 5 | The corpus supports part of it and must say what it does not cover |
| Restricted | 1 | Relevant guidance exists but is above the caller's access level |
| Unanswerable | 6 | The corpus contains nothing; the system must refuse and name what it does have |

Manifest §4.4 asked for at least six questions falling in the deliberate gaps. Six unanswerable
plus five partial clears that comfortably.

**Three distinct refusals must be distinguishable**, and all three are represented:

- *not in the corpus* — Q10, Q16, Q18
- *exists but you cannot read it* — Q4
- *referenced but absent* — the two postmortems, reachable via Q6 and Q9

---

## 2. The set

### Answerable

**Q1 — "checkout throwing 503s, where do i start?"**
`RB-PAY-000` for classification, `RB-PAY-001` for the composite-step attribution. Two
documents, ordered. The baseline case.

**Q2 — "refunds failing too — same payment-service problem or separate thing?"**
**The planted partial-answer test, and it runs in the harder direction.** Sibling corroboration
lives only in `RB-PAY-002`; `RB-PAY-001` says nothing about it and does not even cross-reference
it. If retrieval anchors on `/checkout`, it returns nothing useful. Correct behaviour is to
retrieve `RB-PAY-002` on the `/refunds` half of the question and synthesise.

**Q5 — "a few login 401s — actual incident or people getting passwords wrong?"**
`RB-AUTH-001` low-absolute-counts section plus 4xx composition; `RB-AUTH-000` for the 4xx/5xx
split. The answer is nuanced in both directions: a small count is the expected state *and* a
real rise can hide inside a high baseline.

**Q6 — "search is really slow but all 200s, does that count as degraded?"**
`RB-CAT-002` plus `RB-CAT-000`'s capacity-against-fault check plus `POL-SLO-001` objectives.
Also touches the dangling `PM-2026-009` reference.

**Q7 — "3 refund failures and barely any traffic, enough to wake someone up?"**
**The strongest question in the set.** Three documents: `POL-SLO-001` (the gate — three
failures does not clear a floor of ten), `RB-PAY-002` (a clean verdict on a low-volume slice is
weak evidence, and support-led reports carry more weight here), `POL-SEV-001` (paging). The
correct answer is genuinely two-sided: it does not clear the bar, *and* that is not the same as
nothing being wrong.

**Q9 — "cart works but orders failing, which inventory-service checks apply?"**
`RB-INV-000` plus `RB-INV-002`. Tests whether the system carries the negative-corroboration
nuance — the two endpoints exercise substantially different paths, so a quiet `/cart` is weak
evidence about the backend.

**Q12 — "two payment runbooks say different things, which one is current?"**
**The status-filter demo.** `RB-PAY-000` versus `RB-PAY-000-ARCHIVED`. Without the `status`
filter both score well on similarity. Correct behaviour is to return the current version and
state that the other is superseded. Run it both ways on video.

**Q15 — "inventory owner not answering, who's next on escalation?"**
**Hits the planted stale entry.** `CAT-OWN-001` says fulfilment-core, coverage to 22:00, then
platform on-call. `CAT-DEP-001` still attributes `/orders` to `order-fulfilment`, a superseded
team name. Two sources disagree. The best answer names the conflict rather than silently picking
one.

### Partial — must state what is not covered

**Q3 — "only mobile-app getting errors, what do i check that's different from web?"**
**Unplanned gap.** The corpus has fragments — volume attribution in `RB-PAY-002`, 4xx
composition by client build in `RB-AUTH-001` — but no general consumer-dimension procedure. The
system should surface what exists and say the corpus has no consumer-specific triage runbook.

**Q8 — "timeouts stopped but latency still high, can i close this?"**
**Unplanned gap.** There are no incident-closure criteria anywhere. `POL-SEV-001` covers
time-to-*classification*, not resolution or closure. Correct behaviour is to say so.

**Q14 — "checkout timed out, is retrying safe or could we charge twice?"**
**The most interesting question in the set.** The retry-safety checklist and the idempotency
reasoning live in `RB-INV-002` — a different endpoint on a different service. `RB-PAY-001`'s
partial-completion section says a failed request may have left state and that it goes straight
to payments-platform. So the correct answer is *escalate*, and whether the `/orders` retry
reasoning transfers to `/checkout` is exactly the kind of judgement the system should not make
silently. Watch whether it cites across services and how it hedges.

**Q19 — "refund says success but customer hasn't got the money, where do we trace it?"**
Correctness rather than availability — class 4, invisible in both series. `RB-PAY-000` covers
the concept; `RB-PAY-001` says do not reconstruct from the gateway view. No tracing procedure
exists. Answer: classify it, escalate, do not attempt reconstruction.

**Q20 — "everything looks bad, what do i check first?"**
Genuinely too vague. Tests whether the system asks for narrowing or dumps every runbook it has.

### Restricted

**Q4 — "payment-service just deployed, can i roll it back or do i need approval?"**
`POL-DEPLOY-001`, `access_level: restricted`, opening with a no-relay instruction. In Week 2 the
citation should surface the restriction. In Week 6, with role filtering, the answer becomes
*relevant guidance exists but is not available at your access level* — which is a different
answer from *no guidance exists*, and conflating them is a security problem rather than a
usability one.

Note the cost: the sharpest explanation of causal restraint in the whole corpus — a rollback is
itself a deployment, and is reliably the most recent event before any recovery — sits inside the
document the caller cannot read.

### Unanswerable — the refusal set

**Q10 — "partner-api getting 429s, where are the limits documented?"**
No rate-limit documentation. The corpus is 5xx and latency only.

**Q11 — "admin-portal blank but web-app fine, frontend issue or something behind it?"**
No client-side or frontend guidance. CDN and edge behaviour is an explicit §4.4 gap.

**Q13 — "payment restart procedure — what needs checking first?"**
Every service runbook states "classification only, not remediation" in its first paragraph. No
restart procedures exist anywhere. A strong refusal quotes that scope statement rather than
just saying no.

**Q16 — "failures across unrelated endpoints, how do i check gateway vs dns?"**
No gateway-level or DNS guidance.

**Q17 — "could the external payment provider be down, where do we check that?"**
**The best refusal in the set, because the corpus refuses itself.** `CAT-DEP-001`'s downstream
dependencies section explicitly states that none are declared, that this is *not* an assertion
that none exist, and that such questions escalate to the owning team. The system should retrieve
that passage and cite it — an answer of "the documentation states it cannot answer this" rather
than silence.

**Q18 — "alert firing but no recent logs, is the service quiet or is logging broken?"**
Telemetry-pipeline health is not covered. `POL-SLO-001`'s bucket-containing-requests
precondition is adjacent but does not answer it.

---

## 3. What "correct" means for scoring

Per question, four things:

1. **Retrieval** — were the right documents returned, and were superseded or
   inaccessible ones handled correctly
2. **Citation validity** — does every claim point at a passage that actually says it
3. **Refusal accuracy** — did it refuse when it should, and *not* refuse when it shouldn't
4. **Naming the gap** — on a refusal or a partial answer, did it say what *is* available

Point 4 is the difference between a useful refusal and a dead end. *"The corpus has no guidance
on rate limiting; the payment-service runbook covers 5xx and latency triage"* is an answer.
*"Not found"* is not.

---

## 4. Four questions added from cross-model validation

Four further models (Perplexity, Gemini, Grok, DeepSeek, Kimi) were given the same platform
description independently. Most of their output rephrased the shapes above. These four are
genuinely new and are added to the golden set.

**Q21 — "do we even have a runbook for this?"** *(Grok)*
A meta-question about coverage rather than content. Can the system report on what it holds?
Correct behaviour is to name the documents that exist for the service in question, rather than
attempting to answer the unstated underlying question. No other model asked this.

**Q22 — "is this only one region? wait we only have one region — what's the fallback?"** *(Perplexity)*
A false premise, self-corrected mid-sentence. Tests whether the system follows the correction or
answers the abandoned premise. The corpus has nothing on regional fallback, so the correct
outcome is a refusal — but only after parsing the question correctly.

**Q23 — "payment declined but inventory still reserved"** *(Grok)*
Cross-service state inconsistency. Two backends disagreeing, owned by two different teams, and
no single runbook covers it. `RB-INV-000`'s divergence procedure is adjacent but describes
cart-versus-order divergence, not payment-versus-inventory. Partial at best; watch whether it
over-transfers.

**Q24 — "why is checkout hitting inventory twice and who decided that?"** *(Grok)*
An architecture question asked during an incident. `CAT-DEP-001` is a declared map, not a design
rationale, and it says so. Correct refusal points at the map and states that design decisions
are not recorded in the operational corpus.

### What the cross-model pass actually found

Across roughly 100 questions from five independent models, the most-requested guidance was:

| Theme | Models asking | Corpus coverage |
|---|---|---|
| Restart a service | 5 of 5 | **None** — every runbook states "classification only, not remediation" |
| Roll back a deploy | 5 of 5 | Restricted (`POL-DEPLOY-001`) |
| Where are the logs | 4 of 5 | **None** |
| Rate limits and 429s | 4 of 5 | **None** |
| External provider status | 3 of 5 | Refuses itself (`CAT-DEP-001`) |
| Database, cache, connection pools | 2 of 5 | **None** — deliberate §4.4 gap |

**The single most-asked question shape across five independent models is the one the corpus
refuses.**

Two things follow. First, it validates the refusal set as realistic rather than contrived: five
models independently asked for exactly what was deliberately withheld, so the gaps reflect what
people actually ask. Second, it marks the system's boundary honestly — this is a triage layer,
not a remediation layer, and reasoning about an action is not authorisation to take it. That is
the Week 6 thesis, confirmed from outside before Week 6 begins.

The golden set stops at 24. ChatGPT's original 20 were written against the platform with no
corpus access and are the least contaminated by generic incident-response vocabulary; the other
four sets served as validation, and that validation belongs in the writeup rather than in the
question set.

---

## 5. Two gaps that were not planted

Both surfaced only because the questions came from outside the corpus.

**Consumer-dimension triage (Q3).** The Week 1 application has a consumer filter, the dataset
has four consumers, and the whole `/checkout × mobile-app` NOT EVALUABLE finding is a
consumer-slice problem — yet no runbook documents how to triage a consumer-specific fault. The
fragments that exist are incidental.

**Incident closure (Q8).** The corpus tells a responder how to classify and when to escalate. It
never says when something is over. `POL-SEV-001` limits time-to-classification and explicitly
notes that those limits are not about resolution.

**Do not fill these.** They are honest gaps, they are the kind a real corpus has, and they make
better refusal cases than anything that could be planted deliberately. Record them, refuse them
correctly, and name both in the writeup as gaps an outside perspective found that the author
did not.
