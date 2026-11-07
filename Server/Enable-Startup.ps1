$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'Start-Server.ps1'
$accountName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
try {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptPath + '"')
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $accountName
    $principal = New-ScheduledTaskPrincipal -UserId $accountName -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName 'Fitzgerald Finance Server' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Starts your private household finance server at sign-in.' -Force -ErrorAction Stop | Out-Null
    Write-Output 'Fitzgerald Finance will start when you sign in to Windows (scheduled task).'
} catch {
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Fitzgerald Finance Server.lnk'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptPath + '"'
    $shortcut.WorkingDirectory = Split-Path -Parent $PSScriptRoot
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Output 'Fitzgerald Finance will start when you sign in to Windows (Startup shortcut).'
}
