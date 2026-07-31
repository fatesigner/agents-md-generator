@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT=%~dp0scripts\sync_codex_assets.py"
set "PYTHON=%USERPROFILE%\Programs\1_develop\python-tools\.runtime\.venv\Scripts\python.exe"
set "SYNC_EXIT_CODE=1"

if not exist "%SCRIPT%" goto :missing_script
if not exist "%PYTHON%" goto :missing_runtime

"%PYTHON%" "%SCRIPT%" %*
set "SYNC_EXIT_CODE=%ERRORLEVEL%"
goto :finish

:missing_script
1>&2 echo [ERROR] Sync implementation not found:
1>&2 echo         "%SCRIPT%"
goto :finish

:missing_runtime
1>&2 echo [ERROR] Dedicated Python runtime not found:
1>&2 echo         "%PYTHON%"
1>&2 echo [ACTION] Install or restore the python-tools core runtime, then run this script again.
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
