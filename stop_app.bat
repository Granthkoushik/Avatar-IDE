@echo off
setlocal enabledelayedexpansion

echo ====================================================
echo [AVATAR] Finding process running on port 8000...
echo ====================================================

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r /c:":8000 *LISTENING"') do (
    set PID=%%a
    echo [AVATAR] Found active server process with PID: !PID!
    echo [AVATAR] Shutting down server safely...
    taskkill /f /pid !PID!
    set FOUND=1
    goto :done
)

:done
if "!FOUND!"=="0" (
    echo [AVATAR] No server process was found running on port 8000.
) else (
    echo [AVATAR] Server terminated successfully.
)
pause
