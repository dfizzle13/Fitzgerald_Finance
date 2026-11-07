$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'settings.json') -Raw | ConvertFrom-Json
$serverScript = Join-Path $PSScriptRoot 'main.py'
$pidFile = Join-Path $projectRoot 'Database\server.pid'
$healthUrl = 'http://127.0.0.1:' + $config.port + '/api/status'
if (Test-Path -LiteralPath $pidFile) {
    $serverProcessId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue
    if ($existing -and $existing.CommandLine.Contains($serverScript)) {
        Write-Output ('Fitzgerald Finance is already running: http://localhost:' + $config.port)
        return
    }
}
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
    if ($health.shared) { Write-Output ('Fitzgerald Finance is already available: http://localhost:' + $config.port); return }
} catch {}
$pythonPath = $null
$serverVenv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $serverVenv) { $pythonPath = $serverVenv }
foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.11-64\python.exe'), (Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.15-64\python.exe'))) {
    if (!$pythonPath -and (Test-Path -LiteralPath $candidate)) { $pythonPath = $candidate; break }
}
if (!$pythonPath) { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
$serverArguments = @(('"' + $serverScript + '"'), '--host', [string]$config.host, '--port', [string]$config.port)
if ($config.secureCookie) { $serverArguments += '--secure-cookie' }
$process = Start-Process -FilePath $pythonPath -ArgumentList $serverArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-error.log') -PassThru
$process.Id | Set-Content -LiteralPath $pidFile
for ($attempt = 0; $attempt -lt 24; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($health.shared) { Write-Output ('Fitzgerald Finance is ready: http://localhost:' + $config.port); return }
    } catch {}
    if ($process.HasExited) { break }
}
throw 'Server did not start. Check Server\server-error.log.'
