import argparse
import hashlib
import json
import logging
import logging.handlers
import os
import re
import sqlite3
import sys
import time

import yaml

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_anthropic.chat_models import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.documents import Document
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel, Field

from pipeline import cache as answer_cache
from pipeline import chunking, grading, rerank, tracing
from pipeline.prompts import ANSWER_PROMPT, CONTEXTUALIZE_PROMPT
from search import keyword

# Overridable via env so tests/CI can point at a fixture corpus and a
# throwaway index without touching the real ones.
DOCS_PATH = os.environ.get("RAG_DOCS_PATH", "./docs")
PERSIST_PATH = os.environ.get("RAG_PERSIST_PATH", "./chroma_db")
MANIFEST_PATH = os.path.join(PERSIST_PATH, "manifest.json")
PERMISSIONS_PATH = os.environ.get("RAG_PERMISSIONS_PATH", "./permissions.yaml")
# Overridable because the right model depends on the corpus, which is not
# known until the census runs: bge-small is a straight upgrade on
# MiniLM for English, and bge-m3 is the one to use if the share turns out
# to hold Hindi or Gujarati documents. Changing this invalidates every
# stored embedding, so it requires a full reindex.
EMBEDDING_MODEL = os.environ.get(
    "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MODEL = "claude-sonnet-5"

# "anthropic" calls Claude; "off" never constructs an API client and answers
# with the best-matching passages instead (extractive mode, zero cost);
# "auto" is "anthropic" when ANTHROPIC_API_KEY is set, "off" otherwise, so
# a fresh clone runs without a key. Set "off" on any instance the public
# can reach unless its spend is capped.
LLM_MODE = os.environ.get("RAG_LLM", "auto").lower()
EXTRACTIVE_MODEL = "extractive"  # cache-key and log label for offline answers
# Reranker score below which a passage counts as unrelated in offline mode,
# where there is no model to say "I don't know". Calibrated on the fixture
# corpus with ms-marco-MiniLM: answering passages scored -4 to +5,
# unrelated questions' best passages about -11. Model-specific: re-check
# it when changing RAG_RERANK_MODEL.
OFFLINE_MIN_SCORE = float(os.environ.get("RAG_OFFLINE_MIN_SCORE", -6))
OFFLINE_MAX_PASSAGES = 3
OFFLINE_PASSAGE_CHARS = 700


def llm_enabled():
    if LLM_MODE == "off":
        return False
    if LLM_MODE == "anthropic":
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
HISTORY_TURNS = 10  # remember last 10 exchanges
SUPERUSER_GROUP = "ALL"  # bypasses document filtering entirely

# Retrieval breadth. k is derived from corpus size rather than hardcoded:
# top-4 of a 54-chunk corpus is the top 7%, but top-4 of a 1000-chunk corpus
# is the top 0.4% - the same constant silently narrows recall as documents
# are added. Set RAG_RETRIEVAL_K to pin an explicit value instead.
RETRIEVAL_K_MIN = 4
RETRIEVAL_K_MAX = 20
RETRIEVAL_K_PER_CHUNKS = 100  # +1 to k per this many chunks in the corpus
RETRIEVAL_K_OVERRIDE = os.environ.get("RAG_RETRIEVAL_K")

MAX_QUESTION_LENGTH = 2000  # input guardrail: reject before any retrieval/LLM call
LOG_PATH = os.environ.get("RAG_LOG_PATH", "./logs/events.jsonl")
LOG_MAX_BYTES = int(os.environ.get("RAG_LOG_MAX_BYTES", 10 * 1024 * 1024))
LOG_BACKUP_COUNT = 5  # with LOG_MAX_BYTES, caps the log directory at ~50MB
# Spreadsheets on a shared drive can run to hundreds of thousands of rows
# (exports, logs). Past a few thousand rows a sheet is a database, not a
# document, and embedding all of it buries every real document in the
# index; the cap keeps the head of the sheet, where the schema and the
# representative rows are.
XLSX_MAX_ROWS = int(os.environ.get("RAG_XLSX_MAX_ROWS", 2000))

OCR_ENABLED = os.environ.get("RAG_OCR", "1") != "0"
OCR_LANGS = os.environ.get("RAG_OCR_LANGS", "eng")
OCR_MAX_PAGES = int(os.environ.get("RAG_OCR_MAX_PAGES", 50))
OCR_DPI = int(os.environ.get("RAG_OCR_DPI", 200))

NO_CONTEXT_ANSWER = "I don't have information on that in the indexed documents."

# When a per-file access check is in play, retrieval over-fetches by this
# factor so that dropping the files this user cannot open still leaves
# enough context to answer from. The check is authoritative and runs on
# every question; the index-time group tags are only a pre-filter, and on
# a NAS whose group membership cannot be resolved there is no pre-filter
# at all, so over-fetching is what keeps recall usable for those users.
OVER_FETCH_MULTIPLIER = int(os.environ.get("RAG_OVER_FETCH", 3))

# Deliberately identical to NO_CONTEXT_ANSWER: a user must not be able to
# tell "this does not exist" apart from "this exists but is not yours".
# The distinction is recorded in the event log for admins, never shown.
NO_ACCESS_ANSWER = NO_CONTEXT_ANSWER

# USD per 1M tokens, (input, output). A model missing here logs its token
# counts with cost_usd=None rather than being priced with a guessed rate.
PRICING = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

# High-precision only: patterns specific enough that a false positive is
# unlikely to clobber legitimate content (medical record IDs, phone
# numbers, and specimen numbers in these docs are long digit runs that a
# generic "looks like a card number" regex would wrongly redact, so that
# class of pattern is deliberately not included here).
_SECRET_PATTERNS = [
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b"), "[REDACTED-API-KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[REDACTED-API-KEY]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    # Indian PAN: five letters, four digits, one letter. The shape is
    # distinctive enough to stand alone.
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[REDACTED-PAN]"),
]

# Aadhaar is twelve digits, a shape shared with order numbers, phone
# numbers with country codes, and invoice references - all of which appear
# in these documents. Redacting on shape alone would corrupt legitimate
# answers, so it is redacted only when the surrounding text names it.
_AADHAAR_CONTEXT = re.compile(
    r"(?i)\b(?:aadhaar|aadhar|uidai|uid)\b[^\n]{0,30}?"
    r"(\b\d{4}[ -]?\d{4}[ -]?\d{4}\b)"
)


def redact_secrets(text):
    redacted = False
    for pattern, placeholder in _SECRET_PATTERNS:
        text, count = pattern.subn(placeholder, text)
        redacted = redacted or count > 0

    def _mask_aadhaar(match):
        return match.group(0).replace(match.group(1), "[REDACTED-AADHAAR]")

    text, count = _AADHAAR_CONTEXT.subn(_mask_aadhaar, text)
    return text, redacted or count > 0


_event_logger = None


# One rotating handler, created lazily and only once. Streamlit re-executes
# the script on every interaction, so an unguarded setup would stack a new
# handler per rerun and write each event N times.
def _get_event_logger():
    global _event_logger
    if _event_logger is not None:
        return _event_logger

    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
    logger = logging.getLogger("rag.events")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # keep events out of the root/console logger

    # Look for *our* file handler specifically, not just any handler. A bare
    # "if not logger.handlers" check silently skips setup whenever the host
    # has attached its own handler to this logger (pytest's capture plugin
    # and several app servers do), and event logging then writes nowhere.
    target = os.path.abspath(LOG_PATH)
    already_attached = any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and os.path.abspath(getattr(h, "baseFilename", "")) == target
        for h in logger.handlers
    )
    if not already_attached:
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))  # raw JSON per line
        logger.addHandler(handler)

    _event_logger = logger
    return logger


