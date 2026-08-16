"""
app.py -- minimal Streamlit dashboard for the synthetic API gateway logs.

Scope: four headline numbers plus two time-series charts. No filters and no
incident brief yet.

Run with:  streamlit run app.py
"""

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_FILE = "api_logs.csv"

# Charts are bucketed into 5-minute windows. Per-minute buckets would hold only
# ~140 requests each, and a p95 over ~18 successful checkouts is so noisy that
# the incident would be buried in sampling jitter. 5 minutes is the smallest
# window that still gives each point enough samples to be stable, while staying
# fine-grained enough to show the climb, the peak and the recovery separately.
BUCKET_SIZE = "5min"

# Chart colours, taken in fixed slot order from a validated categorical palette.
# Deliberately NOT red for errors: red is reserved for status indicators, and
# reusing it for a data series makes "this line is a series" and "this thing is
# in a bad state" look like the same signal.
COLOR_ERROR_RATE = "#2a78d6"   # slot 1, blue
COLOR_LATENCY = "#eb6834"      # slot 2, orange

# Recessive chart chrome, so the data line is the loudest thing on the page.
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_MUTED = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_AXIS = "#c3c2b7"

# --- Thresholds used by the incident brief ---------------------------------
# An endpoint needs at least this many requests before the brief will name it
# as the suspect. Without it, an endpoint with 2 requests and 1 failure ranks
# top at 50% and the brief reads as confident about pure noise.
MIN_REQUESTS_TO_NAME_SUSPECT = 20

# "Elevated" has to clear BOTH tests. The multiplier alone would flag a jump
# from 0.2% to 0.5% as an incident; the floor alone would flag an endpoint that
# is simply always a little lossy.
ELEVATED_RATE_MULTIPLIER = 2.0   # at least double the baseline rate, and
ELEVATED_RATE_FLOOR_PCT = 1.0    # at least 1% in absolute terms

# How far back to look for a deployment that might relate to the window.
DEPLOY_LOOKBACK_MINUTES = 60


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_logs():
    """Read the CSV once and hand back the same DataFrame afterwards.

    Streamlit re-runs this whole script top to bottom on every interaction --
    every click, every widget change. Without @st.cache_data we would re-read
    and re-parse 50,000 rows each time. The decorator stores the result, so the
    file is read on first load only.

    parse_dates turns the timestamp column into real datetimes rather than
    strings, so later work can filter and group by time.
    """
    return pd.read_csv(DATA_FILE, parse_dates=["timestamp"])


# ---------------------------------------------------------------------------
# The four headline numbers
# ---------------------------------------------------------------------------

def error_rate_5xx(logs):
    """Percentage of requests that returned a 5xx, or None if there are no rows.

    5xx only, deliberately. A 5xx means the server failed; a 4xx means the
    client sent something wrong (bad password, dead link, invalid payload).
    Mixing them would fold routine user mistakes into the failure number and
    hide the real availability signal -- this dataset carries a steady ~1.6%
    4xx baseline that has nothing to do with the incident.
    """
    if logs.empty:
        return None
    server_errors = (logs["status_code"] >= 500).sum()
    return server_errors / len(logs) * 100


def p95_response_time(logs):
    """95th percentile response time, over successful (2xx) requests only.

    Failed requests get their latency from the failure mechanism, not from how
    slow the service actually is: a 504 sits at the gateway timeout ceiling
    (~3,000 ms) and a 503 fast-fails in under 50 ms. Including them would
    measure the timeout setting instead of real user-facing slowness.
    """
    successful = logs[logs["status_code"].between(200, 299)]
    if successful.empty:
        return None   # a filter can leave rows but no successful ones
    return successful["response_time_ms"].quantile(0.95)


def consumers_hit_by_errors(logs):
    """How many distinct consumers saw at least one 5xx."""
    failed_requests = logs[logs["status_code"] >= 500]
    return failed_requests["consumer"].nunique()


# ---------------------------------------------------------------------------
# Time series (one value per 5-minute bucket)
# ---------------------------------------------------------------------------

