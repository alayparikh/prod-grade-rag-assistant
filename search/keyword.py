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
import json
import logging
import os
import re
import threading
import time

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

-- Which FTS rows belong to which file. `source` inside chunks_fts is
-- UNINDEXED, so deleting a file's rows by it scanned the whole index once
-- per changed file: minutes per file at millions of chunks.
CREATE TABLE IF NOT EXISTS chunk_sources (
    fts_rowid INTEGER PRIMARY KEY,
    chunk_id  TEXT NOT NULL,
    source    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_sources_source ON chunk_sources(source);
"""

_FTS_SPECIAL = re.compile(r"[^\w\s]", re.UNICODE)

# Common words match most of the corpus: every one OR-ed into the query
# walks a posting list as long as the index. Dropped unless the question is
# nothing but stop words.
STOP_WORDS = frozenset("""
a an and are as at be by can do does for from has have how i in is it its
me my of on or our that the their them there these this to was we what when
where which who whom why will with you your
""".split())
MAX_QUERY_TERMS = 32
# Wall-clock budget for one keyword query. Past it the query is interrupted
# and the keyword half of retrieval returns nothing (vector search still
# answers), logged as keyword_timeout.
QUERY_TIME_BUDGET_S = float(os.environ.get("RAG_KEYWORD_TIMEOUT_S", 2.0))
# Max parameters per IN (...) list.
_BATCH = 500

# The deadline is per thread: in the web app one connection is shared by
# Streamlit's pool threads (serialized SQLite), and the progress handler runs
# on whichever thread is executing.
_deadline = threading.local()


def _past_deadline():
    return int(time.monotonic() > getattr(_deadline, "at", float("inf")))


def connect(db_path=None, shared_across_threads=False, persist_path=None):
    import sqlite3

    path = db_path or default_db_path(persist_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=not shared_across_threads)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    # Installed once; only search() sets a deadline, so writes are unaffected.
    connection.set_progress_handler(_past_deadline, 10_000)
    return connection


# Mirror of the chunks written to Chroma. Group names come from the chunk's
# group_* metadata keys, so the two stores stay filtered by the same facts.
def add_chunks(connection, chunks, ids):
    for chunk, chunk_id in zip(chunks, ids):
        metadata = chunk.metadata or {}
        cursor = connection.execute(
            "INSERT INTO chunks_fts (text, chunk_id, source, folder) VALUES (?, ?, ?, ?)",
            (chunk.page_content, chunk_id, metadata.get("source", ""),
             metadata.get("folder", "")),
        )
        connection.execute(
            "INSERT INTO chunk_sources (fts_rowid, chunk_id, source) VALUES (?, ?, ?)",
            (cursor.lastrowid, chunk_id, metadata.get("source", "")),
        )
        for key, value in metadata.items():
            if key.startswith("group_") and value:
                connection.execute(
                    "INSERT INTO chunk_groups (chunk_id, group_name) VALUES (?, ?)",
                    (chunk_id, key[len("group_"):]),
                )
    connection.commit()


def _in_batches(values):
    for i in range(0, len(values), _BATCH):
        batch = values[i:i + _BATCH]
        yield batch, ",".join("?" for _ in batch)


def delete_source(connection, source):
    rows = connection.execute(
        "SELECT fts_rowid, chunk_id FROM chunk_sources WHERE source = ?", (source,)).fetchall()
    if rows:
        for batch, marks in _in_batches([r["fts_rowid"] for r in rows]):
            connection.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({marks})", batch)
        for batch, marks in _in_batches([r["chunk_id"] for r in rows]):
            connection.execute(f"DELETE FROM chunk_groups WHERE chunk_id IN ({marks})", batch)
        connection.execute("DELETE FROM chunk_sources WHERE source = ?", (source,))
    else:
        # Rows written before chunk_sources existed: the slow path, once per
        # file, after which the file's new rows are tracked.
        ids = [r["chunk_id"] for r in connection.execute(
            "SELECT chunk_id FROM chunks_fts WHERE source = ?", (source,))]
        for batch, marks in _in_batches(ids):
            connection.execute(f"DELETE FROM chunk_groups WHERE chunk_id IN ({marks})", batch)
        connection.execute("DELETE FROM chunks_fts WHERE source = ?", (source,))
    connection.commit()


def count(connection):
    return connection.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]


def is_empty(connection):
    """Constant time, unlike count(): checked on every retriever build."""
    return connection.execute("SELECT 1 FROM chunks_fts LIMIT 1").fetchone() is None


# Free-text questions are not FTS5 syntax: an apostrophe, a hyphen or a
# stray parenthesis is a syntax error, not a search. Terms are OR-ed
# because a relevant chunk rarely contains every word of the question.
def to_match_expression(text):
    words = [w for w in _FTS_SPECIAL.sub(" ", text).split() if len(w) > 1]
    content = [w for w in words if w.lower() not in STOP_WORDS] or words
    unique = list(dict.fromkeys(w.lower() for w in content))[:MAX_QUERY_TERMS]
    return " OR ".join(f'"{w}"' for w in unique)


def search(connection, query, k, allowed_groups=None):
    expression = to_match_expression(query)
    if not expression:
        return []
    _deadline.at = time.monotonic() + QUERY_TIME_BUDGET_S
    try:
        return _search(connection, expression, k, allowed_groups)
    except Exception as e:  # sqlite3.OperationalError: interrupted
        if "interrupted" not in str(e):
            raise
        logging.getLogger("rag.events").info(json.dumps(
            {"event": "keyword_timeout", "budget_s": QUERY_TIME_BUDGET_S, "query_len": len(query)}))
        return []
    finally:
        _deadline.at = float("inf")


def _search(connection, expression, k, allowed_groups):

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
