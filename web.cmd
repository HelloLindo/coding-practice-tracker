@echo off
rem Windows launcher for the browser workspace. Requires Python 3.11+ (python.org or Microsoft Store).
setlocal
cd /d "%~dp0"
rem The block is parsed at once, so an update that replaces this file cannot
rem change the commands of a running launcher.
(
  where py >nul 2>nul
  if not errorlevel 1 (py -3 scripts\web_app.py %*) else (python scripts\web_app.py %*)
  if errorlevel 1 pause
  exit /b
)
