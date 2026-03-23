#!/usr/bin/env python3
"""
OCR2Ledger Pipeline
===================
Reads a folder of scanned PDFs, sends each one to Google Document AI for OCR /
structured-data extraction, saves the raw JSON responses to disk, then parses
every response into a single flat CSV file.

Usage
-----
    python pipeline.py <input_folder> <output_csv> \\
        --project-id  <GCP_PROJECT_ID>   \\
        --location    us                  \\
        --processor-id <PROCESSOR_ID>     \\
        [--save-json] [--json-output-folder json_output]
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai


# ---------------------------------------------------------------------------
# Document AI helpers
# ---------------------------------------------------------------------------

def build_client(location: str) -> documentai.DocumentProcessorServiceClient:
    """Return a Document AI client pointed at *location*."""
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    return documentai.DocumentProcessorServiceClient(client_options=opts)


def process_document(
    client: documentai.DocumentProcessorServiceClient,
    processor_name: str,
    file_path: str,
    mime_type: str = "application/pdf",
) -> documentai.Document:
    """Upload *file_path* to Document AI and return the parsed Document object."""
    with open(file_path, "rb") as fh:
        content = fh.read()

    raw_document = documentai.RawDocument(content=content, mime_type=mime_type)
    request = documentai.ProcessRequest(
        name=processor_name, raw_document=raw_document
    )
    result = client.process_document(request=request)
    return result.document


# ---------------------------------------------------------------------------
# Text extraction utilities
# ---------------------------------------------------------------------------

def _layout_text(layout, document_text: str) -> str:
    """Return the text covered by *layout*'s text anchor segments."""
    parts: List[str] = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index)
        end = int(segment.end_index)
        parts.append(document_text[start:end])
    return "".join(parts)


# ---------------------------------------------------------------------------
# Data extraction from a Document AI Document
# ---------------------------------------------------------------------------

def extract_entities(
    document: documentai.Document, source_file: str
) -> List[dict]:
    """Extract top-level entities (e.g. invoice fields, receipt line items)."""
    rows: List[dict] = []
    for entity in document.entities:
        page_num = 1
        if entity.page_anchor and entity.page_anchor.page_refs:
            page_num = int(entity.page_anchor.page_refs[0].page) + 1
        rows.append(
            {
                "source_file": source_file,
                "type": "entity",
                "key": entity.type_,
                "value": (entity.mention_text or "").strip(),
                "normalized_value": (
                    entity.normalized_value.text
                    if entity.normalized_value and entity.normalized_value.text
                    else ""
                ),
                "confidence": round(entity.confidence, 4),
                "page": page_num,
            }
        )
    return rows


def extract_form_fields(
    document: documentai.Document, source_file: str
) -> List[dict]:
    """Extract form key-value pairs from every page."""
    rows: List[dict] = []
    for page in document.pages:
        page_num = page.page_number
        for field in page.form_fields:
            key = _layout_text(field.field_name, document.text).strip()
            value = _layout_text(field.field_value, document.text).strip()
            rows.append(
                {
                    "source_file": source_file,
                    "type": "form_field",
                    "key": key,
                    "value": value,
                    "normalized_value": "",
                    "confidence": round(field.field_value.confidence, 4),
                    "page": page_num,
                }
            )
    return rows


def extract_tables(
    document: documentai.Document, source_file: str
) -> List[dict]:
    """Flatten table cells into individual rows (one cell per CSV row)."""
    rows: List[dict] = []
    for page in document.pages:
        page_num = page.page_number
        for table_idx, table in enumerate(page.tables):
            # Derive column headers from the first header row when available.
            headers: List[str] = []
            if table.header_rows:
                headers = [
                    _layout_text(cell.layout, document.text).strip()
                    for cell in table.header_rows[0].cells
                ]

            for row_idx, row in enumerate(table.body_rows):
                for col_idx, cell in enumerate(row.cells):
                    col_label = (
                        headers[col_idx]
                        if col_idx < len(headers)
                        else f"col_{col_idx}"
                    )
                    rows.append(
                        {
                            "source_file": source_file,
                            "type": "table",
                            "key": (
                                f"table_{table_idx}_row_{row_idx}_{col_label}"
                            ),
                            "value": _layout_text(
                                cell.layout, document.text
                            ).strip(),
                            "normalized_value": "",
                            "confidence": round(cell.layout.confidence, 4),
                            "page": page_num,
                        }
                    )
    return rows


