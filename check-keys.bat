@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo  INDmoney SIP Discovery - API key check
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-keys.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo One or more keys did not validate. Read the message above.
) else (
    echo Key check complete.
)
echo.
pause
exit /b %EXITCODE%
