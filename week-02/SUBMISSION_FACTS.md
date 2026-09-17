# Week 2 — Factual inventory for the submission document

**Compiled:** 12 Sep 2026 from `my-work/week-02/PROMPTS.md`, cross-checked against the code,
`.index/manifest.json` and `.index/spend.jsonl`.

Facts only, in the order they happened. Each item is tagged:

- **[M]** measured number, with where it came from
- **[D]** design decision, with the reason recorded at the time
- **[X]** defect found and fixed

Numbers marked **(verified 12 Sep)** were re-checked against the code or the index files today
rather than taken from the log.

---

## 1. Corpus build — 21 Aug 2026 (Prompts 1–5)

**[M]** 19 internal documents: 12 runbook, 3 policy, 2 catalog, 2 postmortem. Word counts 429 to
1,745. *Source: Prompt 5 response summary.* **(verified 12 Sep: 19 files on disk)**

**[M]** Every document carries all 11 frontmatter fields: `document_id`, `title`, `document_type`,
`service`, `status`, `supersedes`, `superseded_by`, `owner_team`, `access_level`, `version`,
`last_reviewed`. **(verified 12 Sep: 19/19 for each field)**

**[D]** **No document encodes the answer key** (manifest §1). Runbooks describe classes of failure
and the checks that discriminate between them. Reason: a runbook saying "if /checkout slows after
v2.4.1, roll back v2.4.1" makes retrieval trivial and the evaluation meaningless.

**[D]** **Near-duplicate service runbooks preserved deliberately** (manifest §4.5). The four
service runbooks share the scope paragraph, class definitions, evidence-floor line and escalation
shape. Reason: they are the test of whether metadata filtering rescues precision where pure
similarity cannot. Not to be differentiated.

**[D]** **`supersedes` set to a value rather than `null`** on RB-PAY-000. Reason: makes the
supersession link bidirectional so the field is not dead corpus-wide.

**[D]** **Planted stale catalog entry**: `CAT-DEP-001` attributes `/orders` to `order-fulfilment`,
a superseded name for `fulfilment-core`, contradicting `CAT-OWN-001` and `topology.json`. Reason: a
wrong endpoint-to-backend mapping was deliberately avoided instead, because that would corrupt the
corroboration pair the partial-answer case depends on.

**[X]** Eight manifest issues found before writing, four blocking: `RB-CAT-001` ID collision
between manifest §3 (`/search`) and topology (`/products`); three topology join keys
(`RB-INV-001`, `RB-INV-002`, `RB-CAT-002`) with no document assigned; "15 documents" actually 16
once `RB-PAY-000-v2` was counted; §3's "dependency health checks" having nothing legal to point at
given §4.4's gaps. *Source: Prompt 1 response summary.*

**[M]** `POL-SLO-001` thresholds verified against `EVIDENCE_RULES` in Week 1's `detection.py` — read
from the file, not from the prompt. *Source: Prompt 4.*

**[M]** **Tension recorded and deliberately not reconciled**: the declared SLO ceiling is 0.5% 5xx
while the evidence rate floor is 1%, so a slice can breach its objective and still fail the floor.
`POL-SLO-001` §5 states both as simultaneously true. *Source: Prompt 4.*

**[M]** Four planted failure cases in place: superseded document (`RB-PAY-000-ARCHIVED`, three
checkable contradictions, no warning in the body), partial answer (`RB-PAY-001` / `RB-PAY-002`,
live in one direction only), restricted document (`POL-DEPLOY-001`), refusal gaps (no host metrics,
database internals, connection pools, queue depth, CDN, cost).

---

## 2. Golden question set — 5 Sep 2026

**[M]** 24 questions: 8 answerable, 5 partial, 1 restricted, 6 unanswerable, 4 added from
cross-model validation. *Source: `EVAL_QUESTIONS.md` §1.*

**[D]** **Written by ChatGPT with no corpus access.** Reason: if the model that wrote the corpus
also writes the questions, the questions inherit its vocabulary and retrieval scores well for the
wrong reason — matching phrasing rather than meaning.

