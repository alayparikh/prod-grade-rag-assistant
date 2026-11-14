# Graph Report - .  (2026-11-13)

## Corpus Check
- 9 files · ~82,207 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1209 nodes · 1897 edges · 56 communities (50 shown, 6 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 58 edges (avg confidence: 0.87)
- Token cost: 113,123 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Project Rules & README Concepts|Project Rules & README Concepts]]
- [[_COMMUNITY_Demo Browser Check & Orders Templates|Demo Browser Check & Orders Templates]]
- [[_COMMUNITY_Demo Agent Runs & Reranking|Demo Agent Runs & Reranking]]
- [[_COMMUNITY_Agent Tests|Agent Tests]]
- [[_COMMUNITY_Pipeline Tests|Pipeline Tests]]
- [[_COMMUNITY_Eval Harness & Grading|Eval Harness & Grading]]
- [[_COMMUNITY_Access Control Tests|Access Control Tests]]
- [[_COMMUNITY_RAG Unit Tests|RAG Unit Tests]]
- [[_COMMUNITY_Orders NL-to-SQL Tests|Orders NL-to-SQL Tests]]
- [[_COMMUNITY_Agent Loop & Tracing|Agent Loop & Tracing]]
- [[_COMMUNITY_FTS Keyword Retriever & Tests|FTS Keyword Retriever & Tests]]
- [[_COMMUNITY_Index-time ACL Tagging|Index-time ACL Tagging]]
- [[_COMMUNITY_Crawler Tests|Crawler Tests]]
- [[_COMMUNITY_Demo Page Wiring|Demo Page Wiring]]
- [[_COMMUNITY_Indexer Entrypoint, Summaries & Health|Indexer Entrypoint, Summaries & Health]]
- [[_COMMUNITY_Fixture People & Architecture|Fixture People & Architecture]]
- [[_COMMUNITY_Orders SQL Guard & Golden Fixtures|Orders SQL Guard & Golden Fixtures]]
- [[_COMMUNITY_Indexing & Manifest|Indexing & Manifest]]
- [[_COMMUNITY_NAS Search Plan & Scale Paths|NAS Search Plan & Scale Paths]]
- [[_COMMUNITY_Order Lifecycle Policies|Order Lifecycle Policies]]
- [[_COMMUNITY_Loader Tests|Loader Tests]]
- [[_COMMUNITY_Router Tests|Router Tests]]
- [[_COMMUNITY_Summary Tests|Summary Tests]]
- [[_COMMUNITY_Demo Agent Chat Rendering|Demo Agent Chat Rendering]]
- [[_COMMUNITY_SMB Auth & Access Checks|SMB Auth & Access Checks]]
- [[_COMMUNITY_Streamlit App|Streamlit App]]
- [[_COMMUNITY_Answering & Access Filtering|Answering & Access Filtering]]
- [[_COMMUNITY_Manifest Tests|Manifest Tests]]
- [[_COMMUNITY_Crawler & Census|Crawler & Census]]
- [[_COMMUNITY_Deploy Guide|Deploy Guide]]
- [[_COMMUNITY_Answer Cache|Answer Cache]]
- [[_COMMUNITY_Retriever Build & Sizing|Retriever Build & Sizing]]
- [[_COMMUNITY_Demo Orders X-ray|Demo Orders X-ray]]
- [[_COMMUNITY_Demo Browser Search Engine|Demo Browser Search Engine]]
- [[_COMMUNITY_Orders Fixture Generator|Orders Fixture Generator]]
- [[_COMMUNITY_Demo Agent Chat Conversation|Demo Agent Chat Conversation]]
- [[_COMMUNITY_Answer Chain|Answer Chain]]
- [[_COMMUNITY_Demo Roles & BM25|Demo Roles & BM25]]
- [[_COMMUNITY_Demo 3D Scene|Demo 3D Scene]]
- [[_COMMUNITY_Product Catalog|Product Catalog]]
- [[_COMMUNITY_Security Policy|Security Policy]]
- [[_COMMUNITY_Onboarding Guide|Onboarding Guide]]
- [[_COMMUNITY_Networking Runbook|Networking Runbook]]
- [[_COMMUNITY_Testing Standards|Testing Standards]]
- [[_COMMUNITY_Offline Extractive Answers|Offline Extractive Answers]]
- [[_COMMUNITY_Demo Document Search UI|Demo Document Search UI]]
- [[_COMMUNITY_Demo package.json|Demo package.json]]
- [[_COMMUNITY_Test Isolation|Test Isolation]]
- [[_COMMUNITY_Demo Roles|Demo Roles]]
- [[_COMMUNITY_Pipeline Package|Pipeline Package]]
- [[_COMMUNITY_Golden Set Example|Golden Set Example]]
- [[_COMMUNITY_Demo Favicon|Demo Favicon]]

