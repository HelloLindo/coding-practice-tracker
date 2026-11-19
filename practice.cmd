@echo off
rem Windows launcher for the terminal archive flow. Requires Python 3.9+.
setlocal
cd /d "%~dp0"
where py >/dev/null 2>nul
if %errorlevel%==0 (
  py -3 scripts\archive.py %*
) else (
  python scripts\archive.py %*
)
if errorlevel 1 pause
