@echo off
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /PID %%a /F
timeout /t 2 /nobreak >nul
echo Done.
pause
