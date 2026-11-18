"""Fault injection and production bounds.

Each test breaks one thing a production deployment will see sooner or later
- the model API rate-limiting, the orders replica gone, an indexing run
killed half-way, a keyword query that will not finish, a burst of requests
from one user - and asserts the system fails closed, bounded, and with a
clear answer instead of an exception or a runaway.
"""
import json
import os
import threading
import time

import pytest
from langchain_core.documents import Document
from langchain_core.exceptions import ModelRateLimitError
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agent
import rag
from pipeline import health, llm, ratelimit
from search import keyword, orders


# ---- model calls are bounded --------------------------------------------------
class _NoopLLM(RunnableLambda):
    def __init__(self):
        super().__init__(lambda x: x)

    def with_structured_output(self, *_a, **_k):
        return self


class TestModelCallBounds:
    def test_bounded_sets_timeout_and_retry_cap(self):
        kwargs = llm.bounded(1024)
        assert kwargs["max_tokens"] == 1024
        assert kwargs["timeout"] > 0 and kwargs["max_retries"] >= 0

    def test_every_client_in_build_chain_is_bounded(self, monkeypatch):
        built = []
        monkeypatch.setattr(rag, "ChatAnthropic", lambda **kw: built.append(kw) or _NoopLLM())
        monkeypatch.setattr(rag, "llm_enabled", lambda: True)
        monkeypatch.setattr(rag, "build_retriever", lambda *a, **k: object())
        rag.build_chain(object(), use_cache=False)
        assert built, "expected at least one model client"
        for kwargs in built:
            assert {"timeout", "max_retries", "max_tokens"} <= set(kwargs)


# ---- the model API failing ----------------------------------------------------------
class _RateLimitedLLM:
    def bind_tools(self, *_a, **_k):
        return self

    def with_structured_output(self, *_a, **_k):
        return self

    def invoke(self, *_a, **_k):
        raise ModelRateLimitError("429 from upstream")


class TestApiFailures:
    def test_agent_turns_a_429_into_a_typed_answer(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag, "ORDERS_DB", str(tmp_path / "orders.db"))
        result = agent.answer_agent_question("Why is order 1042 late?", [], None, "admin",
                                             llm=_RateLimitedLLM())
        assert result["guardrail"].startswith("api_error:rate_limit")
        assert "rate-limited" in result["answer"]

    def test_order_mode_turns_a_429_into_a_typed_answer(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag, "ORDERS_DB", str(tmp_path / "orders.db"))
        monkeypatch.setattr(rag, "llm_enabled", lambda: True)
        monkeypatch.setattr(rag, "ChatAnthropic", lambda **kw: _RateLimitedLLM())
        result = rag.answer_order_question("Why is order 1042 late?", "admin")
        assert result["guardrail"].startswith("api_error:rate_limit")


# ---- the orders database failing ---------------------------------------------------
@pytest.fixture
def corrupt_orders_db(tmp_path, monkeypatch):
    path = tmp_path / "corrupt_orders.db"
    path.write_text("not a database")
    monkeypatch.setattr(rag, "ORDERS_DB", str(path))
    return path


class TestOrdersUnavailable:
    def test_order_mode_answers_instead_of_raising(self, corrupt_orders_db, monkeypatch):
        monkeypatch.setattr(rag, "llm_enabled", lambda: True)
        result = rag.answer_order_question("Why is order 1042 late?", "admin")
        assert result["guardrail"].startswith("orders_unavailable")
        assert result["answer"] == rag.ORDERS_UNAVAILABLE

    def test_agent_degrades_to_documents_only(self, corrupt_orders_db):
        offered = []

        class Recording:
            def bind_tools(self, tools, tool_choice=None):
                offered.append([t["name"] for t in tools])
                return self

            def invoke(self, *_a, **_k):
                return AIMessage(content="", tool_calls=[{
                    "name": agent.FINAL_ANSWER, "args": {"answer": "x"}, "id": "c1", "type": "tool_call"}])

        result = agent.answer_agent_question("Which orders are late?", [], None, "admin", llm=Recording())
        assert agent.QUERY_ORDERS not in offered[0]
        assert result["guardrail"] == "no_evidence"


# ---- agent bounds count everything --------------------------------------------------
def _closed_toolbox():
    return agent.Toolbox(None, "admin", None, None, {"hidden": set(), "denied": True})


