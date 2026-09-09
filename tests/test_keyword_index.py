"""Persistent keyword-index tests.

These carry over the guarantees the in-memory BM25 retriever provided -
URLs and emails must stay matchable, group filtering must fail closed -
because the storage changed but the failure modes did not.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document  # noqa: E402
from search import keyword  # noqa: E402


def chunk(text, source="/mnt/nas/a.txt", **metadata):
    return Document(page_content=text, metadata={"source": source, **metadata})


@pytest.fixture
def index(tmp_path):
    connection = keyword.connect(str(tmp_path / "chunks.sqlite"))
    yield connection
    connection.close()


def sources(documents):
    return [d.metadata["source"] for d in documents]


class TestTokenizer:
    """The bug this replaces: the default whitespace tokenizer made a whole
    URL one opaque token, so a query for "linkedin" scored zero."""

    def test_url_is_matchable_by_its_parts(self, index):
        keyword.add_chunks(index, [chunk("See https://www.linkedin.com/in/sam-rivera")], ["c1"])
        assert keyword.search(index, "linkedin", 5)
        assert keyword.search(index, "rivera", 5)

    def test_email_is_matchable_by_its_parts(self, index):
        keyword.add_chunks(index, [chunk("write to jane.doe@example.com")], ["c1"])
        assert keyword.search(index, "jane", 5)
        assert keyword.search(index, "example", 5)

    def test_question_punctuation_is_not_a_syntax_error(self, index):
        # "What's the Q1-2026 (final) budget?" is valid English and invalid
        # FTS5 syntax; the raw string would raise rather than search.
        keyword.add_chunks(index, [chunk("the final budget for Q1")], ["c1"])
        assert keyword.search(index, "What's the Q1-2026 (final) budget?", 5)

    def test_empty_query_returns_nothing(self, index):
        keyword.add_chunks(index, [chunk("content")], ["c1"])
        assert keyword.search(index, "?! -", 5) == []


class TestGroupFiltering:
    @pytest.fixture
    def populated(self, index):
        keyword.add_chunks(index, [
            chunk("salary bands for the year", "/mnt/nas/HR/pay.txt", group_HR=True),
            chunk("salary of the deployment", "/mnt/nas/Eng/dep.txt", group_Engineering=True),
        ], ["c1", "c2"])
        return index

    def test_none_means_unrestricted(self, populated):
        assert len(keyword.search(populated, "salary", 10)) == 2

    def test_filters_to_the_users_groups(self, populated):
        found = keyword.search(populated, "salary", 10, allowed_groups=["HR"])
        assert sources(found) == ["/mnt/nas/HR/pay.txt"]

    def test_empty_group_list_denies_everything(self, populated):
        # Must deny, never match everything: the inverse is a silent leak.
        assert keyword.search(populated, "salary", 10, allowed_groups=[]) == []

    def test_unknown_group_matches_nothing(self, populated):
        assert keyword.search(populated, "salary", 10, allowed_groups=["Nobody"]) == []

    def test_multiple_groups_are_or_ed(self, populated):
        found = keyword.search(populated, "salary", 10,
                               allowed_groups=["HR", "Engineering"])
        assert len(found) == 2


class TestLifecycle:
    def test_deleting_a_source_removes_its_chunks_and_group_rows(self, index):
        keyword.add_chunks(index, [
            chunk("first part", "/mnt/nas/a.txt", group_HR=True),
            chunk("second part", "/mnt/nas/a.txt", group_HR=True),
            chunk("other file", "/mnt/nas/b.txt", group_HR=True),
        ], ["c1", "c2", "c3"])

        keyword.delete_source(index, "/mnt/nas/a.txt")

        assert keyword.count(index) == 1
        assert index.execute("SELECT COUNT(*) AS n FROM chunk_groups").fetchone()["n"] == 1
        assert keyword.search(index, "first", 5) == []

    def test_reindexing_a_file_does_not_leave_stale_text(self, index):
        keyword.add_chunks(index, [chunk("old wording", "/mnt/nas/a.txt")], ["c1"])
        keyword.delete_source(index, "/mnt/nas/a.txt")
        keyword.add_chunks(index, [chunk("new wording", "/mnt/nas/a.txt")], ["c2"])

        assert keyword.search(index, "old", 5) == []
        assert keyword.search(index, "new", 5)

    def test_respects_k(self, index):
        keyword.add_chunks(
            index,
            [chunk(f"budget line {i}", f"/mnt/nas/{i}.txt") for i in range(10)],
            [f"c{i}" for i in range(10)],
        )
        assert len(keyword.search(index, "budget", 3)) == 3


class TestRetrieverInterface:
    def test_behaves_as_a_langchain_retriever(self, index):
        keyword.add_chunks(index, [chunk("quarterly revenue report")], ["c1"])
        retriever = keyword.FtsRetriever(connection=index, k=5)
        assert sources(retriever.invoke("revenue")) == ["/mnt/nas/a.txt"]

    def test_passes_its_group_filter_through(self, index):
        keyword.add_chunks(index, [
            chunk("revenue detail", "/mnt/nas/HR/a.txt", group_HR=True),
            chunk("revenue detail", "/mnt/nas/Eng/b.txt", group_Engineering=True),
        ], ["c1", "c2"])
        retriever = keyword.FtsRetriever(connection=index, k=5, allowed_groups=["HR"])
        assert sources(retriever.invoke("revenue")) == ["/mnt/nas/HR/a.txt"]


class TestDefaultPath:
    def test_follows_the_configured_persist_directory(self, monkeypatch):
        # Regression: the path was resolved at import, so a run pointed at
        # a different index still wrote its keyword rows into the default.
        monkeypatch.delenv("RAG_CHUNK_DB", raising=False)
        monkeypatch.setenv("RAG_PERSIST_PATH", "/tmp/somewhere-else")
        assert keyword.default_db_path() == "/tmp/somewhere-else/chunks.sqlite"
        assert keyword.default_db_path("/explicit") == "/explicit/chunks.sqlite"

    def test_explicit_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("RAG_CHUNK_DB", "/var/db/chunks.sqlite")
        assert keyword.default_db_path("/ignored") == "/var/db/chunks.sqlite"
