/** Build the DSH core package directly from the canonical kernel at <repo>/src. */
import { existsSync, readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { spawnSync } from 'node:child_process'

function findRepo(start) {
  let dir = start
  for (;;) {
    const pkg = join(dir, 'package.json')
    if (existsSync(pkg)) {
      try {
        if (JSON.parse(readFileSync(pkg, 'utf8')).name === 'seed-superagent') return dir
      } catch {
        // keep walking
      }
    }
    const parent = dirname(dir)
    if (parent === dir) throw new Error('cannot locate seed-superagent repo root')
    dir = parent
  }
}

const core = process.cwd()
const repo = findRepo(core)
const tsc = join(repo, 'dsh', 'node_modules', 'typescript', 'bin', 'tsc')
const configPath = join(core, '.tsconfig.build.json')
const sourceRoot = relative(core, join(repo, 'src')).replaceAll('\\', '/')
const config = {
  extends: join(repo, 'dsh', 'tsconfig.base.json'),
  compilerOptions: {
    rootDir: sourceRoot,
    outDir: 'lib',
    composite: false,
    incremental: false,
    declaration: true,
    declarationMap: false,
    noEmit: false,
    exactOptionalPropertyTypes: false,
    noUnusedLocals: false,
    noUnusedParameters: false,
    typeRoots: [join(repo, 'dsh', 'node_modules', '@types')],
  },
  include: [`${sourceRoot}/**/*.ts`],
}
writeFileSync(configPath, JSON.stringify(config, null, 2))
try {
  const result = spawnSync(process.execPath, [tsc, '-p', configPath], { stdio: 'inherit' })
  if (result.status !== 0) process.exit(result.status ?? 1)
  // DSH 的 tsdown 约定入口是 lib/types/index.js；桥接到 tsc 生成的 lib/index.js。
  mkdirSync(join(core, 'lib', 'types'), { recursive: true })
  writeFileSync(join(core, 'lib', 'types', 'index.js'), "export * from '../index.js'\n")
} finally {
  rmSync(configPath, { force: true })
}