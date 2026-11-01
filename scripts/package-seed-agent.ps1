# 打包 seed-agent 桌面（需要 Visual Studio C++ Build Tools）
#
# 用法：
#   pwsh -File scripts/package-seed-agent.ps1          # NSIS 安装包（unsigned）
#   pwsh -File scripts/package-seed-agent.ps1 -Dir     # 只产出解包目录
param(
  [switch]$Dir
)
$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
$Repo = Split-Path $here -Parent
$dsh = Join-Path $Repo 'dsh'

if (-not (Test-Path (Join-Path $dsh 'pnpm-workspace.yaml'))) {
  throw "dsh checkout missing; run scripts/sync-dsh.ps1 first"
}
& (Join-Path $Repo 'scripts\apply-dsh-patches.ps1') -Repo $Repo
$env:DSH_DESKTOP_UNSIGNED = '1'

$node = (Get-Command node).Source
$pnpm = (Get-Command pnpm -ErrorAction SilentlyContinue)
if (-not $pnpm) {
  $runtime = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies'
  $node = Join-Path $runtime 'node\bin\node.exe'
  $pnpmMjs = Join-Path $runtime 'pnpm\bin\pnpm.mjs'
  if (-not (Test-Path $pnpmMjs)) { throw "pnpm not found; install Node 24 + pnpm 11" }
  Push-Location $dsh
  try {
    & $node $pnpmMjs install --no-frozen-lockfile
    if ($Dir) {
      & $node $pnpmMjs --filter @deepseek-ai/dsh-desktop exec tsx scripts/package-target.ts win-x64 --dir --unsigned
    } else {
      & $node $pnpmMjs --filter @deepseek-ai/dsh-desktop run package:win:x64:unsigned
    }
  } finally { Pop-Location }
  exit $LASTEXITCODE
}

Push-Location $dsh
try {
  & $node $pnpm.Source install --no-frozen-lockfile
  if ($Dir) {
    & $node $pnpm.Source --filter @deepseek-ai/dsh-desktop exec tsx scripts/package-target.ts win-x64 --dir --unsigned
  } else {
    & $node $pnpm.Source --filter @deepseek-ai/dsh-desktop run package:win:x64:unsigned
  }
} finally { Pop-Location }
exit $LASTEXITCODE