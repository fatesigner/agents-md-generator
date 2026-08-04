@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT=%~dp0scripts\sync_codex_assets.py"
set "MANAGED_PYTHON=%USERPROFILE%\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe"
set "PYTHON="
set "SYNC_EXIT_CODE=1"

if not exist "%SCRIPT%" goto :missing_script
if defined SYNC_CODEX_ASSETS_PYTHON goto :try_override

:try_managed
set "PYTHON=%MANAGED_PYTHON%"
if not exist "%PYTHON%" goto :try_py_launcher
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :try_py_launcher
goto :run_python

:try_override
set "PYTHON=%SYNC_CODEX_ASSETS_PYTHON%"
if not exist "%PYTHON%" goto :invalid_override
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :invalid_override
goto :run_python

:try_py_launcher
where py.exe >nul 2>nul
if errorlevel 1 goto :try_python_executable
py.exe -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :try_python_executable
echo [INFO] Python runtime: py.exe -3
py.exe -3 "%SCRIPT%" %*
set "SYNC_EXIT_CODE=%ERRORLEVEL%"
goto :finish

:try_python_executable
where python.exe >nul 2>nul
if errorlevel 1 goto :missing_runtime
python.exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :missing_runtime
echo [INFO] Python runtime: python.exe
python.exe "%SCRIPT%" %*
set "SYNC_EXIT_CODE=%ERRORLEVEL%"
goto :finish

:run_python
echo [INFO] Python runtime: "%PYTHON%"
"%PYTHON%" "%SCRIPT%" %*
set "SYNC_EXIT_CODE=%ERRORLEVEL%"
goto :finish

:missing_script
1>&2 echo [ERROR] Sync implementation not found:
1>&2 echo         "%SCRIPT%"
goto :finish

:invalid_override
1>&2 echo [ERROR] SYNC_CODEX_ASSETS_PYTHON must point to a Python 3.11+ executable:
1>&2 echo         "%PYTHON%"
goto :finish

:missing_runtime
1>&2 echo [ERROR] Python 3.11 or later runtime not found.
1>&2 echo [CHECKED] "%MANAGED_PYTHON%", py.exe -3, and python.exe
1>&2 echo [ACTION] Install Python 3.11+ or set SYNC_CODEX_ASSETS_PYTHON to an approved python.exe path.
goto :finish

:finish
if "%SYNC_EXIT_CODE%"=="0" goto :success
1>&2 echo.
1>&2 echo [ERROR] sync_codex_assets failed with exit code %SYNC_EXIT_CODE%.
goto :wait

:success
echo.
echo [OK] sync_codex_assets finished successfully.

:wait
if /i "%SYNC_CODEX_ASSETS_NO_PAUSE%"=="1" goto :exit
echo.
pause

:exit
exit /b %SYNC_EXIT_CODE%
