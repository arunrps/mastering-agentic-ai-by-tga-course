"""
detection.py -- evidence-gated incident detection over API gateway request logs.

This module holds the DETECTION logic and nothing else. It imports pandas and
the standard library; it must never import streamlit. That is what lets the
same functions run inside the dashboard today and be called as an agent tool
later, from a script, a test, or a notebook.

Two hard rules shape everything here:

1. No language model computes, recalculates or estimates anything. Every number
   is a pandas aggregation. The functions return STRUCTURED DATA -- Verdict
   objects -- never rendered markdown. Sentences are built by describe_verdict()
   from the fields of a Verdict, so a caller that wants the numbers gets the
   numbers, and a caller that wants prose gets prose derived from exactly those
   same numbers.

2. A baseline is only ever compared against the SAME dimensional slice. A
   /checkout signal is compared against historical /checkout, on the same
   backend, under the same consumer and backend filters. evaluate_all_slices()
   enforces this structurally: it groups the signal frame and the baseline frame
   by the same key and pairs them up by that key, so there is no code path in
   which a filtered slice is compared against an all-platform baseline.

Vocabulary: a signal is "evidence sufficient", "evidence insufficient", or
"not evaluable". Never a confidence percentage -- there is no calibrated
probabilistic model here, so a percentage would be indefensible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import pandas as pd

# Buckets are 5 minutes everywhere: the charts, the slider step, and the
# consecutive-breach rule below all use this same value, so a "bucket" means
# one thing across the whole app.
BUCKET_SIZE = "5min"

# The two columns that together identify one evaluation unit. Grouping by BOTH
# is deliberate: an endpoint can be served by more than one backend, and the
# earlier version of this app assumed one backend per endpoint by reading
# .iloc[0] off the first matching row. That assumption is not safe on real
# data, and later scenarios break it on purpose.
SLICE_COLUMNS = ["endpoint", "backend_service"]

# --- Verdict statuses -------------------------------------------------------
# Three outcomes, not two. "We evaluated this and it does not qualify" and "we
# could not evaluate this at all" are different facts, and showing a green tick
# for the second one is an operational error: a slice with 90 requests in six
# hours is not healthy, it is unmeasured.
EVIDENCE_SUFFICIENT = "EVIDENCE SUFFICIENT"
EVIDENCE_INSUFFICIENT = "EVIDENCE INSUFFICIENT"
NOT_EVALUABLE = "NOT EVALUABLE"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# One object, passed in as a parameter rather than read as a global, so a caller
# can evaluate the same window under two different rule sets -- which is exactly
# what answering "what would it take for this to fire?" requires.
#
# The version identifier travels with every Verdict, so any rendered report or
# screenshot can state which rule set produced it.
#
# NOTE on the same-slice rule and `region`: the rule extends to region -- a
# selected region must be compared against that same region historically. The
# dimension is deliberately NOT implemented here, because this dataset has a
# single region (us-east-1, all 50,000 rows) and the sidebar has no region
# control. Add "region" to SLICE_COLUMNS and to the filter arguments when a
# multi-region dataset exists. The requirement is correct; the dimension isn't
# there yet.
DEFAULT_EVIDENCE_RULES = {
    "version": "evidence-rules-2026-08-20.a",

    # --- how the baseline is built ---------------------------------------
    # The baseline is a property of the DATASET, not of the user's selection:
    # the first N minutes of the data's own time range. It is sliced by the
    # same endpoint/backend/consumer filters as the signal, and NEVER by the
    # time filter -- so selecting 14:00-15:00 still compares against the quiet
    # warm-up period rather than against the incident's own onset.
    #
    # 120 rather than 60. At this dataset's ~0.4% baseline error rate you need
    # roughly 1,250 requests to expect 5 failures, and /checkout only reaches
    # that around the 90-minute mark (exactly 5 failures at 90 min, 8 at 120).
    # A 60-minute baseline gives /checkout 911 requests and 3 failures, which
    # fails baseline_minimum_failures and makes the real incident NOT
    # EVALUABLE. See BASELINE_SIZING.md for the arithmetic.
    "baseline_minutes": 120,

    # --- can this slice be judged at all? (failing these -> NOT EVALUABLE) ---
    # Window-level, never per-bucket. No 5-minute bucket in this dataset
    # reaches 200 requests except /search, so a per-bucket reading of this rule
    # would mean the gate could never fire.
    "minimum_requests": 200,
    # A baseline must itself qualify before a multiplier built on it is
    # trusted. Without these, /refunds gets a "baseline" from 2 failures, and
    # one request either way swings its multiplier between 1.1x and 3.4x.
    "baseline_minimum_requests": 200,
    "baseline_minimum_failures": 5,

    # --- does the evidence clear the bar? (failing these -> INSUFFICIENT) ---
    "minimum_failures": 10,
    # 0.01, not 0.02. The floor's job is "don't even consider this", not "this
    # is bad" -- the baseline multiplier does the real work. At 0.02 the real
    # incident cleared the floor by only 0.6 percentage points on the default
    # full-day view, which is too thin a margin to survive a new dataset.
    "minimum_5xx_rate": 0.01,
    "minimum_baseline_multiplier": 3.0,
    "consecutive_buckets_required": 2,

    "bucket_size": BUCKET_SIZE,
}

# Which rules are preconditions for judging at all, and which are the evidence
# bar itself. Order matters: it is the order failures are reported in, so the
# generated sentence is a deterministic function of the config.
_PRECONDITION_RULES = (
    "minimum_requests",
    "evaluable_buckets",
    "baseline_minimum_requests",
    "baseline_minimum_failures",
)
_EVIDENCE_RULES_ORDER = (
    "minimum_failures",
    "minimum_5xx_rate",
    "minimum_baseline_multiplier",
    "consecutive_buckets_required",
)

# Human-readable fragments for each rule, keyed by config key. The sentence
# builder assembles these with numbers taken from the Verdict -- there is no
# hardcoded message anywhere, so changing a threshold changes the prose.
_RULE_LABELS = {
    "minimum_requests": "requests in the window",
    "evaluable_buckets": "5-minute buckets containing requests",
    "baseline_minimum_requests": "requests in the matching baseline",
    "baseline_minimum_failures": "failures in the matching baseline",
    "minimum_failures": "failed requests",
    "minimum_5xx_rate": "5xx rate",
    "minimum_baseline_multiplier": "5xx rate relative to its matching baseline",
    "consecutive_buckets_required": "consecutive 5-minute buckets over the rate floor",
}

# How to render each rule's observed value and threshold.
_RULE_UNITS = {
    "minimum_requests": "count",
    "evaluable_buckets": "count",
    "baseline_minimum_requests": "count",
    "baseline_minimum_failures": "count",
    "minimum_failures": "count",
    "minimum_5xx_rate": "rate",
    "minimum_baseline_multiplier": "ratio",
    "consecutive_buckets_required": "count",
}


def resolve_rules(rules: Optional[dict] = None) -> dict:
    """Fill in any missing keys from the defaults and reject unknown ones.

    Callers pass a partial dict -- {"minimum_failures": 25} -- and get a
    complete rule set back. An unknown key is an error rather than a silent
    no-op, because a typo in a threshold name would otherwise leave the caller
    believing a rule had been changed when it had not.
    """
    if rules is None:
        return dict(DEFAULT_EVIDENCE_RULES)
    unknown = set(rules) - set(DEFAULT_EVIDENCE_RULES)
    if unknown:
        raise ValueError(
            f"Unknown evidence rule(s): {sorted(unknown)}. "
            f"Known rules: {sorted(DEFAULT_EVIDENCE_RULES)}"
        )
    merged = dict(DEFAULT_EVIDENCE_RULES)
    merged.update(rules)
    return merged


# ---------------------------------------------------------------------------
# Result types
#
# These are plain dataclasses on purpose. An agent tool calling this module
# needs fields it can read, not a paragraph it has to parse -- the moment a
# language model has to re-read "4 failures across 297 requests" out of prose,
# it has the opportunity to say 5.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SliceKey:
    """The dimensional slice being judged: one endpoint on one backend."""
    endpoint: str
    backend_service: str

    @property
    def label(self) -> str:
        return f"{self.endpoint} via {self.backend_service}"


@dataclass(frozen=True)
class RuleCheck:
    """One threshold, the value measured against it, and whether it passed.

    `evaluated` is False when the check could not be run at all -- the baseline
    multiplier when there is no usable baseline, for instance. A check that was
    not run is never counted as passing. That distinction is the whole point:
    the previous version of this app treated a missing baseline as satisfying
    the baseline test, so absence of a comparison became evidence.
    """
    rule: str
    label: str
    observed: Optional[float]
    threshold: float
    passed: bool
    evaluated: bool
    unit: str

    @property
    def is_precondition(self) -> bool:
        return self.rule in _PRECONDITION_RULES


@dataclass
class Verdict:
    """Everything known about one slice in one window, plus the ruling."""
    status: str
    slice_key: SliceKey
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    baseline_start: pd.Timestamp
    baseline_end: pd.Timestamp

    requests: int
    failures: int
    rate: float                       # fraction, not percent

    baseline_requests: int
    baseline_failures: int
    baseline_rate: Optional[float]    # None when the baseline slice is empty
    baseline_multiplier: Optional[float]

    buckets_evaluated: int
    buckets_breaching: int
    longest_breach_run: int

    checks: Sequence[RuleCheck] = field(default_factory=tuple)
    filters: dict = field(default_factory=dict)
    rules_version: str = ""

    @property
    def qualifies(self) -> bool:
        return self.status == EVIDENCE_SUFFICIENT

    @property
    def failed_checks(self) -> list:
        """Checks that ran and failed, plus checks that could not run.

        Reported in config order so the generated sentence is deterministic.
        """
        order = _PRECONDITION_RULES + _EVIDENCE_RULES_ORDER
        blocking = [c for c in self.checks if not c.passed]
        return sorted(blocking, key=lambda c: order.index(c.rule))

    def to_dict(self) -> dict:
        """Flat, JSON-friendly form -- the shape an agent tool should return."""
        return {
            "status": self.status,
            "endpoint": self.slice_key.endpoint,
            "backend_service": self.slice_key.backend_service,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "baseline_start": self.baseline_start.isoformat(),
            "baseline_end": self.baseline_end.isoformat(),
            "requests": self.requests,
            "failures": self.failures,
            "rate": self.rate,
            "baseline_requests": self.baseline_requests,
            "baseline_failures": self.baseline_failures,
            "baseline_rate": self.baseline_rate,
            "baseline_multiplier": self.baseline_multiplier,
            "buckets_evaluated": self.buckets_evaluated,
            "buckets_breaching": self.buckets_breaching,
            "longest_breach_run": self.longest_breach_run,
            "filters": self.filters,
            "rules_version": self.rules_version,
            "checks": [
                {
                    "rule": c.rule,
                    "observed": c.observed,
                    "threshold": c.threshold,
                    "passed": c.passed,
                    "evaluated": c.evaluated,
                }
                for c in self.checks
            ],
        }


@dataclass(frozen=True)
class VerdictText:
    """A headline and a sentence, both built from a Verdict's own fields."""
    headline: str
    detail: str


