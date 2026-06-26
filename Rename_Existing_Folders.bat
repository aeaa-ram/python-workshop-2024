@echo off
REM =====================================================================
REM  ONE-TIME clean-up: renames an existing ProjectWise folder tree so the
REM  numbers match the PIO Document Sorter scheme.
REM
REM  Double-click this file. It opens a folder picker - choose the folder
REM  that contains "400 ..." and "401 ...".
REM
REM  It then shows a PREVIEW of every folder it would rename and changes
REM  NOTHING until you click "APPLY renames" in that window. Files are never
REM  touched - only folder names. A full report is saved next to this file.
REM
REM  Requirement: Python from https://www.python.org/downloads/
REM  (tick "Add python.exe to PATH" during install).
REM =====================================================================
cd /d "%~dp0"

python "PIO_Folder_Renamer.py" %*

if errorlevel 1 (
    echo.
    echo Something went wrong - see the messages above.
    pause
)
