const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const dependencyRoot = process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root;
const esbuild = require(path.join(dependencyRoot, 'node_modules/esbuild'));
const source = fs.readFileSync(path.join(root, 'review/member-map/site-entry.tsx'), 'utf8');
const compiled = esbuild.transformSync(source + '\nexport { loadSiteCanvas };', { loader: 'tsx', format: 'cjs', jsx: 'transform' }).code;
const mod = { exports: {} };
vm.runInNewContext(compiled, { module: mod, exports: mod.exports, TextDecoder, AbortController, Uint8Array,
  require(name) {
    if (name === 'react') return {};
    if (name === 'framer') return { addPropertyControls() {} };
    if (name === 'alphanest-site-map') return {};
    if (name === './company-structure-view') return {};
    throw Error('Unexpected dependency');
  } });
const load = mod.exports.loadSiteCanvas;
const html = fs.readFileSync(path.join(root, 'vercel-api/public/member-map-canvas.html'));

test('current opaque canvas is read without credentials or any login handoff', async () => {
  let call;
  const result = await load(async (url, options) => { call = { url, options }; return new Response(html, { headers: { 'content-type': 'text/html; charset=utf-8' } }); });
  assert.equal(result, html.toString());
  assert.equal(call.url, 'https://project-yw131.vercel.app/member-map-canvas');
  assert.equal(call.options.credentials, 'omit');
  assert.equal(call.options.redirect, 'error');
  assert.equal(call.options.referrerPolicy, 'no-referrer');
  assert.equal(call.options.headers, undefined);
});

for (const [name, bytes, type, reason] of [
  ['wrong MIME', html, 'application/json', 'canvas-response'],
  ['invalid UTF8', new Uint8Array([255]), 'text/html', null],
  ['oversized response', new Uint8Array(2 * 1024 * 1024 + 1), 'text/html', 'canvas-size'],
  ['missing protocol marker', '<!doctype html><html>unrelated</html>', 'text/html', 'canvas-shape'],
]) test('rejects ' + name, async () => {
  await assert.rejects(load(async () => new Response(bytes, { headers: { 'content-type': type } })), reason ? new RegExp(reason) : undefined);
});

test('same-site entries retain safe stock query and new-tab protections', () => {
  const files = ['PublicHoldingsTab.tsx', 'PublicStockBrief.tsx', 'PublicMobileNav.tsx'].map(name => fs.readFileSync(path.join(root, 'framer-components/public-probe', name), 'utf8'));
  assert.ok(files[0].includes('href="/mindmap"'));
  assert.ok(files[1].includes('href={tk ? "/mindmap?market="'));
  assert.ok(files[1].includes('encodeURIComponent(tk)'));
  assert.ok(files[1].includes('rel="noopener noreferrer"'));
  assert.ok(files[2].includes('props.mindmapPath || "/mindmap"'));
  const generated = fs.readFileSync(path.join(root, 'framer-components/public-probe/PublicMindmap.tsx'), 'utf8');
  assert.ok(generated.includes('export default function AlphaNestMindmap'));
  assert.equal(generated.includes('as default\n}'), false);
});