def log_event(event):
    _get_event_logger().info(json.dumps({"ts": time.time(), **event}))


# Collapse the callback's per-model usage into flat totals plus a cost.
# Returns cost_usd=None (not 0) when a model isn't in PRICING, so "unpriced"
# stays distinguishable from "genuinely free" when summing a day of logs.
def summarize_usage(usage_metadata):
    input_tokens = sum(u.get("input_tokens", 0) for u in usage_metadata.values())
    output_tokens = sum(u.get("output_tokens", 0) for u in usage_metadata.values())

    cost = 0.0
    for model, usage in usage_metadata.items():
        if model not in PRICING:
            cost = None
            break
        in_rate, out_rate = PRICING[model]
        cost += (usage.get("input_tokens", 0) / 1_000_000) * in_rate
        cost += (usage.get("output_tokens", 0) / 1_000_000) * out_rate

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6) if cost is not None else None,
        "models_called": sorted(usage_metadata),
    }


# Load the folder -> allowed-groups mapping used to tag each chunk on ingest
def load_permissions():
    if not os.path.exists(PERMISSIONS_PATH):
        return {}, ["Everyone"]
    with open(PERMISSIONS_PATH) as f:
        config = yaml.safe_load(f) or {}
    return config.get("folders", {}), config.get("default_groups", ["Everyone"])


# Every indexed path is stored absolute. The crawler produces absolute
# paths (it walks an absolute root) while discover_files() produced
# "./docs/x" ones, so a corpus indexed by `python -m indexer` and then
# synced from the app looked entirely removed and entirely new: a full
# re-embed of the share on every app start.
def _normalize_path(path):
    return os.path.abspath(path)


# Which groups can see this file - the longest matching folder prefix wins,
# falling back to default_groups for anything not under a listed folder.
def groups_for_path(path, folder_map, default_groups):
    normalized = _normalize_path(path)
    best_key = None
    best_length = -1
    for folder, groups in folder_map.items():
        # Both sides are normalized before comparing, but the *original*
        # key is what indexes back into the map - normalizing the key and
        # then looking it up raises KeyError.
        folder_norm = _normalize_path(folder).rstrip(os.sep)
        if normalized == folder_norm or normalized.startswith(folder_norm + os.sep):
            if len(folder_norm) > best_length:
                best_key, best_length = folder, len(folder_norm)
    return folder_map[best_key] if best_key is not None else default_groups


# Build the Chroma metadata filter for a user's groups. None means no
# restriction (superuser or unauthenticated CLI use); an empty group list
# denies everything (fails closed) rather than matching everything.
def build_group_filter(allowed_groups):
    if allowed_groups is None or SUPERUSER_GROUP in allowed_groups:
        return None
    if not allowed_groups:
        return {"group___none__": True}  # matches no real chunk
    conditions = [{f"group_{g}": True} for g in allowed_groups]
    return conditions[0] if len(conditions) == 1 else {"$or": conditions}


# Extensions load_file() can turn into text. Images are included only
# because OCR may be available; load_file returns nothing for them when it
# is not, and a chunkless file is skipped downstream.
LOADABLE_EXTENSIONS = frozenset({
    ".pdf", ".txt", ".md", ".docx", ".xlsx", ".pptx", ".eml", ".csv",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
})


# List eligible files under docs/ (skips hidden files, filters by extension)
def discover_files():
    if not os.path.isdir(DOCS_PATH):
        os.makedirs(DOCS_PATH, exist_ok=True)
        print("Created docs/ folder. Add your PDFs and text files there.")
        return []

    paths = []
    for root, _, files in os.walk(DOCS_PATH):
        for file in sorted(files):
            if file.startswith("."):  # .DS_Store, AppleDouble ._ files
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in LOADABLE_EXTENSIONS:
                paths.append(_normalize_path(os.path.join(root, file)))

    return sorted(paths)


