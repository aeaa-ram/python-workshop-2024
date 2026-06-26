@echo off
REM =====================================================================
REM  Double-click this file ONCE (on Windows) to build a standalone
REM  "PIO Document Sorter.exe" that needs no Python to run.
REM
REM  Requirement: Python from https://www.python.org/downloads/
REM  During install, tick "Add python.exe to PATH".
REM
REM  The finished program appears in the "dist" folder next to this file.
REM  You can then move "dist\PIO Document Sorter.exe" anywhere and
REM  double-click it.
REM
REM  NOTE: a Windows .exe can only be built on Windows - that is why one
REM  isn't shipped in the repo. This file does it for you in one click.
REM =====================================================================
cd /d "%~dp0"

echo Installing the build tool and PDF library (first time may take a minute)...
python -m pip install --upgrade pyinstaller pikepdf || goto :err

echo.
echo Building the EXE...
pyinstaller --onefile --windowed --name "PIO Document Sorter" "PIO_Document_Sorter.py" || goto :err

echo.
echo ============================================================
echo  Done. Your program is here:
echo      dist\PIO Document Sorter.exe
echo ============================================================
pause
exit /b 0

:err
echo.
echo Build failed - see the messages above.
pause
exit /b 1
