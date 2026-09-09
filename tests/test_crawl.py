"""Crawler and file-search tests.

The crawler's whole value is that it does not reopen unchanged files, and
its whole risk is that the FTS index drifts out of step with the files
table (an external-content FTS5 table does not follow its content table on
its own). Both are tested directly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer import crawl  # noqa: E402
from search import metadata  # noqa: E402


@pytest.fixture
def db(tmp_path):
    connection = crawl.connect(str(tmp_path / "meta.sqlite"))
    yield connection
    connection.close()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "nas"
    (root / "HR").mkdir(parents=True)
    (root / "Marketing" / "2026").mkdir(parents=True)
    (root / "@eaDir").mkdir()
    (root / "HR" / "employee_roster.xlsx").write_text("roster")
    (root / "HR" / "policy.pdf").write_text("policy")
    (root / "Marketing" / "2026" / "Diwali_Flyer_Final.png").write_text("img")
    (root / "@eaDir" / "thumb.jpg").write_text("thumb")
    (root / ".DS_Store").write_text("junk")
    return root


def paths_in(connection):
    return sorted(os.path.basename(r["path"])
                  for r in connection.execute("SELECT path FROM files"))


class TestWalkFiles:
    def test_skips_nas_housekeeping_and_os_litter(self, tree):
        found = {os.path.basename(p) for p, _ in crawl.walk_files(str(tree))}
        assert found == {"employee_roster.xlsx", "policy.pdf", "Diwali_Flyer_Final.png"}

    def test_unreadable_directory_is_reported_not_fatal(self, tmp_path):
        root = tmp_path / "nas"
        (root / "ok").mkdir(parents=True)
        (root / "ok" / "a.txt").write_text("a")
        locked = root / "locked"
        locked.mkdir()
        (locked / "b.txt").write_text("b")
        os.chmod(locked, 0o000)
        errors = []
        try:
            found = {os.path.basename(p) for p, _ in
                     crawl.walk_files(str(root), on_error=lambda p, e: errors.append(p))}
        finally:
            os.chmod(locked, 0o755)
        assert "a.txt" in found  # the readable half still indexes
        assert errors


class TestCrawl:
    def test_first_run_records_every_eligible_file(self, db, tree):
        stats = crawl.crawl(str(tree), db)
        assert stats["added"] == 3
        assert paths_in(db) == ["Diwali_Flyer_Final.png", "employee_roster.xlsx", "policy.pdf"]

    def test_second_run_is_a_no_op(self, db, tree):
        crawl.crawl(str(tree), db)
        stats = crawl.crawl(str(tree), db)
        assert (stats["added"], stats["updated"], stats["removed"]) == (0, 0, 0)
        assert stats["scanned"] == 3

    def test_modified_file_is_updated(self, db, tree):
        crawl.crawl(str(tree), db)
        target = tree / "HR" / "policy.pdf"
        target.write_text("a much longer policy document")
        os.utime(target, (1_000_000, 1_000_000))
        stats = crawl.crawl(str(tree), db)
        assert (stats["updated"], stats["added"]) == (1, 0)
        row = db.execute("SELECT size FROM files WHERE name = 'policy.pdf'").fetchone()
        assert row["size"] == len("a much longer policy document")

    def test_deleted_file_is_removed_from_both_tables(self, db, tree):
        crawl.crawl(str(tree), db)
        (tree / "HR" / "policy.pdf").unlink()
        stats = crawl.crawl(str(tree), db)
        assert stats["removed"] == 1
        assert "policy.pdf" not in paths_in(db)
        hits = db.execute(
            "SELECT COUNT(*) AS n FROM files_fts WHERE files_fts MATCH '\"policy\"*'"
        ).fetchone()["n"]
        assert hits == 0  # the FTS index followed the delete

    def test_renamed_file_leaves_no_stale_fts_row(self, db, tree):
        crawl.crawl(str(tree), db)
        (tree / "HR" / "policy.pdf").rename(tree / "HR" / "handbook.pdf")
        crawl.crawl(str(tree), db)
        query = metadata.FileQuery(terms=["policy"])
        assert metadata.search_files(db, query) == []
        assert metadata.search_files(db, metadata.FileQuery(terms=["handbook"]))

    def test_marks_only_loadable_extensions_as_indexable(self, db, tree):
        crawl.crawl(str(tree), db)
        indexable = {os.path.basename(p) for p in crawl.indexable_paths(db)}
        assert indexable == {"employee_roster.xlsx", "policy.pdf"}
        assert "Diwali_Flyer_Final.png" not in indexable  # censused, not text-indexed

    def test_records_a_run_summary(self, db, tree):
        crawl.crawl(str(tree), db)
        row = db.execute("SELECT * FROM crawl_runs").fetchone()
        assert row["scanned"] == 3 and row["finished_at"] is not None


class TestConnect:
    def test_shared_connection_is_usable_from_another_thread(self, tmp_path):
        # Regression: Streamlit runs each rerun on a different thread, and a
        # cached connection opened with the default guard raised
        # "SQLite objects created in a thread can only be used in that same
        # thread" on the second page view.
        import threading

        connection = crawl.connect(str(tmp_path / "m.sqlite"),
                                   shared_across_threads=True)
        result = {}

        def read():
            try:
                result["n"] = connection.execute(
                    "SELECT COUNT(*) AS n FROM files").fetchone()["n"]
            except Exception as e:  # noqa: BLE001
                result["error"] = e

        thread = threading.Thread(target=read)
        thread.start()
        thread.join()
        connection.close()
        assert result == {"n": 0}


class TestCensus:
    def test_totals_and_breakdown(self, db, tree):
        crawl.crawl(str(tree), db)
        report = crawl.census(db)
        assert report["total_files"] == 3
        assert report["indexable_files"] == 2
        assert {r["ext"] for r in report["by_ext"]} == {".xlsx", ".pdf", ".png"}
        assert "3 files" in crawl.format_census(report)

    def test_scales_units_to_the_data(self):
        # A 50 GB share and a 13-file fixture corpus both have to read
        # sensibly; a fixed GB unit prints "0.00 GB" for the latter.
        assert crawl.human_bytes(512) == "512 B"
        assert crawl.human_bytes(2048) == "2.0 KB"
        assert crawl.human_bytes(50 * 1024**3) == "50.0 GB"


class TestBuildMatchExpression:
    def test_terms_become_or_ed_prefix_queries(self):
        assert metadata.build_match_expression(["diwali", "flyer"]) == '"diwali"* OR "flyer"*'

    def test_strips_fts_operators_that_would_be_a_syntax_error(self):
        # "Q1-2026 (final)" is a plausible question and invalid FTS5 syntax.
        expression = metadata.build_match_expression(["Q1-2026", "(final)"])
        assert "(" not in expression and "-" not in expression
        assert '"final"*' in expression

    def test_drops_single_characters(self):
        assert metadata.build_match_expression(["a", "hr"]) == '"hr"*'

    def test_empty_terms_yield_empty_expression(self):
        assert metadata.build_match_expression([]) == ""


class TestSearchFiles:
    def test_finds_by_partial_name(self, db, tree):
        crawl.crawl(str(tree), db)
        results = metadata.search_files(db, metadata.FileQuery(terms=["diwali"]))
        assert [r["name"] for r in results] == ["Diwali_Flyer_Final.png"]

    def test_finds_by_folder_name(self, db, tree):
        crawl.crawl(str(tree), db)
        results = metadata.search_files(db, metadata.FileQuery(terms=["marketing"]))
        assert [r["name"] for r in results] == ["Diwali_Flyer_Final.png"]

    def test_extension_filter(self, db, tree):
        crawl.crawl(str(tree), db)
        query = metadata.FileQuery(terms=["policy", "roster"], extensions=[".pdf"])
        assert [r["name"] for r in metadata.search_files(db, query)] == ["policy.pdf"]

    def test_year_in_path_matches(self, db, tree):
        crawl.crawl(str(tree), db)
        query = metadata.FileQuery(terms=["diwali"], year=2026)
        assert len(metadata.search_files(db, query)) == 1

    def test_wrong_year_excludes(self, db, tree):
        crawl.crawl(str(tree), db)
        query = metadata.FileQuery(terms=["diwali"], year=1999)
        assert metadata.search_files(db, query) == []

    def test_empty_terms_return_nothing_rather_than_everything(self, db, tree):
        # Fails closed: a router that extracts no usable term must not
        # dump the whole share into the UI.
        crawl.crawl(str(tree), db)
        assert metadata.search_files(db, metadata.FileQuery(terms=[])) == []

    def test_access_check_filters_results(self, db, tree):
        crawl.crawl(str(tree), db)
        query = metadata.FileQuery(terms=["policy", "roster", "diwali"])
        results = metadata.search_files(db, query, access_check=lambda p: "/HR/" not in p)
        assert [r["name"] for r in results] == ["Diwali_Flyer_Final.png"]

    def test_limit_applies_after_access_filtering(self, db, tmp_path):
        root = tmp_path / "nas2"
        (root / "open").mkdir(parents=True)
        (root / "closed").mkdir()
        for i in range(10):
            (root / "closed" / f"report_{i}.pdf").write_text("x")
        for i in range(3):
            (root / "open" / f"report_open_{i}.pdf").write_text("x")
        crawl.crawl(str(root), db)
        results = metadata.search_files(
            db, metadata.FileQuery(terms=["report"]), limit=5,
            access_check=lambda p: "/open/" in p,
        )
        # Denied hits must not consume the result budget.
        assert len(results) == 3
        assert all("open" in r["path"] for r in results)


class TestFallbackParsing:
    def test_strips_stopwords_without_an_llm(self):
        query = metadata.parse_question("show me the flyer for Diwali 2026")
        assert "flyer" in query.terms and "diwali" in query.terms
        assert "show" not in query.terms and "the" not in query.terms

    def test_extracts_year(self):
        assert metadata.parse_question("Diwali 2026 flyer").year == 2026
        assert metadata.parse_question("the Diwali flyer").year is None
