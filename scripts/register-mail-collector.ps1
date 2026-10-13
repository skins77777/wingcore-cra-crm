$ErrorActionPreference = 'Stop'
$mailProject = Split-Path -Parent $PSScriptRoot
$mailScript = Join-Path $PSScriptRoot 'collect-mail.py'
$mailRuntime = 'C:\Program Files\Python312\pythonw.exe'
$mailTaskAction = New-ScheduledTaskAction -Execute $mailRuntime -Argument ('"' + $mailScript + '"') -WorkingDirectory $mailProject
$mailMinuteTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$mailLoginTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$mailTaskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$mailTaskPrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-Mail-Collector' -Action $mailTaskAction -Trigger @($mailMinuteTrigger,$mailLoginTrigger) -Settings $mailTaskSettings -Principal $mailTaskPrincipal -Description 'Read-only IMAP intake for Wingcore inbox and sent mail; no model calls or CRM writes.' -Force | Select-Object TaskName,State
