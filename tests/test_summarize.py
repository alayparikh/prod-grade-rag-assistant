"""Folder-summary tests.

The expensive mistake here is re-summarising folders that have not
changed: one Haiku call per folder per night, forever, for a share with
thousands of folders. The second is a summary pass that dies on one
unreadable folder. Both are tested; no API calls are made.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer import crawl, summarize  # noqa: E402


class _StubLLM:
    def __init__(self, text="Marketing collateral and event flyers.", raises=None):
        self.text = text
        self.raises = raises
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.raises:
            raise self.raises
        return type("Response", (), {"content": self.text})()


@pytest.fixture
def populated(tmp_path):
    root = tmp_path / "nas"
    (root / "Marketing").mkdir(parents=True)
    (root / "HR").mkdir()
    (root / "Marketing" / "flyer.txt").write_text("Diwali celebration flyer 2026")
    (root / "Marketing" / "brief.md").write_text("campaign brief")
    (root / "HR" / "policy.txt").write_text("leave policy")
    connection = crawl.connect(str(tmp_path / "meta.sqlite"))
    crawl.crawl(str(root), connection)
    yield connection, root
    connection.close()


class TestSummarizeFolders:
    def test_writes_one_summary_per_folder(self, populated):
        connection, _ = populated
        stats = summarize.summarize_folders(connection, _StubLLM())
        assert stats["written"] == 2
        rows = {r["path"]: r["summary"] for r in
                connection.execute("SELECT path, summary FROM folders")}
        assert set(rows) == {"Marketing", "HR"}

    def test_unchanged_folders_are_not_resummarised(self, populated):
        # One Haiku call per folder per night, forever, is the cost of
        # getting this wrong on a share with thousands of folders.
        connection, _ = populated
        llm = _StubLLM()
        summarize.summarize_folders(connection, llm)
        calls_after_first = len(llm.prompts)

        stats = summarize.summarize_folders(connection, llm)
        assert stats == {"written": 0, "skipped": 2, "failed": 0, "removed": 0}
        assert len(llm.prompts) == calls_after_first

    def test_added_file_triggers_one_resummary(self, populated):
        connection, root = populated
        llm = _StubLLM()
        summarize.summarize_folders(connection, llm)
        (root / "Marketing" / "poster.txt").write_text("poster")
        crawl.crawl(str(root), connection)

        stats = summarize.summarize_folders(connection, llm)
        assert (stats["written"], stats["skipped"]) == (1, 1)

    def test_a_failing_folder_does_not_stop_the_pass(self, populated):
        connection, _ = populated
        stats = summarize.summarize_folders(connection, _StubLLM(raises=RuntimeError("429")))
        assert stats["failed"] == 2 and stats["written"] == 0
        # The pass completes; those folders are simply un-narrowed.
        assert connection.execute("SELECT COUNT(*) AS n FROM folders").fetchone()["n"] == 0

    def test_removed_folder_drops_its_summary(self, populated):
        connection, root = populated
        summarize.summarize_folders(connection, _StubLLM())
        for child in (root / "HR").iterdir():
            child.unlink()
        crawl.crawl(str(root), connection)

        stats = summarize.summarize_folders(connection, _StubLLM())
        assert stats["removed"] == 1
        remaining = [r["path"] for r in connection.execute("SELECT path FROM folders")]
        assert remaining == ["Marketing"]

    def test_prompt_includes_names_and_a_text_sample(self, populated):
        connection, _ = populated
        llm = _StubLLM()
        summarize.summarize_folders(connection, llm)
        marketing = next(p for p in llm.prompts if "flyer.txt" in p)
        assert "Diwali celebration flyer" in marketing

    def test_prompt_frames_file_content_as_untrusted(self, populated):
        # File names and excerpts are attacker-controllable on a share
        # anyone can write to.
        connection, _ = populated
        llm = _StubLLM()
        summarize.summarize_folders(connection, llm)
        assert "untrusted" in llm.prompts[0]

    def test_summary_is_collapsed_to_one_line(self, populated):
        connection, _ = populated
        summarize.summarize_folders(connection, _StubLLM(text="  Two\nlines here.  "))
        summary = connection.execute("SELECT summary FROM folders").fetchone()["summary"]
        assert summary == "Two lines here."


class TestReadHead:
    def test_reads_only_text_formats(self, tmp_path):
        text = tmp_path / "a.txt"
        text.write_text("hello world")
        assert summarize.read_head(str(text), 50) == "hello world"

        binary = tmp_path / "b.xlsx"
        binary.write_bytes(b"\x50\x4b\x03\x04")
        assert summarize.read_head(str(binary)) == ""

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert summarize.read_head(str(tmp_path / "absent.txt")) == ""

    def test_truncates(self, tmp_path):
        path = tmp_path / "long.txt"
        path.write_text("x" * 1000)
        assert len(summarize.read_head(str(path), 100)) == 100


class TestMatchingFolders:
    def test_finds_folders_whose_summary_matches(self, populated):
        connection, _ = populated
        summarize.summarize_folders(
            connection, _StubLLM(text="Marketing collateral and event flyers."))
        assert "Marketing" in summarize.matching_folders(connection, "the diwali flyers")

    def test_no_match_returns_empty(self, populated):
        connection, _ = populated
        summarize.summarize_folders(connection, _StubLLM(text="Marketing collateral."))
        assert summarize.matching_folders(connection, "server incident postmortems") == []

    def test_short_question_words_are_ignored(self, populated):
        connection, _ = populated
        summarize.summarize_folders(connection, _StubLLM())
        assert summarize.matching_folders(connection, "is it on") == []
