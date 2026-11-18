# Graph Report - .  (2026-11-15)

## Corpus Check
- 30 files · ~99,264 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1393 nodes · 2232 edges · 97 communities (77 shown, 20 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 99 edges (avg confidence: 0.84)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Agent Tests|Agent Tests]]
- [[_COMMUNITY_Access Control Tests|Access Control Tests]]
- [[_COMMUNITY_RAG Unit Tests|RAG Unit Tests]]
- [[_COMMUNITY_Grading & Structured Output|Grading & Structured Output]]
- [[_COMMUNITY_Agent Loop & Tools|Agent Loop & Tools]]
- [[_COMMUNITY_Orders NL-to-SQL Tests|Orders NL-to-SQL Tests]]
- [[_COMMUNITY_Index-time ACL Tagging|Index-time ACL Tagging]]
- [[_COMMUNITY_Demo Page Wiring|Demo Page Wiring]]
- [[_COMMUNITY_Fixture People & Architecture|Fixture People & Architecture]]
- [[_COMMUNITY_Demo Agent Runs|Demo Agent Runs]]
- [[_COMMUNITY_Folder Summaries|Folder Summaries]]
- [[_COMMUNITY_Indexer Entrypoint & Health|Indexer Entrypoint & Health]]
- [[_COMMUNITY_Order Lifecycle Policies|Order Lifecycle Policies]]
- [[_COMMUNITY_NAS Search Plan & Permissions|NAS Search Plan & Permissions]]
- [[_COMMUNITY_Manifest & File Stamps|Manifest & File Stamps]]
- [[_COMMUNITY_Loader Tests|Loader Tests]]
- [[_COMMUNITY_Keyword Index Tests|Keyword Index Tests]]
- [[_COMMUNITY_Demo README & Browser Path|Demo README & Browser Path]]
- [[_COMMUNITY_Scale Benchmark|Scale Benchmark]]
- [[_COMMUNITY_Demo Agent Chat Rendering|Demo Agent Chat Rendering]]
- [[_COMMUNITY_SMB Auth & Access Checks|SMB Auth & Access Checks]]
- [[_COMMUNITY_Streamlit App & Rate Limit|Streamlit App & Rate Limit]]
- [[_COMMUNITY_Eval Metrics & Baselines|Eval Metrics & Baselines]]
- [[_COMMUNITY_Eval Runner & Graders|Eval Runner & Graders]]
- [[_COMMUNITY_Demo Browser Check|Demo Browser Check]]
- [[_COMMUNITY_Demo Orders Translator|Demo Orders Translator]]
- [[_COMMUNITY_Project Rules (CLAUDE.md)|Project Rules (CLAUDE.md)]]
- [[_COMMUNITY_Manifest Tests|Manifest Tests]]
- [[_COMMUNITY_Demo Live Agent Runs|Demo Live Agent Runs]]
- [[_COMMUNITY_Adversarial Corpus Builder|Adversarial Corpus Builder]]
- [[_COMMUNITY_Crawler & Census|Crawler & Census]]
- [[_COMMUNITY_Model Call Bounds & Faults|Model Call Bounds & Faults]]
- [[_COMMUNITY_Answering & Access Filtering|Answering & Access Filtering]]
- [[_COMMUNITY_FTS Keyword Retriever|FTS Keyword Retriever]]
- [[_COMMUNITY_Agent Load Test|Agent Load Test]]
- [[_COMMUNITY_Per-user Rate Limiter|Per-user Rate Limiter]]
- [[_COMMUNITY_Keyword Scale Fault Tests|Keyword Scale Fault Tests]]
- [[_COMMUNITY_Orders DB & SQL Guard|Orders DB & SQL Guard]]
- [[_COMMUNITY_Pipeline Retriever Stubs|Pipeline Retriever Stubs]]
- [[_COMMUNITY_Demo Browser Search Engine|Demo Browser Search Engine]]
- [[_COMMUNITY_SQL Load Test|SQL Load Test]]
- [[_COMMUNITY_Answer Cache|Answer Cache]]
- [[_COMMUNITY_Retriever Build & Sizing|Retriever Build & Sizing]]
- [[_COMMUNITY_Pipeline Stage Tests|Pipeline Stage Tests]]
- [[_COMMUNITY_Injection & Defect Catalogue|Injection & Defect Catalogue]]
- [[_COMMUNITY_Production Eval Definition|Production Eval Definition]]
- [[_COMMUNITY_File Metadata Search|File Metadata Search]]
- [[_COMMUNITY_Chunking Tests|Chunking Tests]]
- [[_COMMUNITY_SQL Attack Tests|SQL Attack Tests]]
- [[_COMMUNITY_App Orders View|App Orders View]]
- [[_COMMUNITY_SQL Attack Corpus & Findings|SQL Attack Corpus & Findings]]
- [[_COMMUNITY_Demo Index Build|Demo Index Build]]
- [[_COMMUNITY_Synology Deploy Guide|Synology Deploy Guide]]
- [[_COMMUNITY_Ingestion Failures & Rollback|Ingestion Failures & Rollback]]
- [[_COMMUNITY_Crawler Tests|Crawler Tests]]
- [[_COMMUNITY_File Search Tests|File Search Tests]]
- [[_COMMUNITY_Answer Cache Tests|Answer Cache Tests]]
- [[_COMMUNITY_Fixture Golden Set|Fixture Golden Set]]
- [[_COMMUNITY_Orders Fixture Generator|Orders Fixture Generator]]
- [[_COMMUNITY_Fault Test Stubs|Fault Test Stubs]]
- [[_COMMUNITY_Synthetic Corpus Generator|Synthetic Corpus Generator]]
- [[_COMMUNITY_Crawler Connection Tests|Crawler Connection Tests]]
- [[_COMMUNITY_Demo Agent Chat Conversation|Demo Agent Chat Conversation]]
- [[_COMMUNITY_Demo Saved Runs & Pages|Demo Saved Runs & Pages]]
- [[_COMMUNITY_Agent Eval Definition|Agent Eval Definition]]
- [[_COMMUNITY_Reranker|Reranker]]
- [[_COMMUNITY_Answer Chain|Answer Chain]]
- [[_COMMUNITY_API Failure Fault Tests|API Failure Fault Tests]]
- [[_COMMUNITY_Indexing Resume Tests|Indexing Resume Tests]]
- [[_COMMUNITY_Demo Roles & Status|Demo Roles & Status]]
- [[_COMMUNITY_Demo 3D Scene|Demo 3D Scene]]
- [[_COMMUNITY_Product Catalog|Product Catalog]]
- [[_COMMUNITY_Security Policy|Security Policy]]
- [[_COMMUNITY_Eval Runner CLI & CI|Eval Runner CLI & CI]]
- [[_COMMUNITY_Onboarding Guide|Onboarding Guide]]
- [[_COMMUNITY_Networking Runbook|Networking Runbook]]
- [[_COMMUNITY_Testing Standards|Testing Standards]]
- [[_COMMUNITY_Offline Extractive Answers|Offline Extractive Answers]]
- [[_COMMUNITY_Match Expression Tests|Match Expression Tests]]
- [[_COMMUNITY_Sync Re-embed Tests|Sync Re-embed Tests]]
- [[_COMMUNITY_Health Tests|Health Tests]]
- [[_COMMUNITY_Agent Bound Fault Tests|Agent Bound Fault Tests]]
- [[_COMMUNITY_Demo Orders Translator Class|Demo Orders Translator Class]]
- [[_COMMUNITY_Demo package.json|Demo package.json]]
- [[_COMMUNITY_Test Isolation|Test Isolation]]
- [[_COMMUNITY_Census Tests|Census Tests]]
- [[_COMMUNITY_Fallback Parsing Tests|Fallback Parsing Tests]]
- [[_COMMUNITY_Walk Tests|Walk Tests]]
- [[_COMMUNITY_Pipeline Package|Pipeline Package]]
- [[_COMMUNITY_Docker Compose|Docker Compose]]
- [[_COMMUNITY_Golden Set Example|Golden Set Example]]
- [[_COMMUNITY_Python Requirements|Python Requirements]]
- [[_COMMUNITY_Demo Favicon|Demo Favicon]]

