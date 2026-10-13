$ErrorActionPreference = 'Stop'
$aliProject = Split-Path -Parent $PSScriptRoot
$aliScript = Join-Path $PSScriptRoot 'ali_export_reader.py'
$aliPython = 'C:\Program Files\Python312\pythonw.exe'
$aliAction = New-ScheduledTaskAction -Execute $aliPython -Argument ('"' + $aliScript + '"') -WorkingDirectory $aliProject
$aliUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$aliLogin = New-ScheduledTaskTrigger -AtLogOn -User $aliUser
$aliRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$aliSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$aliPrincipal = New-ScheduledTaskPrincipal -UserId $aliUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'CRA-Wingcore-Ali-Export-Reader' -Action $aliAction -Trigger @($aliLogin,$aliRepeat) -Settings $aliSettings -Principal $aliPrincipal -Description 'Read project Alibaba XLSX inbox and CRM read-only; create comparison plans. No CRM writes, AI calls, browser automation or customer messages.' -Force | Select-Object TaskName,State
