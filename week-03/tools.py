"""
tools.py -- the four read-only investigation tools.

NEVER imports streamlit. Same boundary as week-01's detection.py and week-02's
ingestion.py, and it is tested the same way: importing this module must leave
'streamlit' out of sys.modules.

Every tool returns a plain JSON-serialisable dict. Not prose, not a dataclass --
the model has to read these, and the moment it has to parse "4 failures across
297 requests" out of a sentence it has the opportunity to say 5.

THE LINE THIS FILE DEFENDS
--------------------------

`get_incident_summary` returns what CHANGED. It does not return what is to
blame. No ranking, no suspect, no narrative. Two consequences that are easy to
get wrong and are handled explicitly below:

  * week-01's `build_incident_brief()` and `select_suspect()` are NOT wrapped and
    are NOT reachable from here. They name a suspect, which is the agent's job.

  * **Row order is a ranking.** `verdicts_to_frame()` sorts by descending error
    rate internally, so handing its output to a model would smuggle the answer
    in through position even with every score stripped. Slices are emitted
    sorted alphabetically by endpoint, which carries no information about which
    one matters.

If the summary tool named the suspect there would be no investigation left to
conduct.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

import detection
import topology as topology_module

WEEK_03 = Path(__file__).resolve().parent
DATA_FILE = WEEK_03 / "data" / "api_logs.csv"
TOPOLOGY_FILE = WEEK_03 / "topology.json"

# The rule set every verdict in this app is produced under. Carried into every
# tool return so a brief or a trace can state which thresholds applied.
EVIDENCE_RULES = dict(detection.DEFAULT_EVIDENCE_RULES)

MAX_RUNBOOK_PASSAGES = 3
RUNBOOK_SNIPPET_CHARS = 700


class ToolInputError(Exception):
    """Invalid arguments from the model.

    Returned to the agent as a structured error it can correct, never retried
    and never raised as a stack trace. FRAMEWORK: zero retries on malformed or
    invalid requests -- a retry of an invalid call is just the same invalid call.
    """


# ---------------------------------------------------------------------------
# Loading, cached at module level so repeated tool calls are cheap
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_logs() -> pd.DataFrame:
    return pd.read_csv(DATA_FILE, parse_dates=["timestamp"])


@lru_cache(maxsize=1)
def load_topology():
    return topology_module.load_topology(TOPOLOGY_FILE)


@lru_cache(maxsize=1)
def _corpus_and_index():
    """The week-02 retrieval stack. Imported lazily.

    Lazy because three of the four tools work with no network and no vector
    index, and a missing index must not stop the incident tools from running.
    FRAMEWORK: search_runbooks is non-critical.
    """
    import embedding
    import ingestion
    import retrieval

    documents = ingestion.load_corpus(WEEK_03 / "corpus" / "internal")
    index = embedding.load_index()
    return documents, index, retrieval.Retriever(index)


def dataset_window() -> dict:
    """The span the dataset actually covers, and its baseline period."""
    logs = load_logs()
    start, end = detection.resolve_baseline_period(logs, EVIDENCE_RULES)
    return {
        "data_start": logs["timestamp"].min().isoformat(),
        "data_end": logs["timestamp"].max().isoformat(),
        "baseline_start": start.isoformat(),
        "baseline_end": end.isoformat(),
        "baseline_minutes": EVIDENCE_RULES["baseline_minutes"],
    }


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def _parse_time(value, field: str) -> pd.Timestamp:
    """Accept 'HH:MM' or a full timestamp, resolved against the dataset's date."""
    if value is None:
        raise ToolInputError(f"{field} is required.")
    text = str(value).strip()
    logs = load_logs()
    day = logs["timestamp"].min().date()
    try:
        if re.fullmatch(r"\d{1,2}:\d{2}", text):
            return pd.Timestamp(f"{day} {text}")
        return pd.Timestamp(text)
    except Exception as error:
        raise ToolInputError(
            f"{field}={value!r} is not a time. Use 'HH:MM' (e.g. '14:00') or an "
            f"ISO timestamp. The dataset covers {day} "
            f"{logs['timestamp'].min():%H:%M}-{logs['timestamp'].max():%H:%M}."
        ) from error


def _known(column: str) -> list:
    return sorted(load_logs()[column].unique())


