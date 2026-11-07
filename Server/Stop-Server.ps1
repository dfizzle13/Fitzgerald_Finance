$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'Database\server.pid'
$serverScript = Join-Path $PSScriptRoot 'main.py'
if (!(Test-Path -LiteralPath $pidFile)) { Write-Output 'No saved server process.'; return }
$serverProcessId = [int](Get-Content -LiteralPath $pidFile -Raw)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue
if ($process -and $process.CommandLine.Contains($serverScript)) { Stop-Process -Id $serverProcessId }
elseif ($process) { throw 'The saved process belongs to another application; it was not stopped.' }
Remove-Item -LiteralPath $pidFile
Write-Output 'Fitzgerald Finance server stopped.'
