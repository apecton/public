@echo off
rem setup_task.cmd
rem Elevates (triggers UAC) then runs setup_task.ps1 with ExecutionPolicy Bypass.
rem Double-click or call from any prompt -- no manual bypass needed.

fltmc >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd.exe -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)
powershell -ExecutionPolicy Bypass -File "%~dp0setup_task.ps1"
pause
