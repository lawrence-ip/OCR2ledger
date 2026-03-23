# OCR2ledger

A command-line pipeline that reads a folder of scanned PDFs, uploads each one
to **Google Document AI** for OCR / structured-data extraction, saves the raw
JSON responses, and writes all results to a flat **CSV** file.

---

## Features

| Capability | Details |
|---|---|
| Batch PDF ingestion | Processes every `*.pdf` in a given directory |
| Google Document AI | Supports any processor type (invoice, form, OCR, …) |
| JSON archiving | Optionally saves the raw API response for each PDF |
| CSV output | One row per extracted entity / form field / table cell |
| Error resilience | Logs errors per file and continues processing the rest |

---

## Prerequisites

1. **Python 3.9+**
2. A **Google Cloud project** with the Document AI API enabled
3. A **Document AI processor** (create one at
   [console.cloud.google.com/ai/document-ai](https://console.cloud.google.com/ai/document-ai))
4. Application Default Credentials configured locally:

   ```bash
   gcloud auth application-default login
   ```

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Usage

```
python pipeline.py <input_folder> <output_csv> \
    --project-id  <GCP_PROJECT_ID>             \
    --processor-id <PROCESSOR_ID>              \
    [--location us]                            \
    [--save-json]                              \
    [--json-output-folder json_output]
```

### Required arguments

| Argument | Description |
|---|---|
| `input_folder` | Directory containing the scanned PDF files |
| `output_csv` | Path of the CSV file to create |
| `--project-id` | Google Cloud project ID |
| `--processor-id` | Document AI processor ID |

### Optional arguments

| Argument | Default | Description |
|---|---|---|
| `--location` | `us` | API location (`us` or `eu`) |
| `--save-json` | off | Save raw JSON responses to disk |
| `--json-output-folder` | `json_output` | Directory for raw JSON files |

### Example

```bash
python pipeline.py ./invoices invoices.csv \
    --project-id my-gcp-project            \
    --processor-id 1a2b3c4d5e6f             \
    --save-json
```

This will:
1. Find all `*.pdf` files inside `./invoices/`
2. Upload each one to Document AI and receive structured JSON
3. Save each JSON response to `./json_output/<stem>.json`
4. Parse every response and write the results to `invoices.csv`

---

## CSV output format

Each row represents one extracted data point:

| Column | Description |
|---|---|
| `source_file` | Name of the originating PDF |
| `type` | `entity`, `form_field`, `table`, or `text` (raw fallback) |
| `key` | Field name / entity type / table cell key |
| `value` | Extracted text value |
| `normalized_value` | Normalised value when provided by the processor |
| `confidence` | Model confidence score (0–1) |
| `page` | 1-based page number |

---

## Running tests

```bash
pip install pytest
pytest tests/
```
