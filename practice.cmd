@echo off
rem Windows launcher for the terminal archive flow. Requires Python 3.9+.
setlocal
cd /d "%~dp0"
rem The block is parsed at once, so an update that replaces this file cannot
rem change the commands of a running launcher.
(
  where py >nul 2>nul
  if not errorlevel 1 (py -3 scripts\archive.py %*) else (python scripts\archive.py %*)
  if errorlevel 1 pause
  exit /b
)
