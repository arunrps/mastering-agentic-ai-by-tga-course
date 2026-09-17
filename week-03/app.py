"""
app.py -- TriageLens Investigator (Week 3).

This file renders. It computes nothing. Every number, verdict and citation comes
from tools.py or agent.py, neither of which imports Streamlit -- the same
boundary Weeks 1 and 2 established.

LAYOUT CONTRACT, from FRAMEWORK: deterministic incident state on top, agent
transcript below it, never above. The deterministic state is what the tools
measured; the transcript is the agent reasoning over it. Putting the reasoning
first would invert what this project argues.

Run with:  streamlit run app.py
"""

import json
import os

import streamlit as st

# ---------------------------------------------------------------------------
# Credentials and tracing config -- BEFORE importing anything that builds a
# client or reads tracing environment variables.
#
# Streamlit Cloud cannot read ~/llm-class/.env, and neither tools.py, agent.py
# nor tracing.py may import streamlit to go looking. So the bridge is here and it
# goes one way: lift values out of st.secrets into os.environ, which is the one
# channel both deployment targets share.
# ---------------------------------------------------------------------------

SECRET_NAMES = (
    "NEBIUS_API_KEY",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_PROJECT",
)


def _bridge_secrets() -> dict:
    """Copy known secrets from st.secrets into os.environ. Returns their sources."""
    sources = {}
    for name in SECRET_NAMES:
        if os.environ.get(name):
            sources[name] = "environment"
            continue
        try:
            value = st.secrets.get(name)
        except Exception:
            # No secrets.toml locally -- st.secrets raises rather than returning
            # empty. That is the normal local path, not an error.
            value = None
        if value:
            os.environ[name] = str(value)
            sources[name] = "st.secrets"
    return sources


SECRET_SOURCES = _bridge_secrets()

import agent        # noqa: E402  -- must follow the secret bridge
import tools        # noqa: E402
import tracing      # noqa: E402

TRACING_CONFIG = tracing.configure()
TRACING_VERIFY = tracing.verify()

COLOR_ELEVATED = "#DC2626"   # reserved for genuinely elevated states

st.set_page_config(page_title="TriageLens Investigator", layout="wide")


@st.cache_resource
def compiled_graph():
    return agent.build_graph()


@st.cache_data
def incident_summary(window_start: str, window_end: str):
    return tools.get_incident_summary(window_start, window_end)


@st.cache_data
def dependencies():
    return tools.get_service_dependencies()


st.title("TriageLens Investigator")
st.caption(
    "A single stateful agent investigating an API gateway incident through four "
    "read-only tools. It suspects; it never concludes cause."
)

# ---------------------------------------------------------------------------
# Sidebar -- the incident window and run controls
# ---------------------------------------------------------------------------

window = tools.dataset_window()
st.sidebar.header("Incident window")
st.sidebar.caption(
    f"Dataset covers {window['data_start'][11:16]}–{window['data_end'][11:16]}. "
    f"Baseline is the first {window['baseline_minutes']} minutes "
    f"({window['baseline_start'][11:16]}–{window['baseline_end'][11:16]}), a property "
    "of the dataset and never derived from the selected window."
)
window_start = st.sidebar.text_input("Window start (HH:MM)", "14:00")
window_end = st.sidebar.text_input("Window end (HH:MM)", "15:00")
case_id = st.sidebar.text_input("Case id", "CASE-001")

st.sidebar.divider()
st.sidebar.caption(
    f"**Step caps** — {agent.MAX_TOOL_CALLS} tool calls, {agent.MAX_TURNS} model turns. "
    "Hitting either is a reported outcome, not a crash."
)
st.sidebar.caption(f"**Model** — `{agent.AGENT_MODEL}`")
st.sidebar.caption(tracing.status_line(TRACING_CONFIG, TRACING_VERIFY))
if SECRET_SOURCES:
    st.sidebar.caption("Secrets resolved: " + ", ".join(
        f"`{k}` ← {v}" for k, v in SECRET_SOURCES.items()))

run = st.sidebar.button("Investigate", type="primary", width="stretch")

# ---------------------------------------------------------------------------
# DETERMINISTIC INCIDENT STATE -- on top, always
# ---------------------------------------------------------------------------

