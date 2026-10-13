$ErrorActionPreference = 'Stop'
$r02Project = Split-Path -Parent $PSScriptRoot
$r02Script = Join-Path $PSScriptRoot 'r02_runtime.py'
$r02Action = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $r02Script + '"') -WorkingDirectory $r02Project
$r02Minute = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$r02Login = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$r02Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$r02Principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-R02-Signal-Runtime' -Action $r02Action -Trigger @($r02Minute,$r02Login) -Settings $r02Settings -Principal $r02Principal -Description 'Known procurement incremental R02 with candidate model fallback and protected purchase-stage writes.' -Force | Select-Object TaskName,State
