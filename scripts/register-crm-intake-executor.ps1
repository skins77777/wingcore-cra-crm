$ErrorActionPreference = 'Stop'
$intakeProject = Split-Path -Parent $PSScriptRoot
$intakeScript = Join-Path $PSScriptRoot 'crm_intake_executor.py'
$intakeAction = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $intakeScript + '"') -WorkingDirectory $intakeProject
$intakeMinute = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$intakeLogin = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$intakeSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$intakePrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-CRM-Intake-Executor' -Action $intakeAction -Trigger @($intakeMinute,$intakeLogin) -Settings $intakeSettings -Principal $intakePrincipal -Description 'Execute approved immutable person and opportunity creation plans only. No order writes or messages.' -Force | Select-Object TaskName,State
