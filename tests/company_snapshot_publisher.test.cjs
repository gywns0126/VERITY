const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const test = require('node:test');
const { createHash } = require('node:crypto');
const publisher = require('../.github/actions/publish-data/publish_company_snapshots.cjs');
const { BASE, RELEASE, PARENT, PREFIX, SOURCES } = publisher;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = value => Buffer.from(JSON.stringify(value));
const TOKEN = 'vercel_blob_rw_rte5guenhonw9fzn_synthetic_only';
const moduleFile = path.join(__dirname, '../vercel-api/api/portfolio_core/portfolio_company_snapshot.py');

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'company-snapshot-publisher-'));
  const sourceBodies = Object.fromEntries(Object.keys(SOURCES).map(name => [name, json({ synthetic: name })]));
  const parent = { schema: 'portfolio-public-business-release-v1', artifact_sha256: '1'.repeat(64),
    source_revision: '2'.repeat(64), implementation_sha256: '3'.repeat(64), utc_day: new Date().toISOString().slice(0, 10) };
  const parentBytes = json(parent);
  const binding = { source_revision: '4'.repeat(64), parent_source_revision: parent.source_revision,
    implementation_sha256: parent.implementation_sha256, projection_sha256: sha(fs.readFileSync(moduleFile)),
    utc_day: parent.utc_day, scope: 'core-facts-disclosures' };
  const manifest = { schema: 'member-map-company-release-v1', ...binding,
    parent_receipt_sha256: sha(parentBytes), parent_artifact_sha256: parent.artifact_sha256,
    source_sha256: Object.fromEntries(Object.entries(sourceBodies).map(([name, bytes]) => [name, sha(bytes)])),
    company_count: 2, buckets: {} };
  for (const id of ['KR:000001', 'US:SYNTH']) {
    const bucket = sha(Buffer.from(id)).slice(0, 2);
    const company = { id, market: id.slice(0, 2), ticker: id.slice(3), name: 'Synthetic Company', sector: null,
      facts: [{ metric: 'revenue', value: 1, unit: 'KRW', as_of: '2024-12-31', source: 'DART' }, { metric: 'net_income', value: 2, unit: 'KRW', as_of: '2025', source: 'DART' }],
      documents: [{ id: 'doc:' + id, title: 'Synthetic filing', as_of: '2025-01-02', kind: 'disclosure', source: 'DART',
        url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250102000001' }] };
    const raw = json({ schema: 'member-map-company-bucket-v1', ...binding, companies: { [id]: company } });
    const digest = sha(raw); fs.writeFileSync(path.join(dir, digest + '.json'), raw);
    manifest.buckets[bucket] = { sha256: digest, bytes: raw.length, companies: 1 };
  }
  const saveManifest = () => fs.writeFileSync(path.join(dir, RELEASE), json(manifest));
  saveManifest();
  return { dir, manifest, parentBytes, sourceBodies, saveManifest,
    close: () => fs.rmSync(dir, { recursive: true, force: true }) };
}
function transport(f, { existing = false, expectedToken = TOKEN } = {}) {
  const store = new Map([[PARENT, f.parentBytes], ...Object.entries(f.sourceBodies)]), etags = new Map(), trace = [];
  if (existing) { store.set(RELEASE, json({ old: true })); etags.set(RELEASE, '"initial-etag"'); }
  let beforeGet = () => {}, beforePut = () => {}, version = 0;
  const response = (url, bytes, status, etag) => {
    const headers = { 'content-type': 'application/json' };
    if (bytes) headers['content-length'] = String(bytes.length);
    if (etag) headers.etag = etag;
    const value = new Response(bytes || null, { status, headers });
    Object.defineProperty(value, 'url', { value: url }); return value;
  };
  return { store, etags, trace, get beforeGet() { return beforeGet; }, set beforeGet(v) { beforeGet = v; },
    get beforePut() { return beforePut; }, set beforePut(v) { beforePut = v; },
    async fetch(url, options) {
      assert.equal(new URL(url).origin + '/', BASE); assert.equal(options.redirect, 'error');
      assert.equal(options.method, 'GET'); assert.equal(options.headers.Authorization, undefined);
      const name = url.slice(BASE.length); trace.push(['GET', name]); beforeGet(name);
      return response(url, store.get(name), store.has(name) ? 200 : 404, etags.get(name));
    },
    async put(name, bytes, options) {
      trace.push(['PUT', name]); beforePut(name, bytes, options);
      if (options.allowOverwrite === false && store.has(name)) throw Error('precondition');
      if (options.ifMatch && etags.get(name) !== options.ifMatch) throw Error('precondition');
      assert.equal(options.token, expectedToken); assert.equal(options.addRandomSuffix, false);
      store.set(name, Buffer.from(bytes)); etags.set(name, '"new-' + (++version) + '"');
      return { url: BASE + name, pathname: name };
    },
  };
}
async function run(f, t) { return publisher.publishCandidate(publisher.loadCandidate(f.dir), { ...t, token: TOKEN }); }

test('same store credential accepts mixed-case store ID and passes the token unchanged', async () => {
  const token = 'vercel_blob_rw_RtE5gUenHonW9fZn_SYNTHETIC_ONLY';
  const f = fixture(), t = transport(f, { expectedToken: token });
  try {
    const result = await publisher.publishCandidate(publisher.loadCandidate(f.dir), { ...t, token });
    assert.equal(result.release, 'published');
    assert.equal(t.trace.filter(([method]) => method === 'PUT').length, 3);
  } finally { f.close(); }
});

for (const token of ['vercel_blob_rw_rte5guenhonw9fzm_SYNTHETIC_ONLY',
  'vercel_blob_rw_rte5guenhonw9fznx_SYNTHETIC_ONLY', 'prefix_vercel_blob_rw_rte5guenhonw9fzn_SYNTHETIC_ONLY']) {
  test('other or malformed store credential is rejected before any request: ' + token, async () => {
    const f = fixture(), t = transport(f);
    try {
      await assert.rejects(publisher.publishCandidate(publisher.loadCandidate(f.dir), { ...t, token }),
        error => error.code === 'credential-store');
      assert.deepEqual(t.trace, []);
    } finally { f.close(); }
  });
}

test('closed local candidate validation retains exact original dates and bytes', () => {
  const f = fixture(); try {
    const data = publisher.loadCandidate(f.dir);
    assert.equal(data.payloads.size, 2); assert.equal(data.manifest.company_count, 2);
    for (const raw of data.payloads.values()) {
      const row = Object.values(JSON.parse(raw).companies)[0];
      assert.equal(row.facts[0].as_of, '2024-12-31'); assert.equal(row.facts[1].as_of, '2025'); assert.equal(row.documents[0].as_of, '2025-01-02');
      assert.equal(raw.length, f.manifest.buckets[sha(Buffer.from(row.id)).slice(0, 2)].bytes);
    }
  } finally { f.close(); }
});

for (const raw of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"a":NaN}', '{"a":1e999}', '{"a":1}garbage']) {
  test('strict parser rejects ambiguous or nonfinite JSON: ' + raw.slice(0, 16), () => {
    assert.throws(() => publisher.strictJson(Buffer.from(raw)));
  });
}
test('strict parser accepts nested values and escaped string contents', () => {
  const value = { a: [true, false, null, -1.25e10, '"\\\n'], nested: { b: 1 } };
  assert.deepEqual(publisher.strictJson(json(value)), value);
  assert.throws(() => publisher.strictJson(Buffer.from('{"a":"' + String.fromCharCode(0) + '"}')));
});

test('first publish validates six raw sources once, verifies immutable buckets, writes release last', async () => {
  const f = fixture(), t = transport(f);
  try {
    const result = await run(f, t); assert.equal(result.release, 'published');
    const firstPut = t.trace.findIndex(([method]) => method === 'PUT');
    for (const name of Object.keys(SOURCES)) {
      assert.equal(t.trace.filter(([method, n]) => method === 'GET' && n === name).length, 1);
      assert(t.trace.findIndex(([method, n]) => method === 'GET' && n === name) < firstPut);
    }
    const writes = t.trace.filter(([method]) => method === 'PUT');
    assert.equal(writes.at(-1)[1], RELEASE); assert.equal(writes.length, 3);
    assert(t.store.get(RELEASE).equals(fs.readFileSync(path.join(f.dir, RELEASE))));
    assert.equal(t.trace.filter(([method, name]) => method === 'GET' && name === PARENT).length, 3);
  } finally { f.close(); }
});

test('existing release uses the original first-GET ETag, immutable buckets never allow overwrite', async () => {
  const f = fixture(), t = transport(f, { existing: true });
  try {
    t.beforePut = (name, bytes, options) => {
      if (name === RELEASE) { assert.equal(options.ifMatch, '"initial-etag"'); assert.equal(options.allowOverwrite, true); }
      else { assert.equal(options.allowOverwrite, false); assert.equal(options.ifMatch, undefined); }
    };
    await run(f, t);
  } finally { f.close(); }
});

for (const failure of ['source', 'parent-initial', 'parent-after-sources', 'parent-before-release', 'bucket-write', 'bucket-readback', 'release-changed', 'release-cas-race']) {
  test('failure keeps previous release: ' + failure, async () => {
    const f = fixture(), t = transport(f, { existing: true });
    const previous = Buffer.from(t.store.get(RELEASE)); let parentReads = 0, releaseReads = 0;
    try {
      if (failure === 'source') t.store.set(Object.keys(SOURCES)[2], json({ changed: true }));
      if (failure === 'parent-initial') t.store.set(PARENT, json({ changed: true }));
      t.beforeGet = name => {
        if (name === PARENT) parentReads++;
        if (name === RELEASE) releaseReads++;
        if (failure === 'parent-after-sources' && name === PARENT && parentReads === 2 ||
            failure === 'parent-before-release' && name === PARENT && parentReads === 3) t.store.set(PARENT, json({ changed: true }));
        if (failure === 'bucket-readback' && name.startsWith(PREFIX) && t.store.has(name)) t.store.set(name, json({ changed: true }));
        if (failure === 'release-changed' && name === RELEASE && releaseReads === 2) t.store.set(RELEASE, json({ foreign: true }));
      };
      t.beforePut = name => {
        if (failure === 'bucket-write' && name.startsWith(PREFIX)) throw Error('secret=must-not-be-logged');
        if (failure === 'release-cas-race' && name === RELEASE) {
          t.store.set(RELEASE, json({ foreign: true })); t.etags.set(RELEASE, '"foreign-etag"');
        }
      };
      await assert.rejects(run(f, t));
      const expected = failure.startsWith('release-') ? json({ foreign: true }) : previous;
      assert(t.store.get(RELEASE).equals(expected));
      if (['source', 'parent-initial', 'parent-after-sources'].includes(failure)) assert.equal(t.trace.filter(([m]) => m === 'PUT').length, 0);
      if (failure !== 'release-cas-race') assert.equal(t.trace.filter(([m, n]) => m === 'PUT' && n === RELEASE).length, 0);
    } finally { f.close(); }
  });
}

test('create-only release rejects a concurrent creation instead of overwriting it', async () => {
  const f = fixture(), t = transport(f);
  try {
    t.beforePut = (name, bytes, options) => {
      if (name === RELEASE) { assert.equal(options.allowOverwrite, false); t.store.set(RELEASE, json({ foreign: true })); }
    };
    await assert.rejects(run(f, t)); assert(t.store.get(RELEASE).equals(json({ foreign: true })));
  } finally { f.close(); }
});

for (const corruption of ['generation', 'extra-fact-field', 'unknown-file', 'symlink', 'hash', 'denominator', 'projection']) {
  test('rejects corrupt local candidate before networking: ' + corruption, () => {
    const f = fixture(); try {
      const entry = Object.values(f.manifest.buckets)[0], file = path.join(f.dir, entry.sha256 + '.json');
      if (corruption === 'unknown-file') fs.writeFileSync(path.join(f.dir, 'notes.json'), '{}');
      else if (corruption === 'symlink') { fs.renameSync(file, file + '.real'); fs.symlinkSync(file + '.real', file); }
      else if (corruption === 'hash') fs.appendFileSync(file, ' ');
      else if (corruption === 'denominator') { f.manifest.company_count++; f.saveManifest(); }
      else if (corruption === 'projection') { f.manifest.projection_sha256 = '0'.repeat(64); f.saveManifest(); }
      else {
        const body = JSON.parse(fs.readFileSync(file));
        if (corruption === 'generation') body.source_revision = '0'.repeat(64);
        else Object.values(body.companies)[0].facts[0].member_note = 'must not publish';
        const raw = json(body), hash = sha(raw); fs.unlinkSync(file); fs.writeFileSync(path.join(f.dir, hash + '.json'), raw);
        entry.sha256 = hash; entry.bytes = raw.length; f.saveManifest();
      }
      assert.throws(() => publisher.loadCandidate(f.dir));
    } finally { f.close(); }
  });
}

test('public reads reject redirect, oversize stream, missing ETag, and bad store token without writes', async () => {
  await assert.rejects(publisher.readPublic('https://evil.invalid/', 100, () => assert.fail('network')));
  const requestUrl = BASE + PARENT;
  const fake = (body, url = requestUrl) => {
    const response = new Response(body, { headers: { 'content-type': 'application/json' } });
    Object.defineProperty(response, 'url', { value: url }); return response;
  };
  await assert.rejects(publisher.readPublic(PARENT, 4, async () => fake('12345')));
  await assert.rejects(publisher.readPublic(PARENT, 4096, async () => fake('{}', 'https://evil.invalid/')));
  const f = fixture(), t = transport(f, { existing: true });
  try {
    t.etags.delete(RELEASE); await assert.rejects(run(f, t));
    assert.equal(t.trace.filter(([m]) => m === 'PUT').length, 0);
    await assert.rejects(publisher.publishCandidate(publisher.loadCandidate(f.dir), { ...t, token: 'wrong-store' }));
  } finally { f.close(); }
});

test('CLI emits only a fixed HOLD diagnostic for unsafe local content', () => {
  const f = fixture();
  try {
    fs.writeFileSync(path.join(f.dir, RELEASE), '{"access_token":"secret-do-not-print"}');
    const { spawnSync } = require('node:child_process');
    const result = spawnSync(process.execPath, [path.join(__dirname, '../.github/actions/publish-data/publish_company_snapshots.cjs'),
      '--output-dir', f.dir], { encoding: 'utf8', env: {}, timeout: 5000 });
    assert.equal(result.status, 1); assert.equal(result.stdout, '');
    assert.equal(result.stderr.trim(), 'company snapshot candidate held');
  } finally { f.close(); }
});

const SUMMARY_FIELDS = ['status', 'reason_code', 'buckets', 'companies', 'manifest_sha256', 'manifest_bytes', 'parent_receipt_sha256', 'source_revision'].sort();
function summaryFolder() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'company-safe-summary-'));
  return { dir, file: path.join(dir, 'summary.json'), close: () => fs.rmSync(dir, { recursive: true, force: true }) };
}
function assertSafeSummary(file) {
  const raw = fs.readFileSync(file, 'utf8'), value = JSON.parse(raw);
  assert.deepEqual(Object.keys(value).sort(), SUMMARY_FIELDS);
  for (const forbidden of ['Synthetic Company', 'KR:000001', 'US:SYNTH', '2025-01-02', TOKEN,
    'access_token', 'secret-do-not-print', 'original-first-get-etag', 'portfolio_public_business']) assert(!raw.includes(forbidden));
  for (const key of ['manifest_sha256', 'parent_receipt_sha256', 'source_revision']) assert(value[key] === null || /^[0-9a-f]{64}$/u.test(value[key]));
  return value;
}
for (const desired of ['published', 'unchanged', 'held']) {
  test('safe summary preserves whitelist and publication result: ' + desired, async () => {
    const f = fixture(), t = transport(f), out = summaryFolder();
    try {
      const data = publisher.loadCandidate(f.dir);
      if (desired === 'unchanged') {
        t.store.set(RELEASE, data.manifestBytes); t.etags.set(RELEASE, '"same"');
        for (const [name, raw] of data.payloads) t.store.set(name, raw);
      }
      if (desired === 'held') t.store.set(Object.keys(SOURCES)[0], json({ changed: true }));
      const run = publisher.processCandidate(f.dir, { publish: true, summaryOutput: out.file,
        perform: candidate => publisher.publishCandidate(candidate, { ...t, token: TOKEN }) });
      if (desired === 'held') await assert.rejects(run); else await run;
      const summary = assertSafeSummary(out.file);
      assert.equal(summary.status, desired); assert.equal(summary.reason_code, desired === 'held' ? 'source-changed' : desired);
      assert.equal(summary.buckets, 2); assert.equal(summary.companies, 2);
      assert.equal(summary.manifest_sha256, sha(data.manifestBytes)); assert.equal(summary.manifest_bytes, data.manifestBytes.length);
      assert.equal(fs.statSync(out.file).mode & 0o777, 0o600);
    } finally { f.close(); out.close(); }
  });
}

