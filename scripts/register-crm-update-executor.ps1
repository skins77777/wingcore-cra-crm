$ErrorActionPreference = 'Stop'
$updateProject = Split-Path -Parent $PSScriptRoot
$updateScript = Join-Path $PSScriptRoot 'crm_update_executor.py'
$updateAction = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $updateScript + '"') -WorkingDirectory $updateProject
$updateMinute = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$updateLogin = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$updateSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$updatePrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-CRM-Update-Executor' -Action $updateAction -Trigger @($updateMinute,$updateLogin) -Settings $updateSettings -Principal $updatePrincipal -Description 'Execute approved immutable customer/opportunity summary updates with atomic version filter; no orders or messages.' -Force | Select-Object TaskName,State
