@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  INDmoney SIP Discovery - API key setup
echo ============================================================
echo.
echo This will ask for your API keys with hidden input.
echo They are written to .env in this folder and never printed.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-key.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo Setup did not complete. Read the message above.
) else (
    echo Setup complete. You can close this window.
)
echo.
pause
exit /b %EXITCODE%