**[M]** Cross-model validation across five models, ~100 questions. Most-requested guidance:
restart a service (5/5 models), roll back a deploy (5/5), locate logs (4/5), rate limits (4/5).
**The corpus covers none of these.** *Source: `EVAL_QUESTIONS.md` §4.*

**[M]** **Two gaps nobody planted**, found only because the questions came from outside:
consumer-dimension triage (Q3) and incident closure criteria (Q8). Recorded as honest gaps, not
filled.

---

## 3. Ingestion layer — 6 Sep 2026 (Prompt 7)

### Corpus measurements

**[M]** Whole corpus on disk: **114,540 characters** (19 files, frontmatter included). Body with
frontmatter stripped: **108,917 characters**. **(verified 12 Sep)**

**[M]** After `## Related documents` is removed, the corpus holds **100 sections**: minimum 167,
median 804, maximum 3,439 characters. **11 sections exceed 2,000 characters; 10 fall under 350.**

**[M]** The `## Discriminating checks` class: **12 sections, 1,878 to 3,439 characters** — every one
over any workable cap. This is the section retrieval most needs.

**[M]** Untitled preamble between `# Title` and the first `##`: present in **all 19 documents**,
ranging **167 to 1,174 characters**. `RB-AUTH-000`'s is **1,174 characters**.

**[M]** `## Related documents` sections: **87 to 369 characters**, **104 references total**.
Inbound reference counts: `POL-SLO-001` **18 of 19**, `POL-SEV-001` 17 of 19, `CAT-OWN-001` 16 of
19, `POL-DEPLOY-001` 12 of 19.

**[M]** Largest atomic blank-line-delimited paragraph block anywhere in the corpus: **1,397
characters** (a numbered lesson in `PM-2026-014`), across **340 blocks**. `RB-INV-002`'s five-step
retry checklist is 557 characters; the largest markdown table is 711 characters (`CAT-OWN-001`).

### Decisions

**[D]** **Chunk size set in characters by section structure, NOT by the embedding model's context
window.** Reason, measured: a 32,768-token window is roughly 130,000 characters and the entire
corpus is 114,540 — the whole corpus fits in one window. Sizing chunks to model capacity would
produce one chunk per document: 19 vectors averaging 5,700 characters each, retrieval returning
whole documents, and the planted partial-answer test untestable. The binding constraint is that a
chunk must be one idea.

**[D]** **Target 1,200 / hard cap 2,000 / minimum section 350 characters**, derived from the
100-section distribution above. Target is above the median section so most sections emit as a single
chunk; the cap splits the 11 oversized sections and nothing else; below 350 a chunk is one or two
sentences and embeds to a vector dominated by shared ops vocabulary.

**[D]** **"Never mid-sentence" holds by construction, not by best effort.** Because the largest
atomic block is 1,397 characters and the cap is 2,000, no block is ever forced to split.
`ingestion.py` therefore contains no sentence-splitter fallback — nothing can reach one.

**[D]** **`## Related documents` parsed to structured links, never embedded.** Reason: each section
is 87–369 characters of document IDs and titles that appear verbatim elsewhere, making them the
highest-similarity lowest-information text in the corpus; and `POL-SLO-001` being referenced by 18
of 19 documents means embedding all nineteen lists would manufacture nineteen near-identical
vectors — a distractor set on top of the ones the manifest plants deliberately.

**[D]** **Gloss text kept rather than discarded.** Reason: several runbooks write
`POL-DEPLOY-001 — deployment validation and rollback (restricted)`, and that marker is the corpus
stating a document exists but is not reproduced — the distinction the restricted refusal path has
to make.

**[D]** **Untitled preamble retained as an `(overview)` section.** Reason: `RB-AUTH-000`'s 1,174
characters carry the "rejection is cheap, so errors can rise while p95 stays flat" principle and the
4xx/5xx split warning, which is what evaluation **Q5** needs. Iterating `##` sections drops it
silently and the corpus loses its answer to a graded question with nothing looking wrong.

**[D]** **Heading matched on a normalised form with the ordinal stripped.** Reason: 16 documents use
`## Related documents`; the three policies use `## 5.`, `## 7.` and `## 8.`. An exact match misses
all three in both directions — their links go unparsed AND their link lists get embedded as prose.

