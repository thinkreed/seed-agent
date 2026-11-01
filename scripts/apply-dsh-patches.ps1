# 把 contrib/dsh 的改动应用到 vendor checkout（dsh/）。
param([string]$Repo = (Split-Path $PSScriptRoot -Parent))

$dsh = Join-Path $Repo 'dsh'
if (-not (Test-Path $dsh)) { throw "dsh/ missing: run scripts/sync-dsh.ps1 first" }

# 1) xlsx：用 registry 版本替换不可达的 CDN 依赖
$pkg = Join-Path $dsh 'packages\client\ui-sidebar-documentpreview\package.json'
if (Test-Path $pkg) {
  $text = [System.IO.File]::ReadAllText($pkg, [System.Text.Encoding]::UTF8)
  $patched = $text.Replace('https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz', '0.18.5')
  if ($patched -ne $text) {
    [System.IO.File]::WriteAllText($pkg, $patched, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "patched xlsx: $pkg"
  }
}

# 2) 覆盖文件（overlay）
$overlay = Join-Path $Repo 'contrib\dsh\overlay'
if (Test-Path $overlay) {
  Get-ChildItem $overlay -Directory | ForEach-Object {
    $package = $_.Name
    $targetDir = Join-Path $dsh "packages\client\$package\src\client\excel"
    if (-not (Test-Path $targetDir)) { $targetDir = Join-Path $dsh "packages\client\$package\src" }
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item (Join-Path $_.FullName '*') $targetDir -Force
    Write-Host "overlay -> $targetDir"
  }
}

# 3) 复制我们新增的包（保持 contrib/dsh/packages 下的相对路径）
$src = Join-Path $Repo 'contrib\dsh\packages'
if (Test-Path $src) {
  Get-ChildItem $src -Directory | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $dsh 'packages') -Recurse -Force
    Write-Host "copied package: $($_.Name)"
  }
  Get-ChildItem $src -Directory -Recurse -Depth 1 | Where-Object { Test-Path (Join-Path $_.FullName 'package.json') } | ForEach-Object {
    $relative = $_.FullName.Substring($src.Length + 1)
    New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $dsh "packages\$relative")) | Out-Null
    Copy-Item $_.FullName (Split-Path (Join-Path $dsh "packages\$relative")) -Recurse -Force
    Write-Host "copied nested package: $relative"
  }
}

# 3) 应用 *.patch（可选）
$patchDir = Join-Path $Repo 'contrib\dsh\patches'
if (Test-Path $patchDir) {
  Get-ChildItem $patchDir -Filter '*.patch' | ForEach-Object {
    git -C $dsh apply --whitespace=nowarn $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "failed to apply $($_.Name)" }
    Write-Host "applied patch: $($_.Name)"
  }
}

Write-Host "done."