## God Nodes (most connected - your core abstractions)
1. `ask()` - 30 edges
2. `final()` - 28 edges
3. `search()` - 17 edges
4. `Tasks` - 17 edges
5. `sync_vectorstore()` - 15 edges
6. `_StubLLM` - 14 edges
7. `bounded()` - 14 edges
8. `document()` - 13 edges
9. `build_chain()` - 13 edges
10. `build()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Ingest Pipeline` --references--> `sync_vectorstore()`  [INFERRED]
  README.md → rag.py
- `Current Choice vs Scale Target Table` --references--> `answer_agent_question()`  [INFERRED]
  CLAUDE.md → agent.py
- `Model and Agent Traffic Failures` --references--> `answer_agent_question()`  [INFERRED]
  PRODUCTION_READINESS.md → agent.py
- `Ask the Agent Mode` --references--> `answer_agent_question()`  [INFERRED]
  README.md → agent.py
- `Model and Agent Traffic Failures` --references--> `ChaosModel`  [INFERRED]
  PRODUCTION_READINESS.md → eval/load/agent_load.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Security enforced outside the model** — production_readiness_guards_outside_model, search_orders_guard, adversarial_sql_attacks_role_escape_cases, readme_nas_authorization, adversarial_injection [INFERRED 0.85]
