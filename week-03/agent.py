"""
agent.py -- the LangGraph investigation agent and its state.

NEVER imports streamlit.

THE STATE SCHEMA, AND WHY THE REDUCERS ARE THE LOAD-BEARING PART
----------------------------------------------------------------

FRAMEWORK requires the state to carry slices examined WITH their individual
verdicts, candidate slices not yet examined, suspects raised, suspects discarded
with reasons, and evidence records. The fields are the easy half. The reducers
are what make the required behaviour possible:

  evidence          append-only  -- it is history, and history that can be
                                    rewritten is not evidence
  slices_examined   append-only  -- same reason, and it is what makes
                                    duplicate-call prevention possible
  candidate_slices  REPLACED     -- a shrinking worklist. If this only grew, the
                                    terminal condition "every reasonable
                                    candidate has been examined" could never
                                    fire and the agent could never halt honestly
  suspects          REPLACED     -- a suspect MUTATES from raised to discarded.
                                    Append-only would leave two versions of the
                                    same suspect in the ledger and the brief
                                    would contradict itself

`slices_examined` and `candidate_slices` are separate collections on purpose.
That separation is the only way to honour the rule that a slice returning
INSUFFICIENT disqualifies THAT SLICE and not the investigation: the agent can
only continue correctly if "what I checked" and "what remains" are distinct, and
the second is visibly non-empty.

Verdicts are stored per slice and never aggregated. Aggregating would destroy the
difference between disqualified-as-evidence and genuinely-quiet, which is the
Week 1 NOT EVALUABLE lesson one layer up.

Evidence IDs exist so claims can be checked mechanically. "Zero claims not
traceable to a tool return" needs a join key, not good intentions.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Optional, Sequence, TypedDict

import tools
import tracing

# ---------------------------------------------------------------------------
# Model and limits
# ---------------------------------------------------------------------------

AGENT_MODEL = os.environ.get("TRIAGELENS_AGENT_MODEL", "openai/gpt-oss-120b")
NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1/"
TEMPERATURE = 0.1

# FRAMEWORK open decision, resolved here with the reasoning.
#
# The typical path is 6 steps. A thorough run -- summary, dependencies, three or
# four slices, two runbook searches -- lands around 8. Twelve allows one wrong
# turn without permitting a spin, and at roughly 5 seconds a call it bounds
# wall-clock near a minute.
#
# The turn cap is the real guard against a loop that alternates between two
# tools without progressing. Hitting either is a REPORTED OUTCOME, never a crash.
#
# Readable from the environment so the caps can be EXERCISED rather than merely
# declared. A cap that has never fired is wired, not tested, and the difference
# matters for the two that are supposed to turn a runaway loop into a reported
# outcome.
# MAX_TURNS was 8 and it was miscalibrated. Demo path 2 showed why: a
# consumer-scoped run has SEVEN candidate slices, so a thorough investigation
# needs 1 summary + 7 comparisons + 1 brief = 9 turns minimum. At 8 the agent
# examined every slice correctly and then had no turn left to write the refusal,
# so it reported STEP_CAP with no brief at all -- the cap consumed the
# deliverable. Sized from the data instead of from the typical path.
MAX_TOOL_CALLS = int(os.environ.get("TRIAGELENS_MAX_TOOL_CALLS", "14"))
MAX_TURNS = int(os.environ.get("TRIAGELENS_MAX_TURNS", "12"))

# After this many identical failing calls, the tool is treated as unavailable.
# FRAMEWORK: zero retries on malformed input -- but a model that repeats the same
# invalid call is a loop, and the loop has to terminate somewhere.
MAX_IDENTICAL_FAILURES = int(os.environ.get("TRIAGELENS_MAX_IDENTICAL_FAILURES", "2"))


# ---------------------------------------------------------------------------
# Ledger types
# ---------------------------------------------------------------------------


class SliceSpec(TypedDict, total=False):
    endpoint: Optional[str]
    backend_service: Optional[str]
    consumer: Optional[str]


def spec_key(spec: dict) -> str:
    """Stable identity for a slice, so the same slice is never examined twice.

    Reads only the three dimensional fields. A candidate may also carry
    `priority` and `reason`, which describe why it is worth examining and must
    NOT affect identity -- otherwise the same slice promoted to priority would
    look like a new slice and get examined twice.
    """
    return (f"{spec.get('endpoint') or '*'}|{spec.get('backend_service') or '*'}"
            f"|{spec.get('consumer') or '*'}")


def _seed_sibling_candidates(endpoint: str, backend: str, consumer: Optional[str],
                             candidates: list, examined_keys: set) -> list:
    """Put the siblings of an elevated slice at the FRONT of the worklist.

    WHY THIS IS HERE. The first run named `payment-service` -- a BACKEND -- from a
    single elevated endpoint, and never examined `/refunds`, the other endpoint on
    that same backend. RB-PAY-000, which the agent had itself retrieved, states
    that sibling corroboration is the check that discriminates "this one
    endpoint's path is broken" from "the shared backend is broken". Naming a
    backend without it is a conclusion reached one step early.

    The fix is deterministic and needs no prompt change: the topology already
    tells us which endpoints share a backend, so when a slice clears the evidence
    gate its siblings are promoted to the front of the candidate list with a
    reason attached. The agent still chooses what to call; the worklist simply
    stops burying the decisive slice behind five irrelevant ones.

    Front rather than appended, because ordering is the whole point -- the first
    run's second call went to `/cart`, an unrelated endpoint on another backend,
    while the informative sibling sat at position four.
    """
    import tools as _tools

    try:
        declared = _tools.load_topology()
        siblings = [e for e in declared.endpoints_for(backend) if e != endpoint]
    except Exception:
        return candidates

    promoted = []
    for sibling in siblings:
        spec = {"endpoint": sibling, "backend_service": backend, "consumer": consumer,
                "priority": True,
                "reason": (f"sibling of {endpoint} on {backend}; corroboration "
                           f"discriminates an endpoint-path fault from a "
                           f"shared-backend fault")}
        if spec_key(spec) in examined_keys:
            continue
        if any(spec_key(c) == spec_key(spec) for c in promoted):
            continue
        promoted.append(spec)

    remaining = [c for c in candidates
                 if not any(spec_key(c) == spec_key(p) for p in promoted)]
    return promoted + remaining


class SliceExamination(TypedDict, total=False):
    spec: SliceSpec
    key: str
    verdict: str
    failed_rules: list
    requests: int
    failed_requests: int
    rate_pct: float
    baseline_rate_pct: Optional[float]
    baseline_multiplier: Optional[float]
    breach_run: int
    evidence_id: str
    disqualified: bool
    explanation: str


class Evidence(TypedDict, total=False):
    evidence_id: str
    tool: str
    arguments: dict
    summary: str
    raw: dict
    seconds: float


class Suspect(TypedDict, total=False):
    suspect_id: str
    service: str
    endpoint: Optional[str]
    scope: str                 # "service" or "endpoint_path"
    raised_from: list
    supporting: list
    contradicting: list
    corroboration: str         # CONFIRMED / CONTRADICTED / UNAVAILABLE / PENDING
    discarded: bool
    discard_reason: str


def _update_suspects(suspects: list, examinations: list, evidence_id: str) -> list:
    """Maintain the suspect ledger from slice verdicts. Written by CODE, not the model.

    FRAMEWORK requires state to carry suspects raised, and suspects discarded with
    reasons. The first build declared the field and populated nothing, which is a
    claim the code does not honour -- so it is wired here, deterministically, from
    the only thing that licenses a suspect: an EVIDENCE SUFFICIENT verdict.

    The rules, all mechanical:

      RAISE          a slice clears the gate -> suspect on its backend_service,
                     scope "service", corroboration PENDING
      CONFIRM        a sibling on the same backend also clears the gate -> the
                     shared backend is corroborated
      CONTRADICT     a sibling was EVALUATED and fell short (EVIDENCE
                     INSUFFICIENT) -> evidence points at the endpoint path
                     rather than the backend, so the suspect NARROWS from
                     service scope to endpoint_path scope
      UNAVAILABLE    a sibling came back NOT EVALUABLE -> corroboration was
                     attempted and could not be established. This is NOT
                     contradiction: an unmeasurable sibling carries no
                     information either way, and treating it as exoneration is
                     the exact NOT-EVALUABLE conflation Week 1 exists to prevent
      DISCARD        a suspect whose every supporting slice has been disqualified
                     retains no evidence and is discarded with that reason

    The CONTRADICT rule is the one that does real work: it is how a service-level
    suspect gets narrowed to an endpoint-level one instead of standing on
    single-endpoint evidence.
    """
    suspects = [dict(s) for s in (suspects or [])]

    for exam in examinations:
        endpoint = exam["spec"].get("endpoint")
        backend = exam["spec"].get("backend_service")
        if not backend:
            continue

        existing = next((s for s in suspects if s["service"] == backend), None)

        if not exam["disqualified"]:
            if existing is None:
                suspects.append({
                    "suspect_id": f"SUS-{len(suspects) + 1:02d}",
                    "service": backend,
                    "endpoint": endpoint,
                    "scope": "service",
                    "raised_from": [exam["evidence_id"]],
                    "supporting": [exam["evidence_id"]],
                    "contradicting": [],
                    "corroboration": "PENDING",
                    "discarded": False,
                    "discard_reason": "",
                })
            else:
                if exam["evidence_id"] not in existing["supporting"]:
                    existing["supporting"].append(exam["evidence_id"])
                if endpoint != existing.get("endpoint"):
                    existing["corroboration"] = "CONFIRMED"
                    existing["scope"] = "service"
            continue

        # Disqualified slice. Only informative about an EXISTING suspect, and
        # only when it is a sibling -- a different endpoint on the same backend.
        if existing is None or endpoint == existing.get("endpoint"):
            continue

        if exam["verdict"] == "EVIDENCE INSUFFICIENT":
            if exam["evidence_id"] not in existing["contradicting"]:
                existing["contradicting"].append(exam["evidence_id"])
            existing["corroboration"] = "CONTRADICTED"
            existing["scope"] = "endpoint_path"
        elif exam["verdict"] == "NOT EVALUABLE":
            if existing["corroboration"] == "PENDING":
                existing["corroboration"] = "UNAVAILABLE"

    for suspect in suspects:
        if not suspect["supporting"] and not suspect["discarded"]:
            suspect["discarded"] = True
            suspect["discard_reason"] = (
                "every slice that supported this suspect was disqualified as evidence"
            )

    return suspects


def _append(left: list, right: list) -> list:
    """Append-only reducer."""
    return (left or []) + (right or [])


class InvestigationState(TypedDict, total=False):
    # --- inputs, never mutated ---
    case_id: str
    window_start: str
    window_end: str
    # Optional investigation-wide consumer scope. When an incident report names a
    # consumer ("mobile-app users are seeing errors"), every candidate slice is
    # seeded with that filter -- which is how the evidence-gate handoff path is
    # reachable, since a consumer-filtered slice is the case DET-02a makes
    # unevaluable.
    consumer_scope: Optional[str]

    # --- conversation ---
    messages: Annotated[list, _append]

    # --- the ledger ---
    evidence: Annotated[list, _append]            # append-only history
    slices_examined: Annotated[list, _append]     # append-only history
    candidate_slices: list                        # REPLACED: a shrinking worklist
    suspects: list                                # REPLACED: suspects mutate

    # --- control ---
    tool_calls: int
    turns: int
    terminal: Optional[str]
    # Set by code when the framework's terminal condition is met: every candidate
    # slice examined and none yielded sufficient evidence. Forces the next turn to
    # produce the brief instead of calling more tools.
    must_conclude: bool
    tool_failures: Annotated[list, _append]
    drift: Optional[dict]
    unavailable_tools: list


TERMINAL_NAME = "NAME"
TERMINAL_REFUSE = "REFUSE"
TERMINAL_HANDOFF = "HANDOFF"
TERMINAL_STEP_CAP = "STEP_CAP"


# ---------------------------------------------------------------------------
# Tool schemas handed to the model
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_incident_summary",
        "description": (
            "What changed in a time window: per-slice request counts, failure counts, "
            "5xx rates, p95 latency over successful requests, and which thresholds each "
            "slice breached. Returns NO ranking and NO suspect -- slices are sorted "
            "alphabetically and the order means nothing. Start here."
        ),
        "parameters": {"type": "object", "properties": {
            "window_start": {"type": "string", "description": "HH:MM, e.g. '14:00'"},
            "window_end": {"type": "string", "description": "HH:MM, e.g. '15:00'"},
        }, "required": ["window_start", "window_end"]}}},
    {"type": "function", "function": {
        "name": "compare_to_baseline",
        "description": (
            "Compare ONE slice you choose against the dataset baseline (first 120 minutes) "
            "and return the evidence-gate verdict: EVIDENCE SUFFICIENT, EVIDENCE "
            "INSUFFICIENT, or NOT EVALUABLE. The evaluation unit is endpoint x "
            "backend_service; consumer is a filter applied before grouping, not a slice "
            "key. Only a SUFFICIENT verdict may support a suspect."
        ),
        "parameters": {"type": "object", "properties": {
            "endpoint": {"type": "string", "description": "required, e.g. '/checkout'"},
            "window_start": {"type": "string"},
            "window_end": {"type": "string"},
            "backend_service": {"type": "string", "description": "optional"},
            "consumer": {"type": "string", "description": "optional consumer filter"},
        }, "required": ["endpoint", "window_start", "window_end"]}}},
    {"type": "function", "function": {
        "name": "get_service_dependencies",
        "description": (
            "Declared topology: which backend serves an endpoint, who owns it, its "
            "runbook IDs, and its sibling endpoints on the same backend. Also reports "
            "drift between declared topology and observed traffic."
        ),
        "parameters": {"type": "object", "properties": {
            "endpoint": {"type": "string"},
            "backend_service": {"type": "string"},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "search_runbooks",
        "description": (
            "Search the 19-document runbook, policy and postmortem corpus for "
            "discriminating checks and procedure. Returns cited passages. Restricted "
            "documents are withheld and named. An empty result is a finding: the corpus "
            "deliberately covers nothing on host metrics, databases, connection pools, "
            "queue depth, CDN or cost."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "service": {"type": "string", "description": "optional service scope"},
        }, "required": ["query"]}}},
]


# ---------------------------------------------------------------------------
# The system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the TriageLens investigator. An on-call engineer has an API gateway incident \
and needs the best-supported suspect, the evidence for and against it, and the next \
diagnostic step — fast.

You investigate by calling read-only tools. You decide which tool to call next based on \
what the previous call returned. There is no fixed pipeline.

A typical path: get_incident_summary to see what changed → get_service_dependencies to \
learn which backend serves what and which endpoints are siblings → compare_to_baseline on \
each slice worth interrogating → search_runbooks for the discriminating checks → then the \
brief. Skip, reorder or repeat as the evidence warrants.

RULES YOU MAY NOT BREAK

1. NEVER assert causation. "Suspect", "correlates with", "consistent with", "worth \
investigating". Never "caused", "because of", "due to", "root cause", "responsible for" \
— at any confidence level.
2. NEVER state a number, rate, count or timestamp that did not come from a tool return.
3. Only a verdict of EVIDENCE SUFFICIENT may support naming a suspect. EVIDENCE \
INSUFFICIENT and NOT EVALUABLE disqualify THAT SLICE as evidence — they do NOT end the \
investigation and they do NOT mean the slice is healthy. When a slice is disqualified, \
examine another reasonable candidate slice instead.
4. NEVER reveal or infer the contents of a restricted document. You may state that \
relevant guidance exists above the caller's access level.
5. You have no write tools. Never claim to have paged, escalated or notified anyone.
6. A tool returning nothing is a finding, not an error. Report it as a finding.
7. Do not call the same tool with the same arguments twice. You already have that result.
8. When you name a suspect, the ledger tells you its corroboration status: CONFIRMED, CONTRADICTED, UNAVAILABLE or PENDING. You must report it in `scope_confirmation`. If it is not CONFIRMED, name the sibling slice involved, say what its verdict was, name the exact failing rule from that slice's `failed_rules` list (for example `baseline_minimum_failures`), and state that the suspect's scope is therefore unconfirmed. This does NOT change the outcome to a refusal: evidence sufficient on one slice supports naming the suspect, it just does not establish whether the fault is the endpoint path or the whole backend.

WHEN TO STOP

Stop and write the brief when one of these is true:
  - A slice returned EVIDENCE SUFFICIENT and you have the discriminating checks for it \
→ name the suspect.
  - Every reasonable candidate slice has been examined and none returned EVIDENCE \
SUFFICIENT → refuse to name a suspect, and say which slices you examined and what each \
returned.
  - Evidence conflicts, or topology drift affects a relationship your suspect depends on \
→ hand off, showing both sides.

THE BRIEF

When you are finished investigating, stop calling tools and reply with ONLY a JSON object:

{
  "outcome": "NAME" | "REFUSE" | "HANDOFF",
  "suspect": "service name, or null",
  "headline": "one sentence an engineer reads first",
  "supporting_evidence": [
    {"claim": "what is true", "evidence_id": "EV-002",
     "figures": "the numbers from that tool return"}
  ],
  "contradicting_evidence": [
    {"claim": "what argues against it", "evidence_id": "EV-004", "figures": "..."}
  ],
  "slices_disqualified": [
    {"slice": "endpoint x backend (consumer)", "verdict": "NOT EVALUABLE",
     "why": "the named failing rule and its numbers", "evidence_id": "EV-003"}
  ],
  "next_diagnostic_step": "what to check next",
  "next_step_source": "document_id the step came from, or null if unsourced",
  "scope_confirmation": "required when a suspect is named. State the corroboration status and, if it is not CONFIRMED, which sibling slice could not confirm it, its verdict, the rule it failed, and that the scope is unconfirmed. Empty string only when no suspect is named.",
  "unavailable_evidence": "which tool returned nothing or failed, and what that costs",
  "caveats": "drift, conflicts, access-level exclusions"
}

Every evidence_id must be one that appeared in a tool result you received. Figures must \
be copied from tool returns, not recalculated."""


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def _client():
    """OpenAI-compatible client for Nebius.

    Plain OpenAI SDK rather than langchain-openai's ChatOpenAI. The tool loop here
    needs the raw tool_call ids to write ledger entries keyed to them, and the
    extra abstraction buys nothing for a four-tool single-agent loop. LangGraph
    still owns the state, the reducers and the graph -- which is what the track
    asks for and what the trace shows.
    """
    from openai import OpenAI

    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        dotenv = Path.home() / "llm-class" / ".env"
        if dotenv.is_file():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                if line.startswith("NEBIUS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise RuntimeError("NEBIUS_API_KEY not found in environment or ~/llm-class/.env")
    # Wrapped so the raw-SDK model calls appear in the trace as child runs.
    # Without this the graph nodes trace and the LLM calls inside them do not,
    # which is a trace that shows the shape of the run and none of its content.
    return tracing.wrap_client(OpenAI(base_url=NEBIUS_BASE_URL, api_key=key, timeout=180))


@tracing.traceable(run_type="tool", name="investigation_tool")
def _call_tool_traced(name: str, arguments: dict) -> dict:
    """Tool dispatch, wrapped so each call is a child run in the trace.

    The decorator lives here rather than on `tools.call_tool` so that tools.py
    stays free of observability concerns -- it is the module Week 4's evaluators
    will import, and a tracing decorator there would put a LangSmith dependency
    in the middle of the deterministic layer.
    """
    return tools.call_tool(name, arguments)


def _summarise(name: str, result: dict) -> str:
    """One line describing a tool return, built from the return itself.

    Deterministic. The model never writes these -- they are what the ledger
    shows, and a ledger summarised by the thing it is auditing is not a ledger.
    """
    if result.get("error"):
        return f"{name} failed: {result.get('error')} -- {str(result.get('detail'))[:120]}"
    if name == "get_incident_summary":
        return (f"{result.get('requests', 0)} requests, "
                f"{result.get('overall_error_rate_pct')}% 5xx overall, "
                f"{len(result.get('slices', []))} endpoint x backend slices present")
    if name == "compare_to_baseline":
        parts = [f"{r['slice_label']}: {r['verdict']} "
                 f"({r['error_rate_pct']}% vs {r['baseline_rate_pct']}% baseline, "
                 f"{r['baseline_multiplier']}x)" for r in result.get("results", [])]
        return "; ".join(parts) or result.get("verdict", "no result")
    if name == "get_service_dependencies":
        return (f"{len(result.get('relationships', []))} declared relationships, "
                f"drift={result.get('drift_detected')}")
    if name == "search_runbooks":
        if not result.get("available"):
            return f"search_runbooks unavailable: {result.get('error')}"
        ids = [p["document_id"] for p in result.get("passages", [])]
        withheld = result.get("withheld_restricted") or []
        return (f"{len(ids)} passages from {', '.join(ids) or 'nothing'}"
                + (f"; withheld restricted: {', '.join(withheld)}" if withheld else ""))
    return json.dumps(result)[:160]


def build_graph():
    """Compile the LangGraph. Two nodes, one conditional edge."""
    from langgraph.graph import END, StateGraph

    client = _client()

    # ---------------- node: the model decides --------------------------------
    def think(state: InvestigationState) -> dict:
        turns = state.get("turns", 0)
        must_conclude = bool(state.get("must_conclude"))

        # A cap that can swallow the brief is not a safety limit, it is a silent
        # failure. Reaching MAX_TURNS converts the NEXT turn into a concluding
        # turn -- no tools offered -- rather than returning nothing. That turn
        # cannot loop: with no tools available the reply carries no tool_calls, so
        # route() sends it straight to END.
        if turns >= MAX_TURNS:
            must_conclude = True
        if turns > MAX_TURNS:
            return {"terminal": TERMINAL_STEP_CAP}

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(state["messages"])

        # Inject the ledger so the model sees what it has and has not examined.
        # This is the duplicate-prevention and the continue-while-candidates-remain
        # mechanism made visible, rather than hoped for.
        examined = state.get("slices_examined") or []
        candidates = state.get("candidate_slices") or []
        if examined or candidates:
            ledger = ["INVESTIGATION LEDGER (maintained by code, not by you):"]
            for item in examined:
                ledger.append(
                    f"  examined {item['key']} -> {item['verdict']} "
                    f"[{item['evidence_id']}]"
                    + ("  DISQUALIFIED as evidence" if item["disqualified"] else "  EVIDENCE")
                )
            # Priority candidates are listed FIRST and with their reason. The
            # worklist is ordered by code; showing the order without the reason
            # would leave the agent to guess why one slice is listed before
            # another.
            if candidates:
                priority = [c for c in candidates if c.get("priority")]
                ordinary = [c for c in candidates if not c.get("priority")]
                if priority:
                    ledger.append("  PRIORITY candidate slices, examine these first:")
                    for spec in priority:
                        ledger.append(f"    {spec_key(spec)} -- {spec.get('reason', '')}")
                if ordinary:
                    ledger.append("  other candidate slices not yet examined: "
                                  + ", ".join(spec_key(c) for c in ordinary))
            else:
                ledger.append("  candidate slices not yet examined: NONE")

            for suspect in state.get("suspects") or []:
                ledger.append(
                    f"  suspect {suspect['suspect_id']} {suspect['service']} "
                    f"(scope {suspect['scope']}) corroboration="
                    f"{suspect['corroboration']} supporting={suspect['supporting']} "
                    f"contradicting={suspect['contradicting']}"
                    + (f" DISCARDED: {suspect['discard_reason']}"
                       if suspect["discarded"] else "")
                )
            if state.get("unavailable_tools"):
                ledger.append("  tools unavailable: "
                              + ", ".join(state["unavailable_tools"]))
            ledger.append(f"  tool calls used: {state.get('tool_calls', 0)}/{MAX_TOOL_CALLS}")
            messages.append({"role": "user", "content": "\n".join(ledger)})

        # When the terminal condition has been reached, the model is called with
        # NO tools available. Asking it nicely to stop is not the same as removing
        # the option: the first run of demo path 2 examined all seven slices,
        # exhausted the candidate list, and then spent its remaining turns calling
        # tools instead of writing the brief -- hitting the turn cap and producing
        # no brief at all. The cap was reported correctly and the OUTCOME was
        # wrong, because the budget that should have produced the refusal went on
        # tool calls that had nothing left to find.
        if must_conclude:
            exhausted = not (state.get("candidate_slices") or [])
            messages.append({"role": "user", "content": (
                ("TERMINAL CONDITION: every candidate slice has been examined and none "
                 "returned EVIDENCE SUFFICIENT. " if exhausted else
                 f"STEP CAP reached ({state.get('tool_calls', 0)} tool calls, "
                 f"{turns} turns; limits {MAX_TOOL_CALLS}/{MAX_TURNS}). ")
                + "Do not call any more tools. Write the brief now from what you have, "
                + ("with outcome REFUSE, listing every slice you examined, what each "
                   "returned, and the named rule each failed on."
                   if exhausted else
                   "stating in unavailable_evidence which candidate slices were left "
                   "unexamined when the cap was reached.")
            )})

        kwargs = {"model": AGENT_MODEL, "temperature": TEMPERATURE,
                  "max_tokens": 2500, "messages": messages}
        if not must_conclude:
            kwargs["tools"] = TOOL_SCHEMAS
            kwargs["tool_choice"] = "auto"
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        recorded = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            recorded["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ]

        update = {"messages": [recorded], "turns": turns + 1}
        if not message.tool_calls:
            # Distinguish a brief written because the investigation finished from
            # one written because a cap forced it. Both are briefs; only one means
            # the agent chose to stop.
            update["terminal"] = (
                TERMINAL_STEP_CAP
                if must_conclude and (state.get("candidate_slices") or [])
                else "BRIEF"
            )
        return update

    # ---------------- node: run the tools, write the ledger -----------------
    def act(state: InvestigationState) -> dict:
        last = state["messages"][-1]
        calls = last.get("tool_calls") or []
        consumer_scope = state.get("consumer_scope")

        new_messages, new_evidence, new_examined, new_failures = [], [], [], []
        drift_state = state.get("drift")
        candidates = list(state.get("candidate_slices") or [])
        unavailable = list(state.get("unavailable_tools") or [])
        examined_keys = {item["key"] for item in (state.get("slices_examined") or [])}
        evidence_count = len(state.get("evidence") or [])
        calls_used = state.get("tool_calls", 0)

        for call in calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}

            if calls_used >= MAX_TOOL_CALLS:
                new_messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps({
                        "error": "step_cap_reached",
                        "detail": (f"The {MAX_TOOL_CALLS}-tool-call cap is reached. Stop "
                                   "calling tools and write the brief from what you have."),
                    }),
                })
                continue

            # --- duplicate-call prevention, for compare_to_baseline ---------
            if name == "compare_to_baseline":
                spec = {"endpoint": arguments.get("endpoint"),
                        "backend_service": arguments.get("backend_service"),
                        "consumer": arguments.get("consumer")}
                key = spec_key(spec)
                if key in examined_keys:
                    prior = next(i for i in (state.get("slices_examined") or [])
                                 if i["key"] == key)
                    new_messages.append({
                        "role": "tool", "tool_call_id": call["id"],
                        "content": json.dumps({
                            "already_examined": True, "slice": key,
                            "verdict": prior["verdict"], "evidence_id": prior["evidence_id"],
                            "detail": ("This slice was already examined and the verdict has "
                                       "not changed. Examine a different candidate slice, "
                                       "or write the brief."),
                        }),
                    })
                    continue

            started = time.perf_counter()
            result = _call_tool_traced(name, arguments)
            elapsed = time.perf_counter() - started
            calls_used += 1

            evidence_count += 1
            evidence_id = f"EV-{evidence_count:03d}"
            new_evidence.append({
                "evidence_id": evidence_id, "tool": name, "arguments": arguments,
                "summary": _summarise(name, result), "raw": result,
                "seconds": round(elapsed, 2),
            })

            # --- ledger writes driven by the tool, not by the model ---------
            if result.get("error"):
                new_failures.append({"tool": name, "arguments": arguments,
                                     "error": result.get("error"),
                                     "detail": str(result.get("detail"))[:200]})
                identical = sum(
                    1 for f in (state.get("tool_failures") or []) + new_failures
                    if f["tool"] == name and f["arguments"] == arguments
                )
                if identical >= MAX_IDENTICAL_FAILURES and name not in unavailable:
                    unavailable.append(name)

            if name == "get_incident_summary" and result.get("slices"):
                # Seed the candidate worklist from what the summary actually found.
                # Code builds this list, not the model -- so "every reasonable
                # candidate examined" is checkable rather than asserted.
                for entry in result["slices"]:
                    spec = {"endpoint": entry["endpoint"],
                            "backend_service": entry["backend_service"],
                            "consumer": consumer_scope}
                    if spec_key(spec) in examined_keys:
                        continue
                    if any(spec_key(c) == spec_key(spec) for c in candidates):
                        continue
                    candidates.append(spec)

            if name == "compare_to_baseline":
                for entry in result.get("results", []):
                    spec = {"endpoint": entry["endpoint"],
                            "backend_service": entry["backend_service"],
                            "consumer": entry.get("consumer_filter")}
                    key = spec_key(spec)
                    examined_keys.add(key)
                    new_examined.append({
                        "spec": spec, "key": key, "verdict": entry["verdict"],
                        "failed_rules": entry["failed_rules"],
                        "requests": entry["requests"],
                        "failed_requests": entry["failed_requests"],
                        "rate_pct": entry["error_rate_pct"],
                        "baseline_rate_pct": entry["baseline_rate_pct"],
                        "baseline_multiplier": entry["baseline_multiplier"],
                        "breach_run": entry["consecutive_breach_buckets"],
                        "evidence_id": evidence_id,
                        "disqualified": entry["disqualified_as_evidence"],
                        "explanation": entry["explanation"],
                    })
                    candidates = [c for c in candidates if spec_key(c) != key]

                    # A slice that clears the gate promotes its siblings to the
                    # front of the worklist. This is the fix for naming a backend
                    # without running the corroboration check that licenses it.
                    if not entry["disqualified_as_evidence"] and entry["backend_service"]:
                        candidates = _seed_sibling_candidates(
                            entry["endpoint"], entry["backend_service"],
                            entry.get("consumer_filter"), candidates, examined_keys,
                        )

            if name == "get_service_dependencies" and result.get("drift_detected"):
                # This was computed into a local and never merged into the state
                # update in the first build, so drift never reached state at all.
                # It happens to be False on this dataset, which is exactly why it
                # went unnoticed -- a bug that only shows on data nobody has yet.
                drift_state = {"messages": result.get("drift", []),
                               "evidence_id": evidence_id}

            new_messages.append({
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps({"evidence_id": evidence_id, **result})[:12000],
            })

        update = {
            "messages": new_messages, "evidence": new_evidence,
            "slices_examined": new_examined, "candidate_slices": candidates,
            "suspects": _update_suspects(state.get("suspects"), new_examined,
                                         f"EV-{evidence_count:03d}"),
            "tool_calls": calls_used, "tool_failures": new_failures,
            "unavailable_tools": unavailable, "drift": drift_state,
        }
        # The framework's investigation-level terminal condition, enforced in code
        # rather than left to the model's judgement: every reasonable candidate
        # examined and none yielded sufficient evidence.
        all_examined = (state.get("slices_examined") or []) + new_examined
        if all_examined and not candidates and not any(
                not item["disqualified"] for item in all_examined):
            update["must_conclude"] = True

        # The tool-call cap grants the concluding turn too. Setting terminal here
        # would route straight to END and produce no brief -- which is what the
        # first version did, so the turn cap yielded a brief and the call cap
        # yielded nothing. Two caps that report the same condition differently is
        # a bug, and the one that swallows the deliverable is the wrong one.
        if calls_used >= MAX_TOOL_CALLS:
            update["must_conclude"] = True
        return update

    # ---------------- routing ------------------------------------------------
    def route(state: InvestigationState) -> str:
        if state.get("terminal") in (TERMINAL_STEP_CAP,):
            return "finish"
        if state.get("terminal") == "BRIEF":
            return "finish"
        last = state["messages"][-1] if state["messages"] else {}
        return "act" if last.get("tool_calls") else "finish"

    graph = StateGraph(InvestigationState)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.set_entry_point("think")
    graph.add_conditional_edges("think", route, {"act": "act", "finish": END})
    graph.add_edge("act", "think")
    return graph.compile()


