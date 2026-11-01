# 把 contrib/dsh 的改动应用到 vendor checkout（dsh/）。
param([string]$Repo)

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Repo) { $Repo = Split-Path $here -Parent }

$dsh = Join-Path $Repo 'dsh'
if (-not (Test-Path $dsh)) { throw "dsh/ missing: run scripts/sync-dsh.ps1 first" }

# 1) xlsx：用 registry 版本替换不可达的 CDN 依赖
$pkg = Join-Path $dsh 'packages\client\ui-sidebar-documentpreview\package.json'
if (Test-Path $pkg) {
  $text = [System.IO.File]::ReadAllText($pkg, [System.Text.Encoding]::UTF8)
  $patched = $text.Replace('https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz', 'npm:@e965/xlsx@0.20.3')
  if ($patched -ne $text) {
    [System.IO.File]::WriteAllText($pkg, $patched, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "patched xlsx: $pkg"
  }
}

# 2) overlay：覆盖文件（相对 packages/client 的路径）
$overlay = Join-Path $Repo 'contrib\dsh\overlay'
if (Test-Path $overlay) {
  Get-ChildItem $overlay -Directory | ForEach-Object {
    $package = $_.Name
    $targetDir = Join-Path $dsh "packages\client\$package\src\client\excel"
    if (-not (Test-Path $targetDir)) {
      $targetDir = Join-Path $dsh "packages\client\$package\src"
    }
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item (Join-Path $_.FullName '*') $targetDir -Force
    Write-Host "overlay -> $targetDir"
  }
}

# 3) 新增包：contrib/dsh/packages/** 镜像到 dsh/packages/**
$src = Join-Path $Repo 'contrib\dsh\packages'
if (Test-Path $src) {
  Get-ChildItem $src -Recurse -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'package.json') } | ForEach-Object {
    $relative = $_.FullName.Substring($src.Length + 1)
    $target = Join-Path $dsh "packages\$relative"
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Copy-Item $_.FullName $target -Recurse -Force
    Write-Host "copied package: $relative"
  }
}

# 4) 应用 *.patch（可选）
$patchDir = Join-Path $Repo 'contrib\dsh\patches'
if (Test-Path $patchDir) {
  Get-ChildItem $patchDir -Filter '*.patch' | ForEach-Object {
    git -C $dsh apply --whitespace=nowarn $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "failed to apply $($_.Name)" }
    Write-Host "applied patch: $($_.Name)"
  }
}

Write-Host "done."