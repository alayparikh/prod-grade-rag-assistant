# Plan: NAS Document Search Assistant (50 GB)

**Source**: pasted delivery plan (Plan Canvas), no PRD file
**Selected Milestone**: full delivery, phased weeks 1-6
**Complexity**: Large

## Summary
Extend the existing local-docs RAG (`rag.py`, `app.py`, `eval/run_eval.py`) into a three-layer
assistant over a read-only CIFS mount of a ~50 GB NAS share: metadata index (SQLite FTS5),
folder summaries (Haiku), and content RAG (existing Chroma + hybrid retrieval). Authorization
is delegated to the NAS: SMB login via `smbprotocol`, index-time ACL tagging as a pre-filter,
and an authoritative per-file SMB open check before any LLM call. `permissions.yaml` /
`users.yaml` code paths are removed.

Four things in the pasted plan do not match the code and change the plan:
1. `app.py` has no login today. RBAC is dormant; `build_chain` runs unrestricted. Login must
   ship in Phase 1, not Phase 4, or no pilot user can be given access.
2. `build_retriever()` (`rag.py:247`) loads the whole corpus with `vectorstore.get()` to build an
   in-memory BM25 and bakes the group filter into the retriever at build time, and `app.py:29`
   caches one chain for all users. At millions of chunks this is a per-user, per-login full
   corpus load. Replace BM25 with a persistent SQLite FTS5 chunk table and inject the filter
   per query.
3. `sync_vectorstore()` (`rag.py:201`) hashes every file every run. On a 50 GB SMB mount that
   is a full read nightly. Manifest keys move to `(size, mtime_ns)`; hash only on change, and
   stream the hash.
4. Stage-1 pre-filter needs the *user's* group list at query time. NTLM login does not return
   it. Resolve via LDAP (`ldap3`) when the NAS is AD-joined; otherwise stage 1 is skipped and
   stage 2 alone is authoritative.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `rag.py:38-46` | Module-level constants, `RAG_*` env overrides with defaults; snake_case; `_private` helpers |
| Naming | `rag.py`, `app.py` | Flat modules at repo root. New code goes in a small package per concern (`indexer/`, `search/`, `auth/`) importing from `rag` |
| Errors | `rag.py:562-580` `_generate` / `_api_error_message` | Catch typed exceptions, return `(user_message, "tag:detail")`; never raise into UI |
| Guardrails | `rag.py:503` `answer_question` | Single call site for every guardrail; new checks (access check, router) go inside it, not in `app.py` |
| Fail-closed | `rag.py:143` `build_group_filter` | Empty allowed list → filter that matches nothing. Access-check must do the same |
| Logging | `rag.py:97` `log_event` | One JSON line per event via rotating handler; paths only, never chunk text |
| Cost | `rag.py:62` `PRICING`, `summarize_usage` | Every model used must be in `PRICING` or cost logs `None`; `claude-haiku-4-5` already present |
| Data access | `rag.py:201` `sync_vectorstore` | Manifest diff → `store.delete(where={"source": path})` → `add_documents`; reuse for content layer |
| Metadata | `rag.py:232` | Group tags are boolean keys `group_<name>`; keep, but sanitize NAS SIDs/names to `[A-Za-z0-9_]` |
| Config | `rag.py:39-42` | Env vars for paths (`RAG_DOCS_PATH`, `RAG_PERSIST_PATH`, `RAG_LOG_PATH`); add `RAG_NAS_HOST`, `RAG_NAS_SHARE`, `RAG_META_DB` |
| Tests | `tests/test_units.py` | pytest, class per unit, `sys.path.insert` import of `rag`, fakes over mocks (`_FakeVS`), fixture skip-if-missing |
| Eval | `eval/run_eval.py`, `eval/fixtures/golden_set.yaml` | Golden set YAML with `expect_answer_contains_any` / `expect_refusal`; retrieval-only in CI, `--live` manual |
| CI | `.github/workflows/ci.yml` | Python 3.13, HF model cache, fixture corpus via `RAG_DOCS_PATH` |

No existing pattern for: SMB access, SQLite, OCR, routing, Docker. State new conventions in the task that introduces each.

