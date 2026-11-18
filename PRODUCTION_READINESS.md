# Production readiness

What breaks when a RAG + NL-to-SQL + agent system meets production: hundreds
of terabytes of documents, millions of orders, many people asking at once,
and a model API that rate-limits, times out and can be talked into things.
For each failure: how it shows up, how to detect it, what guards it in this
repo, what replaces that guard at scale, and which eval proves it.

Written to be reused. Sections 2 and 6 apply to any retrieval or agent
system; the "here" column is this repo's answer.

- [1. Verdict](#1-verdict)
- [2. Failure catalogue](#2-failure-catalogue)
- [3. Capacity math for 100 TB](#3-capacity-math-for-100-tb)
- [4. Eval map](#4-eval-map)
- [5. Measured results](#5-measured-results)
- [6. Launch checklist](#6-launch-checklist)
- [7. SLOs and alerts](#7-slos-and-alerts)
- [8. Fixed in this pass](#8-fixed-in-this-pass)
- [9. Known gaps](#9-known-gaps)

---

## 1. Verdict

**Single-site NAS deployment, generated answers off: ready.** Every path is
bounded, fails closed, and is covered by free evals that run on each push.

**The target in this document (100s of TB, many app instances, answers on):
not ready, and not meant to be on this stack.** The guards are in the right
places and are tested, but four components must be swapped first, and each
swap is a config or adapter change because the backends sit behind one
module each:

| Blocker at scale | Why | Replace with |
|---|---|---|
| Embedded Chroma + SQLite FTS on one disk | ~14 TB of index for 100 TB of documents at 1% text yield (section 3); one writer | Qdrant / pgvector (sharded, quantized) + OpenSearch |
| Single-process indexer | 134 days to embed 1.5B chunks on one CPU at the measured rate | Per-file jobs on a queue, GPU embedding workers |
| In-process cache and rate limit, Streamlit session state | Each instance has its own; N instances allow N x the limit | Redis behind the existing interfaces; a stateless API tier |
| SQLite orders DB with temp views | Analytical queries at 200k orders already take 60-300 ms under load | Postgres replica or warehouse, row-level security, statement_timeout |

**The live tier has never run.** The live golden set (`--live --repeat 3`)
and the prompt-injection suite exist but need an API key and spend
approval. Until they run, the claims about model behaviour (groundedness,
refusals, injection resistance) are design claims, not measurements. The
guarantees that do not depend on the model (access, SQL, bounds) are
measured.

Audit scores, for the record: `/ecc:production-audit` about 55/100 before
this pass (risky); `/ecc:harness-audit` 15/39, which scores the Claude Code
configuration rather than the application and does not detect Python test
suites.

---

## 2. Failure catalogue

Columns: **What breaks** and how it shows up · **Detect** (log field, metric,
eval) · **Here** (the guard in this repo) · **At scale** (what replaces it) ·
**Proven by**.

### 2.1 Ingestion at hundreds of terabytes

| What breaks | Detect | Here | At scale | Proven by |
|---|---|---|---|---|
| Nightly crawl never finishes: walking 10^8 files over SMB takes longer than a night | `crawl` event `elapsed_s`; indexer health goes stale after 36 h | `os.scandir` walk, one pass per run; 54k files/s on local SSD (SMB not measured) | Change feeds instead of walks (USN journal, S3 event notifications, inotify); crawl partitioned per top-level folder | `bench.py index`: `crawl_files_per_s` |
| Embedding is the bottleneck | `chunks_per_s` | Local MiniLM on CPU: **129 chunks/s** measured; embedding is ~83% of indexing time | Batched GPU embedding workers or a self-hosted embedding service; size with section 3 | `bench.py index --real-embeddings` |
| A run killed part-way (OOM, deploy, node loss) starts again from zero | `index_run_failed`; manifest unchanged after a long run | Manifest checkpointed every 200 files, written atomically; next run resumes | Per-file jobs on a queue; the manifest becomes a table updated per job | `test_faults.py::TestIndexingResume`; bench `resume_reembedded` = files not checkpointed |
| Retried job duplicates chunks | chunk count grows on re-runs | Delete-by-source before add, so a retried file replaces itself | Deterministic chunk ids (`hash(path, sha256, n)`) and upserts | bench: no-op re-run re-embeds 0 |
| A night with no changes throws away the answer cache | cache hit rate drops to 0 every morning | Manifest (the cache's index version) is only rewritten when something moved | Index version = content-derived (max job sequence), not a file mtime | `test_faults.py`; bench `noop_manifest_untouched` |
| Poison file: 2,000-page scan, zip bomb, malformed PDF that hangs the parser | one file's `loader_error`, or a run that stops progressing | Per-file `try/except`; OCR page cap (50); spreadsheet row cap (2,000) | **Each loader in a subprocess with a time and memory limit** (gap: a hanging parser blocks the run today) | Gap (section 9) |
| Content silently truncated by those caps | none today | Caps are configurable | Log a `truncated` event per file with what was dropped | Gap |
| Deleted file or revoked permission still answerable | `num_dropped_by_acl`; DEPLOY.md check 2 | Per-file access check at question time: a deleted or revoked file fails the check and is dropped, before the nightly index catches up | Same check, with a short per-(user, file) decision cache to bound NAS calls | `test_access_control.py` |
| Embedding-model change mixes old and new vectors | recall drops for files not yet re-embedded | Model change requires `--reindex` (documented) | Blue/green index: build the new one beside the old, run the retrieval eval against it, switch a pointer, keep the old one for rollback | Retrieval eval with `--baseline` on the new index |
| First build serves a partial index | health `state: running`; the app warns users | Health file + staleness warning | Blue/green: never serve an index that has not finished | `pipeline/health.py` tests |
| One huge file dominates a run | one `sync` taking hours | None | Split large files into page/sheet jobs | Gap |
| Near-duplicate documents (copies, versions) crowd out the top k | the same passage cited from five paths | Reranker | Skip files whose sha256 is already indexed; MMR diversity in the final cut | Gap |

### 2.2 Retrieval at scale

| What breaks | Detect | Here | At scale | Proven by |
|---|---|---|---|---|
| Something on the query path loads the corpus into memory | memory climbs with corpus size | Corpus size counted with a cap (`CORPUS_SIZE_CAP`); keyword index on disk; empty check is `LIMIT 1` | Same rule: no unbounded `get()`, ever | `bench.py query` heap check: flat 0.17 MB -> 0.14 MB for 20x the chunks; the pre-fix code grew 7.6x and fails the check |
| No keyword index and a large corpus: the BM25 fallback loads everything | `bm25_fallback_truncated` event | Fallback capped at 50,000 chunks | Fallback removed once OpenSearch is the keyword index | `test_faults.py` |
| Keyword query walks posting lists as long as the index | `keyword_timeout` event | Stop words dropped, 32 terms max, 2 s budget per query | OpenSearch with per-query timeouts and `minimum_should_match` | `test_faults.py::TestKeywordScale` |
| Deleting a changed file's keyword rows scans the whole index | nightly run slows as the index grows | `chunk_sources` table indexed by source; deletes batched 500 per statement | OpenSearch delete-by-query on a keyword field | `test_faults.py` |
| ANN recall collapses under restrictive filters (HNSW filters after the search) | users with narrow access get "I don't know" more often | 3x over-fetch, then the per-file access check | Filter inside the ANN search (Qdrant payload index, pgvector iterative scan), or one partition per access group | Gap: a filtered-recall eval |
| k too small for a large corpus; the right chunk is at rank 40 | MRR and hit@k drop | k scales with corpus (4-20), then the reranker keeps the top 10 | Two-stage retrieval with a larger first stage on a dedicated service | Retrieval eval: MRR 0.967, hit@3 1.0, compared to baseline in CI |
| Reranker CPU saturates the web process | `rerank_ms` rises with concurrency | Cross-encoder on CPU in the app process (~35 ms warm, measured earlier) | Rerank service on GPU, or fewer candidates | Event log `rerank_ms` |
| Per-chunk NAS access check adds a network call per source | `latency_ms` high for users with broad access | One check per distinct source file | Decision cache per (user, file) for a few minutes; ACL tags at index time (`RAG_ACL_TAGGING`) | `test_acl.py` |
| Stale answers served after a document changes | answer differs from the file | Cache keyed on user + question + index version + model; access re-checked on a hit | Same keys in Redis | `test_pipeline.py` |
| Non-English documents | low recall for Hindi/Gujarati questions | MiniLM is English-only (documented) | bge-m3 embeddings and bge-reranker-v2-m3 | Needs a multilingual golden set |

### 2.3 SQL and orders under load

| What breaks | Detect | Here | At scale | Proven by |
|---|---|---|---|---|
| Model-written SQL writes, drops, attaches, reads base tables or system tables | `sql_rejected:*` guardrail | sqlglot parse: one SELECT, views only, no comments, forced LIMIT 50; read-only connection | Same guard, plus a read-only database role | `tests/test_sql_attacks.py`: 30 attacks rejected before running |
| Resource bombs: `zeroblob(9e8)`, `printf('%.*c', 9e8)`, recursive CTEs, 5-way cross joins | `query exceeded the 2s budget`; memory spikes | Dangerous functions denied by name; SQLite hard limits per connection (1 MB per value, 20 KB statement, no ATTACH); 2 s budget via progress handler | `statement_timeout`, `work_mem`, per-role resource groups | 12 "bounded" attack cases; under load all 224 attack queries finished within the budget |
| A role sees rows or columns it should not | — (must never happen) | Temp views rebuilt per question for the asker's role; hidden columns are NULL | Postgres row-level security and column grants, identity from the session | role cases in `test_sql_attacks.py`; `sql_load.py` contractor sentinel: 0 leaks in 2,000 concurrent questions |
| Analytical questions are slow on a large table | `sql_run_ms`; budget timeouts | 2 s budget, LIMIT 50 | Read replica or warehouse; pre-aggregated tables for the common counts; columnar store for scans | `sql_load.py`: at 200k orders, p95 238 ms at 103 q/s |
| "Add an index" makes it slower | p95 rises after a migration | Measured, not assumed | Check `EXPLAIN` on the real workload before adding an index | At 200k orders the reflex index on `(status, promised_by)` made "late orders" 15 -> 142 ms, and the reflex index set cut throughput from 103 to 28 q/s |
| A row filter that filters nothing still costs a plan | — | Roles that see every customer get no child-view filter | RLS policies that are `true` for unrestricted roles | 70 -> 103.5 q/s, p95 544 -> 238 ms at 200k orders after the change |
| Orders DB missing, locked or corrupt | `orders_unavailable:*` guardrail | Order mode answers "unavailable"; the agent drops to documents only; readiness fails | Same, plus replica failover | `test_faults.py::TestOrdersUnavailable` |
| Connection per question + view DDL per question | connection count, `sql_run_ms` | Fine at the measured 103 q/s | Pooled connections (PgBouncer), RLS instead of per-question DDL | `sql_load.py` |
| Replica lag: answers about orders that have since changed | replication lag metric | Fixture has a fixed "today" | Show "data as of" in the answer; alert on lag | Gap |
| Customer names in logged SQL (`LIKE '%Cobalt%'`) | — | SQL text is logged (rows never are) | Log a parameter-stripped fingerprint of the SQL instead | Gap |

### 2.4 Model and agent traffic

| What breaks | Detect | Here | At scale | Proven by |
|---|---|---|---|---|
| 429 storm from the API | `api_error:rate_limit` rate | Every client: retry cap 2, timeout 60 s (`pipeline/llm.py`); typed message to the user | Shared concurrency limit and a queue in front of the API; backoff with jitter; per-tenant quotas | `agent_load.py`: 110 of 110 injected 429s reported as `api_error:rate_limit`, none raised |
| API timeouts | `api_error:timeout` | Per-call timeout; typed message | Same | `agent_load.py`: 56 of 56 |
| Agent loops forever | `step_cap` guardrail | 6 tool calls, then one closing call that can only answer or ask | Same caps, plus a per-question cost cap | `agent_load.py`: 48 runaway models stopped at the cap |
| Slow upstream makes a question take minutes | `latency_ms`, `timeout` guardrail | 60 s deadline checked before every model call and every tool call; worst case is deadline + one call | Deadline propagated as a per-call timeout | `agent_load.py`: 3 s deadline, slowest question 5.42 s (deadline + one 1.8 s call), as designed |
| Token / cost runaway | `input_tokens`, `cost_usd` per event | 60k-token budget per agent question, now including the grading and rewrite calls inside its searches | Per-user and per-tenant spend caps in Redis; hourly spend alert | `test_faults.py::TestAgentBounds` |
| One user floods the service | per-user request counts | 30 questions/hour per user across all tabs and modes; order mode no longer re-asks the model on every page rerun | Same limiter in Redis; queue with per-user fairness | `test_faults.py::TestRateLimit` (50 concurrent requests, exactly 25 allowed) |
| Prompt injection in a document or an order row | answers containing instructions from a document | Context framed as untrusted; **and the real guard is outside the model**: identity bound into tools, role views, SQL guard, access checks, citations filtered to what tools returned | Same | Outside-model guards: `agent_load.py` injected cases (87, 0 leaks). Model behaviour: `eval/adversarial/injection.yaml` (live, **not yet run**) |
| Ungrounded answers | judge failures in the live eval | Structured `sources_used` validated against retrieval; groundedness judge; empty context never reaches the model | Sample production answers into the judge daily | Live eval (not run this pass) |
| Model version change shifts behaviour | eval pass rate | Model ids pinned in code | Run `--live --repeat 3` on the new model; compare to baseline before switching | `run_eval.py --repeat`, `--baseline` |
| Secrets in answers | `secret_redacted` guardrail | High-precision redaction, also mid-stream | Same | `test_units.py` |
| Concurrency mixes users' data | — (must never happen) | Stateless per-question objects; identity bound per call | Same | `agent_load.py`: 1,000 questions on 64 threads, 0 cross-user leaks |

### 2.5 Platform and operations

| What breaks | Detect | Here | At scale | Proven by |
|---|---|---|---|---|
| Process state that must be shared | users see different limits per instance | Cache, rate limit behind interfaces | Redis | Interface tests |
| Streamlit keeps sessions (and the NAS password) in process memory | sticky sessions required | One instance | A stateless API service with SSO tokens; Streamlit only as a thin client | — |
| Load balancer sends traffic to an instance that cannot answer | errors from one instance | `python -m pipeline.health --ready`: index and orders DB open | Readiness probe on the LB | `test_faults.py::TestReadiness` |
| Index stale and nobody notices | `pipeline.health` exit 1 | Indexer container unhealthy after 36 h | Alert on index age | `pipeline/health.py` tests |
| Event log rotates away history | — | Local rotating file, ~50 MB cap | Ship JSON lines to a central log pipeline; at ~1 KB per question, 1M questions/day is ~1 GB/day | — |
| `--reindex` deletes the live index | answers vanish during a rebuild | Documented: copy the volume first (DEPLOY.md) | Blue/green index with a pointer switch | — |
| No rollback for a bad deploy | — | CI gates: tests, retrieval baseline, scale bench, load tests | Canary instance comparing guardrail and latency rates before full rollout | `.github/workflows/ci.yml` |
| Secrets in files | — | `.env` git-ignored; no secrets in tracked files | Secret manager | — |
| Traces leak document text to a third party | — | Langfuse refuses to start without a self-hosted host | Same | `pipeline/tracing.py` |

---

## 3. Capacity math for 100 TB

The rates are measured (section 5). The **text yield is an assumption**: replace
it with the census numbers (`python -m indexer --census` reports indexable
bytes) and the extracted-text size of a sample.

| Quantity | Value | Source |
|---|---|---|
| Chunks per MB of extracted text | ~1,500 | measured: 24,646 chunks from 16.4 MB |
| Index on disk per chunk (Chroma + FTS, 384-dim) | ~9.5 KB | measured: 468.7 MB for 49,344 chunks |
| Raw vector per chunk (384 x float32) | 1,536 bytes | arithmetic |
| Embedding rate, MiniLM, one Apple M4 CPU | 129 chunks/s | measured |
| **Assumed** text yield of a mixed share | 1% of raw bytes | assumption |

For 100 TB raw at 1% yield: 1 TB of text -> **~1.5 billion chunks**.

- **Embedding the first time:** 1.5e9 / 129 per s = 1.16e7 s = **~134 days**
  on one CPU. To finish in a week takes ~19x that rate; GPU throughput was not
  measured here, so measure it with `bench.py --real-embeddings` on the target
  GPU before sizing.
- **Index storage:** 1.5e9 x 9.5 KB = **~14 TB** at this stack's overhead. Raw
  vectors alone are 2.3 TB; int8 quantization makes that 0.58 TB. A sharded
  vector store with quantization is required, not optional.
- **Nightly changes:** if 0.5% of chunks change a night (assumption), that is
  7.5M chunks, 16 hours on one CPU. Fitting a 4-hour window needs ~520
  chunks/s, about 4 CPU workers at the measured rate.
- **Query side:** at 98,559 chunks, retrieval p95 was 15.7 ms with flat
  memory; latency grew 2.0 -> 13 ms p50 over a 20x larger corpus on embedded
  Chroma. Past a few million chunks this needs the server vector store anyway
  (storage above), so the query curve beyond that is the vector store's.
- **Per-question cost does not grow with the corpus:** retrieval is top-k and
  only the reranked top 10 reach the model. Cost scales with question volume.
  Last measured answered question on the fixture set: ~$0.0055 (README). Agent
  question cost: not measured (live tier not run).

---

## 4. Eval map

Which suite proves which guard, and what it costs to run. Definitions:
`.claude/evals/production.md` and `.claude/evals/agent.md`.

| Suite | Tier | Runs | Covers |
|---|---|---|---|
| `pytest tests/` (360 tests) | free | every push | Unit behaviour, access control, agent bounds with a scripted model, fault injection (`test_faults.py`), SQL attack corpus (`test_sql_attacks.py`) |
| `run_eval.py` retrieval + `--baseline` | free | every push | Expected facts in the reranked top 10; MRR / hit@k regression |
| `bench.py all` (CI size) | free | every push | Incremental indexing, no-op re-runs, resume after a kill, query memory vs corpus size, needle recall |
| `sql_load.py` (CI size) | free | every push | Concurrency, attack mix bounded, role isolation under load |
| `agent_load.py` | free | every push | Bounds under 429s, timeouts, slow and runaway models; cross-user isolation |
| `demo/check_search.mjs`, `agent_runs.py --check` | free | Pages deploy | Browser demo matches the golden set |
| `run_eval.py --live --repeat 3` | paid | manual | Generated answers, refusals, groundedness judge, order and agent cases; pass@3 and pass^3; tokens and cost |
| `injection.yaml` on the adversarial corpus | paid | manual | The model does not follow instructions in documents or questions |
| `bench.py --real-embeddings`, larger sizes | free, slow | before a capacity decision | Embedding throughput, disk per chunk, latency curve |

Evals that do not exist yet are listed in section 9.

---

## 5. Measured results

Machine: Apple M4, 10 cores, 16 GB RAM, macOS 27.0, Python 3.13.6, SQLite
3.50.4. Date: 2026-11-15. Laptop numbers: rerun on the target hardware before
sizing anything.

**Tests:** 360 passed (288 before this pass; +46 SQL attack cases, +26 fault tests).

**Retrieval eval** (fixture corpus, 18 files): 18 passed, 0 failed, 37
skipped (live only). MRR 0.967, hit@1 0.933, hit@3 1.0, hit@5 1.0. Latency
p50 26 ms, p95 34 ms after warm-up (the first, cold query took 3.4 s loading
models, which is why the runner now warms up untimed).

**Indexing** (synthetic corpus; fake embeddings unless stated):

| Files | Chunks | Rate | No-op re-run | 1% change | Killed half-way, resumed |
|---|---|---|---|---|---|
| 300 | 1,498 | 775 chunks/s | 0 re-embedded, manifest untouched | 3 of 3 re-embedded | 150 re-embedded (150 checkpointed) |
| 5,000 | 24,646 | 543 chunks/s | 0, untouched | 50 of 50 | 2,500 (2,500 checkpointed) |
| 500, real MiniLM | 2,508 | **129 chunks/s** | 0, untouched | 5 of 5 | 250 (250 checkpointed) |
| 20,000 | 98,559 | 370 chunks/s (266 s) | — | — | — |

Indexing throughput falls as the index grows (543 -> 370 chunks/s from 25k to
99k chunks) on embedded Chroma + FTS. Crawl: 31k-54k files/s on local SSD.

**Retrieval vs corpus size** (keyword needle queries, hybrid retriever):

| Chunks | Index on disk | Keyword index | Query p50 / p95 | Needle hit rate | Python heap peak |
|---|---|---|---|---|---|
| 4,978 | — | — | 2.0 / 2.1 ms | 1.0 | 0.17 MB |
| 9,878 | 99.0 MB | 15.9 MB | 4.3 / 5.7 ms | 1.0 | 0.17 MB |
| 49,344 | 468.7 MB | 80.6 MB | 8.0 / 9.9 ms | 1.0 | 0.14 MB |
| 98,559 | — | — | 13.0 / 15.7 ms | 1.0 | 0.14 MB |

With the pre-fix `_corpus_size` patched back in, the heap grew 0.11 -> 0.84 MB
(7.6x) for 10x the corpus and the bench failed, as intended.

**SQL load** (16 threads, 2,000 questions, 10% attack queries, fixture + 200k
synthetic orders, 28 MB DB):

| Setup | Throughput | Normal p50 / p95 / p99 | Attack queries | Crashes | Contractor leaks |
|---|---|---|---|---|---|
| Before removing the redundant role filter | 70 q/s | 130 / 544 / 745 ms | p95 2.02 s (76 hit the budget) | 0 | 0 |
| After | **103.5 q/s** | **63 / 238 / 289 ms** | p95 2.01 s (76 hit the budget) | 0 | 0 |
| After, plus reflex indexes | 28.4 q/s | 217 / 2,014 / 2,053 ms | p95 2.03 s | 0 | 0 |

Single-thread at 200k orders, no indexes: 0-82 ms per query (admin);
"revenue by region" is the slowest (82 ms), a 4-way join and aggregate.

**Agent load** (scripted model, 50 ms simulated latency, 3 s deadline):

| Questions x workers | Throughput | p50 / p95 / max | Injected failures | Problems |
|---|---|---|---|---|
| 200 x 16 | 27.6 q/s | 0.16 / 0.39 / 5.42 s | 28 x 429, 12 timeouts, 6 slow, 10 runaway, 15 injection | 0 |
| 1,000 x 64 | 98.5 q/s | 0.16 / 5.41 / 5.42 s | 110 x 429, 56 timeouts, 55 slow, 48 runaway, 87 injection | 0 |

Throughput here measures the loop's own overhead; with a real model it is
set by API latency and rate limits.

**Not measured:** live answer quality and cost (live tier not run), GPU
embedding rate, SMB crawl rate, multi-instance behaviour, Postgres / Qdrant /
OpenSearch at scale.

---

## 6. Launch checklist

Generic: use it for any retrieval, NL-to-SQL or agent system.

**Data and access**
- [ ] Identity comes from the session, never from the model or the prompt.
- [ ] Every tool and query applies the asker's permissions itself (row, column, file).
- [ ] Revoking access takes effect without re-indexing (checked at query time).
- [ ] The answer cache is keyed per user and re-checks access on a hit.
- [ ] Logs hold ids, paths and counts, never document text or result rows.

**Bounds** (each with a test that hits it)
- [ ] Every model call: timeout, retry cap, token cap.
- [ ] Every agent question: step cap, token budget (including nested calls), wall-clock deadline.
- [ ] Every SQL query: statement allow-list, row limit, time limit, value-size limit, read-only role.
- [ ] Every search: result limit, time limit, bounded query size.
- [ ] Every user: request rate limit; every tenant: spend cap.
- [ ] Nothing on the request path loads a whole corpus, table or index (a memory-vs-size bench proves it).

**Ingestion**
- [ ] Incremental by content hash; a no-op run changes nothing, including cache keys.
- [ ] Idempotent per file; a killed run resumes; retries do not duplicate.
- [ ] Poison files are isolated (time and memory limit per file).
- [ ] Model or chunker change triggers a blue/green rebuild, evaluated before the switch.

**Evals**
- [ ] Retrieval eval with a stored baseline, in CI.
- [ ] Adversarial SQL and prompt-injection suites.
- [ ] Load test with injected upstream failures (429, timeout, slow, runaway).
- [ ] Live eval run with repeats (pass@k and pass^k) on the exact model id being shipped.
- [ ] Cost per question and p95 latency recorded from a real run.

**Operations**
- [ ] Liveness, readiness and data-staleness checks are separate.
- [ ] Shared state (cache, rate limit, sessions) is external to app processes.
- [ ] Central logs and dashboards for the guardrail fields; alerts in section 7.
- [ ] Backup, restore and index rollback tested once, by hand, before launch.
- [ ] A canary step compares guardrail rates and latency before a full rollout.

---

## 7. SLOs and alerts

Targets to start from, not measurements. Every field named below is already
in `logs/events.jsonl`.

| Signal | Field(s) | Alert when |
|---|---|---|
| Answer latency | `latency_ms` | p95 over 10 s for 15 min |
| Model API health | `guardrail` starts with `api_error` | over 2% of questions for 10 min |
| Agent limits | `guardrail` in `step_cap`, `budget`, `timeout` | over 5% of agent questions per hour |
| SQL refusals | `guardrail` starts with `sql_rejected` | sudden rise (prompt change or attack) |
| Orders availability | `guardrail` starts with `orders_unavailable` | any, for 5 min |
| Spend | `cost_usd` | hourly sum over budget; any `cost_usd: null` (unpriced model) |
| Index freshness | `pipeline.health` | last success older than 36 h |
| Index tagging drift | `num_dropped_by_acl` / `num_retrieved` | ratio rising week over week |
| Keyword search | `keyword_timeout` events | any sustained rate |
| Cache | `cache` hit / miss | hit rate drops to 0 after a night with no changes |

---

## 8. Fixed in this pass

| Defect | Fix | File |
|---|---|---|
| SQL guard accepted `zeroblob`, `randomblob`, `load_extension`; a 1.8 GB allocation could run in one VM step, past the time budget | Denied functions; SQLite hard limits on every connection; all sqlite errors become a GuardError | `search/orders.py` |
| Model clients without timeout or retry cap (answers, grading, order SQL, summaries, judge) | `pipeline/llm.bounded()` on every client | `pipeline/llm.py`, `rag.py`, `indexer/__main__.py`, `eval/run_eval.py` |
| Agent budget ignored grading and rewrite tokens; deadline checked only between model turns | Budget counts every token in the question; tools are not run past the deadline | `agent.py` |
| Corrupt or missing orders DB raised an unhandled exception | Typed `orders_unavailable` answer; the agent drops to documents | `rag.py`, `agent.py` |
| Rate limit per browser session (a new tab reset it); order mode not limited and re-asked the model on every rerun | Per-user limiter behind an interface; order answers kept per question | `pipeline/ratelimit.py`, `app.py` |
| `_corpus_size` loaded every chunk id on each chain build | Capped count | `rag.py` |
| BM25 fallback loaded the whole corpus | Capped, logged | `rag.py` |
| Keyword delete scanned the whole index per file; unbounded `IN` lists; full `COUNT(*)` per retriever build | `chunk_sources` table, batched deletes, `is_empty()` | `search/keyword.py` |
| Keyword query had no time limit and OR-ed every stop word | 2 s budget, stop words, 32-term cap | `search/keyword.py` |
| Manifest written non-atomically and only at the end of a run | Atomic write, checkpoint every 200 files | `rag.py` |
| A no-op nightly run invalidated the answer cache | Manifest rewritten only when it changed | `rag.py` |
| Role views filtered unrestricted roles anyway (70 q/s) | No child-view filter for roles that see everything (103.5 q/s) | `search/orders.py` |
| No readiness check | `python -m pipeline.health --ready` | `pipeline/health.py` |

---

## 9. Known gaps

Not built, in rough priority order. Each is a known failure from section 2.

1. **Run the live tier**: `--live --repeat 3` and the injection suite. Needs an API key and spend approval.
2. **Per-file loader isolation**: a subprocess with a time and memory limit, so one malformed PDF cannot hang a run.
3. **Spend cap by tokens** per user and tenant (the rate limit counts requests, not cost).
4. **Redis** for cache and rate limit, and a stateless API tier, before a second app instance.
5. **Server vector store and keyword index** (Qdrant or pgvector, OpenSearch) before ~1M chunks; add a **filtered-recall eval** when it lands.
6. **Postgres orders replica** with row-level security and `statement_timeout`; rerun `sql_load.py` against it.
7. **Blue/green index** with an eval gate before the pointer switch.
8. **SQL fingerprint logging** instead of SQL text; **truncation events** for capped files.
9. **Live load test** against the real API at a small, approved spend, to measure real 429 behaviour and cost per agent question.
10. **Multi-instance test**: two app processes, one Redis, proving shared limits and cache.
