# RAG Assistant

Chat with your own PDFs/Word/text files. Embeddings run locally (free); only answer generation calls Claude.

**[▶ Try the live demo](https://alayparikh.github.io/prod-grade-rag-assistant/)**: a fictional company's handbook, runbooks and resumes, searched entirely in your browser (no server, no AI calls, no sign-in). How it works: [demo/README.md](demo/README.md).

## Try it locally (no API key needed)

Without `ANTHROPIC_API_KEY` the app runs in offline mode: answers are the best-matching passages, and nothing calls an API.

```bash
RAG_AUTH_MODE=none RAG_DOCS_PATH=./eval/fixtures/docs RAG_PERSIST_PATH=./demo_index python -m indexer
RAG_DEMO=1 RAG_AUTH_MODE=none RAG_DOCS_PATH=./eval/fixtures/docs RAG_PERSIST_PATH=./demo_index streamlit run app.py
```

The hosted demo is a static page built by [`.github/workflows/pages.yml`](.github/workflows/pages.yml); see [demo/README.md](demo/README.md).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in the project root:

```
ANTHROPIC_API_KEY=your-key-here
```

Get a key at https://console.anthropic.com/. `.env` is git-ignored — never commit it.

## Run

Drop `.pdf`, `.docx`, `.txt`, or `.md` files into `docs/` (auto-created on first run), then:

```bash
python rag.py                   # web chat UI at localhost:8501
python rag.py --cli             # terminal chat instead
python rag.py --cli --reindex   # force a full rebuild of the index
```

First run embeds everything into `chroma_db/`. Later runs only re-embed files that are **new or changed** — edit a file, hit **Sync documents** in the sidebar, no restart needed.

## Architecture

**Ingest** (local, no API calls):

```
docs/ → discover_files() → file_hash() vs manifest.json (skip unchanged)
      → load_file() → split_documents() (1000 chars, 200 overlap)
      → tag chunks with ACL groups → local MiniLM embeddings → Chroma
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
| `permissions.yaml` | Folder → group ACL map, pending NAS ACL tagging |

**Adaptive retrieval breadth.** `k` is derived from corpus size (`compute_k()`), not hardcoded — roughly +1 per 100 chunks, clamped to 4–20, overridable with `RAG_RETRIEVAL_K`. A fixed `k=4` was fine at 54 chunks (the top 7% of the corpus) but silently starved recall at 1,038 chunks (top 0.4%): a document listing every employee stopped being retrieved for "how many employees are there", and the assistant correctly refused rather than guessing. Wider retrieval costs more per question — measured ~$0.011 → ~$0.020 — which is the deliberate tradeoff.

**Notable implementation details:** `.docx` hyperlinks are recovered from the document's relationship table (plain-text extraction drops the URL and keeps only anchor text like "LinkedIn"). BM25 uses a custom regex tokenizer — the default splits on whitespace, making a whole URL one unmatchable token.

## Configuration

| What | Where |
|---|---|
| `ANTHROPIC_API_KEY` | `.env` — required, exits without it |
| Your documents | `docs/` |
| `MODEL` | `rag.py` — defaults to `claude-sonnet-5` |
| `EMBEDDING_MODEL` | `rag.py` — defaults to `all-MiniLM-L6-v2` (small, no GPU) |
| Rerank, grading, cache, tracing, index health | env vars — see `.env.example` |

Every question's event-log line carries per-step timings (`retrieve_ms`, `rerank_ms`, `grade_ms`, `generate_ms`), `cache` hit/miss and whether the rewrite-retry fired. Changing `pipeline/chunking.py` requires bumping `CHUNKER_VERSION`, which re-embeds every file on the next index run.

## Guardrails

All enforced inside `answer_question()`:

- **Input length cap** (2000 chars) — rejected before retrieval or any API call.
- **Prompt-injection resistance** — retrieved content is wrapped in `<retrieved_context>` tags and explicitly framed as untrusted data, not instructions.
- **NAS access check** — every retrieved chunk's file is opened as the asking user before generation; denied files are dropped and an all-denied result never reaches the model.
- **Empty-context short-circuit** — zero retrieved chunks means the LLM is never called. Fires only on a genuinely empty result set (e.g. ACLs filtered everything out), not on retrieved-but-irrelevant content.
- **Typed error handling** — auth/rate-limit/timeout/connection failures each get a distinct message instead of a raw traceback.
- **Secret redaction** — narrow, high-precision patterns only (AWS keys, API keys, SSN format). A generic "long number" pattern would false-positive on medical record IDs and phone numbers.
- **Source attribution** — the "Sources" footer lists only files Claude reports actually using, via a `sources_used` schema field (`with_structured_output`), validated against what was retrieved. A plain text-instruction version of this was tried first and proved unreliable — the model dropped it on longer answers.
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

```bash
python -m pytest tests/ -q       # unit tests, fast, no API
python eval/run_eval.py          # retrieval-only, free — checks the right chunks were found
python eval/run_eval.py --live   # real API calls — checks generated answers
```

`--live` additionally verifies refusal and injection resistance. An `ERROR` (vs. `FAIL`) means the API call itself failed, not a quality regression. Update the golden set when you change `docs/` — a stale one gives false failures and false passes.

**Why both tests and evals.** A hybrid retriever is deliberately redundant: when BM25 degrades, vector search often still surfaces the right chunk. That's good for users and bad for detection — a deliberately broken `_tokenize()` was measured passing the full retrieval eval while `tests/test_units.py` caught it immediately. Evals cover the pipeline end to end; unit tests guard the components the pipeline can mask.

### CI

`.github/workflows/ci.yml` runs unit tests + the retrieval eval on every push and PR — no API key, no cost. It runs against the committed synthetic corpus in `eval/fixtures/` (not `docs/`, which is git-ignored), driven by the `RAG_DOCS_PATH` / `RAG_PERSIST_PATH` / `RAG_LOG_PATH` env overrides. The `--live` eval is a manual `workflow_dispatch` job, since it costs money and needs `ANTHROPIC_API_KEY` in repo secrets.

The fixture corpus is 30 chunks of deliberately competing content — several similar résumés plus engineering runbooks — because a small or semantically well-separated corpus lets every query retrieve everything, and an eval that can't fail is worse than no eval.

## NAS deployment

**Step-by-step Synology instructions are in [DEPLOY.md](DEPLOY.md).** This
section covers how it works; that one covers what to type.

Runs on a host on the LAN beside the NAS, or on the NAS itself, indexing a
read-only mount of the share.

```
NAS  --(SMB, read-only, service account)-->  /mnt/nas  -->  indexer (nightly cron)
NAS  <--(SMB, each user's own credentials)--  app      <--  browser (TLS)
```

Set `RAG_DOCS_PATH=/mnt/nas`, `RAG_NAS_HOST`, and `RAG_NAS_SHARE`, then:

```bash
python -m indexer --census   # file counts per type; decides OCR scope before indexing 50 GB
python -m indexer            # census + content index (nightly cron target)
python -m indexer --reindex  # rebuild the vector store from scratch
```

The indexer is a separate entrypoint from the app on purpose: walking the
share must not depend on anyone having a browser tab open, and the app must
not need a writable mount.

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

| Env | Purpose |
|---|---|
| `RAG_NAS_HOST` / `RAG_NAS_SHARE` | NAS to authenticate and check files against |
| `RAG_DOCS_PATH` | Read-only mount of that share (default `/mnt/nas`) |
| `RAG_SESSION_IDLE_MIN` | Idle minutes before a login expires (default 30) |
| `RAG_AUTH_MODE=none` | Local development only — no login, no access checks |
| `RAG_META_DB` | File catalogue (default `<persist>/meta.sqlite`) |
| `RAG_EXCLUDE_GLOBS` | Extra directory/file globs to skip while crawling |

### Deploying

```bash
docker compose up -d --build                      # separate Linux host
docker compose up -d --build app indexer          # on a Synology, DSM owns 443
```

`app` serves the UI, `indexer` re-indexes nightly at `RAG_INDEX_AT`, and
`caddy` terminates TLS. On a Synology, leave Caddy out and use DSM's own
reverse proxy — DSM already owns ports 80 and 443. See
[DEPLOY.md](DEPLOY.md). Both Python services mount the share read-only, so a bug here cannot
write to the NAS even if the service account is later over-granted. The
index lives in a named volume — back that up and test a restore, because
rebuilding it from 50 GB is hours of OCR and embedding.

**Not yet exercised on real hardware.** The container files, the ACL
tagging in `indexer/acl.py`, and the LDAP group lookup are written and
unit-tested but have never run against an actual NAS. Confirm on site
that the device answers a security-descriptor query and that group
membership resolves before turning `RAG_ACL_TAGGING` on. Until then the
query-time check stands alone, which is correct but slower for users with
narrow access.

### Two search modes

**Ask about content** is the RAG path. **Find a file** matches names and
folder paths through SQLite FTS5 — it costs nothing per query and covers
the files whose contents are never indexed (images, drawings, archives),
which on a disorganized share is most of them. Both render citations as
NAS paths so people can go open the file.

## Notes

- Indexing and retrieval are fully local — no API cost, no network call.
- Corpus size doesn't change per-question cost much: retrieval is always top-k, and k grows only slowly with the corpus. Cost scales mainly with query volume and conversation length.
- `venv/`, `chroma_db/`, `docs/`, `.env`, `users.yaml`, `logs/`, and `eval/golden_set.yaml` are git-ignored — a fresh clone starts clean.
