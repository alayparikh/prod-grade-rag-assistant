"""Layer 1: the file census.

Walks the NAS mount and records one row per file - name, path, extension,
size, mtime - into SQLite, with an FTS5 index over names and paths. This
is what answers "where is the 2026 Diwali flyer" without embedding a
single byte, and it is also the work list the content indexer consumes so
the tree is walked once per run rather than once per layer.

Incremental by (size, mtime_ns): a file whose size and mtime are unchanged
is not reopened. On a 50 GB SMB mount that difference is the whole nightly
run, because reading every file to hash it means pulling 50 GB over the
wire each night.

Configuration (env):
    RAG_DOCS_PATH      Root to crawl (default /mnt/nas).
    RAG_META_DB        SQLite path (default <RAG_PERSIST_PATH>/meta.sqlite).
    RAG_EXCLUDE_GLOBS  Extra comma-separated directory/file globs to skip.
"""
import fnmatch
import os
import sqlite3
import time

DOCS_PATH = os.environ.get("RAG_DOCS_PATH", "/mnt/nas")
PERSIST_PATH = os.environ.get("RAG_PERSIST_PATH", "./chroma_db")
META_DB_PATH = os.environ.get("RAG_META_DB", os.path.join(PERSIST_PATH, "meta.sqlite"))

# NAS housekeeping directories, editor litter, and OS metadata. These hold
# no user documents and on a Synology/QNAP share @eaDir alone can hold a
# thumbnail per image, which would multiply the row count for nothing.
DEFAULT_EXCLUDE_DIRS = (
    "@eaDir", "#recycle", "#snapshot", ".Trash*", ".TemporaryItems",
    "$RECYCLE.BIN", "System Volume Information", ".git", ".svn",
    "node_modules", "__pycache__", ".venv", "venv",
)
DEFAULT_EXCLUDE_FILES = (
    ".DS_Store", "._*", "Thumbs.db", "desktop.ini", "~$*", "*.tmp", "*.part",
    "*.lock",
)

# Extensions the content layer can currently turn into text. Everything
# else is still censused - a file that only layer 1 can find is far better
# than a file nobody can find - but is marked indexable=0 so the content
# sync does not try to load it.
INDEXABLE_EXTENSIONS = frozenset({
    ".pdf", ".txt", ".md", ".docx", ".xlsx", ".pptx", ".eml", ".msg",
    ".csv", ".rtf", ".odt", ".html", ".htm",
})

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    folder      TEXT NOT NULL,
    ext         TEXT NOT NULL,
    size        INTEGER NOT NULL,
    mtime_ns    INTEGER NOT NULL,
    indexable   INTEGER NOT NULL DEFAULT 0,
    seen_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS files_folder ON files(folder);
CREATE INDEX IF NOT EXISTS files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS files_mtime ON files(mtime_ns);

