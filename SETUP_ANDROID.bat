@echo off
echo ==========================================
echo Kenya Restaurant Finder - Android Setup
echo ==========================================
echo.
echo This will set up access from your Android phone.
echo.

:: Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4 Address"') do (
    set "IP=%%a"
    goto :found
)

:found
set "IP=%IP: =%"

echo ==========================================
echo STARTING SERVER FOR ANDROID ACCESS
echo ==========================================
echo.
echo Your computer's IP address: %IP%
echo.
echo IMPORTANT: Your Android phone must be on the SAME WiFi network!
echo.

:: Start server in background
start "Kenya Restaurant Finder Server" python server.py

:: Wait for server to start
timeout /t 3 /nobreak >nul

echo ==========================================
echo SETUP COMPLETE!
echo ==========================================
echo.
echo TO ACCESS FROM YOUR ANDROID PHONE:
echo.
echo 1. Make sure your phone is on the SAME WiFi as this computer
echo 2. Open Chrome on your Android phone
echo 3. Go to: http://%IP%:5000
echo 4. Wait for the app to load (shows 1,983 restaurants)
echo 5. Tap the Chrome menu (3 dots in top right)
echo 6. Select "Add to Home screen"
echo 7. Name it "Kenya Restaurants" and tap "Add"
echo.
echo The app will now be on your phone's home screen!
echo You can access it anytime like a regular app.
echo.
echo ==========================================
echo.
echo Starting browser on this computer...
start http://%IP%:5000

echo.
echo Press any key to exit...
pause >nul
