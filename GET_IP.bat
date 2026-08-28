@echo off
echo ==========================================
echo Kenya Restaurant Finder - Network Access
echo ==========================================
echo.
echo Finding your computer's IP address...
echo.

:: Get the local IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4 Address"') do (
    set "IP=%%a"
    goto :found
)

:found
set "IP=%IP: =%"
echo Your computer's IP address is: %IP%
echo.
echo To access from your Android phone:
echo 1. Make sure your phone is on the SAME WiFi network as this computer
echo 2. Open Chrome on your phone
echo 3. Go to: http://%IP%:5000
echo 4. Tap the menu (3 dots) and select "Add to Home screen"
echo.
echo Starting the server and opening browser...
echo.

start "Kenya Restaurant Finder" python server.py
timeout /t 3 /nobreak >nul
start http://%IP%:5000

pause