# 打包 seed-agent 桌面（Windows；需要 Visual Studio C++ Build Tools）
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

function Resolve-Runtime {
  $runtime = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies'
  $node = Join-Path $runtime 'node\bin\node.exe'
  $pnpm = Join-Path $runtime 'pnpm\bin\pnpm.mjs'
  if ((Test-Path $node) -and (Test-Path $pnpm)) { return @{ Node = $node; Pnpm = $pnpm } }
  $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
  $pnpmCmd = Get-Command pnpm -ErrorAction SilentlyContinue
  if ($nodeCmd -and $pnpmCmd) { return @{ Node = $nodeCmd.Source; Pnpm = $pnpmCmd.Source } }
  throw 'Node 24 + pnpm 11 not found'
}

$runtime = Resolve-Runtime
$node = $runtime.Node
$pnpm = $runtime.Pnpm

# 1) 同步 DSH 变种源码与配置
& (Join-Path $Repo 'scripts\apply-dsh-patches.ps1') -Repo $Repo
$env:DSH_DESKTOP_UNSIGNED = '1'
$env:DSH_DESKTOP_SKIP_PACKAGED_SMOKE = '1'

# 下载加速：可选代理（SEED_AGENT_PROXY=http://127.0.0.1:10809）与 Electron 国内镜像
if ($env:SEED_AGENT_PROXY) {
  $env:HTTP_PROXY = $env:SEED_AGENT_PROXY
  $env:HTTPS_PROXY = $env:SEED_AGENT_PROXY
  $env:NO_PROXY = '127.0.0.1,localhost'
}
if (-not $env:ELECTRON_MIRROR) { $env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/' }

Push-Location $dsh
try {
  & $node $pnpm install --no-frozen-lockfile --reporter=append-only
  # 2) 先构建 Super-agent 各包（apply 会清空它们的 lib，而打包的 build 阶段不会单独编译它们）
  $filters = @(
    '@deepseek-ai/dsh-super-agent-core',
    '@deepseek-ai/dsh-super-agent-host',
    '@deepseek-ai/dsh-super-agent-bundle',
    '@deepseek-ai/dsh-super-agent-tool-recall',
    '@deepseek-ai/dsh-super-agent-tool-background',
    '@deepseek-ai/dsh-super-agent-tool-control',
    '@deepseek-ai/dsh-super-agent-tool-remote',
    '@deepseek-ai/dsh-super-agent-daemon',
    '@deepseek-ai/dsh-client-ui-super-agent'
  )
  foreach ($filter in $filters) {
    & $node $pnpm --filter $filter run build
    if ($LASTEXITCODE -ne 0) { throw "build failed: $filter" }
  }
  # 3) 官方 unsigned 打包
  if ($Dir) {
    & $node $pnpm --filter @deepseek-ai/dsh-desktop exec tsx scripts/package-target.ts win-x64 --dir --unsigned
  } else {
    & $node $pnpm --filter @deepseek-ai/dsh-desktop run package:win:x64:unsigned
  }
  $code = $LASTEXITCODE
} finally { Pop-Location }
exit $code