$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = Join-Path $workspaceRoot "backend\.venv\Scripts\python.exe"

function Test-TcpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetHost,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [int]$TimeoutMilliseconds = 1000
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connectResult = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $connectResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }
        $client.EndConnect($connectResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Backend Python interpreter was not found: $pythonPath. Run 'uv sync' in the backend directory first."
}

$dependencyChecks = @(
    @{ Name = "Redis"; Host = "127.0.0.1"; Port = 6379 },
    @{ Name = "PostgreSQL"; Host = "127.0.0.1"; Port = 15432 }
)

foreach ($dependency in $dependencyChecks) {
    if (-not (Test-TcpEndpoint -TargetHost $dependency.Host -Port $dependency.Port)) {
        throw "$($dependency.Name) is unavailable at $($dependency.Host):$($dependency.Port). Start the Docker dependency first."
    }
    Write-Host "[OK] $($dependency.Name) $($dependency.Host):$($dependency.Port)"
}

$apiListener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($apiListener) {
    $owners = $apiListener |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            Get-Process -Id $_ -ErrorAction SilentlyContinue |
                Select-Object Id, ProcessName
    }
    $ownerText = ($owners | ForEach-Object { "$($_.ProcessName)(PID=$($_.Id))" }) -join ", "
    throw "Port 8000 is already in use by $ownerText. Run the VS Code task that stops this project's old API and workers, or stop the process manually."
}

$workspacePattern = [regex]::Escape($workspaceRoot)
$existingWorkers = Get-CimInstance Win32_Process |
    Where-Object {
        $commandLine = $_.CommandLine
        $commandLine -and
        $commandLine -match $workspacePattern -and
        $commandLine -match "celery(\.exe)?[\s\S]*worker" -and
        $commandLine -match "(dialog_queue|schedule_queue|extraction_queue)"
    }

if ($existingWorkers) {
    $workerText = ($existingWorkers | ForEach-Object {
        "$($_.Name)(PID=$($_.ProcessId))"
    }) -join ", "
    throw "Existing project Celery workers were found: $workerText. Run the VS Code task that stops this project's old API and workers first."
}

Write-Host "[OK] Python $pythonPath"
Write-Host "[OK] Port 8000 is available and no old Celery workers were found"
Write-Host "Backend four-process debug environment check passed."
