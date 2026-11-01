# 验收：Super-agent（DSH fork 桌面版）分层自检。
#
# 默认检查：
#  1. core 冒烟（事件溯源）
#  2. host 插件冒烟（cordis 服务 + 看门狗）
#  3. 桌面启动（Electron）+ /super-agent/state 探活
# 可选：
#  -Slow    追加真实 DSH runtime 回合（sdk-smoke，约 1 分钟）
#  -Network 追加真实飞书回帖（channels-smoke）
param(
  [string]$Repo,
  [switch]$Slow,
  [switch]$Network
)

$ErrorActionPreference = 'Continue'
if (-not $Repo) {
  $here = $PSScriptRoot
  if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
  $Repo = Split-Path $here -Parent
}
$dsh = Join-Path $Repo 'dsh'

function Resolve-Node {
  $candidates = @(
    (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'),
    'C:\Program Files\nodejs\node.exe'
  )
  foreach ($path in $candidates) {
    if (-not (Test-Path $path)) { continue }
    $version = & $path -p "process.versions.node"
    $major = [int]($version.Split('.')[0]); $minor = [int]($version.Split('.')[1])
    if ($major -gt 24 -or ($major -eq 24 -and $minor -ge 9)) { return $path }
  }
  throw 'no Node.js >= 24.9 found'
}

$node = Resolve-Node
# 供 LLM 评估器/真机回合使用（缺失时 host 会回退 explicit 并告警）
$seedEnv = Join-Path $Repo 'seed.env'
if (Test-Path $seedEnv) {
  foreach ($line in Get-Content $seedEnv) {
    if ($line -match '^(BAILIAN_API_KEY|FEISHU_APP_ID|FEISHU_APP_SECRET)=(.+)$') {
      Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
    }
  }
}
$failures = 0
function Report([string]$Name, [bool]$Ok, [string]$Detail) {
  if ($Ok) { Write-Host "[PASS] $Name $Detail" } else { Write-Host "[FAIL] $Name $Detail"; $script:failures++ }
}

# 0) 准备（应用补丁 + 构建包，保证冒烟可跑）
Write-Host 'preparing packages ...'
& (Join-Path $Repo 'scripts\desktop-super-agent.ps1') -Repo $Repo -NoLaunch | Out-Host

# 1) core
try {
  $out = & $node (Join-Path $Repo 'scripts\smoke-super-agent.mjs') 2>&1 | Out-String
  Report 'core smoke' ($out -match 'CORE SMOKE OK') (($out -split "`n" | Where-Object { $_ -match 'tickets:|replay hash:' }) -join ' ')
} catch { Report 'core smoke' $false $_.Exception.Message }

# 2) host
Push-Location $dsh
try {
  $out = & $node 'packages/super-agent/host/tests/smoke.mjs' 2>&1 | Out-String
  Report 'host smoke' ($out -match 'HOST SMOKE OK') (($out -split "`n" | Where-Object { $_ -match 'watchdog:' }) -join ' ')
} catch { Report 'host smoke' $false $_.Exception.Message } finally { Pop-Location }

# 2b) 订阅扇出 / Inline&Spill / 入站 Source
Push-Location $dsh
try {
  $fanout = & $node 'packages/super-agent/host/tests/fanout-smoke.mjs' 2>&1 | Out-String
  Report 'fan-out smoke' ($fanout -match 'FANOUT SMOKE OK') (($fanout -split "`n" | Where-Object { $_ -match 'inputs:' }) -join ' ')
  $spill = & $node 'packages/super-agent/host/tests/spill-smoke.mjs' 2>&1 | Out-String
  Report 'spill smoke' ($spill -match 'SPILL SMOKE OK') (($spill -split "`n" | Where-Object { $_ -match 'spillPath:' }) -join ' ')
  $sources = & $node 'packages/super-agent/host/tests/sources-smoke.mjs' 2>&1 | Out-String
  Report 'sources smoke' ($sources -match 'SOURCES SMOKE OK') (($sources -split "`n" | Where-Object { $_ -match 'sources:' }) -join ' ')
  $recall = & $node 'packages/super-agent/host/tests/recall-smoke.mjs' 2>&1 | Out-String
  Report 'recall smoke' ($recall -match 'RECALL SMOKE OK') (($recall -split "`n" | Where-Object { $_ -match 'thread handles:' }) -join ' ')
  $handback = & $node 'packages/super-agent/host/tests/handback-smoke.mjs' 2>&1 | Out-String
  Report 'handback smoke' ($handback -match 'HANDBACK SMOKE OK') (($handback -split "`n" | Where-Object { $_ -match 'control tools:' }) -join ' ')
  $restart = & $node 'packages/super-agent/host/tests/restart-smoke.mjs' 2>&1 | Out-String
  Report 'restart smoke' ($restart -match 'RESTART SMOKE OK') (($restart -split "`n" | Where-Object { $_ -match 'recovery events|live assignment' }) -join ' ')
  $format = & $node 'packages/super-agent/host/tests/channel-format-smoke.mjs' 2>&1 | Out-String
  Report 'channel format smoke' ($format -match 'CHANNEL FORMAT SMOKE OK') (($format -split "`n" | Where-Object { $_ -match 'im length:|sent:' }) -join ' ')
} catch { Report 'fan-out/spill/sources smoke' $false $_.Exception.Message } finally { Pop-Location }

# 3) 可选：真实 runtime 回合 / Router / 渠道
if ($Slow) {
  Push-Location $dsh
  try {
    $router = & $node 'packages/super-agent/host/tests/router-smoke.mjs' 2>&1 | Out-String
    Report 'router smoke' ($router -match 'ROUTER SMOKE OK') (($router -split "`n" | Where-Object { $_ -match 'lastBatch:' }) -join ' ')
    $recallTool = & $node 'packages/super-agent/host/tests/recall-tool-smoke.mjs' 2>&1 | Out-String
    Report 'recall tool smoke' ($recallTool -match 'RECALL TOOL SMOKE OK') (($recallTool -split "`n" | Where-Object { $_ -match 'worker output:' }) -join ' ')
    $duplex = & $node 'packages/super-agent/host/tests/full-duplex-smoke.mjs' 2>&1 | Out-String
    Report 'full duplex smoke' ($duplex -match 'FULL DUPLEX SMOKE OK') (($duplex -split "`n" | Where-Object { $_ -match 'first file:' }) -join ' ')
    $async = & $node 'packages/super-agent/host/tests/async-react-smoke.mjs' 2>&1 | Out-String
    Report 'async react smoke' ($async -match 'ASYNC REACT SMOKE OK') (($async -split "`n" | Where-Object { $_ -match 'done file:' }) -join ' ')
    $watchdog = & $node 'packages/super-agent/host/tests/watchdog-llm-smoke.mjs' 2>&1 | Out-String
    Report 'watchdog llm smoke' ($watchdog -match 'WATCHDOG LLM SMOKE OK') (($watchdog -split "`n" | Where-Object { $_ -match 'verdict:|deterministic:' }) -join ' ')
    $spec = & $node 'packages/super-agent/host/tests/speculation-smoke.mjs' 2>&1 | Out-String
    Report 'speculation smoke' ($spec -match 'SPECULATION SMOKE OK') (($spec -split "`n" | Where-Object { $_ -match 'case1:|channel sent:' }) -join ' ')
    $out = & $node 'packages/super-agent/host/tests/sdk-smoke.mjs' 2>&1 | Out-String
    Report 'sdk smoke' ($out -match 'DSH EXECUTOR SMOKE OK') ''
  } catch { Report 'router/sdk smoke' $false $_.Exception.Message } finally { Pop-Location }
}
if ($Network) {
  Push-Location $dsh
  try {
    $out = & $node 'packages/super-agent/host/tests/channels-smoke.mjs' 2>&1 | Out-String
    Report 'channels smoke' ($out -match 'CHANNELS SMOKE OK') ''
    $live = & $node 'packages/super-agent/host/tests/inbound-live-smoke.mjs' 2>&1 | Out-String
    Report 'inbound live' ($live -match 'INBOUND LIVE OK') (($live -split "`n" | Where-Object { $_ -match 'feishu messages|github notifications' }) -join ' ')
    $fmtLive = & $node 'packages/super-agent/host/tests/channel-format-live-smoke.mjs' 2>&1 | Out-String
    Report 'channel format live' ($fmtLive -match 'CHANNEL FORMAT LIVE OK') (($fmtLive -split "`n" | Where-Object { $_ -match 'sent:' }) -join ' ')
  } catch { Report 'channels/inbound smoke' $false $_.Exception.Message } finally { Pop-Location }
}

# 4) 桌面启动 + 探活
$homePath = Join-Path $dsh 'apps\desktop\.desktop-build\sa-home'
$launchLog = Join-Path $dsh ('apps\desktop\.desktop-build\verify-launch-' + (Get-Date -Format 'HHmmss') + '.log')
if (Test-Path $launchLog) { Remove-Item $launchLog -Force }
Write-Host 'launching desktop (Electron) ...'
$pwsh = (Get-Process -Id $PID).Path
$child = Start-Process -FilePath $pwsh -PassThru -RedirectStandardOutput $launchLog -RedirectStandardError "$launchLog.err" -ArgumentList @(
  '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Repo 'scripts\desktop-super-agent.ps1'), '-Repo', $Repo, '-DshHome', $homePath, '-Restart', '-SkipPrepare', '-SkipBuild'
)
$url = $null
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $launchLog) {
    $match = Select-String -Path $launchLog -Pattern 'dsh web: (http://127\.0\.0\.1:\d+/\?token=\S+)' -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($match) { $url = $match.Matches[0].Groups[1].Value; break }
  }
}
if (-not $url) {
  Report 'desktop launch' $false 'no dsh web URL within 180s'
} else {
  $token = ([regex]::Match($url, 'token=(\S+)')).Groups[1].Value
  $port = [regex]::Match($url, '127\.0\.0\.1:(\d+)').Groups[1].Value
  $state = (Invoke-WebRequest -Uri "http://127.0.0.1:$port/super-agent/state?token=$token" -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
  $stage = if ($state.tickets.Count -gt 0) { $state.tickets[0].stage } else { '' }
  $routerMode = $state.config.routerMode
  Report 'desktop launch' ($state.ok -eq $true -and $stage -and $routerMode) "port=$port sources=$($state.sources.names -join '+') stage=$stage router=$routerMode spec=$($state.config.speculationEnabled)"
}

Write-Host ''
if ($failures -eq 0) { Write-Host 'VERIFY OK' ; exit 0 }
Write-Host "VERIFY FAIL ($failures)"; exit 1