@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"

if defined DBCTL_PYTHON (
  if not exist "%DBCTL_PYTHON%" (
    1>&2 echo dbctl: DBCTL_PYTHON does not exist
    exit /b 1
  )
  "%DBCTL_PYTHON%" "%SCRIPT_DIR%dbctl.py" %*
  exit /b %ERRORLEVEL%
)

where py.exe >nul 2>nul
if not errorlevel 1 (
  py.exe -3 "%SCRIPT_DIR%dbctl.py" %*
  exit /b %ERRORLEVEL%
)

where python.exe >nul 2>nul
if not errorlevel 1 (
  python.exe "%SCRIPT_DIR%dbctl.py" %*
  exit /b %ERRORLEVEL%
)

1>&2 echo dbctl: Python 3 runtime not found; set DBCTL_PYTHON to an approved absolute path
exit /b 1
