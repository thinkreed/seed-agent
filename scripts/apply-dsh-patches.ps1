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

# 4b) core 没有独立 src：从仓库根 src 生成 lib，供 DSH host 解析。
$coreDir = Join-Path $dsh 'packages\super-agent\core'
if (Test-Path (Join-Path $coreDir 'build.mjs')) {
  Push-Location $coreDir
  try {
    & node build.mjs
    if ($LASTEXITCODE -ne 0) { throw "core build failed" }
  } finally {
    Pop-Location
  }
  Write-Host "built core from canonical src"
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
# 6) 桌面品牌：安装包 productName / 协议名改成 seed-agent（vendor 内替换，脚本可重放；seed-agent productName）
$eb = Join-Path $dsh 'apps\desktop\scripts\electron-builder-config.mjs'
if (Test-Path $eb) {
  $ebText = [System.IO.File]::ReadAllText($eb)
  $ebText = $ebText.Replace("productName: 'DeepSeek Harness'", "productName: 'seed-agent'")
  $ebText = $ebText.Replace("const policy = packagesMacOS && unsigned ? undefined : resolveDesktopPolicyEnvironment(env)", "const policy = unsigned ? undefined : resolveDesktopPolicyEnvironment(env)")
  $ebText = $ebText.Replace("protocols: [{ name: 'DeepSeek Harness', schemes: ['dsh'] }]", "protocols: [{ name: 'seed-agent', schemes: ['dsh'] }]")
  [System.IO.File]::WriteAllText($eb, $ebText, (New-Object System.Text.UTF8Encoding($false)))
}
# 7) 桌面打包环境（无签名本地构建）：contrib/dsh/config/desktop.env.windows -> dsh/apps/desktop/.env.windows
$desktopEnv = Join-Path $Repo 'contrib\dsh\config\desktop.env.windows'
$desktopEnvDst = Join-Path $dsh 'apps\desktop\.env.windows'
if ((Test-Path $desktopEnv) -and -not (Test-Path $desktopEnvDst)) {
  Copy-Item $desktopEnv $desktopEnvDst -Force
}
# 6b) 打包冒烟脚本的可执行名跟随品牌（vendor 上游硬编码 DeepSeek Harness）
$smoke = Join-Path $dsh 'apps\desktop\scripts\smoke-packaged-runtime.ts'
if (Test-Path $smoke) {
  $smokeText = [System.IO.File]::ReadAllText($smoke)
  if ($smokeText.Contains('DeepSeek Harness')) {
    $smokeText = $smokeText.Replace("'DeepSeek Harness.exe'", "'seed-agent.exe'")
    $smokeText = $smokeText.Replace("'DeepSeek Harness.app', 'Contents'", "'seed-agent.app', 'Contents'")
    $smokeText = $smokeText.Replace("'MacOS', 'DeepSeek Harness'", "'MacOS', 'seed-agent'")
    [System.IO.File]::WriteAllText($smoke, $smokeText, (New-Object System.Text.UTF8Encoding($false)))
  }
}
# 8) 把 Super-agent 包加入 @deepseek-ai/dsh 的依赖闭包：桌面打包时随 runtime 一起安装
$cliPkg = Join-Path $dsh 'apps\cli\package.json'
if (Test-Path $cliPkg) {
  $cliText = [System.IO.File]::ReadAllText($cliPkg)
  $changed = $false
  if (-not $cliText.Contains('@deepseek-ai/dsh-super-agent-bundle')) {
    $bundleRow = '"@deepseek-ai/dsh-super-agent-bundle": "workspace:*",'
    $cliText = $cliText.Replace('"@deepseek-ai/dsh-client-ui-super-agent": "workspace:*",', '"@deepseek-ai/dsh-client-ui-super-agent": "workspace:*",' + "`r`n    " + $bundleRow)
    $changed = $true
  }
  if (-not $cliText.Contains('@deepseek-ai/dsh-super-agent-host')) {
    $names = @(
      '@deepseek-ai/dsh-super-agent-core',
      '@deepseek-ai/dsh-super-agent-host',
      '@deepseek-ai/dsh-super-agent-tool-recall',
      '@deepseek-ai/dsh-super-agent-tool-background',
      '@deepseek-ai/dsh-super-agent-tool-control',
      '@deepseek-ai/dsh-super-agent-tool-remote',
      '@deepseek-ai/dsh-super-agent-daemon',
      '@deepseek-ai/dsh-client-ui-super-agent'
    )
    $rows = ($names | ForEach-Object { '    "{0}": "workspace:*",' -f $_ }) -join "`r`n"
    $cliText = [regex]::Replace($cliText, '("dependencies"\s*:\s*\{)', "`$1`r`n$rows", 1)
    $changed = $true
  }
  if ($changed) { [System.IO.File]::WriteAllText($cliPkg, $cliText, (New-Object System.Text.UTF8Encoding($false))) }
}
# 9) 打包冒烟可跳过（本机 Smart App Control 会拦截未签名新构建的 exe，spawn 失败）
$smokePkg = Join-Path $dsh 'apps\desktop\scripts\smoke-packaged-runtime.ts'
if (Test-Path $smokePkg) {
  $smokePkgText = [System.IO.File]::ReadAllText($smokePkg)
  if (-not $smokePkgText.Contains('DSH_DESKTOP_SKIP_PACKAGED_SMOKE')) {
    $guard = "if (process.env.DSH_DESKTOP_SKIP_PACKAGED_SMOKE === '1') { console.log('desktop runtime: packaged smoke skipped (DSH_DESKTOP_SKIP_PACKAGED_SMOKE)'); process.exit(0) }`r`n"
    $smokePkgText = $smokePkgText.Replace('const paths = resolveDesktopTargetBuildPaths()', $guard + 'const paths = resolveDesktopTargetBuildPaths()')
    [System.IO.File]::WriteAllText($smokePkg, $smokePkgText, (New-Object System.Text.UTF8Encoding($false)))
  }
}
# 10) 桌面变种：Super-agent bundle 进闭包 + 默认挂载到 desktop profile + asar 解包 + worker patch
# 10a) worker provider/tool patch 随 host 包发布（宿主 bundleDefaults 默认指向它）
$sdkPatch = Join-Path $Repo 'contrib\dsh\config\sdk-super-agent.patch.yml'
$hostConfigDir = Join-Path $dsh 'packages\super-agent\host\config'
if ((Test-Path $sdkPatch) -and (Test-Path (Split-Path $hostConfigDir -Parent))) {
  New-Item -ItemType Directory -Path $hostConfigDir -Force | Out-Null
  Copy-Item $sdkPatch (Join-Path $hostConfigDir 'sdk-super-agent.patch.yml') -Force
}
# 10c) desktop profile 首次创建时挂载 Super-agent bundle
$pm = Join-Path $dsh 'apps\desktop\src\project-manager.ts'
if (Test-Path $pm) {
  $pmText = [System.IO.File]::ReadAllText($pm)
  if ($pmText.Contains('initProfile(projectDir, WEB_PROFILE.bundles)')) {
    $pmText = $pmText.Replace('initProfile(projectDir, WEB_PROFILE.bundles)', "initProfile(projectDir, [...WEB_PROFILE.bundles, '@deepseek-ai/dsh-super-agent-bundle'])")
    [System.IO.File]::WriteAllText($pm, $pmText, (New-Object System.Text.UTF8Encoding($false)))
  }
}
# 10d) 整个 dsh runtime 解开 asar（worker 子进程是普通 node，读不了 app.asar）
$ebPath = Join-Path $dsh 'apps\desktop\scripts\electron-builder-config.mjs'
if (Test-Path $ebPath) {
  $ebText = [System.IO.File]::ReadAllText($ebPath)
  $needle = "context.packager.config.asarUnpack = [...(typeof existing === 'string' ? [existing] : existing), ...patterns]"
  if ($ebText.Contains($needle) -and -not $ebText.Contains("...patterns, 'dsh/**'")) {
    $ebText = $ebText.Replace($needle, "context.packager.config.asarUnpack = [...(typeof existing === 'string' ? [existing] : existing), ...patterns, 'dsh/**']")
    [System.IO.File]::WriteAllText($ebPath, $ebText, (New-Object System.Text.UTF8Encoding($false)))
  }
}

# 10e) 让 worker 能读到物理 dsh：把 prepared runtime 复制一份到 resources/dsh（app.asar 之外）
$ebExtra = Join-Path $dsh 'apps\desktop\scripts\electron-builder-config.mjs'
if (Test-Path $ebExtra) {
  $ebExtraText = [System.IO.File]::ReadAllText($ebExtra)
  $runtimeLine = "      { from: buildPaths.runtime, to: 'runtime' },"
  if (-not $ebExtraText.Contains("resources/dsh") -and $ebExtraText.Contains($runtimeLine)) {
    $extra = $runtimeLine + "`r`n      // worker 子进程是普通 node，读不了 app.asar：把 runtime 再放一份到 resources/dsh。`r`n      { from: buildPaths.dsh, to: 'dsh' },
      { from: join(buildPaths.dsh, 'node_modules'), to: 'dsh/node_modules', filter: ['**/*'] },"
    $ebExtraText = $ebExtraText.Replace($runtimeLine, $extra)
    [System.IO.File]::WriteAllText($ebExtra, $ebExtraText, (New-Object System.Text.UTF8Encoding($false)))
  }
}
