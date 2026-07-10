@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed.
    echo Please install it from: https://www.python.org/downloads/
    echo During install, tick "Add python.exe to PATH".
    pause
    exit /b 1
)

python "PIO_Document_Sorter.py" %*

if errorlevel 1 (
    echo.
    echo Something went wrong - see the messages above.
    pause
)
