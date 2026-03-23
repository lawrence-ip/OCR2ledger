"""
Unit tests for pipeline.py.

All tests use unittest.mock to avoid real Google Cloud API calls.
"""

import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure the repo root is on sys.path so `import pipeline` works when tests
# are run from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline  # noqa: E402  (import after sys.path manipulation)
from google.cloud import documentai_v1 as documentai


# ---------------------------------------------------------------------------
# Helpers to build minimal Document AI objects for testing
# ---------------------------------------------------------------------------

def _make_entity(
    type_: str,
    mention_text: str,
    confidence: float = 0.95,
    page: int = 0,
    normalized_text: str = "",
) -> documentai.Document.Entity:
    """Return a synthetic Document.Entity."""
    page_ref = documentai.Document.PageAnchor.PageRef(page=page)
    page_anchor = documentai.Document.PageAnchor(page_refs=[page_ref])
    norm_value = documentai.Document.Entity.NormalizedValue(text=normalized_text)
    return documentai.Document.Entity(
        type_=type_,
        mention_text=mention_text,
        confidence=confidence,
        page_anchor=page_anchor,
        normalized_value=norm_value,
    )


def _make_text_segment(start: int, end: int) -> documentai.Document.TextAnchor.TextSegment:
    return documentai.Document.TextAnchor.TextSegment(
        start_index=start, end_index=end
    )


def _make_layout(start: int, end: int, confidence: float = 0.9) -> documentai.Document.Page.Layout:
    anchor = documentai.Document.TextAnchor(
        text_segments=[_make_text_segment(start, end)]
    )
    return documentai.Document.Page.Layout(
        text_anchor=anchor, confidence=confidence
    )


def _make_form_field(
    key_start: int,
    key_end: int,
    val_start: int,
    val_end: int,
    confidence: float = 0.88,
) -> documentai.Document.Page.FormField:
    field_name = documentai.Document.Page.Layout(
        text_anchor=documentai.Document.TextAnchor(
            text_segments=[_make_text_segment(key_start, key_end)]
        ),
        confidence=confidence,
    )
    field_value = documentai.Document.Page.Layout(
        text_anchor=documentai.Document.TextAnchor(
            text_segments=[_make_text_segment(val_start, val_end)]
        ),
        confidence=confidence,
    )
    return documentai.Document.Page.FormField(
        field_name=field_name, field_value=field_value
    )


def _make_table_cell(start: int, end: int, conf: float = 0.85) -> documentai.Document.Page.Table.TableCell:
    layout = _make_layout(start, end, confidence=conf)
    return documentai.Document.Page.Table.TableCell(layout=layout)


def _make_table(header_texts: list, row_texts: list, full_text: str) -> documentai.Document.Page.Table:
    """
    Build a minimal table.

    header_texts: list of strings that appear as consecutive substrings in full_text
    row_texts:    list of strings that appear as consecutive substrings in full_text
    """
    def _find_segment(text, substring):
        start = text.index(substring)
        return start, start + len(substring)

    header_cells = []
    for h in header_texts:
        s, e = _find_segment(full_text, h)
        header_cells.append(_make_table_cell(s, e))

    body_cells = []
    for r in row_texts:
        s, e = _find_segment(full_text, r)
        body_cells.append(_make_table_cell(s, e))

    header_row = documentai.Document.Page.Table.TableRow(cells=header_cells)
    body_row = documentai.Document.Page.Table.TableRow(cells=body_cells)
    return documentai.Document.Page.Table(header_rows=[header_row], body_rows=[body_row])


# ---------------------------------------------------------------------------
# Tests: _layout_text
# ---------------------------------------------------------------------------

class TestLayoutText:
    def test_single_segment(self):
        layout = _make_layout(0, 5)
        assert pipeline._layout_text(layout, "Hello World") == "Hello"

    def test_empty_segments(self):
        layout = documentai.Document.Page.Layout(
            text_anchor=documentai.Document.TextAnchor(text_segments=[])
        )
        assert pipeline._layout_text(layout, "anything") == ""


