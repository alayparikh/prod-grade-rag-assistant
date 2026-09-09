"""Authorization tests: path translation, the per-file access filter, and
the guardrail that keeps denied content away from the LLM.

A bug in this file's subject matter is a silent data leak rather than a
visible error, so the negative cases (denial, failure, absence) matter
more than the positive ones and are tested first.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag  # noqa: E402
from auth import smb  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def doc(source, text="content"):
    return Document(page_content=text, metadata={"source": source})


# The event logger is a process-wide singleton guarded by both a module
# global and logging's own handler list, so re-pointing LOG_PATH is not
# enough on its own - the cached logger keeps writing to whichever file the
# first test in the process opened.
@pytest.fixture
def event_log(tmp_path, monkeypatch):
    import logging

    log_path = tmp_path / "events.jsonl"
    logger = logging.getLogger("rag.events")
    saved = list(logger.handlers)
    logger.handlers.clear()
    monkeypatch.setattr(rag, "LOG_PATH", str(log_path))
    monkeypatch.setattr(rag, "_event_logger", None)
    try:
        yield log_path
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = saved
        rag._event_logger = None


class TestToSharePath:
    MOUNT = "/mnt/nas"

    def test_translates_to_backslash_relative_path(self):
        assert smb.to_share_path("/mnt/nas/HR/roster.xlsx", self.MOUNT) == "HR\\roster.xlsx"

    def test_file_at_mount_root(self):
        assert smb.to_share_path("/mnt/nas/readme.txt", self.MOUNT) == "readme.txt"

    def test_rejects_path_outside_mount(self):
        # Fails closed: a path the indexer should never have produced must
        # not be silently checked against some other file on the share.
        with pytest.raises(ValueError):
            smb.to_share_path("/etc/passwd", self.MOUNT)

    def test_rejects_traversal_escaping_the_mount(self):
        with pytest.raises(ValueError):
            smb.to_share_path("/mnt/nas/../etc/passwd", self.MOUNT)

    def test_rejects_sibling_directory_with_shared_prefix(self):
        # "/mnt/nas-backup" starts with "/mnt/nas" as a string but is a
        # different directory - a prefix check without the separator would
        # wrongly accept it.
        with pytest.raises(ValueError):
            smb.to_share_path("/mnt/nas-backup/secret.txt", self.MOUNT)


class TestNasLinks:
    def test_renders_unc_and_smb_forms(self):
        links = smb.nas_links("/mnt/nas/HR/roster.xlsx", host="nas.local",
                              share="shared", mount="/mnt/nas")
        assert links["unc"] == r"\\nas.local\shared\HR\roster.xlsx"
        assert links["smb"] == "smb://nas.local/shared/HR/roster.xlsx"


class TestFilterByAccess:
    def test_drops_denied_sources(self):
        context = [doc("/mnt/nas/HR/a.txt"), doc("/mnt/nas/Eng/b.txt")]
        allowed = rag._filter_by_access(context, lambda p: "/HR/" in p)
        assert [d.metadata["source"] for d in allowed] == ["/mnt/nas/HR/a.txt"]

    def test_check_that_raises_denies_rather_than_allows(self):
        # An unreachable NAS must not become an open door.
        def exploding_check(path):
            raise OSError("NAS unreachable")

        assert rag._filter_by_access([doc("/mnt/nas/a.txt")], exploding_check) == []

    def test_chunk_without_source_is_dropped(self):
        orphan = Document(page_content="x", metadata={})
        assert rag._filter_by_access([orphan], lambda p: True) == []

    def test_records_counts(self):
        stats = {}
        context = [doc("/mnt/nas/a.txt"), doc("/mnt/nas/b.txt"), doc("/mnt/nas/c.txt")]
        rag._filter_by_access(context, lambda p: p.endswith("a.txt"), stats)
        assert stats == {"num_retrieved": 3, "num_dropped_by_acl": 2}


class _FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, _inputs):
        return list(self.docs)


class _RecordingAnswerChain:
    """Stands in for the structured-output LLM call so the test can assert
    on exactly which chunks would have been sent to Claude."""

    def __init__(self):
        self.seen_context = None

    def invoke(self, inputs):
        self.seen_context = inputs["context"]

        class _Result:
            answer = "an answer"
            sources_used = [d.metadata["source"] for d in inputs["context"]]

        return _Result()


def _chain(docs, max_context=None):
    answer_chain = _RecordingAnswerChain()
    chain = rag.RagChain(_FakeRetriever(docs), answer_chain, max_context=max_context)
    return chain, answer_chain


class TestAnswerQuestionAccessCheck:
    def test_denied_chunks_never_reach_the_model(self, event_log):
        docs = [doc(f"/mnt/nas/HR/{i}.txt") for i in range(2)]
        docs += [doc(f"/mnt/nas/Eng/{i}.txt") for i in range(4)]
        chain, answer_chain = _chain(docs)

        response = rag.answer_question(chain, "q", [], access_check=lambda p: "/HR/" in p)

        sent = [d.metadata["source"] for d in answer_chain.seen_context]
        assert sent == ["/mnt/nas/HR/0.txt", "/mnt/nas/HR/1.txt"]
        assert all("/Eng/" not in s for s in response["sources_used"])

    def test_all_denied_short_circuits_without_calling_the_model(self, event_log):
        chain, answer_chain = _chain([doc("/mnt/nas/Eng/a.txt")])
        response = rag.answer_question(chain, "q", [], access_check=lambda p: False)

        assert answer_chain.seen_context is None  # no LLM call at all
        assert response["guardrail"] == "acl_empty"
        assert response["context"] == []

    def test_denial_is_indistinguishable_from_absence(self, event_log):
        # A user must not learn that a document exists by the wording of
        # the refusal.
        denied, _ = _chain([doc("/mnt/nas/Eng/a.txt")])
        empty, _ = _chain([])

        denied_answer = rag.answer_question(denied, "q", [], access_check=lambda p: False)
        empty_answer = rag.answer_question(empty, "q", [], access_check=lambda p: True)
        assert denied_answer["answer"] == empty_answer["answer"]

    def test_over_fetch_extra_is_truncated_before_generation(self, event_log):
        docs = [doc(f"/mnt/nas/HR/{i}.txt") for i in range(24)]
        chain, answer_chain = _chain(docs, max_context=8)
        rag.answer_question(chain, "q", [], access_check=lambda p: True)
        assert len(answer_chain.seen_context) == 8

    def test_no_access_check_leaves_behaviour_unchanged(self, event_log):
        docs = [doc("/mnt/nas/Eng/a.txt")]
        chain, answer_chain = _chain(docs)
        rag.answer_question(chain, "q", [])
        assert len(answer_chain.seen_context) == 1


class TestAclLogging:
    def test_file_handler_is_attached_even_when_the_host_added_one(self, event_log):
        # Regression: the setup guard used to be "if not logger.handlers",
        # so any host-installed handler (pytest capture, an app server)
        # suppressed the file handler and events went nowhere.
        import logging

        logging.getLogger("rag.events").addHandler(logging.NullHandler())
        rag.log_event({"probe": 1})
        assert event_log.exists()

    def test_logs_drop_count_and_never_the_chunk_text(self, event_log):
        import json

        log_path = event_log
        docs = [doc("/mnt/nas/HR/a.txt", "secret salary data"),
                doc("/mnt/nas/Eng/b.txt", "secret design data")]
        chain, _ = _chain(docs)
        rag.answer_question(chain, "q", [], access_check=lambda p: "/HR/" in p)

        event = json.loads(log_path.read_text().strip().splitlines()[-1])
        assert event["num_dropped_by_acl"] == 1
        assert event["num_retrieved"] == 2
        assert event["num_sources"] == 1
        assert "secret" not in log_path.read_text()


class TestAccessChecker:
    class _StubSession:
        def __init__(self, allowed):
            self.allowed = allowed
            self.calls = 0
            self.touched = 0

        def touch(self):
            self.touched += 1

        def can_read(self, path):
            self.calls += 1
            return path in self.allowed

    def test_memoizes_repeat_paths_within_one_question(self):
        session = self._StubSession({"/mnt/nas/a.txt"})
        checker = smb.AccessChecker(session)
        for _ in range(5):
            assert checker("/mnt/nas/a.txt") is True
        assert session.calls == 1

    def test_counts_denials(self):
        session = self._StubSession({"/mnt/nas/a.txt"})
        checker = smb.AccessChecker(session)
        checker("/mnt/nas/a.txt")
        checker("/mnt/nas/b.txt")
        assert (checker.checked, checker.denied) == (2, 1)


class TestSessionExpiry:
    def test_idle_session_expires(self, monkeypatch):
        monkeypatch.setattr(smb, "SESSION_IDLE_SECONDS", 60)
        session = smb.NasSession("alice", None, None, None)
        session.last_used = 1000.0
        assert session.expired(now=1030.0) is False
        assert session.expired(now=1100.0) is True

    def test_touch_extends_the_session(self, monkeypatch):
        monkeypatch.setattr(smb, "SESSION_IDLE_SECONDS", 60)
        session = smb.NasSession("alice", None, None, None)
        session.last_used = 1000.0
        session.touch()
        assert session.expired() is False


class TestLoginInputValidation:
    def test_blank_credentials_never_reach_the_nas(self, monkeypatch):
        def fail(*a, **kw):
            raise AssertionError("must not attempt a connection")

        monkeypatch.setattr(smb, "NAS_HOST", "nas.local")
        monkeypatch.setitem(sys.modules, "smbprotocol.connection", type(sys)("x"))
        sys.modules["smbprotocol.connection"].Connection = fail
        assert smb.login("", "", host="nas.local") is None
        assert smb.login("alice", "", host="nas.local") is None
