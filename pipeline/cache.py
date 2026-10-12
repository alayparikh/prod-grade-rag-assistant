"""Answer cache.

Exact-match on a normalised question, scoped to one user and one version
of the index. SQLite rather than Redis: one more service on a NAS is a
real cost, and the access pattern is a handful of reads a minute.

Three rules keep it from leaking or going stale:

- The key includes the user. Two users asking the same question can be
  entitled to different answers, so an answer is never shared between
  them.
- The key includes the index version (the manifest's mtime), so any
  re-index - nightly or manual - invalidates every entry without anyone
  having to remember to clear the cache.
- A hit re-runs the caller's access check on every file the answer was
  built from. Permissions revoked on the NAS since the answer was cached
  turn the hit into a miss.

Only first-turn questions are cached: a follow-up's meaning depends on
the conversation before it.
"""
import hashlib
import json
import os
import re
import sqlite3
import time

CACHE_ENABLED = os.environ.get("RAG_CACHE", "1") != "0"
CACHE_TTL_SECONDS = int(os.environ.get("RAG_CACHE_TTL_HOURS", 24)) * 3600


def normalize_question(question):
    text = re.sub(r"\s+", " ", question.strip().lower())
    return text.rstrip("?.! ")


def index_version(manifest_path):
    try:
        return str(os.stat(manifest_path).st_mtime_ns)
    except OSError:
        return "none"


class AnswerCache:
    def __init__(self, path, ttl_seconds=CACHE_TTL_SECONDS):
        self.path = path
        self.ttl_seconds = ttl_seconds
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS answers ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL)")

    # A connection per call: Streamlit serves reruns from a thread pool and
    # sqlite3 connections are not shareable across threads by default.
    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def key(question, user, version, model):
        payload = json.dumps([normalize_question(question), user or "", version, model])
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, key):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value, created FROM answers WHERE key = ?", (key,)).fetchone()
        if row is None or time.time() - row[1] > self.ttl_seconds:
            return None
        return json.loads(row[0])

    def put(self, key, value):
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO answers (key, value, created) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()))
            # Opportunistic expiry keeps the file from growing without a
            # separate cleanup job.
            connection.execute("DELETE FROM answers WHERE created < ?",
                               (time.time() - self.ttl_seconds,))


def still_permitted(entry, access_check):
    if access_check is None:
        return True
    for source in entry.get("context_sources", []):
        try:
            if not access_check(source):
                return False
        except Exception:  # noqa: BLE001 - fail closed, same as live retrieval
            return False
    return True