# Extract a paragraph's text with hyperlink targets inlined, e.g. a run
# reading "LinkedIn" that links to https://linkedin.com/in/x becomes
# "LinkedIn (https://linkedin.com/in/x)". Plain-text extraction (docx2txt,
# python-docx's .text) only sees the anchor text - the actual URL lives in
# the document's relationship table and is otherwise lost entirely.
def _paragraph_text_with_links(paragraph, rels):
    parts = []
    for child in paragraph._p:
        if child.tag == qn("w:hyperlink"):
            text = "".join(t.text or "" for t in child.iter(qn("w:t")))
            r_id = child.get(qn("r:id"))
            url = rels[r_id].target_ref if r_id in rels else None
            parts.append(f"{text} ({url})" if url and text else text)
        elif child.tag == qn("w:r"):
            parts.append("".join(t.text or "" for t in child.iter(qn("w:t"))))
    return "".join(parts)


# Word's "Heading 1-3" styles become markdown headings so the chunker can
# split on them and label each chunk with its section.
def _heading_marker(paragraph):
    style = getattr(paragraph.style, "name", "") or ""
    match = re.fullmatch(r"Heading ([1-3])", style)
    return "#" * int(match.group(1)) + " " if match else ""


def load_docx(path):
    document = DocxDocument(path)
    rels = document.part.rels

    lines = [_heading_marker(p) + _paragraph_text_with_links(p, rels)
             for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                lines.extend(_paragraph_text_with_links(p, rels) for p in cell.paragraphs)

    text = "\n".join(line for line in lines if line.strip())
    return [Document(page_content=text, metadata={"source": path})]


# A spreadsheet's meaning lives in the relationship between a row's cells,
# so rows are flattened to "header: value" pairs rather than bare cell
# dumps. A roster row read as "Alay Parikh | Engineering | 2024-03-01" is
# nearly useless to retrieval; "Name: Alay Parikh | Team: Engineering" is
# answerable. Formulas are read as their last cached value, which is what
# a reader would see.
def load_xlsx(path, max_rows_per_sheet=None):
    from openpyxl import load_workbook

    max_rows_per_sheet = max_rows_per_sheet or XLSX_MAX_ROWS
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        blocks = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                continue
            labels = [str(c).strip() if c is not None else "" for c in header]

            lines = [f"Sheet: {sheet.title}", " | ".join(l for l in labels if l)]
            for i, row in enumerate(rows):
                if i >= max_rows_per_sheet:
                    lines.append(f"[... {sheet.title} truncated at "
                                 f"{max_rows_per_sheet} rows]")
                    break
                cells = [
                    f"{labels[j]}: {value}" if j < len(labels) and labels[j] else str(value)
                    for j, value in enumerate(row) if value is not None
                ]
                if cells:
                    lines.append(" | ".join(cells))
            if len(lines) > 2:
                blocks.append("\n".join(lines))
    finally:
        workbook.close()

    return [Document(page_content="\n\n".join(blocks), metadata={"source": path})]


# Slide text plus speaker notes, which often carry the actual explanation
# a slide only gestures at.
def load_pptx(path):
    from pptx import Presentation

    presentation = Presentation(path)
    blocks = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines = [f"Slide {number}"]
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"Notes: {notes}")
        if len(lines) > 1:
            blocks.append("\n".join(lines))

    return [Document(page_content="\n\n".join(blocks), metadata={"source": path})]


# Headers carry most of an email's searchable value (who, when, subject),
# so they are kept as text rather than dropped in favour of the body.
def load_eml(path):
    import email
    from email import policy

    with open(path, "rb") as handle:
        message = email.message_from_binary_file(handle, policy=policy.default)

    lines = [f"{field}: {message[field]}"
             for field in ("From", "To", "Cc", "Date", "Subject") if message[field]]

    body = message.get_body(preferencelist=("plain", "html"))
    if body is not None:
        text = body.get_content()
        if body.get_content_subtype() == "html":
            text = re.sub(r"<[^>]+>", " ", text)
        lines.append("")
        lines.append(re.sub(r"[ \t]+", " ", text).strip())

    attachments = [part.get_filename() for part in message.iter_attachments()
                   if part.get_filename()]
    if attachments:
        lines.append("Attachments: " + ", ".join(attachments))

    return [Document(page_content="\n".join(lines), metadata={"source": path})]


# OCR is opt-in and degrades quietly: on a host without Tesseract installed
# a scanned document is simply not text-indexed, which is the state it was
# already in. The alternative - failing the nightly run over a missing
# system binary - would be worse.
def ocr_available():
    if not OCR_ENABLED:
        return False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 - missing module or missing binary alike
        return False
    return True


def load_image_ocr(path):
    import pytesseract
    from PIL import Image

    with Image.open(path) as image:
        text = pytesseract.image_to_string(image, lang=OCR_LANGS)
    return [Document(page_content=text.strip(),
                     metadata={"source": path, "extraction": "ocr"})]


# A PDF with no extractable text is a scan. Trying OCR on every PDF would
# multiply a 50 GB index's runtime for nothing, so it is attempted only
# when the text layer comes back empty.
def load_pdf(path):
    documents = PyPDFLoader(path).load()
    if any(d.page_content.strip() for d in documents):
        return documents
    if not ocr_available():
        return documents
    return _ocr_pdf(path)


def _ocr_pdf(path):
    import pytesseract
    from pdf2image import convert_from_path

    pages = convert_from_path(path, dpi=OCR_DPI, last_page=OCR_MAX_PAGES)
    documents = []
    for number, page in enumerate(pages, start=1):
        text = pytesseract.image_to_string(page, lang=OCR_LANGS).strip()
        if text:
            documents.append(Document(
                page_content=text,
                metadata={"source": path, "page": number, "extraction": "ocr"},
            ))
    return documents


IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"})


