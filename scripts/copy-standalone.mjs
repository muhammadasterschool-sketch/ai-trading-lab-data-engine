// Cross-platform standalone copy — works on Windows, Linux and macOS.
// Replaces the Unix-only `cp -r` chain that used to break on Windows.
// Run automatically by `bun run build` (see package.json).
import { cpSync, existsSync, mkdirSync, rmSync } from 'fs'
import { join } from 'path'

const root = process.cwd()
const staticSrc = join(root, '.next', 'static')
const publicSrc = join(root, 'public')
const standalone = join(root, '.next', 'standalone')

if (!existsSync(standalone)) {
  console.error('[copy-standalone] .next/standalone missing - run "next build" first')
  process.exit(1)
}

// .next/static -> .next/standalone/.next/static
mkdirSync(join(standalone, '.next'), { recursive: true })
const staticDst = join(standalone, '.next', 'static')
rmSync(staticDst, { recursive: true, force: true })
cpSync(staticSrc, staticDst, { recursive: true })
console.log('[copy-standalone] static assets copied')

// public -> .next/standalone/public
const publicDst = join(standalone, 'public')
if (existsSync(publicSrc)) {
  rmSync(publicDst, { recursive: true, force: true })
  cpSync(publicSrc, publicDst, { recursive: true })
  console.log('[copy-standalone] public folder copied')
}

console.log('[copy-standalone] OK - standalone is self-contained')
