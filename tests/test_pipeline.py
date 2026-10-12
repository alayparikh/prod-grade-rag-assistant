"""Tests for the pipeline stages: chunking, reranking, grading/retry,
the answer cache, streaming redaction and the indexer heartbeat."""
import time

import pytest
from langchain_core.documents import Document

import rag
from pipeline import cache as answer_cache
from pipeline import chunking, health, rerank


def doc(source, text="x"):
    return Document(page_content=text, metadata={"source": source})


class TestChunking:
    def test_sections_are_labelled_with_their_heading_path(self):
        text = "# Runbook\n## Restart\nStep 1: stop the service.\n## Rollback\nRevert."
        chunks = chunking.split_documents([doc("/d/runbook.md", text)])
        restart = next(c for c in chunks if "Step 1" in c.page_content)
        assert restart.page_content.startswith("Section: Runbook > Restart\n")
        assert restart.metadata["section"] == "Runbook > Restart"
        assert restart.metadata["source"] == "/d/runbook.md"

    def test_plain_text_falls_back_to_windows(self):
        chunks = chunking.split_documents([doc("/d/a.txt", "word " * 600)])
        assert len(chunks) > 1
        assert not any(c.page_content.startswith("Section:") for c in chunks)

    def test_chunker_change_reembeds_unchanged_files(self, tmp_path, monkeypatch):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.txt").write_text("hello")
        store = _RecordingStore()
        rag.sync_vectorstore(store, paths=[str(docs_dir / "a.txt")])
        assert store.added == 1
        rag.sync_vectorstore(store, paths=[str(docs_dir / "a.txt")])
        assert store.added == 1  # unchanged file, same chunker: skipped
        monkeypatch.setattr(chunking, "CHUNKER_VERSION", chunking.CHUNKER_VERSION + 1)
        rag.sync_vectorstore(store, paths=[str(docs_dir / "a.txt")])
        assert store.added == 2


class _RecordingStore:
    def __init__(self):
        self.added = 0

        class _Collection:
            def count(_self):
                return self.added
        self._collection = _Collection()

    def delete(self, where):
        pass

    def add_documents(self, chunks):
        self.added += 1
        return [f"id{i}" for i in range(len(chunks))]


class _FakeCrossEncoder:
    def predict(self, pairs):
        return [len(text) for _, text in pairs]  # longer = more relevant


class TestReranker:
    def test_orders_by_score_and_keeps_top_n(self):
        reranker = rerank.Reranker(top_n=2, model=_FakeCrossEncoder())
        docs = [doc("a", "x"), doc("b", "xxx"), doc("c", "xx")]
        kept = reranker.rerank("q", docs)
        assert [d.metadata["source"] for d in kept] == ["b", "c"]
        assert kept[0].metadata["rerank_score"] == 3


class _Retriever:
    """Supports the standalone/retrieve protocol; answers per query."""

    def __init__(self, by_query):
        self.by_query = by_query
        self.queries = []

    def standalone(self, question, chat_history, config=None):
        return question

    def retrieve(self, query, config=None):
        self.queries.append(query)
        return list(self.by_query.get(query, []))


class _Grader:
    def grade(self, question, docs, config=None):
        return [d for d in docs if "relevant" in d.page_content]


class _Rewriter:
    def rewrite(self, question, config=None):
        return "better query"


class _Answer:
    def __init__(self):
        self.seen = None

    def invoke(self, inputs):
        self.seen = inputs["context"]
        return rag.AnswerWithSources(answer="ok", sources_used=["/b"])


class TestCorrectiveRetrieval:
    def test_retries_with_rewritten_query_when_nothing_is_relevant(self):
        retriever = _Retriever({"q": [doc("/a", "noise")],
                                "better query": [doc("/b", "relevant")]})
        answer = _Answer()
        chain = rag.RagChain(retriever, answer, grader=_Grader(), rewriter=_Rewriter())
        result = rag.answer_question(chain, "q", [])
        assert retriever.queries == ["q", "better query"]
        assert [d.metadata["source"] for d in answer.seen] == ["/b"]
        assert result["sources_used"] == ["/b"]

    def test_refuses_without_llm_when_retry_also_finds_nothing(self):
        retriever = _Retriever({"q": [doc("/a", "noise")]})
        answer = _Answer()
        chain = rag.RagChain(retriever, answer, grader=_Grader(), rewriter=_Rewriter())
        result = rag.answer_question(chain, "q", [])
        assert result["guardrail"] == "no_relevant_context"
        assert answer.seen is None

    def test_grader_never_sees_chunks_the_user_cannot_open(self):
        seen = []

        class Grader:
            def grade(self, question, docs, config=None):
                seen.extend(d.metadata["source"] for d in docs)
                return docs

        retriever = _Retriever({"q": [doc("/ok", "relevant"), doc("/secret", "relevant")]})
        chain = rag.RagChain(retriever, _Answer(), grader=Grader())
        rag.answer_question(chain, "q", [], access_check=lambda p: p == "/ok")
        assert seen == ["/ok"]