# Load a single file's contents, using the loader for its extension
def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return load_pdf(path)
    if ext == ".docx":
        return load_docx(path)
    if ext == ".xlsx":
        return load_xlsx(path)
    if ext == ".pptx":
        return load_pptx(path)
    if ext == ".eml":
        return load_eml(path)
    if ext in IMAGE_EXTENSIONS:
        if not ocr_available():
            return []
        return load_image_ocr(path)
    return TextLoader(path, autodetect_encoding=True).load()


# Streamed rather than read whole: the corpus is a 50 GB network share and
# a single video or disk image would otherwise be pulled entirely into
# memory just to be fingerprinted.
HASH_BLOCK_SIZE = 1024 * 1024


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


# What the manifest records per file. size+mtime is the cheap check that
# decides whether the file is worth opening at all; sha256 is the
# authoritative one that decides whether it is worth re-embedding. Keeping
# both means a touched-but-identical file (a copy, a restore, a metadata
# change) costs one read instead of a re-embed of every chunk.
def file_stamp(path, stat_result=None, previous=None):
    stat_result = stat_result or os.stat(path)
    stamp = {"size": stat_result.st_size, "mtime_ns": stat_result.st_mtime_ns}

    if previous and _unchanged_on_disk(stamp, previous):
        stamp["sha256"] = previous["sha256"]
        return stamp, False

    stamp["sha256"] = file_hash(path)
    return stamp, True


def _unchanged_on_disk(stamp, previous):
    return (previous.get("size") == stamp["size"]
            and previous.get("mtime_ns") == stamp["mtime_ns"]
            and previous.get("sha256"))


# Manifests written before stamps were introduced map path -> sha256 string.
# Upgrading them in place would mean re-reading the whole corpus, so they
# are read as-is and each file is re-stamped the first time it is examined.
def _as_stamp(value):
    if isinstance(value, str):
        return {"size": None, "mtime_ns": None, "sha256": value}
    return value or {}


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return {path: _as_stamp(value) for path, value in json.load(f).items()}
    return {}


