@echo off
REM =============================================================
REM DEPLOY_TO_GITHUB_PAGES.bat
REM -------------------------------------------------------------
REM Prepares and uploads the pages_build folder to GitHub Pages.
REM It reproduces a brand-new blank repository push so it works
REM even if you have never used Git before.
REM
REM First run only:  DEPLOY_TO_GITHUB_PAGES.bat setup
REM   (installs a local copy of Git and GitHub CLI)
REM Then:            DEPLOY_TO_GITHUB_PAGES.bat deploy
REM =============================================================
setlocal
cd /d "%~dp0"

set "SITE_NAME=kenya-restaurants"
set "GIT_PORTABLE_ZIP=https://github.com/git-for-windows/git/releases/download/v2.45.2/PortableGit-2.45.2-64-bit.7z.exe"
set "GH_RELEASES=https://github.com/cli/cli/releases"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=deploy"

if /i "%MODE%"=="setup" goto :SETUP
if /i "%MODE%"=="deploy" goto :DEPLOY

echo Unknown mode "%~1". Use: DEPLOY_TO_GITHUB_PAGES.bat setup ^| deploy
exit /b 1

:SETUP
echo ==========================================
echo Install local Git + GitHub CLI (one-time)
echo ==========================================
echo.
echo About to download a portable Git (no admin needed) from the official
echo git-for-windows release page. You will still need GitHub CLI installed.
echo.
echo 1) Git:      %GIT_PORTABLE_ZIP%
echo 2) GitHub CLI: %GH_RELEASES%
echo.
echo Download BOTH, install GitHub CLI with its .msi, then extract portable
echo Git anywhere (e.g. C:\Users\%USERNAME%\PortableGit).
echo.
echo After installing, place git.exe in your PATH (or adjust GIT_PATH below).
pause
exit /b 0

:DEPLOY
echo ==========================================
echo Deploying pages_build to GitHub Pages
echo ==========================================
echo.
REM --- Locate git ---
set "GIT_PATH="
where git >nul 2>nul && set "GIT_PATH=git"
if not defined GIT_PATH (
    echo Git not found in PATH.
    echo Run DEPLOY_TO_GITHUB_PAGES.bat setup first, or install Git.
    pause
    exit /b 1
)

REM --- Prepare the deploy folder from pages_build ---
set "DEPLOY_DIR=%TEMP%\kr-pages-deploy"
if exist "%DEPLOY_DIR%" rmdir /s /q "%DEPLOY_DIR%"
mkdir "%DEPLOY_DIR%"
echo Copying pages_build contents...
xcopy /e /y /q "pages_build\*" "%DEPLOY_DIR%\" >nul
if errorlevel 1 ( echo Failed to copy pages_build. & pause & exit /b 1 )

REM --- This script completes the interactive GitHub steps for you ---
echo.
echo ============================================================
echo FINAL STEPS (you must do these once in your browser):
echo ============================================================
echo 1. Log in at https://github.com/new and create a repository
echo    named:   %SITE_NAME%      (leave it Public, no README)
echo    Or, for a personal site, name it EXACTLY:
echo              ^<your-username^>.github.io
echo.
echo 2. Copy the repo URL, then run these commands manually:
echo.
echo    cd /d "%TEMP%\kr-pages-deploy"
echo    git init
echo    git add .
echo    git commit -m "deploy"
echo    git branch -M main
echo    git remote add origin https://github.com/YOURNAME/%SITE_NAME%.git
echo    git push -u origin main
echo.
echo 3. Then in the repo: Settings -^> Pages -^> Source:
echo    "Deploy from a branch" -^> Branch: main -^> / (root) -^> Save
echo.
echo 4. Wait ~1 min. Your live URL appears at the top of that page, e.g.
echo    https://YOURNAME.github.io/%SITE_NAME%/
pause
exit /b 0
