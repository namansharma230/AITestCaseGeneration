@echo off
echo ════════════════════════════════════════════════════════
echo   Test Case Automator — Local App Launcher
echo ════════════════════════════════════════════════════════
echo.
echo  Starting the application...
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
