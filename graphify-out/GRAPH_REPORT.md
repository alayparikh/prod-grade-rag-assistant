# Graph Report - .  (2026-11-12)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1085 nodes · 1756 edges · 50 communities (44 shown, 6 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 62 edges (avg confidence: 0.83)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b97ca40a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Streamlit App & RAG Core|Streamlit App & RAG Core]]
- [[_COMMUNITY_Pipeline Tests|Pipeline Tests]]
- [[_COMMUNITY_Access Control Tests|Access Control Tests]]
- [[_COMMUNITY_RAG Unit Tests|RAG Unit Tests]]
- [[_COMMUNITY_Orders NL-to-SQL Tests|Orders NL-to-SQL Tests]]
- [[_COMMUNITY_Index-time ACL Tagging|Index-time ACL Tagging]]
- [[_COMMUNITY_Crawler Tests|Crawler Tests]]
- [[_COMMUNITY_Eval Harness|Eval Harness]]
- [[_COMMUNITY_Demo UI App|Demo UI App]]
- [[_COMMUNITY_Loader Tests|Loader Tests]]
- [[_COMMUNITY_Keyword Index Tests|Keyword Index Tests]]
- [[_COMMUNITY_Fixture People & Architecture|Fixture People & Architecture]]
- [[_COMMUNITY_Indexer Entrypoint & Summaries|Indexer Entrypoint & Summaries]]
- [[_COMMUNITY_Deploy, Demo & Eval Docs|Deploy, Demo & Eval Docs]]
- [[_COMMUNITY_Router Tests|Router Tests]]
- [[_COMMUNITY_Summary Tests|Summary Tests]]
- [[_COMMUNITY_SMB Auth & Access Checks|SMB Auth & Access Checks]]
- [[_COMMUNITY_Orders SQL Guard|Orders SQL Guard]]
- [[_COMMUNITY_Manifest Tests|Manifest Tests]]
- [[_COMMUNITY_Demo Index Build & Chunking|Demo Index Build & Chunking]]
- [[_COMMUNITY_Crawler & Census|Crawler & Census]]
- [[_COMMUNITY_Demo Orders Templates|Demo Orders Templates]]
- [[_COMMUNITY_Demo Browser Search|Demo Browser Search]]
- [[_COMMUNITY_FTS Keyword Retriever|FTS Keyword Retriever]]
- [[_COMMUNITY_Demo Browser Check|Demo Browser Check]]
- [[_COMMUNITY_Order Lifecycle Policies|Order Lifecycle Policies]]
- [[_COMMUNITY_Answer Cache|Answer Cache]]
- [[_COMMUNITY_Tracing|Tracing]]
- [[_COMMUNITY_Relevance Grading|Relevance Grading]]
- [[_COMMUNITY_Indexer Health|Indexer Health]]
- [[_COMMUNITY_Demo Orders X-ray|Demo Orders X-ray]]
- [[_COMMUNITY_Orders Fixture Generator|Orders Fixture Generator]]
- [[_COMMUNITY_Demo 3D Scene|Demo 3D Scene]]
- [[_COMMUNITY_Product Catalog|Product Catalog]]
- [[_COMMUNITY_Networking Runbook|Networking Runbook]]
- [[_COMMUNITY_Demo Translator|Demo Translator]]
- [[_COMMUNITY_Demo package.json|Demo package.json]]
- [[_COMMUNITY_Onboarding Guide|Onboarding Guide]]
- [[_COMMUNITY_Security Policy|Security Policy]]
- [[_COMMUNITY_Test Isolation|Test Isolation]]
- [[_COMMUNITY_Testing Standards|Testing Standards]]
- [[_COMMUNITY_Pipeline Package|Pipeline Package]]
- [[_COMMUNITY_Package Init A|Package Init A]]
- [[_COMMUNITY_Package Init B|Package Init B]]
- [[_COMMUNITY_Package Init C|Package Init C]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 49|Community 49]]

