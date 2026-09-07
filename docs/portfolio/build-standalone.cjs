// Build a shareable HTML with embedded local screenshots. No dependencies or network.
const fs = require('node:fs')
const path = require('node:path')
let html = fs.readFileSync(path.join(__dirname, 'interview.html'), 'utf8')
for (const name of ['chat', 'source']) {
  const image = fs.readFileSync(path.join(__dirname, 'assets', `${name}.png`)).toString('base64')
  html = html.replaceAll(`assets/${name}.png`, `data:image/png;base64,${image}`)
}
fs.writeFileSync(path.join(__dirname, 'tax-ai-interview.html'), html, 'utf8')
console.log('Built docs/portfolio/tax-ai-interview.html (embedded screenshots)')
