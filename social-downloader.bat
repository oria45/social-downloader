@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PORT=8765"

rem --- 1. winget (needed to install Python/Node/ffmpeg if they're missing) ---
where winget >nul 2>&1
if errorlevel 1 (
  echo ERROR: winget was not found on this PC.
  echo Please install Python, Node.js, and ffmpeg manually, then re-run this file:
  echo   Python:  https://www.python.org/downloads/
  echo   Node.js: https://nodejs.org/
  echo   ffmpeg:  https://www.gyan.dev/ffmpeg/builds/
  pause
  exit /b 1
)

set "NEED_RESTART=0"

rem --- 2. Python 3 ---
where python >nul 2>&1
if errorlevel 1 (
  echo Installing Python...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
  where python >nul 2>&1
  if errorlevel 1 set "NEED_RESTART=1"
)

rem --- 3. Node.js / npm ---
where npm >nul 2>&1
if errorlevel 1 (
  echo Installing Node.js...
  winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
  where npm >nul 2>&1
  if errorlevel 1 set "NEED_RESTART=1"
)

rem --- 4. ffmpeg (needed by yt-dlp to merge some video+audio streams) ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo Installing ffmpeg...
  winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
  where ffmpeg >nul 2>&1
  if errorlevel 1 set "NEED_RESTART=1"
)

if "!NEED_RESTART!"=="1" (
  echo.
  echo Install complete. Windows needs a fresh window to pick up the new PATH.
  echo Please close this window and double-click social-downloader.bat again.
  pause
  exit /b 0
)

rem --- 5. Python virtualenv + backend dependencies ---
set "VENV=backend\venv"
if not exist "%VENV%\Scripts\python.exe" (
  python -m venv "%VENV%"
)

set "REQ_HASH_FILE=%VENV%\.requirements.sha256"
set "CURRENT_HASH="
for /f "skip=1 tokens=* delims=" %%h in ('certutil -hashfile backend\requirements.txt SHA256') do (
  if not defined CURRENT_HASH set "CURRENT_HASH=%%h"
)
set "CURRENT_HASH=!CURRENT_HASH: =!"

set "STORED_HASH="
if exist "!REQ_HASH_FILE!" set /p STORED_HASH=<"!REQ_HASH_FILE!"

if not "!CURRENT_HASH!"=="!STORED_HASH!" (
  echo Installing backend dependencies ^(fastapi, yt-dlp, gallery-dl, ...^)...
  "%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip
  "%VENV%\Scripts\python.exe" -m pip install -q -r backend\requirements.txt
  >"!REQ_HASH_FILE!" echo !CURRENT_HASH!
)

rem --- 6. Frontend build (only if missing or source changed) ---
set "NEEDS_BUILD=0"
if not exist "frontend\dist\index.html" (
  set "NEEDS_BUILD=1"
) else (
  powershell -NoProfile -Command "$dist = 'frontend/dist/index.html'; $distTime = (Get-Item $dist).LastWriteTime; $newer = Get-ChildItem -Recurse -File 'frontend/src' | Where-Object { $_.LastWriteTime -gt $distTime }; if ($newer) { exit 1 } else { exit 0 }"
  if errorlevel 1 set "NEEDS_BUILD=1"
)

if "!NEEDS_BUILD!"=="1" (
  echo Building frontend...
  pushd frontend
  call npm install && call npm run build
  popd
)

rem --- 7. Run ---
echo Starting server on http://localhost:%PORT% ...
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 1; Start-Process 'http://localhost:%PORT%'"
"%VENV%\Scripts\uvicorn.exe" app.main:app --app-dir backend --host 127.0.0.1 --port %PORT%