def _validate_member(value: Optional[str], column: str, field: str) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    value = str(value).strip()
    known = _known(column)
    if value not in known:
        raise ToolInputError(
            f"{field}={value!r} is not present in the data. Known values: "
            f"{', '.join(known)}."
        )
    return value


# ---------------------------------------------------------------------------
# TOOL 1 -- get_incident_summary
# ---------------------------------------------------------------------------


def get_incident_summary(window_start: str, window_end: str) -> dict:
    """What changed in a window. Per-slice counts, rates, p95, thresholds breached.

    Deliberately NOT included: any ranking, any suspect, any narrative, any
    ordering that implies importance. See the module docstring.
    """
    start = _parse_time(window_start, "window_start")
    end = _parse_time(window_end, "window_end")
    if end <= start:
        raise ToolInputError(
            f"window_end ({end:%H:%M}) must be after window_start ({start:%H:%M})."
        )

    logs = load_logs()
    window = detection.slice_time_window(logs, start, end)
    if window.empty:
        return {
            "tool": "get_incident_summary",
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "requests": 0,
            "slices": [],
            "note": "No requests in this window. This is a finding, not an error.",
        }

    failures = window[window["status_code"] >= 500]
    successful = window[window["status_code"].between(200, 299)]
    rate_floor = EVIDENCE_RULES["minimum_5xx_rate"]

    slices = []
    for (endpoint, backend), rows in window.groupby(detection.SLICE_COLUMNS):
        slice_failures = int((rows["status_code"] >= 500).sum())
        rate = slice_failures / len(rows)
        ok = rows[rows["status_code"].between(200, 299)]
        breached = []
        if rate >= rate_floor:
            breached.append(f"5xx rate at or above the {rate_floor * 100:.1f}% floor")
        if slice_failures >= EVIDENCE_RULES["minimum_failures"]:
            breached.append(
                f"failed requests at or above the minimum of "
                f"{EVIDENCE_RULES['minimum_failures']}"
            )
        if len(rows) < EVIDENCE_RULES["minimum_requests"]:
            breached.append(
                f"BELOW the {EVIDENCE_RULES['minimum_requests']}-request minimum "
                f"for evaluation"
            )
        slices.append({
            "endpoint": endpoint,
            "backend_service": backend,
            "requests": int(len(rows)),
            "failed_requests": slice_failures,
            "error_rate_pct": round(rate * 100, 2),
            "p95_ms_successful_only": (
                round(float(ok["response_time_ms"].quantile(0.95)), 0)
                if not ok.empty else None
            ),
            "thresholds": breached or ["none breached"],
            "consumers_present": sorted(rows["consumer"].unique()),
        })

    # Alphabetical by endpoint. NOT by rate -- see the module docstring on why
    # row order would otherwise be a ranking the contract forbids.
    slices.sort(key=lambda s: (s["endpoint"], s["backend_service"]))

    return {
        "tool": "get_incident_summary",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "requests": int(len(window)),
        "failed_requests": int(len(failures)),
        "overall_error_rate_pct": round(len(failures) / len(window) * 100, 2),
        "p95_ms_successful_only": (
            round(float(successful["response_time_ms"].quantile(0.95)), 0)
            if not successful.empty else None
        ),
        "slices": slices,
        "slices_are_unranked": (
            "Sorted alphabetically by endpoint. This tool reports what changed, "
            "not what is to blame -- order carries no information about "
            "importance. Use compare_to_baseline to establish whether a slice "
            "has evidence behind it."
        ),
        "rule_set": EVIDENCE_RULES["version"],
        **dataset_window(),
    }


# ---------------------------------------------------------------------------
# TOOL 2 -- compare_to_baseline
# ---------------------------------------------------------------------------


