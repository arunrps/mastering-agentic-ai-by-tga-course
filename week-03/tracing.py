"""
tracing.py -- LangSmith configuration, deliberately non-load-bearing.

NEVER imports streamlit.

FRAMEWORK: "Observability is instrumented early but never load-bearing... The
application must run correctly with tracing disabled or unreachable."

That sentence is the whole design of this file. Everything here is best-effort:
it reads configuration, reports what it found, and returns. There is no code path
in which a missing key, a bad project name or an unreachable LangSmith endpoint
can fail an investigation. `status()` is how the app shows the user which of those
happened, so a silent absence of traces is visible rather than mysterious.

Configuration order, matching the rest of the project:
  1. environment variables -- what Streamlit Cloud sets, via st.secrets in app.py
  2. ~/llm-class/.env -- the local convenience fallback

Keys are never written to disk by this module and never logged.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

DEFAULT_PROJECT = "triagelens-week-03"
DOTENV = Path.home() / "llm-class" / ".env"

# LangChain has used both spellings. Accept either so a key set under the older
# name is not silently ignored.
KEY_NAMES = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")


def _from_dotenv(name: str) -> Optional[str]:
    if not DOTENV.is_file():
        return None
    try:
        for line in DOTENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _resolve_key() -> tuple:
    """(key, source) or (None, None). Never raises."""
    for name in KEY_NAMES:
        value = os.environ.get(name)
        if value:
            return value, f"environment ({name})"
    for name in KEY_NAMES:
        value = _from_dotenv(name)
        if value:
            return value, f"~/llm-class/.env ({name})"
    return None, None


def configure(project: Optional[str] = None) -> dict:
    """Turn tracing on if a key is available. Returns a status dict either way.

    Called once at start-up. Sets the environment variables the LangChain/
    LangGraph tracer reads; if there is no key it sets LANGSMITH_TRACING=false
    explicitly, because leaving it unset has meant different things across
    versions and an ambiguous default is the thing most likely to produce a
    confusing partial state.
    """
    project = project or os.environ.get("LANGSMITH_PROJECT") or DEFAULT_PROJECT
    key, source = _resolve_key()

    if not key:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return {
            "enabled": False,
            "project": project,
            "reason": (
                "No LANGSMITH_API_KEY or LANGCHAIN_API_KEY found in the environment "
                "or ~/llm-class/.env. Tracing is off; the agent runs normally."
            ),
            "key_source": None,
        }

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    for name in KEY_NAMES:
        os.environ[name] = key

    return {
        "enabled": True,
        "project": project,
        "reason": "Tracing enabled.",
        "key_source": source,
    }


def verify() -> dict:
    """Best-effort reachability check. Never raises, never blocks.

    Distinguishes the three states that matter and that look identical from the
    outside: no key configured, key configured but the service is unreachable or
    rejects it, and working. A missing trace with no explanation is the thing
    that wastes an afternoon.
    """
    status = {"configured": os.environ.get("LANGSMITH_TRACING") == "true",
              "reachable": False, "detail": ""}
    if not status["configured"]:
        status["detail"] = "Tracing not configured; nothing to verify."
        return status

    try:
        from langsmith import Client

        client = Client()
        project = os.environ.get("LANGSMITH_PROJECT", DEFAULT_PROJECT)
        if not client.has_project(project):
            client.create_project(project)
        status["reachable"] = True
        status["detail"] = f"LangSmith reachable; project '{project}' ready."
    except Exception as error:          # noqa: BLE001 -- status, not a failure
        status["detail"] = (
            f"Tracing is configured but LangSmith is not reachable: "
            f"{type(error).__name__}: {str(error)[:160]}. The agent runs normally; "
            f"traces will not appear."
        )
    return status


def traceable(**kwargs):
    """`langsmith.traceable`, or a pass-through decorator if it is unavailable.

    The project rule is that observability can never be load-bearing. A decorator
    imported at module scope would make `import agent` fail when langsmith is
    absent, so the fallback is a no-op that returns the function untouched.
    """
    def decorate(function):
        try:
            from langsmith import traceable as _traceable

            return _traceable(**kwargs)(function)
        except Exception:        # noqa: BLE001 -- absence is not an error here
            return function

    return decorate


def wrap_client(client):
    """Instrument an OpenAI client so its calls appear as child runs.

    The agent deliberately uses the raw OpenAI SDK rather than langchain-openai
    (see agent._client), which means LangChain's automatic tracing does not see
    the model calls. `wrap_openai` restores them without changing the call site.

    Returns the client unchanged if wrapping is unavailable or fails, so a
    tracing problem degrades to "no traces" rather than "no agent".
    """
    if os.environ.get("LANGSMITH_TRACING") != "true":
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:            # noqa: BLE001
        return client


def status_line(configure_result: dict, verify_result: dict) -> str:
    """One line for the UI and the CLI."""
    if not configure_result["enabled"]:
        return f"LangSmith tracing: OFF — {configure_result['reason']}"
    if verify_result["reachable"]:
        return (f"LangSmith tracing: ON — project '{configure_result['project']}', "
                f"key from {configure_result['key_source']}")
    return f"LangSmith tracing: CONFIGURED BUT UNREACHABLE — {verify_result['detail']}"
