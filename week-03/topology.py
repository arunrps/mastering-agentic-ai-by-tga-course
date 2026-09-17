"""
topology.py -- loads and validates the declared service topology.

Real platforms have a service catalog. They do not rediscover their own
architecture from logs every time someone opens a dashboard. topology.json is
that catalog: it declares which backend serves which endpoint, who owns each
one, and which runbook applies.

Like detection.py, this module never imports streamlit and holds no caching
decorator, so it can be imported from a script, a test, or a Week 2 agent tool.

It also deliberately does NOT import detection.py, and detection.py does not
import this. The gate measures what the telemetry actually contains; the
topology declares what should be there. Keeping them independent is what makes
a disagreement between the two visible as drift rather than resolved silently
in favour of whichever module happened to run first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

TOPOLOGY_FILE = Path(__file__).parent / "topology.json"

# Fields every declaration must carry. Checked on load, so a half-filled entry
# fails at startup with a clear message rather than as a KeyError three
# functions deep when someone opens the incident brief.
REQUIRED_ENDPOINT_FIELDS = (
    "backend_service",
    "business_capability",
    "runbook_id",
    "owner_team",
)
REQUIRED_BACKEND_FIELDS = (
    "owner_team",
    "runbook_id",
    "slo_p95_latency_ms",
    "slo_max_5xx_rate_pct",
)


class TopologyError(Exception):
    """Raised when topology.json is missing, malformed, or self-inconsistent.

    Loud on purpose. A topology that references a backend it does not declare
    is a broken catalog, and a dashboard that starts anyway would be asserting
    ownership and runbooks it cannot actually resolve.
    """


# ---------------------------------------------------------------------------
# The loaded topology
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Topology:
    """The declared catalog, after validation."""
    version: str
    platform: str
    region: str
    endpoints: dict
    backends: dict

    # --- resolution -------------------------------------------------------

    def backend_for(self, endpoint: str) -> str:
        """The DECLARED backend for an endpoint.

        This is the call that replaces reading backend_service off the first
        matching row. A row-derived answer is only correct while the mapping
        happens to be 1:1 and while the selected window happens to contain the
        endpoint at all; a declared answer is correct regardless of what the
        user has filtered to.
        """
        entry = self.endpoints.get(endpoint)
        if entry is None:
            raise TopologyError(
                f"Endpoint {endpoint!r} is not declared in topology.json. "
                f"Declared endpoints: {sorted(self.endpoints)}"
            )
        return entry["backend_service"]

    def endpoints_for(self, backend: str) -> list:
        """Every declared endpoint served by a backend, sorted."""
        return sorted(
            name for name, entry in self.endpoints.items()
            if entry["backend_service"] == backend
        )

    def endpoint_meta(self, endpoint: str) -> dict:
        entry = self.endpoints.get(endpoint)
        if entry is None:
            raise TopologyError(
                f"Endpoint {endpoint!r} is not declared in topology.json."
            )
        return dict(entry)

    def backend_meta(self, backend: str) -> dict:
        entry = self.backends.get(backend)
        if entry is None:
            raise TopologyError(
                f"Backend {backend!r} is not declared in topology.json."
            )
        return dict(entry)

    def serves(self, endpoint: str, backend: str) -> bool:
        """Is this endpoint/backend combination declared?

        Lets the app tell a user that /checkout is served by payment-service
        rather than asking them to work out for themselves whether their filter
        selection "goes together".
        """
        entry = self.endpoints.get(endpoint)
        return entry is not None and entry["backend_service"] == backend

    def owner_of(self, endpoint: str) -> str:
        return self.endpoint_meta(endpoint)["owner_team"]

    def runbooks_for(self, endpoint: str) -> dict:
        """Both runbook IDs that apply to an endpoint: its own and its service.

        Returned as a pair rather than one ID because an incident on /checkout
        can be a checkout problem or a payment-service problem, and the Week 2
        corpus will be keyed on both.
        """
        entry = self.endpoint_meta(endpoint)
        backend = entry["backend_service"]
        return {
            "endpoint_runbook": entry["runbook_id"],
            "service_runbook": self.backend_meta(backend)["runbook_id"],
        }

    @property
    def declared_pairs(self) -> set:
        return {
            (name, entry["backend_service"])
            for name, entry in self.endpoints.items()
        }


def load_topology(path: Optional[Path] = None) -> Topology:
    """Read topology.json, validate it, and return it. Raises TopologyError.

    Validation is referential, not just structural: every endpoint's declared
    backend_service must itself be declared in `backends`. A catalog that
    points at a service it does not describe cannot answer "who owns this?",
    which is the whole reason the file exists.
    """
    path = Path(path) if path else TOPOLOGY_FILE

    if not path.exists():
        raise TopologyError(f"topology.json not found at {path}")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise TopologyError(f"topology.json is not valid JSON: {error}") from error

    for section in ("endpoints", "backends"):
        if section not in raw or not isinstance(raw[section], dict):
            raise TopologyError(
                f"topology.json must contain an object named {section!r}."
            )
        if not raw[section]:
            raise TopologyError(f"topology.json declares no {section}.")

    endpoints, backends = raw["endpoints"], raw["backends"]

    problems = []

    for name, entry in endpoints.items():
        missing = [f for f in REQUIRED_ENDPOINT_FIELDS if f not in entry]
        if missing:
            problems.append(f"endpoint {name!r} is missing {missing}")
            continue
        backend = entry["backend_service"]
        if backend not in backends:
            problems.append(
                f"endpoint {name!r} declares backend_service {backend!r}, "
                f"which is not declared in 'backends' "
                f"(declared: {sorted(backends)})"
            )

    for name, entry in backends.items():
        missing = [f for f in REQUIRED_BACKEND_FIELDS if f not in entry]
        if missing:
            problems.append(f"backend {name!r} is missing {missing}")

    # An orphan backend is a warning-shaped thing, not an error: a service can
    # legitimately exist with no endpoint routed to it yet. It is surfaced by
    # the CSV cross-check instead, where the reader can see it next to the
    # traffic that does or does not exist.

    if problems:
        raise TopologyError(
            "topology.json is self-inconsistent:\n  - " + "\n  - ".join(problems)
        )

    return Topology(
        version=raw.get("version", "unversioned"),
        platform=raw.get("platform", "unknown"),
        region=raw.get("region", "unknown"),
        endpoints=endpoints,
        backends=backends,
    )


# ---------------------------------------------------------------------------
# Cross-check against observed traffic
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TopologyDrift:
    """Differences between the declared catalog and the observed telemetry.

    Drift is reported, never raised. A gap between what a platform says about
    itself and what its traffic actually does is an operational signal in its
    own right -- an undeclared endpoint in production is exactly the thing you
    want a dashboard to tell you about, not the thing you want it to crash on.
    """
    undeclared_pairs: tuple = ()       # observed in the CSV, absent from topology
    unobserved_pairs: tuple = ()       # declared in topology, absent from the CSV
    mismatched_endpoints: tuple = ()   # declared under one backend, seen under another
    undeclared_backends: tuple = ()
    unobserved_backends: tuple = ()

    @property
    def has_drift(self) -> bool:
        return bool(
            self.undeclared_pairs or self.unobserved_pairs
            or self.mismatched_endpoints or self.undeclared_backends
            or self.unobserved_backends
        )

    def messages(self) -> list:
        """One plain sentence per kind of drift found, for display or logging."""
        lines = []
        for endpoint, backend in self.undeclared_pairs:
            lines.append(
                f"`{endpoint}` served by `{backend}` appears in the telemetry "
                f"but is not declared in topology.json."
            )
        for endpoint, backend in self.unobserved_pairs:
            lines.append(
                f"`{endpoint}` is declared as served by `{backend}` but no such "
                f"traffic appears in the dataset."
            )
        for endpoint, declared, observed in self.mismatched_endpoints:
            lines.append(
                f"`{endpoint}` is declared under `{declared}` but was "
                f"observed under `{observed}`. The declaration is wrong, not "
                f"merely incomplete."
            )
        for backend in self.undeclared_backends:
            lines.append(
                f"Backend `{backend}` appears in the telemetry but is not "
                f"declared in topology.json."
            )
        for backend in self.unobserved_backends:
            lines.append(
                f"Backend `{backend}` is declared but carries no traffic in "
                f"this dataset."
            )
        return lines


def cross_check(topology: Topology, logs: pd.DataFrame) -> TopologyDrift:
    """Compare the declared catalog against the endpoint/backend pairs in logs.

    IMPORTANT: pass the FULL dataset, not a filtered frame. Cross-checking a
    filtered window would report every endpoint the user happened to filter out
    as "declared but not observed", which is noise rather than drift.
    """
    observed_pairs = set(
        map(tuple, logs[["endpoint", "backend_service"]].drop_duplicates().values)
    )
    declared_pairs = topology.declared_pairs

    observed_backends = set(logs["backend_service"].unique())
    declared_backends = set(topology.backends)

    # An endpoint declared under one backend but also seen under another. This
    # is reported separately from a plain undeclared pair, because it means the
    # declaration is WRONG rather than merely incomplete -- and it is the case
    # that will appear once an endpoint is served by more than one backend.
    mismatched = []
    for endpoint, backend in sorted(observed_pairs):
        declared = topology.endpoints.get(endpoint, {}).get("backend_service")
        if declared is not None and declared != backend:
            mismatched.append((endpoint, declared, backend))

    mismatched_endpoints = {m[0] for m in mismatched}

    return TopologyDrift(
        undeclared_pairs=tuple(sorted(
            pair for pair in observed_pairs - declared_pairs
            if pair[0] not in mismatched_endpoints
        )),
        # Mismatched endpoints are excluded here too. Reporting "/refunds is
        # declared under payment-service but no such traffic exists" alongside
        # "/refunds was observed under inventory-service" is the same fact
        # twice, and the second sentence is the useful one.
        unobserved_pairs=tuple(sorted(
            pair for pair in declared_pairs - observed_pairs
            if pair[0] not in mismatched_endpoints
        )),
        mismatched_endpoints=tuple(mismatched),
        undeclared_backends=tuple(sorted(observed_backends - declared_backends)),
        unobserved_backends=tuple(sorted(declared_backends - observed_backends)),
    )