# ---------------------------------------------------------------------------
# Running one investigation
# ---------------------------------------------------------------------------


@dataclass
class Investigation:
    """The result of one run: the brief, the ledger, and what it cost."""

    case_id: str
    outcome: str
    brief: dict
    state: dict
    seconds: float
    invalid_evidence_ids: tuple = ()
    causal_violations: tuple = ()
    hit_cap: bool = False
    scope_gap: str = ""

    @property
    def evidence(self) -> list:
        return self.state.get("evidence") or []

    @property
    def slices_examined(self) -> list:
        return self.state.get("slices_examined") or []


# FRAMEWORK: "no causal assertions at any confidence", checked against a
# forbidden-phrase set. Deterministic, cheap, and it catches the failure the
# whole project is organised around.
FORBIDDEN_CAUSAL = (
    "caused by", "caused the", "root cause", "is responsible for",
    "because of the", "due to the", "resulted from", "the cause is",
    "this is why", "led to the",
)


def _extract_brief(messages: Sequence) -> dict:
    """Pull the JSON brief out of the final assistant message."""
    import re

    for message in reversed(list(messages)):
        if message.get("role") != "assistant" or message.get("tool_calls"):
            continue
        content = message.get("content") or ""
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    return {}


def scope_gap(brief: dict, suspects: Sequence, examined: Sequence) -> str:
    """Whether a named suspect's scope is unconfirmed and the brief failed to say so.

    The state already knew this -- `corroboration` has been maintained from slice
    verdicts since the suspect ledger was wired -- and the narration ignored it,
    claiming single-endpoint evidence sufficed to name a backend. Knowing a thing
    in state and not saying it in the brief is the same class of defect as a
    number with no denominator: the system is right and its output is not.

    Returns a description of the gap, or "" when there is none. Reported rather
    than repaired: the brief is the model's sentence, and silently appending the
    caveat would hide that the model omitted it.
    """
    if (brief.get("outcome") or "") != TERMINAL_NAME:
        return ""
    unconfirmed = [s for s in (suspects or [])
                   if not s.get("discarded") and s.get("corroboration") != "CONFIRMED"]
    if not unconfirmed:
        return ""

    stated = " ".join(str(brief.get(k, "")) for k in
                      ("scope_confirmation", "caveats", "headline")).lower()
    missing = []
    for suspect in unconfirmed:
        status = str(suspect.get("corroboration", "")).lower()
        sibling_rows = [e for e in (examined or [])
                        if e["spec"].get("backend_service") == suspect.get("service")
                        and e["spec"].get("endpoint") != suspect.get("endpoint")]
        siblings = [e["spec"].get("endpoint") for e in sibling_rows]

        named = any(s and s.lower() in stated for s in siblings)
        said_status = status in stated or "unconfirmed" in stated

        # "Could not be evaluated" is the verdict. The REASON is the rule that
        # failed, and the first run gave the verdict without it -- which is the
        # explained-restraint principle half-applied. A reader who is told a slice
        # is unevaluable and not told why cannot judge whether the gap is the data
        # or the thresholds.
        rules = [r for e in sibling_rows for r in (e.get("failed_rules") or [])]
        said_rule = (not rules) or any(r.lower() in stated for r in rules)

        if not (named and said_status and said_rule):
            faults = []
            if siblings and not named:
                faults.append(f"sibling(s) {', '.join(s for s in siblings if s)} not named")
            if not siblings:
                faults.append("no sibling was examined")
            if not said_status:
                faults.append("the corroboration status was not stated")
            if not said_rule:
                faults.append(f"the failing rule was not named (expected one of "
                              f"{', '.join(sorted(set(rules))[:3])})")
            missing.append(
                f"{suspect['service']} is named at {suspect.get('scope')} scope with "
                f"corroboration={suspect.get('corroboration')}: " + "; ".join(faults)
            )
    return " | ".join(missing)


