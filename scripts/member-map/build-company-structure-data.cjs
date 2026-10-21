#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { makeCatalog } = require('../../review/member-map/company-structure-data.cjs');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  if (i < 0) return fallback;
  if (!process.argv[i + 1] || process.argv[i + 1].startsWith('--')) throw Error(`Missing value for ${name}`);
  return process.argv[i + 1];
}

const inputArg = arg('--input', null);
if (!inputArg) throw Error('Pass --input explicitly (the 39-issuer root snapshot, not the worktree copy)');
const input = path.resolve(inputArg);
const outputArg = arg('--output', null);
if (!outputArg) throw Error('Pass --output explicitly');
const output = path.resolve(outputArg);
const namesArg = arg('--names', null);
const sourcePaths = [input, ...(namesArg ? [path.resolve(namesArg)] : [])].map(p => fs.realpathSync(p));
const targetPath = fs.existsSync(output) ? fs.realpathSync(output) : output;
if (sourcePaths.includes(targetPath)) throw Error('Output must not overwrite an input');
const names = namesArg ? JSON.parse(fs.readFileSync(namesArg, 'utf8')) : {};
const catalog = makeCatalog(JSON.parse(fs.readFileSync(input, 'utf8')), { names });
if (catalog.coverage.sourceIssuers !== 39) throw Error(`Expected 39 source issuers, received ${catalog.coverage.sourceIssuers}`);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(catalog, null, 2)}\n`);
process.stdout.write(`${catalog.coverage.sourceIssuers} issuers → ${catalog.companies.length} companies, ${catalog.relations.length} relations\n`);
