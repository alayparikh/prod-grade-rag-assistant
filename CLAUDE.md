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
| Keyword search | SQLite FTS5 on disk (`search/keyword.py`): 2 s query budget, stop words dropped, 32-term cap, per-source delete table | Index past one disk / one writer, or multiple app instances | OpenSearch / Elasticsearch, or Postgres full-text |
| Embeddings | Local MiniLM on CPU | Indexing throughput too low (`eval/scale/bench.py --real-embeddings` measures it) | Batched GPU workers or a self-hosted embedding service |
| Answer cache, rate limit | SQLite cache; in-process per-user rate limit behind `pipeline/ratelimit.py` | More than one app instance | Redis, same interfaces |
| Model calls | `pipeline/llm.bounded()`: per-call timeout, retry cap, token cap on every client | Shared spend across instances or tenants | API gateway or Redis token bucket for per-user / per-tenant spend caps |
| Orders DB | SQLite, read-only, role views, hard SQLite limits (1 MB value, 2 s budget) | Real order volume / concurrency (`eval/load/sql_load.py` measures it) | Postgres read replica or warehouse, read-only role, row-level security, statement_timeout |
| Indexer | Single process; manifest written atomically and checkpointed every 200 files (resumes after a kill) | Corpus too large for one pass | Per-file jobs on a queue (SQS/Kafka/Celery), manifest in a table |
| NL to SQL | One forced tool call + sqlglot guard | Multi-step / mixed questions | Agent loop with `query_orders` / `search_docs` tools, same guards inside each tool (built: `agent.py`, next row) |
| Agent | Opt-in "Ask the agent" mode: bounded tool loop (`agent.py`), no answer cache | Users pick the wrong mode, or agent traffic makes repeat questions costly | Router sends multi-step questions to the agent; answers cached per user + index version + orders snapshot in the shared cache |
| Demo agent answers | Chat panel docked bottom-right (`demo/web/agent.js`); a short reply to a question the agent asked back is joined to it, no other context carried. Saved example runs per role built by `demo/agent_runs.py` (real tools, scripted steps and answers); any other question runs live in the browser with fixed steps (`demo/web/liverun.js`: SQL templates + policy search, no model) | Visitors need questions planned beyond the fixed steps, or follow-ups that depend on earlier turns | Hosted agent endpoint with server-side key, spend cap and rate limit |
| Tracing | JSON logs, optional self-hosted Langfuse | Production traffic | Central log pipeline + self-hosted tracing |
| Health | Liveness (Streamlit), indexer staleness, readiness (`python -m pipeline.health --ready`) | Behind a load balancer | Readiness wired to the LB; SLO alerts on the event log fields |

Keep this table current when a component changes. The failure scenarios
behind each row, and the eval that proves each guard, are in
`PRODUCTION_READINESS.md`; production-scale evals are defined in
`.claude/evals/production.md`.

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
