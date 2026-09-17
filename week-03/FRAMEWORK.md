# Week 3 — Agent Framework

**TriageLens Investigator** · written 11 Sep 2026, before any code.
**Build track: Track 2 — LangChain + LangGraph, single stateful investigation agent.**

Written first, deliberately. The instructors' strongest negative signal is a project that looks
one-shotted; their strongest positive is architectural intent plus justification. This file is
the intent, dated before the build.

---

## The one-liner

> My agent helps an **on-call engineer** investigate an API production incident from alert to
> evidence-backed next diagnostic step in the **TriageLens workspace**, replacing **~30 minutes
> of pivoting between gateway metrics, service dependencies and runbooks and correlating that
> evidence by hand mid-incident**. It investigates on its own using **4 read-only tools** —
> incident summary, baseline comparison, service dependencies, runbook search — and hands off to
> a human **when evidence is insufficient or conflicting; all production actions remain outside the
> agent**. I'll know it works when an engineer can identify the best-supported suspect, see
> supporting and contradicting evidence, and know what to check next **in under 5 minutes**,
> with **the expected investigator outcome matched in ≥90% of a frozen evaluation set**, **zero
> claims not traceable to a tool return**, and **no causal assertions at any confidence**.

---

## The framework

### Agent goal

Given an incident window, decide what evidence is needed, gather it through deterministic
tools, and produce a cited investigation brief that names the best-supported suspect, shows
what contradicts it, and states the next diagnostic step. It suspects; it never concludes cause.

### Where do people use it?

Streamlit console — the same surface as Weeks 1 and 2, as a separate app. Deterministic incident
state on top, agent transcript below it, never above.

### What steps does it take, in order?

1. Resolve scope from `topology.json` — which services, endpoints and consumers are in play
2. Pull the deterministic incident summary for the window
3. Compare against the dataset baseline (first 120 minutes), never a baseline derived from the
   selected window
4. Form candidate suspects from what the metrics show
5. Retrieve discriminating checks from the runbook corpus for those suspects
6. Narrate: best-supported suspect, supporting evidence, contradicting evidence, next check —
   every claim cited to a tool return

**These steps are a typical path, not a fixed pipeline.** The model chooses which tool to call
next from what the previous call returned; it may skip tools, repeat `compare_to_baseline` on
different slices, or halt early. Two incidents should produce visibly different trajectories.

### Tool contracts — the line that makes this agentic

`get_incident_summary` returns **what changed**, never **what is to blame**: per-slice counts,
rates, p95 and which slices breached which thresholds. No ranking, no suspect, no narrative.

`compare_to_baseline` accepts a **model-selected slice spec** (endpoint and/or backend and/or
consumer) so the agent actively chooses what to interrogate.

If the summary tool named the suspect, there would be no investigation left to conduct. The
Week 1 boundary restated: deterministic code computes; the model decides what to compute about.

### What can it actually do? (4 tools, all reads)

| Tool | Read/write | What it returns |
|---|---|---|
| `get_incident_summary` | read | Deterministic brief for a window: rates, counts, p95, affected slices |
| `compare_to_baseline` | read | Slice metrics vs dataset baseline, plus the evidence-gate verdict (SUFFICIENT / INSUFFICIENT / NOT EVALUABLE) |
| `get_service_dependencies` | read | Declared topology relationships, with the drift banner |
| `search_runbooks` | read | Hybrid retrieval over the 19-document corpus, with access-level and superseded handling intact |

**No write tools in scope.** Escalation drafting is deliberately out — see "What should it never
do." If a `draft_escalation` tool is added later it is a write and requires human approval
before it fires.

**Deferred, not cut:** `get_change_events` (deployment history) and `get_blast_radius`. Both
need data the generator does not currently produce. Adding them means building a data source
before the agent exists, and the agent is the graded artefact. Revisit only if the build lands
early.

### What does it need to remember?

**Session only.** Within one investigation: slices already examined **and their
individual verdicts**, candidate slices not yet examined, suspects raised, suspects discarded
and why, evidence already gathered. This exists so the agent does not re-request
evidence it already has and does not re-raise a suspect it already ruled out.

**No cross-session memory, and no persistent store.** Considered and rejected: an incident
investigation is bounded by its window, and carrying findings between unrelated incidents would
import exactly the kind of stale conclusion the Week 1 consumer-sentence bug came from. Memory
would have to earn its place; here it does not.

### What should it never do?

- **Assert causation.** Suspect, never caused — at any confidence level
- State any figure, rate or timestamp that did not come from a tool return
- Reveal the contents of a restricted document; it may name that one exists above access level
- Cite a superseded document as current
- Page, escalate, notify or write anywhere. It has no write tools
- Treat simulator ground truth as investigator evidence
- Proceed past an INSUFFICIENT or NOT EVALUABLE verdict as though evidence existed

### Human-in-the-loop

- **Slice-level verdict is not investigation-level termination.** A `compare_to_baseline(slice)`
  returning INSUFFICIENT or NOT EVALUABLE **disqualifies that slice as evidence** and is recorded
  as such. The investigation continues while reasonable candidate slices remain unexamined. The
  agent does not substitute reasoning for evidence on a disqualified slice, and it does not give
  up because one slice failed
- **Investigation-level terminal handoff** occurs when: every reasonable candidate slice has been
  examined and none yielded sufficient evidence; or conflicting evidence prevents a supported
  conclusion; or topology drift on a load-bearing relationship makes any conclusion unreliable.
  The agent then halts and reports which slices it examined, what each returned, and why no
  suspect can be named
- **Conflict stop:** when retrieved evidence contradicts itself, it surfaces both sides and
  hands over rather than choosing
