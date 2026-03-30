@echo off
echo ════════════════════════════════════════
echo   Test Case Automator - Edge Launcher
echo ════════════════════════════════════════
echo.

REM Try default Edge installation path
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug"
    goto :success
)

REM Try alternate path
if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug"
    goto :success
)

echo ERROR: Edge not found in default locations.
echo Find your Edge path by running: where msedge
echo Then update this file with the correct path.
pause
exit /b 1

:success
echo Edge is launching with remote debugging on port 9222.
echo.
echo NEXT STEPS:
echo  1. Wait for Edge to open
echo  2. Log in to Jira at https://astrogo.atlassian.net
echo  3. Leave this Edge window open
echo  4. Run your script in a separate Command Prompt
echo.
pause