def error_rate_over_time(logs):
    """5xx rate per 5-minute bucket, as a percentage.

    resample() needs the timestamp as the index -- it then slices the day into
    5-minute windows and applies a calculation to each one.

    The trick here: a True/False column averages straight to a rate, because
    Python counts True as 1 and False as 0. So mean([True, False, False]) is
    0.33, i.e. a 33% error rate. No counting and dividing needed.
    """
    per_request = pd.DataFrame({
        "timestamp": logs["timestamp"],
        "is_server_error": logs["status_code"] >= 500,
    })
    buckets = per_request.set_index("timestamp").resample(BUCKET_SIZE)
    return buckets["is_server_error"].mean() * 100


def p95_over_time(logs):
    """p95 response time per 5-minute bucket, over successful requests only.

    Same 2xx-only reasoning as the KPI card: a 504 sits at the gateway timeout
    ceiling and a 503 fast-fails, so including failures would measure the
    failure mechanism instead of how slow the service really is. That matters
    far more here than in the KPI, because during the incident failures are
    ~19% of checkout traffic rather than a rounding error.
    """
    successful = logs[logs["status_code"].between(200, 299)]
    buckets = successful.set_index("timestamp").resample(BUCKET_SIZE)
    return buckets["response_time_ms"].quantile(0.95)


def build_line_chart(series, title, y_axis_label, line_color, hover_suffix, x_range):
    """Turn one bucketed series into a styled Plotly line chart.

    Written once and called twice so both charts are guaranteed to share the
    same styling and the same x-axis -- which is what makes the two curves
    comparable by eye when they are stacked.
    """
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",   # no dots: 72 markers would crowd the line
            line=dict(color=line_color, width=2),
            hovertemplate="%{x|%H:%M}<br>%{y:.2f}" + hover_suffix + "<extra></extra>",
        )
    )
    figure.update_layout(
        title=dict(text=title, font=dict(size=17, color=COLOR_TEXT)),
        height=300,
        margin=dict(l=60, r=20, t=50, b=45),
        paper_bgcolor=COLOR_SURFACE,
        plot_bgcolor=COLOR_SURFACE,
        font=dict(color=COLOR_MUTED),
        hovermode="x unified",   # crosshair readout, so no dots are needed
        showlegend=False,        # one series per chart -- the title names it
    )
    figure.update_xaxes(
        title=dict(text="Time (local, us-east-1)", font=dict(color=COLOR_TEXT)),
        showgrid=False,
        linecolor=COLOR_AXIS,
        tickformat="%H:%M",
        # Both charts are pinned to the same window rather than each fitting
        # itself to its own data. Otherwise a bucket with no successful
        # requests could make one chart start or end somewhere else, and the
        # two curves would no longer line up when read by eye.
        range=x_range,
    )
    figure.update_yaxes(
        title=dict(text=y_axis_label, font=dict(color=COLOR_TEXT)),
        gridcolor=COLOR_GRID,
        zeroline=False,
        linecolor=COLOR_AXIS,
        rangemode="tozero",   # start at 0 so a spike's size is read honestly
    )
    return figure


# ---------------------------------------------------------------------------
# Top Suspects table
# ---------------------------------------------------------------------------

def top_suspects(logs):
    """One row per endpoint + backend pair, ranked by 5xx error rate.

    Grouping by BOTH columns is deliberate. Two endpoints can sit behind the
    same backend (/checkout and /refunds both hit payment-service), so seeing
    them side by side is what tells you whether one endpoint is broken or the
    whole backend is.

    No weighted "suspect score" here on purpose. A composite number hides the
    arithmetic that produced the ranking, and it cannot be checked against the
    charts. Plain sorting with the supporting columns visible means every
    number on screen traces back to data you can see.
    """
    working = logs.copy()
    working["is_server_error"] = working["status_code"] >= 500

    # groupby(...).agg(...) builds one row per group. "size" counts the rows in
    # the group; "sum" over a True/False column counts the Trues.
    summary = working.groupby(["endpoint", "backend_service"]).agg(
        requests=("is_server_error", "size"),
        failed_requests=("is_server_error", "sum"),
    )
    summary["error_rate_pct"] = summary["failed_requests"] / summary["requests"] * 100

    # p95 needs its own pass, because it is calculated over 2xx rows only while
    # the counts above are over every row. pandas lines the two up by group.
    successful = working[working["status_code"].between(200, 299)]
    summary["p95_ms"] = (
        successful.groupby(["endpoint", "backend_service"])["response_time_ms"]
        .quantile(0.95)
    )

    ranked = summary.sort_values("error_rate_pct", ascending=False)
    return ranked.reset_index()   # turn the grouped keys back into columns