def validate(brief: dict, evidence: Sequence) -> tuple:
    """Check the brief against the ledger. Deterministic, reusing Week 2's idea.

    Two checks, both mechanical:
      * every evidence_id cited must be one the agent actually received
      * no forbidden causal phrase appears anywhere in the brief's prose
    """
    valid_ids = {item["evidence_id"] for item in evidence}
    cited = []
    for field_name in ("supporting_evidence", "contradicting_evidence", "slices_disqualified"):
        for row in brief.get(field_name) or []:
            if isinstance(row, dict) and row.get("evidence_id"):
                cited.append(row["evidence_id"])
    invalid = tuple(sorted({c for c in cited if c not in valid_ids}))

    prose = " ".join(
        str(value) for key, value in brief.items()
        if isinstance(value, str)
    ).lower()
    for row in brief.get("supporting_evidence") or []:
        if isinstance(row, dict):
            prose += " " + str(row.get("claim", "")).lower()
    violations = tuple(sorted({p for p in FORBIDDEN_CAUSAL if p in prose}))
    return invalid, violations


def investigate(window_start: str, window_end: str, case_id: str = "CASE-001",
                consumer_scope: Optional[str] = None, graph=None) -> Investigation:
    """Run one investigation end to end.

    `consumer_scope` mirrors a real incident report that names a consumer. It is
    stated in the opening message AND seeded into every candidate slice, so the
    agent interrogates that consumer's traffic rather than the aggregate.
    """
    # Configure from here as well as from app.py. The CLI, the demo scripts and
    # Week 4's evaluation harness all call investigate() directly, and a trace
    # that only appears when the Streamlit app is the entry point is not
    # instrumentation, it is a coincidence. configure() is idempotent.
    tracing.configure()
    graph = graph or build_graph()
    opening = (
        f"Incident window {window_start}-{window_end} on the API gateway. "
        + (f"The report comes from {consumer_scope} traffic specifically, so scope "
           f"your slice comparisons to consumer={consumer_scope}. " if consumer_scope else "")
        + f"Investigate and produce the brief. Case id {case_id}."
    )
    initial: InvestigationState = {
        "case_id": case_id, "window_start": window_start, "window_end": window_end,
        "consumer_scope": consumer_scope,
        "messages": [{"role": "user", "content": opening}],
        "evidence": [], "slices_examined": [], "candidate_slices": [],
        "suspects": [], "tool_calls": 0, "turns": 0, "terminal": None,
        "must_conclude": False,
        "tool_failures": [], "drift": None, "unavailable_tools": [],
    }

    started = time.perf_counter()
    final = graph.invoke(initial, {"recursion_limit": (MAX_TURNS * 2) + 4})
    elapsed = time.perf_counter() - started

    brief = _extract_brief(final.get("messages") or [])
    invalid, violations = validate(brief, final.get("evidence") or [])
    gap = scope_gap(brief, final.get("suspects") or [], final.get("slices_examined") or [])

    outcome = brief.get("outcome") or ""
    hit_cap = (final.get("turns", 0) >= MAX_TURNS
               or final.get("tool_calls", 0) >= MAX_TOOL_CALLS
               or final.get("terminal") == TERMINAL_STEP_CAP)
    if final.get("terminal") == TERMINAL_STEP_CAP and not outcome:
        outcome = TERMINAL_STEP_CAP
    if outcome not in (TERMINAL_NAME, TERMINAL_REFUSE, TERMINAL_HANDOFF, TERMINAL_STEP_CAP):
        outcome = TERMINAL_STEP_CAP if final.get("terminal") == TERMINAL_STEP_CAP else TERMINAL_HANDOFF

    return Investigation(
        case_id=case_id, outcome=outcome, brief=brief, state=final,
        seconds=round(elapsed, 1),
        invalid_evidence_ids=invalid, causal_violations=violations,
        hit_cap=hit_cap, scope_gap=gap,
    )
