import { defineConfig } from 'tsdown'

/** Bundle the Super-agent handback/unsubscribe tool plugin. */
export default defineConfig([
  {
    entry: ['lib/types/index.js'],
    outDir: 'lib',
    format: ['esm'],
    platform: 'node',
    target: 'es2024',
    fixedExtension: false,
    dts: false,
    clean: false,
    external: ['@deepseek-ai/cordis', '@deepseek-ai/dsh-tools', '@deepseek-ai/dsh-llm'],
  },
])