# 一键准备并启动「seed-agent 桌面版」（DSH fork + Super-agent 插件）。
#
# 做的事：
#  1. 从 seed.env 读 BAILIAN / FEISHU 凭据到当前进程环境
#  2. 应用 contrib/dsh 补丁与新增包（apply-dsh-patches.ps1）
#  3. 构建 core / host / ui-super-agent 三个包（-SkipBuild 可跳过）
#  4. 准备隔离 DSH_HOME：拷贝桌面 profile、link 两个包、注入 profile 行、pnpm install
#  5. 启动 Electron 桌面壳（-NoLaunch 只准备不启动）
#
# 例子：
#   pwsh -File scripts/desktop-super-agent.ps1 -Restart
#   pwsh -File scripts/desktop-super-agent.ps1 -Fresh -NoLaunch
param(
  [string]$Repo,
  [string]$DshHome,
  [switch]$SkipBuild,
  [switch]$NoLaunch,
  [switch]$Restart,
  [switch]$SkipPrepare,
  [switch]$Fresh
)

$ErrorActionPreference = 'Stop'
if (-not $Repo) {
  $here = $PSScriptRoot
  if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
  $Repo = Split-Path $here -Parent
}
$dsh = Join-Path $Repo 'dsh'
if (-not (Test-Path $dsh)) { throw "dsh/ missing: run scripts/sync-dsh.ps1 first" }
if (-not $DshHome) { $DshHome = Join-Path $dsh 'apps\desktop\.desktop-build\sa-home' }

function Resolve-Runtime {
  $candidates = @(
    (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'),
    'C:\Program Files\nodejs\node.exe'
  )
  foreach ($nodePath in $candidates) {
    if (-not (Test-Path $nodePath)) { continue }
    $version = & $nodePath -p "process.versions.node"
    $major = [int]($version.Split('.')[0])
    $minor = [int]($version.Split('.')[1])
    if ($major -gt 24 -or ($major -eq 24 -and $minor -ge 9)) {
      $dependencies = Split-Path (Split-Path (Split-Path $nodePath)); $pnpmMjs = Join-Path $dependencies 'pnpm\bin\pnpm.mjs'
      if (Test-Path $pnpmMjs) { return @{ Node = $nodePath; Pnpm = $pnpmMjs } }
      return @{ Node = $nodePath; Pnpm = $null }
    }
  }
  throw 'no Node.js >= 24.9 found (set PATH or install the DSH runtime)'
}

$runtime = Resolve-Runtime
$node = $runtime.Node
function Invoke-Pnpm([string[]]$Arguments) {
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    if ($runtime.Pnpm) { & $node $runtime.Pnpm @Arguments 2>&1 | Out-Host } else { & pnpm @Arguments 2>&1 | Out-Host }
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $previous }
  if ($code -ne 0) { throw "pnpm $($Arguments -join ' ') failed ($code)" }
}

# 1) 凭据
$seedEnv = Join-Path $Repo 'seed.env'
if (Test-Path $seedEnv) {
  foreach ($line in Get-Content $seedEnv) {
    if ($line -match '^(BAILIAN_API_KEY|FEISHU_APP_ID|FEISHU_APP_SECRET)=(.+)$') {
      Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
    }
  }
}
if (-not $env:BAILIAN_API_KEY) { Write-Host 'warn: BAILIAN_API_KEY missing; worker model calls will fail' }

# 2) 补丁
if (-not $SkipPrepare) { & (Join-Path $Repo 'scripts\apply-dsh-patches.ps1') -Repo $Repo | Out-Host }

# 3) 构建
if (-not $SkipBuild) {
  Push-Location $dsh
  try {
    Invoke-Pnpm @('install', '--no-frozen-lockfile', '--reporter=append-only')
    foreach ($filter in @('@deepseek-ai/dsh-super-agent-core', '@deepseek-ai/dsh-super-agent-host', '@deepseek-ai/dsh-super-agent-tool-recall', '@deepseek-ai/dsh-super-agent-tool-background', '@deepseek-ai/dsh-client-ui-super-agent')) {
      Invoke-Pnpm @('--filter', $filter, 'run', 'build')
    }
  } finally { Pop-Location }
}

