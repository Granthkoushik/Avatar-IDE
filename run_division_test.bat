@echo off
cd /d "%~dp0"
echo ====================================================
echo Preparing to run division_test.py...
echo Running command: python projects\division_test.py
echo ====================================================
call .venv\Scripts\python.exe projects\division_test.py
pause