**[D]** **Chunk IDs derived from `document_id` plus an integer, never from title.** Reason:
`RB-PAY-000` and `RB-PAY-000-ARCHIVED` carry an identical title by design.

**[D]** **Determinism is a hard requirement**: sorted filename order, integer-indexed chunk IDs, no
dependence on dict ordering, set iteration, clock or random seed. Reason: re-embedding costs money.

### Defects in the first output, found and fixed

**[X]** **Five stranded chunk tails, 168 to 289 characters** — below the 350-character minimum that
exists to prevent exactly that. The minimum was enforced between sections and violated between the
pieces of a section: the same bug one level down. Worst instance: `RB-INV-002`'s *"Bulk retries are
never authorised from this document, at any class, for any number of requests"* landed in its own
289-character chunk, separated from the five-step checklist it qualifies — so a retrieval hit on the
checklist would return the procedure without the prohibition. **Fix:** tails fold back into the
preceding chunk when the join fits under the cap.

**[X]** **Topology cross-check reported a by-design state as a mismatch.** It flagged
`RB-PAY-000-ARCHIVED` as "runbook in corpus, not declared in topology". That document is superseded,
and a catalog still pointing at it would be the actual defect. **Fix:** only *current* runbooks are
expected to be declared. Reason it mattered: a check that fires unconditionally trains its reader to
skip the line, and that line is the only place real drift would appear.

**[D]** **Token counts deliberately not produced**, and no characters-divided-by-four estimate
printed in their place. Reason: an estimate presented as a token count is a guess that looks like a
measurement, and the number's purpose is to be the pre-approval figure for a run that spends credit.

### Ingestion report as shipped

**[M]** **19 documents loaded, 0 failures. 106 chunks.** Characters: min **358**, median **881**,
mean **950**, max **1,855**, total **100,745**. Over target (1,200): **28**. Over hard cap (2,000):
**0**. **(verified 12 Sep)**

**[M]** Metadata cardinality: 5 services, 4 document types, 2 statuses, 2 access levels, 4 owner
teams.

**[M]** Topology cross-check: **no mismatches** — all 11 declared `runbook_id`s exist, all 11
current runbooks are declared. 8 documents undeclared by design (3 policy, 2 catalog, 2 postmortem,
1 superseded).

**[M]** Document references: **104 parsed links, zero dangling**, none pointing to a superseded
document. `RB-PAY-000-ARCHIVED` referenced by nothing.

**[M]** Verified, not asserted: `import ingestion` leaves `streamlit` out of `sys.modules`;
chunking byte-identical across three runs (SHA-256 over all chunk IDs and text); all 11 metadata
fields on all 106 chunks; no `Related documents` text in any chunk; zero duplicate chunk IDs.

---

## 4. Embedding and retrieval — 11 Sep 2026 (Prompt 8)

### The model that did not exist

**[M]** `BAAI/bge-en-icl` returns **404 on both** `api.studio.nebius.com` and
`api.tokenfactory.nebius.com`. The `/models` endpoint on both returns **24 models and exactly one
embedding model**: `Qwen/Qwen3-Embedding-8B`.

**[M]** **Output dimension 4,096**, measured from `len(response.data[0].embedding)` on a live call,
not read from a model card. **(verified 12 Sep: `.index/manifest.json` records `dimensions: 4096`)**

**[M]** Cost of finding out: **18 tokens** (two probe calls of nine tokens each).

**[D]** Switched to `Qwen/Qwen3-Embedding-8B` — the only embedding model on the account. **The 106
chunks did not change.** Reason that held: chunk sizes are expressed in characters and driven by
section structure, so the model choice cannot invalidate the chunking.

### The token count

**[M]** The earlier figure of **26,178 tokens** was `bge-en-icl`'s tokenizer counting text that was
never going to `bge-en-icl`. Under Qwen3's tokenizer: **23,309 tokens** — min 85, median 211, mean
219, max 410.

**[M]** **The API then billed exactly 23,309 tokens.** Estimate and invoice agree to the token.
**(verified 12 Sep: `.index/manifest.json` records `tokens_billed: 23309`)**