## God Nodes (most connected - your core abstractions)
1. `ask()` - 30 edges
2. `final()` - 28 edges
3. `search()` - 17 edges
4. `liveRun()` - 15 edges
5. `_StubLLM` - 14 edges
6. `sync_vectorstore()` - 13 edges
7. `TestGroupsFromDescriptor` - 12 edges
8. `descriptor()` - 11 edges
9. `allow()` - 11 edges
10. `chunk()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `"My orders" clarifying rule (ask which customer)` --references--> `_system_prompt()`  [INFERRED]
  demo/README.md → agent.py
- `Stateless app processes (shared state behind Redis-ready interface)` --conceptually_related_to--> `allow_request()`  [INFERRED]
  CLAUDE.md → app.py
- `checkAgentRun()` --references--> `demo_live cases (run live in the browser, five cases)`  [INFERRED]
  demo/check_search.mjs → eval/fixtures/golden_set.yaml
- `Same guards, inside the tools` --references--> `guard()`  [INFERRED]
  README.md → search/orders.py
- `"My orders" clarifying rule (ask which customer)` --references--> `schema_prompt()`  [INFERRED]
  demo/README.md → search/orders.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **"My orders" clarifying rule shared by translator, SQL prompt and agent** — demo_readme_my_orders_clarifying_rule, web_orders_clarifyingquestion, search_orders_schema_prompt, agent_system_prompt, fixtures_golden_set_my_orders_cases [INFERRED 0.85]
- **demo_live cases run live in the browser and checked in CI** — fixtures_golden_set_demo_live_cases, web_liverun, demo_check_search, demo_readme_live_agent_runs [EXTRACTED 1.00]
- **Saved agent run build, check and playback** — demo_agent_runs, demo_readme_saved_agent_runs, demo_readme_staleness_fingerprint, fixtures_golden_set_demo_agent_questions, web_agent_renderrun [INFERRED 0.85]

## Communities (50 total, 6 thin omitted)

### Community 0 - "Streamlit App & RAG Core"
Cohesion: 0.06
Nodes (56): answer_order_question(), answer_question(), AnswerChain, AnswerWithSources, _api_error_message(), _as_stamp(), build_chain(), build_group_filter() (+48 more)

### Community 1 - "Pipeline Tests"
Cohesion: 0.06
Nodes (46): answer_agent_question(), _bound_hit(), _execute(), _failed(), The agent: questions that need more than one step or more than one source.  rag., What one tool call produced. `text` goes back to the model; `detail`     is for, The tools for one question, with the asker's identity bound in., The ask_user / final_answer call, if it is the only call of the turn.     One se (+38 more)

### Community 2 - "Access Control Tests"
Cohesion: 0.10
Nodes (17): ask(), chain(), doc(), final(), Agent tests.  The loop lets the model choose its own steps, so nothing here trus, Plays back a fixed list of turns; each turn is a list of (tool, args).     Recor, Every tool result the model was shown, in order., ScriptedLLM (+9 more)

### Community 3 - "RAG Unit Tests"
Cohesion: 0.06
Nodes (17): _Answer, doc(), _FakeCrossEncoder, _Grader, Tests for the pipeline stages: chunking, reranking, grading/retry, the answer ca, Supports the standalone/retrieve protocol; answers per query., _RecordingStore, _Retriever (+9 more)

### Community 4 - "Orders NL-to-SQL Tests"
Cohesion: 0.07
Nodes (43): Agent Example Script (agent_examples.yaml), build(), check(), CutoffReranker, demo_items(), doc_files(), example_run(), fingerprint() (+35 more)

### Community 5 - "Index-time ACL Tagging"
Cohesion: 0.06
Nodes (42): abutton, aform, ainput, alist, allowed(), aresults, ask(), askOrders() (+34 more)

### Community 6 - "Crawler Tests"
Cohesion: 0.06
Nodes (15): _chain(), doc(), _FakeRetriever, Authorization tests: path translation, the per-file access filter, and the guard, Stands in for the structured-output LLM call so the test can assert     on exact, _RecordingAnswerChain, _StubSession, TestAccessChecker (+7 more)

### Community 7 - "Eval Harness"
Cohesion: 0.05
Nodes (13): Unit tests for the pure functions in rag.py.  These exist because the retrieval, compute_k() being correct is useless if build_retriever() ignores it.     A reve, Guards the BM25 tokenizer. The original bug: the default whitespace     tokenize, The model self-reports which sources it used; a path it names that     wasn't ac, TestBuildGroupFilter, TestBuildRetrieverUsesComputedK, TestComputeK, TestGroupsForPath (+5 more)

### Community 8 - "Demo UI App"
Cohesion: 0.06
Nodes (11): ask(), FakeLLM, The order path's safety rails: they must hold whatever SQL Claude writes., Writes the SQL it was given and answers with a fixed sentence., Same expectations as the role cases in eval/fixtures/golden_set.yaml., StubRetriever, TestAnswerOrderQuestion, TestDatabase (+3 more)

### Community 9 - "Loader Tests"
Cohesion: 0.07
Nodes (17): BaseRetriever, connect(), default_db_path(), FtsRetriever, Persistent keyword index for hybrid retrieval.  Replaces the in-memory BM25 retr, LangChain retriever over the SQLite index, so it can slot into the     existing, search(), to_match_expression() (+9 more)

### Community 10 - "Keyword Index Tests"
Cohesion: 0.05
Nodes (10): paths_in(), Crawler and file-search tests.  The crawler's whole value is that it does not re, TestBuildMatchExpression, TestCensus, TestConnect, TestCrawl, TestExtensionListsAgree, TestFallbackParsing (+2 more)

### Community 11 - "Fixture People & Architecture"
Cohesion: 0.07
Nodes (34): Fixed today (2026-10-28) in the meta table, permissions.yaml Folder-Group Mapping, NAS Document Search Assistant Plan, Index-time ACL Tagging Pre-filter, Folder Summaries (Haiku), SQLite FTS5 Metadata Index, NAS-delegated SMB Authorization, RAG Assistant README (+26 more)

### Community 12 - "Indexer Entrypoint & Summaries"
Cohesion: 0.10
Nodes (25): main(), Indexer entrypoint: `python -m indexer`.  Runs on the host next to the NAS, on a, run_crawl(), run_forever(), run_summaries(), seconds_until(), ensure_schema(), _evidence() (+17 more)

### Community 13 - "Deploy, Demo & Eval Docs"
Cohesion: 0.11
Nodes (10): allow(), deny(), descriptor(), ACL-mapping tests.  Built on real SMB2CreateSDBuffer objects rather than hand-ro, sid(), TestFeatureGate, TestGrantsRead, TestGroupsForUser (+2 more)

### Community 14 - "Router Tests"
Cohesion: 0.12
Nodes (22): "My orders" clarifying rule (ask which customer), Singular/plural order guard (one order never matches many), Typed question matching (0.8 similarity + matching numbers), Paraphrases and look-alikes, TestSchemaPrompt, answerHtml(), escape(), evidenceHtml() (+14 more)

### Community 15 - "Summary Tests"
Cohesion: 0.09
Nodes (20): BaseModel, _numbered(), QueryRewriter, Relevance grading and query rewriting - the corrective-retrieval loop.  After re, RelevanceGrader, RelevantChunks, build_match_expression(), _fallback_terms() (+12 more)

### Community 16 - "SMB Auth & Access Checks"
Cohesion: 0.07
Nodes (7): Loader tests for the formats a shared drive is actually full of.  Each loader is, TestLoadEml, TestLoaderErrorsAreSurvivable, TestLoadFileDispatch, TestLoadPptx, TestLoadXlsx, TestSecretRedaction

### Community 17 - "Orders SQL Guard"
Cohesion: 0.08
Nodes (27): Atlas Project, Sam Rivera, Alex Chen, Nimbus Project, SLO-based Alerting, Event Bus, Platform Architecture Notes, Service Datastore Boundaries (+19 more)

### Community 18 - "Manifest Tests"
Cohesion: 0.14
Nodes (22): _agent_evidence(), check_agent_result(), check_expectations(), contains_all(), contains_any(), _grade(), Groundedness, load_golden_set() (+14 more)

### Community 19 - "Demo Index Build & Chunking"
Cohesion: 0.15
Nodes (22): access_checker(), allow_request(), current_order_role(), current_session(), load_chain(), login_form(), meta_db(), order_role_for() (+14 more)

### Community 20 - "Crawler & Census"
Cohesion: 0.09
Nodes (7): Router tests.  The router is only worth having if it is right about the cases th, Returns a fixed Route, like with_structured_output would., _StubLLM, TestCanonicalSources, TestEmbeddingModelOverride, TestFallbackRouting, TestLlmRouting

### Community 21 - "Demo Orders Templates"
Cohesion: 0.13
Nodes (5): Folder-summary tests.  The expensive mistake here is re-summarising folders that, _StubLLM, TestMatchingFolders, TestReadHead, TestSummarizeFolders

### Community 22 - "Demo Browser Search"
Cohesion: 0.13
Nodes (13): AccessChecker, login(), nas_links(), NasSession, NasUnavailable, _open_for_read(), NAS-backed authentication and per-file authorization over SMB.  The NAS is the o, Callable wrapper around NasSession.can_read with a per-question memo.     Retrie (+5 more)

### Community 23 - "FTS Keyword Retriever"
Cohesion: 0.13
Nodes (18): agentFile, checkAgentRun(), checkOrders(), db, engine, golden, index, NEEDS_A_MODEL (+10 more)

### Community 24 - "Demo Browser Check"
Cohesion: 0.12
Nodes (5): Incremental-sync tests.  On a 50 GB network share the difference between "stat e, TestFileHash, TestFileStamp, TestLegacyManifest, TestPathNormalisation

### Community 25 - "Order Lifecycle Policies"
Cohesion: 0.28
Nodes (15): Live agent runs in the browser (liverun.js), capital(), CLOSED, documentRun(), excerpt(), filledSql(), human(), liveRun() (+7 more)

### Community 26 - "Answer Cache"
Cohesion: 0.22
Nodes (13): connect(), crawl(), _delete(), _exclude_globs(), format_census(), human_bytes(), is_excluded_dir(), is_excluded_file() (+5 more)

### Community 27 - "Tracing"
Cohesion: 0.18
Nodes (15): ASK_FOR, daysBetween(), extractSlots(), findCustomer(), human(), INTENTS, iso(), money() (+7 more)

### Community 28 - "Relevance Grading"
Cohesion: 0.21
Nodes (5): Bm25, Engine, fuse(), queryTerms(), tokenize()

### Community 29 - "Indexer Health"
Cohesion: 0.18
Nodes (7): In-browser Demo README, Ingest/query split (Python in CI, JavaScript in browser), Order translator 0.45 similarity floor, Parameterized SQL Templates (orders.js), Role replay is an illustration, not security, Translator, ROLES

### Community 30 - "Demo Orders X-ray"
Cohesion: 0.18
Nodes (12): on_hold, Order Lifecycle, returned, Repairs, Returns and Warranty, Warranty, Hold Reasons, Promised Delivery Date (+4 more)

### Community 31 - "Orders Fixture Generator"
Cohesion: 0.27
Nodes (4): AnswerCache, normalize_question(), Answer cache.  Exact-match on a normalised question, scoped to one user and one, still_permitted()

### Community 32 - "Demo 3D Scene"
Cohesion: 0.20
Nodes (8): invoke(), _langfuse_handler(), Per-question tracing.  Two layers. Step timings are always on and land in the ex, Accumulates wall-clock milliseconds per named pipeline step. A step     that run, LangChain config for one question, or None when tracing is off.     None (not {}, Call runnable.invoke, passing config only when there is one., run_config(), StepTimer

### Community 33 - "Product Catalog"
Cohesion: 0.43
Nodes (7): build(), business_days(), main(), q(), Generate eval/fixtures/orders.sql: Acme Robotics' fictional orders database.  De, A plausible tracking timeline for one order., shipments()

### Community 34 - "Networking Runbook"
Cohesion: 0.29
Nodes (7): askAgent(), onScroll(), Acme Docs & Orders Demo Page, Ask the agent section (#agent), Where company search breaks section (#problems), Ask the orders section (#orders), Scroll story (four steps over the 3D hero)

### Community 35 - "Demo Translator"
Cohesion: 0.43
Nodes (5): COLORS, glyphPoints(), mountScene(), rand(), slipTexture()

### Community 36 - "Demo package.json"
Cohesion: 0.40
Nodes (5): Acme Robotics Product Catalog, Fleet Console, PR-200 Tote Runner, PR-400 Pallet Runner, PR-900 Heavy Runner

### Community 37 - "Onboarding Guide"
Cohesion: 0.50
Nodes (4): Certificates, Firewall, Load Balancer, Networking Runbook

### Community 39 - "Test Isolation"
Cohesion: 1.00
Nodes (3): Synology NAS Deployment Guide, Read-only CIFS Mount, Docker Compose (app, indexer, caddy)

### Community 40 - "Testing Standards"
Cohesion: 0.67
Nodes (3): Engineering Onboarding Guide, Local Development, Team Rituals

### Community 41 - "Pipeline Package"
Cohesion: 0.67
Nodes (3): Access Review, Data Classification, Security Policy

## Knowledge Gaps
- **80 isolated node(s):** `private`, `type`, `COLORS`, `Folder Summaries (Haiku)`, `Demo Favicon` (+75 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Live agent runs in the browser (liverun.js)` connect `Order Lifecycle Policies` to `Pipeline Tests`, `Networking Runbook`, `Indexer Health`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Why does `Agent Regression Evals (code-graded, free, pass^3 = 100%)` connect `FTS Keyword Retriever` to `Access Control Tests`, `Orders NL-to-SQL Tests`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **What connects `NAS-backed authentication and per-file authorization over SMB.  The NAS is the o`, `The NAS could not be reached or refused the connection for a reason     other th`, `One logged-in user's SMB session. Holds the live connection objects     and the` to the rest of the system?**
  _169 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Streamlit App & RAG Core` be split into smaller, more focused modules?**
  _Cohesion score 0.061381074168797956 - nodes in this community are weakly interconnected._
- **Should `Pipeline Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.05519480519480519 - nodes in this community are weakly interconnected._
- **Should `Access Control Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.10437710437710437 - nodes in this community are weakly interconnected._
- **Should `RAG Unit Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.061683599419448475 - nodes in this community are weakly interconnected._