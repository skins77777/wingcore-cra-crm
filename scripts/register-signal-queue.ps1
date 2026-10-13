$ErrorActionPreference = 'Stop'
$signalProject = Split-Path -Parent $PSScriptRoot
$signalScript = Join-Path $PSScriptRoot 'signal_queue.py'
$signalAction = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $signalScript + '"') -WorkingDirectory $signalProject
$signalMinute = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$signalLogin = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$signalSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$signalPrincipal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-Signal-Queue' -Action $signalAction -Trigger @($signalMinute,$signalLogin) -Settings $signalSettings -Principal $signalPrincipal -Description 'Local message normalization and candidate queue only; no AI calls or CRM writes.' -Force | Select-Object TaskName,State
