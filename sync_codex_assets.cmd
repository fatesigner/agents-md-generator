@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT=%~dp0scripts\sync_codex_assets.py"

where py.exe >nul 2>nul
if not errorlevel 1 (
  py.exe -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where python.exe >nul 2>nul
if not errorlevel 1 (
  python.exe "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

1>&2 echo sync_codex_assets: Python 3 runtime not found
exit /b 1
