// Runs every *.browser.cjs against UI_TEST_URL (default: the Docker service on localhost:3001).
// The checks intercept /api/** with synthetic responses and write no account or chat data.
const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const files = fs.readdirSync(__dirname).filter(name => name.endsWith('.browser.cjs')).sort()
const failed = []
for (const name of files) {
  const run = spawnSync(process.execPath, [path.join(__dirname, name)], { encoding: 'utf8', env: process.env })
  const summary = (run.stdout + run.stderr).trim().split('\n').filter(Boolean).pop() || ''
  const ok = run.status === 0
  if (!ok) failed.push(name)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name} — ${summary.slice(0, 160)}`)
}
console.log(`${files.length - failed.length}/${files.length} browser checks passed`)
process.exitCode = failed.length ? 1 : 0
