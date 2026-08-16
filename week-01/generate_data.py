"""
generate_data.py — reproducible synthetic API gateway logs for an incident exercise.

Scenario: a fictional e-commerce platform in us-east-1. A deployment of
payment-service v2.4.1 at 13:50 is followed (5 minutes later) by /checkout
latency climbing, then a partial outage from 14:05-14:45, then recovery.
payment-service stays on v2.4.1 through 15:00 -- there is NO rollback, which is
what keeps the deploy a *correlation worth investigating* rather than proof.

MEASUREMENT CONVENTIONS (important -- charts must use the same ones):
  * p95 latency is computed over SUCCESSFUL (2xx) requests only. Failed requests
    get their latency from the failure mechanism (a 504 sits at the gateway
    timeout ceiling), so mixing them in would measure the timeout, not the
    service's real slowness.
  * The primary error metric is 5xx-only. 4xx is client fault (bad password,
    dead link, invalid payload) and is tracked as a separate series.

TIMEZONE: timestamps are naive *local* wall-clock time (no offset written).
The platform is in us-east-1, so read these as America/New_York. 09:00-15:00
local is a normal business-hours window; writing them as UTC would place the
data at 05:00-11:00 ET, which is the wrong six hours for e-commerce traffic.

Standard library only. Run: python3 generate_data.py
"""

import csv
import math
import random
from datetime import date, datetime, time, timedelta

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------

SEED = 42
OUTPUT_FILE = "api_logs.csv"
TOTAL_ROWS = 50_000

# The fictional day. Fixed rather than "today" on purpose: a hardcoded date
# keeps the CSV byte-identical on every run, so screenshots, notebooks and
# write-ups stay consistent with the data instead of drifting each time the
# script is re-run. Only the clock times below define the incident.
SIMULATION_DATE = date(2026, 8, 14)
START_TIME = datetime.combine(SIMULATION_DATE, time(9, 0, 0))
TOTAL_MINUTES = 360          # 09:00 -> 15:00
BUCKET_MINUTES = 5           # the chart bucket size we must be able to support
NUM_BUCKETS = TOTAL_MINUTES // BUCKET_MINUTES   # 72 buckets

# Phase boundaries, expressed as minutes since 09:00. Using minutes (not
# datetimes) for the timeline math keeps the interpolation below readable.
DEPLOY_MINUTE = 290          # 13:50 -- payment-service v2.4.0 -> v2.4.1
EARLY_WARNING_START = 295    # 13:55 -- latency starts climbing (5 min AFTER deploy)
INCIDENT_START = 305         # 14:05 -- errors begin
INCIDENT_END = 345           # 14:45 -- recovery begins

REGION = "us-east-1"

# Strict endpoint -> backend mapping. /refunds is the second payment-service
# endpoint: because payment-service now owns TWO endpoints, a "top suspects"
# table can tell "this backend is sick" apart from "this one endpoint is sick".
BACKEND_OF = {
    "/search":   "catalog-service",
    "/products": "catalog-service",
    "/cart":     "inventory-service",
    "/orders":   "inventory-service",
    "/checkout": "payment-service",
    "/refunds":  "payment-service",
    "/login":    "auth-service",
}

# Both payment-service endpoints degrade together -- same backend, same illness.
PAYMENT_ENDPOINTS = ("/checkout", "/refunds")

# Relative traffic weights. random.choices() normalises these for us, so they
# do not need to add up to 100 (they add up to 102 with /refunds included).
ENDPOINT_WEIGHTS = {
    "/search":   28,
    "/products": 20,
    "/cart":     15,
    "/checkout": 13,
    "/orders":   12,
    "/login":    12,
    "/refunds":   2,
}
# Fixed list order == reproducible weighted draws. Never iterate a set here:
# set ordering varies between runs and would silently break the seed.
ENDPOINTS = list(ENDPOINT_WEIGHTS.keys())

# During the incident, slow checkouts mean clients retry, so the endpoint's
# share of traffic *rises*. This is a volume multiplier only -- we do not model
# individual retry attempts.
CHECKOUT_RETRY_MULTIPLIER = 1.20

FIXED_METHOD = {
    "/search":   "GET",
    "/products": "GET",
    "/orders":   "GET",
    "/checkout": "POST",
    "/refunds":  "POST",
    "/login":    "POST",
}   # /cart is mixed GET/POST -- handled in pick_method()

