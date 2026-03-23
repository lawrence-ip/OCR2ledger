@echo off
REM build_exe.bat – Build a standalone Windows executable for OCR2Ledger
REM ======================================================================
REM Prerequisites (run once):
REM   pip install pyinstaller
REM
REM Usage:
REM   build_exe.bat
REM
REM The resulting executable is placed in:
REM   dist\ocr2ledger\ocr2ledger.exe
REM
REM To run it:
REM   dist\ocr2ledger\ocr2ledger.exe --config config.ini
REM   dist\ocr2ledger\ocr2ledger.exe invoices output.csv ^
REM       --project-id my-gcp-project --processor-id 1a2b3c4d5e6f

echo.
echo ============================================================
echo  OCR2Ledger – Windows executable builder
echo ============================================================
echo.

REM Check that PyInstaller is available.
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed.
    echo        Run:  pip install pyinstaller
    exit /b 1
)

REM Build the executable.
pyinstaller ^
    --onedir ^
    --name ocr2ledger ^
    --console ^
    --clean ^
    pipeline.py

if errorlevel 1 (
    echo.
    echo Build FAILED. See output above for details.
    exit /b 1
)

echo.
echo ============================================================
echo  Build succeeded!
echo  Executable:  dist\ocr2ledger\ocr2ledger.exe
echo ============================================================
echo.
echo Copy the entire  dist\ocr2ledger\  folder to the target machine.
echo Place your  config.ini  alongside the executable before running.
echo.
