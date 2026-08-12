@echo off
REM Knight Labs - see what changed on GitHub. READ ONLY.
REM
REM Fetches from origin and reports what is new. It does not commit, push,
REM merge, rebase, reset, or touch your working files in any way, so it is
REM always safe to run.
REM
REM Double-click this file, then tell Claude what it printed.

cd /d "%~dp0"

echo ============================================
echo   Knight Labs - what changed on GitHub?
echo ============================================
echo.

if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
if exist ".git\HEAD.lock"  del /f /q ".git\HEAD.lock"  >nul 2>&1

echo --- Your local commit ----------------------
git log --oneline -1
echo.

echo --- Fetching origin (read only) ------------
git fetch origin main
if errorlevel 1 (
    echo.
    echo Fetch failed - check your connection. Nothing was changed.
    pause
    exit /b 1
)
echo Done.
echo.

echo --- How far apart are you? -----------------
for /f "tokens=1,2" %%a in ('git rev-list --left-right --count origin/main...HEAD') do (
    echo   New on GitHub that you do NOT have : %%a
    echo   Yours not yet pushed to GitHub     : %%b
)
echo.

echo --- New commits on GitHub ------------------
git log --oneline --no-decorate HEAD..origin/main
git rev-list --count HEAD..origin/main > "%TEMP%\kl-incoming.txt" 2>nul
set /p INCOMING=<"%TEMP%\kl-incoming.txt"
del /f /q "%TEMP%\kl-incoming.txt" >nul 2>&1
if "%INCOMING%"=="0" echo   (nothing - you are up to date with GitHub)
echo.

echo --- Who wrote them -------------------------
if not "%INCOMING%"=="0" (
    git log --format="  %%h  %%an  %%ad  %%s" --date=short HEAD..origin/main
) else (
    echo   (n/a)
)
echo.

echo --- Which files they touch -----------------
if not "%INCOMING%"=="0" (
    git diff --stat HEAD origin/main
) else (
    echo   (n/a)
)
echo.

echo --- Your unpushed commits ------------------
git log --oneline --no-decorate origin/main..HEAD
echo.

echo --- Uncommitted local edits ----------------
git status --short
echo   (blank above means nothing uncommitted^)
echo.

echo ============================================
echo   Read-only check complete. Nothing changed.
echo ============================================
echo.
pause
