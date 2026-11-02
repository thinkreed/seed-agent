import { cpSync, rmSync, statSync } from 'node:fs'
import { join } from 'node:path'

const [src, dst] = process.argv.slice(2)
if (!src || !dst) throw new Error('usage: node copy-dsh-runtime.mjs <src> <dst>')

rmSync(dst, { recursive: true, force: true })
cpSync(src, dst, {
  recursive: true,
  dereference: true,
  filter: (path) => !path.endsWith('node_modules/.cache'),
})
const bin = join(dst, 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')
try {
  statSync(bin)
  console.log(`copied dsh runtime -> ${dst}`)
} catch {
  throw new Error(`dsh bin missing after copy: ${bin}`)
}