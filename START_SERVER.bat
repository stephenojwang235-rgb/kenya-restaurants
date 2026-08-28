@echo off
cd /d "%~dp0"
echo Starting Kenya Restaurant Finder...
echo.
echo The app will run permanently at http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
start "Kenya Restaurant Finder" python server.py
timeout /t 3 /nobreak >nul
start http://localhost:5000
pause