def save_manifest(manifest):
    os.makedirs(PERSIST_PATH, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


# Split documents into chunks - heading-aware where the document has
# headings; see pipeline/chunking.py.
def split_documents(documents):
    return chunking.split_documents(documents)


def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


# The keyword index lives beside the vector store and is written in the
# same pass. It is optional so that a caller passing a stub vector store
# (tests, notebooks) does not need one; retrieval then falls back to the
# in-memory BM25 path.
#
# shared_across_threads is for the retriever: the web app caches the chain
# for the life of the process and Streamlit runs each rerun on whichever
# pool thread is free, so the connection opened on the first question's
# thread is read from others. Safe because the retriever only reads and
# sqlite3 is built in serialized mode (checked, as in indexer/crawl.py).
def _keyword_index(shared_across_threads=False):
    if shared_across_threads and sqlite3.threadsafety < 3:
        log_event({"event": "keyword_index_unavailable",
                   "error": "sqlite3 not in serialized mode"})
        return None
    try:
        # PERSIST_PATH, not the env var, so the keyword index follows the
        # vector store even when a caller has overridden it in-process.
        return keyword.connect(persist_path=PERSIST_PATH,
                               shared_across_threads=shared_across_threads)
    except Exception as e:  # noqa: BLE001 - a missing keyword index is degraded, not fatal
        log_event({"event": "keyword_index_unavailable", "error": str(e)})
        return None


# Re-embed only files that are new or whose content changed since the last
# run, and drop chunks for files that were removed. Unchanged files are
# never re-read or re-embedded.
def sync_vectorstore(store, paths=None):
    current_files = (discover_files() if paths is None
                     else sorted(_normalize_path(p) for p in paths))

    manifest = load_manifest()
    current_stamps = {}
    reads = 0
    for path in current_files:
        try:
            stamp, was_read = file_stamp(path, previous=manifest.get(path))
        except OSError as e:
            # One unreadable file must not abort a nightly run over a share
            # that is still being written to.
            log_event({"event": "stamp_error", "source": path, "error": str(e)})
            continue
        stamp["chunker"] = chunking.CHUNKER_VERSION
        current_stamps[path] = stamp
        reads += was_read

    # A chunker change re-embeds files whose content did not change: their
    # stored chunks were cut by the old rules.
    changed_or_new = [
        p for p, stamp in current_stamps.items()
        if manifest.get(p, {}).get("sha256") != stamp["sha256"]
        or manifest.get(p, {}).get("chunker") != chunking.CHUNKER_VERSION
    ]
    removed = [p for p in manifest if p not in current_stamps]

    if not changed_or_new and not removed:
        print(f"Index up to date ({store._collection.count()} chunks, "
              f"{reads} file(s) re-read).")
        save_manifest(current_stamps)  # refresh mtimes so the next run reads none
        return

    keyword_index = _keyword_index()

    for path in removed + changed_or_new:
        store.delete(where={"source": path})
        if keyword_index is not None:
            keyword.delete_source(keyword_index, path)

    folder_map, default_groups = load_permissions()

    added_chunks = 0
    for path in changed_or_new:
        try:
            documents = load_file(path)
        except Exception as e:  # noqa: BLE001 - one bad file must not end the run
            ext = os.path.splitext(path)[1].lower()
            log_event({"event": "loader_error", "source": path,
                       "guardrail": f"loader_error:{ext}", "error": str(e)})
            current_stamps.pop(path, None)  # retry it on the next run
            continue
        chunks = split_documents(documents)
        groups = groups_for_path(path, folder_map, default_groups)
        for chunk in chunks:
            for group in groups:
                chunk.metadata[f"group_{group}"] = True
        if chunks:
            ids = store.add_documents(chunks)
            if keyword_index is not None:
                if ids:
                    keyword.add_chunks(keyword_index, chunks, ids)
                else:
                    # Without ids the keyword rows could not be deleted when
                    # the file changes, so they are not written at all: a
                    # missing keyword row degrades recall, a stale one
                    # serves deleted content.
                    log_event({"event": "keyword_index_skipped", "source": path,
                               "reason": "vector store returned no ids"})
        added_chunks += len(chunks)

    save_manifest(current_stamps)

    print(f"Synced index: {len(changed_or_new)} new/updated file(s) "
          f"({added_chunks} chunks), {len(removed)} removed file(s), "
          f"{reads} file(s) re-read. "
          f"Total: {store._collection.count()} chunks.")


# Open the persisted vector store and bring it up to date with docs/
def get_vectorstore(reindex=False):
    embeddings = get_embeddings()

    if reindex and os.path.isdir(PERSIST_PATH):
        import shutil
        shutil.rmtree(PERSIST_PATH)

    store = Chroma(
        embedding_function=embeddings,
        persist_directory=PERSIST_PATH,
        collection_name="docs",
    )

    sync_vectorstore(store)

    if store._collection.count() == 0:
        return None
    return store


# BM25's default tokenizer just splits on whitespace, so a URL like
# "https://www.linkedin.com/in/x" is one opaque token that never matches a
# query for "linkedin" - every doc scores 0 and results become arbitrary.
# Splitting on non-alphanumeric characters breaks URLs/emails into real,
# matchable terms (linkedin, com, gmail, ...).
def _tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


# Scale retrieval breadth with corpus size, clamped to a sane range. Each
# retriever gets k, so the ensemble returns up to 2k chunks before dedup.
def compute_k(corpus_size):
    if RETRIEVAL_K_OVERRIDE:
        return max(1, int(RETRIEVAL_K_OVERRIDE))
    scaled = corpus_size // RETRIEVAL_K_PER_CHUNKS
    return max(RETRIEVAL_K_MIN, min(RETRIEVAL_K_MAX, scaled))


# Chunk count visible under a group filter, used to size retrieval. Kept
# separate from build_retriever so build_chain can compute the unfiltered
# context ceiling without building a second retriever.
def _corpus_size(vectorstore, allowed_groups=None):
    where_filter = build_group_filter(allowed_groups)
    get_kwargs = {"include": []}
    if where_filter:
        get_kwargs["where"] = where_filter
    return len(vectorstore.get(**get_kwargs).get("ids", []))


# Combine vector similarity search with BM25 keyword search, both scoped to
# the given groups (None = unrestricted). Vector search alone misses short,
# dense chunks (headers, contact lines, links) that get outscored by
# longer, unrelated chunks; BM25 catches literal terms (names, emails,
# "linkedin"/"github") that vector search keeps losing.
def build_retriever(vectorstore, allowed_groups=None, over_fetch=1):
    where_filter = build_group_filter(allowed_groups)
    keyword_index = _keyword_index(shared_across_threads=True)
    use_keyword_index = keyword_index is not None and keyword.count(keyword_index) > 0

    # Corpus size only. Fetching documents and metadata here was what made
    # building a retriever cost a full corpus load; with the keyword index
    # on disk, nothing needs the chunk text in memory.
    if use_keyword_index:
        corpus_size = _corpus_size(vectorstore, allowed_groups)
        all_chunks = None
    else:
        get_kwargs = {"include": ["documents", "metadatas"]}
        if where_filter:
            get_kwargs["where"] = where_filter
        raw = vectorstore.get(**get_kwargs)
        all_chunks = [
            Document(page_content=doc, metadata=meta)
            for doc, meta in zip(raw["documents"], raw["metadatas"])
        ]
        corpus_size = len(all_chunks)

    k = compute_k(corpus_size) * max(1, int(over_fetch))

    search_kwargs = {"k": k}
    if where_filter:
        search_kwargs["filter"] = where_filter
    vector_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)

    if corpus_size == 0:
        return vector_retriever  # same filter applied, so this also yields nothing

    if use_keyword_index:
        # SUPERUSER_GROUP is expressed as "no filter", matching
        # build_group_filter(), so the two stores agree on who sees what.
        groups = None if where_filter is None else list(allowed_groups)
        keyword_retriever = keyword.FtsRetriever(
            connection=keyword_index, k=k, allowed_groups=groups,
        )
    else:
        keyword_retriever = BM25Retriever.from_documents(
            all_chunks, preprocess_func=_tokenize)
        keyword_retriever.k = k

    return EnsembleRetriever(retrievers=[vector_retriever, keyword_retriever],
                             weights=[0.5, 0.5])


class AnswerWithSources(BaseModel):
    answer: str = Field(description="The answer to the user's question, based only on the retrieved context.")
    sources_used: list[str] = Field(
        default_factory=list,
        description="Exact source paths, as labeled 'Source: <path>' in the "
                     "context, that were actually relied on to answer. Empty "
                     "list if none were used (e.g. the answer is 'I don't know').",
    )


def _format_context(docs):
    return "\n\n".join(f"Source: {d.metadata.get('source', '?')}\n{d.page_content}" for d in docs)


class AnswerChain:
    """Wraps a structured-output LLM call so sources_used is a guaranteed
    schema field rather than a trailing line the model has to remember to
    add. Tested in practice: a plain instruction to append a "Sources
    used: ..." line was reliably dropped on longer answers (0 of 4 real
    answers in a live session included it) - structured output complied
    every time in repeated testing, since it's enforced by the API's
    response schema rather than hoped for from a text instruction."""

    def __init__(self, structured_llm, prompt):
        self.structured_llm = structured_llm
        self.prompt = prompt

    def _messages(self, inputs):
        return self.prompt.format_messages(
            input=inputs["input"],
            context=_format_context(inputs["context"]),
            chat_history=inputs["chat_history"],
        )

    def invoke(self, inputs, config=None):
        return self.structured_llm.invoke(self._messages(inputs), config=config)

    # Structured output streams as a growing AnswerWithSources: the answer
    # text fills in token by token and sources_used is complete at the end,
    # so streaming does not cost the schema guarantee above.
    def stream(self, inputs, config=None):
        return self.structured_llm.stream(self._messages(inputs), config=config)


