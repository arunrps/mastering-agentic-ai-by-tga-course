# Week 2 Build Handoff — TriageLens

**Written:** 6 Sep 2026 · **Purpose:** paste as the first message in a new chat to continue the
Week 2 build without re-establishing context.

**Precedence:** `STATUS.md` wins on *where I am*. `TRACK_C_HANDOFF.md` wins on *decisions
already made*. `TRIAGELENS_PROBLEM_STATEMENT_AND_REQUIREMENTS.md` wins on *what the product is*.
This file covers *what happens next*.

---

## 1. The calendar — read this first

| | |
|---|---|
| Today | 6 Sep 2026 |
| Demo Days | **15–16 Sep — nine days** |
| Week 2 deadline | 23 Aug, passed, confirmed soft |
| Outstanding | Weeks 2, 3, 4, 5, 6 |
| Available | 12 hours/day, no competing commitments |

Weeks 3–6 session material is **unwatched**. Budget ~15 hours for it inside the nine days.

`STATUS.md` names the failure mode already observed twice: reviews → more reviews → enhancement
→ "the deadline is soft." It cost a day on 20 Aug and thirteen more after. **Redirect me toward
shipping if I start collecting opinions instead of building.**

---

## 2. What TriageLens is

An evidence-first incident investigation layer for API gateway telemetry. One system across six
weeks, each a separate app sharing the fictional platform and the story but not the codebase.

**The principle that constrains everything:**

> The model decides what evidence it needs; deterministic code produces that evidence; the model
> narrates only from what the tools returned.

Plus: causal restraint (suspect, never caused) · evidence sufficiency rather than confidence
percentages · explained restraint when nothing is raised · simulator truth is not investigator
evidence · policy lives outside the model.

**Fictional platform:** endpoints `/checkout` `/refunds` `/cart` `/orders` `/products` `/search`
`/login` · backends payment-service, inventory-service, catalog-service, auth-service ·
consumers web-app, mobile-app, partner-api, admin-portal · single region us-east-1.

---

## 3. Week 1 — shipped, hardened, tested

Submitted 16 Aug. Hardened 20 Aug (`3ec6a07`), verified and tested 5 Sep.

- Deterministic incident brief — pandas and an f-string, no LLM
- Two-stage evidence gate, three outcomes: EVIDENCE SUFFICIENT / EVIDENCE INSUFFICIENT / NOT
  EVALUABLE. Rule set versioned `evidence-rules-2026-08-20.a`
- Baseline is a property of the **dataset** (first 120 min), never derived from the selected
  window. My original spec said otherwise and was disproved by measurement: it made the incident
  its own control, collapsing 7.28× to 1.25× when zooming into the spike. Multiplier now rises
  6.4× → 34.7× → 41.4×
- Explained suppression: `/login` fails on `minimum_failures` and says so with numbers
- `topology.json` + `topology.py` — declared topology with a drift banner. Owns resolution,
  annotation and validation, **not** enumeration
- `detection.py` verified Streamlit-free — the boundary that makes these functions agent tools
  in Week 3
- **49 tests passing**, committed

**Two bugs found 5 Sep by an external ChatGPT review and fixed:**

1. The brief appended *"...so this looks like traffic share rather than a consumer-specific
   fault"* whenever both consumer rates existed, ungated. At 100% vs 0% it printed the same
   sentence. **It was written when the real numbers were 19.72% vs 16.77%, where it was
   defensible — never gated, so it outlived its own evidence.** This is the determinism boundary
   failing from the inside: the rule protects against a model inventing figures, not against a
   human hardcoding a conclusion that was true once. Worse than a hallucination, because nothing
   looks wrong.
2. TypeError when p95 over 2xx returned None and the brief formatted it directly.

**Deferred to the Week 3 generator:** DET-02a (baseline sufficiency gates the whole verdict;
should gate only the multiplier — `/checkout × mobile-app` clears every absolute rule and still
reads NOT EVALUABLE), DET-02b (multi-backend endpoints split, never pooled), scenario warm-up
length (21 of 26 consumer-sliced pairs unevaluable).

**Do not touch the Week 1 deployed app.** It builds from the public repo,
`mastering-agentic-ai-by-tga-course · main · week-01/app.py`, and still carries the 16 Aug
submission. It updates only when Week 2 is synced across, deliberately.

---

## 4. Week 2 — decisions locked

