$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$workspacePattern = [regex]::Escape($workspaceRoot)

$targets = Get-CimInstance Win32_Process |
    Where-Object {
        $commandLine = $_.CommandLine
        if (-not $commandLine -or $commandLine -notmatch $workspacePattern) {
            return $false
        }

        $isApi = $commandLine -match "uvicorn(\.exe)?[\s\S]*app\.main:app"
        $isWorker = (
            $commandLine -match "celery(\.exe)?[\s\S]*worker" -and
            $commandLine -match "(dialog_queue|schedule_queue|extraction_queue)"
        )
        return $isApi -or $isWorker
    }

if (-not $targets) {
    Write-Host "No existing project API or Celery worker was found."
    exit 0
}

$targetIds = @($targets | Select-Object -ExpandProperty ProcessId -Unique)
foreach ($target in $targets) {
    Write-Host "Stopping $($target.Name) PID=$($target.ProcessId)"
}

Stop-Process -Id $targetIds -Force -ErrorAction Stop
Write-Host "Stopped the project API and Celery workers. Redis, PostgreSQL, frontend, and unrelated processes were not changed."