- **Free production-shape CI gate** — workflows_ci_test_job, scale_bench_bench_query, load_sql_load_run_load, load_agent_load_chaosmodel, eval_metrics_compare, evals_production_regression_evals [EXTRACTED 1.00]
- **Live prompt-injection eval flow** — adversarial_build_corpus_build, docs_meeting_minutes_q3, docs_vendor_notice, adversarial_injection, workflows_ci_live_eval_job [EXTRACTED 1.00]

## Communities (97 total, 20 thin omitted)

### Community 0 - "Agent Tests"
Cohesion: 0.10
Nodes (18): ask(), chain(), doc(), final(), Agent tests.  The loop lets the model choose its own steps, so nothing here trus, Plays back a fixed list of turns; each turn is a list of (tool, args).     Recor, Every tool result the model was shown, in order., ScriptedLLM (+10 more)

### Community 1 - "Access Control Tests"
Cohesion: 0.06
Nodes (15): _chain(), doc(), _FakeRetriever, Authorization tests: path translation, the per-file access filter, and the guard, Stands in for the structured-output LLM call so the test can assert     on exact, _RecordingAnswerChain, _StubSession, TestAccessChecker (+7 more)

### Community 2 - "RAG Unit Tests"
Cohesion: 0.05
Nodes (13): Unit tests for the pure functions in rag.py.  These exist because the retrieval, compute_k() being correct is useless if build_retriever() ignores it.     A reve, Guards the BM25 tokenizer. The original bug: the default whitespace     tokenize, The model self-reports which sources it used; a path it names that     wasn't ac, TestBuildGroupFilter, TestBuildRetrieverUsesComputedK, TestComputeK, TestGroupsForPath (+5 more)

### Community 3 - "Grading & Structured Output"
Cohesion: 0.05
Nodes (18): BaseModel, _numbered(), QueryRewriter, Relevance grading and query rewriting - the corrective-retrieval loop.  After re, RelevanceGrader, RelevantChunks, Sql, classify() (+10 more)

### Community 4 - "Agent Loop & Tools"
Cohesion: 0.07
Nodes (29): answer_agent_question(), _bound_hit(), _execute(), _failed(), The agent: questions that need more than one step or more than one source.  rag., What one tool call produced. `text` goes back to the model; `detail`     is for, The tools for one question, with the asker's identity bound in., The ask_user / final_answer call, if it is the only call of the turn.     One se (+21 more)

### Community 5 - "Orders NL-to-SQL Tests"
Cohesion: 0.06
Nodes (11): ask(), FakeLLM, The order path's safety rails: they must hold whatever SQL Claude writes., Writes the SQL it was given and answers with a fixed sentence., Same expectations as the role cases in eval/fixtures/golden_set.yaml., StubRetriever, TestAnswerOrderQuestion, TestDatabase (+3 more)