## God Nodes (most connected - your core abstractions)
1. `ask()` - 30 edges
2. `final()` - 28 edges
3. `search()` - 17 edges
4. `Tasks` - 17 edges
5. `_StubLLM` - 14 edges
6. `sync_vectorstore()` - 13 edges
7. `In-browser demo README (Acme Robotics)` - 13 edges
8. `build()` - 12 edges
9. `build_chain()` - 12 edges
10. `TestGroupsFromDescriptor` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Agent cases (mode: agent)` --references--> `answer_agent_question()`  [EXTRACTED]
  eval/fixtures/golden_set.yaml → agent.py
- `Agent Regression Evals (code-graded, free, pass^3 = 100%)` --references--> `check()`  [EXTRACTED]
  .claude/evals/agent.md → demo/agent_runs.py
- `Agent Capability Evals (--live tier, pass@3 >= 90%)` --references--> `Groundedness`  [INFERRED]
  .claude/evals/agent.md → eval/run_eval.py
- `Query pipeline (only Claude usage)` --references--> `answer_question()`  [EXTRACTED]
  README.md → rag.py
- `answer_question() as single guardrail entry point` --rationale_for--> `answer_question()`  [EXTRACTED]
  README.md → rag.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Guardrail chain inside answer_question()** — readme_answer_cache, readme_empty_context_short_circuit, readme_nas_access_check, readme_cross_encoder_rerank, readme_relevance_grading, readme_source_attribution, readme_secret_redaction, readme_event_logging [EXTRACTED 1.00]
- **Demo agent answering without a model (saved runs, live runs, back-and-forth)** — demo_readme_agent_chat, demo_readme_saved_runs, demo_readme_live_runs, demo_readme_back_and_forth_rule, demo_readme_typed_question_matching, web_index_agent_chat_panel [EXTRACTED 1.00]
- **Production-scale coding rules** — claude_never_load_whole_corpus, claude_incremental_idempotent_indexing, claude_backends_behind_interfaces, claude_bound_everything, claude_stateless_app_processes, claude_security_outside_model, claude_measure_it [EXTRACTED 1.00]

## Communities (56 total, 6 thin omitted)

### Community 0 - "Project Rules & README Concepts"
Cohesion: 0.05
Nodes (65): CLAUDE.md Agent Instructions, Agent: opt-in bounded tool loop now, router plus shared answer cache at scale, Keep backends behind interfaces, Bound everything (row limits, timeouts, token budgets, step caps), Answer cache and rate limit: in-process now, Redis at scale, Demo agent answers: saved runs plus fixed-step live runs now, hosted agent endpoint at scale, Keep docs and UI in sync checklist, Indexer: single process now, per-file queue jobs at scale (+57 more)

### Community 1 - "Demo Browser Check & Orders Templates"
Cohesion: 0.05
Nodes (52): agentFile, db, engine, golden, index, NEEDS_A_MODEL, octx, require (+44 more)

### Community 2 - "Demo Agent Runs & Reranking"
Cohesion: 0.06
Nodes (46): Agent Example Script (agent_examples.yaml), Per-role tool-call plans, build(), check(), CutoffReranker, demo_items(), doc_files(), example_run() (+38 more)

### Community 3 - "Agent Tests"
Cohesion: 0.10
Nodes (18): ask(), chain(), doc(), final(), Agent tests.  The loop lets the model choose its own steps, so nothing here trus, Plays back a fixed list of turns; each turn is a list of (tool, args).     Recor, Every tool result the model was shown, in order., ScriptedLLM (+10 more)

### Community 4 - "Pipeline Tests"
Cohesion: 0.06
Nodes (17): _Answer, doc(), _FakeCrossEncoder, _Grader, Tests for the pipeline stages: chunking, reranking, grading/retry, the answer ca, Supports the standalone/retrieve protocol; answers per query., _RecordingStore, _Retriever (+9 more)

### Community 5 - "Eval Harness & Grading"
Cohesion: 0.07
Nodes (39): BaseModel, _agent_evidence(), check_agent_result(), check_expectations(), contains_all(), contains_any(), _grade(), Groundedness (+31 more)

### Community 6 - "Access Control Tests"
Cohesion: 0.06
Nodes (15): _chain(), doc(), _FakeRetriever, Authorization tests: path translation, the per-file access filter, and the guard, Stands in for the structured-output LLM call so the test can assert     on exact, _RecordingAnswerChain, _StubSession, TestAccessChecker (+7 more)

### Community 7 - "RAG Unit Tests"
Cohesion: 0.05
Nodes (13): Unit tests for the pure functions in rag.py.  These exist because the retrieval, compute_k() being correct is useless if build_retriever() ignores it.     A reve, Guards the BM25 tokenizer. The original bug: the default whitespace     tokenize, The model self-reports which sources it used; a path it names that     wasn't ac, TestBuildGroupFilter, TestBuildRetrieverUsesComputedK, TestComputeK, TestGroupsForPath (+5 more)

### Community 8 - "Orders NL-to-SQL Tests"
Cohesion: 0.06
Nodes (11): ask(), FakeLLM, The order path's safety rails: they must hold whatever SQL Claude writes., Writes the SQL it was given and answers with a fixed sentence., Same expectations as the role cases in eval/fixtures/golden_set.yaml., StubRetriever, TestAnswerOrderQuestion, TestDatabase (+3 more)

### Community 9 - "Agent Loop & Tracing"
Cohesion: 0.07
Nodes (28): answer_agent_question(), _bound_hit(), _execute(), _failed(), The agent: questions that need more than one step or more than one source.  rag., What one tool call produced. `text` goes back to the model; `detail`     is for, The tools for one question, with the asker's identity bound in., The ask_user / final_answer call, if it is the only call of the turn.     One se (+20 more)

### Community 10 - "FTS Keyword Retriever & Tests"
Cohesion: 0.07
Nodes (18): BaseRetriever, connect(), count(), default_db_path(), FtsRetriever, Persistent keyword index for hybrid retrieval.  Replaces the in-memory BM25 retr, LangChain retriever over the SQLite index, so it can slot into the     existing, search() (+10 more)

### Community 11 - "Index-time ACL Tagging"
Cohesion: 0.08
Nodes (15): grants_read(), groups_for_user(), groups_from_descriptor(), Stage 1 of authorization: index-time ACL tagging.  Reads each folder's SMB secur, sanitize_group(), allow(), deny(), descriptor() (+7 more)

### Community 12 - "Crawler Tests"
Cohesion: 0.05
Nodes (10): paths_in(), Crawler and file-search tests.  The crawler's whole value is that it does not re, TestBuildMatchExpression, TestCensus, TestConnect, TestCrawl, TestExtensionListsAgree, TestFallbackParsing (+2 more)

### Community 13 - "Demo Page Wiring"
Cohesion: 0.06
Nodes (30): abutton, aform, agentSeg, ainput, alist, alog, button, CASES (+22 more)

### Community 14 - "Indexer Entrypoint, Summaries & Health"
Cohesion: 0.10
Nodes (25): main(), Indexer entrypoint: `python -m indexer`.  Runs on the host next to the NAS, on a, run_crawl(), run_forever(), run_summaries(), seconds_until(), ensure_schema(), _evidence() (+17 more)

### Community 15 - "Fixture People & Architecture"
Cohesion: 0.06
Nodes (30): Atlas Project, Sam Rivera, Alex Chen, Nimbus Project, SLO-based Alerting, Boundaries, Caching, Event Bus (+22 more)

### Community 16 - "Orders SQL Guard & Golden Fixtures"
Cohesion: 0.07
Nodes (31): Per-role scripted answers and cited sources, Fixture Golden Set, Agent cases (mode: agent), Agent permission cases (contractor, engineer, hr), My-orders cases (orders-my-orders, orders-our-orders, agent-my-orders), Orders cases (mode: orders), Changing the fixtures, Fixed today (2026-10-28) in the meta table (+23 more)

### Community 17 - "Indexing & Manifest"
Cohesion: 0.12
Nodes (31): Incremental and idempotent indexing, _as_stamp(), discover_files(), file_hash(), file_stamp(), get_embeddings(), _get_event_logger(), get_vectorstore() (+23 more)

### Community 18 - "NAS Search Plan & Scale Paths"
Cohesion: 0.06
Nodes (32): Keyword search: in-process BM25 now, OpenSearch/Postgres full-text at scale, permissions.yaml Folder-Group Mapping, Acceptance, Index-time ACL Tagging Pre-filter, Files to Change, Folder Summaries (Haiku), SQLite FTS5 Metadata Index, Patterns to Mirror (+24 more)

### Community 19 - "Order Lifecycle Policies"
Cohesion: 0.07
Nodes (26): cancelled, delivered, on_hold, Order Lifecycle, picking, placed, returned, shipped (+18 more)

### Community 20 - "Loader Tests"
Cohesion: 0.07
Nodes (7): Loader tests for the formats a shared drive is actually full of.  Each loader is, TestLoadEml, TestLoaderErrorsAreSurvivable, TestLoadFileDispatch, TestLoadPptx, TestLoadXlsx, TestSecretRedaction

### Community 21 - "Router Tests"
Cohesion: 0.09
Nodes (7): Router tests.  The router is only worth having if it is right about the cases th, Returns a fixed Route, like with_structured_output would., _StubLLM, TestCanonicalSources, TestEmbeddingModelOverride, TestFallbackRouting, TestLlmRouting

### Community 22 - "Summary Tests"
Cohesion: 0.13
Nodes (5): Folder-summary tests.  The expensive mistake here is re-summarising folders that, _StubLLM, TestMatchingFolders, TestReadHead, TestSummarizeFolders

### Community 23 - "Demo Agent Chat Rendering"
Cohesion: 0.18
Nodes (18): answerHtml(), escape(), evidenceHtml(), gap(), isRecorded(), normalise(), numbersIn(), ordersIn() (+10 more)

### Community 24 - "SMB Auth & Access Checks"
Cohesion: 0.13
Nodes (13): AccessChecker, login(), nas_links(), NasSession, NasUnavailable, _open_for_read(), NAS-backed authentication and per-file authorization over SMB.  The NAS is the o, Callable wrapper around NasSession.can_read with a per-question memo.     Retrie (+5 more)

### Community 25 - "Streamlit App"
Cohesion: 0.24
Nodes (17): access_checker(), allow_request(), current_order_role(), current_session(), load_chain(), login_form(), meta_db(), order_role_for() (+9 more)

### Community 26 - "Answering & Access Filtering"
Cohesion: 0.19
Nodes (13): answer_order_question(), answer_question(), _api_error_message(), _filter_by_access(), _generate(), HistoryAwareRetriever, Rewrites a follow-up into a standalone question, then retrieves.     Done by han, redact_secrets() (+5 more)

### Community 27 - "Manifest Tests"
Cohesion: 0.12
Nodes (5): Incremental-sync tests.  On a 50 GB network share the difference between "stat e, TestFileHash, TestFileStamp, TestLegacyManifest, TestPathNormalisation

### Community 28 - "Crawler & Census"
Cohesion: 0.22
Nodes (13): connect(), crawl(), _delete(), _exclude_globs(), format_census(), human_bytes(), is_excluded_dir(), is_excluded_file() (+5 more)

### Community 29 - "Deploy Guide"
Cohesion: 0.17
Nodes (12): 1. Decide where it runs, 2. Prepare the Synology, 3a. Install on the Synology, 3b. Install on a separate Linux host, 4. First run: census before you index, 5. Name your roster files, 6. Verify before letting anyone in, 7. What IT needs to do (+4 more)

### Community 30 - "Answer Cache"
Cohesion: 0.27
Nodes (4): AnswerCache, normalize_question(), Answer cache.  Exact-match on a normalised question, scoped to one user and one, still_permitted()

### Community 31 - "Retriever Build & Sizing"
Cohesion: 0.25
Nodes (10): build_chain(), build_group_filter(), build_retriever(), compute_k(), _corpus_size(), llm_enabled(), main(), RagChain (+2 more)

### Community 32 - "Demo Orders X-ray"
Cohesion: 0.24
Nodes (10): askOrders(), cell(), chip(), escape(), fmt(), highlight(), oxray(), short() (+2 more)

### Community 33 - "Demo Browser Search Engine"
Cohesion: 0.31
Nodes (3): Engine, fuse(), tokenize()

### Community 34 - "Orders Fixture Generator"
Cohesion: 0.43
Nodes (7): build(), business_days(), main(), q(), Generate eval/fixtures/orders.sql: Acme Robotics' fictional orders database.  De, A plausible tracking timeline for one order., shipments()

### Community 35 - "Demo Agent Chat Conversation"
Cohesion: 0.29
Nodes (8): followUp(), addMessage(), agentAllowed(), askAgent(), noteRole(), showAgentAccess(), toEnd(), toggleChat()

### Community 36 - "Answer Chain"
Cohesion: 0.38
Nodes (3): AnswerChain, _format_context(), Wraps a structured-output LLM call so sources_used is a guaranteed     schema fi

### Community 37 - "Demo Roles & BM25"
Cohesion: 0.29
Nodes (5): allowed(), setRole(), showAccess(), Bm25, queryTerms()

### Community 38 - "Demo 3D Scene"
Cohesion: 0.43
Nodes (5): COLORS, glyphPoints(), mountScene(), rand(), slipTexture()

### Community 39 - "Product Catalog"
Cohesion: 0.33
Nodes (5): Acme Robotics Product Catalog, Fleet Console, PR-200 Tote Runner, PR-400 Pallet Runner, PR-900 Heavy Runner

### Community 40 - "Security Policy"
Cohesion: 0.33
Nodes (5): Access Review, Classification, Data Classification, Dependencies, Security Policy

### Community 41 - "Onboarding Guide"
Cohesion: 0.40
Nodes (4): Engineering Onboarding Guide, First Week, Local Development, Team Rituals

### Community 42 - "Networking Runbook"
Cohesion: 0.40
Nodes (4): Certificates, Firewall, Load Balancer, Networking Runbook

### Community 43 - "Testing Standards"
Cohesion: 0.40
Nodes (4): Flaky Tests, Integration Tests, Testing Standards, Unit Tests

### Community 44 - "Offline Extractive Answers"
Cohesion: 0.40
Nodes (3): AnswerWithSources, ExtractiveAnswerChain, Offline answerer: no LLM, so the "answer" is the top reranked     passages, quot

### Community 45 - "Demo Document Search UI"
Cohesion: 0.50
Nodes (4): ask(), render(), setStatus(), xray()

## Knowledge Gaps
- **147 isolated node(s):** `private`, `type`, `ORDER_ROLES`, `STATUS_WORDS`, `MONTHS` (+142 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Agent Regression Evals (code-graded, free, pass^3 = 100%)` connect `Demo Browser Check & Orders Templates` to `Demo Agent Runs & Reranking`, `Agent Tests`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `answer_question()` connect `Answering & Access Filtering` to `Project Rules & README Concepts`, `Streamlit App`, `Indexing & Manifest`, `Retriever Build & Sizing`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `Query pipeline (only Claude usage)` connect `Project Rules & README Concepts` to `Answering & Access Filtering`, `NAS Search Plan & Scale Paths`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **What connects `The agent: questions that need more than one step or more than one source.  rag.`, `What one tool call produced. `text` goes back to the model; `detail`     is for`, `The tools for one question, with the asker's identity bound in.` to the rest of the system?**
  _238 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Project Rules & README Concepts` be split into smaller, more focused modules?**
  _Cohesion score 0.052884615384615384 - nodes in this community are weakly interconnected._
- **Should `Demo Browser Check & Orders Templates` be split into smaller, more focused modules?**
  _Cohesion score 0.05288207297726071 - nodes in this community are weakly interconnected._
- **Should `Demo Agent Runs & Reranking` be split into smaller, more focused modules?**
  _Cohesion score 0.056261343012704176 - nodes in this community are weakly interconnected._