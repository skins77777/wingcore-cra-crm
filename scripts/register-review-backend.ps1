$ErrorActionPreference = 'Stop'
$reviewProject = Split-Path -Parent $PSScriptRoot
$reviewStarter = Join-Path $PSScriptRoot 'start-review-backend.py'
$reviewAction = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $reviewStarter + '"') -WorkingDirectory $reviewProject
$reviewLogin = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$reviewRecovery = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$reviewSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$reviewPrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-Review-Backend' -Action $reviewAction -Trigger @($reviewLogin,$reviewRecovery) -Settings $reviewSettings -Principal $reviewPrincipal -Description 'Recover authenticated local review API. No AI calls, CRM writes, or customer messages.' -Force | Select-Object TaskName,State