st.subheader("Incident state")
st.caption(
    "Measured by deterministic code before the agent runs. Slices are sorted "
    "alphabetically — this panel reports what changed, not what is to blame."
)

try:
    summary = incident_summary(window_start, window_end)
except tools.ToolInputError as error:
    st.error(str(error))
    st.stop()

if summary["requests"] == 0:
    st.warning(summary["note"])
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Requests", f"{summary['requests']:,}")
col2.metric("Failed", f"{summary['failed_requests']:,}")
col3.metric("5xx rate", f"{summary['overall_error_rate_pct']}%")
col4.metric("p95 (2xx only)", f"{summary['p95_ms_successful_only']:,.0f} ms"
            if summary["p95_ms_successful_only"] else "n/a")

import pandas as pd  # noqa: E402  -- display only

st.dataframe(
    pd.DataFrame([{
        "endpoint": s["endpoint"],
        "backend": s["backend_service"],
        "requests": s["requests"],
        "failed": s["failed_requests"],
        "5xx %": s["error_rate_pct"],
        "p95 ms": s["p95_ms_successful_only"],
        "thresholds": "; ".join(s["thresholds"]),
    } for s in summary["slices"]]),
    hide_index=True, width="stretch",
)

deps = dependencies()
if deps["drift_detected"]:
    st.warning("**Topology drift** — " + " · ".join(deps["drift"]) + "\n\n"
               + deps["drift_guidance"])
else:
    st.success(deps["drift_guidance"])

st.caption(f"Rule set `{summary['rule_set']}` · topology `{deps['topology_version']}`")

st.divider()

# ---------------------------------------------------------------------------
# AGENT TRANSCRIPT -- below the deterministic state, never above
# ---------------------------------------------------------------------------

st.subheader("Investigation")

if "investigation" not in st.session_state:
    st.session_state.investigation = None

if run:
    with st.spinner("Investigating — the agent chooses its own tool sequence…"):
        try:
            st.session_state.investigation = agent.investigate(
                window_start, window_end, case_id=case_id, graph=compiled_graph()
            )
        except Exception as error:       # noqa: BLE001 -- surface it
            st.error(f"Investigation failed: {type(error).__name__}: {error}")
            st.session_state.investigation = None

investigation = st.session_state.investigation

if investigation is None:
    st.info(
        "Press **Investigate**. The agent decides which tool to call next from what "
        "the previous call returned, so two incidents produce visibly different "
        "trajectories."
    )
    st.stop()

brief = investigation.brief
badge = {
    agent.TERMINAL_NAME: ("⚠️", "Suspect named"),
    agent.TERMINAL_REFUSE: ("∅", "Refused — insufficient evidence"),
    agent.TERMINAL_HANDOFF: ("⇄", "Handoff — conflicting evidence"),
    agent.TERMINAL_STEP_CAP: ("⏱", "Step cap reached"),
}.get(investigation.outcome, ("?", investigation.outcome))

left, right = st.columns([3, 1])
left.markdown(f"### {badge[0]} {badge[1]}")
if brief.get("suspect"):
    left.markdown(f"**Suspect:** `{brief['suspect']}` — *suspected, not concluded*")
if brief.get("headline"):
    left.write(brief["headline"])

right.metric("Wall clock", f"{investigation.seconds}s")
right.metric("Tool calls", investigation.state.get("tool_calls", 0))

# --- the two deterministic validators, shown whether they pass or fail ------
if investigation.invalid_evidence_ids:
    st.error("**Citation validator** — the brief cited evidence it never received: "
             + ", ".join(investigation.invalid_evidence_ids))
else:
    st.success("**Citation validator** — every cited evidence id traces to a tool return.")

if investigation.causal_violations:
    st.error("**Causal restraint** — forbidden phrasing found: "
             + ", ".join(f"`{p}`" for p in investigation.causal_violations))
else:
    st.success("**Causal restraint** — no causal assertion found in the brief.")

