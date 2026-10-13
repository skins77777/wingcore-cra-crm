$ErrorActionPreference = 'Stop'
$reviewProject = Split-Path -Parent $PSScriptRoot
$reviewScript = Join-Path $PSScriptRoot 'review_backend.py'
foreach ($reviewBind in @('127.0.0.1','172.22.176.1')) {
    $reviewListener = Get-NetTCPConnection -LocalAddress $reviewBind -LocalPort 3002 -State Listen -ErrorAction SilentlyContinue
    if ($reviewListener) {
        $reviewOwner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $reviewListener.OwningProcess)
        if ($reviewOwner.CommandLine -notlike ('*' + $reviewScript + '*')) { throw ('Port 3002 already belongs to another service on ' + $reviewBind) }
        continue
    }
    if ($reviewBind -ne '127.0.0.1' -and -not (Get-NetIPAddress -IPAddress $reviewBind -ErrorAction SilentlyContinue)) { continue }
    Start-Process -FilePath 'C:\Program Files\Python312\pythonw.exe' -ArgumentList @(('"' + $reviewScript + '"'),'--bind',$reviewBind) -WorkingDirectory $reviewProject -WindowStyle Hidden
}
