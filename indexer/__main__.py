"""Indexer entrypoint: `python -m indexer`.

Runs on the host next to the NAS, on a nightly cron, as the read-only
service account. Separate from the web app on purpose - the app must not
be the thing that decides to walk 50 GB, and the indexer must not need an
HTTP port.

    python -m indexer --census      # layer 1 only, then print the file census
    python -m indexer               # census + content index
    python -m indexer --reindex     # rebuild the vector store from scratch
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

import rag  # noqa: E402
from indexer import crawl  # noqa: E402
from pipeline import health  # noqa: E402


def run_crawl(root, connection, verbose=True):
    started = time.time()
    errors = []

    def note(path, error):
        errors.append((path, error))
        if verbose and len(errors) <= 20:
            print(f"  skipped {path}: {error}", file=sys.stderr)

    stats = crawl.crawl(root, connection, on_error=note)
    elapsed = time.time() - started

    rag.log_event({"event": "crawl", "root": root, "elapsed_s": round(elapsed, 1), **stats})
    if verbose:
        print(f"Census: {stats['scanned']:,} files scanned in {elapsed:.0f}s "
              f"({stats['added']} new, {stats['updated']} updated, "
              f"{stats['removed']} removed, {stats['errors']} unreadable).")
    return stats


# Off by default and never implied by another flag: this is the only part
# of indexing that sends document text off the network, and it does so
# under the indexer's account rather than any one user's.
def run_summaries(connection, verbose=True):
    from langchain_anthropic import ChatAnthropic

    from indexer import summarize

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Skipping summaries: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return None

    llm = ChatAnthropic(model=summarize.SUMMARY_MODEL, max_tokens=200)
    stats = summarize.summarize_folders(connection, llm)
    rag.log_event({"event": "summaries", **stats})
    if verbose:
        print(f"Summaries: {stats['written']} written, {stats['skipped']} unchanged, "
              f"{stats['failed']} failed, {stats['removed']} removed.")
    return stats


# Seconds until the next occurrence of HH:MM in local time. Kept in Python
# rather than a shell one-liner because the container's shell, its `date`
# implementation and YAML quoting are three things that can each silently
# break a schedule nobody looks at until the index is a week stale.
def seconds_until(target, now=None):
    from datetime import datetime, timedelta

    now = now or datetime.now()
    hour, minute = (int(part) for part in target.split(":"))
    nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return max(1, int((nxt - now).total_seconds()))


def main(argv=None):
    load_dotenv()

    parser = argparse.ArgumentParser(description="Index the NAS share")
    parser.add_argument("--root", default=rag.DOCS_PATH,
                        help="directory to index (default: RAG_DOCS_PATH)")
    parser.add_argument("--census", action="store_true",
                        help="crawl and report file counts only; no embedding")
    parser.add_argument("--reindex", action="store_true",
                        help="delete and rebuild the vector store")
    parser.add_argument("--loop", action="store_true",
                        help="index once, then repeat every night at --at")
    parser.add_argument("--at", default=os.environ.get("RAG_INDEX_AT", "02:00"),
                        help="local time to run the nightly pass (HH:MM)")
    parser.add_argument("--summaries", action="store_true",
                        help="also generate one-line folder summaries (calls "
                             "the Claude API and sends short excerpts of "
                             "documents, including from folders individual "
                             "users cannot read)")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"{args.root} is not a directory. Is the NAS mounted?", file=sys.stderr)
        return 1

    if not args.census:
        health.write_status(rag.PERSIST_PATH, "running")

    connection = crawl.connect()
    try:
        run_crawl(args.root, connection)

        report = crawl.census(connection)
        print()
        print(crawl.format_census(report))
        rag.log_event({"event": "census",
                       "total_files": report["total_files"],
                       "total_bytes": report["total_bytes"],
                       "indexable_files": report["indexable_files"],
                       "indexable_bytes": report["indexable_bytes"]})

        if args.summaries:
            run_summaries(connection)

        if args.census:
            return 0

        paths = crawl.indexable_paths(connection)
        print(f"\nIndexing {len(paths):,} text-bearing file(s)...")
    finally:
        connection.close()

    # Embeddings are local, so this costs time rather than money; the
    # vector store is opened here (not in the app) so a nightly run never
    # depends on anyone having a browser tab open.
    embeddings = rag.get_embeddings()
    if args.reindex and os.path.isdir(rag.PERSIST_PATH):
        import shutil
        shutil.rmtree(rag.PERSIST_PATH)

    from langchain_chroma import Chroma
    store = Chroma(
        embedding_function=embeddings,
        persist_directory=rag.PERSIST_PATH,
        collection_name="docs",
    )
    rag.sync_vectorstore(store, paths=paths)
    health.write_status(rag.PERSIST_PATH, "ok", files=len(paths))
    return 0


def run_forever(argv, at):
    import time

    while True:
        try:
            main(argv)
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001 - a failed night must not end the loop
            print(f"Indexing run failed: {e}", file=sys.stderr)
            rag.log_event({"event": "index_run_failed", "error": str(e)})
            health.write_status(rag.PERSIST_PATH, "failed", error=str(e)[:500])

        delay = seconds_until(at)
        print(f"Next run at {at} (in {delay // 3600}h {(delay % 3600) // 60}m).")
        time.sleep(delay)


if __name__ == "__main__":
    _args, _rest = None, [a for a in sys.argv[1:] if a != "--loop"]
    if "--loop" in sys.argv[1:]:
        import argparse as _argparse

        _peek = _argparse.ArgumentParser(add_help=False)
        _peek.add_argument("--at", default=os.environ.get("RAG_INDEX_AT", "02:00"))
        _known, _ = _peek.parse_known_args(sys.argv[1:])
        sys.exit(run_forever(_rest, _known.at))
    sys.exit(main())
