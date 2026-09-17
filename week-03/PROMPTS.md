# Week 3 — Prompt Log

Every prompt recorded verbatim, with a summary of the response and a DESIGN RATIONALE block.
Appended as work proceeds, not reconstructed afterwards.

A verbatim prompt records what was asked and the code records what was produced; neither records
*why*. The rationale block holds the decisions, the alternatives rejected and the reason, anything
found in the data that changed the approach, and anything fixed in the first attempt. It is
written for a reader three months out with no code in front of them.

---

## Prompt 1 — 2026-09-11 — Scaffold, four tools, LangGraph state, one real investigation

### Prompt (verbatim)

```
Week 3 build starts. Read my-work/week-03/FRAMEWORK.md first — it is the design,
written before any code, and it is the contract for this build. Do not redesign it.

Standing instructions unchanged: every prompt verbatim plus a design-rationale block
to my-work/week-03/PROMPTS.md as we go. No blanket git add, one explicit path per
stage. Ask before any API call with the token estimate first.

Week 3 is a SEPARATE app in my-work/week-03/. It shares the platform and the story,
not the codebase. Do not import from week-01 or week-02 — copy what you need.

Track 2: LangChain + LangGraph, single stateful investigation agent.

## This session

1. Scaffold: agent.py, tools.py, app.py, clean deploy-only requirements.txt,
   requirements-dev.txt, .streamlit/config.toml with the Week 2 palette.

2. LangSmith tracing from this first commit. Config via st.secrets with an
   environment-variable fallback. Verify ONE end-to-end trace with LangGraph and tool
   child runs visible before continuing. Never commit keys. If a LangSmith config,
   key or network problem blocks you, record it in PROMPTS.md and keep building —
   the agent must run correctly with tracing disabled or unreachable.

3. The four tools, per the contracts in FRAMEWORK.md. get_incident_summary returns
   what changed, never what is to blame. compare_to_baseline takes a model-selected
   slice spec. tools.py must not import streamlit — same boundary as detection.py and
   ingestion.py, and I will test it the same way.

4. The LangGraph state schema. It must carry slices examined WITH their individual
   verdicts, candidate slices not yet examined, suspects raised, suspects discarded
   with reasons, and evidence records. A slice returning INSUFFICIENT disqualifies
   that slice, not the investigation.

5. One real investigation running end to end on a seeded scenario.

## Before you write

Tell me:
1. Your proposed state schema and why
2. Anything in the four tool contracts that will not survive contact with the actual
   week-01 and week-02 code
3. Where you expect the agent to loop or stall, and what step cap you propose

Then build.
```

### Response summary

Answered the three questions from measurement, then built. All five deliverables exist and the
investigation runs end to end: **outcome NAME, 9.8 s, 5 tool calls, 6 turns, zero invalid
evidence ids, zero causal-phrase violations.**

Two things in the tool contracts did not survive contact with the real code and were reconciled
rather than papered over: **row order in `verdicts_to_frame()` is a ranking** the contract
forbids, and **`consumer` is not a slice key** in `detection.py` but a filter applied before
grouping. One thing was measured and is worse than `STATUS.md` recorded: **DET-02a makes 21 of 26
consumer-sliced pairs NOT EVALUABLE**, including `/checkout × mobile-app` at 15.20% with a 53.9×
multiplier.

LangSmith tracing is wired from this commit and is **OFF** — no key exists in the environment or
`~/llm-class/.env`. Recorded below per the framework's instruction; the agent runs normally.

Step caps resolved at **12 tool calls / 8 model turns**. Two quality findings from the first run
are recorded rather than patched.

**Spend: 3 probe calls plus one investigation ≈ 21,000 tokens, ~$0.004.**

### Design rationale

**What exists after this session.** A separate Week 3 app: four read-only tools over copied
Week 1 and Week 2 assets, a LangGraph state machine whose reducers enforce the framework's
central distinction, a Streamlit page with deterministic state above the transcript, and
tracing that cannot break anything. One investigation runs start to finish and its brief
passes both deterministic validators.

---

#### 1. Why the assets were copied and not imported

The instruction was explicit, and it is also the right call for a reason worth recording: each
week is a separately deployable Streamlit app. An import across week directories would make
Week 3's deploy depend on Week 2's directory layout, and Community Cloud deploys a repository
subtree. Copied: `api_logs.csv`, `detection.py`, `topology.py`, `topology.json` from Week 1; the
19-document corpus, `vectors.npy`, `manifest.json`, `ingestion.py`, `embedding.py`,
`retrieval.py` from Week 2.

The copy is not free and the cost should be named: **`detection.py` now exists in two places and
can drift.** The alternative — a shared package — would couple three deploys together. For a
six-week course where each week is graded separately, duplication is the cheaper mistake. If this
were production it would be a library.

One thing resolved itself for free: `ingestion.py` computes its paths from `Path(__file__).parent`,
so the copy in `week-03/` resolves `corpus/internal` and `.index/` to Week 3's own directories
with no edit. The index fingerprint matched on first load, because the corpus files are identical
copies — so `search_runbooks` worked without re-embedding anything.

---

#### 2. THE RANKING LEAK — row order is a ranking, and it would have been invisible

The contract says `get_incident_summary` returns what changed, never what is to blame: no
ranking, no suspect, no narrative. The obvious reading is "strip the scores", and that reading is
insufficient.

