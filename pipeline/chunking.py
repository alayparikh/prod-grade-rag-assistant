"""Structure-aware chunking.

Fixed-size windows cut straight through headings, runbook steps and
table rows, and a chunk from the middle of a section loses the heading
that said what it was about. Documents with markdown headings (.md files,
and .docx files whose Heading styles the loader turns into markdown) are
split on those headings first, and every chunk is prefixed with its
section path so "Step 3: restart the service" still says which runbook
and which section it came from. Everything else falls back to the
recursive character splitter.

Bump CHUNKER_VERSION whenever chunk boundaries or content change: the
indexer re-embeds every file whose manifest entry carries an older one.
"""
import re

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

CHUNKER_VERSION = 2
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_HEADING_LINE = re.compile(r"^#{1,3} \S", re.MULTILINE)


def has_headings(text):
    return bool(_HEADING_LINE.search(text))


def section_path(metadata):
    return " > ".join(metadata[k] for k in ("h1", "h2", "h3") if metadata.get(k))


def split_documents(documents):
    window = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    headings = MarkdownHeaderTextSplitter(_HEADERS, strip_headers=True)

    chunks = []
    for doc in documents:
        if not has_headings(doc.page_content):
            chunks.extend(window.split_documents([doc]))
            continue
        for section in headings.split_text(doc.page_content):
            path = section_path(section.metadata)
            prefix = f"Section: {path}\n" if path else ""
            for piece in window.split_text(section.page_content):
                metadata = dict(doc.metadata)
                if path:
                    metadata["section"] = path
                chunks.append(type(doc)(page_content=prefix + piece, metadata=metadata))
    return chunks
