@echo off
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python main.py
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py main.py
    exit /b %ERRORLEVEL%
)

echo Python not found in PATH. Install Python and try again.
pause
exit /b 1
