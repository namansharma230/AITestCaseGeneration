@echo off
echo ════════════════════════════════════════════════════════
echo   Test Case Automator — Local App Launcher
echo ════════════════════════════════════════════════════════
echo.

REM ── Step 1: Ensure Edge is running with remote debugging ─────────────────
echo  Step 1: Checking if Edge debug session is active (port 9222)...
netstat -aon | findstr ":9222" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  Edge is NOT running on port 9222. Starting it now...
    echo.
    set JIRA_URL=https://astrogo.atlassian.net

    REM Try Program Files x86 first
    if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
        start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug" "%JIRA_URL%"
        goto :edge_started
    )
    REM Try Program Files
    if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
        start "" "C:\Program Files\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug" "%JIRA_URL%"
        goto :edge_started
    )
    echo  WARNING: Could not find msedge.exe to auto-start Edge.
    echo  Please run start_edge.bat manually, log in to Jira, then re-run this script.
    pause
    exit /b 1

    :edge_started
    echo  Edge launched. Waiting 5 seconds for it to initialise...
    timeout /t 5 /nobreak >nul
    echo  NOTE: If you are not logged in to Jira yet, log in now
    echo        before generating test cases in the app.
    echo.
) else (
    echo  Edge debug session already active on port 9222. Good to go!
    echo.
)

REM ── Step 2: Start the Flask application ──────────────────────────────────
echo  Step 2: Starting the Test Case Automator...
echo  Your browser will open automatically at http://localhost:5000
echo.
echo  IMPORTANT: Keep this window open while using the app.
echo             Close it (or press Ctrl+C) to stop the server.
echo.
echo ════════════════════════════════════════════════════════
echo.

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Launch the app
python launcher.py

echo.
echo Application stopped.
pause