# ---------------------------------------------------------------------------
# Tests: extract_entities
# ---------------------------------------------------------------------------

class TestExtractEntities:
    def _make_doc(self) -> documentai.Document:
        doc = documentai.Document(text="Invoice #12345  $100.00")
        doc.entities.append(_make_entity("invoice_id", "12345", page=0))
        doc.entities.append(
            _make_entity("total_amount", "$100.00", confidence=0.99, page=0, normalized_text="100.00")
        )
        return doc

    def test_returns_one_row_per_entity(self):
        rows = pipeline.extract_entities(self._make_doc(), "test.pdf")
        assert len(rows) == 2

    def test_entity_row_fields(self):
        rows = pipeline.extract_entities(self._make_doc(), "inv.pdf")
        row = rows[0]
        assert row["source_file"] == "inv.pdf"
        assert row["type"] == "entity"
        assert row["key"] == "invoice_id"
        assert row["value"] == "12345"
        assert row["page"] == 1  # 0-indexed → 1-indexed conversion

    def test_normalized_value_populated(self):
        rows = pipeline.extract_entities(self._make_doc(), "inv.pdf")
        total_row = next(r for r in rows if r["key"] == "total_amount")
        assert total_row["normalized_value"] == "100.00"

    def test_empty_entities(self):
        doc = documentai.Document(text="no entities here")
        assert pipeline.extract_entities(doc, "empty.pdf") == []


# ---------------------------------------------------------------------------
# Tests: extract_form_fields
# ---------------------------------------------------------------------------

class TestExtractFormFields:
    def _make_doc(self) -> documentai.Document:
        # full_text: "Name:  John Doe"  (indices: Name: 0-5, John Doe 7-15)
        text = "Name:  John Doe"
        page = documentai.Document.Page(page_number=1)
        page.form_fields.append(_make_form_field(0, 5, 7, 15))
        doc = documentai.Document(text=text)
        doc.pages.append(page)
        return doc

    def test_returns_one_row_per_field(self):
        rows = pipeline.extract_form_fields(self._make_doc(), "form.pdf")
        assert len(rows) == 1

    def test_form_field_row_fields(self):
        rows = pipeline.extract_form_fields(self._make_doc(), "form.pdf")
        row = rows[0]
        assert row["type"] == "form_field"
        assert row["key"] == "Name:"
        assert row["value"] == "John Doe"
        assert row["page"] == 1

    def test_empty_form_fields(self):
        doc = documentai.Document(text="plain text")
        page = documentai.Document.Page(page_number=1)
        doc.pages.append(page)
        assert pipeline.extract_form_fields(doc, "plain.pdf") == []


# ---------------------------------------------------------------------------
# Tests: extract_tables
# ---------------------------------------------------------------------------

class TestExtractTables:
    def _make_doc(self) -> documentai.Document:
        # Headers and body values are distinct substrings at known positions.
        # text layout: "Item|Quantity|Price|Apple|5|10.00"
        text = "Item|Quantity|Price|Apple|5|10.00"
        table = _make_table(
            header_texts=["Item", "Quantity", "Price"],
            row_texts=["Apple", "5", "10.00"],
            full_text=text,
        )
        page = documentai.Document.Page(page_number=1)
        page.tables.append(table)
        doc = documentai.Document(text=text)
        doc.pages.append(page)
        return doc

    def test_table_cell_rows_produced(self):
        rows = pipeline.extract_tables(self._make_doc(), "tbl.pdf")
        assert len(rows) == 3  # one body row × 3 columns

    def test_table_row_key_includes_header(self):
        rows = pipeline.extract_tables(self._make_doc(), "tbl.pdf")
        keys = [r["key"] for r in rows]
        assert any("Item" in k for k in keys)
        assert any("Quantity" in k for k in keys)
        assert any("Price" in k for k in keys)

    def test_table_body_values_are_distinct_from_headers(self):
        rows = pipeline.extract_tables(self._make_doc(), "tbl.pdf")
        values = [r["value"] for r in rows]
        assert "Apple" in values
        assert "5" in values
        assert "10.00" in values