class ExtractiveAnswerChain:
    """Offline answerer: no LLM, so the "answer" is the top reranked
    passages, quoted with their sources. Same invoke() contract as
    AnswerChain, so everything around it - access checks, source
    validation, redaction, logging, caching - applies unchanged."""

    def __init__(self, min_score=None, max_passages=OFFLINE_MAX_PASSAGES):
        self.min_score = OFFLINE_MIN_SCORE if min_score is None else min_score
        self.max_passages = max_passages

    def invoke(self, inputs, config=None):
        docs = [d for d in inputs["context"]
                if d.metadata.get("rerank_score", self.min_score) >= self.min_score]
        docs = docs[: self.max_passages]
        if not docs:
            return AnswerWithSources(answer=NO_CONTEXT_ANSWER, sources_used=[])
        blocks = []
        for d in docs:
            text = d.page_content.strip()
            if len(text) > OFFLINE_PASSAGE_CHARS:
                text = text[:OFFLINE_PASSAGE_CHARS].rsplit(" ", 1)[0] + " …"
            quoted = "\n".join("> " + line for line in text.splitlines() if line.strip())
            blocks.append(f"{quoted}\n\n— *{os.path.basename(d.metadata.get('source', '?'))}*")
        return AnswerWithSources(
            answer="Most relevant passages:\n\n" + "\n\n".join(blocks),
            sources_used=sorted({d.metadata.get("source") for d in docs}),
        )


class HistoryAwareRetriever:
    """Rewrites a follow-up into a standalone question, then retrieves.
    Done by hand rather than with create_history_aware_retriever so the
    standalone question is available afterwards: the reranker and grader
    need it, and scoring chunks against "what about her?" is meaningless."""

    def __init__(self, llm, retriever, prompt):
        self.retriever = retriever
        self.rewrite_chain = None if llm is None else prompt | llm | StrOutputParser()

    def standalone(self, question, chat_history, config=None):
        if not chat_history or self.rewrite_chain is None:
            return question  # no LLM call on a first turn, or in offline mode
        rewritten = tracing.invoke(
            self.rewrite_chain, {"input": question, "chat_history": chat_history}, config)
        return rewritten.strip() or question

    def retrieve(self, query, config=None):
        return tracing.invoke(self.retriever, query, config)

    def invoke(self, inputs, config=None):
        query = self.standalone(inputs["input"], inputs["chat_history"], config)
        return self.retrieve(query, config)


class RagChain:
    """Retrieval + generation, kept as separate steps (rather than the
    bundled create_retrieval_chain) so answer_question() can inspect
    retrieved context and skip the LLM call entirely when it's empty.

    reranker, grader, rewriter and cache are optional stages; a chain built
    without them behaves exactly as retrieve-then-answer."""

    def __init__(self, history_aware_retriever, answer_chain, max_context=None,
                 reranker=None, grader=None, rewriter=None, cache=None, model=MODEL):
        self.history_aware_retriever = history_aware_retriever
        self.answer_chain = answer_chain
        # Cap on chunks passed to the model after access filtering. Set when
        # retrieval over-fetches for the ACL check, so an over-fetch of 3x
        # does not silently triple prompt size (and cost) for users who can
        # in fact read everything.
        self.max_context = max_context
        self.reranker = reranker
        self.grader = grader
        self.rewriter = rewriter
        self.cache = cache
        self.model = model


# Build the chat chain: rewrite the question using history, then answer from context.
# allowed_groups scopes retrieval to what that user is permitted to see;
# None means unrestricted (CLI/local admin use). use_cache=False is for the
# eval, where a cached answer would hide a regression.
def build_chain(vectorstore, allowed_groups=None, over_fetch=1, use_cache=True):
    over_fetch = max(1, int(over_fetch))
    retriever = build_retriever(vectorstore, allowed_groups, over_fetch=over_fetch)
    # The ensemble merges two retrievers of k each, so an unfiltered chain
    # can legitimately surface up to 2k distinct chunks. Keep that ceiling
    # and strip only the extra breadth the over-fetch added.
    max_context = None
    if over_fetch > 1:
        max_context = 2 * compute_k(_corpus_size(vectorstore, allowed_groups))

    online = llm_enabled()
    # Offline, no client is constructed at all - not merely unused - so
    # there is no code path that can reach the API.
    llm = ChatAnthropic(model=MODEL, max_tokens=16000) if online else None
    history_aware_retriever = HistoryAwareRetriever(llm, retriever, CONTEXTUALIZE_PROMPT)
    if online:
        answer_chain = AnswerChain(llm.with_structured_output(AnswerWithSources), ANSWER_PROMPT)
    else:
        answer_chain = ExtractiveAnswerChain()

    grader = rewriter = None
    if online and grading.GRADING_ENABLED:
        small_llm = ChatAnthropic(model=grading.GRADER_MODEL, max_tokens=1024)
        grader = grading.RelevanceGrader(small_llm)
        rewriter = grading.QueryRewriter(small_llm)

    cache = None
    if use_cache and answer_cache.CACHE_ENABLED:
        cache = answer_cache.AnswerCache(os.path.join(PERSIST_PATH, "answer_cache.sqlite"))

    return RagChain(history_aware_retriever, answer_chain, max_context=max_context,
                    reranker=rerank.get_reranker(), grader=grader, rewriter=rewriter,
                    cache=cache, model=MODEL if online else EXTRACTIVE_MODEL)


