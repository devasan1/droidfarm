@echo off
REM =============================================================
REM  DroidFarm  -  single-click launcher
REM
REM  Double-click this file. First run:
REM    - checks / installs Python 3.11, Node 20, Git, ADB, LDPlayer 9
REM    - sets up a Python venv, installs the backend
REM    - builds the frontend
REM    - starts the desktop app
REM  Subsequent runs skip installation and launch in ~3 seconds.
REM
REM  Anything this script does manually, it also writes to
REM    %LOCALAPPDATA%\DroidFarm\bootstrap.log
REM  so you can inspect what happened.
REM =============================================================
setlocal enableextensions

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

REM Relaunch ourselves in PowerShell so we get a real scripting env.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\bootstrap.ps1" %*

REM Keep the console window open if the launcher errored so the user can
REM read the message.
if errorlevel 1 (
  echo.
  echo DroidFarm failed to start. Press any key to close.
  pause >nul
)
endlocal
