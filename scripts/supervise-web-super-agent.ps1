# Keep the Super-agent Web Harness alive: restart it if the node process exits.
# Registered by scripts/install-service.ps1 (Windows Task Scheduler) or run detached.
param(
  [int]$Port = 4780,
  [string]$Repo
)

$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Repo) { $Repo = Split-Path -Parent $here }
$logDir = Join-Path $Repo 'runtime'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'service.log'
$harnessLog = Join-Path $logDir 'harness.log'
$launcher = Join-Path $here 'run-web-super-agent.ps1'

while ($true) {
  $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  "[$stamp] starting Super-agent on port $Port" | Out-File -Append -Encoding utf8 $log
  # Child stdout/stderr goes to a separate file: it holds an exclusive handle while running.
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -Port $Port -Repo $Repo -NoOpen *>> $harnessLog
  $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  "[$stamp] harness exited ($LASTEXITCODE); restarting in 5s" | Out-File -Append -Encoding utf8 $log
  Start-Sleep -Seconds 5
}