## Files to Change
| File | Action | Why |
|---|---|---|
| `rag.py` | UPDATE | Manifest by size+mtime; streamed hash; loaders for xlsx/pptx/eml/OCR; chunk metadata `folder`, `ext`, `mtime`; retriever accepts per-query filter; BM25 → FTS5; `answer_question` gains `access_check` + router; remove `load_permissions`/`groups_for_path` yaml path; extend `_SECRET_PATTERNS` |
| `app.py` | UPDATE | SMB login form, session with idle timeout, per-user filter passed per query, "Find files" mode, NAS-path citations (UNC + smb://), thumbs up/down, remove `docs/` copy |
| `indexer/__init__.py`, `indexer/__main__.py` | CREATE | `python -m indexer` entrypoint: crawl → summarize → content sync; cron target |
| `indexer/crawl.py` | CREATE | `os.scandir` walk of `/mnt/nas`, `files` table + FTS5, exclude list, incremental by size+mtime |
| `indexer/summarize.py` | CREATE | Per-folder Haiku one-liner → `folders` table + embedding |
| `indexer/acl.py` | CREATE | Read folder security descriptors via `smbprotocol`, map to `group_*` tags (stage 1) |
| `search/metadata.py` | CREATE | Haiku tool call → `{terms, ext_filter, year_filter}` → FTS5 query |
| `search/router.py` | CREATE | Haiku classifies `find_file` / `content` / `aggregate` |
| `search/keyword.py` | CREATE | FTS5 chunk index + `BaseRetriever` wrapper replacing `BM25Retriever` |
| `auth/smb.py` | CREATE | Login (open SMB session), per-file `can_read(user_session, path)`, session cache, LDAP group lookup (optional) |
| `permissions.yaml`, `users.yaml.example` | DELETE | Replaced by NAS ACLs |
| `requirements.txt` | UPDATE | +`smbprotocol`, `openpyxl`, `python-pptx`, `pytesseract`, `Pillow`, `ldap3`; -`streamlit-authenticator` |
| `Dockerfile`, `docker-compose.yml`, `Caddyfile` | CREATE | app, indexer loop, caddy TLS; `/mnt/nas:/mnt/nas:ro` |
| `tests/test_crawl.py`, `test_router.py`, `test_loaders.py`, `test_acl.py`, `test_smb_access.py` | CREATE | Unit tests; samba container fixture for access check |
| `eval/fixtures/golden_set.yaml`, `eval/run_eval.py` | UPDATE | Add `find_file` / `aggregate` cases and a per-user access case (`as_user`) |
| `.github/workflows/ci.yml` | UPDATE | samba service container, tesseract apt install |
| `README.md` | UPDATE | NAS deployment, IT checklist, retire yaml RBAC docs |

## Tasks

### Phase 0 (week 0, IT + owner): host, mount, accounts
- **Action**: IT delivers host per spec, `/mnt/nas` CIFS ro mount, `rag-indexer` account, API key via secrets store, answers NAS questions (vendor, AD/LDAP vs local, SMB3, ACLs set).
- **Validate**: `ls /mnt/nas` as root after reboot; `smbclient -L nas -U rag-indexer` lists shares.

### Task 1: SMB login + per-file access check (Phase 1, first)
- **Action**: `auth/smb.py`: `login(username, password) -> Session | None` opening `smbprotocol` connection to `RAG_NAS_HOST`; `can_read(session, nas_path) -> bool` via file open for read, closed immediately; `AccessChecker` caches session per Streamlit session id; idle timeout `RAG_SESSION_IDLE_MIN` (default 30). Password lives only in `st.session_state`; never in `log_event`.
- **Mirror**: typed error handling from `_api_error_message`; fail-closed like `build_group_filter`.
- **Validate**: `tests/test_smb_access.py` against samba container (two users, two folders); `pytest -q`.

### Task 2: Per-query authorization inside `answer_question`
- **Action**: `answer_question(rag_chain, question, chat_history, log_context, allowed_groups=None, access_check=None)`. Retriever over-fetches `3*k`; `access_check(path)` drops unreadable sources before `answer_chain`; remaining truncated to `k`. Log `num_dropped_by_acl`. Retriever built once per process; filter passed per invoke via a thin `BaseRetriever` that reads `allowed_groups` from `config` metadata.
- **Mirror**: `answer_question` single call site; `_FakeVS` style test.
- **Validate**: unit test: retrieval returns 6 docs, checker denies 4, LLM sees 2; empty after filter → `NO_CONTEXT_ANSWER`, `guardrail="acl_empty"`, no LLM call.

### Task 3: Login UI + rate limit + feedback (Phase 1)
- **Action**: `app.py` login form → `auth.smb.login`; store user id + session; logout; thumbs up/down → `log_event({"event":"feedback", ...})`. Keep existing per-session rate limit.
- **Validate**: manual: bad password rejected; `events.jsonl` shows `user` field, never password.

### Task 4: Metadata crawler + FTS5 (Phase 1, layer 1)
- **Action**: `indexer/crawl.py`: `os.scandir` recursion, `files(path, name, ext, size, mtime_ns, sha256 NULL, folder)` + `files_fts(name, path)` in `RAG_META_DB` (`chroma_db/meta.sqlite`). Exclude `@eaDir`, `#recycle`, `.Trash*`, `._*`, configurable `RAG_EXCLUDE_GLOBS`. Skip unchanged `(size, mtime_ns)`; delete rows for vanished paths. Emit census summary (counts by ext, total bytes, scanned-PDF estimate) — gates OCR scope.
- **Mirror**: manifest diff semantics of `sync_vectorstore`.
- **Validate**: `tests/test_crawl.py` on tmp tree: add/modify/delete/exclude; rerun is no-op.

### Task 5: "Find files" search (Phase 1, layer 1)
- **Action**: `search/metadata.py`: Haiku tool call (`claude-haiku-4-5`, in `PRICING`) → `{terms, ext_filter, year_filter}`; FTS5 `MATCH` with prefix terms; results through `access_check`; UI renders UNC `\\nas\share\path` and `smb://` link.
- **Validate**: golden `find_file` cases retrieval-only (FTS hit contains expected path); `tests/test_metadata_query.py` with fake LLM.

### Task 6: Manifest by size+mtime, streamed hash (Phase 3 prerequisite, do in week 2)
- **Action**: `rag.py`: `file_hash` streams 1 MiB blocks; manifest value becomes `{"size", "mtime_ns", "sha256"}`; hash only when size/mtime changed; keep sha256 so touched-but-identical files are not re-embedded. `discover_files` reads from `files` table instead of walking again.
- **Validate**: unit test: unchanged mtime → no read (assert open not called); touched identical → hash computed, no re-embed.

### Task 7: Folder summaries (Phase 2, layer 2)
- **Action**: `indexer/summarize.py`: per folder, child names + first 500 chars of up to 5 files → Haiku one line → `folders(path, summary, n_files, updated)`; embed into Chroma collection `folders` with `get_embeddings()`. Re-summarize only when folder's child set or any child mtime changed. Query: top-N folders → `where {"folder": {"$in": [...]}}` combined with group filter using `$and`.
- **Validate**: unit test with fake LLM; cost line logged per folder.

### Task 8: Loaders + OCR (Phase 3)
- **Action**: `load_file`: `.xlsx` (openpyxl, sheet+row text), `.pptx` (python-pptx), `.eml` (`email` stdlib, headers + text part), images and PDFs with no text layer → `pytesseract` (`RAG_OCR_LANGS`, default `eng`; add `hin`,`guj` if census shows). Cap OCR pages per file (`RAG_OCR_MAX_PAGES`, default 50). Per-file loader errors logged with tag `loader_error:<ext>` and skipped, never abort the run.
- **Mirror**: `load_docx` style, one function per format.
- **Validate**: `tests/test_loaders.py` with tiny fixtures per format.

### Task 9: Keyword index replaces in-memory BM25 (Phase 3)
- **Action**: `search/keyword.py`: FTS5 `chunks(chunk_id, source, folder, text)` written in `sync_vectorstore` alongside Chroma; `FtsRetriever(BaseRetriever)` returns `Document`s with metadata pulled from Chroma by id; group and folder filter applied in SQL join to `files`. `build_retriever` uses `EnsembleRetriever([vector, fts])`; `vectorstore.get()` full load removed. Keep `_tokenize` semantics via FTS5 `unicode61` tokenizer.
- **Validate**: `TestBuildRetrieverUsesComputedK` updated; new test: filter excludes chunks of denied folder.

### Task 10: Router + aggregate mode (Phase 3)
- **Action**: `search/router.py`: Haiku classify → `find_file | content | aggregate`. `aggregate`: layer 1 locates canonical source from `RAG_CANONICAL_SOURCES` (yaml map: `employees: "HR/roster.xlsx"`), loads full file (not chunks) into context, answers with citation. Router result logged as `mode`.
- **Validate**: `tests/test_router.py` fake LLM; golden `aggregate` case.

### Task 11: Embedding model switch + full reindex (Phase 3)
- **Action**: `EMBEDDING_MODEL` env override `RAG_EMBEDDING_MODEL`, default `BAAI/bge-small-en-v1.5` (or `bge-m3` if census shows Hindi/Gujarati). `--reindex` path in `python -m indexer`.
- **Validate**: retrieval-only eval green on fixture corpus with new model.

### Task 12: ACL tagging, stage 1 (Phase 4)
- **Action**: `indexer/acl.py`: spike first — confirm `smbprotocol` `Open.query_info(InfoType.SMB2_0_INFO_SECURITY)` returns DACL on this NAS. Map allow-ACEs to `group_<sanitized>` tags per folder; children inherit unless own DACL. `auth/smb.py` gains `groups_for_user()` via `ldap3` `memberOf` (transitive) when `RAG_LDAP_URL` set; else returns `None` → no stage-1 filter. Delete `load_permissions`, `groups_for_path` yaml path and both yaml files.
- **Validate**: `tests/test_acl.py` on captured descriptor fixtures; samba-container test that tagged groups match `can_read`.

### Task 13: Secrets patterns + audit (Phase 4)
- **Action**: `_SECRET_PATTERNS` += PAN `\b[A-Z]{5}[0-9]{4}[A-Z]\b`, Aadhaar `\b\d{4}\s\d{4}\s\d{4}\b` only when preceded by "aadhaar|uid" within 30 chars. `log_event` gains `user`, `mode`, `num_dropped_by_acl`.
- **Validate**: `TestRedactSecrets` extended; phone/long-id negatives still pass.

### Task 14: Docker + cron + TLS (Phase 4)
- **Action**: `Dockerfile` (python:3.13-slim + tesseract-ocr + cifs client libs), `docker-compose.yml` services `app`, `indexer` (`while true; python -m indexer; sleep until 02:00`), `caddy`. Volumes: `/mnt/nas:ro`, `chroma_db/`, `logs/`. Secrets via env file owned by root.
- **Validate**: `docker compose up`, login, ask, `events.jsonl` written; restore `chroma_db/` volume on clean host and query.

### Task 15: Eval + CI (all phases)
- **Action**: golden set gains `mode`, `as_user` fields; `run_eval.py` builds chain per `as_user` with samba fixture users; CI adds samba service and `apt install tesseract-ocr`.
- **Validate**: `python -m pytest tests/ -q`; `python eval/run_eval.py`; `--live` on manual dispatch.

## Validation
```bash
cd /Users/alay/IdeaProjects/prod-grade-rag-assistant
python -m pytest tests/ -q
RAG_DOCS_PATH=./eval/fixtures/docs RAG_PERSIST_PATH=/tmp/ci_index python eval/run_eval.py --golden-set eval/fixtures/golden_set.yaml
python eval/run_eval.py --live          # manual, costs money
python -m indexer --census              # week-1 file census on /mnt/nas
docker compose up -d && curl -k https://search.company.local/healthz
```
Pilot checks (from source plan, unchanged): Diwali flyer via layer 1/2; HR vs non-HR user on
"documents for employee Alay"; revoke NAS access → hidden without reindex; "how many
employees" cites roster; nightly cron re-embeds edited file; backup restore; per-query
`user`, paths, `latency_ms`, `cost_usd` in `events.jsonl`.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| NAS does not expose security descriptors over SMB (stage 1 impossible) | Medium | Spike in Task 12 before building; stage 2 alone is correct |
| User group list unobtainable (local NAS users, no LDAP) | Medium | Stage 1 skipped; over-fetch `3*k` and accept slower answers for narrow-access users |
| Share is mostly scanned PDFs; CPU OCR of 50 GB takes days | Medium | Task 4 census gates OCR scope; `RAG_OCR_MAX_PAGES`; skip PDFs with text layer; OCR in background pass after text docs are live |
| Chunk count > 2M; Chroma memory | Low | Watch count in census; pgvector swap is retriever-only change after Task 9 |
| Streamlit session holds NAS password; leak via traceback/log | Medium | Never pass password past `auth/smb.py`; idle timeout; `log_event` allowlist of keys; review in Task 13 |
| Haiku summaries send 500 chars from every folder (incl. restricted) to API | Certain | Explicit item in security approval; Ollama fallback keeps `get_embeddings`/`ChatAnthropic` behind one factory |
| One dev, 6 weeks, 15 tasks | High | Phase 1 (Tasks 1-5) is a shippable product on its own; Tasks 12-14 can slip to week 7-8 without blocking pilot |
| SMB mount hiccup mid-index corrupts manifest | Low | Write manifest only after successful run; `nofail,_netdev` in fstab |

## Acceptance
- [ ] All tasks complete
- [ ] Validation passes
- [ ] Patterns mirrored, not reinvented
- [ ] `permissions.yaml` / `users.yaml` gone; no code path reads them
- [ ] No user password appears in `logs/`, tracebacks, or `manifest.json`