**[M]** Largest chunk: **410 tokens against a 32,768-token window — 1.3% of capacity.**

### Decisions

**[D]** **Asymmetric query instruction.** Qwen3-Embedding is instruction-tuned: queries carry a task
prefix, documents do not. The instruction string is **recorded in the index manifest** because it is
part of the index contract — change it later and queries quietly stop matching the documents they
were built against. Reason it matters: omitting the prefix fails invisibly, results merely get worse.

**[D]** **Reciprocal rank fusion, k=60, instead of a weighted score blend.** Reason: BM25 scores are
unbounded and corpus-dependent, cosine sits in [-1, 1], and any weighted sum needs a normalisation
constant that is a tuning parameter in disguise and would need re-deriving whenever the corpus
changed. RRF uses only ranks, has one parameter, and k=60 is the original paper's value left
deliberately untuned.

**[D]** **Deterministic rerank instead of a cross-encoder.** Reason: no rerank model exists on the
account; a local cross-encoder needs torch (~900MB against a five-line deploy file); an
LLM-as-reranker would make *retrieval* probabilistic, breaking the project's core principle, and add
a second round trip. Stage 5 is therefore a per-document cap (2 chunks) plus demotion of superseded
documents — both aimed at failures the corpus plants deliberately.

**[D]** **Ties break on corpus position, not list order.** Reason: makes reproducibility a property
of the code rather than an accident.

**[D]** **`vectors.npy` committed** (1.7MB). Reason: Streamlit Community Cloud sleeps idle apps, so
an app that embedded at startup would spend 23,309 tokens and 30-plus seconds on every cold start.

### Latency, measured

| Stage | Measured |
|---|---|
| BM25 index build (once per process) | **30 ms** |
| All local retrieval — filter, BM25, dense, RRF, rerank | **0.6 – 2.7 ms** |
| Query embedding round trip to Nebius | **3.6 – 8.7 s** |

**[M]** The declared ceiling was **under 3 seconds end to end**, stated before building. It is
missed by the query embedding alone, which consumes **120% to 290%** of the ceiling before any
generation.

**[D]** **Do not optimise for it.** Reason: the only embedding model on the account is the slow one,
so it is not tunable from application code. The remaining options each trade something real — a
local model needs torch; dropping the dense arm loses the paraphrase half of hybrid retrieval.
Re-declared as: local retrieval under 50 ms, end-to-end bounded by Nebius embedding time.

### Defect

**[X]** A directory-wide `git add` swept a **340-line deletion** of the previous session's rationale
block into a commit about retrieval. `git status` showed the file as modified and it was committed
without the diff being read. **Fix:** restored from the prior commit; standing rule adopted of one
explicit path per staging step.

---

## 5. Evaluation, generation, UI — 11 Sep 2026 (Prompt 9)

### THE MAIN RESULT — the score-based refusal gate does not work

**[M]** Top dense cosine similarity per question, by the class the golden set assigns:

| Expected class | n | min | median | max |
|---|---|---|---|---|
| answered | 8 | **0.515** | 0.607 | 0.755 |
| partial | 7 | 0.506 | 0.541 | 0.660 |
| restricted | 1 | 0.546 | 0.546 | 0.546 |
| not_in_corpus | 8 | 0.442 | 0.506 | **0.553** |

**[M]** **Answerable floor 0.515. Not-in-corpus ceiling 0.553. The ranges overlap.** Three
answerable questions sit below the highest-scoring unanswerable one:

```
0.553  Q16  gateway vs dns              — nothing in corpus
0.543  Q1   checkout throwing 503s      — answerable
0.530  Q17  external payment provider   — nothing in corpus
0.515  Q12  which runbook is current    — answerable
```

**[D]** **The similarity threshold was designed, measured and abandoned.** Reason: no value works —
a threshold at 0.52 refuses Q12; at 0.56 it refuses Q1 and Q12; in between it answers Q16 and Q17.
Not a tuning failure: cosine measures topical proximity, and an unanswerable question about this
platform is topically adjacent to the corpus.

