@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\Manage-Twenty.ps1" -Action Backup
pause
