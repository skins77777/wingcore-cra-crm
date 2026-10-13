param(
    [ValidateSet('Start', 'Stop', 'Status', 'Backup')]
    [string]$Action = 'Status'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxRoot = '/mnt/' + $projectRoot.Substring(0, 1).ToLowerInvariant() + $projectRoot.Substring(2).Replace('\', '/')
$distro = 'CRA-Ubuntu-24.04'
$composeDir = $linuxRoot + '/deployment/twenty'
switch ($Action) {
    'Start' {
        & (Join-Path $PSScriptRoot 'Start-ImageProxy.ps1')
        $holderPath = Join-Path $projectRoot 'runtime/wsl-session.json'
        $holderRunning = $false
        if (Test-Path -LiteralPath $holderPath) {
            $holderState = Get-Content -LiteralPath $holderPath -Raw | ConvertFrom-Json
            $holderProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($holderState.ProcessId)" -ErrorAction SilentlyContinue
            $holderRunning = $holderProcess -and $holderProcess.CommandLine -like '*CRA-Ubuntu-24.04*sleep infinity*'
        }
        if (-not $holderRunning) {
            $holder = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $distro, '-u', 'root', '--', 'sleep', 'infinity') -WindowStyle Hidden -PassThru
            [pscustomobject]@{ProcessId=$holder.Id} | ConvertTo-Json | Set-Content -LiteralPath $holderPath -Encoding ascii
        }
        & wsl.exe -d $distro -u root --cd $composeDir -- docker compose up -d --wait --wait-timeout 600
    }
    'Stop' {
        & wsl.exe -d $distro -u root --cd $composeDir -- docker compose stop
    }
    'Status' {
        & wsl.exe -d $distro -u root --cd $composeDir -- docker compose ps
    }
    'Backup' {
        & wsl.exe -d $distro -u root -- bash ($linuxRoot + '/scripts/backup-twenty.sh')
    }
}
if ($LASTEXITCODE -ne 0) { throw "Twenty $Action failed (exit $LASTEXITCODE)." }
if ($Action -eq 'Start') { Write-Host 'Twenty is available at http://localhost:3000' }