# ---------------------------------------------------------------------------
# Filtering
#
# The module owns filtering rather than the Streamlit layer, because the
# same-slice guarantee depends on the signal and the baseline being cut the
# same way. Two functions, so the caller can apply the dimension filters once
# and then take two different time slices from the result -- which is precisely
# how the baseline is kept dimension-matched but time-independent.
# ---------------------------------------------------------------------------

def apply_dimension_filters(
    logs: pd.DataFrame,
    endpoints: Optional[Sequence[str]] = None,
    backends: Optional[Sequence[str]] = None,
    consumers: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Keep rows matching every supplied dimension filter.

    Filter contract, stated explicitly because it used to be implicit:

        None        -> no constraint on this dimension ("any endpoint")
        ["/cart"]   -> keep only these values
        []          -> ValueError

    An empty list is rejected rather than silently returning zero rows. As a UI
    that produced a "no data" message; as an agent tool it would produce an
    empty result indistinguishable from a genuine no-match, and the caller
    would have no way to tell "you asked for nothing" from "nothing is there".
    """
    conditions = {
        "endpoint": endpoints,
        "backend_service": backends,
        "consumer": consumers,
    }
    keep = pd.Series(True, index=logs.index)
    for column, allowed in conditions.items():
        if allowed is None:
            continue
        if len(allowed) == 0:
            raise ValueError(
                f"Empty selection for '{column}'. Pass None for no constraint, "
                "or a non-empty list of values."
            )
        keep &= logs[column].isin(list(allowed))
    return logs[keep]


def slice_time_window(logs: pd.DataFrame, start, end) -> pd.DataFrame:
    """Rows with a timestamp in [start, end], both ends inclusive."""
    return logs[logs["timestamp"].between(pd.Timestamp(start), pd.Timestamp(end))]


def resolve_baseline_period(all_logs: pd.DataFrame, rules: Optional[dict] = None):
    """The first `baseline_minutes` of the dataset's own time range.

    Derived from the data, not hardcoded to a clock time, so pointing the app
    at a dataset that runs 22:00-04:00 needs no code change. Returned to the
    caller so the UI can show the user what the comparison is actually against
    -- an unstated baseline is an unfalsifiable one.

    Start is floored to a bucket boundary so the period reads as a clean
    09:00 rather than 09:00:00.106.
    """
    rules = resolve_rules(rules)
    start = all_logs["timestamp"].min().floor(rules["bucket_size"])
    end = start + pd.Timedelta(minutes=rules["baseline_minutes"])
    return start, end


# ---------------------------------------------------------------------------
# Bucketed breach detection
# ---------------------------------------------------------------------------

def _bucket_breaches(rows: pd.DataFrame, window_start, window_end, rules: dict):
    """Count 5-minute buckets over the rate floor, and the longest run of them.

    Two decisions that the spec left open, made explicitly here:

    1. PARTIAL BUCKETS AT THE WINDOW EDGES ARE DROPPED. Only buckets whose full
       5 minutes sit inside the window are counted. The Streamlit slider steps
       in 5-minute increments from a floored start, so its windows always align
       and this never bites in the UI -- but an agent will call this with
       arbitrary timestamps, and a 40-second edge bucket holding 3 requests and
       1 failure is a "33% rate" that would breach the floor and help complete
       a run. A truncated bucket is not a bucket.

    2. BUCKETS WITH ZERO REQUESTS ARE EXCLUDED FROM THE SEQUENCE ENTIRELY --
       they neither breach nor reset a run. A gap in the data is not evidence
       of recovery. Low-volume slices (/refunds runs 6-23 requests a bucket,
       and less once a consumer filter is applied) have real gaps, and letting
       one break a run would hide a genuine sustained failure. The consequence:
       "consecutive" means consecutive among buckets that contain requests, and
       describe_verdict() says so.

    Note there is deliberately no per-bucket minimum request count. A thin
    bucket can breach the rate floor spuriously, but the breach rule is one AND
    in a chain -- the window-level request and failure floors still gate the
    verdict -- so a spurious run cannot on its own produce a false positive.
    """
    freq = rules["bucket_size"]
    floor = rules["minimum_5xx_rate"]
    step = pd.Timedelta(freq)
    window_start = pd.Timestamp(window_start)
    window_end = pd.Timestamp(window_end)

    if rows.empty:
        return 0, 0, 0

    per_request = pd.DataFrame({
        "timestamp": rows["timestamp"],
        "is_server_error": rows["status_code"] >= 500,
    })
    grouped = (
        per_request.set_index("timestamp")
        .resample(freq)["is_server_error"]
        .agg(["size", "sum"])
    )

    complete = grouped[
        (grouped.index >= window_start) & (grouped.index + step <= window_end)
    ]
    populated = complete[complete["size"] > 0]
    if populated.empty:
        return 0, 0, 0

    breaching = (populated["sum"] / populated["size"]) >= floor

    longest = run = 0
    for is_breach in breaching:
        run = run + 1 if is_breach else 0
        longest = max(longest, run)

    return len(populated), int(breaching.sum()), longest


def _count_failures(rows: pd.DataFrame) -> int:
    """5xx only. A 4xx is the client's fault and is not an availability signal."""
    return int((rows["status_code"] >= 500).sum())


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def evaluate_slice(
    window_rows: pd.DataFrame,
    baseline_rows: pd.DataFrame,
    window_start,
    window_end,
    baseline_start,
    baseline_end,
    slice_key: SliceKey,
    rules: Optional[dict] = None,
    filters: Optional[dict] = None,
) -> Verdict:
    """Judge one dimensional slice in one window. Returns a Verdict, not text.

    CONTRACT: `window_rows` and `baseline_rows` must already be cut to the SAME
    dimensional slice -- same endpoint, same backend, same consumer/backend
    filters. This function cannot verify that, which is why callers should
    normally go through evaluate_all_slices(), where the pairing is done by a
    shared group key and the guarantee is structural.

    The gate runs in two stages:

      Stage 1, preconditions -- can this slice be judged at all? Too little
      traffic, too few buckets holding any requests, or a baseline that is
      itself too thin to be a rate. Any failure here gives NOT EVALUABLE. This
      is not a soft verdict: a slice with 90 requests in six hours is unmeasured,
      not healthy, and the two must not render the same.

      Stage 2, the evidence bar -- failures, absolute rate, rate against its own
      matching baseline, and sustained breach. All four must pass for EVIDENCE
      SUFFICIENT; any failure gives EVIDENCE INSUFFICIENT.

    Every check is recorded either way, including the ones that passed, so the
    caller can explain the ruling without recomputing anything.
    """
    rules = resolve_rules(rules)

    requests = len(window_rows)
    failures = _count_failures(window_rows)
    rate = failures / requests if requests else 0.0

    baseline_requests = len(baseline_rows)
    baseline_failures = _count_failures(baseline_rows)
    baseline_rate = (
        baseline_failures / baseline_requests if baseline_requests else None
    )

    buckets_evaluated, buckets_breaching, longest_run = _bucket_breaches(
        window_rows, window_start, window_end, rules
    )

    def check(rule, observed, threshold, passed, evaluated=True):
        return RuleCheck(
            rule=rule,
            label=_RULE_LABELS[rule],
            observed=observed,
            threshold=threshold,
            passed=passed,
            evaluated=evaluated,
            unit=_RULE_UNITS[rule],
        )

    # --- Stage 1: preconditions ------------------------------------------
    preconditions = [
        check("minimum_requests", requests, rules["minimum_requests"],
              requests >= rules["minimum_requests"]),
        # Reuses the consecutive-buckets threshold: you cannot look for a run of
        # N buckets in a window that does not hold N buckets with data in them.
        # This covers both "the window is too short" and "this slice is too
        # sparse to fill the window's buckets", which are the same problem.
        check("evaluable_buckets", buckets_evaluated,
              rules["consecutive_buckets_required"],
              buckets_evaluated >= rules["consecutive_buckets_required"]),
        check("baseline_minimum_requests", baseline_requests,
              rules["baseline_minimum_requests"],
              baseline_requests >= rules["baseline_minimum_requests"]),
        check("baseline_minimum_failures", baseline_failures,
              rules["baseline_minimum_failures"],
              baseline_failures >= rules["baseline_minimum_failures"]),
    ]
    baseline_usable = all(
        c.passed for c in preconditions
        if c.rule.startswith("baseline_")
    )

    # The multiplier is only meaningful against a baseline that qualified.
    # Computed for display either way, but marked not-evaluated when the
    # baseline is thin, so it can never be read as a passing check.
    multiplier = (
        rate / baseline_rate if baseline_rate else None
    )

    # --- Stage 2: the evidence bar ---------------------------------------
    evidence = [
        check("minimum_failures", failures, rules["minimum_failures"],
              failures >= rules["minimum_failures"]),
        check("minimum_5xx_rate", rate, rules["minimum_5xx_rate"],
              rate >= rules["minimum_5xx_rate"]),
        check(
            "minimum_baseline_multiplier", multiplier,
            rules["minimum_baseline_multiplier"],
            passed=bool(
                baseline_usable
                and multiplier is not None
                and multiplier >= rules["minimum_baseline_multiplier"]
            ),
            evaluated=baseline_usable and multiplier is not None,
        ),
        check("consecutive_buckets_required", longest_run,
              rules["consecutive_buckets_required"],
              longest_run >= rules["consecutive_buckets_required"]),
    ]

    if not all(c.passed for c in preconditions):
        status = NOT_EVALUABLE
    elif all(c.passed for c in evidence):
        status = EVIDENCE_SUFFICIENT
    else:
        status = EVIDENCE_INSUFFICIENT

    return Verdict(
        status=status,
        slice_key=slice_key,
        window_start=pd.Timestamp(window_start),
        window_end=pd.Timestamp(window_end),
        baseline_start=pd.Timestamp(baseline_start),
        baseline_end=pd.Timestamp(baseline_end),
        requests=requests,
        failures=failures,
        rate=rate,
        baseline_requests=baseline_requests,
        baseline_failures=baseline_failures,
        baseline_rate=baseline_rate,
        baseline_multiplier=multiplier,
        buckets_evaluated=buckets_evaluated,
        buckets_breaching=buckets_breaching,
        longest_breach_run=longest_run,
        checks=tuple(preconditions + evidence),
        filters=dict(filters or {}),
        rules_version=rules["version"],
    )


def evaluate_all_slices(
    window_logs: pd.DataFrame,
    baseline_logs: pd.DataFrame,
    window_start,
    window_end,
    baseline_start,
    baseline_end,
    rules: Optional[dict] = None,
    filters: Optional[dict] = None,
) -> list:
    """Judge every endpoint x backend pair present in the window.

    This is where the same-slice rule is ENFORCED rather than merely intended.
    Both frames are grouped by the same SLICE_COLUMNS, and a pair's baseline
    rows are looked up by that pair's own key. There is no branch in which one
    key's signal meets another key's baseline, or an all-platform baseline.

    `baseline_logs` must already carry the same dimension filters as
    `window_logs` and must NOT carry its time filter -- that is the caller's
    job, and slice_time_window() over a dimension-filtered frame is how it is
    done.

    Pairs present in the baseline but absent from the window are skipped: no
    signal, nothing to judge. Pairs present in the window but absent from the
    baseline get an empty baseline frame and come back NOT EVALUABLE, which is
    the honest answer.
    """
    rules = resolve_rules(rules)
    baseline_groups = dict(list(baseline_logs.groupby(SLICE_COLUMNS)))
    empty_baseline = baseline_logs.iloc[0:0]

    verdicts = []
    for key, rows in window_logs.groupby(SLICE_COLUMNS):
        endpoint, backend = key
        verdicts.append(
            evaluate_slice(
                window_rows=rows,
                baseline_rows=baseline_groups.get(key, empty_baseline),
                window_start=window_start,
                window_end=window_end,
                baseline_start=baseline_start,
                baseline_end=baseline_end,
                slice_key=SliceKey(endpoint=endpoint, backend_service=backend),
                rules=rules,
                filters=filters,
            )
        )
    return verdicts


# ---------------------------------------------------------------------------
# Selection -- deliberately separate from the gate
#
# The gate judges a slice. Selection ranks slices that have already been
# judged. Keeping them apart is what lets an agent ask "is /login elevated?"
# about one specific slice without the module first deciding for itself which
# slice is interesting.
# ---------------------------------------------------------------------------

def rank_verdicts(verdicts: Sequence[Verdict]) -> list:
    """Verdicts sorted by 5xx rate, highest first.

    Plain sorting on one visible number. No weighted or composite score: a
    composite hides the arithmetic that produced the ranking and cannot be
    checked against the table or the charts.
    """
    return sorted(verdicts, key=lambda v: v.rate, reverse=True)


def select_suspect(verdicts: Sequence[Verdict]) -> Optional[Verdict]:
    """The highest-rate slice that cleared the evidence bar, or None."""
    qualifying = [v for v in verdicts if v.status == EVIDENCE_SUFFICIENT]
    return rank_verdicts(qualifying)[0] if qualifying else None


def select_closest_candidate(verdicts: Sequence[Verdict]) -> Optional[Verdict]:
    """The slice worth explaining when nothing cleared the gate.

    Ranked purely by 5xx rate, ACROSS both remaining statuses. An earlier
    version preferred a slice that had been evaluated and fell short, on the
    grounds that a real suppression is the more interesting story. That was
    wrong, and the mobile-app filter proved it: mobile-app's /checkout runs at
    3.6% during the incident but cannot be judged (its consumer-sliced baseline
    is too thin), so preferring an evaluated 0.4% endpoint put a green tick on
    the page in the middle of a live outage.

    If the worst thing in the window cannot be judged, that is the headline.
    Showing something quieter instead is the exact conflation the NOT EVALUABLE
    status exists to prevent.
    """
    candidates = [
        v for v in verdicts
        if v.status in (EVIDENCE_INSUFFICIENT, NOT_EVALUABLE)
    ]
    return rank_verdicts(candidates)[0] if candidates else None


def summarise_statuses(verdicts: Sequence[Verdict]) -> dict:
    """How many slices landed in each status. Used to caption the brief.

    A headline about one slice is not a picture of the window: a user needs to
    know how many pairs were judged and how many could not be.
    """
    return {
        status: sum(1 for v in verdicts if v.status == status)
        for status in (EVIDENCE_SUFFICIENT, EVIDENCE_INSUFFICIENT, NOT_EVALUABLE)
    }


# ---------------------------------------------------------------------------
# Rendering the verdict as words
#
# Separate, pure, and downstream of everything above: it reads Verdict fields
# and the rule labels, and interpolates. No hardcoded verdict sentences, so
# changing a threshold in the config changes the prose automatically. And no
# confidence percentage -- only counts, rates over a stated denominator, and
# ratios of two numbers that are themselves displayed.
# ---------------------------------------------------------------------------

def _check_by_rule(verdict: Verdict, rule: str) -> RuleCheck:
    """The recorded check for one rule. Thresholds are read from the Verdict,
    not from the module defaults, so a custom rule set is reported accurately."""
    for check in verdict.checks:
        if check.rule == rule:
            return check
    raise KeyError(f"Verdict carries no check for rule {rule!r}")


def _format_value(value, unit) -> str:
    if value is None:
        return "not measurable"
    if unit == "rate":
        return f"{value * 100:.2f}%"
    if unit == "ratio":
        return f"{value:.1f}x"
    return f"{int(value):,}"


def _describe_check(check: RuleCheck) -> str:
    """One failing rule as a phrase: what was needed, and what was there."""
    needed = _format_value(check.threshold, check.unit)
    if not check.evaluated:
        return f"{check.label} could not be measured (needs {needed})"
    seen = _format_value(check.observed, check.unit)
    return f"{check.label} {seen}, below the required {needed}"


def _join(phrases: Sequence[str]) -> str:
    phrases = list(phrases)
    if len(phrases) == 1:
        return phrases[0]
    return "; ".join(phrases[:-1]) + "; and " + phrases[-1]


def describe_verdict(verdict: Verdict) -> VerdictText:
    """Build the headline and sentence for one Verdict.

    Every failing rule is named, in config order, rather than a single generic
    "insufficient evidence" -- a user who cannot see which rule bit cannot tell
    a noisy endpoint from an unmeasured one, and cannot tell what would change
    the answer.
    """
    label = verdict.slice_key.label
    counts = (
        f"`{label}` recorded {verdict.failures:,} failures across "
        f"{verdict.requests:,} requests "
        f"({verdict.rate * 100:.2f}% 5xx rate)"
    )
    baseline_period = (
        f"{verdict.baseline_start:%H:%M}-{verdict.baseline_end:%H:%M}"
    )

    if verdict.status == EVIDENCE_SUFFICIENT:
        # Read the floor off the verdict's own recorded check rather than the
        # module default, so a caller who passed a custom rule set gets the
        # threshold that was actually applied.
        floor = _check_by_rule(verdict, "minimum_5xx_rate").threshold
        detail = (
            f"{counts}, a rate {verdict.baseline_multiplier:.1f}x its matching "
            f"baseline of {verdict.baseline_rate * 100:.2f}% "
            f"({verdict.baseline_failures:,} failures across "
            f"{verdict.baseline_requests:,} requests, {baseline_period}). "
            f"The {floor * 100:.1f}% rate floor was breached in "
            f"{verdict.longest_breach_run} consecutive 5-minute buckets "
            f"({verdict.buckets_breaching} of {verdict.buckets_evaluated} "
            f"buckets holding requests)."
        )
        return VerdictText("Evidence threshold met", detail)

    if verdict.status == NOT_EVALUABLE:
        # Report ONLY the preconditions that blocked evaluation. The evidence
        # rules were never really applied to this slice -- listing them would
        # imply the slice was tested and found wanting, which is the exact
        # conflation this verdict exists to prevent.
        blockers = [c for c in verdict.failed_checks if c.is_precondition]
        detail = (
            f"{counts}. Not evaluable: {_join([_describe_check(c) for c in blockers])}. "
            f"This is not a clean bill of health -- the slice cannot be judged "
            f"against this rule set, so no claim is made about it either way."
        )
        return VerdictText("Not evaluable", detail)

    reasons = _join([_describe_check(c) for c in verdict.failed_checks])
    detail = (
        f"{counts}, against a matching baseline of "
        f"{verdict.baseline_rate * 100:.2f}% ({baseline_period}). "
        f"Evidence insufficient: {reasons}."
    )
    return VerdictText("No elevated incident signal", detail)


def verdicts_to_frame(verdicts: Sequence[Verdict]) -> pd.DataFrame:
    """Verdicts as a DataFrame, one row per slice, for tabular display.

    Carries the baseline rate and multiplier alongside the status, so the
    status column traces to numbers visible in the same row rather than to an
    invisible calculation.
    """
    return pd.DataFrame([
        {
            "endpoint": v.slice_key.endpoint,
            "backend_service": v.slice_key.backend_service,
            "requests": v.requests,
            "failed_requests": v.failures,
            "error_rate_pct": v.rate * 100,
            "baseline_rate_pct": (
                v.baseline_rate * 100 if v.baseline_rate is not None else None
            ),
            "baseline_multiplier": v.baseline_multiplier,
            "breach_run": v.longest_breach_run,
            "evidence_status": v.status,
        }
        for v in rank_verdicts(verdicts)
    ])