### Community 6 - "Index-time ACL Tagging"
Cohesion: 0.08
Nodes (15): grants_read(), groups_for_user(), groups_from_descriptor(), Stage 1 of authorization: index-time ACL tagging.  Reads each folder's SMB secur, sanitize_group(), allow(), deny(), descriptor() (+7 more)

### Community 7 - "Demo Page Wiring"
Cohesion: 0.06
Nodes (30): abutton, aform, agentSeg, ainput, alist, alog, button, CASES (+22 more)

### Community 8 - "Fixture People & Architecture"
Cohesion: 0.06
Nodes (30): Atlas Project, Sam Rivera, Alex Chen, Nimbus Project, SLO-based Alerting, Boundaries, Caching, Event Bus (+22 more)

### Community 9 - "Demo Agent Runs"
Cohesion: 0.11
Nodes (28): Agent Example Script (agent_examples.yaml), build(), check(), CutoffReranker, demo_items(), doc_files(), example_run(), fingerprint() (+20 more)

### Community 10 - "Folder Summaries"
Cohesion: 0.09
Nodes (14): ensure_schema(), _evidence(), fingerprint(), folders_with_files(), matching_folders(), _one_line(), Layer 2: one-line summaries of what each folder holds.  A disorganized share hid, read_head() (+6 more)

### Community 11 - "Indexer Entrypoint & Health"
Cohesion: 0.11
Nodes (21): Readiness Probe (pipeline.health --ready), main(), Indexer entrypoint: `python -m indexer`.  Runs on the host next to the NAS, on a, run_crawl(), run_forever(), run_summaries(), seconds_until(), check() (+13 more)

### Community 12 - "Order Lifecycle Policies"
Cohesion: 0.07
Nodes (26): cancelled, delivered, on_hold, Order Lifecycle, picking, placed, returned, shipped (+18 more)

### Community 13 - "NAS Search Plan & Permissions"
Cohesion: 0.07
Nodes (29): permissions.yaml Folder-Group Mapping, Acceptance, Index-time ACL Tagging Pre-filter, Files to Change, Folder Summaries (Haiku), SQLite FTS5 Metadata Index, Patterns to Mirror, Phase 0 (week 0, IT + owner): host, mount, accounts (+21 more)

### Community 14 - "Manifest & File Stamps"
Cohesion: 0.14
Nodes (28): _as_stamp(), discover_files(), file_hash(), file_stamp(), _get_event_logger(), groups_for_path(), _heading_marker(), _keyword_index() (+20 more)

### Community 15 - "Loader Tests"
Cohesion: 0.07
Nodes (7): Loader tests for the formats a shared drive is actually full of.  Each loader is, TestLoadEml, TestLoaderErrorsAreSurvivable, TestLoadFileDispatch, TestLoadPptx, TestLoadXlsx, TestSecretRedaction

### Community 16 - "Keyword Index Tests"
Cohesion: 0.11
Nodes (9): chunk(), Persistent keyword-index tests.  These carry over the guarantees the in-memory B, The bug this replaces: the default whitespace tokenizer made a whole     URL one, sources(), TestDefaultPath, TestGroupFiltering, TestLifecycle, TestRetrieverInterface (+1 more)

### Community 17 - "Demo README & Browser Path"
Cohesion: 0.13
Nodes (27): Demo agent chat panel (docked bottom-right, own role switch), Back-and-forth rule (short reply joined to the asked-back question), Browser query path (embed, meaning search, BM25, RRF, rerank, cutoff), check_search.mjs browser check (golden set, 64 agent checks, 18 order cases), Where company search breaks (live failure cases), In-browser demo README (Acme Robotics), index.json hand-off (chunks, embeddings, pipeline constants), Ingest in CI (Python) / query in browser (JavaScript) split (+19 more)

### Community 18 - "Scale Benchmark"
Cohesion: 0.16
Nodes (17): bench_index(), bench_query(), build(), check_index(), check_query(), corpus_paths(), CountingStore, dir_mb() (+9 more)

