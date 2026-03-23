# OCR2Ledger – Docker image
# =========================
# Works with Docker Desktop on Windows, macOS, and Linux.
#
# Build:
#   docker build -t ocr2ledger .
#
# Run (mounting a local folder of PDFs and writing the CSV to the host):
#   docker run --rm \
#     -v "%cd%\invoices:/data/invoices" \
#     -v "%cd%\output:/data/output" \
#     -v "%cd%\config.ini:/app/config.ini:ro" \
#     -v "%APPDATA%\gcloud:/root/.config/gcloud:ro" \
#     ocr2ledger
#
# On Linux / macOS replace %cd% with $(pwd) and %APPDATA% with ~/.config.
# You can also pass settings via environment variables instead of config.ini
# (see the ENTRYPOINT section below).

FROM python:3.11-slim

# Keeps Python from buffering stdout/stderr so logs appear immediately.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first (cached layer when only code changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY pipeline.py .
COPY config.ini.example .

# Default data directories (override by mounting volumes at these paths).
RUN mkdir -p /data/invoices /data/output /data/json_output

# Entrypoint: run the pipeline.
# Settings are read from /app/config.ini (mount your own or override via CLI).
# Environment variables for Google credentials:
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
#   (or mount the gcloud config directory as shown in the usage comment above)
ENTRYPOINT ["python", "pipeline.py"]

# Default arguments – used when the image is run without extra arguments.
# The user can override individual settings by appending CLI flags:
#   docker run ... ocr2ledger --project-id myproj --processor-id abc123 \
#       /data/invoices /data/output/results.csv
CMD ["--config", "/app/config.ini"]
