"""Per-question tracing.

Two layers. Step timings are always on and land in the existing event log,
so "why was that answer slow" is answerable from logs/events.jsonl alone.
Langfuse is opt-in: a trace holds the retrieved chunk text and the full
prompt, and this corpus holds personal records, so it must only ever point
at a self-hosted Langfuse on the same network - never the hosted cloud.
"""
import os
import time
from contextlib import contextmanager

TRACING_BACKEND = os.environ.get("RAG_TRACING", "").lower()  # "" or "langfuse"


class StepTimer:
    """Accumulates wall-clock milliseconds per named pipeline step. A step
    that runs twice (retrieval on a retry) is summed, not overwritten."""

    def __init__(self):
        self.steps = {}

    @contextmanager
    def step(self, name):
        started = time.perf_counter()
        try:
            yield
        finally:
            key = f"{name}_ms"
            elapsed = round((time.perf_counter() - started) * 1000)
            self.steps[key] = self.steps.get(key, 0) + elapsed


_handler = None
_handler_loaded = False


# Built once per process. A missing package or unset keys degrade to "no
# tracing" with a single warning rather than failing every question.
def _langfuse_handler():
    global _handler, _handler_loaded
    if _handler_loaded:
        return _handler
    _handler_loaded = True
    if TRACING_BACKEND != "langfuse":
        return None
    if not os.environ.get("LANGFUSE_HOST"):
        # Refuse the SDK's cloud default: see the module docstring.
        print("RAG_TRACING=langfuse but LANGFUSE_HOST is unset; tracing disabled.")
        return None
    try:
        from langfuse.langchain import CallbackHandler
        _handler = CallbackHandler()
    except Exception as e:  # noqa: BLE001 - tracing must never take the app down
        print(f"Langfuse tracing unavailable: {e}")
        _handler = None
    return _handler


def run_config(user=None, session_id=None, tags=None):
    """LangChain config for one question, or None when tracing is off.
    None (not {}) so callers can skip passing config to stubs that do not
    accept it."""
    handler = _langfuse_handler()
    if handler is None:
        return None
    metadata = {}
    if user:
        metadata["langfuse_user_id"] = user
    if session_id:
        metadata["langfuse_session_id"] = session_id
    if tags:
        metadata["langfuse_tags"] = list(tags)
    return {"callbacks": [handler], "metadata": metadata}


def invoke(runnable, inputs, config):
    """Call runnable.invoke, passing config only when there is one."""
    if config is None:
        return runnable.invoke(inputs)
    return runnable.invoke(inputs, config=config)