# ---------------------------------------------------------------------------
# Incident brief
#
# Every sentence below is built from a pandas aggregation and an f-string. No
# language model is involved, so the same filters always produce exactly the
# same words, and each number can be checked against the table and charts.
# ---------------------------------------------------------------------------

def baseline_window(all_logs):
    """The quiet reference period, 09:00-13:55 on the day in the data.

    Fixed rather than "whatever is before the selection", so the comparison
    means the same thing no matter what the user has selected.
    """
    day = all_logs["timestamp"].min().normalize()
    return (
        day + pd.Timedelta(hours=9),
        day + pd.Timedelta(hours=13, minutes=55),
    )


def endpoint_error_summary(logs):
    """One row per endpoint: how many requests, how many failed, and the rate.

    agg(["size", "sum", "mean"]) over a True/False column gives all three at
    once: size counts rows, sum counts the Trues, mean is the rate.
    """
    working = logs.assign(is_server_error=logs["status_code"] >= 500)
    return working.groupby("endpoint")["is_server_error"].agg(["size", "sum", "mean"])


def find_suspect_endpoint(logs):
    """The endpoint with the highest 5xx rate, ignoring tiny groups.

    The minimum-requests rule matters: without it, an endpoint with 2 requests
    and 1 failure ranks first at 50% and the brief would confidently name a
    suspect out of noise. Groups below the threshold are simply not eligible
    to be named.
    """
    summary = endpoint_error_summary(logs)
    eligible = summary[summary["size"] >= MIN_REQUESTS_TO_NAME_SUSPECT]
    if eligible.empty:
        return None
    return eligible["mean"].idxmax()


def find_version_change(all_logs, backend, window_start, window_end):
    """The most recent deployment_version change on a backend near the window.

    Read from the UNFILTERED logs on purpose: the deployment history of a
    service is a fact about the service, not about the rows the user selected.
    """
    backend_rows = all_logs[all_logs["backend_service"] == backend]
    first_seen = backend_rows.groupby("deployment_version")["timestamp"].min()
    first_seen = first_seen.sort_values()

    if len(first_seen) < 2:
        return None   # this backend never changed version

    # The earliest version was already running, so it is not a "change".
    # Anything after it counts if it appeared shortly before, or during, the window.
    earliest_of_interest = window_start - pd.Timedelta(minutes=DEPLOY_LOOKBACK_MINUTES)
    changes = first_seen.iloc[1:]
    nearby = changes[(changes >= earliest_of_interest) & (changes <= window_end)]
    if nearby.empty:
        return None

    new_version = nearby.index[-1]
    previous_version = first_seen.index[list(first_seen.index).index(new_version) - 1]
    still_running = backend_rows.sort_values("timestamp")["deployment_version"].iloc[-1]

    return {
        "previous_version": previous_version,
        "new_version": new_version,
        "changed_at": nearby.iloc[-1],
        "rolled_back": still_running != new_version,
    }


