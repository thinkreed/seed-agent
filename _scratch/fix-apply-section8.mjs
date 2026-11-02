import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/scripts/apply-dsh-patches.ps1'
let text = readFileSync(path, 'utf8')
const start = text.indexOf('# 8) 把 Super-agent 包加入')
const end = text.indexOf('# 9) 打包冒烟')
if (start < 0 || end < 0) throw new Error('section markers not found')

const replacement = `# 8) 把 Super-agent 包加入 @deepseek-ai/dsh 的依赖闭包：桌面打包时随 runtime 一起安装
$cliPkg = Join-Path $dsh 'apps\\cli\\package.json'
if (Test-Path $cliPkg) {
  $cliText = [System.IO.File]::ReadAllText($cliPkg)
  $changed = $false
  if (-not $cliText.Contains('@deepseek-ai/dsh-super-agent-bundle')) {
    $bundleRow = '"@deepseek-ai/dsh-super-agent-bundle": "workspace:*",'
    $cliText = $cliText.Replace('"@deepseek-ai/dsh-client-ui-super-agent": "workspace:*",', '"@deepseek-ai/dsh-client-ui-super-agent": "workspace:*",' + "\`r\`n    " + $bundleRow)
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
    $rows = ($names | ForEach-Object { '    "{0}": "workspace:*",' -f $_ }) -join "\`r\`n"
    $cliText = [regex]::Replace($cliText, '("dependencies"\\s*:\\s*\\{)', "\`$1\`r\`n$rows", 1)
    $changed = $true
  }
  if ($changed) { [System.IO.File]::WriteAllText($cliPkg, $cliText, (New-Object System.Text.UTF8Encoding($false))) }
}
`
text = text.slice(0, start) + replacement + text.slice(end)
writeFileSync(path, text, 'utf8')
console.log('section 8 rewritten')