### Community 19 - "Demo Agent Chat Rendering"
Cohesion: 0.18
Nodes (18): answerHtml(), escape(), evidenceHtml(), gap(), isRecorded(), normalise(), numbersIn(), ordersIn() (+10 more)

### Community 20 - "SMB Auth & Access Checks"
Cohesion: 0.13
Nodes (13): AccessChecker, login(), nas_links(), NasSession, NasUnavailable, _open_for_read(), NAS-backed authentication and per-file authorization over SMB.  The NAS is the o, Callable wrapper around NasSession.can_read with a per-question memo.     Retrie (+5 more)

### Community 21 - "Streamlit App & Rate Limit"
Cohesion: 0.22
Nodes (19): access_checker(), allow_request(), current_order_role(), current_session(), load_chain(), login_form(), meta_db(), order_role_for() (+11 more)

### Community 22 - "Eval Metrics & Baselines"
Cohesion: 0.13
Nodes (18): baseline_view(), build_report(), compare(), expected_keywords(), first_hit_rank(), git_sha(), percentile(), Eval metrics: ranking quality, latency, cost, repeat reliability, baselines.  PA (+10 more)

### Community 23 - "Eval Runner & Graders"
Cohesion: 0.19
Nodes (19): _agent_evidence(), check_agent_result(), check_expectations(), contains_all(), contains_any(), _grade(), Groundedness, looks_like_refusal() (+11 more)

### Community 24 - "Demo Browser Check"
Cohesion: 0.12
Nodes (12): agentFile, db, engine, golden, index, NEEDS_A_MODEL, octx, require (+4 more)

### Community 25 - "Demo Orders Translator"
Cohesion: 0.16
Nodes (17): applyRole(), ASK_FOR, clarifyingQuestion(), daysBetween(), extractSlots(), findCustomer(), human(), INTENTS (+9 more)

### Community 26 - "Project Rules (CLAUDE.md)"
Cohesion: 0.13
Nodes (17): CLAUDE.md Agent Instructions, Keep Docs and UI in Sync Checklist, Use Knowledge Graph Before Reading Code, Build for Production Scale Rules, Verify Before Calling It Done, Pre-launch Verification Checklist, Acme Robotics Fixtures, orders.sql (generated, fixed today 2026-10-28) (+9 more)

### Community 27 - "Manifest Tests"
Cohesion: 0.12
Nodes (5): Incremental-sync tests.  On a 50 GB network share the difference between "stat e, TestFileHash, TestFileStamp, TestLegacyManifest, TestPathNormalisation

### Community 28 - "Demo Live Agent Runs"
Cohesion: 0.25
Nodes (16): answerFrom(), capital(), CLOSED, documentRun(), excerpt(), filledSql(), FILLER, human() (+8 more)

### Community 29 - "Adversarial Corpus Builder"
Cohesion: 0.18
Nodes (15): build(), main(), Assemble the adversarial corpus: the fixture docs plus injected documents., Prompt-injection Eval Cases, Document-injected Cases, Census Before Indexing, Q3 Ops Meeting Minutes (injection fixture), FreightLine Vendor Notice (injection fixture) (+7 more)

### Community 30 - "Crawler & Census"
Cohesion: 0.22
Nodes (13): connect(), crawl(), _delete(), _exclude_globs(), format_census(), human_bytes(), is_excluded_dir(), is_excluded_file() (+5 more)