-- Contentless-delta FTS over the human-meaningful parts of a path. The
-- content table is files, so names are stored once rather than twice.
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    name, folder, content='files', content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    started_at  REAL NOT NULL,
    finished_at REAL,
    scanned     INTEGER NOT NULL DEFAULT 0,
    added       INTEGER NOT NULL DEFAULT 0,
    updated     INTEGER NOT NULL DEFAULT 0,
    removed     INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0
);
"""


def connect(db_path=None):
    path = db_path or META_DB_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    # WAL lets the Streamlit app read the census while the nightly indexer
    # is still writing it, instead of blocking on the writer's lock.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(SCHEMA)
    return connection


def _exclude_globs():
    extra = os.environ.get("RAG_EXCLUDE_GLOBS", "")
    return tuple(g.strip() for g in extra.split(",") if g.strip())


def _matches(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def is_excluded_dir(name, extra=()):
    return _matches(name, DEFAULT_EXCLUDE_DIRS + tuple(extra))


def is_excluded_file(name, extra=()):
    if name.startswith("."):
        return True
    return _matches(name, DEFAULT_EXCLUDE_FILES + tuple(extra))


# Yield (path, stat_result) for every eligible file under root. Directories
# that cannot be listed are reported through on_error rather than aborting
# the crawl: one unreadable folder on a 50 GB share must not cost the whole
# night's index.
def walk_files(root, extra_excludes=(), on_error=None):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as e:
            if on_error:
                on_error(current, e)
            continue

        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if not is_excluded_dir(entry.name, extra_excludes):
                        stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    if not is_excluded_file(entry.name, extra_excludes):
                        yield entry.path, entry.stat()
            except OSError as e:
                if on_error:
                    on_error(entry.path, e)


def _row(path, stat_result, root):
    folder = os.path.dirname(os.path.relpath(path, root))
    ext = os.path.splitext(path)[1].lower()
    return {
        "path": path,
        "name": os.path.basename(path),
        "folder": folder,
        "ext": ext,
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "indexable": 1 if ext in INDEXABLE_EXTENSIONS else 0,
    }


# Bring the files table in line with what is on disk. Returns counts rather
# than printing, so the caller decides how to report.
def crawl(root=None, connection=None, extra_excludes=None, on_error=None):
    root = os.path.abspath(root or DOCS_PATH)
    own_connection = connection is None
    connection = connection or connect()
    extra_excludes = extra_excludes if extra_excludes is not None else _exclude_globs()

    started = time.time()
    stats = {"scanned": 0, "added": 0, "updated": 0, "removed": 0, "errors": 0}

    def record_error(path, error):
        stats["errors"] += 1
        if on_error:
            on_error(path, error)

    known = {
        row["path"]: (row["size"], row["mtime_ns"])
        for row in connection.execute("SELECT path, size, mtime_ns FROM files")
    }

    try:
        seen = set()
        for path, stat_result in walk_files(root, extra_excludes, record_error):
            stats["scanned"] += 1
            seen.add(path)
            row = _row(path, stat_result, root)
            previous = known.get(path)

            if previous is None:
                stats["added"] += 1
            elif previous == (row["size"], row["mtime_ns"]):
                continue  # unchanged: not reopened, not rewritten
            else:
                stats["updated"] += 1

            _upsert(connection, row, started)

        removed = [p for p in known if p not in seen]
        for path in removed:
            _delete(connection, path)
        stats["removed"] = len(removed)

        connection.execute(
            "INSERT INTO crawl_runs (started_at, finished_at, scanned, added, "
            "updated, removed, errors) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (started, time.time(), stats["scanned"], stats["added"],
             stats["updated"], stats["removed"], stats["errors"]),
        )
        connection.commit()
    finally:
        if own_connection:
            connection.close()

    return stats


# FTS5 external-content tables do not follow their content table on their
# own; every write has to be mirrored. Deleting first (with the old values,
# which the 'delete' command requires) keeps the index from accumulating
# stale rows for a renamed or re-created path.
def _upsert(connection, row, seen_at):
    existing = connection.execute(
        "SELECT rowid, name, folder FROM files WHERE path = ?", (row["path"],)
    ).fetchone()

    if existing is not None:
        connection.execute(
            "INSERT INTO files_fts(files_fts, rowid, name, folder) "
            "VALUES ('delete', ?, ?, ?)",
            (existing["rowid"], existing["name"], existing["folder"]),
        )

    connection.execute(
        "INSERT INTO files (path, name, folder, ext, size, mtime_ns, indexable, seen_at) "
        "VALUES (:path, :name, :folder, :ext, :size, :mtime_ns, :indexable, :seen_at) "
        "ON CONFLICT(path) DO UPDATE SET "
        "name=excluded.name, folder=excluded.folder, ext=excluded.ext, "
        "size=excluded.size, mtime_ns=excluded.mtime_ns, "
        "indexable=excluded.indexable, seen_at=excluded.seen_at",
        {**row, "seen_at": seen_at},
    )
    rowid = connection.execute(
        "SELECT rowid FROM files WHERE path = ?", (row["path"],)
    ).fetchone()["rowid"]
    connection.execute(
        "INSERT INTO files_fts(rowid, name, folder) VALUES (?, ?, ?)",
        (rowid, row["name"], row["folder"]),
    )


def _delete(connection, path):
    existing = connection.execute(
        "SELECT rowid, name, folder FROM files WHERE path = ?", (path,)
    ).fetchone()
    if existing is None:
        return
    connection.execute(
        "INSERT INTO files_fts(files_fts, rowid, name, folder) "
        "VALUES ('delete', ?, ?, ?)",
        (existing["rowid"], existing["name"], existing["folder"]),
    )
    connection.execute("DELETE FROM files WHERE path = ?", (path,))


# What the content indexer works from: files this build can turn into text.
def indexable_paths(connection):
    return [r["path"] for r in connection.execute(
        "SELECT path FROM files WHERE indexable = 1 ORDER BY path"
    )]


# Week-1 deliverable: the numbers that decide OCR scope and embedding
# model before anyone commits to indexing 50 GB.
def census(connection):
    by_ext = [
        dict(ext=r["ext"] or "(none)", files=r["files"], bytes=r["bytes"])
        for r in connection.execute(
            "SELECT ext, COUNT(*) AS files, SUM(size) AS bytes FROM files "
            "GROUP BY ext ORDER BY SUM(size) DESC"
        )
    ]
    totals = connection.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes FROM files"
    ).fetchone()
    indexable = connection.execute(
        "SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes "
        "FROM files WHERE indexable = 1"
    ).fetchone()
    return {
        "total_files": totals["files"],
        "total_bytes": totals["bytes"],
        "indexable_files": indexable["files"],
        "indexable_bytes": indexable["bytes"],
        "by_ext": by_ext,
    }


def human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def format_census(report):
    lines = [
        f"{report['total_files']:,} files, {human_bytes(report['total_bytes'])} total",
        f"{report['indexable_files']:,} indexable, "
        f"{human_bytes(report['indexable_bytes'])}",
        "",
        f"{'ext':<10}{'files':>10}{'size':>12}",
    ]
    for row in report["by_ext"][:25]:
        lines.append(f"{row['ext']:<10}{row['files']:>10,}"
                     f"{human_bytes(row['bytes']):>12}")
    return "\n".join(lines)