**[D]** **The refusal boundary was redrawn instead.** Deterministic in code: access-level refusal,
superseded handling, which passages the model may see, and what counts as a valid citation.
Model-judged: whether the supplied passages actually answer the question. Reason: thresholds and
permissions are policy; "does this paragraph contain the procedure being asked for" is reading
comprehension, and making it deterministic would need a labelled corpus that does not exist.

### Retrieval results

**[M]** **21 of 27 expected documents found (78%).** All expected documents surfaced on **10 of 16**
questions; at least one on **14 of 16**. Median rank of found documents **2**; found at rank 1 on
**7 of 21**.

### Generation results

**[M]** Generation estimate before the run: **54,559 input tokens**, counted with the real tokenizer
on the actual prompts. Actual: **55,359 — 1.5% over**, the gap being the shadow-retrieval prompts not
modelled in the estimate. Output: **14,558** against 7,200 assumed.

**[M]** **Outcome agreement 16 of 24.** Full confusion:

| expected → produced | n | questions |
|---|---|---|
| answered → answered | 7 | Q1, Q5, Q6, Q7, Q9, Q12, Q15 |
| answered → partial | 1 | Q2 |
| not_in_corpus → answered | 1 | **Q11** |
| not_in_corpus → not_in_corpus | 3 | Q10, Q18, Q24 |
| not_in_corpus → partial | 3 | Q16, Q17, Q22 |
| not_in_corpus → restricted | 1 | Q13 |
| partial → answered | 2 | Q19, Q20 |
| partial → partial | 5 | Q3, Q8, Q14, Q21, Q23 |
| restricted → restricted | 1 | Q4 |

**[M]** **Zero fabricated citations across all 24 questions.** The deterministic citation validator
found nothing to reject.

**[M]** **Q11 is the one genuine failure.** *"admin-portal blank but web-app fine, frontend issue or
something behind it?"* — the corpus has nothing on frontends or CDN. It answered, citing
`RB-PAY-000` and `RB-PAY-001`, by applying the sibling-endpoint corroboration pattern.
`admin-portal` and `web-app` are **consumers, not endpoints**, so they share no backend.

**[M]** **Q13 may be the golden label rather than the system.** Expected `not_in_corpus`; produced
`restricted`. The model correctly said no restart procedure exists; the deterministic gate added the
restricted flag because `POL-DEPLOY-001` would have ranked.

**[M]** **Q17 half-worked.** `CAT-DEP-001` — the passage where the corpus refuses itself — was
retrieved at rank 5 and was in the context, but the answer cited `RB-PAY-001` and `RB-PAY-000`
instead.

**[M]** Error distribution is asymmetric: **4 of 8** disagreements are refusal-to-partial (hedging);
**3 over-claim** (Q11, Q19, Q20); **1 under-claims** (Q2).

### Decisions

**[D]** **Citation validity enforced by code, not by the prompt that requested it.** Every cited
`document_id` is checked against the supplied set; anything else is stripped and reported. Reason: a
prompt is a request, not a guarantee.

**[D]** **Restricted detection by shadow retrieval** — the same query re-run with the access filter
lifted, reusing the same query vector, so it costs **zero extra tokens and no extra round trip**.
Reason: `POL-DEPLOY-001` is excluded from every query, so reporting that exclusion every time is
noise; what matters is whether it would actually have *ranked*.

**[D]** **`.index/` ships with the deploy; the app never embeds.** Made safe by `load_index()`
recomputing the content fingerprint and **raising on a mismatch** rather than silently re-embedding
— so a stale index is a loud failure, never a quiet charge.

**[D]** **`query_vectors.npz` gitignored** as a runtime cache. **Spend log and query cache writes
tolerate a read-only filesystem**, because an accounting write must not fail a request that already
succeeded.

**[D]** **The API key crosses the Streamlit boundary in one direction only**, in `app.py`, before
`embedding` is imported: `st.secrets` lifted into `os.environ`, the one channel both local and
Streamlit Cloud share.

**[D]** **UI layout: deterministic state above, chat below.** Reason: a page that puts generated
prose on top and evidence underneath inverts what the project argues.

### Defects

