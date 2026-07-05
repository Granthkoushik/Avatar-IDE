@echo off
cd /d "%~dp0"
echo ====================================================
echo Preparing to run test_error.py...
echo Running command: python projects\test_error.py
echo ====================================================
call .venv\Scripts\python.exe projects\test_error.py > run_output.log 2>&1
type run_output.log
if %ERRORLEVEL% neq 0 (
    echo.
    echo ====================================================
    echo [AVATAR] Execution failed! Reporting crash to AI...
    echo ====================================================
    powershell -Command "$err = Get-Content -Raw run_output.log; Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/report_error' -Method Post -Body (ConvertTo-Json @{ filename='test_error.py'; error=$err }) -ContentType 'application/json'"
) else (
    del run_output.log
)
pause