Week 1's `verdicts_to_frame()` ends with `for v in rank_verdicts(verdicts)` — it sorts by
descending error rate internally. Wrapping it and deleting the score columns would have produced
a tool return with no numbers indicating importance and **the highest-rate slice in row one**.
For a language model reading a JSON array, position is information. The agent would have opened
every investigation by interrogating whatever the tool had already decided was worst, and the
investigation would have been theatre: the suspect handed over in the ordering, then
"discovered".

Nothing about that would have looked wrong. The tool returns would have contained no ranking
field, the code would have read as compliant, and the agent would have appeared to investigate.
This is the same failure family as the Week 1 consumer sentence and the five other instances now
catalogued — correct-looking output whose defect is in what produced it.

The fix is one line and the reasoning is the valuable part: slices are sorted **alphabetically by
endpoint**, and the return carries a field saying so, because the model should be told that order
means nothing rather than left to infer it.

`build_incident_brief()` and `select_suspect()` are deliberately **not wrapped and not
reachable** from `tools.py`. They name a suspect. That is the agent's job, and a tool that does it
would leave no investigation to conduct.

---

#### 3. THE SLICE MODEL — the contract's wording and the code's model differ

The contract says `compare_to_baseline` accepts a slice spec of "endpoint and/or backend and/or
consumer". `detection.py` says `SLICE_COLUMNS = ["endpoint", "backend_service"]`.

Consumer is not a slice key. It is a **filter applied before grouping**. So a spec carrying a
consumer means "restrict to that consumer's traffic, then evaluate that endpoint × backend
pair". Mechanically reconcilable — and the consequence is not cosmetic:

> A NOT EVALUABLE on a consumer-filtered slice says **that consumer's own baseline is too thin to
> judge against.** It does **not** say the endpoint is healthy.

An agent that believed consumer was a slice dimension would read NOT EVALUABLE as "this consumer
is fine" and move on, which inverts the finding. So the tool return carries an explicit
`slice_model_note` stating the distinction. Telling the model the shape of the data it is reading
is cheaper than hoping it infers it.

`endpoint` is **required** for the same reason: a spec with only a consumer describes many slices,
not one, and a tool that silently returned seven verdicts to a caller who asked about "one slice"
would corrupt the ledger's one-spec-one-examination invariant.

---

#### 4. DET-02a MEASURED — worse than recorded, and it decides what each demo can show

`STATUS.md` deferred DET-02a to the Week 3 generator with a note that `/checkout × mobile-app`
reads NOT EVALUABLE. Measured directly against the dataset for the incident hour:

```
/checkout × mobile-app, 14:00-15:00
  592 requests · 90 failures · 15.20% 5xx · 53.9× baseline · 9 consecutive breach buckets
  -> NOT EVALUABLE
  -> failed: baseline_minimum_failures  (baseline holds 3 failures, 5 required)
```

And across every consumer-sliced pair in that window: **21 NOT EVALUABLE · 4 EVIDENCE
INSUFFICIENT · 1 EVIDENCE SUFFICIENT.** The single evaluable pair is `web-app × /checkout`.

A 53.9× multiplier over nine consecutive buckets is not a marginal call. The gate is refusing to
judge the most obvious signal in the dataset because the *comparison period* is thin, and the
framework's own DET-02a note says baseline sufficiency should gate only the multiplier test
rather than the whole verdict.

**Not fixed here.** It belongs to the generator (a longer warm-up produces a thicker baseline),
the framework says do not redesign, and changing the gate would silently alter every Week 1
number. Recorded because it determines what the three demo paths can actually show:

- **Demo 1, normal investigation** — must stay at endpoint × backend scope, or use `web-app`.
  A consumer-scoped investigation cannot reach a named suspect.
- **Demo 2, human handoff** — abundantly available. Almost any consumer slice produces an honest
  halt with real numbers, which is the path that is hardest to fake and easiest to show.
- **Demo 3, degraded path** — unaffected; it depends on `search_runbooks` failing.

There is an unexpected upside. The framework's hardest requirement — that a disqualified slice
disqualifies the slice and not the investigation — is normally difficult to demonstrate because
you need a real INSUFFICIENT verdict to show it. DET-02a supplies twenty-one of them.

---

#### 5. THE STATE SCHEMA — the reducers are the design, the fields are bookkeeping

The framework lists what state must carry. Satisfying that list is easy; satisfying the
*behaviour* the list exists for is where the design is:

| Field | Reducer | Why |
|---|---|---|
| `evidence` | **append-only** | It is history. History that can be rewritten is not evidence. |
| `slices_examined` | **append-only** | Same, and it is what makes duplicate-call prevention possible. |
| `candidate_slices` | **replaced** | A *shrinking worklist*. |
| `suspects` | **replaced** | A suspect *mutates* from raised to discarded. |

**`candidate_slices` must be replaced, and this is the one that would have broken the
framework's core requirement.** Under an append-only reducer the list only grows, so the terminal
condition *"every reasonable candidate slice has been examined and none yielded sufficient
evidence"* could never become true. The agent would never be able to halt honestly — it would
either spin to the step cap or stop arbitrarily, and "I examined everything" would be unprovable.
The reducer choice is the difference between a halt that means something and one that does not.

**`suspects` must be replaced because suspects mutate.** Raised, then discarded with a reason.
Append-only would leave both versions in the ledger and the brief would cite a suspect that the
same ledger also records as ruled out.

**`slices_examined` and `candidate_slices` are separate collections** — this is what makes the
rule *a slice returning INSUFFICIENT disqualifies that slice, not the investigation* enforceable
rather than aspirational. The agent can only continue correctly if "what I checked" and "what
remains" are distinct, and the second is visibly non-empty. One merged list with a status flag
would technically hold the same information and would make the terminal check a filter over
mutable state instead of a length check over an authoritative worklist.