| | |
|---|---|
| Track | Track 2 — LangChain + LangGraph, code-heavy |
| Retrieval | **Hybrid: BM25 + dense + rerank**, metadata pre-filter on `service` and `status`. Core, not stretch — the corpus is dense with exact-match tokens |
| Not GraphRAG | Settled by Aish: graph only when answering *requires* traversal. This is passage-finding |
| Query source | Service-scoped, driven by a **structured context request from the detector** — not a free-text chat box |
| Embeddings + generation | **Nebius.** Key is now in `~/llm-class/.env` as `NEBIUS_API_KEY` |
| Latency ceiling | **RE-DECLARED 11 Sep — see below.** Original target: under 3 seconds end to end, declared before building. Missed, and not by anything in the application |
| Refusal | Designed before the happy path |
| Chat UI | Bonus. Sits **below** the deterministic incident state, never above |
| App | **Separate from Week 1**, its own Streamlit Cloud deployment, its own clean `requirements.txt` |

**Streamlit Cloud cannot read `~/llm-class/.env`.** The app must read the key via `st.secrets`
with an environment-variable fallback so the same code runs locally and deployed.

### Latency ceiling — re-declared 11 Sep 2026

**Original target: under 3 seconds end to end.** Declared before building, which was the right
way round. It is missed, and the measurement is more useful than the target was.

| Stage | Measured |
|---|---|
| BM25 index build, once per process | 30 ms |
| **All local retrieval** — metadata filter, BM25, dense, RRF, rerank | **0.6 – 2.7 ms** |
| **Nebius query-embedding round trip** | **3.6 – 8.7 s** |

**Re-declared ceiling: local retrieval under 50 ms. End-to-end latency is bounded by Nebius
query-embedding time, measured 3.6–8.7 s.**

**Why it was missed.** Not by anything in the application. Every stage that was designed, tuned
or worried about completes in under three milliseconds across 106 chunks. The entire budget goes
to a single network call to an 8-billion-parameter embedding model, which consumes 120–290% of
the original ceiling on its own, before any answer generation.

**Why it is not tunable from application code.** `Qwen/Qwen3-Embedding-8B` is the only embedding
model deployed on this Nebius account — the `/models` endpoint returns exactly one. There is no
smaller or faster option to switch to. The remaining routes are a local embedding model (torch,
~900MB, against a five-line deploy file) or dropping the dense arm entirely (sub-millisecond,
but loses the paraphrase half of hybrid retrieval). Both trade something real for a number.

**Decision: do not optimise for it.** A declared ceiling that was measured, missed and explained
is a stronger artefact than one that was never checked. Query embeddings are cached, which helps
repeat questions and demo reruns and does nothing for a first-time question — which is the case
that matters and is stated as such.

Generation adds its own: measured 3.7–10.9 s on `openai/gpt-oss-120b`, which spends output
tokens on reasoning before emitting the answer. **A genuinely cold first-time question measured
21.6 s end to end** — clean venv, no query cache, embedding plus generation. That is the number
to state in the video. Do not quote the warm path as if it were the normal one.

### `.index/` ships with the deploy — decided 11 Sep 2026

**The index is committed. The deployed app never embeds.**

| | |
|---|---|
| `.index/vectors.npy` | **committed**, 1.7 MB |
| `.index/manifest.json` | **committed** — model, dimensions, fingerprint, chunk ids, query instruction |
| `.index/spend.jsonl` | committed as the build record; appended to at runtime, writes are failure-tolerant |
| `.index/query_vectors.npz` | **gitignored** — runtime cache, grows per question asked, correct for nobody else |

**Why ship it rather than embed on first run.** Streamlit Community Cloud sleeps idle apps and
restarts them on demand. An app that embeds at startup would spend 23,309 tokens *and* 30-plus
seconds on every cold start, repeatedly, for a corpus that has not changed. Shipping 1.7 MB
removes a recurring cost and a recurring delay in exchange for a file well inside any limit.

**The safety property that makes this sound.** `embedding.load_index()` recomputes the content
fingerprint of the chunks on disk and compares it to the manifest. If the corpus or the chunking
has changed, it **raises with an explicit message** rather than silently re-embedding. So a stale
index is a loud failure, never a quiet spend. Rebuilding is always deliberate:
`python embedding.py --embed`.

**What this means operationally:** a corpus edit requires a re-embed and a re-commit of
`.index/` before deploy. That is a real constraint and it is the right trade — it makes spending
money an explicit act.

---

