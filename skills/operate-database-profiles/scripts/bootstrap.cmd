@echo off
setlocal EnableExtensions DisableDelayedExpansion

call "%~dp0dbctl.cmd" bootstrap %*
exit /b %ERRORLEVEL%
