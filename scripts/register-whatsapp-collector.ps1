$ErrorActionPreference = 'Stop'
$waProject = Split-Path -Parent $PSScriptRoot
$waScript = Join-Path $PSScriptRoot 'collect-whatsapp.py'
$waRuntime = 'C:\Program Files\Python312\pythonw.exe'
$waAction = New-ScheduledTaskAction -Execute $waRuntime -Argument ('"' + $waScript + '"') -WorkingDirectory $waProject
$waMinute = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$waLogin = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$waSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$waPrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-WhatsApp-Collector' -Action $waAction -Trigger @($waMinute,$waLogin) -Settings $waSettings -Principal $waPrincipal -Description 'Read-only Evolution WhatsApp snapshots; no send, AI or CRM write.' -Force | Select-Object TaskName,State
