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

# 3) 品牌：把 locale 里的 "DSH 本地构建 / DSH Local Build" 改成 seed-agent
$localeDir = Join-Path $dsh 'packages\client\locale\src\locales'
if (Test-Path $localeDir) {
  Get-ChildItem $localeDir -Filter '*.ts' | ForEach-Object {
    $text = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
    $branded = [regex]::Replace($text, "'brand\.localBuild': '[^']*'", "'brand.localBuild': 'seed-agent'")
    if ($branded -ne $text) {
      [System.IO.File]::WriteAllText($_.FullName, $branded, (New-Object System.Text.UTF8Encoding($false)))
      Write-Host "brand -> $($_.Name)"
    }
  }
}

# 4) 新增包：contrib/dsh/packages/** 镜像到 dsh/packages/**
$src = Join-Path $Repo 'contrib\dsh\packages'
if (Test-Path $src) {
  Get-ChildItem $src -Recurse -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'package.json') } | ForEach-Object {
    $relative = $_.FullName.Substring($src.Length + 1)
    $target = Join-Path $dsh "packages\$relative"
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
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
# 5) 配置模板：contrib/dsh/config -> dsh/config；并把工具 URL 占位替换成实际构建产物路径
$cfgSrc = Join-Path $Repo 'contrib\dsh\config'
$cfgDst = Join-Path $dsh 'config'
if (Test-Path $cfgSrc) {
  New-Item -ItemType Directory -Force -Path $cfgDst | Out-Null
  Copy-Item (Join-Path $cfgSrc '*') $cfgDst -Force
  $toolUrls = @{
    '__SUPER_AGENT_RECALL_TOOL__' = 'file:///' + ((Join-Path $dsh 'packages\super-agent\tool-recall\lib\index.js') -replace '\\', '/')
    '__SUPER_AGENT_BACKGROUND_TOOL__' = 'file:///' + ((Join-Path $dsh 'packages\super-agent\tool-background\lib\index.js') -replace '\\', '/')
    '__SUPER_AGENT_CONTROL_TOOL__' = 'file:///' + ((Join-Path $dsh 'packages\super-agent\tool-control\lib\index.js') -replace '\\', '/')
    '__SUPER_AGENT_REMOTE_TOOL__' = 'file:///' + ((Join-Path $dsh 'packages\super-agent\tool-remote\lib\index.js') -replace '\\', '/')
  }
  foreach ($cfgFile in Get-ChildItem $cfgDst -Filter '*.yml') {
    $cfgText = [System.IO.File]::ReadAllText($cfgFile.FullName)
    $changed = $false
    foreach ($key in $toolUrls.Keys) {
      if ($cfgText.Contains($key)) { $cfgText = $cfgText.Replace($key, $toolUrls[$key]); $changed = $true }
    }
    if ($changed) {
      [System.IO.File]::WriteAllText($cfgFile.FullName, $cfgText, (New-Object System.Text.UTF8Encoding($false)))
    }
  }
}