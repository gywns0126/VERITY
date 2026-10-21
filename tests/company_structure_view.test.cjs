const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const dependencyRoot = path.resolve(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root);
const projectRequire = createRequire(path.join(dependencyRoot, 'package.json'));
const esbuild = projectRequire('esbuild');
const source = fs.readFileSync(path.join(root, 'review/member-map/company-structure-view.tsx'), 'utf8');
const code = esbuild.transformSync(source, {
  loader: 'tsx', format: 'cjs', target: 'es2022',
}).code;
const box = { exports: {} };
vm.runInNewContext(code, {
  module: box,
  exports: box.exports,
  URL,
  require(name) {
    if (name === 'react') return {};
    throw new Error(`unexpected module: ${name}`);
  },
}, { timeout: 1000 });
const { makeStructureLayout, validateStructure } = box.exports;

const company = id => ({ id, name: `Company ${id}` });
const relation = (id, from, to, extra = {}) => ({
  id, from, to, type: 'investment', label: '투자 지분', asOf: null,
  status: 'undated-snapshot', ownershipPct: null, evidence: [], ...extra,
});

test('actual catalogue preserves dated and officially undated source evidence', () => {
  const catalogue = JSON.parse(fs.readFileSync(path.join(root, 'vercel-api/public/member-map-review/company-structure.json'), 'utf8'));
  assert.equal(catalogue.schema, 'alphanest-company-structure-v1');
  assert.equal(catalogue.companies.length, 570);
  assert.equal(catalogue.relations.length, 535);
  assert.strictEqual(validateStructure(catalogue), catalogue);

  const dated = catalogue.relations.find(r => r.type === 'major-shareholder' && r.from === 'KR:402340' && r.to === 'KR:000660');
  assert.equal(dated.asOf, '2026-05-06');
  assert.equal(dated.status, 'source-dated');
  assert.ok(dated.evidence.some(e => e.url === 'https://www.skhynix.com/ir/UI-FR-IR04/' && e.asOf === '2026-05-06'));

  const officialUndated = catalogue.relations.find(r => r.to === 'FOREIGN:solidigm-inc');
  assert.equal(officialUndated.asOf, null);
  assert.equal(officialUndated.status, 'official-undated');
  assert.ok(officialUndated.evidence.some(e => e.url === 'https://www.solidigm.com/support/faqs.html'));
  assert.ok(officialUndated.evidence.some(e => e.asOf === '2026-03-03'));
});

test('validator rejects duplicate company IDs and malformed evidence URLs', () => {
  const duplicate = {
    schema: 'alphanest-company-structure-v1',
    companies: [company('KR:one'), company('KR:one')], relations: [],
  };
  assert.throws(() => validateStructure(duplicate), /company/);

  const unsafeEvidence = {
    schema: 'alphanest-company-structure-v1',
    companies: [company('KR:one'), company('KR:two')],
    relations: [relation('edge', 'KR:one', 'KR:two', {
      evidence: [{ title: 'bad', url: 'javascript:alert(1)' }],
    })],
  };
  assert.throws(() => validateStructure(unsafeEvidence), /relation/);
});

test('layout terminates on cycles and duplicate edges without duplicating nodes', () => {
  const catalogue = {
    schema: 'alphanest-company-structure-v1',
    companies: ['focus', 'a', 'b'].map(company),
    relations: [
      relation('focus-a', 'focus', 'a'), relation('focus-a-duplicate', 'focus', 'a'),
      relation('a-focus', 'a', 'focus'), relation('a-b', 'a', 'b'), relation('b-a', 'b', 'a'),
    ],
  };
  const layout = makeStructureLayout(catalogue, company('focus'));
  assert.deepEqual([...layout.byId.keys()].sort(), ['a', 'b', 'focus']);
  assert.equal(layout.roots.length, 1);
  assert.equal(layout.roots[0], 'focus');
  for (const node of layout.byId.values()) {
    assert.equal(new Set(node.children).size, node.children.length);
    assert.ok(node.children.every(id => layout.byId.has(id)));
  }
});

test('layout caps each branch at six and spaces sibling cards without overlap', () => {
  const companies = ['focus', ...Array.from({ length: 8 }, (_, i) => `child-${i}`)].map(company);
  const relations = Array.from({ length: 8 }, (_, i) => relation(`edge-${i}`, 'focus', `child-${i}`));
  const layout = makeStructureLayout({ schema: 'alphanest-company-structure-v1', companies, relations }, company('focus'));
  const root = layout.byId.get('focus');
  assert.equal(root.children.length, 6);
  assert.equal(layout.byId.size, 7);
  const xs = root.children.map(id => layout.byId.get(id).x).sort((a, b) => a - b);
  assert.ok(xs.every((x, i) => i === 0 || x - xs[i - 1] >= 224), `overlapping child x positions: ${xs}`);
});

test('validation and layout leave the source catalogue unchanged', () => {
  const catalogue = {
    schema: 'alphanest-company-structure-v1',
    companies: [company('focus'), company('child')],
    relations: [relation('edge', 'focus', 'child')],
  };
  const before = structuredClone(catalogue);
  validateStructure(catalogue);
  makeStructureLayout(catalogue, company('focus'));
  assert.deepEqual(catalogue, before);
});