def compare_to_baseline(endpoint: str, window_start: str, window_end: str,
                        backend_service: Optional[str] = None,
                        consumer: Optional[str] = None) -> dict:
    """One model-selected slice against the dataset baseline, with the gate verdict.

    THE SLICE MODEL, stated because the contract's wording and the code's model
    differ and the difference matters:

      detection.py's evaluation unit is endpoint x backend_service. `consumer`
      is a FILTER applied before grouping, not a slice key. So a spec carrying
      a consumer means "restrict to this consumer's traffic, then evaluate that
      endpoint x backend pair". The returned slice label says so explicitly,
      because an agent that believed consumer was a slice dimension would draw
      the wrong conclusion from a NOT EVALUABLE.

      `endpoint` is required for that reason: a spec with only a consumer
      describes many slices, not one.

    The baseline is a property of the DATASET -- the first 120 minutes -- sliced
    by the same dimension filters and never by the time filter. Deriving it from
    the selected window would make an incident its own control group.
    """
    start = _parse_time(window_start, "window_start")
    end = _parse_time(window_end, "window_end")
    if end <= start:
        raise ToolInputError(
            f"window_end ({end:%H:%M}) must be after window_start ({start:%H:%M})."
        )
    endpoint = _validate_member(endpoint, "endpoint", "endpoint")
    if endpoint is None:
        raise ToolInputError(
            "endpoint is required. A slice spec without an endpoint describes "
            f"many slices rather than one. Known endpoints: "
            f"{', '.join(_known('endpoint'))}."
        )
    backend_service = _validate_member(backend_service, "backend_service", "backend_service")
    consumer = _validate_member(consumer, "consumer", "consumer")

    logs = load_logs()
    baseline_start, baseline_end = detection.resolve_baseline_period(logs, EVIDENCE_RULES)

    dimension_filtered = detection.apply_dimension_filters(
        logs,
        endpoints=[endpoint],
        backends=[backend_service] if backend_service else None,
        consumers=[consumer] if consumer else None,
    )
    window = detection.slice_time_window(dimension_filtered, start, end)
    baseline = detection.slice_time_window(dimension_filtered, baseline_start, baseline_end)

    if window.empty:
        declared = load_topology().backend_for(endpoint) if endpoint else None
        return {
            "tool": "compare_to_baseline",
            "slice": {"endpoint": endpoint, "backend_service": backend_service,
                      "consumer": consumer},
            "verdict": "NO DATA",
            "detail": (
                f"No requests match this slice in {start:%H:%M}-{end:%H:%M}. "
                + (f"The declared topology serves {endpoint} from {declared}. "
                   if declared and backend_service and declared != backend_service
                   else "")
                + "This is a finding, not an error."
            ),
            "is_evidence": False,
        }

    verdicts = detection.evaluate_all_slices(
        window, baseline, start, end, baseline_start, baseline_end,
        rules=EVIDENCE_RULES,
        filters={"endpoint": [endpoint],
                 "backend_service": [backend_service] if backend_service else None,
                 "consumer": [consumer] if consumer else None},
    )

    results = []
    for verdict in sorted(verdicts, key=lambda v: v.slice_key.label):
        text = detection.describe_verdict(verdict)
        results.append({
            "slice_label": verdict.slice_key.label
                           + (f" (consumer filter: {consumer})" if consumer else ""),
            "endpoint": verdict.slice_key.endpoint,
            "backend_service": verdict.slice_key.backend_service,
            "consumer_filter": consumer,
            "verdict": verdict.status,
            "requests": verdict.requests,
            "failed_requests": verdict.failures,
            "error_rate_pct": round(verdict.rate * 100, 2),
            "baseline_rate_pct": (round(verdict.baseline_rate * 100, 2)
                                  if verdict.baseline_rate is not None else None),
            "baseline_multiplier": (round(verdict.baseline_multiplier, 1)
                                    if verdict.baseline_multiplier is not None else None),
            "baseline_requests": verdict.baseline_requests,
            "baseline_failures": verdict.baseline_failures,
            "consecutive_breach_buckets": verdict.longest_breach_run,
            "failed_rules": [c.rule for c in verdict.failed_checks],
            "explanation": text.detail,
            # The single most important field for the agent's control flow.
            "is_evidence": verdict.status == detection.EVIDENCE_SUFFICIENT,
            "disqualified_as_evidence": verdict.status != detection.EVIDENCE_SUFFICIENT,
        })

    return {
        "tool": "compare_to_baseline",
        "requested_slice": {"endpoint": endpoint, "backend_service": backend_service,
                            "consumer": consumer},
        "slice_model_note": (
            "The evaluation unit is endpoint x backend_service. A consumer is a "
            "filter applied before grouping, not a slice key. A NOT EVALUABLE on "
            "a consumer-filtered slice says that consumer's own baseline is too "
            "thin to judge against -- it does NOT say the endpoint is healthy."
        ),
        "baseline_period": f"{baseline_start:%H:%M}-{baseline_end:%H:%M}",
        "results": results,
        "rule_set": EVIDENCE_RULES["version"],
        "verdict_meanings": {
            "EVIDENCE SUFFICIENT": "this slice clears every rule and may support a suspect",
            "EVIDENCE INSUFFICIENT": "evaluated and fell short; this slice is not evidence",
            "NOT EVALUABLE": (
                "could not be judged at all. NOT a clean bill of health, and NOT a "
                "reason to stop the investigation -- it disqualifies this slice only"
            ),
        },
    }


