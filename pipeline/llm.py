"""Bounds for every model call.

Every ChatAnthropic in the app is built with `**bounded(max_tokens)`, so no
call can wait forever or retry without limit: a stuck upstream connection or
a 429 storm turns into a typed error the caller already handles
(rag._API_ERRORS), not a hung worker thread.

Kept as a kwargs helper rather than a client factory so the construction
sites stay plain `ChatAnthropic(...)` calls (tests patch them by name).

Scale path: per-tenant spend caps and a shared concurrency limit belong in
front of this - an API gateway or a token-bucket in Redis - not here.
"""
import os

CALL_TIMEOUT_S = float(os.environ.get("RAG_LLM_TIMEOUT_S", 60))
CALL_MAX_RETRIES = int(os.environ.get("RAG_LLM_MAX_RETRIES", 2))


def bounded(max_tokens, timeout=None, max_retries=None):
    """kwargs for ChatAnthropic: token cap, per-call timeout, retry cap.

    Worst-case wall clock for one call is timeout * (1 + max_retries) plus
    backoff, so callers with their own deadline (the agent) pass a smaller
    timeout."""
    return {
        "max_tokens": max_tokens,
        "timeout": CALL_TIMEOUT_S if timeout is None else timeout,
        "max_retries": CALL_MAX_RETRIES if max_retries is None else max_retries,
    }