STABLE_VERSIONS = {
    "catalog-service":   "v3.1.0",
    "inventory-service": "v1.8.3",
    "auth-service":      "v2.0.7",
}
PAYMENT_VERSION_BEFORE = "v2.4.0"
PAYMENT_VERSION_AFTER = "v2.4.1"

# Consumer mix. Two lists only: one global, one for the payment endpoints where
# mobile-app is ~55%. That 55% is the ONLY thing that makes mobile-app the
# most-affected consumer -- it is never given a worse failure rate. Its failure
# *rate* on /checkout is identical to web-app's; only its *count* is larger.
CONSUMERS = ["mobile-app", "web-app", "partner-api", "admin-portal"]
GLOBAL_CONSUMER_WEIGHTS = [45, 35, 14, 6]
# admin-portal is 0 here on purpose: staff tools do not place orders or issue
# self-service refunds. Leaving it at 2% gave it ~11 checkout requests in the
# incident window, and a failure rate over 11 requests is noise that invites a
# wrong conclusion.
PAYMENT_CONSUMER_WEIGHTS = [55, 34, 11, 0]

# --- Latency shape ---------------------------------------------------------
# Latency is drawn from a lognormal distribution: most requests fast, a long
# slow tail. sigma controls how heavy that tail is; mu is then SOLVED so the
# distribution's p95 lands on the target. So p95 is an outcome of the shape,
# not a value we assign to individual rows.
LATENCY_SIGMA = 0.70
SEARCH_SIGMA = 0.75          # search is naturally more variable

BASELINE_P95_MS = {
    "/products": 180,
    "/cart":     160,
    "/orders":   220,
    "/login":    200,
}   # /search jitters per bucket; the payment endpoints follow the curve below

SEARCH_P95_RANGE = (380, 520)   # re-drawn each bucket; sampling noise then
                                # widens the observed p95 to roughly 300-600 ms

# Anchor points for the /checkout (and /refunds) p95 target, as
# (minutes_since_09:00, target_p95_ms). Values BETWEEN anchors are linearly
# interpolated, so the chart shows a curve rather than a staircase.
CHECKOUT_P95_ANCHORS = [
    (0,   250),    # baseline, flat all morning
    (295, 250),    # 13:55 -- degradation begins here, 5 min after the deploy
    (300, 620),    # the climb is steep enough that the 14:00-14:05 bucket
    (305, 880),    # 14:05 -- lands in the 700-900 ms early-warning band
    (320, 2300),   # 14:20 -- incident peak
    (345, 2300),   # 14:45 -- still bad when recovery starts
    (350, 1200),   # latency TAPERS. Connection pools drain and caches refill
    (355, 700),    # gradually, so this decays over ~15 min instead of snapping
    (360, 320),    # 15:00 -- close to, but not exactly back at, baseline
]

# Anchor points for the /checkout 5xx rate. Note the deliberate asymmetry with
# the curve above: errors STOP quickly (the failing path is shed or restarted)
# while latency takes much longer to come home. Real recoveries look like this.
CHECKOUT_5XX_ANCHORS = [
    (0,   0.005),
    (295, 0.005),
    (305, 0.008),  # early warning window: error rate stays near baseline
    (310, 0.190),  # ~19% of payment requests failing
    (345, 0.190),
    (349, 0.020),  # errors collapse within a few minutes
    (353, 0.006),
    (360, 0.005),
]

BASELINE_5XX_RATE = 0.005     # every endpoint except the two below
SEARCH_5XX_RATE = 0.0005      # a floor, not zero: nothing is perfect for 6 hours

# 4xx noise. Realistic client-side failure rates, tracked separately from 5xx.
FOUR_XX_RULES = {
    "/login":    (401, 0.08),   # people mistype passwords
    "/products": (404, 0.02),   # dead links and crawlers
    "/cart":     (400, 0.015),  # invalid payloads
}

HEX_DIGITS = "0123456789abcdef"


# ---------------------------------------------------------------------------
# 2. SMALL HELPERS
# ---------------------------------------------------------------------------

def interpolate(anchors, minute):
    """Linear interpolation between (minute, value) anchor points.

    This is what turns four phase descriptions into a smooth curve. Before the
    first anchor or after the last, we hold the end value flat.
    """
    if minute <= anchors[0][0]:
        return anchors[0][1]
    if minute >= anchors[-1][0]:
        return anchors[-1][1]

    for i in range(len(anchors) - 1):
        start_min, start_val = anchors[i]
        end_min, end_val = anchors[i + 1]
        if start_min <= minute <= end_min:
            span = end_min - start_min
            progress = (minute - start_min) / span
            return start_val + (end_val - start_val) * progress
    return anchors[-1][1]


