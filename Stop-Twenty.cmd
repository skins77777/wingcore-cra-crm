@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\Manage-Twenty.ps1" -Action Stop
if errorlevel 1 pause