# Runs the full guardrail pipeline around one question: length cap, cache,
# retrieval, an empty-context short-circuit (skips the LLM call entirely
# rather than risk a hallucinated answer with nothing to ground it), typed
# error handling on the actual Claude call, secret redaction on the output,
# and structured logging of every request. This is the single call site
# both the CLI loop and the web UI use, so every guardrail applies in both.
#
# on_token, when given, receives the redacted answer-so-far as it streams.
def answer_question(rag_chain, question, chat_history, log_context=None,
                    access_check=None, user=None, on_token=None):
    start = time.time()
    log_context = log_context or {}
    acl_stats = {"num_retrieved": 0, "num_dropped_by_acl": 0}
    timer = tracing.StepTimer()
    trace = {"retried": False, "cache": "off"}

    def finish(answer, context, guardrail, sources_used=(), usage=None):
        # No usage means no LLM call happened (a guardrail short-circuit),
        # which is genuinely free - hence 0.0, not None. None is reserved
        # for "tokens were spent but the model isn't in PRICING".
        usage = usage if usage is not None else {
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "models_called": [],
        }
        log_event({
            "question_len": len(question),
            "num_sources": len(context),
            "num_sources_used": len(sources_used),
            # Paths only, never chunk text - this file is not access-controlled
            # and the corpus can hold medical records and resumes.
            "sources_retrieved": sorted({d.metadata.get("source", "?") for d in context}),
            "sources_used": sorted(sources_used),
            "guardrail": guardrail,
            # num_sources is what the model saw; num_retrieved is what
            # retrieval produced before the per-file NAS access check.
            # A persistent gap between them means the index is tagged
            # more loosely than the NAS actually permits.
            **acl_stats,
            **trace,
            **timer.steps,
            "latency_ms": round((time.time() - start) * 1000),
            **usage,
            **log_context,
        })
        return {"answer": answer, "context": context, "guardrail": guardrail,
                "sources_used": list(sources_used)}

    if len(question) > MAX_QUESTION_LENGTH:
        return finish(
            f"Question is too long ({len(question)} characters, max {MAX_QUESTION_LENGTH}).",
            [], "input_too_long",
        )

    cache = getattr(rag_chain, "cache", None)
    cache_key = None
    if cache is not None and not chat_history:
        cache_key = cache.key(question, user, answer_cache.index_version(MANIFEST_PATH),
                              getattr(rag_chain, "model", MODEL))
        with timer.step("cache"):
            entry = cache.get(cache_key)
        if entry is not None and answer_cache.still_permitted(entry, access_check):
            trace["cache"] = "hit"
            if on_token is not None:
                on_token(entry["answer"])
            return finish(entry["answer"], [], None, entry["sources_used"])
        trace["cache"] = "miss"

    config = tracing.run_config(user=user or log_context.get("user"),
                                tags=[log_context.get("mode", "unknown")])

    # _generate returns the same tuple finish() takes rather than logging
    # itself, so every exit path inside the block - including the error
    # paths - has its token usage counted before the event is written.
    # The callback is an inheritable context var, so it captures the
    # query-rewrite and grading calls too, not just the answer call.
    with get_usage_metadata_callback() as usage_cb:
        answer, context, guardrail, sources_used = _generate(
            rag_chain, question, chat_history, access_check, acl_stats,
            timer=timer, trace=trace, config=config, on_token=on_token,
        )

    if cache_key is not None and guardrail in (None, "secret_redacted"):
        cache.put(cache_key, {
            "answer": answer, "sources_used": list(sources_used),
            "context_sources": sorted({d.metadata.get("source") for d in context
                                       if d.metadata.get("source")}),
        })

    return finish(answer, context, guardrail, sources_used,
                  summarize_usage(usage_cb.usage_metadata))


_API_ERRORS = (ModelAuthenticationError, ModelRateLimitError, ModelTimeoutError,
               ModelConnectionError, ModelAPIError)


# Retrieval + generation with typed error handling. Several steps call the
# LLM (query rewriting, grading, answer generation), so a rate-limit/auth/
# timeout failure can happen during any of them.
def _generate(rag_chain, question, chat_history, access_check=None, acl_stats=None,
              timer=None, trace=None, config=None, on_token=None):
    timer = timer or tracing.StepTimer()
    trace = trace if trace is not None else {}
    retriever = rag_chain.history_aware_retriever

    try:
        with timer.step("retrieve"):
            if hasattr(retriever, "standalone"):
                query = retriever.standalone(question, chat_history, config)
                context = retriever.retrieve(query, config)
            else:
                query = question
                context = tracing.invoke(
                    retriever, {"input": question, "chat_history": chat_history}, config)
    except _API_ERRORS as e:
        message, tag = _api_error_message(e)
        return message, [], tag, []

    if not context:
        return NO_CONTEXT_ANSWER, [], "no_context", []

    context = _refine(rag_chain, query, context, access_check, acl_stats, timer, config)
    if context is None:
        return NO_ACCESS_ANSWER, [], "acl_empty", []

    # Corrective retrieval: nothing relevant survived grading, so try once
    # more with a rewritten query before telling the user there is nothing.
    if not context and getattr(rag_chain, "rewriter", None) is not None \
            and hasattr(retriever, "retrieve"):
        trace["retried"] = True
        try:
            with timer.step("rewrite"):
                query = rag_chain.rewriter.rewrite(query, config)
        except _API_ERRORS:
            query = None
        if query:
            with timer.step("retrieve"):
                context = retriever.retrieve(query, config)
            context = _refine(rag_chain, query, context, access_check, acl_stats,
                              timer, config) or []
    if not context:
        return NO_CONTEXT_ANSWER, [], "no_relevant_context", []

    inputs = {"input": question, "context": context, "chat_history": chat_history}
    try:
        with timer.step("generate"):
            if on_token is not None and hasattr(rag_chain.answer_chain, "stream"):
                result = _stream_answer(rag_chain.answer_chain, inputs, config, on_token)
            else:
                result = tracing.invoke(rag_chain.answer_chain, inputs, config)
    except _API_ERRORS as e:
        message, tag = _api_error_message(e)
        return message, context, tag, []

    # Validate against what was actually retrieved - a path the model
    # names that wasn't in the retrieved context is dropped rather than
    # trusted, since retrieval returns more chunks than end up relevant.
    retrieved = {d.metadata.get("source") for d in context}
    sources_used = [s for s in result.sources_used if s in retrieved]

    answer, was_redacted = redact_secrets(result.answer)
    return answer, context, "secret_redacted" if was_redacted else None, sources_used