class TestAnswerCache:
    def _chain(self, tmp_path, answer):
        retriever = _Retriever({"q": [doc("/b", "relevant")]})
        cache = answer_cache.AnswerCache(str(tmp_path / "cache.sqlite"))
        return rag.RagChain(retriever, answer, cache=cache), retriever

    def test_second_ask_is_served_from_cache(self, tmp_path):
        chain, retriever = self._chain(tmp_path, _Answer())
        rag.answer_question(chain, "q", [], user="alice")
        rag.answer_question(chain, "  Q? ", [], user="alice")
        assert retriever.queries == ["q"]

    def test_never_shared_between_users(self, tmp_path):
        chain, retriever = self._chain(tmp_path, _Answer())
        rag.answer_question(chain, "q", [], user="alice")
        rag.answer_question(chain, "q", [], user="bob")
        assert len(retriever.queries) == 2

    def test_revoked_access_turns_a_hit_into_a_miss(self, tmp_path):
        chain, retriever = self._chain(tmp_path, _Answer())
        rag.answer_question(chain, "q", [], user="alice", access_check=lambda p: True)
        result = rag.answer_question(chain, "q", [], user="alice",
                                     access_check=lambda p: False)
        assert len(retriever.queries) == 2
        assert result["guardrail"] == "acl_empty"

    def test_follow_ups_are_not_cached(self, tmp_path):
        chain, retriever = self._chain(tmp_path, _Answer())
        history = ["earlier turn"]
        rag.answer_question(chain, "q", history, user="alice")
        rag.answer_question(chain, "q", history, user="alice")
        assert len(retriever.queries) == 2

    def test_expired_entries_are_misses(self, tmp_path):
        store = answer_cache.AnswerCache(str(tmp_path / "c.sqlite"), ttl_seconds=-1)
        store.put("k", {"answer": "a"})
        assert store.get("k") is None


class TestStreaming:
    def test_secret_split_across_chunks_is_never_shown(self):
        secret = "AKIA" + "A" * 16
        full = "The key is " + secret + " and that is all." + " filler" * 30

        class Streamer:
            def stream(self, inputs, config=None):
                for end in range(1, len(full) + 1, 3):
                    yield rag.AnswerWithSources(answer=full[:end], sources_used=[])
                yield rag.AnswerWithSources(answer=full, sources_used=[])

        shown = []
        result = rag._stream_answer(Streamer(), {}, None, shown.append)
        assert shown, "nothing streamed"
        assert not any("AKIA" in s for s in shown)
        assert result.answer == full  # redaction of the final text happens in _generate


class TestHealth:
    def test_fresh_success_is_healthy(self, tmp_path):
        health.write_status(str(tmp_path), "ok")
        assert health.check(str(tmp_path))[0]

    def test_never_indexed_is_unhealthy(self, tmp_path):
        assert not health.check(str(tmp_path))[0]

    def test_failed_run_keeps_last_success_age(self, tmp_path):
        health.write_status(str(tmp_path), "ok")
        health.write_status(str(tmp_path), "failed", error="NAS unmounted")
        later = time.time() + 40 * 3600
        healthy, message = health.check(str(tmp_path), now=later)
        assert not healthy and "NAS unmounted" in message

    def test_long_first_run_counts_as_healthy(self, tmp_path):
        health.write_status(str(tmp_path), "running")
        assert health.check(str(tmp_path), now=time.time() + 20 * 3600)[0]


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    from pipeline import tracing
    monkeypatch.setattr(tracing, "run_config", lambda **_: None)


class TestOfflineMode:
    def test_off_never_constructs_an_api_client(self, monkeypatch):
        monkeypatch.setattr(rag, "LLM_MODE", "off")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-present-but-ignored")

        def forbidden(*args, **kwargs):
            raise AssertionError("API client constructed in offline mode")

        monkeypatch.setattr(rag, "ChatAnthropic", forbidden)
        monkeypatch.setattr(rag, "build_retriever", lambda *a, **k: _Retriever({}))
        chain = rag.build_chain(vectorstore=None, use_cache=False)
        assert isinstance(chain.answer_chain, rag.ExtractiveAnswerChain)
        assert chain.grader is None and chain.rewriter is None

    def test_auto_is_offline_without_a_key(self, monkeypatch):
        monkeypatch.setattr(rag, "LLM_MODE", "auto")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert not rag.llm_enabled()

    def test_extractive_answer_quotes_passages_with_sources(self):
        relevant = doc("/d/handbook.md", "Deploy window is 10:00-16:00.")
        relevant.metadata["rerank_score"] = 2.5
        result = rag.ExtractiveAnswerChain().invoke({"context": [relevant]})
        assert "10:00-16:00" in result.answer and "handbook.md" in result.answer
        assert result.sources_used == ["/d/handbook.md"]

    def test_low_scoring_passages_become_a_refusal(self):
        unrelated = doc("/d/a.md", "pizza")
        unrelated.metadata["rerank_score"] = -11.0
        result = rag.ExtractiveAnswerChain().invoke({"context": [unrelated]})
        assert result.answer == rag.NO_CONTEXT_ANSWER
        assert result.sources_used == []


class TestRetrieverAcrossThreads:
    def test_cached_retriever_works_from_another_thread(self):
        # Streamlit caches the chain and serves later questions from other
        # threads; a thread-bound sqlite connection raised ProgrammingError.
        import threading

        connection = rag._keyword_index(shared_across_threads=True)
        from search import keyword
        errors = []

        def use():
            try:
                keyword.count(connection)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        worker = threading.Thread(target=use)
        worker.start()
        worker.join()
        assert errors == []
