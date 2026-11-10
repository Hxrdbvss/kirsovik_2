@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_demo.ps1" -Action stop -NoBrowser
if errorlevel 1 pause
