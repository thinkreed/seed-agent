import { readFileSync, writeFileSync } from 'node:fs'

const path = 'E:/projects/reed-dev/seed-agent/scripts/package-seed-agent.ps1'
let text = readFileSync(path, 'utf8')
const start = text.indexOf('  # 3) 官方 unsigned 打包')
if (start < 0) throw new Error('tail marker missing')

const replacement = `  # 3) 先解包打包（脚本补物理 runtime 后再出安装包）
  & $node $pnpm --filter @deepseek-ai/dsh-desktop exec tsx scripts/package-target.ts win-x64 --dir --unsigned
  if ($LASTEXITCODE -ne 0) { throw 'desktop package --dir failed' }

  # 4) 把 prepared runtime 复制到 resources/dsh：worker 子进程是普通 node，读不了 app.asar
  $winUnpacked = Join-Path $dsh 'apps\\desktop\\.desktop-build\\targets\\win-x64\\unsigned-artifacts\\win-unpacked'
  $dshTarget = Join-Path $dsh 'apps\\desktop\\.desktop-build\\targets\\win-x64\\dsh'
  $resourcesDsh = Join-Path $winUnpacked 'resources\\dsh'
  & $node (Join-Path $Repo 'scripts\\copy-dsh-runtime.mjs') $dshTarget $resourcesDsh
  if ($LASTEXITCODE -ne 0) { throw 'copy dsh runtime failed' }

  # 5) 安装包：从 prepackaged 目录出 NSIS（不再二次打包 app）
  if (-not $Dir) {
    & $node $pnpm --filter @deepseek-ai/dsh-desktop exec electron-builder --win nsis --prepackaged $winUnpacked --config electron-builder.config.mjs --publish never
    if ($LASTEXITCODE -ne 0) { throw 'installer build failed' }
  }
  $code = $LASTEXITCODE
} finally { Pop-Location }
exit $code
`
text = text.slice(0, start) + replacement
writeFileSync(path, text, 'utf8')
console.log('package script tail rewritten')