# ---------------------------------------------------------------------------
# TOOL 3 -- get_service_dependencies
# ---------------------------------------------------------------------------


def get_service_dependencies(endpoint: Optional[str] = None,
                             backend_service: Optional[str] = None) -> dict:
    """Declared topology relationships, with the drift banner.

    Drift is cross-checked against the FULL dataset, never a filtered window:
    checking a window would report every endpoint absent from it as "declared
    but not observed", which is noise rather than drift.
    """
    declared = load_topology()
    logs = load_logs()
    drift = topology_module.cross_check(declared, logs)

    endpoint = _validate_member(endpoint, "endpoint", "endpoint")
    backend_service = _validate_member(backend_service, "backend_service", "backend_service")

    relationships = []
    endpoints = [endpoint] if endpoint else sorted(declared.endpoints)
    for name in endpoints:
        try:
            backend = declared.backend_for(name)
        except Exception:
            continue
        if backend_service and backend != backend_service:
            continue
        runbooks = declared.runbooks_for(name)
        siblings = [e for e in declared.endpoints_for(backend) if e != name]
        relationships.append({
            "endpoint": name,
            "backend_service": backend,
            "owner_team": declared.owner_of(name),
            "endpoint_runbook": runbooks["endpoint_runbook"],
            "service_runbook": runbooks["service_runbook"],
            "sibling_endpoints_on_same_backend": siblings,
        })

    return {
        "tool": "get_service_dependencies",
        "source": "declared topology, not inferred from traffic",
        "topology_version": declared.version,
        "relationships": relationships,
        "drift_detected": drift.has_drift,
        "drift": list(drift.messages()) if drift.has_drift else [],
        "drift_guidance": (
            "Declared topology and observed traffic disagree. Use the declared "
            "relationship, but flag any conclusion that depends on a drifted one. "
            "Drift alone does not halt an investigation; drift on a relationship "
            "the suspect depends on does."
            if drift.has_drift else
            "Declared topology and observed traffic agree on every relationship."
        ),
    }


# ---------------------------------------------------------------------------
# TOOL 4 -- search_runbooks
# ---------------------------------------------------------------------------


