@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_windows.ps1" %*
echo.
pause
exit /b %ERRORLEVEL%
