@echo off
rem ============================================================
rem  showcase-kit - turn any codebase into a portfolio site
rem  Double-click this file to open the studio.
rem ============================================================
cd /d "%~dp0"
title showcase-kit  -  studio  (port 8778)

rem --- find a Python interpreter -----------------------------
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
  echo.
  echo   Python 3 was not found on your PATH.
  echo   Install it from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

echo.
echo   ^<^>   showcase-kit  studio
echo   ------------------------------------------
echo   Opening   http://127.0.0.1:8778
echo   Close this window to stop the server.
echo.

%PY% kit_web.py
if errorlevel 1 (
  echo.
  echo   The server stopped. If it never started, port 8778
  echo   may already be in use ^(another studio window open?^).
  echo.
  pause
)
