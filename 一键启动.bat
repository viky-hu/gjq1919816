@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
    echo.
    echo Local startup failed. Review the message above.
    pause
)

endlocal