## 5. Week 2 — done

### Corpus: 19 internal documents, complete and committed

- 4 service runbooks: `RB-PAY-000` `RB-INV-000` `RB-CAT-000` `RB-AUTH-000`
- 7 endpoint runbooks: `RB-PAY-001` `RB-PAY-002` `RB-INV-001` `RB-INV-002` `RB-CAT-001`
  `RB-CAT-002` `RB-AUTH-001`
- 3 policies: `POL-SLO-001` `POL-SEV-001` `POL-DEPLOY-001` (restricted)
- 2 catalog: `CAT-OWN-001` `CAT-DEP-001`
- 2 postmortems: `PM-2026-014` `PM-2026-009`
- 1 superseded: `RB-PAY-000-ARCHIVED`

Every document carries eleven frontmatter fields: `document_id`, `title`, `document_type`,
`service`, `status`, `supersedes`, `superseded_by`, `owner_team`, `access_level`, `version`,
`last_reviewed`.

**Absolute corpus rule:** no document encodes the answer key. No dataset version strings, no
incident timestamps, no causal attribution. Runbooks describe classes of failure and the checks
that discriminate between them.

**Planted failure cases:**

1. **Partial answer** — `RB-PAY-001` (/checkout) says nothing about sibling corroboration and
   does not even cross-reference `RB-PAY-002`, because a bare reference is followable by the
   retrieval layer. `RB-PAY-002` links back, leaving the synthesis test live in one direction
2. **Superseded document** — `RB-PAY-000-ARCHIVED`, three verifiable contradictions, no warning
   in the body. Only the frontmatter signals it
3. **Restricted** — `POL-DEPLOY-001`, referenced by eleven runbooks, reproduced by none
4. **Near-duplicate distractors** — the four service runbooks deliberately share the scope
   paragraph, class definitions, evidence-floor line and escalation shape
5. **Stale catalog entry** — `CAT-DEP-001` attributes `/orders` to `order-fulfilment`, a
   superseded name for `fulfilment-core`, contradicting `CAT-OWN-001` and `topology.json`
6. **Refusal gaps** — nothing on host metrics, database internals, connection pools, queue
   depth, CDN, or cost

**Deliberate design detail:** `POL-SLO-001` carries the same thresholds as `EVIDENCE_RULES` in
`detection.py`, verified against the file. It also surfaced a real tension — the declared SLO
ceiling is 0.5% 5xx while the evidence rate floor is 1%, so a slice can breach its objective and
still fail the floor. §5 states both as simultaneously true. **Recorded, not reconciled.**

### Golden question set: 24 questions, committed

`my-work/week-02/EVAL_QUESTIONS.md`. Written by **ChatGPT with no corpus access**, deliberately —
if the model that wrote the corpus also writes the questions, they inherit its vocabulary and
retrieval scores well for the wrong reason.

8 answerable · 5 partial · 1 restricted · 6 unanswerable · 4 added from cross-model validation.

All three refusal types must be distinguishable: *not in the corpus* · *exists but above your
access level* · *referenced but absent*.

**The cross-model finding:** five independent models, ~100 questions. Most-requested guidance was
restart a service (5/5), roll back a deploy (5/5), locate logs (4/5), rate limits (4/5). **The
corpus covers none of these** — every runbook says "classification only, not remediation." This
validates the refusal set as realistic rather than contrived, and marks the boundary honestly:
triage layer, not remediation layer.

**Two gaps nobody planted**, found only because the questions came from outside: consumer-
dimension triage, and incident closure criteria. **Do not fill them.** They are honest, and
"an outside perspective found gaps the author didn't" is better writeup material than any planted
case.

---

## 6. Week 2 — remaining, in order

1. **Ingestion** — scaffold, frontmatter parsing, section-aware chunking, theming. *Prompt is
   written and ready, in §8 below. Not yet run.*
2. **Embedding + index** — Nebius, vector store
3. **Hybrid retrieval + rerank** — BM25 + dense, metadata pre-filter
4. **Context assembly** — detector verdict → structured context request → bounded context
5. **Refusal path** — three distinguishable refusal types
6. **Grounded generation** — citations naming source, section, and why retrieved
7. **Measurement** — faithfulness and retrieval quality across the 24 questions
8. **Presentation** — guided views (Incident / Healthy / Insufficient evidence), product name,
   benefit line, page sequence