class TestAgentBounds:
    def test_tokens_spent_inside_tools_count_toward_the_budget(self, monkeypatch):
        # The grader and rewriter run inside search_docs; their tokens never
        # appear on the agent's own replies. spent() reports them.
        monkeypatch.setattr(agent, "TOKEN_BUDGET", 1000)
        offered = []

        class Model:
            def bind_tools(self, tools, tool_choice=None):
                names = [t["name"] for t in tools]

                class Bound:
                    def invoke(_self, messages, config=None):
                        offered.append(names)
                        return AIMessage(content="", tool_calls=[{
                            "name": agent.FINAL_ANSWER, "args": {"answer": "x"}, "id": "c", "type": "tool_call"}])
                return Bound()

        _, bound = agent._run_loop(Model(), _closed_toolbox(), [], [], None, time.monotonic() + 60, None,
                                   spent=lambda: 5000)
        assert bound == "budget"
        assert set(offered[0]) == agent.TERMINAL_TOOLS

    def test_no_tool_runs_after_the_deadline(self):
        message = agent._execute({"name": agent.SEARCH_DOCS, "args": {"query": "q"}, "id": "c"},
                                 _closed_toolbox(), [], None, deadline=time.monotonic() - 1)
        assert message.content.startswith("Not run: the time limit")


# ---- indexing survives being killed ---------------------------------------------------
class _Store:
    def __init__(self):
        self.added = []

        class _Collection:
            def count(_self):
                return len(self.added)
        self._collection = _Collection()

    def delete(self, where):
        pass

    def add_documents(self, chunks):
        self.added.extend(c.metadata["source"] for c in chunks)
        return [f"id{len(self.added)}-{i}" for i in range(len(chunks))]


