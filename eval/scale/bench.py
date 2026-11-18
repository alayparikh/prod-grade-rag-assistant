"""Scale benchmarks: indexing and querying as the corpus grows.

    python eval/scale/bench.py index --files 2000
    python eval/scale/bench.py query --sizes 500,5000
    python eval/scale/bench.py all --files 1000 --sizes 300,3000 --report out.json

`index` generates a corpus (eval/scale/make_corpus.py), then measures:
  - crawl rate (files/s) and full-index rate (files/s, chunks/s), peak RSS
  - a no-op re-run: nothing re-embedded, manifest untouched (answer cache kept)
  - a 1% change: only the changed files re-embedded
  - a run killed half-way: the next run re-embeds only what was not
    checkpointed

`query` builds an index per size and measures retriever build time, query
p50/p95, needle hit rate (the keyword half must find a unique token), and
the Python heap peak while building and querying. The peak must not grow in
proportion to the corpus: that is the check that catches "loaded every chunk
id into memory" before it reaches production.

Embeddings default to a deterministic fake (hash -> vector): the point is
the pipeline's own cost and memory shape, not the model's. --real-embeddings
uses the configured model and measures embedding throughput, which is what
sizes the indexer hardware (see PRODUCTION_READINESS.md).

Exit status 1 when a check fails, so CI can run it at small sizes.
"""
import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import time
import tracemalloc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import make_corpus  # noqa: E402

rag = None  # imported after the environment points it at the work dir