# ---------------------------------------------------------------------------
# Tests: document_to_rows (integration-style)
# ---------------------------------------------------------------------------

class TestDocumentToRows:
    def test_fallback_to_text_when_no_structured_data(self):
        doc = documentai.Document(text="Some scanned text")
        rows = pipeline.document_to_rows(doc, "scan.pdf")
        assert len(rows) == 1
        assert rows[0]["type"] == "text"
        assert rows[0]["value"] == "Some scanned text"

    def test_entities_take_priority(self):
        doc = documentai.Document(text="Invoice #42")
        doc.entities.append(_make_entity("invoice_id", "42"))
        rows = pipeline.document_to_rows(doc, "inv.pdf")
        assert any(r["type"] == "entity" for r in rows)

    def test_empty_text_fallback_value_is_empty_string(self):
        doc = documentai.Document(text="   ")
        rows = pipeline.document_to_rows(doc, "blank.pdf")
        assert rows[0]["value"] == ""


# ---------------------------------------------------------------------------
# Tests: save_document_json / load_document_json
# ---------------------------------------------------------------------------

class TestJsonPersistence:
    def test_round_trip(self, tmp_path):
        doc = documentai.Document(text="round trip test")
        doc.entities.append(_make_entity("field", "value"))
        saved_path = pipeline.save_document_json(doc, tmp_path, "my_doc")
        assert saved_path.exists()

        loaded = pipeline.load_document_json(str(saved_path))
        assert loaded.text == "round trip test"

    def test_json_file_named_correctly(self, tmp_path):
        doc = documentai.Document(text="x")
        path = pipeline.save_document_json(doc, tmp_path, "invoice_2024")
        assert path.name == "invoice_2024.json"

    def test_output_folder_created_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        doc = documentai.Document(text="x")
        pipeline.save_document_json(doc, nested, "doc")
        assert nested.is_dir()


# ---------------------------------------------------------------------------
# Tests: write_csv
# ---------------------------------------------------------------------------

class TestWriteCsv:
    def test_creates_file_with_header(self, tmp_path):
        csv_path = str(tmp_path / "out.csv")
        pipeline.write_csv([], csv_path)
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == pipeline.CSV_FIELDNAMES

    def test_rows_written_correctly(self, tmp_path):
        csv_path = str(tmp_path / "out.csv")
        rows = [
            {
                "source_file": "a.pdf",
                "type": "entity",
                "key": "total",
                "value": "42",
                "normalized_value": "42.00",
                "confidence": 0.9,
                "page": 1,
            }
        ]
        pipeline.write_csv(rows, csv_path)
        with open(csv_path, newline="") as fh:
            content = list(csv.DictReader(fh))
        assert len(content) == 1
        assert content[0]["key"] == "total"
        assert content[0]["value"] == "42"


# ---------------------------------------------------------------------------
# Tests: process_pdf_folder (mocked Document AI)
# ---------------------------------------------------------------------------

