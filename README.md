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
| CSV output | One ledger row per document (date, description, amount) |
| Error resilience | Logs errors per file and continues processing the rest |
| Config file | All settings can be stored in `config.ini` – no CLI flags required |
| Docker container | Run on any Windows/macOS/Linux machine with Docker Desktop |
| Windows executable | Build a self-contained `.exe` with PyInstaller |

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

### Option 1 – Config file (recommended for desktop use)

1. Copy the example config file and fill in your values:

   ```bash
   # Windows
   copy config.ini.example config.ini

   # Linux / macOS
   cp config.ini.example config.ini
   ```

2. Edit `config.ini`:

   ```ini
   [ocr2ledger]
   input_folder  = ./invoices
   output_csv    = output.csv
   project_id    = my-gcp-project
   processor_id  = 1a2b3c4d5e6f
   location      = us
   save_json     = false
   json_output_folder = json_output
   ```

3. Run the pipeline (it auto-detects `config.ini` in the current directory):

   ```bash
   python pipeline.py
   ```

   Or point at a custom config file:

   ```bash
   python pipeline.py --config /path/to/myconfig.ini
   ```

### Option 2 – CLI arguments

```
python pipeline.py <input_folder> <output_csv> \
    --project-id  <GCP_PROJECT_ID>             \
    --processor-id <PROCESSOR_ID>              \
    [--location us]                            \
    [--save-json]                              \
    [--json-output-folder json_output]
```

CLI arguments always override values from a config file when both are provided.

#### Required arguments

| Argument | Description |
|---|---|
| `input_folder` | Directory containing the scanned PDF files |
| `output_csv` | Path of the CSV file to create |
| `--project-id` | Google Cloud project ID |
| `--processor-id` | Document AI processor ID |

#### Optional arguments

| Argument | Default | Description |
|---|---|---|
| `--config` | *(auto-detect `config.ini`)* | Path to a config file |
| `--location` | `us` | API location (`us` or `eu`) |
| `--save-json` | off | Save raw JSON responses to disk |
| `--json-output-folder` | `json_output` | Directory for raw JSON files |

#### Example

```bash
python pipeline.py ./invoices invoices.csv \
    --project-id my-gcp-project            \
    --processor-id 1a2b3c4d5e6f             \
    --save-json
```

---

## Docker container (Windows / macOS / Linux)

Docker lets you run OCR2Ledger without installing Python – ideal for
distributing the tool to multiple Windows devices via Docker Desktop.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed

### Quick start

1. Copy and edit the config file:

   ```bash
   copy config.ini.example config.ini   # Windows
   ```

2. Create the folders Docker will mount:

   ```
   invoices\     ← put your PDF files here
   output\       ← CSV will be written here
   ```

3. Build and run:

   ```bash
   docker compose up --build
   ```

   On subsequent runs (no code changes):

   ```bash
   docker compose up
   ```

### Manual Docker commands

```bash
# Build
docker build -t ocr2ledger .

# Run (Windows Command Prompt)
docker run --rm ^
  -v "%cd%\invoices:/data/invoices:ro" ^
  -v "%cd%\output:/data/output" ^
  -v "%cd%\config.ini:/app/config.ini:ro" ^
  -v "%APPDATA%\gcloud:/root/.config/gcloud:ro" ^
  ocr2ledger

# Run (PowerShell)
docker run --rm `
  -v "${PWD}\invoices:/data/invoices:ro" `
  -v "${PWD}\output:/data/output" `
  -v "${PWD}\config.ini:/app/config.ini:ro" `
  -v "$env:APPDATA\gcloud:/root/.config/gcloud:ro" `
  ocr2ledger
```

### Google credentials inside Docker

Either mount the `gcloud` config directory (Application Default Credentials,
shown above) **or** pass a service-account JSON key file:

```bash
docker run --rm \
  -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-key \
  -v /path/to/service-account-key.json:/run/secrets/gcp-key:ro \
  ... \
  ocr2ledger
```

---

## Windows executable (PyInstaller)

Build a standalone `.exe` that runs without Python or Docker.

### Prerequisites

```bash
pip install pyinstaller
```

### Build

```bat
# Windows
build_exe.bat

# Linux / macOS
chmod +x build_exe.sh
./build_exe.sh
```

The executable is placed in `dist\ocr2ledger\ocr2ledger.exe`.

### Distribute

Copy the **entire** `dist\ocr2ledger\` folder to the target Windows machine.
Place `config.ini` (with your settings) in the same folder, then run:

```bat
cd dist\ocr2ledger
ocr2ledger.exe
```

Or pass CLI arguments directly:

```bat
ocr2ledger.exe --config C:\Users\Me\Documents\myconfig.ini
ocr2ledger.exe C:\invoices C:\output\results.csv ^
    --project-id my-gcp-project --processor-id 1a2b3c4d5e6f
```

> **Note:** Google credentials must still be configured on the target machine.
> Run `gcloud auth application-default login` once, or set
> `GOOGLE_APPLICATION_CREDENTIALS` to the path of a service-account key file.

---

## CSV output format

Each row represents one document:

| Column | Description |
|---|---|
| `source_file` | Name of the originating PDF |
| `date` | Extracted transaction / invoice date |
| `description` | Vendor, merchant, or item description |
| `amount` | Total amount / amount due |

---

## Running tests

```bash
pip install pytest
pytest tests/
```

