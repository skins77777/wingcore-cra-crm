$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
$linuxRoot = '/mnt/' + $projectRoot.Substring(0, 1).ToLowerInvariant() + $projectRoot.Substring(2).Replace('\', '/')
$distro = 'CRA-Ubuntu-24.04'
$route = (& wsl.exe -d $distro -u root -- ip -j -4 route show default) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read WSL routing.' }
$adapter = (& wsl.exe -d $distro -u root -- ip -j -4 addr show eth0) | ConvertFrom-Json
$gateway = @($route)[0].gateway
$client = @(@($adapter)[0].addr_info | Where-Object family -eq 'inet')[0].local
if (-not $gateway -or -not $client) { throw 'Missing WSL NAT addresses.' }
$statePath = Join-Path $projectRoot 'runtime/image-proxy-state.json'
if (Test-Path -LiteralPath $statePath) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($previous.ProcessId)" -ErrorAction SilentlyContinue
    if ($existing -and $existing.CommandLine -like '*wsl-image-proxy.py*') {
        if ($previous.Gateway -eq $gateway -and $previous.Client -eq $client) { return }
        Stop-Process -Id $previous.ProcessId
    }
}
$ruleName = 'CRA-Twenty-WSL-ImageProxy'
$rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($rule) { Remove-NetFirewallRule -Name $ruleName }
New-NetFirewallRule -Name $ruleName -DisplayName 'CRA Twenty WSL image proxy (WSL client only)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18080 -LocalAddress $gateway -RemoteAddress $client -Profile Any | Out-Null
$python = (Get-Command python.exe -ErrorAction Stop).Source
$proxyScript = Join-Path $PSScriptRoot 'wsl-image-proxy.py'
$proxyProcess = Start-Process -FilePath $python -ArgumentList @('"' + $proxyScript + '"', '--listen', $gateway, '--client', $client) -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $projectRoot 'docs/deployment/logs/image-proxy-error.log')
Start-Sleep -Milliseconds 500
if ($proxyProcess.HasExited) { throw 'Image proxy failed to start. Check its log.' }
[pscustomobject]@{ProcessId=$proxyProcess.Id;Gateway=$gateway;Client=$client;Port=18080} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'deployment/wsl/docker-daemon.json') -Raw | ConvertFrom-Json
$config.proxies.'http-proxy' = "http://${gateway}:18080"
$config.proxies.'https-proxy' = "http://${gateway}:18080"
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $projectRoot 'runtime/docker-daemon.json') -Encoding ascii
$envPath = Join-Path $projectRoot 'deployment/twenty/.env'
if (Test-Path -LiteralPath $envPath) {
    $envText = [System.IO.File]::ReadAllText($envPath)
    $proxyLine = "OUTBOUND_PROXY=http://${gateway}:18080"
    if ($envText -match '(?m)^OUTBOUND_PROXY=.*$') { $envText = [regex]::Replace($envText, '(?m)^OUTBOUND_PROXY=.*$', $proxyLine) }
    else { $envText = $envText.TrimEnd() + "`n$proxyLine`n" }
    [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))
}
& wsl.exe -d $distro -u root -- cp ($linuxRoot + '/runtime/docker-daemon.json') /etc/docker/daemon.json
if ($LASTEXITCODE -ne 0) { throw 'Failed to configure Docker proxy.' }
& wsl.exe -d $distro -u root -- dockerd --validate --config-file /etc/docker/daemon.json
if ($LASTEXITCODE -ne 0) { throw 'Docker proxy configuration is invalid.' }
& wsl.exe -d $distro -u root -- systemctl restart docker
if ($LASTEXITCODE -ne 0) { throw 'Docker failed to restart.' }
