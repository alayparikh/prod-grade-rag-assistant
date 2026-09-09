"""Loader tests for the formats a shared drive is actually full of.

Each loader is judged on whether its output is *answerable*, not merely
non-empty: a spreadsheet row flattened to bare cell values retrieves badly
even though the extraction "worked".
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rag  # noqa: E402


@pytest.fixture
def roster_xlsx(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "roster.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Employees"
    sheet.append(["Name", "Team", "Start date"])
    sheet.append(["Alay Parikh", "Engineering", "2024-03-01"])
    sheet.append(["Priya Nair", "Design", "2023-11-15"])
    second = workbook.create_sheet("Contractors")
    second.append(["Name", "Agency"])
    second.append(["Sam Rivera", "Northwind"])
    workbook.save(path)
    return str(path)


class TestLoadXlsx:
    def test_pairs_each_value_with_its_column_header(self, roster_xlsx):
        # "Alay Parikh | Engineering" retrieves far worse than
        # "Name: Alay Parikh | Team: Engineering" for "which team is Alay on".
        text = rag.load_xlsx(roster_xlsx)[0].page_content
        assert "Name: Alay Parikh" in text
        assert "Team: Engineering" in text

    def test_covers_every_sheet(self, roster_xlsx):
        text = rag.load_xlsx(roster_xlsx)[0].page_content
        assert "Sheet: Employees" in text and "Sheet: Contractors" in text
        assert "Sam Rivera" in text

    def test_truncates_a_sheet_that_is_really_a_database(self, tmp_path):
        from openpyxl import Workbook

        path = tmp_path / "log.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["id", "event"])
        for i in range(50):
            sheet.append([i, f"event {i}"])
        workbook.save(path)

        documents = rag.load_xlsx(str(path), max_rows_per_sheet=10)
        text = documents[0].page_content
        assert "truncated at 10 rows" in text
        assert "event 9" in text and "event 40" not in text

    def test_empty_sheet_does_not_crash(self, tmp_path):
        from openpyxl import Workbook

        path = tmp_path / "empty.xlsx"
        Workbook().save(path)
        assert rag.load_xlsx(str(path))[0].page_content == ""


class TestLoadPptx:
    @pytest.fixture
    def deck(self, tmp_path):
        from pptx import Presentation

        path = tmp_path / "deck.pptx"
        presentation = Presentation()
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = "Q1 Roadmap"
        slide.placeholders[1].text = "Ship the search assistant"
        slide.notes_slide.notes_text_frame.text = "Budget approved in January"
        presentation.save(path)
        return str(path)

    def test_extracts_slide_text(self, deck):
        text = rag.load_pptx(deck)[0].page_content
        assert "Q1 Roadmap" in text and "Ship the search assistant" in text

    def test_keeps_speaker_notes(self, deck):
        # The notes often hold the explanation the slide only gestures at.
        assert "Budget approved in January" in rag.load_pptx(deck)[0].page_content

    def test_numbers_slides(self, deck):
        assert "Slide 1" in rag.load_pptx(deck)[0].page_content


class TestLoadEml:
    def _write(self, tmp_path, raw):
        path = tmp_path / "mail.eml"
        path.write_text(raw)
        return str(path)

    def test_keeps_headers_and_body(self, tmp_path):
        raw = (
            "From: alice@example.com\n"
            "To: bob@example.com\n"
            "Subject: Diwali flyer\n"
            "Date: Mon, 1 Sep 2026 10:00:00 +0000\n"
            "\n"
            "The flyer is on the share under Marketing.\n"
        )
        text = rag.load_eml(self._write(tmp_path, raw))[0].page_content
        assert "Subject: Diwali flyer" in text
        assert "From: alice@example.com" in text
        assert "under Marketing" in text

    def test_strips_html_markup(self, tmp_path):
        raw = (
            "From: a@example.com\n"
            "Subject: Update\n"
            "Content-Type: text/html\n"
            "\n"
            "<html><body><p>Server <b>migration</b> is done</p></body></html>\n"
        )
        text = rag.load_eml(self._write(tmp_path, raw))[0].page_content
        assert "migration" in text
        assert "<b>" not in text and "<html>" not in text


class TestLoadFileDispatch:
    def test_unknown_extension_falls_back_to_text(self, tmp_path):
        path = tmp_path / "notes.log"
        path.write_text("plain content")
        assert "plain content" in rag.load_file(str(path))[0].page_content

    def test_image_without_ocr_yields_nothing_rather_than_failing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag, "ocr_available", lambda: False)
        path = tmp_path / "scan.png"
        path.write_bytes(b"not really a png")
        assert rag.load_file(str(path)) == []

    def test_ocr_disabled_by_env(self, monkeypatch):
        monkeypatch.setattr(rag, "OCR_ENABLED", False)
        assert rag.ocr_available() is False

    def test_pdf_with_a_text_layer_is_not_ocred(self, monkeypatch):
        # OCR on every PDF would multiply the runtime of a 50 GB index.
        from langchain_core.documents import Document

        monkeypatch.setattr(rag, "PyPDFLoader",
                            lambda path: type("L", (), {"load": lambda self: [
                                Document(page_content="real text", metadata={})]})())
        monkeypatch.setattr(rag, "ocr_available",
                            lambda: (_ for _ in ()).throw(AssertionError("must not OCR")))
        assert rag.load_pdf("x.pdf")[0].page_content == "real text"


class TestSecretRedaction:
    def test_redacts_pan(self):
        out, flagged = rag.redact_secrets("PAN ABCDE1234F on file")
        assert "ABCDE1234F" not in out and flagged

    def test_redacts_aadhaar_when_named(self):
        out, flagged = rag.redact_secrets("Aadhaar 1234 5678 9012")
        assert "1234 5678 9012" not in out and flagged

    def test_leaves_a_bare_twelve_digit_number_alone(self):
        # Order numbers, invoice references and phone numbers share the
        # shape; redacting on shape alone corrupts real answers.
        out, flagged = rag.redact_secrets("order 1234 5678 9012 shipped")
        assert "1234 5678 9012" in out and not flagged

    def test_still_leaves_phone_numbers_and_long_ids_alone(self):
        out, _ = rag.redact_secrets("call 408-483-1223, id 8573032742367710")
        assert "408-483-1223" in out and "8573032742367710" in out


class TestLoaderErrorsAreSurvivable:
    def test_one_unreadable_file_does_not_end_the_sync(self, tmp_path, monkeypatch):
        # A nightly run over a share that is still being written to will hit
        # locked and half-written files; the run must continue.
        import json
        import logging

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "good.txt").write_text("readable content")
        (docs / "bad.txt").write_text("x")

        persist = tmp_path / "index"
        persist.mkdir()
        log_path = tmp_path / "events.jsonl"
        logger = logging.getLogger("rag.events")
        saved = list(logger.handlers)
        logger.handlers.clear()

        monkeypatch.setattr(rag, "DOCS_PATH", str(docs))
        monkeypatch.setattr(rag, "MANIFEST_PATH", str(persist / "manifest.json"))
        monkeypatch.setattr(rag, "PERSIST_PATH", str(persist))
        monkeypatch.setattr(rag, "LOG_PATH", str(log_path))
        monkeypatch.setattr(rag, "_event_logger", None)

        real_load = rag.load_file

        def flaky(path):
            if path.endswith("bad.txt"):
                raise OSError("Resource temporarily unavailable")
            return real_load(path)

        monkeypatch.setattr(rag, "load_file", flaky)

        added = []

        class _FakeStore:
            _collection = type("C", (), {"count": staticmethod(lambda: len(added))})()

            def delete(self, where=None):
                pass

            def add_documents(self, chunks):
                # Chroma returns the ids it assigned; the keyword index
                # needs them to delete the right rows on the next change.
                added.extend(chunks)
                return [f"id-{len(added) - len(chunks) + i}" for i in range(len(chunks))]

        try:
            rag.sync_vectorstore(_FakeStore())
            events = [json.loads(line) for line in
                      log_path.read_text().strip().splitlines()]
        finally:
            for handler in logger.handlers:
                handler.close()
            logger.handlers[:] = saved
            rag._event_logger = None

        assert added, "the readable file must still be indexed"
        assert any(e.get("guardrail", "").startswith("loader_error") for e in events)

        # The failed file must not be recorded as done, or it would never
        # be retried.
        manifest = json.loads((persist / "manifest.json").read_text())
        assert not any(p.endswith("bad.txt") for p in manifest)
        assert any(p.endswith("good.txt") for p in manifest)
