@echo off
setlocal enabledelayedexpansion

echo ════════════════════════════════════════
echo   Test Case Automator - Edge Launcher
echo ════════════════════════════════════════
echo.

REM Jira URL to open automatically so you can log in immediately
set "JIRA_URL=https://astrogo.atlassian.net"

REM Kill any Edge process already using port 9222 to avoid conflicts
echo  Checking for existing Edge debug sessions...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":9222" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo  Done. Launching fresh Edge with remote debugging...
echo.

REM Try default Edge installation path (Program Files x86)
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug" --new-window "!JIRA_URL!"
    goto :success
)

REM Try alternate path (Program Files)
if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug" --new-window "!JIRA_URL!"
    goto :success
)

echo ERROR: Edge not found in default locations.
echo Find your Edge path by running: where msedge
echo Then update this file with the correct path.
pause
exit /b 1

:success
echo  Edge is launching with remote debugging on port 9222.
echo  Opening Jira: !JIRA_URL!
echo.
echo ════════════════════════════════════════
echo  NEXT STEPS:
echo   1. Edge will open directly to Jira
echo   2. Log in to your Jira account
echo   3. Leave this Edge window OPEN
echo   4. Run run_app.bat to start the automator
echo ════════════════════════════════════════
echo.
pause
endlocal