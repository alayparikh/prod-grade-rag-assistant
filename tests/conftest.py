"""Test isolation.

Without this, anything that resolves a default path at call time - the
keyword index, the manifest, the event log - writes into the developer's
real ./chroma_db and ./logs while the suite runs. That polluted index then
changes the behaviour of later tests, which is exactly how the retriever
test started failing for reasons unrelated to the retriever.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    import rag

    # Deliberately not "index": several tests create their own
    # tmp_path/"index" and would collide with it.
    persist = tmp_path / "_default_index"
    persist.mkdir()
    monkeypatch.setenv("RAG_PERSIST_PATH", str(persist))
    monkeypatch.delenv("RAG_CHUNK_DB", raising=False)
    monkeypatch.setattr(rag, "PERSIST_PATH", str(persist))
    monkeypatch.setattr(rag, "MANIFEST_PATH", str(persist / "manifest.json"))
    monkeypatch.setattr(rag, "LOG_PATH", str(tmp_path / "_default_events.jsonl"))
    monkeypatch.setattr(rag, "_event_logger", None)
    yield
    rag._event_logger = None
