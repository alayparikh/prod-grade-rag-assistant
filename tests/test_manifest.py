"""Incremental-sync tests.

On a 50 GB network share the difference between "stat every file" and
"read every file" is the entire nightly run, so the tests that matter here
are the ones asserting that a file is *not* opened.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag  # noqa: E402


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("hello")
    return str(path)


class TestFileHash:
    def test_streams_without_reading_the_whole_file_at_once(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag, "HASH_BLOCK_SIZE", 8)
        path = tmp_path / "big.bin"
        path.write_bytes(b"x" * 100)

        import hashlib
        assert rag.file_hash(str(path)) == hashlib.sha256(b"x" * 100).hexdigest()

    def test_matches_across_block_boundaries(self, tmp_path, monkeypatch):
        import hashlib
        payload = bytes(range(256)) * 40
        path = tmp_path / "b.bin"
        path.write_bytes(payload)
        monkeypatch.setattr(rag, "HASH_BLOCK_SIZE", 7)
        assert rag.file_hash(str(path)) == hashlib.sha256(payload).hexdigest()


class TestFileStamp:
    def test_first_look_reads_and_hashes(self, sample):
        stamp, was_read = rag.file_stamp(sample)
        assert was_read is True
        assert stamp["sha256"] and stamp["size"] == 5

    def test_unchanged_file_is_not_reopened(self, sample, monkeypatch):
        previous, _ = rag.file_stamp(sample)

        def fail(_path):
            raise AssertionError("unchanged file must not be re-read")

        monkeypatch.setattr(rag, "file_hash", fail)
        stamp, was_read = rag.file_stamp(sample, previous=previous)
        assert was_read is False
        assert stamp["sha256"] == previous["sha256"]

    def test_changed_size_forces_a_re_read(self, sample):
        previous, _ = rag.file_stamp(sample)
        with open(sample, "w") as f:
            f.write("hello world")
        stamp, was_read = rag.file_stamp(sample, previous=previous)
        assert was_read is True
        assert stamp["sha256"] != previous["sha256"]

    def test_touched_but_identical_file_is_re_read_but_keeps_its_hash(self, sample):
        # A restore or a copy changes mtime without changing content. One
        # read is unavoidable; re-embedding every chunk is not.
        previous, _ = rag.file_stamp(sample)
        os.utime(sample, (1_000_000, 1_000_000))
        stamp, was_read = rag.file_stamp(sample, previous=previous)
        assert was_read is True
        assert stamp["sha256"] == previous["sha256"]

    def test_missing_sha_in_previous_forces_a_re_read(self, sample):
        stat = os.stat(sample)
        legacy = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        _, was_read = rag.file_stamp(sample, previous=legacy)
        assert was_read is True


class TestLegacyManifest:
    def test_old_path_to_hash_format_still_loads(self, tmp_path, monkeypatch):
        import json

        persist = tmp_path / "index"
        persist.mkdir()
        manifest_path = persist / "manifest.json"
        manifest_path.write_text(json.dumps({"./docs/a.txt": "abc123"}))
        monkeypatch.setattr(rag, "MANIFEST_PATH", str(manifest_path))

        manifest = rag.load_manifest()
        assert manifest["./docs/a.txt"]["sha256"] == "abc123"
        assert manifest["./docs/a.txt"]["mtime_ns"] is None  # forces one re-stamp
