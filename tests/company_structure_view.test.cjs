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
const style = source.match(/const CSS = `([\s\S]*?)`/)[1];
const styleRule = selector => style.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\{([^}]*)\\}`))[1];
const code = esbuild.transformSync(source, {
  loader: 'tsx', format: 'cjs', target: 'es2022',
}).code;
const box = { exports: {} };
vm.runInNewContext(code, {
  module: box,
  exports: box.exports,
  URL,
  TextDecoder,
  require(name) {
    if (name === 'react') return {};
    throw new Error(`unexpected module: ${name}`);
  },
}, { timeout: 1000 });
const { makeStructureLayout, validateStructure, loadCompanyStructure, structureCoverageText, resolveFocus, isFlowEligibleRelation, resetInitialFocusAfterInitialLoad, installStructureCameraInput } = box.exports;

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

test('CSS contract allows long or unbroken card and detail text to wrap or clip', () => {
  assert.match(source, /className="acs-name" title=\{n\.company\.name\}>\{n\.company\.name\}/);
  assert.ok(source.includes('title={`${focus?.name || "기업 구조"}의 주주·출자 연결`}'));
  assert.match(styleRule('.acs-toolbar>span'), /display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden/);
  assert.match(styleRule('.acs-card'), /width:224px/);
  assert.match(styleRule('.acs-card-main'), /min-width:0/);
  assert.match(styleRule('.acs-name'), /overflow:hidden;text-overflow:ellipsis;white-space:nowrap/);
  assert.match(styleRule('.acs-inspector'), /width:286px;max-width:40%;min-width:0/);
  assert.match(styleRule('.acs-inspector'), /overflow:auto/);
  for (const selector of ['.acs-inspector h2', '.acs-inspector p', '.acs-inspector summary', '.acs-inspector a']) {
    assert.match(styleRule(selector), /overflow-wrap:anywhere/);
  }
  assert.match(style, /\.acs-space\{[^}]*overflow:hidden/);
  const mobile = style.slice(style.indexOf('@media(max-width:700px)'));
  assert.match(mobile, /\.acs-inspector\{position:absolute;bottom:0;left:0;right:0;width:auto;max-width:none/);
});

test('relationship flow is a subtle stable overlay that preserves trust strokes and pauses for motion preferences', () => {
  const verified = relation('verified', 'KR:one', 'KR:two', { status: 'source-dated', evidence: [{ title: 'official', url: 'https://example.com/source' }] });
  const officialUndated = { ...verified, status: 'official-undated' };
  const unverified = { ...verified, status: 'undated-snapshot' };
  assert.equal(isFlowEligibleRelation(verified), true);
  assert.equal(isFlowEligibleRelation(officialUndated), true);
  assert.equal(isFlowEligibleRelation(unverified), false);
  assert.equal(isFlowEligibleRelation(undefined), false);
  assert.match(source, /<React\.Fragment key=\{n\.company\.id\}><path d=\{d\} data-undated=\{undated\} \/>\{flow && <path className="acs-flow" d=\{d\} aria-hidden="true" \/>\}<\/React\.Fragment>/);
  assert.match(source, /aria-pressed=\{flowPaused\} aria-label=\{flowPaused \? "선 움직임 켜기" : "선 움직임 멈추기"\} onClick=\{\(\) => setFlowPaused\(v => !v\)\}/);
  assert.match(source, /<svg className="acs-lines" data-flow-paused=\{flowPaused\}/);
  assert.match(styleRule('.acs-lines path'), /stroke:var\(--acs-line\);stroke-width:1\.5/);
  assert.match(styleRule('.acs-lines path[data-undated=true]'), /stroke-dasharray:4 4/);
  assert.match(styleRule('.acs-lines .acs-flow'), /stroke:var\(--acs-line\);stroke-width:2;stroke-linecap:round;stroke-dasharray:3 20;opacity:\.38;animation:acs-edge-flow 8s linear infinite/);
  assert.match(style, /@keyframes acs-edge-flow\{to\{stroke-dashoffset:-23\}\}/);
  assert.match(style, /\[data-motion=paused\] \.acs-flow\{animation-play-state:paused;visibility:hidden\}/);
  assert.match(style, /\.acs-lines\[data-flow-paused=true\] \.acs-flow\{animation-play-state:paused\}/);
  assert.match(style, /@media\(prefers-reduced-motion:reduce\)\{\.acs-flow\{display:none!important;animation:none!important\}\}/);
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

const catalogueFor = ticker => ({schema:'alphanest-company-structure-v1',companies:[{id:`KR:${ticker}`,ticker,market:'KR',name:'Fixture'}],relations:[],coverage:{sourceStatus:'not-attempted'}});
const responseFor = doc => new Response(JSON.stringify(doc),{headers:{'Content-Type':'application/json'}});
test('targeted reader accepts alphanumeric KR tickers and never sends member credentials', async () => {
  const calls=[]; const signal=new AbortController().signal;
  const value=await loadCompanyStructure({market:'KR',ticker:'0068Y0'},signal,async (url,init)=>{calls.push({url,init});return responseFor(catalogueFor('0068Y0'));});
  assert.equal(calls.length,1); assert.equal(calls[0].url,'/api/company_structure?market=KR&ticker=0068Y0');
  assert.equal(calls[0].init.credentials,'omit'); assert.equal(value.companies[0].ticker,'0068Y0');
  assert.match(structureCoverageText(value),/수집 대기/);
});
test('failed live reader labels retained data and does not invent a fresh clock', async () => {
  const old={...catalogueFor('000660'),observedAt:'2026-01-01T00:00:00Z'}; let calls=0;
  const value=await loadCompanyStructure({market:'KR',ticker:'000660'},new AbortController().signal,async()=>{if(calls++===0) throw Error('offline');return responseFor(old);});
  assert.equal(calls,2); assert.equal(value.observedAt,old.observedAt); assert.equal(value.coverage.fallback,true);
  assert.match(structureCoverageText(value),/이전 저장 자료/);
});
test('coverage status text distinguishes review, source gap, deferred, and attempting states', () => {
  const messages = {
    'needs-review': '원문 확보 · 관계 검수 보류 · 확인된 기존 근거만 유지',
    'source-gap': '관계 원문 미확보 · 관계가 없다는 뜻은 아니에요',
    'budget-deferred': '조회 예산에 따라 다음 수집 대기',
    attempting: '관계 원문을 확인하고 있어요',
  };
  for (const [sourceStatus, expected] of Object.entries(messages)) {
    assert.equal(structureCoverageText({ coverage: { sourceStatus } }), expected);
  }
  assert.equal(structureCoverageText({ coverage: { sourceStatus: 'refresh-error' } }), '최근 원문 조회 실패 · 이전 근거와 기준일 유지');
  assert.equal(structureCoverageText({ coverage: { sourceStatus: 'needs-review', fallback: true } }), '최신 조회 연결 실패 · 이전 저장 자료를 표시하고 있어요');
});
test('invalid ticker and cancelled reader never trigger a fallback request', async () => {
  let calls=0; const c=new AbortController(); c.abort();
  await assert.rejects(loadCompanyStructure({market:'KR',ticker:'../../etc'},c.signal,async()=>{calls++;}),/ticker/);
  await assert.rejects(loadCompanyStructure({market:'KR',ticker:'000660'},c.signal,async()=>{calls++;throw Error('aborted');}),/aborted/);
  assert.equal(calls,1);
});
test('two US securities mapped to one filing retain the canonical company connections', () => {
  const catalogue={schema:'alphanest-company-structure-v1',companies:[{id:'US:ABC',name:'ABC Corporation',market:'US',ticker:'ABC'},{id:'US:ABC.A',name:'ABC Class A',market:'US',ticker:'ABC.A'}],relations:[],coverage:{canonicalId:'US:ABC',securityIds:['US:ABC','US:ABC.A']}};
  assert.equal(resolveFocus(catalogue,{id:'US:ABC.A',name:'ABC Class A',market:'US',ticker:'ABC.A'}).id,'US:ABC');
});

test('only a successful initial catalogue load releases the focus-fit guard', () => {
  const initialFocus = { current: 'KR:CPK:false' };
  resetInitialFocusAfterInitialLoad(true, initialFocus);
  assert.equal(initialFocus.current, null);

  initialFocus.current = 'KR:AORT:false';
  resetInitialFocusAfterInitialLoad(false, initialFocus);
  assert.equal(initialFocus.current, 'KR:AORT:false');
});

function cameraInputFixture() {
  const listeners = new Map(), rect = { left: 10, top: 20, width: 800, height: 600 };
  const camera = { current: { x: 31, y: -17, zoom: .8 } }, updates = [];
  let dragging = false;
  const element = {
    getBoundingClientRect: () => rect,
    addEventListener(name, run, options) { listeners.set(name, { run, options }); },
    removeEventListener(name, run) { if (listeners.get(name)?.run === run) listeners.delete(name); },
  };
  const cleanup = installStructureCameraInput(element, camera, value => updates.push(value), () => dragging);
  const emit = (type, fields = {}) => {
    const event = { deltaX: 0, deltaY: 0, deltaMode: 0, clientX: 310, clientY: 220,
      ctrlKey: false, metaKey: false, shiftKey: false, prevented: false, stopped: false,
      preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...fields };
    listeners.get(type)?.run(event); return event;
  };
  return { camera, updates, listeners, rect, emit, cleanup, drag(value) { dragging = value; } };
}
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
const atPointer = f => ({ x: (300 - f.camera.current.x) / f.camera.current.zoom, y: (200 - f.camera.current.y) / f.camera.current.zoom });

test('ordinary two-finger wheel pans on first input and overlay cards without changing zoom or source geometry', () => {
  const f = cameraInputFixture();
  const catalogue = { schema: 'alphanest-company-structure-v1', companies: [company('focus'), company('child')], relations: [relation('edge','focus','child')] };
  const layout = makeStructureLayout(catalogue, company('focus'));
  const native = { catalogue, positions: [...layout.byId.values()].map(n => [n.company.id, n.x, n.y]), notes: { synthetic: 'unchanged' } };
  const before = structuredClone(native);
  const event = f.emit('wheel', { deltaX: 12, deltaY: 45, target: { tagName: 'BUTTON' } });
  near(f.camera.current.x, 19); near(f.camera.current.y, -62); near(f.camera.current.zoom, .8);
  assert.equal(event.prevented, true); assert.equal(event.stopped, true);
  f.emit('wheel', { deltaX: -12, deltaY: -45 });
  near(f.camera.current.x, 31); near(f.camera.current.y, -17);
  assert.deepEqual(native, before);
  assert.equal(f.listeners.get('wheel').options.capture, true);
  assert.equal(f.listeners.get('wheel').options.passive, false);
  assert.match(source, /installStructureCameraInput\(element, cameraRef, setCamera, \(\) => drag.current !== null\)/);
});

test('line/page deltas and Shift pan are normalized; nonfinite input never poisons the camera', () => {
  const f = cameraInputFixture();
  f.emit('wheel', { deltaX: 1, deltaY: 2, deltaMode: 1 }); near(f.camera.current.x, 15); near(f.camera.current.y, -49);
  f.emit('wheel', { deltaX: 1, deltaY: 1, deltaMode: 2 }); near(f.camera.current.x, -785); near(f.camera.current.y, -649);
  f.emit('wheel', { deltaY: 10, shiftKey: true }); near(f.camera.current.x, -795); near(f.camera.current.y, -649);
  const before = structuredClone(f.camera.current); f.emit('wheel', { deltaX: NaN, deltaY: 5 });
  assert.deepEqual({ ...f.camera.current }, before); near(f.camera.current.zoom, .8);
});

for (const modifier of ['ctrlKey', 'metaKey']) test(`${modifier} wheel pinches around a stable pointer anchor and composes before React rerenders`, () => {
  const f = cameraInputFixture(), anchor = atPointer(f);
  f.emit('wheel', { [modifier]: true, deltaY: -20 });
  f.emit('wheel', { [modifier]: true, deltaY: -20 });
  near(f.camera.current.zoom, .8 * Math.exp(.06)); near(atPointer(f).x, anchor.x); near(atPointer(f).y, anchor.y);
  f.emit('wheel', { [modifier]: true, deltaY: -100000 }); near(f.camera.current.zoom, 2.5);
  near(atPointer(f).x, anchor.x); near(atPointer(f).y, anchor.y);
  f.emit('wheel', { [modifier]: true, deltaY: 100000 }); near(f.camera.current.zoom, .12);
  near(atPointer(f).x, anchor.x); near(atPointer(f).y, anchor.y);
});

test('WebKit gesture uses its starting scale and anchor; duplicate wheel cannot zoom twice', () => {
  const f = cameraInputFixture(), anchor = atPointer(f);
  f.emit('gesturestart', { scale: 2 });
  f.emit('gesturechange', { scale: 3 }); near(f.camera.current.zoom, 1.2);
  near(atPointer(f).x, anchor.x); near(atPointer(f).y, anchor.y);
  const before = structuredClone(f.camera.current);
  f.emit('wheel', { ctrlKey: true, deltaY: -50 }); assert.deepEqual({ ...f.camera.current }, before);
  f.emit('gesturechange', { scale: 4, clientX: 330, clientY: 230 }); near(f.camera.current.zoom, 1.6);
  near((320 - f.camera.current.x) / 1.6, anchor.x); near((210 - f.camera.current.y) / 1.6, anchor.y);
  f.emit('gesturechange', { scale: NaN }); near(f.camera.current.zoom, 1.6);
  f.emit('gestureend'); f.emit('wheel', { deltaY: 10 }); near(f.camera.current.zoom, 1.6);
  near(f.camera.current.y, 210 - anchor.y * 1.6 - 10);
});

test('gesture without pointer coordinates anchors at center, active drag owns input, and unmount removes handlers', () => {
  const f = cameraInputFixture(), initial = structuredClone(f.camera.current);
  f.drag(true); f.emit('wheel', { deltaY: 20 }); f.emit('gesturestart', { scale: 1 }); f.emit('gesturechange', { scale: 2 });
  assert.deepEqual({ ...f.camera.current }, initial);
  f.drag(false); f.emit('gesturechange', { scale: 2 }); assert.deepEqual({ ...f.camera.current }, initial);
  f.emit('gesturestart', { scale: 1, clientX: undefined, clientY: undefined });
  const x = (400 - initial.x) / .8, y = (300 - initial.y) / .8;
  f.emit('gesturechange', { scale: 2, clientX: undefined, clientY: undefined });
  near((400 - f.camera.current.x) / 1.6, x); near((300 - f.camera.current.y) / 1.6, y);
  f.cleanup(); assert.equal(f.listeners.size, 0);
  const before = structuredClone(f.camera.current); f.emit('wheel', { deltaY: 20 }); assert.deepEqual({ ...f.camera.current }, before);
});
