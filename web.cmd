@echo off
rem Windows launcher for the browser workspace. Requires Python 3.9+ (python.org or Microsoft Store).
setlocal
cd /d "%~dp0"
where py >/dev/null 2>nul
if %errorlevel%==0 (
  py -3 scripts\web_app.py %*
) else (
  python scripts\web_app.py %*
)
if errorlevel 1 pause
