# RAG Assistant

Chat with your own PDFs/Word/text files. Embedding, keyword search and reranking run locally (free); Claude is called only to grade relevance and write the answer, and not at all in offline mode.

**[▶ Try the live demo](https://alayparikh.github.io/prod-grade-rag-assistant/)**: a fictional company's handbook, runbooks and resumes, searched entirely in your browser (no server, no AI calls, no sign-in). How it works: [demo/README.md](demo/README.md).

## Architecture

**Ingest** (local, no API calls):

```
docs/ → discover_files() → file_hash() + CHUNKER_VERSION vs manifest.json (skip unchanged)
      → load_file()        .docx headings become markdown headings, hyperlinks recovered
      → split_documents()  split at headings, then 1000-char windows; each chunk
                           prefixed with its section path  (pipeline/chunking.py)
      → tag chunks with ACL groups → local MiniLM embeddings → Chroma + SQLite FTS5
      → write indexer_status.json heartbeat                 (pipeline/health.py)
```

**Query** (only Claude usage):

```
question → answer_question()          ← every guardrail lives here
   ├ length cap                        reject before any API call
   ├ answer cache (per user + index version, first turn only)
   ├ standalone rewrite                LLM call only if chat history exists
   │    └ EnsembleRetriever = vector (k) + BM25 keyword (k), RRF-fused, k scales with corpus
   ├ empty context? → short-circuit, never calls Claude
   ├ per-file NAS access check
   ├ cross-encoder rerank → top 10     local, pipeline/rerank.py
   ├ Haiku relevance grading           nothing relevant → rewrite query, retry once
   ├ structured-output answer → claude-sonnet-5, streamed
   │    └ offline (RAG_LLM=off or no key): top reranked passages quoted, -6 score cutoff
   ├ validate sources_used ⊆ retrieved, redact secrets
   └ log to logs/events.jsonl
```

`answer_question()` is the single entry point for both the CLI and web UI, so guardrails apply everywhere by construction.

| File | Role |
|---|---|
| `rag.py` | The engine — ingest, index, retrieve, guardrails, CLI, launcher |
| `app.py` | Streamlit UI + per-session rate limiting (thin; logic lives in `rag.py`) |
| `eval/run_eval.py` | Golden-set eval runner; exits non-zero on failure (CI-ready) |
| `indexer/crawl.py` | Walks the share into SQLite + FTS5; the file census |
| `indexer/__main__.py` | `python -m indexer` — the cron entrypoint |
| `search/metadata.py` | Question → file-name search over the catalogue |
| `auth/smb.py` | NAS login and per-file access checks |
| `pipeline/` | Query stages: rerank, grading, cache, chunking, tracing, index health |
| `search/orders.py` | Order questions: SQL guard, read-only connection, per-role views, prompt |
| `demo/` | The in-browser demo published to GitHub Pages ([demo/README.md](demo/README.md)) |
| `permissions.yaml` | Folder → group ACL map, pending NAS ACL tagging |

**Adaptive retrieval breadth.** `k` is derived from corpus size (`compute_k()`), not hardcoded — roughly +1 per 100 chunks, clamped to 4–20, overridable with `RAG_RETRIEVAL_K`. A fixed `k=4` was fine at 54 chunks (the top 7% of the corpus) but silently starved recall at 1,038 chunks (top 0.4%): a document listing every employee stopped being retrieved for "how many employees are there", and the assistant correctly refused rather than guessing. Wider retrieval cost more per question (measured ~$0.011 → ~$0.020) until the reranker and Haiku grading started trimming what reaches Sonnet: on the fixture golden set an answered question now costs about $0.0055.

**Notable implementation details:** `.docx` hyperlinks are recovered from the document's relationship table (plain-text extraction drops the URL and keeps only anchor text like "LinkedIn"). BM25 uses a custom regex tokenizer — the default splits on whitespace, making a whole URL one unmatchable token.

## Guardrails

All enforced inside `answer_question()`:

- **Input length cap** (2000 chars) — rejected before retrieval or any API call.
- **Prompt-injection resistance** — retrieved content is wrapped in `<retrieved_context>` tags and explicitly framed as untrusted data, not instructions.
- **NAS access check** — every retrieved chunk's file is opened as the asking user before generation; denied files are dropped and an all-denied result never reaches the model.
- **Empty-context short-circuit** — zero retrieved chunks means the LLM is never called. Fires only on a genuinely empty result set (e.g. ACLs filtered everything out), not on retrieved-but-irrelevant content.
- **Typed error handling** — auth/rate-limit/timeout/connection failures each get a distinct message instead of a raw traceback.
- **Secret redaction** — narrow, high-precision patterns only (AWS keys, API keys, SSN format). A generic "long number" pattern would false-positive on medical record IDs and phone numbers.
- **Source attribution** — the "Sources" footer lists only files Claude reports actually using, via a `sources_used` schema field (`with_structured_output`), validated against what was retrieved. A plain text-instruction version of this was tried first and proved unreliable — the model dropped it on longer answers.
- **Relevance grading fails open** — Haiku decides which chunks can help and, if none can, the query is rewritten and retried once. A grading error keeps every chunk: grading trims cost and noise, it never authorizes.
- **Answer cache** — keyed on the user, the normalised question and the index version, first turns only; a hit re-runs the access check on every source file, so revoked permissions turn it into a miss.
- **Streaming redaction** — redaction runs on the whole answer-so-far and the newest 80 characters are held back, so a secret split across two stream chunks is never on screen.
- **Offline mode** — `RAG_LLM=off` never constructs an API client; answers are quoted passages, and passages scoring below the reranker cutoff become a refusal.
- **Rate limiting** (web UI only) — 30 questions/hour per session. In-memory; multi-instance needs Redis.

## Logging

Every request appends a JSON line to `logs/events.jsonl` (rotating, ~50MB ceiling):

```json
{"ts": 1788..., "question_len": 34, "num_sources": 7, "num_sources_used": 2,
 "sources_retrieved": ["./docs/a.pdf", "./docs/b.docx"], "sources_used": ["./docs/b.docx"],
 "guardrail": null, "latency_ms": 4633, "input_tokens": 4053, "output_tokens": 255,
 "cost_usd": 0.010656, "models_called": ["claude-sonnet-5"]}
```

Token counts come from a `get_usage_metadata_callback()` wrapping the whole pipeline, so they include the **query-rewrite call** that fires on follow-up turns — a first question costs one API call, every follow-up costs two. `cost_usd` is `0.0` when a guardrail short-circuited before any API call, and `null` when tokens were spent on a model absent from `PRICING` (never silently priced at zero).

Source **paths** are logged, never chunk text — the log file isn't access-controlled.

`num_retrieved` alongside `num_sources` shows how many chunks the NAS check
removed: a persistent gap means the index is tagged more loosely than the
NAS actually permits. Logins, failed logins, file searches and thumbs
up/down are logged the same way, with the username and never the password.

## Evals

`eval/golden_set.yaml` holds test questions grounded in your actual `docs/` content — fact lookups, out-of-scope negatives (should refuse), a multi-turn follow-up, and a prompt-injection attempt. Git-ignored; `eval/golden_set.example.yaml` is the schema template.

The retrieval-only run checks the reranked top 10, which is what the model actually sees. `--live` additionally verifies refusal and injection resistance, and an LLM judge fails any answer making a claim the retrieved text doesn't support (`--no-judge` to skip); it runs with the answer cache off so a cached answer can't hide a regression. An `ERROR` (vs. `FAIL`) means the API call itself failed, not a quality regression. Update the golden set when you change `docs/` — a stale one gives false failures and false passes.

**Why both tests and evals.** A hybrid retriever is deliberately redundant: when BM25 degrades, vector search often still surfaces the right chunk. That's good for users and bad for detection — a deliberately broken `_tokenize()` was measured passing the full retrieval eval while `tests/test_units.py` caught it immediately. Evals cover the pipeline end to end; unit tests guard the components the pipeline can mask.

### Authorization comes from the NAS

There is no user table and no group file. Login opens a real SMB session
with the user's own credentials, so an AD/LDAP-joined NAS validates against
the directory transparently. The password is held in server memory for the
session only — never logged, never written to disk, never passed to
anything but `auth/smb.login`.

Every question is authorized in two stages:

1. **Index-time tags** (pre-filter) — chunks carry the groups allowed on
   their folder, filtered in Chroma. Cheap but a stale snapshot.
2. **Query-time check** (authoritative) — before any chunk reaches Claude,
   each candidate file is opened for read over SMB *as that user*. Anything
   that fails to open is dropped, including files that merely no longer
   exist. Revoking someone's NAS access takes effect on their next
   question, with no reindex.

Retrieval over-fetches (`RAG_OVER_FETCH`, default 3x) so filtering still
leaves enough context, and truncates back afterwards so users who can read
everything don't pay for triple the prompt. A fully-filtered result returns
the same wording as an empty one — a refusal must not reveal that a
document exists.

### Three modes

**Ask about orders** answers plain-English order questions from the orders
database, leading with the answer and showing the SQL below it. A held or
late order also gets the policy passage that explains it ("why is order 1042
late?" → `on_hold, address_verification` + the shipping policy on that hold).

- **App:** Claude writes the SQL; `search/orders.py` runs it only if it's a
  single `SELECT` over the asker's role views, read-only, `LIMIT 50`, 2s.
- **Demo:** no model; the question picks one of nine SQL templates by meaning
  (see [demo/README.md](demo/README.md)).

**Ask about content** is the RAG path. **Find a file** matches names and
folder paths through SQLite FTS5 — it costs nothing per query and covers
the files whose contents are never indexed (images, drawings, archives),
which on a disorganized share is most of them. Both render citations as
NAS paths so people can go open the file.

## Notes

- Indexing and retrieval are fully local — no API cost, no network call.
- Corpus size doesn't change per-question cost much: retrieval is always top-k, and k grows only slowly with the corpus. Cost scales mainly with query volume and conversation length.
