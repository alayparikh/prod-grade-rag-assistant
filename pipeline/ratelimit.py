"""Request rate limit, keyed on the asker.

Keyed on the signed-in user, not the browser session: a per-session limit
resets the moment someone opens a new tab, which is no limit at all.

Behind a two-method interface so the in-process store can be swapped for a
shared one without touching callers. Scale path: more than one app instance
needs RedisRateLimiter (a sorted set per key: ZADD now, ZREMRANGEBYSCORE
older than the window, ZCARD, all in one MULTI) - the in-process version
gives each instance its own budget, so N instances allow N times the limit.
"""
import os
import threading
import time
from collections import deque

MAX_REQUESTS = int(os.environ.get("RAG_RATE_LIMIT_MAX", 30))
WINDOW_SECONDS = int(os.environ.get("RAG_RATE_LIMIT_WINDOW_S", 3600))
# Bounds memory: keys idle for a whole window are dropped when the table
# grows past this.
MAX_KEYS = 100_000


class RateLimiter:
    def allow(self, key):
        """True if `key` may make another request now; records it if so."""
        raise NotImplementedError

    def remaining(self, key):
        raise NotImplementedError


class InProcessRateLimiter(RateLimiter):
    """Sliding window per key. Thread-safe: Streamlit serves sessions from a
    thread pool, so two tabs of one user can call allow() at once."""

    def __init__(self, max_requests=MAX_REQUESTS, window_seconds=WINDOW_SECONDS, clock=time.monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        return hits

    def allow(self, key):
        with self._lock:
            now = self.clock()
            hits = self._recent(key, now)
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > MAX_KEYS:
                self._evict(now)
            return True

    def remaining(self, key):
        with self._lock:
            return self.max_requests - len(self._recent(key, self.clock()))

    def _evict(self, now):
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window_seconds]
        for k in stale:
            del self._hits[k]


_limiter = None
_limiter_lock = threading.Lock()


def get_rate_limiter():
    """One limiter per process (shared by every session)."""
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            _limiter = InProcessRateLimiter()
        return _limiter
