$ErrorActionPreference = 'Stop'
$craProject = Split-Path -Parent $PSScriptRoot
$craStarter = Join-Path $PSScriptRoot 'start-local-services.py'
$craAction = New-ScheduledTaskAction -Execute 'C:\Program Files\Python312\pythonw.exe' -Argument ('"' + $craStarter + '"') -WorkingDirectory $craProject
$craUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$craLogin = New-ScheduledTaskTrigger -AtLogOn -User $craUser
$craRecovery = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$craSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$craPrincipal = New-ScheduledTaskPrincipal -UserId $craUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-Local-Services' -Action $craAction -Trigger @($craLogin,$craRecovery) -Settings $craSettings -Principal $craPrincipal -Description 'Keep project WSL alive and recover existing Twenty and Evolution containers silently. No installs, image pulls, AI calls or business writes.' -Force | Select-Object TaskName,State
