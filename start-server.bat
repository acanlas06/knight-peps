@echo off
REM Knight Labs local dev server launcher
REM Double-click this file to start the site at http://localhost:8123

cd /d "%~dp0"

echo ============================================
echo   Knight Labs dev server
echo   Open: http://localhost:8123
echo   Press Ctrl+C or close this window to stop
echo ============================================
echo.

where python >nul 2>&1
if %errorlevel%==0 (
    python server.py 8123
    goto :end
)

where py >nul 2>&1
if %errorlevel%==0 (
    py server.py 8123
    goto :end
)

echo Python was not found on your PATH.
echo Install Python from https://www.python.org/downloads/
echo and be sure to check "Add python.exe to PATH" during setup.
echo.

:end
echo.
echo Server stopped.
pause