test('unknown SDK failure text and invalid source body never enter held summary', async () => {
  const f = fixture(), out = summaryFolder();
  try {
    await assert.rejects(publisher.processCandidate(f.dir, { publish: true, summaryOutput: out.file,
      perform: async () => { throw Error('Bearer secret-do-not-print access_token=' + TOKEN); } }));
    const summary = assertSafeSummary(out.file);
    assert.equal(summary.status, 'held'); assert.equal(summary.reason_code, 'publisher-error');
  } finally { f.close(); out.close(); }
});

test('candidate rejection writes only held metadata with unknown counters', async () => {
  const f = fixture(), out = summaryFolder();
  try {
    fs.writeFileSync(path.join(f.dir, RELEASE), '{"access_token":"secret-do-not-print"}');
    await assert.rejects(publisher.processCandidate(f.dir, { summaryOutput: out.file }));
    const summary = assertSafeSummary(out.file);
    assert.equal(summary.status, 'held'); assert.equal(summary.companies, null); assert.equal(summary.manifest_sha256, null);
  } finally { f.close(); out.close(); }
});

for (const target of ['inside', 'symlink-inside', 'existing']) {
  test('summary path cannot alter candidate or existing files: ' + target, async () => {
    const f = fixture(), out = summaryFolder();
    try {
      const files = fs.readdirSync(f.dir).sort(); let file;
      if (target === 'inside') file = path.join(f.dir, 'summary.json');
      if (target === 'symlink-inside') { fs.symlinkSync(f.dir, path.join(out.dir, 'alias')); file = path.join(out.dir, 'alias', 'summary.json'); }
      if (target === 'existing') { file = out.file; fs.writeFileSync(file, 'preserve'); }
      await assert.rejects(publisher.processCandidate(f.dir, { publish: true, summaryOutput: file, perform: () => assert.fail('must not publish') }));
      assert.deepEqual(fs.readdirSync(f.dir).sort(), files);
      if (target === 'existing') assert.equal(fs.readFileSync(file, 'utf8'), 'preserve');
    } finally { f.close(); out.close(); }
  });
}

