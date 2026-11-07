$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $PSScriptRoot 'settings.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$tailscalePath = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
if (!(Test-Path -LiteralPath $tailscalePath)) { throw 'Install Tailscale and sign in on this PC, then run this script again.' }
$statusJson = & $tailscalePath status --json
if ($LASTEXITCODE -ne 0) { throw 'Tailscale is unavailable. Open Tailscale and sign in first.' }
$status = $statusJson | ConvertFrom-Json
if ($status.BackendState -ne 'Running') { throw 'Open Tailscale on this PC and sign in, then run this script again.' }
& $tailscalePath serve --bg ('http://127.0.0.1:' + $config.port)
if ($LASTEXITCODE -ne 0) { throw 'Follow the HTTPS approval instructions printed by Tailscale, then run this script again.' }
$config.secureCookie = $true
$config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
& (Join-Path $PSScriptRoot 'Stop-Server.ps1')
& (Join-Path $PSScriptRoot 'Start-Server.ps1')
Write-Output 'Private HTTPS access is ready. Use the Tailscale HTTPS address on this PC and both phones.'
