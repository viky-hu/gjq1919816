@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
    echo.
    echo Local startup failed. Review the message above.
    echo API and model settings belong in "%~dp0backend.local.env"
    echo Use "%~dp0backend.local.env.example" as the template.
    pause
)

endlocal