def peak_rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / 1e6 if sys.platform == "darwin" else peak / 1e3, 1)  # bytes on macOS, KB on Linux


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    return values[max(1, -(-p * len(values) // 100)) - 1]


def point_rag_at(persist):
    """What tests/conftest.py does: every path rag resolves follows persist."""
    os.makedirs(persist, exist_ok=True)
    os.environ["RAG_PERSIST_PATH"] = persist
    rag.PERSIST_PATH = persist
    rag.MANIFEST_PATH = os.path.join(persist, "manifest.json")


def embeddings(real):
    if real:
        return rag.get_embeddings()
    from langchain_core.embeddings import DeterministicFakeEmbedding
    return DeterministicFakeEmbedding(size=384)


class CountingStore:
    """Wraps the vector store to count which files were (re-)embedded."""

    def __init__(self, store):
        self.store = store
        self._collection = store._collection
        self.sources = set()

    def delete(self, **kwargs):
        return self.store.delete(**kwargs)

    def add_documents(self, chunks):
        self.sources.update(c.metadata.get("source") for c in chunks)
        return self.store.add_documents(chunks)

    def get(self, **kwargs):
        return self.store.get(**kwargs)

    def as_retriever(self, **kwargs):
        return self.store.as_retriever(**kwargs)


def open_store(persist, emb):
    from langchain_chroma import Chroma
    return CountingStore(Chroma(embedding_function=emb, persist_directory=persist, collection_name="docs"))


def corpus_paths(root):
    for folder, _, names in os.walk(root):
        for name in names:
            yield os.path.join(folder, name)


def build(workdir, files, emb, name="index"):
    corpus = os.path.join(workdir, f"corpus_{files}")
    if not os.path.isdir(corpus):
        make_corpus.write(corpus, files)
    persist = os.path.join(workdir, f"{name}_{files}")
    point_rag_at(persist)
    store = open_store(persist, emb)
    paths = sorted(corpus_paths(corpus))
    started = time.perf_counter()
    rag.sync_vectorstore(store, paths=paths)
    return store, corpus, paths, time.perf_counter() - started


def bench_index(workdir, files, emb):
    from indexer import crawl

    out = {"files": files}
    corpus = os.path.join(workdir, f"corpus_{files}")
    started = time.perf_counter()
    out["corpus_mb"] = round(make_corpus.write(corpus, files) / 1e6, 1)
    out["generate_s"] = round(time.perf_counter() - started, 2)

    connection = crawl.connect(os.path.join(workdir, "meta.sqlite"))
    started = time.perf_counter()
    stats = crawl.crawl(corpus, connection)
    connection.close()
    crawl_s = time.perf_counter() - started
    out["crawl_files_per_s"] = round(stats["scanned"] / crawl_s)

    store, _, paths, full_s = build(workdir, files, emb)
    chunks = store._collection.count()
    out.update(full_index_s=round(full_s, 2), files_per_s=round(files / full_s, 1),
               chunks=chunks, chunks_per_s=round(chunks / full_s, 1), peak_rss_mb=peak_rss_mb())

    # No-op re-run: nothing re-embedded, and the manifest (the answer cache's
    # index version) is not rewritten.
    before = os.stat(rag.MANIFEST_PATH).st_mtime_ns
    store.sources.clear()
    started = time.perf_counter()
    rag.sync_vectorstore(store, paths=paths)
    out["noop_rerun_s"] = round(time.perf_counter() - started, 2)
    out["noop_reembedded"] = len(store.sources)
    out["noop_manifest_untouched"] = os.stat(rag.MANIFEST_PATH).st_mtime_ns == before

    # 1% of files change: only those are re-embedded.
    changed = paths[::100]
    for path in changed:
        with open(path, "a") as f:
            f.write("\nAmended.\n")
    store.sources.clear()
    started = time.perf_counter()
    rag.sync_vectorstore(store, paths=paths)
    out["incremental_s"] = round(time.perf_counter() - started, 2)
    out["incremental_changed"] = len(changed)
    out["incremental_reembedded"] = len(store.sources)

    # Killed half-way, then resumed.
    resume_dir = os.path.join(workdir, f"resume_{files}")
    point_rag_at(resume_dir)
    store = open_store(resume_dir, emb)
    real_load, loaded = rag.load_file, []
    checkpoint = rag.MANIFEST_CHECKPOINT_EVERY
    rag.MANIFEST_CHECKPOINT_EVERY = max(1, files // 20)

    def dies_half_way(path):
        if len(loaded) >= files // 2:
            raise KeyboardInterrupt("simulated kill")
        loaded.append(path)
        return real_load(path)

    rag.load_file = dies_half_way
    try:
        rag.sync_vectorstore(store, paths=paths)
    except KeyboardInterrupt:
        pass
    finally:
        rag.load_file = real_load
    checkpointed = len(rag.load_manifest())
    store.sources.clear()
    rag.sync_vectorstore(store, paths=paths)
    rag.MANIFEST_CHECKPOINT_EVERY = checkpoint
    out["resume_done_before_kill"] = len(loaded)
    out["resume_checkpointed"] = checkpointed
    out["resume_reembedded"] = len(store.sources)
    out["peak_rss_mb"] = peak_rss_mb()
    return out


def check_index(result):
    problems = []
    if result["noop_reembedded"]:
        problems.append(f"no-op re-run re-embedded {result['noop_reembedded']} files")
    if not result["noop_manifest_untouched"]:
        problems.append("no-op re-run rewrote the manifest (invalidates the answer cache)")
    if result["incremental_reembedded"] != result["incremental_changed"]:
        problems.append(f"1% change re-embedded {result['incremental_reembedded']} files, "
                        f"expected {result['incremental_changed']}")
    expected = result["files"] - result["resume_checkpointed"]
    if result["resume_reembedded"] != expected:
        problems.append(f"resume re-embedded {result['resume_reembedded']}, expected {expected}")
    if result["resume_checkpointed"] == 0:
        problems.append("killed run checkpointed nothing")
    return problems


def dir_mb(path):
    total = 0
    for folder, _, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass
    return round(total / 1e6, 1)


def bench_query(workdir, size, emb, num_queries=40):
    store, _, _, index_s = build(workdir, size, emb, name="query")
    persist = rag.PERSIST_PATH
    keyword_mb = round(os.path.getsize(os.path.join(persist, "chunks.sqlite")) / 1e6, 1)
    disk = {"index_disk_mb": dir_mb(persist), "keyword_index_mb": keyword_mb}
    tracemalloc.start()
    tracemalloc.reset_peak()
    started = time.perf_counter()
    retriever = rag.build_retriever(store)
    build_ms = (time.perf_counter() - started) * 1000
    step = max(1, size // num_queries)
    targets = list(range(0, size, step))[:num_queries]
    latencies, hits = [], 0
    for i in targets:
        token = make_corpus.needle(i)
        started = time.perf_counter()
        docs = retriever.invoke(f"Who owns reference {token}?")
        latencies.append((time.perf_counter() - started) * 1000)
        hits += any(token in d.page_content for d in docs)
    _, py_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "size": size, "chunks": store._collection.count(), "index_s": round(index_s, 2), **disk,
        "retriever_build_ms": round(build_ms, 1),
        "query_p50_ms": round(percentile(latencies, 50), 1),
        "query_p95_ms": round(percentile(latencies, 95), 1),
        "needle_hit_rate": round(hits / len(targets), 3),
        "py_peak_mb": round(py_peak / 1e6, 2), "peak_rss_mb": peak_rss_mb(),
    }


def check_query(results, min_hit_rate, max_growth):
    problems = []
    for r in results:
        if r["needle_hit_rate"] < min_hit_rate:
            problems.append(f"size {r['size']}: needle hit rate {r['needle_hit_rate']} < {min_hit_rate}")
    if len(results) >= 2:
        small, large = results[0], results[-1]
        growth = large["py_peak_mb"] / max(small["py_peak_mb"], 0.01)
        corpus_growth = large["chunks"] / max(small["chunks"], 1)
        if growth > max_growth:
            problems.append(f"query-path heap grew {growth:.1f}x for {corpus_growth:.0f}x the corpus "
                            f"(allowed {max_growth}x): something loads the corpus per query")
    return problems


def main():
    parser = argparse.ArgumentParser(description="Scale benchmarks for indexing and retrieval")
    parser.add_argument("what", choices=["index", "query", "all"])
    parser.add_argument("--files", type=int, default=1000, help="corpus size for `index`")
    parser.add_argument("--sizes", default="300,3000", help="corpus sizes for `query`, small to large")
    parser.add_argument("--real-embeddings", action="store_true")
    parser.add_argument("--min-hit-rate", type=float, default=0.9)
    parser.add_argument("--max-heap-growth", type=float, default=3.0)
    parser.add_argument("--workdir", help="keep the corpus and indexes here (default: a temp dir, removed)")
    parser.add_argument("--report", help="write the results as JSON here")
    args = parser.parse_args()

    workdir = args.workdir or tempfile.mkdtemp(prefix="rag_bench_")
    os.environ.setdefault("RAG_LOG_PATH", os.path.join(workdir, "events.jsonl"))
    os.environ["RAG_PERMISSIONS_PATH"] = os.path.join(workdir, "no_permissions.yaml")
    global rag
    import rag as _rag
    rag = _rag
    emb = embeddings(args.real_embeddings)

    report, problems = {"embeddings": "real" if args.real_embeddings else "fake"}, []
    try:
        if args.what in ("index", "all"):
            report["index"] = bench_index(workdir, args.files, emb)
            problems += check_index(report["index"])
            print(json.dumps({"index": report["index"]}, indent=2))
        if args.what in ("query", "all"):
            sizes = [int(s) for s in args.sizes.split(",")]
            report["query"] = [bench_query(workdir, s, emb) for s in sizes]
            problems += check_query(report["query"], args.min_hit_rate, args.max_heap_growth)
            print(json.dumps({"query": report["query"]}, indent=2))
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    report["problems"] = problems
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
    for problem in problems:
        print(f"FAIL {problem}")
    print("OK" if not problems else f"{len(problems)} check(s) failed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
