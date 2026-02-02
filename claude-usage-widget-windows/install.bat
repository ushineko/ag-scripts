@echo off
REM Claude Usage Widget for Windows - Installer
REM Installs dependencies and creates a startup shortcut

echo Claude Usage Widget Installer
echo ==============================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully.
echo.

REM Ask about startup
set /p ADD_STARTUP="Add to Windows startup? (y/n): "
if /i "%ADD_STARTUP%"=="y" (
    REM Create startup shortcut using PowerShell
    echo Creating startup shortcut...
    powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Claude Usage Widget.lnk'); $Shortcut.TargetPath = 'pythonw'; $Shortcut.Arguments = '-m src.main'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = 'Claude Usage Widget'; $Shortcut.Save()"
    if errorlevel 1 (
        echo WARNING: Failed to create startup shortcut.
    ) else (
        echo Startup shortcut created.
    )
)

echo.
echo ==============================
echo Installation complete!
echo.
echo To run manually:
echo   cd "%SCRIPT_DIR%"
echo   python -m src.main
echo.
echo Or use pythonw to run without console:
echo   pythonw -m src.main
echo.
pause
