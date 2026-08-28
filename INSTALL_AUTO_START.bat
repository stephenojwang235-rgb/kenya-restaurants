@echo off
echo ==========================================
echo Kenya Restaurant Finder - Auto-Start Setup
echo ==========================================
echo.
echo This will make the app start automatically when you log into Windows.
echo.
pause

:: Create a scheduled task that runs on user logon
schtasks /create /tn "KenyaRestaurantFinder" /tr "python \"c:\Users\PC\OneDrive\Desktop\restaurant website\server.py\"" /sc onlogon /ru "%USERNAME%" /f

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS! The app will now start automatically when you log into Windows.
    echo.
    echo To start it now without logging out, run START_SERVER.bat
) else (
    echo.
    echo Failed to create scheduled task. Please run this as Administrator.
)

pause