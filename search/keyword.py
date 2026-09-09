"""Persistent keyword index for hybrid retrieval.

Replaces the in-memory BM25 retriever. That one called
`vectorstore.get()` with no limit on every build, so constructing a
retriever meant loading every chunk in the corpus into Python objects -
fine at 54 chunks, ruinous at the millions a 50 GB share produces, and
paid again for every distinct group filter.

SQLite FTS5 keeps the same job on disk: bm25-ranked keyword search, with
the group filter pushed down into SQL so a restricted user's query
touches only their rows instead of materializing the corpus first.

The tokenizer splits on the punctuation inside URLs and emails, so
"https://linkedin.com/in/x" is matchable by "linkedin". The default
whitespace tokenizer made that one opaque token and any query for
"linkedin" scored zero - the bug rag._tokenize() was written to fix, kept
here because the storage moved but the failure mode did not.
"""
import os
import re

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

# Resolved per call, not at import: the keyword index must follow whatever
# persist directory the vector store is using, including when a test or a
# one-off run points that somewhere else. A path frozen at import silently
# wrote into the default index instead.
def default_db_path(persist_path=None):
    explicit = os.environ.get("RAG_CHUNK_DB")
    if explicit:
        return explicit
    base = persist_path or os.environ.get("RAG_PERSIST_PATH", "./chroma_db")
    return os.path.join(base, "chunks.sqlite")

TOKENIZE = "unicode61 remove_diacritics 2 separators './-_:@?&=+#%~'"

SCHEMA = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    chunk_id UNINDEXED,
    source UNINDEXED,
    folder UNINDEXED,
    tokenize="{TOKENIZE}"
);

CREATE TABLE IF NOT EXISTS chunk_groups (
    chunk_id   TEXT NOT NULL,
    group_name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_groups_id ON chunk_groups(chunk_id);
CREATE INDEX IF NOT EXISTS chunk_groups_name ON chunk_groups(group_name);
"""

_FTS_SPECIAL = re.compile(r"[^\w\s]", re.UNICODE)


def connect(db_path=None, shared_across_threads=False, persist_path=None):
    import sqlite3

    path = db_path or default_db_path(persist_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=not shared_across_threads)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    return connection


# Mirror of the chunks written to Chroma. Group names come from the chunk's
# group_* metadata keys, so the two stores stay filtered by the same facts.
def add_chunks(connection, chunks, ids):
    for chunk, chunk_id in zip(chunks, ids):
        metadata = chunk.metadata or {}
        connection.execute(
            "INSERT INTO chunks_fts (text, chunk_id, source, folder) VALUES (?, ?, ?, ?)",
            (chunk.page_content, chunk_id, metadata.get("source", ""),
             metadata.get("folder", "")),
        )
        for key, value in metadata.items():
            if key.startswith("group_") and value:
                connection.execute(
                    "INSERT INTO chunk_groups (chunk_id, group_name) VALUES (?, ?)",
                    (chunk_id, key[len("group_"):]),
                )
    connection.commit()


def delete_source(connection, source):
    ids = [r["chunk_id"] for r in connection.execute(
        "SELECT chunk_id FROM chunks_fts WHERE source = ?", (source,))]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        connection.execute(
            f"DELETE FROM chunk_groups WHERE chunk_id IN ({placeholders})", ids)
    connection.execute("DELETE FROM chunks_fts WHERE source = ?", (source,))
    connection.commit()


def count(connection):
    return connection.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]


# Free-text questions are not FTS5 syntax: an apostrophe, a hyphen or a
# stray parenthesis is a syntax error, not a search. Terms are OR-ed
# because a relevant chunk rarely contains every word of the question.
def to_match_expression(text):
    words = [w for w in _FTS_SPECIAL.sub(" ", text).split() if len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words)


def search(connection, query, k, allowed_groups=None):
    expression = to_match_expression(query)
    if not expression:
        return []

    sql = ["SELECT text, chunk_id, source, folder, bm25(chunks_fts) AS score",
           "FROM chunks_fts WHERE chunks_fts MATCH ?"]
    params = [expression]

    # None means unrestricted. An empty list must deny everything rather
    # than match everything - the same fail-closed rule the Chroma filter
    # follows, and the one whose inverse would be a silent leak.
    if allowed_groups is not None:
        if not allowed_groups:
            return []
        placeholders = ",".join("?" for _ in allowed_groups)
        sql.append(
            f"AND EXISTS (SELECT 1 FROM chunk_groups g WHERE g.chunk_id = "
            f"chunks_fts.chunk_id AND g.group_name IN ({placeholders}))"
        )
        params.extend(allowed_groups)

    sql.append("ORDER BY score LIMIT ?")
    params.append(k)

    return [
        Document(
            page_content=row["text"],
            metadata={"source": row["source"], "folder": row["folder"],
                      "chunk_id": row["chunk_id"]},
        )
        for row in connection.execute(" ".join(sql), params)
    ]


class FtsRetriever(BaseRetriever):
    """LangChain retriever over the SQLite index, so it can slot into the
    existing EnsembleRetriever in place of BM25Retriever."""

    connection: object
    k: int = 4
    allowed_groups: list | None = None

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(self, query, *, run_manager=None):
        return search(self.connection, query, self.k, self.allowed_groups)