# Post-retrieval stages, in order: access check, cap, rerank, grade.
# Returns None when the access check removed everything (a distinct
# outcome for the log), otherwise the refined - possibly empty - list.
def _refine(rag_chain, query, context, access_check, acl_stats, timer, config):
    # Authoritative authorization, between retrieval and the LLM call. The
    # index's group tags are a stale snapshot; this asks the NAS itself,
    # as this user, right now. It must run before any chunk text reaches
    # Claude - grader included - so it lives here rather than in the UI.
    if access_check is not None:
        with timer.step("acl"):
            context = _filter_by_access(context, access_check, acl_stats)
        if not context:
            return None

    reranker = getattr(rag_chain, "reranker", None)
    if reranker is not None and context:
        with timer.step("rerank"):
            context = reranker.rerank(query, context)

    max_context = getattr(rag_chain, "max_context", None)
    if access_check is not None and max_context:
        context = context[:max_context]

    grader = getattr(rag_chain, "grader", None)
    if grader is not None and context:
        try:
            with timer.step("grade"):
                context = grader.grade(query, context, config)
        except _API_ERRORS as e:
            # Fail open: grading trims cost and noise, it does not authorize.
            log_event({"event": "grade_error", "error": str(e)})
    return context


# Redaction runs on the whole answer-so-far each time, and the newest
# STREAM_HOLDBACK characters are withheld until more text arrives: a secret
# split across two stream chunks would otherwise be on screen before the
# pattern that catches it has seen all of it. Longer than any pattern in
# _SECRET_PATTERNS / _AADHAAR_CONTEXT can match.
STREAM_HOLDBACK = 80


def _stream_answer(answer_chain, inputs, config, on_token):
    last = None
    shown = 0
    for partial in answer_chain.stream(inputs, config=config):
        last = partial
        text = getattr(partial, "answer", None) or ""
        redacted, _ = redact_secrets(text)
        visible = redacted[:max(0, len(redacted) - STREAM_HOLDBACK)]
        if len(visible) > shown:
            on_token(visible)
            shown = len(visible)
    if last is None:
        raise ModelAPIError("empty streamed response")
    if not isinstance(last, AnswerWithSources):
        last = AnswerWithSources.model_validate(last)
    return last


# Drop retrieved chunks whose source file this user cannot open on the NAS.
# Fails closed in every direction: a check that raises, a chunk with no
# source path, and a chunk whose source is denied are all removed.
def _filter_by_access(context, access_check, acl_stats=None):
    allowed = []
    for doc in context:
        source = doc.metadata.get("source")
        if not source:
            continue
        try:
            permitted = access_check(source)
        except Exception:  # noqa: BLE001 - an unavailable NAS must not open access
            permitted = False
        if permitted:
            allowed.append(doc)

    if acl_stats is not None:
        acl_stats["num_retrieved"] = len(context)
        acl_stats["num_dropped_by_acl"] = len(context) - len(allowed)
    return allowed


def _api_error_message(e):
    if isinstance(e, ModelAuthenticationError):
        return "Assistant is misconfigured (invalid API key). Contact an admin.", f"api_error:auth:{e}"
    if isinstance(e, ModelRateLimitError):
        return "Assistant is rate-limited right now - please try again in a moment.", f"api_error:rate_limit:{e}"
    if isinstance(e, ModelTimeoutError):
        return "The request timed out - please try again.", f"api_error:timeout:{e}"
    if isinstance(e, ModelConnectionError):
        return "Couldn't reach the Claude API - check your network and try again.", f"api_error:connection:{e}"
    return "The assistant hit an error answering that - please try again.", f"api_error:other:{e}"


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="RAG assistant over ./docs")
    parser.add_argument("--reindex", action="store_true",
                        help="delete and rebuild the vector store (--cli mode only; "
                             "the web UI has a Sync button instead)")
    parser.add_argument("--cli", action="store_true",
                        help="use the terminal chat instead of the web UI")
    args = parser.parse_args()

    if not llm_enabled():
        print("Offline mode: no Claude API calls; answers are the best-matching "
              "passages. Set ANTHROPIC_API_KEY (and RAG_LLM=auto) for generated answers.")

    if not args.cli:
        import subprocess
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", app_path])

    vectorstore = get_vectorstore(reindex=args.reindex)
    if vectorstore is None:
        print("No documents found. Add files to the docs/ folder and try again.")
        return 1

    chain = build_chain(vectorstore)
    chat_history = []

    print("\nRAG Assistant ready. Type your questions (type 'quit' to exit):\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ["quit", "exit", "q"]:
            break

        response = answer_question(chain, question, chat_history, log_context={"mode": "cli"})
        print(f"\nAssistant: {response['answer']}\n")

        if response["sources_used"]:
            print(f"Sources: {', '.join(sorted(response['sources_used']))}\n")

        chat_history.extend([
            HumanMessage(content=question),
            AIMessage(content=response["answer"]),
        ])
        chat_history[:] = chat_history[-HISTORY_TURNS * 2:]

    return 0


if __name__ == "__main__":
    sys.exit(main())