9. **Vendor layer** — 4 real public docs (AWS API Gateway 5xx, Kubernetes probes, PostgreSQL
   connection limits, Kafka consumer lag). **Cuttable if time is short** — the internal corpus
   carries every graded failure case
10. **One-liner and the handout's framework fields** — technically overdue
11. **Deliverables** — Google Doc, ≤5-minute video, submit via the Week 2 Google Form
    (`https://forms.gle/1EYiudaGDfp2eY9f8` — verify)

**Presentation matters more than it looks.** Aishwarya named UX and product sense as
Builder-of-the-Week criteria, and it is Week 1's weakest area. The guided views are the highest-
value 30 minutes available — the author himself struggled to find the right filter combination,
so a reviewer with five minutes has no chance.

---

## 7. Working rules

- **Claude Code** (WSL, Max subscription, not the API key) is the single coding assistant. One
  continuous session per task.
- **Every prompt saved verbatim** to `my-work/week-02/PROMPTS.md` as it happens, with a response
  summary. Graded, cannot be reconstructed.
- Track A's "type code manually" rule is **suspended**. Vibe coding is the graded skill.
- **Never open the Solution Kit.**
- Screenshot as you build.
- Build in the private repo `genacademy-ai-native`. The public
  `mastering-agentic-ai-by-tga-course` is a **publish target only**, synced by manual `cp`, one
  direction. Never edit in two places.
- **Sync trap:** private `requirements.txt` is a ~90-package pip freeze; public is the clean
  3-line file Streamlit Cloud deploys from. Never overwrite it, never copy `__pycache__/`.
- Keep VS Code in **WSL Remote** (bottom-left reads `WSL: Ubuntu-24.04`). Editing over the
  Windows UNC path flips file modes to 755 and pollutes every diff.
- End every session with a `STATUS.md` update and a commit.

**How I want to work:** bold title then "(Claude Response)" · why before how · one task at a
time with confirmation · direct and honest, no sugarcoating · **call it out if I am polishing
instead of shipping** · reasonably concise · no integration or middleware analogies unless asked.

---

## 8. The immediate next action — this prompt, into Claude Code

Not yet run. Paste it as-is.

```
Week 2 build starts. This session is the ingestion layer only — no embeddings, no
retrieval, no LLM calls. Those come next.

Read my-work/week-02/CORPUS_MANIFEST.md and my-work/week-02/EVAL_QUESTIONS.md
first. The corpus is 19 internal documents at my-work/week-02/corpus/internal/.

Standing instruction: append every prompt verbatim plus a response summary to
my-work/week-02/PROMPTS.md as we go. Graded, cannot be reconstructed.

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
- chunk size distribution: min, median, max, and the count over your split threshold
- the metadata cardinality: how many distinct services, document_types, statuses,
  access_levels
- any topology cross-check mismatches
- any dangling document references found in ## Related documents sections

## Before you write

Tell me:

1. Your chunking strategy in three sentences, including the size target and why it
   matches a typical embedding model's capacity
2. What you plan to do with ## Related documents and why
3. Anything in the corpus structure that will make chunking awkward — I would
   rather know now than discover it in retrieval quality

Then build.
```

**What to check in its answer, before it builds:**

- Chunk size must be tied to a **named** embedding model and its capacity. If it doesn't name
  one, push back — the handout is explicit that chunk size and embedding model are chosen
  together.
- Its decision on `## Related documents`. Structured links rather than embedded text is the
  expected answer; hear its reasoning if it disagrees.
- Question 3 is the load-bearing one. `RB-CAT-001` collapses Symptoms and Discriminating checks
  into one section and adds a "Known non-issues" list; `RB-INV-002` has a numbered retry
  checklist that must not split mid-list. **If it reports the corpus as uniformly structured, it
  did not look.**

---

## 9. Environment

- WSL2 Ubuntu 24.04 on ThinkPad P14s · Docker Desktop · VS Code with WSL Remote
- Multi-root workspace `~/learning.code-workspace`
- Class sandbox `~/llm-class` (venv), `~/llm-class/.env` chmod 600, five keys including
  `NEBIUS_API_KEY`
- Git remotes are on **SSH** for both repos
- Private: `github.com/arunrps/genacademy-ai-native` — source of truth
- Public: `github.com/arunrps/mastering-agentic-ai-by-tga-course` — publish target only
- Week 1 live app: `arunrps-api-incident-explorer.streamlit.app`, builds from the **public**
  repo, still the 16 Aug submission