### Community 31 - "Model Call Bounds & Faults"
Cohesion: 0.12
Nodes (5): Bounds for every model call.  Every ChatAnthropic in the app is built with `**bo, Fault injection and production bounds.  Each test breaks one thing a production, TestCorpusSizeIsBounded, TestOrdersUnavailable, TestRateLimit

### Community 32 - "Answering & Access Filtering"
Cohesion: 0.21
Nodes (12): answer_order_question(), answer_question(), _api_error_message(), _filter_by_access(), _generate(), HistoryAwareRetriever, Rewrites a follow-up into a standalone question, then retrieves.     Done by han, redact_secrets() (+4 more)

### Community 33 - "FTS Keyword Retriever"
Cohesion: 0.17
Nodes (11): BaseRetriever, connect(), count(), default_db_path(), delete_source(), FtsRetriever, _in_batches(), Persistent keyword index for hybrid retrieval.  Replaces the in-memory BM25 retr (+3 more)

### Community 34 - "Agent Load Test"
Cohesion: 0.19
Nodes (10): ask(), call(), ChaosModel, main(), pct(), pick_behaviour(), problems_for(), Agent load test: many concurrent agent questions with a misbehaving model. (+2 more)

### Community 35 - "Per-user Rate Limiter"
Cohesion: 0.18
Nodes (7): get_rate_limiter(), InProcessRateLimiter, RateLimiter, Request rate limit, keyed on the asker.  Keyed on the signed-in user, not the br, True if `key` may make another request now; records it if so., Sliding window per key. Thread-safe: Streamlit serves sessions from a     thread, One limiter per process (shared by every session).

### Community 36 - "Keyword Scale Fault Tests"
Cohesion: 0.18
Nodes (4): _built_index(), chunk(), TestKeywordScale, TestReadiness

### Community 37 - "Orders DB & SQL Guard"
Cohesion: 0.22
Nodes (12): connect(), ensure_db(), generate(), load_group_roles(), Order questions, answered from the orders database with SQL written by Claude., Build the database from the fixture SQL if it isn't there (dev and demo).     A, For a single held or late order: what to search the policy docs for., role_for_groups() (+4 more)

### Community 38 - "Pipeline Retriever Stubs"
Cohesion: 0.21
Nodes (5): _Grader, Supports the standalone/retrieve protocol; answers per query., _Retriever, _Rewriter, TestCorrectiveRetrieval

### Community 39 - "Demo Browser Search Engine"
Cohesion: 0.21
Nodes (5): Bm25, Engine, fuse(), queryTerms(), tokenize()

### Community 40 - "SQL Load Test"
Cohesion: 0.29
Nodes (10): attack_cases(), build_db(), check(), main(), one_question(), pct(), SQL load test: many concurrent order questions against a large orders DB.      p, The order path's database half, as answer_order_question runs it. (+2 more)

### Community 41 - "Answer Cache"
Cohesion: 0.27
Nodes (4): AnswerCache, normalize_question(), Answer cache.  Exact-match on a normalised question, scoped to one user and one, still_permitted()

### Community 42 - "Retriever Build & Sizing"
Cohesion: 0.27
Nodes (10): Retrieval Failures at Scale, build_chain(), build_group_filter(), build_retriever(), compute_k(), _corpus_size(), llm_enabled(), main() (+2 more)

### Community 43 - "Pipeline Stage Tests"
Cohesion: 0.20
Nodes (5): _FakeCrossEncoder, Tests for the pipeline stages: chunking, reranking, grading/retry, the answer ca, TestReranker, TestRetrieverAcrossThreads, TestStreaming

### Community 44 - "Injection & Defect Catalogue"
Cohesion: 0.22
Nodes (10): Question-injected Cases, Reject Cases (writes, base tables, comments, functions), zeroblob Attack, Defects Fixed in This Pass, Ask the Agent Mode, Four Modes (orders, agent, content, find a file), is_empty(), Constant time, unlike count(): checked on every retriever build. (+2 more)

### Community 45 - "Production Eval Definition"
Cohesion: 0.27
Nodes (10): Current Choice vs Scale Target Table, Production Eval Definition, Larger Capacity Runs (manual), pass^3 / pass@3 Targets, Production Readiness, Capacity Math for 100 TB, Eval Map, Measured Results (Apple M4, 2026-11-15) (+2 more)

### Community 46 - "File Metadata Search"
Cohesion: 0.29
Nodes (9): build_match_expression(), _fallback_terms(), FileQuery, _find_year(), parse_question(), Layer 1 query path: a question becomes a filename search.  Haiku turns "the flye, What the router extracts from a natural-language file request., Extract a FileQuery from the question. Falls back to the question's     own word (+1 more)

### Community 47 - "Chunking Tests"
Cohesion: 0.27
Nodes (3): doc(), TestChunking, TestOfflineMode

### Community 48 - "SQL Attack Tests"
Cohesion: 0.27
Nodes (5): Adversarial SQL corpus (eval/adversarial/sql_attacks.yaml).  The model writes th, run_as(), test_bounded_when_it_runs(), test_contractor_only_ever_sees_west(), test_hidden_columns_are_null_for_the_role()

### Community 49 - "App Orders View"
Cohesion: 0.24
Nodes (10): askOrders(), cell(), chip(), escape(), fmt(), highlight(), oxray(), short() (+2 more)

### Community 50 - "SQL Attack Corpus & Findings"
Cohesion: 0.25
Nodes (9): SQL Attack Corpus, Bounded Resource-exhaustion Cases, Role-escape Cases, Reflex Index Slowdown Finding, SQL and Orders Under Load Failures, apply_role(), GuardError, The SQL was refused before it ran. The message says why. (+1 more)

### Community 51 - "Demo Index Build"
Cohesion: 0.31
Nodes (7): build_orders_db(), main(), Build demo/web/index.json for the in-browser demo.  The browser cannot run Pytho, has_headings(), Structure-aware chunking.  Fixed-size windows cut straight through headings, run, section_path(), split_documents()

### Community 52 - "Synology Deploy Guide"
Cohesion: 0.25
Nodes (9): Deploying Against a Synology NAS, ACL Pre-filter (RAG_ACL_TAGGING), canonical_sources.yaml Roster Files, Read-only CIFS Mount (fstab, uid 10001), DSM Reverse Proxy TLS with WebSocket, Folder Summaries (--summaries), rag-indexer Read-only Service Account, Synology vs Separate Linux Host Decision (+1 more)

### Community 53 - "Ingestion Failures & Rollback"
Cohesion: 0.31
Nodes (9): Index Rollback by Volume Copy, Capability Evals (--live, paid), Blue/Green Index, Failure Catalogue, Ingestion Failures at Hundreds of TB, Known Gaps, Per-file Loader Isolation (gap), Manifest Checkpoint Every 200 Files (+1 more)

### Community 57 - "Fixture Golden Set"
Cohesion: 0.25
Nodes (8): Per-role scripted answers and cited sources, Fixture Golden Set, Agent cases (mode: agent), Agent permission cases (contractor, engineer, hr), demo_live cases (run live in the browser, five cases), My-orders cases (orders-my-orders, orders-our-orders, agent-my-orders), Orders cases (mode: orders), Story Orders (1042-1051)

### Community 58 - "Orders Fixture Generator"
Cohesion: 0.43
Nodes (7): build(), business_days(), main(), q(), Generate eval/fixtures/orders.sql: Acme Robotics' fictional orders database.  De, A plausible tracking timeline for one order., shipments()

### Community 59 - "Fault Test Stubs"
Cohesion: 0.25
Nodes (3): RunnableLambda, _NoopLLM, TestModelCallBounds

### Community 60 - "Synthetic Corpus Generator"
Cohesion: 0.39
Nodes (7): generate(), main(), needle(), Generate a synthetic document corpus of any size, for scale benchmarks.  Streams, Yields (relative_path, text, needle, owner), one file at a time., relative_path(), write()

### Community 61 - "Crawler Connection Tests"
Cohesion: 0.25
Nodes (3): Crawler and file-search tests.  The crawler's whole value is that it does not re, TestConnect, TestExtensionListsAgree

### Community 62 - "Demo Agent Chat Conversation"
Cohesion: 0.29
Nodes (8): followUp(), addMessage(), agentAllowed(), askAgent(), noteRole(), showAgentAccess(), toEnd(), toggleChat()

### Community 63 - "Demo Saved Runs & Pages"
Cohesion: 0.29
Nodes (7): Saved agent runs (agent.json built by agent_runs.py, scripted by agent_examples.yaml), Staleness fingerprint (agent_runs.py --check), Typed question matching (0.8 similarity + matching numbers), Paraphrases and look-alikes, Demo Site Pages Workflow, CI step: check browser search against the golden set, CI step: check the saved agent runs are current

### Community 64 - "Agent Eval Definition"
Cohesion: 0.29
Nodes (6): Capability evals (model-graded and code-graded, `--live` tier), EVAL DEFINITION: agent, Agent eval last run (2026-11-12: 288 pytest, 60 check_search, 15 retrieval passed), Last run (2026-11-12), Agent Regression Evals (code-graded, free, pass^3 = 100%), Regression evals (code-graded, free, every change)

### Community 65 - "Reranker"
Cohesion: 0.33
Nodes (3): get_reranker(), Cross-encoder reranking.  Retrieval is tuned for recall (wide k, two retrievers), Reranker

### Community 66 - "Answer Chain"
Cohesion: 0.38
Nodes (3): AnswerChain, _format_context(), Wraps a structured-output LLM call so sources_used is a guaranteed     schema fi

### Community 69 - "Demo Roles & Status"
Cohesion: 0.29
Nodes (7): allowed(), ask(), render(), setRole(), setStatus(), showAccess(), xray()

### Community 70 - "Demo 3D Scene"
Cohesion: 0.43
Nodes (5): COLORS, glyphPoints(), mountScene(), rand(), slipTexture()

### Community 71 - "Product Catalog"
Cohesion: 0.33
Nodes (5): Acme Robotics Product Catalog, Fleet Console, PR-200 Tote Runner, PR-400 Pallet Runner, PR-900 Heavy Runner

### Community 72 - "Security Policy"
Cohesion: 0.33
Nodes (5): Access Review, Classification, Data Classification, Dependencies, Security Policy

### Community 73 - "Eval Runner CLI & CI"
Cohesion: 0.47
Nodes (6): load_golden_set(), main(), print_report(), Regression Evals (code-graded, CI), golden_set.yaml, CI test job (free, every push)

### Community 74 - "Onboarding Guide"
Cohesion: 0.40
Nodes (4): Engineering Onboarding Guide, First Week, Local Development, Team Rituals

### Community 75 - "Networking Runbook"
Cohesion: 0.40
Nodes (4): Certificates, Firewall, Load Balancer, Networking Runbook

### Community 76 - "Testing Standards"
Cohesion: 0.40
Nodes (4): Flaky Tests, Integration Tests, Testing Standards, Unit Tests

### Community 77 - "Offline Extractive Answers"
Cohesion: 0.40
Nodes (3): AnswerWithSources, ExtractiveAnswerChain, Offline answerer: no LLM, so the "answer" is the top reranked     passages, quot

## Ambiguous Edges - Review These
- `Q3 Ops Meeting Minutes (injection fixture)` → `Story Orders (1042-1051)`  [AMBIGUOUS]
  eval/adversarial/docs/meeting_minutes_q3.md · relation: conceptually_related_to

## Knowledge Gaps
- **137 isolated node(s):** `private`, `type`, `ORDER_ROLES`, `STATUS_WORDS`, `MONTHS` (+132 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Q3 Ops Meeting Minutes (injection fixture)` and `Story Orders (1042-1051)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Agent Regression Evals (code-graded, free, pass^3 = 100%)` connect `Agent Eval Definition` to `Demo Browser Check`, `Demo Agent Runs`, `Agent Tests`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Why does `AnswerWithSources` connect `Offline Extractive Answers` to `Grading & Structured Output`, `Manifest & File Stamps`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `sync_vectorstore()` (e.g. with `Ingestion Failures at Hundreds of TB` and `Ingest Pipeline`) actually correct?**
  _`sync_vectorstore()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `NAS-backed authentication and per-file authorization over SMB.  The NAS is the o`, `The NAS could not be reached or refused the connection for a reason     other th`, `One logged-in user's SMB session. Holds the live connection objects     and the` to the rest of the system?**
  _256 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Agent Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.0955837870538415 - nodes in this community are weakly interconnected._
- **Should `Access Control Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.06105457909343201 - nodes in this community are weakly interconnected._