def lognormal_mu(target_p95, sigma):
    """Solve for mu so the lognormal's p95 equals target_p95.

    For a lognormal:  p95 = exp(mu + 1.645 * sigma)
    Rearranged:       mu  = ln(p95) - 1.645 * sigma
    (1.645 is the 95th-percentile z-score of the standard normal.)
    """
    return math.log(target_p95) - 1.645 * sigma


def make_request_id():
    """A seeded pseudo-random id.

    Deliberately NOT uuid.uuid4(): uuid4 reads from os.urandom and ignores
    random.seed(), so it would make the file different on every run.
    """
    return "req-" + "".join(random.choices(HEX_DIGITS, k=16))


def percentile_95(values):
    """Nearest-rank p95: sort, then take the value at position ceil(0.95 * n)."""
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(0.95 * len(ordered)) - 1
    return ordered[index]


# ---------------------------------------------------------------------------
# 3. PER-REQUEST DECISIONS
# ---------------------------------------------------------------------------

def bucket_request_counts():
    """How many requests fall in each 5-minute bucket.

    Rather than simulating arrival times (hard), we decide a count per bucket
    from a gentle midday hump plus jitter, then scatter that many requests
    inside the bucket. The running-total trick guarantees the counts add up to
    exactly TOTAL_ROWS.
    """
    shares = []
    for i in range(NUM_BUCKETS):
        minute = i * BUCKET_MINUTES
        curve = 1.0 + 0.45 * math.sin(math.pi * minute / TOTAL_MINUTES)
        jitter = random.uniform(0.92, 1.08)
        shares.append(curve * jitter)

    total_share = sum(shares)
    counts = []
    placed = 0
    running = 0.0
    for share in shares:
        running += share / total_share
        target = round(running * TOTAL_ROWS)
        counts.append(target - placed)
        placed = target
    return counts


def endpoint_weights_at(minute):
    """Traffic mix at a point in time, with the incident-window retry bump."""
    weights = []
    for endpoint in ENDPOINTS:
        weight = ENDPOINT_WEIGHTS[endpoint]
        if endpoint == "/checkout" and INCIDENT_START <= minute < INCIDENT_END:
            weight *= CHECKOUT_RETRY_MULTIPLIER
        weights.append(weight)
    return weights


def pick_method(endpoint):
    if endpoint == "/cart":
        return random.choices(["GET", "POST"], weights=[70, 30], k=1)[0]
    return FIXED_METHOD[endpoint]


def pick_consumer(endpoint):
    """Consumer is chosen independently of the response status.

    That independence is the whole point: no consumer is given worse behaviour,
    so any difference in the affected-consumer analysis comes purely from
    traffic share.
    """
    if endpoint in PAYMENT_ENDPOINTS:
        return random.choices(CONSUMERS, weights=PAYMENT_CONSUMER_WEIGHTS, k=1)[0]
    return random.choices(CONSUMERS, weights=GLOBAL_CONSUMER_WEIGHTS, k=1)[0]


def five_xx_rate(endpoint, minute):
    if endpoint in PAYMENT_ENDPOINTS:
        return interpolate(CHECKOUT_5XX_ANCHORS, minute)
    if endpoint == "/search":
        return SEARCH_5XX_RATE
    return BASELINE_5XX_RATE


def target_p95_for(endpoint, minute, search_p95_this_bucket):
    if endpoint in PAYMENT_ENDPOINTS:
        return interpolate(CHECKOUT_P95_ANCHORS, minute)
    if endpoint == "/search":
        return search_p95_this_bucket
    return BASELINE_P95_MS[endpoint]


def pick_status(endpoint, minute):
    """Decide the status code. 5xx is evaluated first, then 4xx, else 200."""
    if random.random() < five_xx_rate(endpoint, minute):
        # When the error rate is elevated the failure MODE changes: a saturated
        # service fast-fails (503, pool exhausted) or times out at the gateway
        # (504). A quiet-hours 5xx is just a random 500/502.
        if five_xx_rate(endpoint, minute) > 0.02:
            return random.choices([503, 504], weights=[60, 40], k=1)[0]
        return random.choices([500, 502], weights=[80, 20], k=1)[0]

    if endpoint in FOUR_XX_RULES:
        code, rate = FOUR_XX_RULES[endpoint]
        if random.random() < rate:
            return code

    return 200