def document_to_rows(
    document: documentai.Document, source_file: str
) -> List[dict]:
    """
    Convert a Document AI Document into a list of flat dicts ready for CSV.

    Extraction priority:
    1. Entities  (structured processors: invoice, expense, ID, …)
    2. Form fields  (form parser)
    3. Tables
    4. Raw text fallback when none of the above yield data
    """
    rows: List[dict] = []
    rows.extend(extract_entities(document, source_file))
    rows.extend(extract_form_fields(document, source_file))
    rows.extend(extract_tables(document, source_file))

    if not rows:
        # Fall back to the complete OCR text so we always produce output.
        rows.append(
            {
                "source_file": source_file,
                "type": "text",
                "key": "content",
                "value": document.text.strip(),
                "normalized_value": "",
                "confidence": 1.0,
                "page": 1,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# JSON persistence helpers
# ---------------------------------------------------------------------------

def save_document_json(
    document: documentai.Document,
    output_folder: Path,
    stem: str,
) -> Path:
    """Serialise *document* to ``<output_folder>/<stem>.json`` and return the path."""
    output_folder.mkdir(parents=True, exist_ok=True)
    json_path = output_folder / f"{stem}.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(type(document).to_dict(document), fh, indent=2)
    return json_path


def load_document_json(json_path: str) -> documentai.Document:
    """Load a previously-saved Document AI JSON file back into a Document object."""
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return documentai.Document(data)


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

CSV_FIELDNAMES = [
    "source_file",
    "type",
    "key",
    "value",
    "normalized_value",
    "confidence",
    "page",
]


def write_csv(rows: List[dict], output_csv: str) -> None:
    """Write *rows* to *output_csv* using the standard CSV dialect."""
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def process_pdf_folder(
    input_folder: str,
    output_csv: str,
    project_id: str,
    location: str,
    processor_id: str,
    save_json: bool = False,
    json_output_folder: Optional[str] = "json_output",
) -> int:
    """
    Process every PDF in *input_folder* and write results to *output_csv*.

    Returns the total number of CSV data rows written.
    """
    input_path = Path(input_folder)
    pdf_files = sorted(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in '{input_folder}'")
        return 0

    print(f"Found {len(pdf_files)} PDF file(s) to process")

    client = build_client(location)
    processor_name = client.processor_path(project_id, location, processor_id)
    json_folder = Path(json_output_folder) if save_json and json_output_folder else None

    all_rows: List[dict] = []

    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name} …", end=" ", flush=True)
        try:
            document = process_document(client, processor_name, str(pdf_path))

            if save_json and json_folder is not None:
                json_path = save_document_json(document, json_folder, pdf_path.stem)
                print(f"(JSON saved → {json_path})", end=" ", flush=True)

            rows = document_to_rows(document, pdf_path.name)
            all_rows.extend(rows)
            print(f"→ {len(rows)} row(s)")

        except Exception:  # pylint: disable=broad-except
            import traceback
            print(f"ERROR processing {pdf_path.name}:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    write_csv(all_rows, output_csv)
    print(f"\nCSV written to '{output_csv}'  ({len(all_rows)} total row(s))")
    return len(all_rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process scanned PDFs with Google Document AI and write results to CSV."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input_folder",
        help="Directory containing the scanned PDF files to process.",
    )
    parser.add_argument(
        "output_csv",
        help="Path of the CSV file to create.",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Google Cloud project ID.",
    )
    parser.add_argument(
        "--location",
        default="us",
        help="Document AI API location (e.g. 'us' or 'eu').",
    )
    parser.add_argument(
        "--processor-id",
        required=True,
        help="Document AI processor ID.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save the raw Document AI JSON responses alongside the CSV.",
    )
    parser.add_argument(
        "--json-output-folder",
        default="json_output",
        help="Directory in which to store raw JSON responses.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    process_pdf_folder(
        input_folder=args.input_folder,
        output_csv=args.output_csv,
        project_id=args.project_id,
        location=args.location,
        processor_id=args.processor_id,
        save_json=args.save_json,
        json_output_folder=args.json_output_folder,
    )


if __name__ == "__main__":
    main()
