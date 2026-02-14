@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PYTHON=%SCRIPT_DIR%python\python.exe

if not exist "%PYTHON%" (
  echo ERROR: Portable Python not found at %PYTHON%
  pause
  exit /b 1
)

echo Starting LLM-in-a-Box Server...
echo.

REM Launch the launcher directly (shows output in this window)
"%PYTHON%" "%SCRIPT_DIR%app\launcher\launch.py"

REM If we get here, server exited
echo.
echo Server stopped.
pause