def draw_latency_ms(endpoint, status, minute, search_p95_this_bucket):
    """Latency comes from the failure mechanism, or from the lognormal shape."""
    if status == 503:
        return round(random.uniform(5, 50))          # fast-fail: pool exhausted
    if status == 504:
        return round(random.gauss(3000, 100))        # parked at the timeout ceiling
    if status == 401:
        return round(random.uniform(80, 130))        # password hashing costs ~100 ms
    if 400 <= status < 500:
        return round(random.uniform(5, 40))          # validation rejects are cheap

    # 200s and the occasional 500/502 come from the real latency distribution.
    sigma = SEARCH_SIGMA if endpoint == "/search" else LATENCY_SIGMA
    target = target_p95_for(endpoint, minute, search_p95_this_bucket)
    mu = lognormal_mu(target, sigma)
    return max(1, round(random.lognormvariate(mu, sigma)))


def deployment_version(backend, minute):
    """payment-service flips at 13:50 and NEVER rolls back."""
    if backend == "payment-service":
        if minute >= DEPLOY_MINUTE:
            return PAYMENT_VERSION_AFTER
        return PAYMENT_VERSION_BEFORE
    return STABLE_VERSIONS[backend]


# ---------------------------------------------------------------------------
# 4. GENERATION
# ---------------------------------------------------------------------------

