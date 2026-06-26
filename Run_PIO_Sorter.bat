@echo off
REM =====================================================================
REM  Double-click this file to RUN the PIO Document Sorter.
REM
REM  Requirement: Python from https://www.python.org/downloads/
REM  During install, tick "Add python.exe to PATH".
REM
REM  No building needed - this just runs the script and opens the two
REM  folder-picker windows.
REM =====================================================================
cd /d "%~dp0"

REM Install the PDF library the first time only (skipped if already present,
REM and the tool still runs - just without merging - if this can't install).
python -c "import pikepdf" 2>nul || python -m pip install pikepdf

python "PIO_Document_Sorter.py" %*

if errorlevel 1 (
    echo.
    echo Something went wrong - see the messages above.
    pause
)