# 4) 隔离 DSH_HOME
if ($Fresh -and (Test-Path $DshHome)) { Remove-Item $DshHome -Recurse -Force }
$profileDir = Join-Path $DshHome 'profiles\desktop'
if (-not (Test-Path $profileDir)) {
  $source = Join-Path $env:USERPROFILE '.dsh\profiles\desktop'
  if (-not (Test-Path $source)) { throw "no desktop profile to seed from: $source" }
  New-Item -ItemType Directory -Force -Path (Split-Path $profileDir) | Out-Null
  Copy-Item $source $profileDir -Recurse -Force
}

# 4a) link 两个包
$manifestPath = Join-Path $profileDir 'package.json'
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$links = @{
  '@deepseek-ai/dsh-super-agent-host' = "link:$($dsh -replace '\\','/')/packages/super-agent/host"
  '@deepseek-ai/dsh-client-ui-super-agent' = "link:$($dsh -replace '\\','/')/packages/client/ui-super-agent"
}
foreach ($name in $links.Keys) {
  $manifest.dependencies | Add-Member -NotePropertyName $name -NotePropertyValue $links[$name] -Force
}
$json = $manifest | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($manifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))

# 4b) profile 行（幂等：先删旧块）
$patchPath = Join-Path $profileDir 'cordis.patch.yml'
$patchText = if (Test-Path $patchPath) { [System.IO.File]::ReadAllText($patchPath) } else { "[]`n" }
$patchText = [regex]::Replace($patchText, '(?s)\r?\n# === seed-agent Super-agent \(fork integration\) ===.*$', '')
$repoPosix = $dsh -replace '\\','/'
$block = @"

# === seed-agent Super-agent (fork integration) ===
- insert:
    - id: super-agent-host
      name: '@deepseek-ai/dsh-super-agent-host'
      config:
        dbPath: .seed/super-agent.db
        slots: 2
        dshBin: $repoPosix/apps/cli/lib/bin.js
        dshHome: $repoPosix/apps/desktop/.desktop-build/sa-runtime-home
        dshProfile: sdk
        dshProvider: bailian
        dshModel: deepseek-v4.1-flash
        dshPatch: $repoPosix/config/sdk-bailian.patch.yml
        workspace: $($Repo -replace '\\','/')
        dshPermissionMode: danger-full-access
        sourcesEnabled: true
        sourceFeishuChatIds: oc_93f1a464c8258f572ff133db799a2546
        sourceGithubRepos: thinkreed/seed-agent-e2e
        sourceIntervalSeconds: 20
    - id: super-agent-ui
      name: '@deepseek-ai/dsh-client-ui-super-agent'
"@
[System.IO.File]::WriteAllText($patchPath, $patchText.TrimEnd() + $block, (New-Object System.Text.UTF8Encoding($false)))

# 4c) profile 依赖
Push-Location $profileDir
try {
  $env:CI = 'true'
  Invoke-Pnpm @('install', '--no-frozen-lockfile', '--reporter=append-only')
} finally { Pop-Location }

# 5) 启动
if ($Restart) {
  Get-Process -Name electron -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like (Join-Path $dsh '*') } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}
if ($NoLaunch) {
  Write-Host "ready: DSH_HOME=$DshHome (not launched)"
  exit 0
}
Write-Host "launching seed-agent desktop, DSH_HOME=$DshHome"
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$env:DSH_HOME = $DshHome
$env:DSH_DESKTOP_OPEN_DEVTOOLS = '0'
Push-Location $dsh
try {
  Invoke-Pnpm @('--filter', '@deepseek-ai/dsh-desktop', 'run', 'start')
} finally { Pop-Location }