"""Layer 1 query path: a question becomes a filename search.

Haiku turns "the flyer for Diwali 2026" into search terms plus optional
extension and year filters; SQLite FTS5 matches those against file names
and folder paths. No embeddings, no chunk text, no Sonnet call - this is
the cheap layer that answers "where is X" for the many files whose
content is never worth indexing (images, CAD, archives).

Every result still passes the caller's access check before it is shown.
"""
import os
import re

from pydantic import BaseModel, Field

ROUTER_MODEL = os.environ.get("RAG_ROUTER_MODEL", "claude-haiku-4-5")
DEFAULT_LIMIT = int(os.environ.get("RAG_FIND_LIMIT", 20))

# FTS5 treats these as operators/syntax. A user asking for "Q1-2026 (final)"
# would otherwise produce a malformed MATCH expression and an exception
# where they expected results.
_FTS_SPECIAL = re.compile(r'[^\w\s]', re.UNICODE)


class FileQuery(BaseModel):
    """What the router extracts from a natural-language file request."""

    terms: list[str] = Field(
        default_factory=list,
        description="Distinctive words likely to appear in the file name or "
                    "its folder path. Omit generic words like 'file', "
                    "'document', 'find', 'show'.",
    )
    extensions: list[str] = Field(
        default_factory=list,
        description="File extensions to restrict to, with the dot, e.g. "
                    "['.pdf', '.docx']. Empty means any type.",
    )
    year: int | None = Field(
        default=None,
        description="Four-digit year the file relates to, if the question "
                    "names one. Null otherwise.",
    )


# Build a safe FTS5 MATCH expression: every term becomes a prefix query so
# "diwali" finds "Diwali2026Flyer", and terms are OR-ed because a file name
# rarely contains every word of the question.
def build_match_expression(terms):
    cleaned = []
    for term in terms:
        stripped = _FTS_SPECIAL.sub(" ", term).strip()
        for word in stripped.split():
            if len(word) > 1:
                cleaned.append(f'"{word}"*')
    return " OR ".join(cleaned)


def parse_question(question, llm=None):
    """Extract a FileQuery from the question. Falls back to the question's
    own words when no LLM is available, so the file search still works
    without an API key (and in retrieval-only evals)."""
    if llm is None:
        return FileQuery(terms=_fallback_terms(question), extensions=[], year=_find_year(question))

    structured = llm.with_structured_output(FileQuery)
    return structured.invoke(
        "Extract file-search criteria from this request. Keep only "
        "distinctive words that would plausibly appear in a file name or "
        f"folder path.\n\nRequest: {question}"
    )


_STOPWORDS = frozenset("""
a an the of for from in on at to by with and or is are was were be been
show find get me my our all any please can you what where which who when
file files document documents folder folder's need want looking look
""".split())


def _fallback_terms(question):
    words = re.findall(r"[\w']+", question.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _find_year(question):
    match = re.search(r"\b(19|20)\d{2}\b", question)
    return int(match.group()) if match else None


# Run the query. access_check, when given, is applied to every candidate
# before it is returned, so a stale index row cannot surface a path this
# user has since lost access to. Over-fetches for the same reason the
# content path does.
def search_files(connection, query, limit=DEFAULT_LIMIT, access_check=None):
    match_expression = build_match_expression(query.terms)
    if not match_expression:
        return []

    sql = [
        "SELECT f.path, f.name, f.folder, f.ext, f.size, f.mtime_ns",
        "FROM files_fts JOIN files f ON f.rowid = files_fts.rowid",
        "WHERE files_fts MATCH ?",
    ]
    params = [match_expression]

    if query.extensions:
        placeholders = ",".join("?" for _ in query.extensions)
        sql.append(f"AND f.ext IN ({placeholders})")
        params.extend(e.lower() if e.startswith(".") else f".{e.lower()}"
                      for e in query.extensions)

    if query.year:
        # A year in the question can mean either the file's name or its
        # modification time; matching only one of the two loses obvious
        # hits, so accept either.
        sql.append("AND (f.name LIKE ? OR f.folder LIKE ? "
                   "OR CAST(strftime('%Y', f.mtime_ns / 1000000000, 'unixepoch') AS INTEGER) = ?)")
        params.extend([f"%{query.year}%", f"%{query.year}%", query.year])

    sql.append("ORDER BY bm25(files_fts) LIMIT ?")
    params.append(limit * 3 if access_check else limit)

    rows = connection.execute(" ".join(sql), params).fetchall()

    results = []
    for row in rows:
        if access_check is not None and not access_check(row["path"]):
            continue
        results.append(dict(row))
        if len(results) >= limit:
            break
    return results
