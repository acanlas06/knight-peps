@echo off
REM Knight Labs - one-time fix for the diverged branch.
REM
REM Our local commits and Alex's affiliate-promo commit changed adjacent lines
REM in the same long HTML lines, so git cannot auto-merge them. Our work is
REM purely mechanical (a domain rename plus this folder's sync script), so the
REM cleanest fix is to rebuild it on top of Alex's commit rather than
REM hand-resolving 24 conflict markers.
REM
REM Nothing is discarded: the old commits are kept on a backup branch.
REM
REM Double-click this file, then tell Claude it has finished.

cd /d "%~dp0"

echo ============================================
echo   Knight Labs - resolve diverged branch
echo ============================================
echo.

if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
if exist ".git\HEAD.lock"  del /f /q ".git\HEAD.lock"  >nul 2>&1

REM A half-finished rebase from an earlier attempt would block everything.
if exist ".git\rebase-merge" git rebase --abort >nul 2>&1
if exist ".git\rebase-apply" git rebase --abort >nul 2>&1

echo --- Current state --------------------------
git log --oneline -1
echo.

echo --- Fetching origin ------------------------
git fetch origin main
if errorlevel 1 (
    echo.
    echo Fetch failed. Nothing has been changed. Check your connection.
    pause
    exit /b 1
)
echo.

echo --- Saving a backup of local commits -------
git branch -f backup/pre-knightpeps HEAD
echo Saved as branch: backup/pre-knightpeps
git log --oneline -2 backup/pre-knightpeps
echo.

echo --- Rebuilding main on top of origin/main ---
git checkout -B main origin/main
if errorlevel 1 (
    echo.
    echo Could not move onto origin/main. Your commits are safe on
    echo backup/pre-knightpeps. Tell Claude what this printed.
    pause
    exit /b 1
)

REM Take the finished sync script wholesale from the backup. Using checkout
REM rather than a patch means there is no context to conflict with.
git checkout backup/pre-knightpeps -- git-sync.bat
if errorlevel 1 (
    echo.
    echo Could not restore git-sync.bat. Tell Claude.
    pause
    exit /b 1
)
echo Restored git-sync.bat from the backup branch.
echo.

echo ============================================
echo   Done. Now on origin/main plus git-sync.bat
echo ============================================
git log --oneline -1
echo.
echo Alex's affiliate work is now in your working copy, and the
echo domain rename has been intentionally left OFF for the moment.
echo.
echo NEXT: tell Claude "resolve done" so it can re-apply the rename,
echo then run git-sync.bat to commit and push.
echo.
pause