def build_incident_brief(window_logs, baseline_logs, all_logs, window_start, window_end):
    """Return (is_elevated, list_of_markdown_lines) describing the selection."""
    lines = []
    window_rate = error_rate_5xx(window_logs)

    lines.append(
        f"**Window examined:** {window_start:%H:%M}-{window_end:%H:%M} "
        f"· {len(window_logs):,} requests · {window_rate:.2f}% 5xx overall"
    )

    suspect = find_suspect_endpoint(window_logs)
    if suspect is None:
        lines.append(
            f"No endpoint has at least {MIN_REQUESTS_TO_NAME_SUSPECT} requests in "
            "this window, which is too little data to name a suspect. Widen the "
            "time range or clear a filter."
        )
        return False, lines

    suspect_rows = window_logs[window_logs["endpoint"] == suspect]
    suspect_rate = error_rate_5xx(suspect_rows)
    baseline_rows = baseline_logs[baseline_logs["endpoint"] == suspect]
    baseline_rate = error_rate_5xx(baseline_rows)

    # "Elevated" needs both tests. The multiplier alone would flag a jump from
    # 0.2% to 0.5% as an incident; the absolute floor alone would flag an
    # endpoint that is simply always a bit lossy.
    is_elevated = suspect_rate >= ELEVATED_RATE_FLOOR_PCT and (
        baseline_rate is None or suspect_rate >= baseline_rate * ELEVATED_RATE_MULTIPLIER
    )

    if not is_elevated:
        lines.append(
            f"**No elevated errors in this window.** The worst endpoint is "
            f"`{suspect}` at {suspect_rate:.2f}% 5xx"
            + (
                f", against a {baseline_rate:.2f}% baseline (09:00-13:55) -- "
                "in line with normal behaviour."
                if baseline_rate is not None
                else " (no baseline data for this selection to compare against)."
            )
        )
        return False, lines

    # --- Suspect endpoint ---
    comparison = (
        f"against {baseline_rate:.2f}% in the 09:00-13:55 baseline"
        if baseline_rate is not None
        else "with no baseline data for this selection"
    )
    if baseline_rate:   # skips both None and 0.0, so we never divide by zero
        comparison += f" ({suspect_rate / baseline_rate:.0f}x higher)"
    lines.append(
        f"**Suspect endpoint:** `{suspect}` at {suspect_rate:.2f}% 5xx, {comparison}."
    )

    # --- Where the failures sit ---
    failures = window_logs[window_logs["status_code"] >= 500]
    backend_counts = failures["backend_service"].value_counts()
    top_backend = backend_counts.index[0]
    lines.append(
        f"**Failures concentrate in:** `{top_backend}` -- "
        f"{backend_counts.iloc[0]:,} of {len(failures):,} failed requests "
        f"({backend_counts.iloc[0] / len(failures) * 100:.0f}%)."
    )

    # --- Most affected consumer ---
    consumer_counts = failures["consumer"].value_counts()
    top_consumer = consumer_counts.index[0]
    consumer_line = (
        f"**Most affected consumer:** `{top_consumer}` with "
        f"{consumer_counts.iloc[0]:,} failed requests "
        f"({consumer_counts.iloc[0] / len(failures) * 100:.0f}% of failures)"
    )

    # The rate comparison is scoped to the suspect endpoint, not the whole
    # window. Across all endpoints a checkout-heavy consumer looks worse simply
    # because it sends more of the traffic that is failing -- comparing like
    # with like is what shows whether the consumer itself is being treated
    # differently. Counts and rates answer different questions, so show both.
    theirs = suspect_rows[suspect_rows["consumer"] == top_consumer]
    others = suspect_rows[suspect_rows["consumer"] != top_consumer]
    their_rate = error_rate_5xx(theirs)
    others_rate = error_rate_5xx(others)
    if their_rate is not None and others_rate is not None:
        consumer_line += (
            f". On `{suspect}` its failure rate is {their_rate:.2f}% against "
            f"{others_rate:.2f}% for other consumers -- so this looks like "
            "traffic share rather than a consumer-specific fault"
        )
    lines.append(consumer_line + ".")

    # --- Latency ---
    suspect_p95 = p95_response_time(suspect_rows)
    baseline_p95 = p95_response_time(baseline_rows)
    latency_line = f"**Latency:** `{suspect}` p95 is {suspect_p95:,.0f} ms"
    if baseline_p95:
        latency_line += (
            f", against {baseline_p95:,.0f} ms at baseline "
            f"({suspect_p95 / baseline_p95:.1f}x higher)"
        )
    lines.append(latency_line + ".")

    # --- Suggested next check ---
    suspect_backend = suspect_rows["backend_service"].iloc[0]
    change = find_version_change(all_logs, suspect_backend, window_start, window_end)
    if change is None:
        lines.append(
            f"**Suggested next check:** no deployment_version change on "
            f"`{suspect_backend}` near this window, so look instead at its "
            "dependencies, resource limits and upstream traffic."
        )
    else:
        changed_at = change["changed_at"]
        when = (
            f"{(window_start - changed_at).total_seconds() / 60:.0f} minutes before "
            "this window opened"
            if changed_at < window_start
            else "during this window"
        )
        next_check = (
            f"**Suggested next check:** `{suspect_backend}` moved from "
            f"`{change['previous_version']}` to `{change['new_version']}` at "
            f"{changed_at:%H:%M}, {when}. That correlates with the onset and is "
            "worth investigating first."
        )
        if not change["rolled_back"]:
            # Recovery without a rollback is the strongest reason to keep saying
            # "suspect" rather than "cause".
            next_check += (
                f" Note the service is still running `{change['new_version']}` at "
                "the end of the data, so the deployment remains a suspect rather "
                "than a confirmed cause."
            )
        lines.append(next_check)

    return True, lines


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