class TestProcessPdfFolder:
    def _create_dummy_pdfs(self, folder: Path, count: int = 2):
        for i in range(count):
            (folder / f"scan_{i:02d}.pdf").write_bytes(b"%PDF-1.4 fake content")

    def _make_simple_document(self, name: str) -> documentai.Document:
        doc = documentai.Document(text=f"Content of {name}")
        doc.entities.append(_make_entity("doc_name", name))
        return doc

    @mock.patch("pipeline.process_document")
    @mock.patch("pipeline.build_client")
    def test_processes_all_pdfs(self, mock_build_client, mock_process_doc, tmp_path):
        pdf_folder = tmp_path / "pdfs"
        pdf_folder.mkdir()
        self._create_dummy_pdfs(pdf_folder, count=3)

        mock_client = mock.MagicMock()
        mock_build_client.return_value = mock_client
        mock_client.processor_path.return_value = "projects/p/locations/us/processors/x"
        mock_process_doc.side_effect = lambda client, name, path, **kw: self._make_simple_document(
            Path(path).name
        )

        csv_path = str(tmp_path / "output.csv")
        total = pipeline.process_pdf_folder(
            input_folder=str(pdf_folder),
            output_csv=csv_path,
            project_id="my-project",
            location="us",
            processor_id="abc123",
        )

        assert total == 3  # one entity row per PDF
        assert Path(csv_path).exists()

    @mock.patch("pipeline.process_document")
    @mock.patch("pipeline.build_client")
    def test_saves_json_when_flag_set(self, mock_build_client, mock_process_doc, tmp_path):
        pdf_folder = tmp_path / "pdfs"
        pdf_folder.mkdir()
        self._create_dummy_pdfs(pdf_folder, count=1)

        mock_client = mock.MagicMock()
        mock_build_client.return_value = mock_client
        mock_client.processor_path.return_value = "projects/p/locations/us/processors/x"
        mock_process_doc.return_value = self._make_simple_document("scan_00.pdf")

        json_folder = tmp_path / "json"
        csv_path = str(tmp_path / "output.csv")
        pipeline.process_pdf_folder(
            input_folder=str(pdf_folder),
            output_csv=csv_path,
            project_id="my-project",
            location="us",
            processor_id="abc123",
            save_json=True,
            json_output_folder=str(json_folder),
        )

        json_files = list(json_folder.glob("*.json"))
        assert len(json_files) == 1
        assert json_files[0].name == "scan_00.json"

    @mock.patch("pipeline.build_client")
    def test_empty_folder_returns_zero(self, mock_build_client, tmp_path):
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        total = pipeline.process_pdf_folder(
            input_folder=str(empty_folder),
            output_csv=str(tmp_path / "out.csv"),
            project_id="p",
            location="us",
            processor_id="x",
        )
        assert total == 0

    @mock.patch("pipeline.process_document")
    @mock.patch("pipeline.build_client")
    def test_continues_after_single_pdf_error(
        self, mock_build_client, mock_process_doc, tmp_path
    ):
        pdf_folder = tmp_path / "pdfs"
        pdf_folder.mkdir()
        self._create_dummy_pdfs(pdf_folder, count=2)

        mock_client = mock.MagicMock()
        mock_build_client.return_value = mock_client
        mock_client.processor_path.return_value = "projects/p/locations/us/processors/x"

        # First PDF raises, second succeeds
        mock_process_doc.side_effect = [
            RuntimeError("API error"),
            self._make_simple_document("scan_01.pdf"),
        ]

        csv_path = str(tmp_path / "output.csv")
        total = pipeline.process_pdf_folder(
            input_folder=str(pdf_folder),
            output_csv=csv_path,
            project_id="p",
            location="us",
            processor_id="x",
        )

        assert total == 1  # only the second PDF produced output


# ---------------------------------------------------------------------------
# Tests: CLI argument parsing
# ---------------------------------------------------------------------------

class TestCli:
    @mock.patch("pipeline.process_pdf_folder")
    def test_required_args_passed_through(self, mock_pipeline, tmp_path):
        pdf_folder = tmp_path / "pdfs"
        pdf_folder.mkdir()
        csv_out = str(tmp_path / "out.csv")

        pipeline.main(
            [
                str(pdf_folder),
                csv_out,
                "--project-id", "my-gcp-project",
                "--processor-id", "my-processor",
            ]
        )

        mock_pipeline.assert_called_once_with(
            input_folder=str(pdf_folder),
            output_csv=csv_out,
            project_id="my-gcp-project",
            location="us",
            processor_id="my-processor",
            save_json=False,
            json_output_folder="json_output",
        )

    @mock.patch("pipeline.process_pdf_folder")
    def test_save_json_flag(self, mock_pipeline, tmp_path):
        pdf_folder = tmp_path / "pdfs"
        pdf_folder.mkdir()
        csv_out = str(tmp_path / "out.csv")

        pipeline.main(
            [
                str(pdf_folder),
                csv_out,
                "--project-id", "p",
                "--processor-id", "x",
                "--save-json",
                "--json-output-folder", "/tmp/my_json",
            ]
        )

        _, kwargs = mock_pipeline.call_args
        assert kwargs["save_json"] is True
        assert kwargs["json_output_folder"] == "/tmp/my_json"
