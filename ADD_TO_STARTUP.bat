@echo off
echo ==========================================
echo Kenya Restaurant Finder - Add to Startup
echo ==========================================
echo.

:: Create a shortcut in the Startup folder
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_FOLDER%\Kenya Restaurant Finder.lnk"

:: Create the shortcut using PowerShell
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '\"c:\Users\PC\OneDrive\Desktop\restaurant website\server.py\"'; $Shortcut.WorkingDirectory = 'c:\Users\PC\OneDrive\Desktop\restaurant website'; $Shortcut.IconLocation = 'python.exe,0'; $Shortcut.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo SUCCESS! The app will now start automatically when you log into Windows.
    echo.
    echo To remove it later, delete this file:
    echo %SHORTCUT%
) else (
    echo.
    echo Failed to create shortcut.
)

echo.
pause