def choices_for(logs, column):
    """Sorted list of the distinct values in a column.

    Sorted so the checkbox order is stable between runs. Never build this from
    a Python set: set ordering can change, and the list would shuffle itself.
    """
    return sorted(logs[column].unique())


def render_sidebar_filters(logs):
    """Draw the sidebar controls and return whatever the user picked.

    This only *collects* the selections -- apply_filters() below does the
    filtering. Keeping the two apart means the filtering logic can be read and
    explained without any Streamlit code in the way.
    """
    st.sidebar.header("Filters")

    # Round the ends out to whole 5-minute marks so the slider reads a clean
    # 09:00 - 15:00 rather than 09:00:00.106 - 14:59:58.
    earliest = logs["timestamp"].min().floor(BUCKET_SIZE).to_pydatetime()
    latest = logs["timestamp"].max().ceil(BUCKET_SIZE).to_pydatetime()

    start_time, end_time = st.sidebar.slider(
        "Time range",
        min_value=earliest,
        max_value=latest,
        value=(earliest, latest),   # default: the whole window
        step=timedelta(minutes=5),  # matches the chart buckets
        format="HH:mm",
    )

    # default=... preselects everything, so the app opens on the full dataset.
    endpoints = st.sidebar.multiselect(
        "Endpoint", choices_for(logs, "endpoint"),
        default=choices_for(logs, "endpoint"),
    )
    backends = st.sidebar.multiselect(
        "Backend service", choices_for(logs, "backend_service"),
        default=choices_for(logs, "backend_service"),
    )
    consumers = st.sidebar.multiselect(
        "Consumer", choices_for(logs, "consumer"),
        default=choices_for(logs, "consumer"),
    )

    return start_time, end_time, endpoints, backends, consumers


def apply_filters(logs, start_time, end_time, endpoints, backends, consumers):
    """Keep only the rows that match every filter.

    Each condition is a column of True/False, and & combines them so a row
    survives only if it passes all four. isin() is the "is this value one of
    the selected ones?" test.
    """
    keep = (
        logs["timestamp"].between(start_time, end_time)
        & logs["endpoint"].isin(endpoints)
        & logs["backend_service"].isin(backends)
        & logs["consumer"].isin(consumers)
    )
    return logs[keep]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.set_page_config(page_title="API Gateway Health", layout="wide")

st.title("API Gateway Health")
st.caption(
    "Synthetic request logs for a fictional e-commerce platform in us-east-1, "
    "09:00-15:00."
)

all_logs = load_logs()

start_time, end_time, endpoints, backends, consumers = render_sidebar_filters(all_logs)
logs = apply_filters(all_logs, start_time, end_time, endpoints, backends, consumers)

# Every filter combination is allowed, including ones that match nothing --
# /checkout with catalog-service, for instance. Stop here with a friendly
# message rather than letting the KPI functions divide by a row count of zero.
if logs.empty:
    st.warning(
        "No requests match the current filters. "
        "Widen the time range, or check whether the selected endpoints and "
        "backend services actually go together."
    )
    st.stop()   # ends the script cleanly, so nothing below runs

