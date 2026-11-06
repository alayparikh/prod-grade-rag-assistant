# CLAUDE.md

Instructions for AI agents working in this repo. Read this before changing code.

## 1. Use the knowledge graph before reading code

A graphify knowledge graph of the repo lives in `graphify-out/`. Use it instead of
reading the whole codebase.

- Start with `graphify-out/GRAPH_REPORT.md` for the module map, key nodes and communities.
- For questions about how something works or what calls what, run
  `graphify query "<question>"` (or `graphify path "A" "B"`, `graphify explain "X"`).
- Open only the source files the graph points to.
- After adding, removing or restructuring files, refresh it with `/graphify . --update`.
- Gitignored files (`INTERVIEW_NOTES.md`, `ARCHITECTURE.md`, `/docs/`) are not in the
  graph. Read them directly when needed.

## 2. Build for production scale

Treat this as a production system that will hold terabytes of documents and millions
of orders, used by many concurrent users. The current setup is sized for the demo
corpus, but code must not assume the data stays small.

Rules for all code:

- **Never load a whole corpus, table or index into memory.** Stream, paginate, batch.
  Iterate files and rows with generators; use `LIMIT`/cursors, not `fetchall()` on
  unbounded queries.
- **Indexing is incremental and idempotent.** Re-index only changed files (content
  hash / mtime), make every job safe to retry, and design it so it can run as
  per-file jobs on a queue.
- **Keep backends behind interfaces.** Vector store, keyword index, cache, rate limiter,
  database and LLM are accessed through one module each (LangChain interfaces or a thin
  wrapper), so swapping Chroma for pgvector is a config change, not a rewrite.
- **Bound everything.** Every query has a row limit and timeout; every LLM call has a
  token budget, timeout and retry cap; every agent loop has a step cap.
- **Stateless app processes.** No per-process state that must be shared across
  instances (cache, rate limits, sessions); put it behind an interface that can move to
  Redis.
- **Security is enforced outside the model.** Access filtering, the SQL guard, role
  views and read-only connections stay in code and the database, never in the prompt.
  The model never supplies user identity.
- **Measure it.** New pipeline steps log timings, tokens and cost like the existing
  steps, and come with tests plus eval cases (`eval/`).
- **Pick the simplest tool that works now, and note the scale path.** When you choose a
  small-scale option, add a comment or doc line saying what replaces it and when.

### Current choice vs. scale target

| Component | Now (demo scale) | Switch when | Scale target |
|---|---|---|---|
| Vector store | Chroma (embedded) | >1M chunks, multiple app instances, or filtered search at scale | pgvector (if on Postgres) or Qdrant; OpenSearch if already running it |
| Keyword search | In-process BM25 | Index no longer fits in memory | OpenSearch / Elasticsearch, or Postgres full-text |
| Embeddings | Local MiniLM on CPU | Indexing throughput too low | Batched GPU workers or a self-hosted embedding service |
| Answer cache, rate limit | In-process | More than one app instance | Redis |
| Orders DB | SQLite, read-only, role views | Real order volume / concurrency | Postgres read replica or warehouse, read-only role, row-level security |
| Indexer | Single process | Corpus too large for one pass | Per-file jobs on a queue (SQS/Kafka/Celery) |
| NL to SQL | One forced tool call + sqlglot guard | Multi-step / mixed questions | Agent loop with `query_orders` / `search_docs` tools, same guards inside each tool |
| Tracing | JSON logs, optional self-hosted Langfuse | Production traffic | Central log pipeline + self-hosted tracing |

Keep this table current when a component changes.

## 3. Keep docs and UI in sync

Any change that affects architecture, behaviour, data flow, configuration or
measured numbers must update, in the same change:

- [ ] `README.md`: features, architecture, setup, config
- [ ] `INTERVIEW_NOTES.md`: architecture diagram, design decisions, metrics, Q&A
- [ ] `demo/README.md` and the demo UI (`demo/web/`): scroll story text, counts, poses
- [ ] `DEPLOY.md`: if deployment, env vars or services change
- [ ] `eval/fixtures/README.md` and golden sets: if fixtures or expected answers change
- [ ] Section 2 table above: if a component or its scale path changes
- [ ] The knowledge graph: `/graphify . --update`

Numbers in docs (file counts, chunk counts, latency, cost) must come from a real run,
not estimates. If a number can't be re-measured, say so rather than leaving it stale.

## 4. Verify before calling it done

- `pytest` passes.
- Retrieval eval passes (`eval/`); run the live eval for changes to prompts or generation.
- Demo changes: build the index and run the browser check (`demo/check_search.mjs`).
