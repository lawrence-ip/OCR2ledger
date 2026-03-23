#!/usr/bin/env bash
# build_exe.sh – Build a standalone Windows executable for OCR2Ledger
#               using PyInstaller (run from Linux / macOS / WSL).
# =====================================================================
# Prerequisites (run once):
#   pip install pyinstaller
#
# Usage:
#   chmod +x build_exe.sh
#   ./build_exe.sh
#
# The resulting executable is placed in:
#   dist/ocr2ledger/ocr2ledger  (or  dist/ocr2ledger/ocr2ledger.exe
#                                    when cross-compiled for Windows)
#
# To run it:
#   ./dist/ocr2ledger/ocr2ledger --config config.ini
#   ./dist/ocr2ledger/ocr2ledger invoices output.csv \
#       --project-id my-gcp-project --processor-id 1a2b3c4d5e6f

set -euo pipefail

echo
echo "============================================================"
echo " OCR2Ledger – executable builder"
echo "============================================================"
echo

if ! command -v pyinstaller &>/dev/null; then
    echo "ERROR: PyInstaller is not installed."
    echo "       Run:  pip install pyinstaller"
    exit 1
fi

pyinstaller \
    --onedir \
    --name ocr2ledger \
    --console \
    --clean \
    pipeline.py

echo
echo "============================================================"
echo " Build succeeded!"
echo " Executable:  dist/ocr2ledger/ocr2ledger"
echo "============================================================"
echo
echo "Copy the entire  dist/ocr2ledger/  directory to the target machine."
echo "Place your  config.ini  alongside the executable before running."
echo
