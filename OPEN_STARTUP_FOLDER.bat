@echo off
echo Opening Startup folder...
echo.
echo INSTRUCTIONS:
echo 1. This will open your Windows Startup folder
echo 2. Right-click on START_SERVER.bat in the "restaurant website" folder
echo 3. Select "Create shortcut"
echo 4. Copy the shortcut to this Startup folder
echo 5. Done! The app will now start automatically when you log in
echo.
pause

:: Open the Startup folder
explorer "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"