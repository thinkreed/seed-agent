import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/scripts/apply-dsh-patches.ps1'
let text = readFileSync(path, 'utf8')
if (!text.includes("resources/dsh")) {
  const block = `
# 10e) 让 worker 能读到物理 dsh：把 prepared runtime 复制一份到 resources/dsh（app.asar 之外）
$ebExtra = Join-Path $dsh 'apps\\desktop\\scripts\\electron-builder-config.mjs'
if (Test-Path $ebExtra) {
  $ebExtraText = [System.IO.File]::ReadAllText($ebExtra)
  $runtimeLine = "      { from: buildPaths.runtime, to: 'runtime' },"
  if (-not $ebExtraText.Contains("resources/dsh") -and $ebExtraText.Contains($runtimeLine)) {
    $extra = $runtimeLine + "\`r\`n      // worker 子进程是普通 node，读不了 app.asar：把 runtime 再放一份到 resources/dsh。\`r\`n      { from: buildPaths.dsh, to: 'dsh' },"
    $ebExtraText = $ebExtraText.Replace($runtimeLine, $extra)
    [System.IO.File]::WriteAllText($ebExtra, $ebExtraText, (New-Object System.Text.UTF8Encoding($false)))
  }
}
`
  text = text.trimEnd() + '\n' + block
  writeFileSync(path, text, 'utf8')
  console.log('10e appended')
} else {
  console.log('already present')
}