- **Before any write:** none exist today; if one is added, approval gates it
- The engineer's own next action — running the suggested check, escalating — is always theirs

**Handoff is terminal, not an interrupt-and-resume.** The agent stops, states what is missing or
conflicting with numbers, and returns control. No LangGraph interrupt, no resume-with-context
path. Chosen because it is the simplest thing that is honest, it matches the evidence gate's
semantics (insufficient evidence is a finding, not a pause), and it demos in fifteen seconds.

**Topology drift is conflicting evidence.** When `get_service_dependencies` reports drift
between declared topology and observed traffic, the agent names the drift in the brief, uses the
declared topology but flags every conclusion that depends on the drifted relationship, and does
not silently treat declared topology as ground truth. Drift alone does not halt the
investigation; drift on a relationship load-bearing for the suspect does.

### What happens when something breaks?

- **A tool returning nothing is evidence, not an error.** "No runbook covers host metrics" is a
  finding and gets reported as one
- **Tool criticality — failure is not uniform:**
  - `get_incident_summary` — **critical.** Without it there is no incident to investigate. Halt
  - `compare_to_baseline` — **critical for naming a suspect.** Without it, no suspect may be
    raised; the agent may still report what the summary showed, explicitly as unevaluated
  - `get_service_dependencies` — **non-critical.** Continue; flag that relationships are
    unverified
  - `search_runbooks` — **non-critical.** Continue with an evidence-only brief and "procedure
    unavailable"; the next diagnostic step is then stated as unsourced or omitted
- **Retry policy:** one retry on transient failure (timeout, 5xx, connection). **Zero retries on
  malformed or invalid requests** — those are returned to the agent as a structured error to
  correct, not retried
- Whatever the outcome, the brief states which evidence was unavailable and why. Never silently
  proceed as if a tool returned empty
- **Step cap** on the agent loop so it cannot spin re-requesting the same evidence. Exceeding it
  is a reported outcome, not a crash
- **Malformed tool input:** validate and return a structured error the agent can act on, rather
  than a stack trace

### How do you know it worked?

**The primary metric is end-to-end task success, binary per run.** A run succeeds only when all
five hold:

1. Evidence-gate behaviour is correct — it stopped when it should have, proceeded when it could
2. The best-supported suspect is correct, **or** the agent correctly refused to name one
3. Supporting and contradicting evidence are traceable to tool returns
4. The next diagnostic step is grounded in retrieved material
5. No unsupported causal claim appears

Reported as a success rate across a small frozen Week 3 scenario set. The full evaluation
framework belongs to Week 4; this is the minimum that makes "it worked" mean something.

Three supporting numbers, all machine-checkable:

1. **Outcome match:** the agent's outcome matches the **expected investigator outcome** in
   **≥90%** of a frozen evaluation set. Ground truth is what a competent investigator should
   conclude **from observable evidence**, not what the simulator seeded. Outcome classes:
   `NAME <service>` · `REFUSE — insufficient evidence` · `HANDOFF — conflicting evidence`.
   "Seeded suspect ranked first" applies **only** to scenarios deliberately constructed so the
   seeded suspect is supportable from visible evidence. Simulator truth is not investigator
   evidence, and grading against it would violate the principle the system is built on
2. **Citation validity:** **zero** claims not traceable to a tool return — reusing the Week 2
   citation validator
3. **Causal restraint:** **zero** causal assertions, checked against a forbidden-phrase set

Plus a cost/latency pair, as the handout requires quality and cost together: agent wall-clock
per investigation and tokens per run, both measured and reported rather than targeted.

**Status of every number in this document.** ~30 minutes of manual work is an **assumption**,
not a measurement. Under 5 minutes and ≥90% are **targets declared before building**, not
results. None of them is stated as achieved until the evals produce evidence, and a missed
target is reported as a miss.

---

## Open decisions — resolve during the build, record the answer here

- [ ] Frozen evaluation set size and how scenarios are seeded
- [ ] Step cap value, and what the agent reports when it hits it
- [ ] Whether the four tools are enough to reach a suspect, or whether a fifth is forced by the
      first real run
- [ ] Agent wall-clock target — Week 2 measured 21.6s cold for a single query; several tool
      calls will exceed that, so the number is measured, not promised
- [ ] LangGraph state schema — evidence records and IDs, slices examined, suspects raised and
      discarded with reasons, duplicate-call prevention, terminal conditions. Designed during
      the build against real tool returns, not guessed in advance

## Observability is instrumented early but never load-bearing

LangSmith tracing goes in at the first commit and one end-to-end trace is verified before the
build continues. **If a LangSmith config, key or network problem blocks progress, record it in
`PROMPTS.md` and carry on building the locally runnable agent.** The application must run
correctly with tracing disabled or unreachable. Observability is a lens on the system, never a
dependency of it.

## Demo paths — design the build so these three are quick to show

1. **A normal investigation** — suspect named, evidence cited, next step grounded
2. **A human-handoff path** — evidence gate returns INSUFFICIENT, agent halts and says why with
   numbers
3. **A degraded path** — `search_runbooks` fails; evidence-only brief with "procedure
   unavailable"

These are the video. Have a scenario ready for each before recording.

## Not doing, and why

- **Multi-agent / deep agents** — Arvind: only where the problem mandates it. One investigation
  loop over four tools does not. A single traceable loop is also far easier to instrument
- **Persistent memory (mem0, checkpointers)** — see "What does it need to remember"
- **Local inference (Ollama)** — the production version of this system would plausibly run
  inference inside the enterprise boundary for data-residency reasons. Noted as a real
  consideration; not built
- **Change events and blast radius tools** — deferred, see above
