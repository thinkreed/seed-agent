import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/scripts/package-seed-agent.ps1'
let text = readFileSync(path, 'utf8')
const anchor = `  # 5) 安装包：从 prepackaged 目录出 NSIS（不再二次打包 app）`
if (!text.includes('4b) prepackaged')) {
  const envBlock = `  # 4b) prepackaged 构建需要打包环境变量（与官方 package-target 相同的 .env.windows）
  $envFile = Join-Path $dsh 'apps\\desktop\\.env.windows'
  if (Test-Path $envFile) {
    foreach ($line in [System.IO.File]::ReadAllLines($envFile)) {
      $trim = $line.Trim()
      if ($trim -eq '' -or $trim.StartsWith('#')) { continue }
      $eq = $trim.IndexOf('=')
      if ($eq -gt 0) { [Environment]::SetEnvironmentVariable($trim.Substring(0, $eq).Trim(), $trim.Substring($eq + 1).Trim(), 'Process') }
    }
  }

`
  text = text.replace(anchor, envBlock + anchor)
  writeFileSync(path, text, 'utf8')
  console.log('env block inserted')
} else {
  console.log('already present')
}