# Scope corroboration. The status comes from the ledger, which code maintains from
# slice verdicts, so it is shown whether or not the narration mentioned it -- the
# deterministic fact does not depend on the model having said it. The validator
# separately reports when the brief failed to say it.
for suspect in investigation.state.get("suspects") or []:
    if suspect.get("discarded"):
        continue
    status = suspect.get("corroboration")
    line = (f"**Scope corroboration** — `{suspect['service']}` named at "
            f"*{suspect.get('scope')}* scope · corroboration **{status}**")
    if status == "CONFIRMED":
        st.success(line + " — a sibling endpoint on the same backend also cleared the gate.")
    elif status == "CONTRADICTED":
        st.warning(line + " — a sibling was evaluated and fell short, so the evidence "
                          "points at this endpoint's path rather than the whole backend.")
    elif status == "UNAVAILABLE":
        st.warning(line + " — sibling corroboration was attempted and could not be "
                          "established, so the scope is unconfirmed. An unevaluable "
                          "sibling is not exoneration and not confirmation.")
    else:
        st.info(line + " — no sibling has been examined yet.")

if investigation.scope_gap:
    st.error(
        "**Scope reporting** — the brief did not state the corroboration status the "
        f"ledger recorded: {investigation.scope_gap}."
    )
elif (investigation.state.get("suspects") or []):
    st.success("**Scope reporting** — the brief states the corroboration status.")

# --- evidence for and against ----------------------------------------------
ev_left, ev_right = st.columns(2)
with ev_left:
    st.markdown("**Supporting evidence**")
    for row in brief.get("supporting_evidence") or []:
        st.markdown(f"- {row.get('claim')}  \n  `{row.get('evidence_id')}` · "
                    f"{row.get('figures', '')}")
    if not brief.get("supporting_evidence"):
        st.caption("none")
with ev_right:
    st.markdown("**Contradicting evidence**")
    for row in brief.get("contradicting_evidence") or []:
        st.markdown(f"- {row.get('claim')}  \n  `{row.get('evidence_id')}` · "
                    f"{row.get('figures', '')}")
    if not brief.get("contradicting_evidence"):
        st.caption("none reported")

# --- disqualified slices: the framework's central distinction ---------------
examined = investigation.slices_examined
disqualified = [s for s in examined if s["disqualified"]]
if disqualified:
    st.markdown("**Slices disqualified as evidence**")
    st.caption(
        "A slice returning INSUFFICIENT or NOT EVALUABLE disqualifies that slice. "
        "It is not a clean bill of health and it does not end the investigation."
    )
    st.dataframe(
        pd.DataFrame([{
            "slice": s["key"],
            "verdict": s["verdict"],
            "5xx %": s["rate_pct"],
            "baseline %": s["baseline_rate_pct"],
            "vs baseline": s["baseline_multiplier"],
            "failed rules": ", ".join(s["failed_rules"]),
            "evidence": s["evidence_id"],
        } for s in disqualified]),
        hide_index=True, width="stretch",
    )

remaining = investigation.state.get("candidate_slices") or []
if remaining:
    st.caption("Candidate slices left unexamined when the agent stopped: "
               + ", ".join(agent.spec_key(c) for c in remaining))

# --- next step --------------------------------------------------------------
if brief.get("next_diagnostic_step"):
    source = brief.get("next_step_source")
    st.info(f"**Next diagnostic step:** {brief['next_diagnostic_step']}\n\n"
            + (f"Source: `{source}`" if source else
               "_Unsourced — no runbook passage supports this step._"))

for label, key in (("Unavailable evidence", "unavailable_evidence"),
                   ("Caveats", "caveats")):
    if brief.get(key):
        st.caption(f"**{label}:** {brief[key]}")

# --- the ledger -------------------------------------------------------------
with st.expander(f"Evidence ledger — {len(investigation.evidence)} tool returns"):
    for item in investigation.evidence:
        st.markdown(f"**`{item['evidence_id']}`** · `{item['tool']}` · "
                    f"{item['seconds']}s")
        st.caption(item["summary"])
        st.code(json.dumps(item["arguments"]), language="json")

with st.expander("Agent trajectory — the tool sequence it chose"):
    for message in investigation.state.get("messages") or []:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                st.markdown(f"→ `{call['function']['name']}`"
                            f"({call['function']['arguments']})")
        elif message.get("role") == "assistant" and message.get("content"):
            st.caption("model wrote the brief")

if investigation.state.get("tool_failures"):
    with st.expander("Tool failures"):
        st.json(investigation.state["tool_failures"])
