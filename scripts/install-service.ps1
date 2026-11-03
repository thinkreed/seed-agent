# Register the Super-agent Web Harness as a logon task with automatic restart.
# Usage: powershell -File scripts/install-service.ps1 [-Port 4780]
param(
  [int]$Port = 4780,
  [string]$Repo
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Repo) { $Repo = Split-Path -Parent $here }
$taskName = 'seed-agent-superagent'
$supervisor = Join-Path $here 'supervise-web-super-agent.ps1'

if (-not (Test-Path $supervisor)) { throw "supervisor missing: $supervisor" }

# Remove any previous instance/task so this is idempotent.
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'supervise-web-super-agent\.ps1' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
  Where-Object { $_.CommandLine -match 'seed-agent-superagent.*bin\.js.*--profile web' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$supervisor`" -Port $Port -Repo `"$Repo`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "installed and started scheduled task: $taskName"
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State