@echo off
REM Knight Labs — commit and push in one step.
REM
REM Double-click this file to stage everything, commit, and push to GitHub.
REM It runs on Windows with your own git credentials, so it can push (Claude's
REM sandbox has no network access to GitHub) and it can clean up the stale
REM lock files that Claude's sandbox cannot delete.

cd /d "%~dp0"

echo ============================================
echo   Knight Labs - commit and push
echo ============================================
echo.

REM Claude's sandbox cannot delete files, so git's own lock cleanup fails there
REM and leaves these behind. Clearing them is safe: they are empty leftovers.
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1 && echo Cleared stale .git\index.lock
if exist ".git\HEAD.lock"  del /f /q ".git\HEAD.lock"  >nul 2>&1 && echo Cleared stale .git\HEAD.lock

REM Stray probe files from sandbox permission checks.
if exist ".git\probe-test" del /f /q ".git\probe-test" >nul 2>&1
if exist "probe2" del /f /q "probe2" >nul 2>&1

echo.
echo --- Changes to be committed -----------------
git add -A
git status --short
echo --------------------------------------------
echo.

REM Nothing staged means nothing to do.
git diff --cached --quiet
if %errorlevel%==0 (
    echo No changes to commit. Nothing to push.
    echo.
    pause
    exit /b 0
)

REM Use the prepared message if Claude left one, otherwise ask.
set MSGFILE=..\knight-peps-commit-msg.txt
if exist "%MSGFILE%" (
    echo Using prepared commit message from %MSGFILE%
    echo.
    git commit -F "%MSGFILE%"
) else (
    set /p MSG="Commit message: "
    if "%MSG%"=="" (
        echo No message given - aborting.
        pause
        exit /b 1
    )
    git commit -m "%MSG%"
)

if %errorlevel% neq 0 (
    echo.
    echo Commit failed. Nothing was pushed.
    pause
    exit /b 1
)

echo.
echo --- Pushing --------------------------------
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo Push failed. The commit is saved locally - you can retry the push.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done. Commit pushed to origin/main.
echo ============================================
git log --oneline -1
echo.
pause
