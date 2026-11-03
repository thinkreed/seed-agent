/** Copy the canonical kernel sources into the DSH core package; run after editing src/**. */
import { copyFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = join(import.meta.dirname, '..')
const src = join(root, 'src')
const core = join(root, 'contrib', 'dsh', 'packages', 'super-agent', 'core', 'src')

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    return entry.isDirectory() ? walk(full) : [full]
  })
}

let copied = 0
for (const file of walk(src)) {
  if (!file.endsWith('.ts')) continue
  const rel = relative(src, file)
  // core 的 Engine 额外包含 Router 自动回复/批处理接入，属于 host 专属扩展。
  if (rel === 'engine.ts') continue
  const target = join(core, rel)
  try {
    if (!statSync(target).isFile()) continue
  } catch {
    continue
  }
  copyFileSync(file, target)
  copied += 1
}
console.log(`synced ${copied} kernel files to core`)