@pytest.fixture
def corpus(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    paths = []
    for i in range(10):
        path = folder / f"f{i:02d}.txt"
        path.write_text(f"document number {i}")
        paths.append(str(path))
    return paths


class TestIndexingResume:
    def test_a_killed_run_resumes_instead_of_starting_over(self, corpus, monkeypatch):
        monkeypatch.setattr(rag, "MANIFEST_CHECKPOINT_EVERY", 2)
        real_load = rag.load_file
        loaded = []

        def dies_after_five(path):
            if len(loaded) == 5:
                raise KeyboardInterrupt("container killed")
            loaded.append(path)
            return real_load(path)

        monkeypatch.setattr(rag, "load_file", dies_after_five)
        with pytest.raises(KeyboardInterrupt):
            rag.sync_vectorstore(_Store(), paths=corpus)
        assert len(rag.load_manifest()) == 4  # the last checkpoint before the kill

        monkeypatch.setattr(rag, "load_file", real_load)
        store = _Store()
        rag.sync_vectorstore(store, paths=corpus)
        assert len(set(store.added)) == 6  # only what the killed run had not checkpointed
        assert set(rag.load_manifest()) == set(corpus)

    def test_manifest_write_is_atomic(self, corpus):
        rag.sync_vectorstore(_Store(), paths=corpus)
        assert not os.path.exists(rag.MANIFEST_PATH + ".tmp")
        with open(rag.MANIFEST_PATH) as f:
            assert len(json.load(f)) == len(corpus)

    def test_a_no_op_run_does_not_invalidate_the_answer_cache(self, corpus):
        from pipeline import cache
        rag.sync_vectorstore(_Store(), paths=corpus)
        version = cache.index_version(rag.MANIFEST_PATH)
        rag.sync_vectorstore(_Store(), paths=corpus)
        assert cache.index_version(rag.MANIFEST_PATH) == version


# ---- keyword index at scale ---------------------------------------------------------------
@pytest.fixture
def index(tmp_path):
    connection = keyword.connect(str(tmp_path / "chunks.sqlite"))
    yield connection
    connection.close()


def chunk(text, source="/d/a.txt"):
    return Document(page_content=text, metadata={"source": source, "group_ALL": True})


class TestKeywordScale:
    def test_delete_uses_the_source_table(self, index):
        keyword.add_chunks(index, [chunk("alpha", "/d/a.txt"), chunk("beta", "/d/b.txt")], ["c1", "c2"])
        keyword.delete_source(index, "/d/a.txt")
        assert keyword.search(index, "alpha", 5) == []
        assert keyword.search(index, "beta", 5)
        assert index.execute("SELECT COUNT(*) FROM chunk_sources").fetchone()[0] == 1

    def test_rows_written_before_the_source_table_still_delete(self, index):
        keyword.add_chunks(index, [chunk("legacy words", "/d/old.txt")], ["c1"])
        index.execute("DELETE FROM chunk_sources")
        keyword.delete_source(index, "/d/old.txt")
        assert keyword.count(index) == 0

    def test_delete_of_a_huge_file_batches_its_parameters(self, index):
        n = keyword._BATCH * 2 + 7
        keyword.add_chunks(index, [chunk(f"w{i}", "/d/big.txt") for i in range(n)], [f"c{i}" for i in range(n)])
        keyword.delete_source(index, "/d/big.txt")
        assert keyword.count(index) == 0

    def test_stop_words_are_dropped(self):
        assert keyword.to_match_expression("What is the deploy window?") == '"deploy" OR "window"'

    def test_a_question_of_only_stop_words_still_searches(self):
        assert keyword.to_match_expression("who is it") != ""

    def test_terms_are_capped(self):
        expression = keyword.to_match_expression(" ".join(f"term{i}" for i in range(200)))
        assert expression.count(" OR ") == keyword.MAX_QUERY_TERMS - 1

    def test_a_slow_query_is_cut_off_not_waited_for(self, index, monkeypatch):
        keyword.add_chunks(index, [chunk(f"common word {i}") for i in range(3000)],
                           [f"c{i}" for i in range(3000)])
        monkeypatch.setattr(keyword, "QUERY_TIME_BUDGET_S", -1)
        assert keyword.search(index, "common word", 5) == []
        # The deadline does not leak into the next query.
        monkeypatch.setattr(keyword, "QUERY_TIME_BUDGET_S", 5)
        assert keyword.search(index, "common", 5)

    def test_is_empty(self, index):
        assert keyword.is_empty(index)
        keyword.add_chunks(index, [chunk("x")], ["c1"])
        assert not keyword.is_empty(index)


class TestCorpusSizeIsBounded:
    def test_filtered_count_asks_for_a_capped_number_of_ids(self):
        seen = {}

        class Store:
            def get(self, **kwargs):
                seen.update(kwargs)
                return {"ids": ["x"] * 3}

        rag._corpus_size(Store(), allowed_groups=["HR"])
        assert seen["limit"] == rag.CORPUS_SIZE_CAP

    def test_unfiltered_count_does_not_list_ids(self):
        class Collection:
            def count(self):
                return 10_000_000

        class Store:
            _collection = Collection()

            def get(self, **kwargs):
                raise AssertionError("must not list every id")

        assert rag._corpus_size(Store()) == rag.CORPUS_SIZE_CAP


# ---- rate limit ---------------------------------------------------------------------------
class TestRateLimit:
    def test_limit_is_per_key_and_slides(self):
        now = [0.0]
        limiter = ratelimit.InProcessRateLimiter(max_requests=2, window_seconds=10, clock=lambda: now[0])
        assert limiter.allow("alice") and limiter.allow("alice")
        assert not limiter.allow("alice")
        assert limiter.allow("bob")
        now[0] = 10.0
        assert limiter.allow("alice")

    def test_concurrent_requests_never_exceed_the_limit(self):
        limiter = ratelimit.InProcessRateLimiter(max_requests=25, window_seconds=60)
        allowed = []
        barrier = threading.Barrier(50)

        def hit():
            barrier.wait()
            allowed.append(limiter.allow("alice"))

        threads = [threading.Thread(target=hit) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(allowed) == 25


# ---- readiness ------------------------------------------------------------------------------
def _built_index(folder):
    connection = keyword.connect(str(folder / "chunks.sqlite"))
    keyword.add_chunks(connection, [chunk("x")], ["c1"])
    connection.close()


class TestReadiness:
    def test_not_ready_without_an_index(self, tmp_path):
        ok, problems = health.ready(str(tmp_path / "missing"))
        assert not ok and problems

    def test_ready_with_index_and_orders(self, tmp_path):
        _built_index(tmp_path)
        db = orders.ensure_db(str(tmp_path / "orders.db"))
        assert health.ready(str(tmp_path), db) == (True, [])

    def test_corrupt_orders_db_is_not_ready(self, tmp_path, corrupt_orders_db):
        _built_index(tmp_path)
        ok, problems = health.ready(str(tmp_path), str(corrupt_orders_db))
        assert not ok and "orders" in problems[0]
