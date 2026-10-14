// Lists t('...') messages in src that the English dictionary lacks, and dictionary entries no longer used.
// Usage: node scripts/i18n-check.mjs [--keys]  (exit code 1 when anything is missing)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(path.resolve('package.json'));
const { parse } = require('@babel/parser');

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === 'locales' ? [] : files(full);
    return /\.(jsx?|mjs)$/.test(entry.name) ? [full] : [];
  });
}

const keys = new Set();
for (const file of files('src')) {
  const ast = parse(fs.readFileSync(file, 'utf8'), { sourceType: 'module', plugins: ['jsx'] });
  (function visit(node) {
    if (!node || typeof node.type !== 'string') return;
    if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 't' && node.arguments[0]?.type === 'StringLiteral') keys.add(node.arguments[0].value);
    for (const [key, child] of Object.entries(node)) {
      if (['loc', 'start', 'end', 'extra'].includes(key)) continue;
      if (Array.isArray(child)) child.forEach(visit);
      else if (child && typeof child.type === 'string') visit(child);
    }
  })(ast.program);
}

const { default: en } = await import(path.resolve('src/locales/en.js').replace(/\\/g, '/').replace(/^([A-Z]):/, 'file:///$1:'));
const missing = [...keys].filter(key => !(key in en));
const unused = Object.keys(en).filter(key => !keys.has(key));
if (process.argv.includes('--keys')) console.log(JSON.stringify(missing, null, 1));
else {
  console.log(`messages=${keys.size} missing=${missing.length} unused=${unused.length}`);
  for (const key of missing) console.log('MISSING', key);
  for (const key of unused) console.log('UNUSED', key);
}
process.exitCode = missing.length ? 1 : 0;
