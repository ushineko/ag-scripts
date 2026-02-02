@echo off
REM Claude Usage Widget for Windows - Uninstaller
REM Removes startup shortcut and config files

echo Claude Usage Widget Uninstaller
echo ================================
echo.

REM Remove startup shortcut
set "STARTUP_SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Claude Usage Widget.lnk"
if exist "%STARTUP_SHORTCUT%" (
    echo Removing startup shortcut...
    del "%STARTUP_SHORTCUT%"
    echo Startup shortcut removed.
) else (
    echo No startup shortcut found.
)

echo.

REM Ask about config files
set "CONFIG_DIR=%APPDATA%\claude-usage-widget"
if exist "%CONFIG_DIR%" (
    set /p REMOVE_CONFIG="Remove configuration files? (y/n): "
    if /i "%REMOVE_CONFIG%"=="y" (
        echo Removing configuration directory...
        rmdir /s /q "%CONFIG_DIR%"
        echo Configuration files removed.
    ) else (
        echo Configuration files preserved at:
        echo   %CONFIG_DIR%
    )
) else (
    echo No configuration files found.
)

echo.
echo ================================
echo Uninstallation complete.
echo.
echo Note: Python dependencies were not removed.
echo To remove them manually:
echo   pip uninstall pystray customtkinter Pillow
echo.
pause