st.caption(
    f"Showing **{len(logs):,}** of {len(all_logs):,} requests "
    f"({start_time:%H:%M}-{end_time:%H:%M})."
)

# Everything below reads `logs`, the FILTERED frame, so the cards and both
# charts recompute automatically whenever a filter changes.

# --- Incident brief ----------------------------------------------------------
# The baseline keeps the endpoint/backend/consumer filters but ignores the time
# filter, because the baseline is a fixed period. Reusing apply_filters() means
# the comparison is scoped exactly like the numbers it is compared against.
baseline_start, baseline_end = baseline_window(all_logs)
baseline_logs = apply_filters(
    all_logs, baseline_start, baseline_end, endpoints, backends, consumers
)

is_elevated, brief_lines = build_incident_brief(
    logs, baseline_logs, all_logs, start_time, end_time
)

with st.container(border=True):
    # Icon plus wording, never colour alone, so the state is readable either way.
    st.markdown(
        "#### :warning: Incident Brief" if is_elevated
        else "#### :white_check_mark: Incident Brief -- nothing elevated"
    )
    for line in brief_lines:
        st.markdown(f"- {line}")
    st.caption(
        "Generated from the filtered data by fixed rules -- no language model. "
        "Every figure above also appears in the charts and the Top Suspects table."
    )

# st.columns puts the four cards side by side instead of stacking them.
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total requests", f"{len(logs):,}")
error_rate = error_rate_5xx(logs)
col2.metric("5xx error rate", f"{error_rate:.2f}%")
p95 = p95_response_time(logs)
col3.metric("p95 response time", f"{p95:,.0f} ms" if p95 is not None else "n/a")
col4.metric("Consumers affected", consumers_hit_by_errors(logs))

# --- Charts, stacked vertically so the two curves line up in time ------------
# Two separate charts rather than one chart with two y-axes. A dual-axis chart
# lets you slide the two scales against each other until they appear to agree,
# which invents a correlation the data may not support. Stacked charts sharing
# an x-axis let the eye compare timing without that trap.

st.plotly_chart(
    build_line_chart(
        error_rate_over_time(logs),
        title="5xx error rate over time",
        y_axis_label="5xx error rate (%)",
        line_color=COLOR_ERROR_RATE,
        hover_suffix="%",
        x_range=(start_time, end_time),
    ),
    theme=None,   # keep our own colours instead of Streamlit's plotly theme
)

st.plotly_chart(
    build_line_chart(
        p95_over_time(logs),
        title="p95 response time over time (successful requests only)",
        y_axis_label="p95 response time (ms)",
        line_color=COLOR_LATENCY,
        hover_suffix=" ms",
        x_range=(start_time, end_time),
    ),
    theme=None,
)

# --- Top Suspects ------------------------------------------------------------

st.subheader("Top Suspects")
st.caption(
    "Ranked by 5xx error rate -- an investigation aid, not root-cause analysis. "
    "Read the rate next to the request count: a high rate over a handful of "
    "requests is noise, not a suspect."
)

# The values stay as numbers and column_config only changes how they are
# displayed. Formatting them into strings would break the click-to-sort
# behaviour, because "9.00" sorts before "18.43" alphabetically.
st.dataframe(
    top_suspects(logs),
    hide_index=True,
    column_order=[
        "endpoint", "backend_service", "requests",
        "error_rate_pct", "p95_ms", "failed_requests",
    ],
    column_config={
        "endpoint": "Endpoint",
        "backend_service": "Backend service",
        "requests": st.column_config.NumberColumn("Requests", format="%d"),
        "error_rate_pct": st.column_config.NumberColumn(
            "5xx error rate", format="%.2f%%"
        ),
        "p95_ms": st.column_config.NumberColumn("p95 (2xx only)", format="%.0f ms"),
        "failed_requests": st.column_config.NumberColumn(
            "Failed requests", format="%d"
        ),
    },
)