def generate_rows():
    rows = []
    counts = bucket_request_counts()

    for bucket_index, count in enumerate(counts):
        bucket_start_minute = bucket_index * BUCKET_MINUTES

        # /search latency wobbles bucket to bucket. Drawing the target once per
        # bucket (rather than per request) is what makes the *chart line* jitter.
        search_p95 = random.uniform(*SEARCH_P95_RANGE)

        weights = endpoint_weights_at(bucket_start_minute)

        for _ in range(count):
            # Scatter the request anywhere inside the 5-minute bucket.
            offset_seconds = random.uniform(0, BUCKET_MINUTES * 60)
            timestamp = START_TIME + timedelta(
                minutes=bucket_start_minute, seconds=offset_seconds
            )
            minute = bucket_start_minute + offset_seconds / 60.0

            endpoint = random.choices(ENDPOINTS, weights=weights, k=1)[0]
            backend = BACKEND_OF[endpoint]
            status = pick_status(endpoint, minute)

            rows.append({
                "timestamp": timestamp.isoformat(timespec="milliseconds"),
                "request_id": make_request_id(),
                "endpoint": endpoint,
                "http_method": pick_method(endpoint),
                "status_code": status,
                "response_time_ms": draw_latency_ms(
                    endpoint, status, minute, search_p95
                ),
                "consumer": pick_consumer(endpoint),
                "backend_service": backend,
                "deployment_version": deployment_version(backend, minute),
                "region": REGION,
            })

    # Requests inside a bucket were placed at random offsets, so sort at the end.
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def write_csv(rows):
    columns = [
        "timestamp", "request_id", "endpoint", "http_method", "status_code",
        "response_time_ms", "consumer", "backend_service",
        "deployment_version", "region",
    ]
    # newline="" is the documented way to stop csv writing blank lines.
    with open(OUTPUT_FILE, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# 5. VALIDATION -- re-read the file and check it against the spec
# ---------------------------------------------------------------------------

def load_csv():
    """Read back what we actually wrote, not what we think we wrote."""
    with open(OUTPUT_FILE, newline="") as handle:
        records = list(csv.DictReader(handle))
    for record in records:
        record["status_code"] = int(record["status_code"])
        record["response_time_ms"] = int(record["response_time_ms"])
        record["minute"] = (
            datetime.fromisoformat(record["timestamp"]) - START_TIME
        ).total_seconds() / 60.0
    return records


def bucket_label(bucket_index):
    return (START_TIME + timedelta(minutes=bucket_index * BUCKET_MINUTES)).strftime("%H:%M")


def report_buckets(records):
    print("\n=== Per 5-minute bucket ===")
    print("(checkout p95 is over 2xx only; error rates are 5xx-only)\n")
    print(f"{'time':<7}{'reqs':>7}{'ckout':>7}{'ckout p95':>11}"
          f"{'ckout 5xx':>11}{'platform 5xx':>14}")

    for bucket_index in range(NUM_BUCKETS):
        low = bucket_index * BUCKET_MINUTES
        high = low + BUCKET_MINUTES
        in_bucket = [r for r in records if low <= r["minute"] < high]
        if not in_bucket:
            continue

        checkout = [r for r in in_bucket if r["endpoint"] == "/checkout"]
        ok_latencies = [
            r["response_time_ms"] for r in checkout if 200 <= r["status_code"] < 300
        ]
        checkout_5xx = sum(1 for r in checkout if r["status_code"] >= 500)
        platform_5xx = sum(1 for r in in_bucket if r["status_code"] >= 500)

        p95 = percentile_95(ok_latencies)
        checkout_rate = checkout_5xx / len(checkout) if checkout else 0.0

        print(f"{bucket_label(bucket_index):<7}"
              f"{len(in_bucket):>7}"
              f"{len(checkout):>7}"
              f"{(f'{p95} ms' if p95 else '-'):>11}"
              f"{checkout_rate:>10.1%}"
              f"{platform_5xx / len(in_bucket):>14.1%}")


def report_phases(records):
    phases = [
        ("baseline      09:00-13:55", 0, EARLY_WARNING_START),
        ("early warning 13:55-14:05", EARLY_WARNING_START, INCIDENT_START),
        ("incident      14:05-14:45", INCIDENT_START, INCIDENT_END),
        ("recovery      14:45-15:00", INCIDENT_END, TOTAL_MINUTES),
    ]
    print("\n=== Phase summary ===\n")
    print(f"{'phase':<28}{'reqs':>8}{'ckout p95':>11}{'ckout 5xx':>11}"
          f"{'platform 5xx':>14}{'platform 4xx':>14}")

    for name, low, high in phases:
        window = [r for r in records if low <= r["minute"] < high]
        checkout = [r for r in window if r["endpoint"] == "/checkout"]
        ok = [r["response_time_ms"] for r in checkout if 200 <= r["status_code"] < 300]
        p95 = percentile_95(ok)
        c5 = sum(1 for r in checkout if r["status_code"] >= 500)
        p5 = sum(1 for r in window if r["status_code"] >= 500)
        p4 = sum(1 for r in window if 400 <= r["status_code"] < 500)

        print(f"{name:<28}"
              f"{len(window):>8}"
              f"{(f'{p95} ms' if p95 else '-'):>11}"
              f"{(c5 / len(checkout) if checkout else 0):>10.1%}"
              f"{p5 / len(window):>14.1%}"
              f"{p4 / len(window):>14.1%}")


def report_consumers(records):
    """The key check: mobile-app should lead on COUNT but match on RATE."""
    print("\n=== /checkout by consumer, incident window 14:05-14:45 ===\n")
    print(f"{'consumer':<15}{'requests':>10}{'failures':>10}{'fail rate':>12}")

    window = [
        r for r in records
        if INCIDENT_START <= r["minute"] < INCIDENT_END and r["endpoint"] == "/checkout"
    ]
    for consumer in CONSUMERS:
        theirs = [r for r in window if r["consumer"] == consumer]
        if not theirs:
            continue
        failures = sum(1 for r in theirs if r["status_code"] >= 500)
        print(f"{consumer:<15}{len(theirs):>10}{failures:>10}"
              f"{failures / len(theirs):>11.1%}")

    print("\nmobile-app should top the FAILURE COUNT while its failure RATE stays")
    print("in line with the others -- it is hit hardest because it sends the most")
    print("checkout traffic, not because it behaves differently.")


def report_backends(records):
    """Both payment-service endpoints should be sick; everything else healthy."""
    print("\n=== 5xx rate by endpoint, incident window 14:05-14:45 ===\n")
    print(f"{'endpoint':<12}{'backend':<20}{'reqs':>8}{'5xx rate':>11}")

    window = [r for r in records if INCIDENT_START <= r["minute"] < INCIDENT_END]
    for endpoint in ENDPOINTS:
        theirs = [r for r in window if r["endpoint"] == endpoint]
        if not theirs:
            continue
        failures = sum(1 for r in theirs if r["status_code"] >= 500)
        print(f"{endpoint:<12}{BACKEND_OF[endpoint]:<20}{len(theirs):>8}"
              f"{failures / len(theirs):>10.1%}")


# ---------------------------------------------------------------------------
# 6. MAIN
# ---------------------------------------------------------------------------

def main():
    # One seed, set once, before any random call. Every draw below happens in a
    # fixed order in a single-threaded loop, so the file is byte-identical on
    # every run.
    random.seed(SEED)

    rows = generate_rows()
    write_csv(rows)
    print(f"Wrote {len(rows):,} rows to {OUTPUT_FILE}")

    records = load_csv()
    report_buckets(records)
    report_phases(records)
    report_backends(records)
    report_consumers(records)


if __name__ == "__main__":
    main()
