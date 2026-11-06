# Graph Report - .  (2026-11-05)

## Corpus Check
- 77 files · ~58,464 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 853 nodes · 1229 edges · 45 communities (40 shown, 5 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 23 edges (avg confidence: 0.86)
- Token cost: 122,327 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `$()` - 55 edges
2. `_StubLLM` - 14 edges
3. `sync_vectorstore()` - 13 edges
4. `build_chain()` - 12 edges
5. `TestGroupsFromDescriptor` - 12 edges
6. `descriptor()` - 11 edges
7. `allow()` - 11 edges
8. `chunk()` - 11 edges
9. `doc()` - 10 edges
10. `FakeLLM` - 10 edges

## Surprising Connections (you probably didn't know these)
- `permissions.yaml Folder-Group Mapping` --semantically_similar_to--> `Index-time ACL Tagging Pre-filter`  [INFERRED] [semantically similar]
  permissions.yaml → .claude/plans/nas-document-search.plan.md
- `RAG Assistant README` --implements--> `NAS-delegated SMB Authorization`  [INFERRED]
  README.md → .claude/plans/nas-document-search.plan.md
- `Team Roster` --references--> `Sam Rivera`  [INFERRED]
  eval/fixtures/docs/team_roster.md → graphify-out/converted/sam_rivera_resume_00d55517.md
- `NAS Document Search Assistant Plan` --references--> `permissions.yaml Folder-Group Mapping`  [EXTRACTED]
  .claude/plans/nas-document-search.plan.md → permissions.yaml
- `NAS Document Search Assistant Plan` --references--> `answer_question Guardrails`  [EXTRACTED]
  .claude/plans/nas-document-search.plan.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **NAS Authorization Layers** — plans_nas_document_search_plan_smb_authorization, plans_nas_document_search_plan_acl_tagging, permissions, readme_answer_question_guardrails [INFERRED 0.85]
- **Demo Build and Publish Pipeline** — workflows_pages, demo_readme, web_index, fixtures_readme [INFERRED 0.75]
- **Order Hold Handling Flow** — docs_order_lifecycle_on_hold, docs_shipping_policy_hold_reasons, docs_support_playbook_held_orders [INFERRED 0.85]

## Communities (45 total, 5 thin omitted)

### Community 0 - "Streamlit App & RAG Core"
Cohesion: 0.05
Nodes (69): access_checker(), current_session(), load_chain(), login_form(), meta_db(), order_role_for(), Streamlit UI. Deliberately thin: every decision lives in rag.py and search/.  Th, render_chat() (+61 more)

### Community 1 - "Pipeline Tests"
Cohesion: 0.06
Nodes (17): _Answer, doc(), _FakeCrossEncoder, _Grader, Tests for the pipeline stages: chunking, reranking, grading/retry, the answer ca, Supports the standalone/retrieve protocol; answers per query., _RecordingStore, _Retriever (+9 more)

### Community 2 - "Access Control Tests"
Cohesion: 0.06
Nodes (15): _chain(), doc(), _FakeRetriever, Authorization tests: path translation, the per-file access filter, and the guard, Stands in for the structured-output LLM call so the test can assert     on exact, _RecordingAnswerChain, _StubSession, TestAccessChecker (+7 more)

### Community 3 - "RAG Unit Tests"
Cohesion: 0.05
Nodes (13): Unit tests for the pure functions in rag.py.  These exist because the retrieval, compute_k() being correct is useless if build_retriever() ignores it.     A reve, Guards the BM25 tokenizer. The original bug: the default whitespace     tokenize, The model self-reports which sources it used; a path it names that     wasn't ac, TestBuildGroupFilter, TestBuildRetrieverUsesComputedK, TestComputeK, TestGroupsForPath (+5 more)

### Community 4 - "Orders NL-to-SQL Tests"
Cohesion: 0.06
Nodes (11): ask(), FakeLLM, The order path's safety rails: they must hold whatever SQL Claude writes., Writes the SQL it was given and answers with a fixed sentence., Same expectations as the role cases in eval/fixtures/golden_set.yaml., StubRetriever, TestAnswerOrderQuestion, TestDatabase (+3 more)

### Community 5 - "Index-time ACL Tagging"
Cohesion: 0.08
Nodes (15): grants_read(), groups_for_user(), groups_from_descriptor(), Stage 1 of authorization: index-time ACL tagging.  Reads each folder's SMB secur, sanitize_group(), allow(), deny(), descriptor() (+7 more)

### Community 6 - "Crawler Tests"
Cohesion: 0.05
Nodes (10): paths_in(), Crawler and file-search tests.  The crawler's whole value is that it does not re, TestBuildMatchExpression, TestCensus, TestConnect, TestCrawl, TestExtensionListsAgree, TestFallbackParsing (+2 more)

### Community 7 - "Eval Harness"
Cohesion: 0.09
Nodes (30): BaseModel, check_expectations(), contains_all(), contains_any(), _grade(), Groundedness, load_golden_set(), looks_like_refusal() (+22 more)

### Community 8 - "Demo UI App"
Cohesion: 0.07
Nodes (28): $(), allowed(), ask(), button, CASES, EXAMPLES, FILLER, form (+20 more)

### Community 9 - "Loader Tests"
Cohesion: 0.07
Nodes (7): Loader tests for the formats a shared drive is actually full of.  Each loader is, TestLoadEml, TestLoaderErrorsAreSurvivable, TestLoadFileDispatch, TestLoadPptx, TestLoadXlsx, TestSecretRedaction

### Community 10 - "Keyword Index Tests"
Cohesion: 0.11
Nodes (9): chunk(), Persistent keyword-index tests.  These carry over the guarantees the in-memory B, The bug this replaces: the default whitespace tokenizer made a whole     URL one, sources(), TestDefaultPath, TestGroupFiltering, TestLifecycle, TestRetrieverInterface (+1 more)

### Community 11 - "Fixture People & Architecture"
Cohesion: 0.08
Nodes (27): Atlas Project, Sam Rivera, Alex Chen, Nimbus Project, SLO-based Alerting, Event Bus, Platform Architecture Notes, Service Datastore Boundaries (+19 more)

### Community 12 - "Indexer Entrypoint & Summaries"
Cohesion: 0.13
Nodes (17): main(), Indexer entrypoint: `python -m indexer`.  Runs on the host next to the NAS, on a, run_crawl(), run_forever(), run_summaries(), seconds_until(), ensure_schema(), _evidence() (+9 more)

### Community 13 - "Deploy, Demo & Eval Docs"
Cohesion: 0.11
Nodes (24): In-browser Demo README, Parameterized SQL Templates (orders.js), Synology NAS Deployment Guide, Read-only CIFS Mount, Docker Compose (app, indexer, caddy), Golden Set Example, Fixture Golden Set, Acme Robotics Fixtures (+16 more)

### Community 14 - "Router Tests"
Cohesion: 0.09
Nodes (7): Router tests.  The router is only worth having if it is right about the cases th, Returns a fixed Route, like with_structured_output would., _StubLLM, TestCanonicalSources, TestEmbeddingModelOverride, TestFallbackRouting, TestLlmRouting

### Community 15 - "Summary Tests"
Cohesion: 0.13
Nodes (5): Folder-summary tests.  The expensive mistake here is re-summarising folders that, _StubLLM, TestMatchingFolders, TestReadHead, TestSummarizeFolders

### Community 16 - "SMB Auth & Access Checks"
Cohesion: 0.13
Nodes (13): AccessChecker, login(), nas_links(), NasSession, NasUnavailable, _open_for_read(), NAS-backed authentication and per-file authorization over SMB.  The NAS is the o, Callable wrapper around NasSession.can_read with a per-question memo.     Retrie (+5 more)

### Community 17 - "Orders SQL Guard"
Cohesion: 0.15
Nodes (16): connect(), ensure_db(), generate(), guard(), GuardError, load_group_roles(), Order questions, answered from the orders database with SQL written by Claude., Return a safe version of `sql`, or raise GuardError. (+8 more)

### Community 18 - "Manifest Tests"
Cohesion: 0.12
Nodes (5): Incremental-sync tests.  On a 50 GB network share the difference between "stat e, TestFileHash, TestFileStamp, TestLegacyManifest, TestPathNormalisation

### Community 19 - "Demo Index Build & Chunking"
Cohesion: 0.16
Nodes (10): build_orders_db(), main(), Build demo/web/index.json for the in-browser demo.  The browser cannot run Pytho, has_headings(), Structure-aware chunking.  Fixed-size windows cut straight through headings, run, section_path(), split_documents(), get_reranker() (+2 more)

### Community 20 - "Crawler & Census"
Cohesion: 0.22
Nodes (13): connect(), crawl(), _delete(), _exclude_globs(), format_census(), human_bytes(), is_excluded_dir(), is_excluded_file() (+5 more)

### Community 21 - "Demo Orders Templates"
Cohesion: 0.20
Nodes (14): daysBetween(), extractSlots(), findCustomer(), human(), INTENTS, iso(), money(), MONTHS (+6 more)

### Community 22 - "Demo Browser Search"
Cohesion: 0.19
Nodes (6): highlight(), Bm25, Engine, fuse(), queryTerms(), tokenize()

### Community 23 - "FTS Keyword Retriever"
Cohesion: 0.19
Nodes (8): BaseRetriever, connect(), default_db_path(), FtsRetriever, Persistent keyword index for hybrid retrieval.  Replaces the in-memory BM25 retr, LangChain retriever over the SQLite index, so it can slot into the     existing, search(), to_match_expression()

### Community 24 - "Demo Browser Check"
Cohesion: 0.19
Nodes (12): checkOrders(), db, engine, golden, index, NEEDS_A_MODEL, octx, require (+4 more)

### Community 25 - "Order Lifecycle Policies"
Cohesion: 0.18
Nodes (12): on_hold, Order Lifecycle, returned, Repairs, Returns and Warranty, Warranty, Hold Reasons, Promised Delivery Date (+4 more)

### Community 26 - "Answer Cache"
Cohesion: 0.27
Nodes (4): AnswerCache, normalize_question(), Answer cache.  Exact-match on a normalised question, scoped to one user and one, still_permitted()

### Community 27 - "Tracing"
Cohesion: 0.20
Nodes (8): invoke(), _langfuse_handler(), Per-question tracing.  Two layers. Step timings are always on and land in the ex, Accumulates wall-clock milliseconds per named pipeline step. A step     that run, LangChain config for one question, or None when tracing is off.     None (not {}, Call runnable.invoke, passing config only when there is one., run_config(), StepTimer

### Community 28 - "Relevance Grading"
Cohesion: 0.22
Nodes (5): _numbered(), QueryRewriter, Relevance grading and query rewriting - the corrective-retrieval loop.  After re, RelevanceGrader, RelevantChunks

### Community 29 - "Indexer Health"
Cohesion: 0.36
Nodes (8): check(), main(), Indexer heartbeat and staleness checks.  The indexer writes a small status file, state is "running", "ok" or "failed". last_success survives a failed     run so, Returns (healthy, message)., read_status(), status_path(), write_status()

### Community 30 - "Demo Orders X-ray"
Cohesion: 0.28
Nodes (9): askOrders(), cell(), chip(), escape(), fmt(), oxray(), short(), sqlHtml() (+1 more)

### Community 31 - "Orders Fixture Generator"
Cohesion: 0.43
Nodes (7): build(), business_days(), main(), q(), Generate eval/fixtures/orders.sql: Acme Robotics' fictional orders database.  De, A plausible tracking timeline for one order., shipments()

### Community 32 - "Demo 3D Scene"
Cohesion: 0.43
Nodes (5): COLORS, glyphPoints(), mountScene(), rand(), slipTexture()

### Community 33 - "Product Catalog"
Cohesion: 0.40
Nodes (5): Acme Robotics Product Catalog, Fleet Console, PR-200 Tote Runner, PR-400 Pallet Runner, PR-900 Heavy Runner

### Community 34 - "Networking Runbook"
Cohesion: 0.50
Nodes (4): Certificates, Firewall, Load Balancer, Networking Runbook

### Community 37 - "Onboarding Guide"
Cohesion: 0.67
Nodes (3): Engineering Onboarding Guide, Local Development, Team Rituals

### Community 38 - "Security Policy"
Cohesion: 0.67
Nodes (3): Access Review, Data Classification, Security Policy

## Knowledge Gaps
- **65 isolated node(s):** `require`, `index`, `golden`, `NEEDS_A_MODEL`, `engine` (+60 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AnswerWithSources` connect `Streamlit App & RAG Core` to `Eval Harness`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **What connects `Streamlit UI. Deliberately thin: every decision lives in rag.py and search/.  Th`, `NAS-backed authentication and per-file authorization over SMB.  The NAS is the o`, `The NAS could not be reached or refused the connection for a reason     other th` to the rest of the system?**
  _132 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Streamlit App & RAG Core` be split into smaller, more focused modules?**
  _Cohesion score 0.050200803212851405 - nodes in this community are weakly interconnected._
- **Should `Pipeline Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.061683599419448475 - nodes in this community are weakly interconnected._
- **Should `Access Control Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.06105457909343201 - nodes in this community are weakly interconnected._
- **Should `RAG Unit Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.045454545454545456 - nodes in this community are weakly interconnected._
- **Should `Orders NL-to-SQL Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.06155632984901278 - nodes in this community are weakly interconnected._