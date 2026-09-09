"""Router tests.

The router is only worth having if it is right about the cases that go
wrong without it: a "how many" question answered from the top-k fragments
of a roster produces a confident wrong number, and a "where is" question
answered by RAG produces a summary when the user wanted a path.

All tests use a stub LLM or the keyword fallback - no API calls.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from search import router  # noqa: E402


class _StubLLM:
    """Returns a fixed Route, like with_structured_output would."""

    def __init__(self, route=None, raises=None):
        self.route = route
        self.raises = raises
        self.calls = 0

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _prompt):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.route


class TestFallbackRouting:
    @pytest.mark.parametrize("question", [
        "where is the Diwali flyer",
        "Find the 2026 marketing deck",
        "which folder holds the payroll exports",
        "path to the onboarding checklist",
    ])
    def test_locating_a_file(self, question):
        assert router.classify(question).mode == router.FIND_FILE

    @pytest.mark.parametrize("question", [
        "how many employees do we have",
        "what is the total number of contractors",
        "list all engineers",
    ])
    def test_counting_and_listing(self, question):
        assert router.classify(question).mode == router.AGGREGATE

    @pytest.mark.parametrize("question", [
        "what is the production deploy window",
        "summarise the security policy",
        "who leads the Orion project",
    ])
    def test_ordinary_content_questions(self, question):
        assert router.classify(question).mode == router.CONTENT

    def test_duration_questions_are_not_aggregates(self):
        # "How many days of leave do I get" is answered from the handbook's
        # prose, not from counting rows in a register.
        assert router.classify("how many days of leave do I get").mode == router.CONTENT


class TestLlmRouting:
    def test_uses_the_model_when_one_is_given(self):
        llm = _StubLLM(router.Route(mode=router.AGGREGATE, subject="employees"))
        route = router.classify("what's our headcount", llm)
        assert (route.mode, route.subject) == (router.AGGREGATE, "employees")
        assert llm.calls == 1

    def test_model_failure_falls_back_instead_of_failing_the_question(self):
        # A routing outage must degrade to ordinary RAG, never to an error.
        llm = _StubLLM(raises=RuntimeError("rate limited"))
        assert router.classify("where is the flyer", llm).mode == router.FIND_FILE


class TestCanonicalSources:
    SOURCES = {"employees": "/mnt/nas/HR/roster.xlsx",
               "leave requests": "/mnt/nas/HR/leave.xlsx"}

    def test_exact_subject_match(self):
        assert router.canonical_source_for("employees", self.SOURCES) == \
            "/mnt/nas/HR/roster.xlsx"

    def test_matches_a_longer_phrasing(self):
        assert router.canonical_source_for("current employees", self.SOURCES) == \
            "/mnt/nas/HR/roster.xlsx"

    def test_unconfigured_subject_returns_nothing(self):
        # Falls back to ordinary retrieval rather than inventing a source.
        assert router.canonical_source_for("server incidents", self.SOURCES) is None

    def test_no_subject_returns_nothing(self):
        assert router.canonical_source_for(None, self.SOURCES) is None

    def test_missing_config_file_is_not_an_error(self, tmp_path):
        assert router.load_canonical_sources(str(tmp_path / "absent.yaml")) == {}

    def test_reads_configured_sources(self, tmp_path):
        path = tmp_path / "canonical.yaml"
        path.write_text("sources:\n  employees: /mnt/nas/HR/roster.xlsx\n")
        assert router.load_canonical_sources(str(path)) == \
            {"employees": "/mnt/nas/HR/roster.xlsx"}


class TestEmbeddingModelOverride:
    def test_defaults_to_minilm(self):
        import rag
        assert "MiniLM" in rag.EMBEDDING_MODEL or os.environ.get("RAG_EMBEDDING_MODEL")
