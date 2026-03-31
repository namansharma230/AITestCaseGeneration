@echo off
echo ════════════════════════════════════════════════════════
echo   Test Case Automator — PyInstaller Build Script
echo ════════════════════════════════════════════════════════
echo.
echo  This will build a standalone Windows .exe
echo  Output: dist\TestCaseAutomator.exe
echo.

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  Virtual environment activated.
) else (
    echo  No .venv found — using global Python.
)

echo.
echo  Checking PyInstaller...
python -m pip install pyinstaller --quiet

echo  Building...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "TestCaseAutomator" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import=flask ^
    --hidden-import=flask.json ^
    --hidden-import=jinja2 ^
    --hidden-import=selenium ^
    --hidden-import=selenium.webdriver.edge.service ^
    --hidden-import=selenium.webdriver.edge.options ^
    --hidden-import=selenium.webdriver.common.by ^
    --hidden-import=openpyxl ^
    --hidden-import=openpyxl.styles ^
    --hidden-import=bs4 ^
    --hidden-import=lxml ^
    --hidden-import=openai ^
    --hidden-import=dotenv ^
    --hidden-import=groq ^
    --collect-all flask ^
    --collect-all jinja2 ^
    --collect-submodules selenium ^
    launcher.py

echo.
if exist "dist\TestCaseAutomator.exe" (
    echo ════════════════════════════════════════════════════════
    echo   BUILD SUCCESSFUL!
    echo.
    echo   Executable: dist\TestCaseAutomator.exe
    echo.
    echo   IMPORTANT — Before distributing the .exe:
    echo   1. Copy your .env file next to the .exe
    echo      (it contains your GROQ_API_KEY)
    echo   2. Users must still run start_edge.bat and log into
    echo      Jira/Confluence before launching the .exe
    echo ════════════════════════════════════════════════════════
) else (
    echo   BUILD FAILED — check the output above for errors.
)

echo.
pause
