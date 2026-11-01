# 拉取/刷新 DSH 上游源码到 seed-agent\dsh（不入库的 vendor checkout）。
param(
  [string]$Repo = (Split-Path $PSScriptRoot -Parent),
  [string]$Ref = "ce7073d5",
  [switch]$Force
)

$dst = Join-Path $Repo 'dsh'

if (-not (Test-Path (Join-Path $dst '.git'))) {
  if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
  Write-Host "cloning deepseek-harness -> $dst"
  gh repo clone deepseek-ai/deepseek-harness $dst -- --depth 1
}

git -C $dst fetch --depth 1 origin $Ref
git -C $dst checkout --detach $Ref
if ($LASTEXITCODE -ne 0) { throw "checkout $Ref failed" }

$node = 'C:\Users\think\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
$pnpm = 'C:\Users\think\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs'
if ($Force -and (Test-Path $node)) {
  Write-Host "pnpm install"
  Push-Location $dst
  & $node $pnpm install --reporter=append-only
  Pop-Location
}

git -C $dst log --oneline -1
Write-Host "done: $dst"