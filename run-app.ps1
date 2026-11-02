param(
    [switch]$UseConfiguredDatabase
)

$ErrorActionPreference = "Stop"
$workspace = $PSScriptRoot
$backendDirectory = Join-Path $workspace "backend"
$frontendDirectory = Join-Path $workspace "frontend"
$viteCli = Join-Path $frontendDirectory "node_modules\vite\bin\vite.js"
$dataDirectory = Join-Path $env:LOCALAPPDATA "BusinessProjectAssistance"
$logDirectory = Join-Path $dataDirectory "logs"

if (-not (Test-Path -LiteralPath $viteCli)) {
    throw "Vite is not installed. Run 'npm install' from the frontend folder first."
}

$pythonLauncher = Get-Command "py.exe" -ErrorAction Stop
$nodeCommand = Get-Command "node.exe" -ErrorAction Stop
$pythonExecutable = (& $pythonLauncher.Source -c "import sys; print(sys.executable)").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExecutable)) {
    throw "Could not locate the Python interpreter. Check the Python launcher installation."
}

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

if (-not $UseConfiguredDatabase) {
    $databasePath = (Join-Path $dataDirectory "local-dev.sqlite").Replace("\", "/")
    $env:DATABASE_URL = "sqlite:///$databasePath"
}

function Stop-ProjectListener {
    param([int]$Port)

    $processIds = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )

    foreach ($processId in $processIds) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        if ($null -eq $process) {
            continue
        }

        $commandLine = [string]$process.CommandLine
        $isProjectBackend = $Port -eq 5000 -and
            $process.Name -match "^python" -and
            $commandLine -match "(?i)-m\s+flask" -and
            $commandLine -match "(?i)--app\s+wsgi" -and
            $commandLine -match "(?i)--port\s+5000"
        $isProjectFrontend = $Port -eq 5173 -and
            $process.Name -eq "node.exe" -and
            $commandLine.IndexOf($workspace, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $commandLine -match "(?i)vite"

        if (-not ($isProjectBackend -or $isProjectFrontend)) {
            throw "Port $Port is used by another process (PID $processId). Stop it before running this script."
        }

        Stop-Process -Id $processId
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
                break
            }
            Start-Sleep -Milliseconds 250
        }
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            throw "Could not stop the existing project process on port $Port (PID $processId)."
        }
    }
}

function Wait-ForEndpoint {
    param(
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [string]$ServiceName
    )

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {
            throw "$ServiceName exited during startup. Check the logs in '$logDirectory'."
        }

        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch [System.Net.WebException] {
            Start-Sleep -Milliseconds 500
        }
    }

    Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
    throw "$ServiceName did not become ready at $Url. Check the logs in '$logDirectory'."
}

Stop-ProjectListener -Port 5000
Stop-ProjectListener -Port 5173

Push-Location $backendDirectory
try {
    & $pythonExecutable -m flask --app wsgi db upgrade
    if ($LASTEXITCODE -ne 0) {
        throw "Database upgrade failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$backendProcess = Start-Process `
    -FilePath $pythonExecutable `
    -ArgumentList @("-m", "flask", "--app", "wsgi", "run", "--host", "127.0.0.1", "--port", "5000") `
    -WorkingDirectory $backendDirectory `
    -RedirectStandardOutput (Join-Path $logDirectory "backend.stdout.log") `
    -RedirectStandardError (Join-Path $logDirectory "backend.stderr.log") `
    -PassThru `
    -WindowStyle Hidden

$frontendProcess = Start-Process `
    -FilePath $nodeCommand.Source `
    -ArgumentList @($viteCli, "--host", "127.0.0.1") `
    -WorkingDirectory $frontendDirectory `
    -RedirectStandardOutput (Join-Path $logDirectory "frontend.stdout.log") `
    -RedirectStandardError (Join-Path $logDirectory "frontend.stderr.log") `
    -PassThru `
    -WindowStyle Hidden

Wait-ForEndpoint `
    -Url "http://127.0.0.1:5000/api/health" `
    -Process $backendProcess `
    -ServiceName "Flask backend"
Wait-ForEndpoint `
    -Url "http://127.0.0.1:5173/" `
    -Process $frontendProcess `
    -ServiceName "Vite frontend"

Write-Host "Database upgraded and app started."
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend health: http://localhost:5000/api/health"
Write-Host "Logs: $logDirectory"
