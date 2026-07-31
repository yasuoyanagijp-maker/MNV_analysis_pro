@echo off
REM =============================================================================
REM compute_caliber_u2_from_csv.bat — Windows helper for Caliber U2 CSV tool
REM Place next to ARIAKE_OCTA.exe in a release folder, or run from repo root.
REM =============================================================================
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%..\.."

if "%~1"=="" (
  echo Usage: %~nx0 INPUT.csv [-o OUTPUT.csv] [--inplace] [--size-class small^|large^|small_3mm]
  echo.
  echo Example:
  echo   %~nx0 MNV_batch.csv
  echo   %~nx0 MNV_batch.csv -o MNV_batch_u2.csv
  echo   %~nx0 MNV_batch.csv --inplace --size-class small_3mm
  exit /b 1
)

REM Prefer repo venv Python, then python on PATH
set "PY="
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" set "PY=%REPO_ROOT%\.venv\Scripts\python.exe"
if not defined PY if exist "%SCRIPT_DIR%python\python.exe" set "PY=%SCRIPT_DIR%python\python.exe"
if not defined PY set "PY=python"

"%PY%" "%REPO_ROOT%\tools\caliber_u2\compute_caliber_u2_from_csv.py" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo ERROR: exit code %EC%
  pause
)
exit /b %EC%
