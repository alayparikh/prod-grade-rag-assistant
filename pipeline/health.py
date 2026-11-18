"""Indexer heartbeat and staleness checks.

The indexer writes a small status file beside the index after every run.
The app reads it to warn users when answers may be out of date, and the
container healthchecks read it so a silently stalled nightly job shows
up as an unhealthy container instead of a week-old index nobody noticed.

    python -m pipeline.health            # exit 1 if the index is stale
"""
import argparse
import json
import os
import sys
import time

STATUS_FILE = "indexer_status.json"
MAX_AGE_HOURS = float(os.environ.get("RAG_INDEX_MAX_AGE_HOURS", 36))
# A first full index of a large share can take a day or more; while a run
# is in progress the index counts as healthy for this long.
MAX_RUN_HOURS = float(os.environ.get("RAG_INDEX_MAX_RUN_HOURS", 48))


def status_path(persist_path):
    return os.path.join(persist_path, STATUS_FILE)


def read_status(persist_path):
    try:
        with open(status_path(persist_path)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_status(persist_path, state, **info):
    """state is "running", "ok" or "failed". last_success survives a failed
    run so the age reported is that of the data actually being served."""
    status = read_status(persist_path)
    now = time.time()
    status.update(info)
    status["state"] = state
    status["updated"] = now
    if state == "running":
        status["started"] = now
    if state == "ok":
        status["last_success"] = now
        status.pop("error", None)
    os.makedirs(persist_path, exist_ok=True)
    tmp = status_path(persist_path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(status, f)
    os.replace(tmp, status_path(persist_path))  # atomic: readers never see half a file


def check(persist_path, max_age_hours=MAX_AGE_HOURS, now=None):
    """Returns (healthy, message)."""
    now = now or time.time()
    status = read_status(persist_path)
    last_success = status.get("last_success")
    if last_success and now - last_success <= max_age_hours * 3600:
        return True, f"indexed {(now - last_success) / 3600:.1f}h ago"
    if status.get("state") == "running" and now - status.get("started", 0) <= MAX_RUN_HOURS * 3600:
        return True, "first index in progress" if not last_success else "index run in progress"
    if not last_success:
        return False, "the index has never completed a run"
    return False, (f"last successful index was {(now - last_success) / 3600:.0f}h ago"
                   + (f" (last run failed: {status['error']})" if status.get("error") else ""))


def ready(persist_path, orders_db=None):
    """Readiness, as opposed to liveness: can this instance answer a question
    right now? Opens what a question needs - the keyword index and the
    orders database - read-only, with a short timeout. Staleness is not part
    of it: a day-old index still answers, and failing readiness on it would
    take every instance out of the load balancer at once.

    Returns (ready, [problems])."""
    import sqlite3

    problems = []
    chunks = os.environ.get("RAG_CHUNK_DB") or os.path.join(persist_path, "chunks.sqlite")
    try:
        connection = sqlite3.connect(f"file:{chunks}?mode=ro", uri=True, timeout=2)
        try:
            if connection.execute("SELECT 1 FROM chunks_fts LIMIT 1").fetchone() is None:
                problems.append("keyword index is empty")
        finally:
            connection.close()
    except sqlite3.Error as e:
        problems.append(f"keyword index unreadable: {e}")

    if orders_db:
        try:
            connection = sqlite3.connect(f"file:{orders_db}?mode=ro", uri=True, timeout=2)
            try:
                connection.execute("SELECT value FROM meta WHERE key = 'today'").fetchone()
            finally:
                connection.close()
        except sqlite3.Error as e:
            problems.append(f"orders database unreadable: {e}")
    return not problems, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exit non-zero when the index is stale")
    parser.add_argument("--persist-path", default=os.environ.get("RAG_PERSIST_PATH", "./chroma_db"))
    parser.add_argument("--max-age-hours", type=float, default=MAX_AGE_HOURS)
    parser.add_argument("--ready", action="store_true",
                        help="readiness instead: exit 1 unless the index and orders DB open")
    parser.add_argument("--orders-db", default=os.environ.get("RAG_ORDERS_DB"))
    args = parser.parse_args(argv)
    if args.ready:
        orders_db = args.orders_db or os.path.join(args.persist_path, "orders.db")
        ok, problems = ready(args.persist_path, orders_db)
        print("ready" if ok else "; ".join(problems))
        return 0 if ok else 1
    healthy, message = check(args.persist_path, args.max_age_hours)
    print(message)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