test('explicit summary option needs no environment destination and preflight cannot claim publication', async () => {
  const f = fixture(), out = summaryFolder();
  try {
    await publisher.main(['--output-dir', f.dir, '--summary-output', out.file]);
    const summary = assertSafeSummary(out.file);
    assert.equal(summary.status, 'held'); assert.equal(summary.reason_code, 'validation-only');
  } finally { f.close(); out.close(); }
});

test('SDK metadata resolves from entry without requiring an unexported package subpath', () => {
  const out = summaryFolder();
  try {
    const dist = path.join(out.dir, 'dist'); fs.mkdirSync(dist);
    const entry = path.join(dist, 'index.cjs'); fs.writeFileSync(entry, '');
    const metadataFile = path.join(out.dir, 'package.json');
    fs.writeFileSync(metadataFile, JSON.stringify({ name: '@vercel/blob', version: '2.4.1', exports: { '.': './dist/index.cjs' } }));
    const resolve = name => { assert.equal(name, '@vercel/blob'); return entry; };
    assert.equal(publisher.sdkMetadata(resolve).version, '2.4.1');
    fs.writeFileSync(metadataFile, JSON.stringify({ name: '@vercel/blob', version: '0.27.0' }));
    assert.throws(() => publisher.sdkMetadata(resolve));
  } finally { out.close(); }
});