def search_runbooks(query: str, service: Optional[str] = None,
                    max_passages: int = MAX_RUNBOOK_PASSAGES) -> dict:
    """Hybrid retrieval over the 19-document corpus.

    Access level and superseded handling are intact from week-02: restricted
    documents are withheld and NAMED, never silently dropped, and superseded
    documents are excluded rather than competing on similarity with the versions
    that replaced them.

    Passages are capped and truncated. Each call costs a query embedding --
    measured at 3.6-8.7 seconds in week-02 -- and six full passages is ~1,700
    tokens of context per call, which across several calls grows faster than the
    investigation does.
    """
    if not query or not str(query).strip():
        raise ToolInputError("query is required and must be non-empty.")

    # Demo path 3, the degraded path. A switch rather than a code edit, so the
    # failure is reproducible on demand and the recovery behaviour is a tested
    # path rather than a described one. It returns the SAME structure a genuine
    # failure returns, so nothing downstream can tell the difference -- a
    # simulated outage the agent could distinguish from a real one would prove
    # nothing.
    if os.environ.get("TRIAGELENS_DISABLE_RUNBOOKS") == "1":
        return {
            "tool": "search_runbooks",
            "available": False,
            "error": "ServiceUnavailable",
            "detail": "Runbook retrieval is disabled (TRIAGELENS_DISABLE_RUNBOOKS=1).",
            "guidance": (
                "Runbook retrieval is unavailable. Continue with an evidence-only "
                "brief and state that procedure is unavailable; do not invent a "
                "next diagnostic step and do not recall runbook content from "
                "memory."
            ),
        }

    try:
        _documents, _index, retriever = _corpus_and_index()
    except Exception as error:
        # Non-critical tool. A failure here is reported as a finding so the
        # agent can produce an evidence-only brief rather than stalling.
        return {
            "tool": "search_runbooks",
            "available": False,
            "error": f"{type(error).__name__}: {error}",
            "guidance": (
                "Runbook retrieval is unavailable. Continue with an evidence-only "
                "brief and state that procedure is unavailable; do not invent a "
                "next diagnostic step."
            ),
        }

    import retrieval as retrieval_module

    service = _validate_member(service, "backend_service", "service") if service else None
    max_passages = max(1, min(int(max_passages or MAX_RUNBOOK_PASSAGES), 6))

    request = retrieval_module.ContextRequest(
        question=str(query).strip(),
        service=service,
        top_k=max_passages,
        access_level="operations",      # the agent never reads restricted content
        statuses=("current",),          # superseded documents never returned as current
    )

    try:
        result = retriever.retrieve(request)
    except Exception as error:
        return {
            "tool": "search_runbooks",
            "available": False,
            "error": f"{type(error).__name__}: {error}",
            "guidance": (
                "Runbook retrieval failed. Continue with an evidence-only brief "
                "and state that procedure is unavailable."
            ),
        }

    passages = []
    for scored in result.results:
        chunk = scored.chunk
        text = " ".join(chunk.text.split())
        if len(text) > RUNBOOK_SNIPPET_CHARS:
            text = text[:RUNBOOK_SNIPPET_CHARS].rsplit(" ", 1)[0] + " ..."
        passages.append({
            "document_id": chunk.document_id,
            "title": chunk.metadata["title"],
            "section": chunk.heading,
            "document_type": chunk.metadata["document_type"],
            "service": chunk.metadata["service"],
            "status": chunk.metadata["status"],
            "version": str(chunk.metadata["version"]),
            "last_reviewed": str(chunk.metadata["last_reviewed"]),
            "text": text,
            "why_retrieved": scored.why,
        })

    return {
        "tool": "search_runbooks",
        "available": True,
        "query": str(query).strip(),
        "service_scope": service,
        "chunks_searched": result.candidates_considered,
        "corpus_chunks": result.corpus_size,
        "passages": passages,
        "withheld_restricted": list(result.excluded_restricted),
        "withheld_guidance": (
            "Relevant guidance may exist in the documents named above but is "
            "above this caller's access level. You may state that such guidance "
            "exists; you may NOT state or infer its contents."
            if result.excluded_restricted else ""
        ),
        "note_if_empty": (
            "No passage matched. The corpus deliberately contains nothing on host "
            "metrics, database internals, connection pools, queue depth, CDN "
            "behaviour or cost. An empty result is a finding: say the corpus does "
            "not cover it, and name what it does cover."
            if not passages else ""
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "get_incident_summary": get_incident_summary,
    "compare_to_baseline": compare_to_baseline,
    "get_service_dependencies": get_service_dependencies,
    "search_runbooks": search_runbooks,
}

# FRAMEWORK: failure is not uniform. Criticality drives what the agent does when
# a tool fails, and it is declared here rather than decided in the prompt.
TOOL_CRITICALITY = {
    "get_incident_summary": "critical",
    "compare_to_baseline": "critical_for_suspect",
    "get_service_dependencies": "non_critical",
    "search_runbooks": "non_critical",
}


def call_tool(name: str, arguments: dict) -> dict:
    """Dispatch, converting invalid input into a structured error, never a trace."""
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {
            "tool": name, "error": "unknown_tool",
            "detail": f"No such tool. Available: {', '.join(TOOL_FUNCTIONS)}.",
            "retryable": False,
        }
    try:
        return function(**(arguments or {}))
    except ToolInputError as error:
        return {
            "tool": name, "error": "invalid_input", "detail": str(error),
            "retryable": False,
            "guidance": "Correct the arguments and call again. Do not repeat this call unchanged.",
        }
    except TypeError as error:
        return {
            "tool": name, "error": "invalid_arguments", "detail": str(error),
            "retryable": False,
            "guidance": "Check the argument names against the tool schema.",
        }
    except Exception as error:       # noqa: BLE001 -- surfaced, never swallowed
        return {
            "tool": name, "error": type(error).__name__, "detail": str(error),
            "retryable": True,
            "criticality": TOOL_CRITICALITY.get(name, "non_critical"),
        }
