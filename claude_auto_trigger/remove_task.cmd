@echo off
rem remove_task.cmd
rem Elevates (triggers UAC) then runs remove_task.ps1 with ExecutionPolicy Bypass.
rem Double-click or call from any prompt -- no manual bypass needed.

fltmc >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd.exe -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)
powershell -ExecutionPolicy Bypass -File "%~dp0remove_task.ps1"
pause
