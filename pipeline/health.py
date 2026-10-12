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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exit non-zero when the index is stale")
    parser.add_argument("--persist-path", default=os.environ.get("RAG_PERSIST_PATH", "./chroma_db"))
    parser.add_argument("--max-age-hours", type=float, default=MAX_AGE_HOURS)
    args = parser.parse_args(argv)
    healthy, message = check(args.persist_path, args.max_age_hours)
    print(message)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