**[X]** **`max_tokens=900` truncated the JSON mid-object**, so the parse failed. It presented as a
format problem and was a budget problem — `gpt-oss-120b` spends output tokens on reasoning before
emitting the answer. **Fix:** raised to 2,500, added `response_format=json_object`, and the error
message now points at the token budget when a reply ends mid-object.

**[X]** **The restricted notice fired on all 24 questions**, including ones about DNS and logging.
**Fix:** shadow retrieval, so only a restricted document that would have ranked is named.

**[X]** **The refusal's "what the corpus does hold" list offered `POL-DEPLOY-001`** to
operations-level callers — handing them a document they cannot open and collapsing the two refusal
types into one. **Fix:** restricted documents excluded from that list.

### Clean virtual environment

**[M]** Fresh venv, installing only from `requirements.txt`: **49 packages from 5 declared lines.**
**Nothing had to be added.**

**[M]** Six tests passed, including the one that mattered: **a cold end-to-end question with the
query cache moved aside — 21.6 seconds**, answered, zero invalid citations.

**[M]** The only thing that does not work in the clean venv is `estimate_generation()`, which needs
`transformers` and raises a clear message. Correct by design: the deployed app never prices a run.

---

## 6. Spend — actual, from `.index/spend.jsonl`

**(verified 12 Sep, authoritative)**

| Operation | Calls | Tokens | USD |
|---|---|---|---|
| `embed_corpus` | 1 | 23,309 | $0.000233 |
| `generate` | 29 | 86,276 | $0.000863 |
| `query` | 30 | 1,396 | $0.000014 |
| **Total** | **60** | **110,981** | **$0.001110** |

Rate used: $0.01 per million tokens for embeddings. Every figure is read back from each API
response's usage block, never computed from an assumed rate.

Note: `PROMPTS.md` Prompt 9 quotes a session total of **107,709 tokens / $0.001077**. That was a
point-in-time figure; the ledger has since grown with the clean-venv test and later runs. **Use the
ledger figures above.**

Against a $50 balance with a $1.00 trial credit burning first: the whole of Week 2 used about
**0.11% of the trial credit alone.**

---

## 7. Items recorded as open or deliberately not done

**[D]** **Vendor layer not built.** `corpus/vendor/` is empty. Four real public documents (AWS API
Gateway 5xx, Kubernetes probes, PostgreSQL connection limits, Kafka consumer lag) were specified and
deferred. Reason: the internal corpus carries every graded failure case.

**[D]** **Q1's ranking defect not fixed.** `EVAL_QUESTIONS.md` expects RB-PAY-000 then RB-PAY-001;
the system returns RB-PAY-001 first, whose own opening line is *"Use RB-PAY-000 to establish the
class first."* BM25's strongest tokens are `checkout` and `503s`, and the corpus's precedence
relation is not a lexical signal. Three candidate fixes listed (use the parsed link graph; rank
service runbooks above endpoint runbooks; let generation order the citations); **none applied**,
because one question is not evidence.

**[D]** **The two unplanted gaps (Q3 consumer triage, Q8 incident closure) deliberately not
filled.** Reason: they are honest gaps an outside perspective found, which makes better refusal
cases than anything planted.

**[M]** **No committed test suite for Week 2.** Week 1 has 49 passing tests; Week 2's boundary and
determinism were verified by hand.

---

## 8. Cross-cutting: one failure pattern, six instances

Recorded in `PROMPTS.md` (week-02 Prompt 10 and week-03 Prompt 2) as a single named pattern —
**output that looks right**: nothing throws, nothing appears broken, and every instance survives a
review that reads the report instead of the data.

1. Week 1 — the ungated consumer sentence, printing the same conclusion at 100% vs 0%
2. Week 1 — p95 over 2xx returning `None` and being formatted directly
3. Week 2 — the stranded `RB-INV-002` tail separating the bulk-retry prohibition from its checklist
4. Week 2 — the topology cross-check flagging a by-design state as a mismatch
5. Week 2 — the restricted notice firing on all 24 questions
6. Week 2 — Q11 answering a frontend question by transferring the sibling-endpoint pattern

The detection method that now catches this class: check the output against the data that produced
it, not against the output's own shape. The citation validator, the fingerprint recomputation and
the score-distribution measurement are all instances of that.