**Verdicts are stored per slice and never aggregated.** Any roll-up ("2 of 7 slices had
evidence") destroys the difference between disqualified-as-evidence and genuinely-quiet — the
Week 1 NOT EVALUABLE lesson, one layer up.

**Evidence IDs exist so claims can be checked mechanically.** "Zero claims not traceable to a
tool return" needs a join key. `EV-001`, `EV-002`, assigned by code at the moment a tool returns,
are that key, and the validator is a set-difference rather than a judgement.

**The ledger is written by code from tool returns, never by the model**, and injected into every
turn as a user message. Three consequences, all deliberate:

- Candidate slices are **seeded from what `get_incident_summary` actually found**, so "every
  candidate examined" is checkable against data rather than asserted by the thing being audited.
- A duplicate `compare_to_baseline` on an already-examined slice **returns the prior verdict
  without re-running the tool**, with a line telling the agent to examine a different candidate.
  This is the loop I expected to be most likely, given that 21 of 26 consumer slices come back
  unevaluable and a model may well retry hoping for a different answer.
- The per-turn ledger shows tool calls used against the cap, so the agent can see the budget it
  is spending rather than hitting a wall.

---

#### 6. Step caps — 12 tool calls, 8 model turns, and why two caps

FRAMEWORK left this open. Resolved with the reasoning rather than a round number.

The typical path is 6 steps. A thorough run — summary, dependencies, three or four slices, two
runbook searches — lands near 8. **Twelve allows one wrong turn without permitting a spin.**

The **turn cap of 8 is the real guard**, and it is there because the tool-call cap alone does not
catch the loop that matters. A model alternating between two tools without progressing consumes
turns and calls together; a model that stops calling tools but keeps producing prose consumes
turns only. The two caps bound different failure shapes, and a single cap would leave one of them
open.

`MAX_IDENTICAL_FAILURES = 2` handles the third shape. The framework specifies **zero retries on
malformed input** — correctly, since retrying an invalid call just reissues it — but a model that
repeats the same invalid call is a loop, and the loop needs a floor. After two identical
failures the tool is marked unavailable and the agent is told so in the ledger.

Hitting any cap sets `terminal = "STEP_CAP"` and is a **reported outcome**, never an exception.
The first run used 5 calls and 6 turns, so none of this was exercised yet — which means it is
wired, not proven. Worth exercising deliberately before the video.

---

#### 7. Tracing — wired from the first commit, and it is OFF

FRAMEWORK: *"Observability is instrumented early but never load-bearing... The application must
run correctly with tracing disabled or unreachable."*

**No LangSmith key exists.** `~/llm-class/.env` holds `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
`GROQ_API_KEY`, `NEBIUS_API_KEY` and `OPENAI_API_KEY` — no `LANGSMITH_API_KEY` and no
`LANGCHAIN_API_KEY`. So the one end-to-end trace the session asked me to verify **could not be
verified**, and per the framework's own instruction that is recorded here and the build continued.

What was built instead of skipping it:

- `tracing.py` reads either spelling of the key name, from environment first and
  `~/llm-class/.env` second, matching the rest of the project.
- When no key is found it sets `LANGSMITH_TRACING=false` **explicitly** rather than leaving it
  unset. Leaving it unset has meant different things across LangChain versions, and an ambiguous
  default is the thing most likely to produce a confusing half-configured state later.
- `verify()` distinguishes **three** states that otherwise look identical from outside: no key
  configured · configured but unreachable or rejected · working. A missing trace with no
  explanation is what wastes an afternoon.
- `status_line()` puts whichever state it is in the sidebar, so an absent trace is visible rather
  than mysterious.
- Nothing in the module can raise. There is no code path where a key, a project name or a network
  failure reaches an investigation.

**To finish this:** create a LangSmith key, add `LANGSMITH_API_KEY` to `~/llm-class/.env`, and
the status line will flip to ON with the project name. Nothing in the agent changes.

---

#### 8. THE FIRST INVESTIGATION — and two quality findings not patched

```
outcome=NAME   9.8s   turns=6   tool_calls=5
invalid evidence ids: none        causal violations: none

EV-001  get_incident_summary      0.3s  7378 requests, 2.55% 5xx, 7 slices present
EV-002  compare_to_baseline       0.1s  /checkout via payment-service: EVIDENCE SUFFICIENT (14.15% vs 0.41%, 34.7x)
EV-003  compare_to_baseline       0.0s  /cart via inventory-service: EVIDENCE INSUFFICIENT (0.19% vs 0.48%, 0.4x)
EV-004  get_service_dependencies  0.0s  1 declared relationship, drift=False
EV-005  search_runbooks           1.0s  3 passages from RB-PAY-000, RB-PAY-001; withheld restricted: POL-DEPLOY-001
```

The trajectory is genuinely chosen, not scripted: summary → a slice → a *different* slice →
dependencies → runbooks → brief. It cited `EV-002` for its figures, recorded `/cart` as
disqualified with its four failing rules, and produced a next step sourced to `RB-PAY-000` and
`RB-PAY-001`. Both validators passed.

**Finding A — it named a service-level suspect on single-endpoint evidence.** It stopped after
examining 2 of 7 slices, leaving five unexamined, and among them `/refunds via payment-service`
at 10.29%. `/refunds` is `/checkout`'s **sibling on the same backend** — and `RB-PAY-000`, which
the agent itself retrieved, states that sibling corroboration is the check that discriminates
"one endpoint's path is broken" from "the shared backend is broken". The agent named
`payment-service` — a *backend* — without running the check that licenses moving from endpoint
level to service level.

By the letter of the framework this is a correct NAME: a slice returned EVIDENCE SUFFICIENT and
it had the discriminating checks. By the standard of the corpus it retrieved, it skipped the
decisive step. Not patched, because the fix is either a prompt change (tell it to check siblings)
or a state change (seed sibling slices as priority candidates) and both are investigation-method
changes the framework told me not to make unilaterally. **Recommend the second** — it is
deterministic and it uses the topology the tool already returns.

**Finding B — `/cart` was a poor choice of second slice.** It is on a different backend and
nothing connected it to the signal. The agent spent a call establishing that an unrelated
endpoint was quiet, which is true and uninformative, while the informative slice sat unexamined.
This is the same gap as Finding A seen from the other side: nothing in the state tells the agent
which unexamined candidates are *relevant*, only which exist.

**One line worth watching.** The brief says *"examine any recent deployments per
POL-DEPLOY-001"* — a restricted document. This is **not** a violation: `RB-PAY-000`'s
Discriminating checks section, which the agent legitimately retrieved, itself says *"Where a
change window overlaps the onset, follow POL-DEPLOY-001. That document is access_level restricted
and is not reproduced here."* The agent learned the document's subject from permitted material
and named its existence, which the framework explicitly allows. But the line between *naming that
restricted guidance exists* and *summarising what it says* is thin, and the current validator
does not check it. Worth a rule before Week 6, where this becomes the graded question.

---

#### 9. What is wired but not yet proven

Named explicitly so none of it is mistaken for tested:

- **Step caps** — the first run used 5 of 12 calls and 6 of 8 turns. Both caps are untested.
- **`MAX_IDENTICAL_FAILURES`** — no tool failed in this run.
- **Demo path 2, the handoff** — the data supports it abundantly but it has not been run.
- **Demo path 3, degraded** — `search_runbooks` has not been made to fail.
- **`suspects`** — the field and reducer exist; the agent currently expresses suspects only in
  the final brief rather than writing them into state as it goes. Either wire it or remove it;
  a state field nothing populates is a claim in the schema that the code does not honour.
- **`requirements.txt`** — written but not proven in a clean venv. Week 2 taught that the only
  way to know is to build one and install from it alone.
- **LangSmith** — see §7.

---

#### 10. Spend, actual

| Operation | Tokens | USD |
|---|---|---|
| Tool-calling verification, 3 models | ~700 | ~$0.0001 |
| `search_runbooks` query embedding (×2) | ~100 | ~$0.000001 |
| One full investigation, 6 turns | ~20,000 | ~$0.004 |
| **Session total** | **~21,000** | **~$0.004** |

The estimate given before the run was 40–50k tokens; the actual was roughly half, because the
agent finished in 6 turns rather than the 8–10 I budgeted for. Tool returns are also smaller than
Week 2's retrieval contexts — three capped passages rather than six full ones.

Cumulative across Weeks 2 and 3: roughly **$0.005** against a $50 balance with a $1.00 trial
credit. Agent loops are not where this budget goes either; the frozen evaluation set, run
repeatedly, will be.

---

## Prompt 2 — 2026-09-11 — Capture check

### Prompt (verbatim)

```
Did you capture the prompt request and response?
```

### Response summary

Verified rather than asserted. `week-03/PROMPTS.md` exists, is tracked, and was committed in
`98758ff` at 392 lines, carrying Prompt 1's verbatim text, a response summary and a ten-section
design-rationale block.

The verbatim block was checked by extracting lines 18–61 from the file and diffing them against
the prompt as received: **identical, byte for byte, 44 lines.** That is the one part of this log
that cannot be reconstructed later, so "present" was not treated as the same claim as "accurate".

This exchange was not captured at the time of asking and is captured by this entry.

### Design rationale

*No code. The reasoning is about the verification method and one process gap.*

**Why the diff rather than an eyeball.** A verbatim prompt is the only artefact in this file that
cannot be regenerated — the code can be re-read, the rationale can be rewritten from the code, but
a prompt that was paraphrased on the way in is lost. Checking that a fenced block *exists* is a
weaker claim than checking that it *matches*, and the two are easy to conflate when the block
looks right. So the check was mechanical: extract the logged lines, diff against the source, report
the result. Identical, 44 lines.

This is the same discipline the project applies everywhere else — the citation validator checks
cited ids against what was actually supplied rather than trusting the instruction that asked for
it, and the index fingerprint is recomputed rather than assumed. A log that is audited by
inspection is audited by the thing most likely to be wrong.

**The process gap this question exposes, for the second time.** In Week 2 the same question
arrived at the same point in the cycle and produced Prompt 10 there. The pattern is consistent:
the build work gets logged because it is the session's subject, and the *conversation about the
work* — the assessment, the decision, the check — gets logged only when asked for. That is
backwards for a file whose purpose is learning, because the decisions discussed in those exchanges
are exactly the ones not visible in any commit.

Standing instruction says every prompt. The instruction is not ambiguous; the execution has been
selective, twice. Recording that here rather than resolving it silently, because the correction
worth making is to log the short exchanges as they happen rather than at the end of a build
session, and the failure mode is predictable enough to name: a prompt that asks a question rather
than requesting code does not feel like a build step, and gets deferred until the build step is
finished.

**Status of the week-03 log after this entry:** two prompts, both verbatim, both with rationale
blocks. The gaps listed in §9 of Prompt 1 — step caps unexercised, `suspects` having a reducer and
no writer, `requirements.txt` unproven in a clean venv, LangSmith absent — are unchanged by this
entry and remain open.

---

## Prompt 3 — 2026-09-12 — Sibling priority, suspect writer, demo paths, clean venv

### Prompt (verbatim)

```
Approved to proceed. Four items, in this order, then close the session.

1. Seed sibling slices as priority candidates from the topology the tool already
   returns. Deterministic, no prompt change. This fixes the real defect: the agent
   named a backend without running the sibling-corroboration check that RB-PAY-000
   — which it retrieved itself — says discriminates an endpoint-path fault from a
   shared-backend fault. Re-run the same scenario and show me whether /refunds via
   payment-service now gets examined before a service-level suspect is named.

2. suspects: wire the writer or drop the field. A schema field nothing populates is
   a claim the code does not honour. Your call which, but not both.

3. Prove demo paths 2 and 3. Path 2 (evidence-gate handoff) has 21 NOT EVALUABLE
   consumer-sliced pairs to choose from — pick one and show the agent halting with
   numbers. Path 3 (degraded): force search_runbooks to fail and show the
   evidence-only brief with "procedure unavailable". Also exercise the step caps
   and MAX_IDENTICAL_FAILURES at least once so they are tested, not just wired.

4. Clean venv check: create one, install ONLY from requirements.txt, run the agent
   end to end. Report what you had to add.

Then STATUS.md and commit.
```

### Response summary

All four items done. The tests found **three defects in the step caps** and one latent bug in the
`act` node, all fixed. **Tracing turned out to be unblocked** — a LangSmith key has appeared in
`~/llm-class/.env` since the last session — so the one end-to-end trace the framework asked for is
now verified rather than recorded as blocked.

`requirements.txt` needed **nothing added**: 68 packages from 8 declared lines, every test passing.

**Week 3 cumulative spend: ~152,000 tokens, ~$0.024.**

### Design rationale

---

#### 1. Sibling priority — ordering was the entire defect

The previous run named `payment-service`, a *backend*, from one elevated endpoint, and its second
tool call went to `/cart` — a different endpoint on a different backend — while `/refunds`, the
sibling sharing `payment-service`, sat unexamined at position four of the worklist.

Nothing was wrong with the agent's reasoning given what it was shown. The candidate list was
seeded alphabetically from the summary, so `/cart` came first and the decisive slice came fourth.
**The agent was choosing sensibly from a badly ordered list.**

The fix is `_seed_sibling_candidates()`: when a slice clears the evidence gate, the topology is
consulted for endpoints sharing its backend and those are pushed to the **front** of the worklist
with a reason attached. Front rather than appended, because position is the whole mechanism —
appending would have left the ordering exactly as broken.

Two details that matter:

- **`spec_key()` ignores `priority` and `reason`.** A candidate is identified by its three
  dimensional fields only. Had identity included the new fields, the same slice promoted to
  priority would have looked like a *new* slice and been examined twice — the duplicate call the
  ledger exists to prevent.
- **The ledger shows the reason, not just the order.** Listing priority candidates first without
  saying why would leave the agent to infer what the ordering means. The reason names the
  corroboration test explicitly.

Result on the same scenario: `/refunds via payment-service` examined **second**, immediately after
`/checkout` clears. Defect closed.

---

#### 2. `suspects` — wired, and the discard rule is honest about what can fire

Wiring was the right half of the choice: FRAMEWORK names suspects-raised and suspects-discarded as
required state, so dropping the field would have been editing the contract.

The writer is deterministic, in `_update_suspects()`, driven by slice verdicts rather than by the
model:

| Rule | Trigger | Effect |
|---|---|---|
| RAISE | a slice clears the gate | suspect on its backend, scope `service`, corroboration `PENDING` |
| CONFIRM | a *sibling* also clears | corroboration `CONFIRMED`, shared backend supported |
| CONTRADICT | a sibling was **evaluated** and fell short | corroboration `CONTRADICTED`, scope narrows to `endpoint_path` |
| UNAVAILABLE | a sibling returns **NOT EVALUABLE** | corroboration `UNAVAILABLE` |
| DISCARD | every supporting slice disqualified | discarded, with that reason |

**CONTRADICT is the rule that does real investigative work:** it is how a service-level suspect
narrows to an endpoint-level one instead of standing on single-endpoint evidence. That is the
corpus's own logic — `RB-PAY-000` says a quiet sibling points at the endpoint path rather than the
backend — encoded as a state transition rather than left to the model.

**UNAVAILABLE is deliberately not CONTRADICTED**, and this is the distinction the whole project
turns on. A sibling that cannot be measured carries no information in either direction. Treating an
unmeasurable sibling as exoneration is the Week 1 NOT EVALUABLE conflation exactly — a green tick
because something could not be judged.

On the live scenario the ledger reads `SUS-01 payment-service, scope=service,
corroboration=UNAVAILABLE` — correct and slightly unsatisfying: `/refunds` sits at 10.29% but its
baseline holds too few failures to judge, so corroboration was attempted and could not be
established.

**One gap left open, named rather than hidden.** State records `UNAVAILABLE`; the brief does not
read it, and the model still writes that the evidence-sufficient verdict for `/checkout` suffices
to name `payment-service`. The ledger is right and the narration ignores it. Fixing that means
either a brief schema field for corroboration or a prompt change — both investigation-method
changes, so flagged, not applied.

**DISCARD is wired and does not fire on this dataset.** Slice verdicts never change, so supporting
evidence cannot be withdrawn. Stated plainly rather than left to look tested.

---

#### 3. THREE DEFECTS IN THE CAPS, all found by exercising them

This is what "tested, not just wired" was worth.

**(a) `MAX_TURNS = 8` was miscalibrated, and the cap ate the deliverable.** A consumer-scoped run
has **seven** candidate slices, so a thorough investigation needs 1 summary + 7 comparisons + 1
brief = **9 turns minimum**. At 8 the agent did everything right — examined all seven, continued
correctly past every disqualification, exhausted the worklist — then had no turn left to write the
refusal. It reported `STEP_CAP` with **no brief at all**: no outcome, no slice list, no numbers.

The cap behaved as specified ("exceeding it is a reported outcome, not a crash") and the *outcome
was still wrong*, because the budget that should have produced the refusal went on tool calls that
had nothing left to find. I sized the cap from the framework's "typical path is 6 steps" instead of
from the data's seven slices. Now 12 turns / 14 calls.

**(b) A cap that can swallow the brief is a silent failure, not a safety limit.** Raising the
number alone would leave the same shape one step further out. Reaching either cap now converts the
*next* turn into a concluding turn with **no tools offered** — not a request to stop, a removal of
the option. That turn cannot loop: with no tools the reply carries no `tool_calls`, so `route()`
sends it straight to `END`.

My earlier plan said "once candidates are empty and no SUFFICIENT verdict exists, force the
terminal handoff." I described the mechanism and did not build it. The first path-2 run is exactly
what that omission looks like from outside.

**(c) The two caps reported the same condition differently.** The turn cap produced a brief; the
tool-call cap produced nothing, because it set `terminal` in `act` and routed straight to `END`.
Two limits for one situation with different outcomes is a bug, and the one that discards the
deliverable is the wrong one. Both now grant the concluding turn. Verified at `MAX_TOOL_CALLS=2`:
`outcome=REFUSE`, `terminal=STEP_CAP`, `unavailable_evidence` naming the six slices left
unexamined — both facts recorded, deliverable intact.

**Plus a latent bug found by reading rather than running.** In `act`, drift was computed into a
local and never merged into the returned state update, so **topology drift never reached state at
all**. Drift is `False` on this dataset, which is precisely why it went unnoticed: a bug that only
manifests on data nobody has yet. The framework gives drift real behaviour — flag conclusions
depending on a drifted relationship, halt when the drift is load-bearing — and none of it could
ever have fired.

---

#### 4. Demo paths 2 and 3, proven

**Path 2 — evidence-gate handoff, consumer-scoped to `mobile-app`.** All seven slices examined,
every one disqualified, `outcome=REFUSE`, no suspect raised, all seven reported in
`slices_disqualified` with their named failing rules. Both validators clean.

This is the path that most directly demonstrates the framework's hardest rule — a disqualified
slice disqualifies the slice, not the investigation — and it is only reachable because DET-02a
makes consumer-sliced baselines too thin to judge. **A defect in the generator supplies the
evidence for the agent's best behaviour.**

`consumer_scope` was added to `investigate()` to reach it: a real incident report names a consumer
("mobile-app users are seeing errors"), so the scope is stated in the opening message *and* seeded
into every candidate slice. Without it the agent has no reason to filter by consumer and the path
is unreachable.

**Path 3 — degraded, runbooks forced down.** `TRIAGELENS_DISABLE_RUNBOOKS=1` returns the **same
structure a genuine failure returns**, deliberately: a simulated outage the agent could
distinguish from a real one would prove nothing. Result: suspect still named from metrics, and both
`next_diagnostic_step` and `next_step_source` came back **null rather than invented**, with the
unavailability stated and attributed to `EV-004`. That is the framework's requirement — the next
step is omitted rather than recalled from the model's own knowledge of runbooks.

**`MAX_IDENTICAL_FAILURES`** was verified without an API call, by driving the `act` node directly
with a state holding one prior identical failure and replaying the same invalid call. The tool is
marked unavailable on the second identical failure, and the invalid call is executed **once**,
never retried — FRAMEWORK's "zero retries on malformed input" holding while the loop still
terminates.

---

#### 5. TRACING — the blocked item was not blocked any more

The previous entry recorded tracing as OFF because no key existed. **A `LANGSMITH_API_KEY` has
since appeared in `~/llm-class/.env`.** The status line picked it up immediately and reported ON
and reachable — and LangSmith held **zero runs**.

Configured, reachable, tracing nothing. Two independent causes:

1. **`tracing.configure()` was only called from `app.py`.** Every CLI run, demo script and Week 4
   harness call goes through `investigate()` directly, so `LANGSMITH_TRACING` was never `true` in
   those processes. A trace that appears only when Streamlit is the entry point is a coincidence,
   not instrumentation. `configure()` is now called from `investigate()` too; it is idempotent.
2. **The agent uses the raw OpenAI SDK on purpose**, so LangChain's automatic tracing never sees
   the model calls. Unwrapped, the graph nodes trace and their contents do not — a trace showing
   the shape of the run and none of its substance.

Fixed with `wrap_openai` on the client and `@traceable(run_type="tool")` on the tool dispatch.
**The decorator lives in `agent.py`, not `tools.py`** — `tools.py` is the deterministic module
Week 4's evaluators will import, and a LangSmith dependency in the middle of it would make
observability load-bearing for evaluation, which is what the framework forbids.

Verified: **one root `LangGraph` run, 39 runs total — 24 chain (`think`/`act`/`route`), 8 `llm`,
7 `tool`.** LangGraph and tool child runs both visible.

Everything still degrades safely: `traceable()` falls back to a pass-through decorator and
`wrap_client()` returns the client untouched if langsmith is missing, so `import agent` cannot fail
for an observability reason.

---

#### 6. Clean venv — nothing to add

Fresh `python3 -m venv`, `pip install -r requirements.txt` only. **68 packages from 8 declared
lines.**

| Test | Result |
|---|---|
| `tools`, `agent`, `tracing` import | pass — `streamlit` still absent from `sys.modules` |
| All four tools | pass — 7,378 requests · EVIDENCE SUFFICIENT · drift=False · 3 passages |
| Tracing status | pass — reported ON, key source named |
| Agent end to end | pass — `NAME`, 25.6 s, 5 calls, both validators clean |
| Streamlit app renders | pass — no exception, four metrics |

Nothing was missing. The agent run also served as the regression check for every change made
earlier in the session, which is why it was placed last.

---

#### 7. Still open

- **The brief does not read `corroboration`.** State records `UNAVAILABLE`; the narration still
  claims single-endpoint evidence suffices to name a backend. See §2.
- **`DISCARD` never fires** on this dataset — wired, not exercised.
- **Drift behaviour is now reachable but untested**, because drift is `False` here. The framework
  specifies flag-and-continue versus halt-when-load-bearing; neither branch has run.
- **No frozen evaluation set.** One scenario, one window. Outcome match against an
  expected-outcome set is Week 4's and needs the scenario factory.
- **Latency:** 9.8–32.8 s per investigation depending on cache state and slice count. Measured,
  not targeted, per FRAMEWORK.

---

#### 8. Spend, actual

| Operation | Tokens | USD |
|---|---|---|
| Carried in from the scaffold session | ~21,000 | ~$0.004 |
| Item 1 re-run | ~18,000 | ~$0.003 |
| Demo path 2, three runs across the cap fixes | ~75,000 | ~$0.011 |
| Demo path 3, cap tests, traced run, venv run | ~38,000 | ~$0.006 |
| **Week 3 cumulative** | **~152,000** | **~$0.024** |

`MAX_IDENTICAL_FAILURES` cost nothing — driving the node directly needs no model call, which is
worth preferring wherever a mechanism can be tested without one.

---

## Prompt 4 — 2026-09-12 — Capture check, third occurrence

### Prompt (verbatim)

```
Have you add the prompt request and response?
```

### Response summary

Verified: Prompt 3 was captured and is accurate — extracted from the file and diffed against the
prompt as received, **identical byte for byte, 22 lines**, committed in `007ad7d`.

This exchange was not captured at the time of asking, and is captured by this entry.

**That is the third time.** The gap was named in Prompt 2's rationale, the correction was stated
there, and the behaviour did not change. This entry is about that, because recording a lesson twice
and acting on it zero times is a worse failure than the original omission.

### Design rationale

*No code.*

#### 1. What was verified, and how

Same method as Prompt 2, for the same reason: a fenced block *existing* is a weaker claim than a
fenced block *matching*, and a verbatim prompt is the only artefact in this file that cannot be
regenerated from anything else. Lines 458-479 extracted, diffed against the source text.
Identical.

#### 2. The recurrence, stated plainly

| Occurrence | Where | What I wrote at the time |
|---|---|---|
| 1st | week-02 Prompt 10 | Named six gaps in the log, recommended a LEARNING_LOG.md |
| 2nd | week-03 Prompt 2 | Named the pattern: "build work gets logged because it is the session's subject, the conversation about the work gets logged only when asked for" — and stated the correction as "log the short exchanges as they happen rather than at the end of a build session" |
| 3rd | this entry | Did exactly what the 2nd entry said not to |

The diagnosis in Prompt 2 was correct and it was not a fix. I described the failure mode
accurately, wrote down the remedy, and then ran the next session the same way — finishing four
build items, writing their rationale, updating STATUS, committing twice, and never logging the
prompt that asked for any of it until prompted again.

**Why a correct diagnosis changed nothing.** The remedy I wrote was an intention ("log them as they
happen"), and an intention has no trigger. Every mechanism in this project that actually works has
one: the citation validator runs on every brief, the index fingerprint is recomputed on every load,
the duplicate-call check fires inside the tool node. None of those depends on remembering. The
logging remedy depended entirely on remembering, at the one moment — mid-build — when attention is
furthest from the log.

This is the same shape as the defect fixed earlier today, and the irony is worth recording: the
step cap *reported correctly* and still swallowed the brief, because the mechanism satisfied its
stated rule while failing its purpose. An intention to log is the same thing one level up — it
satisfies "the standing instruction is understood" while failing "the prompt is in the file".

#### 3. The change, as a rule rather than an intention

**Write the prompt entry as the FIRST action of a turn, before any other work, with the verbatim
block and an empty response summary. Fill the summary and the rationale at the end.**

That has a trigger — it is bound to the start of the turn, not to remembering at the end — and it
degrades well: if a session is interrupted halfway, the verbatim prompt is already on disk, which
is the part that cannot be reconstructed. The response summary can always be written later from the
commits and the code. The prompt cannot be written later from anything.

It also removes the failure mode entirely for the exchanges that have been missed three times
running, because those are short: a question-shaped prompt with no build work attached reaches the
"write the entry" step before there is anything to be distracted by.

#### 4. Status of the week-03 log

Four prompts, all verbatim, all with rationale blocks. Prompt 1's §9 open items are partly closed
by Prompt 3 — step caps now exercised, `suspects` wired, `requirements.txt` proven, LangSmith
verified. Still open: the brief not reading `corroboration`, `DISCARD` never firing, drift
reachable but untested, and no frozen evaluation set.

---

## Prompt 5 — 2026-09-12 — The brief must read corroboration status

### Prompt (verbatim)

```
One change, then we stop building. Nothing after this.

The brief must read corroboration status. When a suspect is named at service scope
with corroboration=UNAVAILABLE, the narration must say so — name the sibling, say it
could not be evaluated and why, and state that the suspect's scope is therefore
unconfirmed. Do not widen it into a refusal; the evidence supports naming, it does
not support the scope.

Smallest change that works. Then STATUS.md, commit, and we move to deliverables.
```

### Response summary

Three small parts, all in service of one sentence reaching the brief.

The state already knew the answer — `corroboration` has been maintained from slice verdicts since
the suspect ledger was wired in Prompt 3 — and the narration ignored it. So the change is not a new
computation, it is closing the gap between what the system knows and what it says.

1. **Prompt rule 8** requires `scope_confirmation`, and requires the sibling, the verdict, the
   exact failing rule, and the unconfirmed-scope statement when corroboration is not CONFIRMED.
2. **Brief schema field** `scope_confirmation`.
3. **`scope_gap()`**, a deterministic check that the brief actually said it — reported, never
   repaired.

Plus the UI renders the ledger's corroboration status from state regardless of what the model
wrote, because the deterministic fact should not depend on the narration having mentioned it.

Result on the real scenario:

```
outcome=NAME   suspect=payment-service
ledger: payment-service scope=service corroboration=UNAVAILABLE

scope_confirmation:
  UNAVAILABLE - sibling slice /refunds via payment-service was NOT EVALUABLE
  (failed_rules: minimum_requests). Therefore the service-wide scope remains unconfirmed.

scope_gap: ''        validators: invalid=none causal=none
```

Outcome stayed `NAME`, as instructed — the evidence supports naming, it does not support the scope.

### Design rationale

#### 1. Why this was a defect rather than a missing feature

Knowing something in state and not saying it in the output is the same class of problem as a number
with no denominator: the system is right and its output is not. The suspect ledger had recorded
`corroboration=UNAVAILABLE` correctly for two sessions, and the brief had been writing that "the
evidence-sufficient verdict for /checkout is sufficient to name payment-service" — which is true
about *naming* and silent about *scope*.

The distinction the brief was flattening is the one `RB-PAY-000` exists to make: whether one
endpoint's path is broken or the whole backend is. The agent had the material to say "I cannot tell
which" and said nothing instead.

#### 2. Why it is reported rather than repaired

`scope_gap()` returns a description of the omission; it does not append the missing sentence. Two
reasons:

- The brief is the model's sentence. Silently appending the caveat would produce output that looks
  like the model said it, which is the reverse of the evidence/interpretation boundary — code would
  be writing narration while appearing not to.
- An omission that gets auto-filled is an omission nobody ever sees. The same argument as the
  rejected-citations display in Week 2: the value is in knowing the model left it out.

The UI does both, and the split matters: the **ledger status** is rendered from state by code
(deterministic fact, always shown), and the **narration** is the model's, with a separate validator
line saying whether it matched. Two channels, clearly attributed.

#### 3. The "why" nearly got lost, and the validator caught it

The first run after the change produced:

> `UNAVAILABLE – sibling slice /refunds via payment-service could not be evaluated (NOT EVALUABLE,
> EV-003), so we cannot confirm whether the degradation is endpoint-specific or service-wide.`

That names the sibling, states the status, and declares the scope unconfirmed — and `scope_gap()`
returned empty, so the check passed. But the instruction was "say it could not be evaluated **and
why**", and `NOT EVALUABLE` is the verdict, not the reason. **The system was half-applying its own
explained-restraint principle**: Week 1 exists to say *"failed requests 4, below the required 10"*
rather than *"insufficient evidence"*, and this was the latter.

So `scope_gap()` now also requires one of the sibling's `failed_rules` to appear in the stated text,
and rule 8 asks for the exact rule name. The second run names `minimum_requests`.

Worth recording that the first version of the check would have signed off on the weaker sentence. A
validator is only as good as the thing it insists on, and "mentions the sibling and the status" was
a weaker bar than the instruction actually set.

#### 4. Smallest change that works — what was deliberately not done

- **No new tool, no state change, no graph change.** The data was already in state.
- **The outcome classes are untouched.** UNAVAILABLE does not become a refusal or a handoff. The
  framework's terminal conditions are about whether evidence exists, not about whether its scope is
  established, and widening them would have made every single-sibling-unevaluable incident
  unanswerable — which on this dataset is most of them.
- **`CONTRADICTED` and `PENDING` are handled by the same path** rather than special-cased, so the
  narrowing case is covered when a sibling is evaluated and falls short.
- **`scope_gap` is not added to the FORBIDDEN_CAUSAL or citation validators** — it is a third,
  separate check with its own line in the UI, because conflating three different failure modes into
  one pass/fail would hide which one fired.

#### 5. State of the boundary and the build

`tools.py` and `agent.py` still import without pulling Streamlit. App renders clean. Both other
validators still pass. Nothing else was touched.

This closes the first item on Prompt 3's open list. Still open and now deliberately left:
`DISCARD` never fires on this dataset, drift behaviour is reachable but untested, and there is no
frozen evaluation set — all Week 4's, and none of them graded this week.

**Spend: two investigations plus unit checks, ~40,000 tokens, ~$0.006. Week 3 cumulative ~$0.030.**

