'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { buildArtifacts, writeArtifacts, MAX_BYTES } = require('../scripts/member-map/build-live-company-structure.cjs');
const { loadArtifacts, publish, main, sanitizeUsSources, BASE, INDEX } = require('../scripts/member-map/publish-company-structure.cjs');
const at = '2026-10-21T10:00:00Z';
const sha = b => createHash('sha256').update(b).digest('hex');
function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'structure-publish-')); t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const dir = path.join(temp, 'public');
  const result = buildArtifacts({ listed: { '111111': { name: 'Issuer Corp.' } }, generatedAt: at,
    groups: { structures: { '111111': { collected_at: at, major_shareholders: [{ name: 'Holder Ltd.', ownership_pct: 30 }], subsidiaries: [] } } } });
  writeArtifacts(result, dir); return { dir, result };
}
function mock() {
  const store = new Map(), writes = [], reads = [];
  const options = { token: 'vercel_blob_rw_rte5guenhonw9fzn_OFFLINE_TEST_ONLY', pause: async () => {},
    fetch: async (url, opts) => {
      assert.ok(url.startsWith(BASE)); assert.equal(opts.redirect, 'error');
      const name = new URL(url).pathname.slice(1); reads.push(name);
      return store.has(name) ? new Response(store.get(name)) : new Response(null, { status: 404 });
    },
    head: async url => ({ etag: sha(store.get(url.slice(BASE.length))), url, pathname: url.slice(BASE.length) }),
    put: async (name, bytes, opts) => {
      assert.equal(opts.token, options.token); assert.equal(opts.addRandomSuffix, false); assert.equal(opts.access, 'public');
      if (store.has(name)) assert.equal(opts.ifMatch, sha(store.get(name)));
      else assert.equal(opts.allowOverwrite, false);
      writes.push(name); store.set(name, Buffer.from(bytes)); return { url: BASE + name };
    } };
  return { store, writes, reads, options };
}
function editPayload(dir, fn) {
  const m = JSON.parse(fs.readFileSync(path.join(dir, INDEX))), meta = m.issuers['KR:111111'];
  const p = JSON.parse(fs.readFileSync(path.join(dir, 'company-structure', meta.sha256 + '.json')));
  fn(p); const bytes = Buffer.from(JSON.stringify(p) + '\n'); meta.sha256 = sha(bytes); meta.bytes = bytes.length;
  fs.writeFileSync(path.join(dir, 'company-structure', meta.sha256 + '.json'), bytes);
  fs.writeFileSync(path.join(dir, INDEX), JSON.stringify(m) + '\n');
}
test('exact-byte artifacts validate offline, fixed-path payloads publish before manifest, repeat is read-only', async t => {
  const { dir, result } = fixture(t), remote = mock();
  assert.equal(loadArtifacts(dir).payloads.size, 1);
  const validation = await main(['--output-dir', dir]); assert.equal(validation.validated, true);
  await publish(dir, remote.options);
  assert.equal(remote.writes.at(-1), INDEX); assert.equal(remote.writes.length, 2);
  assert.ok(remote.store.get(INDEX).equals(result.manifestBytes));
  const before = remote.writes.length; await publish(dir, remote.options); assert.equal(remote.writes.length, before);
});
test('corrupted immutable bytes are repaired conditionally and exact readback is required', async t => {
  const { dir, result } = fixture(t), r = mock(); const key = `company-structure/${[...result.payloads.keys()][0]}.json`;
  r.store.set(key, Buffer.from('corrupt')); await publish(dir, r.options);
  assert.ok(r.store.get(key).equals([...result.payloads.values()][0])); assert.equal(r.writes.at(-1), INDEX);
});
test('payload upload failure or readback mismatch never writes the manifest', async t => {
  for (const mode of ['upload', 'readback']) {
    const { dir } = fixture(t), r = mock(), put = r.options.put;
    r.options.put = async (...args) => { if (mode === 'upload') throw Error('synthetic'); const value = await put(...args); r.store.set(args[0], Buffer.from('{}')); return value; };
    await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.includes(INDEX), false); assert.equal(r.store.has(INDEX), false);
  }
});
test('local hash/bytes, missing files, symlinks, max bytes and raw/personal/key fields fail before any write', async t => {
  for (const mutation of [p => p.sourceRow = { nm: 'PERSON' }, p => p.companies[0].email = 'private@example.com',
    p => p.coverage.api_key = 'private', p => p.relations[0].evidence = [{ title: 'unsafe', url: 'https://evil.example/raw' }],
    p => p.relations[0].from = p.relations[0].to, p => p.relations.push(...Array(3000).fill(p.relations[0]))]) {
    const { dir } = fixture(t), r = mock(); editPayload(dir, mutation);
    await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.length, 0); assert.equal(r.reads.length, 0);
  }
  const { dir, result } = fixture(t), r = mock(), file = path.join(dir, 'company-structure', [...result.payloads.keys()][0] + '.json');
  fs.appendFileSync(file, ' '); await assert.rejects(publish(dir, r.options));
  fs.unlinkSync(file); await assert.rejects(publish(dir, r.options));
  fs.symlinkSync(path.join(dir, INDEX), file); await assert.rejects(publish(dir, r.options));
  fs.unlinkSync(file); fs.writeFileSync(file, Buffer.alloc(MAX_BYTES + 1)); await assert.rejects(publish(dir, r.options));
  assert.equal(r.writes.length, 0);
});
test('manifest is path-free with closed schema, issuer bound and exact-byte count', async t => {
  for (const change of [m => m.rawResponse = {}, m => m.issuers['KR:111111'].url = 'https://evil.example/',
    m => m.issuers['KR:111111'].bytes++, m => { m.issuers = Object.fromEntries(Array.from({ length: 25001 }, (_, n) => [String(n), {}])); }]) {
    const { dir } = fixture(t), r = mock(), file = path.join(dir, INDEX), m = JSON.parse(fs.readFileSync(file)); change(m); fs.writeFileSync(file, JSON.stringify(m));
    await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.length, 0);
  }
});
test('a newer public manifest blocks rollback; concurrent manifest change blocks final write', async t => {
  const { dir } = fixture(t), r = mock();
  r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-22T00:00:00Z' })));
  await assert.rejects(publish(dir, r.options), /older/u); assert.equal(r.writes.length, 0);
  r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-20T00:00:00Z' })));
  const put = r.options.put;
  r.options.put = async (...args) => { const value = await put(...args); r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-21T09:00:00Z' }))); return value; };
  await assert.rejects(publish(dir, r.options), /changed/u); assert.equal(r.writes.includes(INDEX), false);
});
test('wrong store credential/endpoint, SDK destination and non-committed publication fail closed', async t => {
  const { dir } = fixture(t), r = mock();
  await assert.rejects(publish(dir, { ...r.options, token: 'other' })); assert.equal(r.writes.length, 0);
  r.options.put = async () => ({ url: 'https://other.public.blob.vercel-storage.com/a' });
  await assert.rejects(publish(dir, r.options), /store/u); assert.equal(r.writes.includes(INDEX), false);
  await assert.rejects(main(['--output-dir', dir, '--publish']));
  await assert.rejects(main(['--output-dir', dir, '--url', 'https://evil.example/']));
});
test('public US source projection retains budgets/failure/old document dates, drops raw/caches/private fields', () => {
  const doc = { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at,
    requestBudget: { day: '2026-10-21', requests: 2, ciks: ['0000001234'], private: 'secret' }, rawResponse: 'private',
    issuers: { '0000001234': { tickerAliases: ['ABC'], attemptStatus: 'HTTP429', attemptedAt: at, lastSuccessAt: '2026-10-03T10:00:00Z',
      exhibit: { schema: 'sec-company-subsidiaries-v1', cik: '0000001234', accession: '0000001234-26-000001',
        url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm', filedDate: '2026-02-01', periodEnd: '2025-12-31', documentSha256: 'a'.repeat(64), status: 'parsed',
        rows: [{ name: 'Sub Corp.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified', sourceRow: { text: 'private' } }] } } } };
  doc.issuers['0000001234'].exhibit.rows.push(
    { name: 'John Doe', ownershipPct: null, directOwnership: 'unspecified' },
    { name: 'Example Fund LLC', ownershipPct: null, directOwnership: 'unspecified' });
  const before = JSON.stringify(doc), safe = sanitizeUsSources(doc);
  assert.equal(JSON.stringify(doc), before); assert.equal(safe.requestBudget.requests, 2);
  assert.equal(safe.issuers['0000001234'].attemptStatus, 'HTTP429'); assert.equal(safe.issuers['0000001234'].exhibit.periodEnd, '2025-12-31');
  function inspect(value) {
    if (!value || typeof value !== 'object') { assert.notEqual(value, 'private'); assert.notEqual(value, 'secret'); return; }
    for (const [key, child] of Object.entries(value)) {
      assert.ok(!['private', 'rawResponse', 'sourceRow'].includes(key), `Forbidden raw/private key: ${key}`);
      inspect(child);
    }
  }
  inspect(safe); assert.equal(safe.issuers['0000001234'].exhibit.sourceRowCount, 3);
  assert.equal(safe.issuers['0000001234'].exhibit.corporateRowCount, 1);
  assert.equal(safe.issuers['0000001234'].exhibit.rows[0].jurisdiction, 'Delaware');
  doc.requestBudget.requests = 201; assert.throws(() => sanitizeUsSources(doc));
});

test('SEC 20-F-style list URL and retained HTTP403 status pass public validation without EX-21 or direct-control claims', async t => {
  const { dir } = fixture(t), output = path.join(path.dirname(dir), 'us-public');
  const result = buildArtifacts({ generatedAt: at, universe: { stocks: [{ ticker: 'ABC', market: 'US', name: 'ABC Corp.' }] }, cikMap: { ABC: '1234' }, strictSources: true,
    usSources: { schema: 'alphanest-company-structure-us-sources-v1', issuers: { '0000001234': {
      tickerAliases: ['ABC'], attemptedAt: at, lastSuccessAt: '2026-10-03T00:00:00Z', attemptStatus: 'HTTP403',
      exhibit: { schema: 'sec-company-subsidiaries-v1', cik: '0000001234', accession: '0000001234-26-000001',
        url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex81.htm', documentSha256: 'b'.repeat(64),
        filedDate: '2026-02-01', periodEnd: '2025-12-31', status: 'parsed',
        rows: [{ name: 'Sub Corp.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified' }] } } } } });
  writeArtifacts(result, output);
  const validated = loadArtifacts(output), p = [...validated.payloads.values()][0].payload;
  assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.attemptStatus, 'HTTP403'); assert.equal(p.coverage.status, 'refresh-error');
  assert.equal(p.relations[0].evidence[0].title.includes('EX-21'), false);
  assert.equal(p.relations[0].observedAt, '2026-10-03T00:00:00Z'); assert.equal(p.relations[0].ownershipPct, null);
  const r = mock(); await publish(output, r.options); assert.equal(r.writes.at(-1), INDEX);
});
test('workflow preserves schedule/concurrency, original annual backfill, explicit durable paths and no raw staging', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../.github/workflows/ownership_backfill.yml'), 'utf8');
  assert.match(source, /40 19 \* \* \*/u); assert.match(source, /group: verity-ownership-backfill/u); assert.match(source, /cancel-in-progress: false/u);
  assert.match(source, /--limit 100 --fetch-public/u); assert.match(source, /0 <= n <= 300/u);
  for (const file of ['member_map_company_structure_sources.json', 'member_map_company_structure_us_sources.json', INDEX, 'kr_ownership.json', 'metadata/kr_ownership_cursor.json']) assert.ok(source.includes('git add data/' + file));
  assert.match(source, /steps\.durable\.outcome == 'success'/u); assert.match(source, /git merge-base --is-ancestor HEAD origin\/main/u);
  assert.match(source, /git pull --rebase --autostash origin main\n\s+# Autostash[^\n]*\n\s+test -z "\$\(git ls-files -u\)"\n\s+git push origin HEAD:main/u);
  const publication = source.split('name: Publish verified immutable payloads then manifest')[1].split('name: Report collection failures')[0];
  assert.match(publication, /always\(\).*steps\.safe\.outcome == 'success'/u);
  assert.doesNotMatch(publication, /steps\.(?:kr|us)\.outcome/u);
  assert.match(source, /--source-dir "\$GITHUB_WORKSPACE\/data"/u);
  assert.doesNotMatch(source, /git add data\/$|git add .*raw|upload-artifact|kis_broker|KISBroker|build_mapping\(|sys\.modules/mu);
  assert.match(source, /python -m api\.builders\.ownership_backfill_builder/u);
  assert.match(source, /NOT a proven <=900 physical/u);
});

test('immutable uploads use at most four workers and drain in-flight failure before refusing manifest', async t => {
  for (const failUpload of [false, true]) {
    const { dir } = fixture(t);
    const listed = {}, structures = {};
    for (let n = 0; n < 9; n++) {
      const ticker = String(200000 + n); listed[ticker] = { name: `Issuer ${n} Corp.` };
      structures[ticker] = { collected_at: at, major_shareholders: [{ name: 'Holder Ltd.' }], subsidiaries: [] };
    }
    const result = buildArtifacts({ listed, groups: { structures }, generatedAt: at });
    const output = path.join(path.dirname(dir), 'parallel'); writeArtifacts(result, output);
    const r = mock(), put = r.options.put; let active = 0, peak = 0, calls = 0;
    r.options.put = async (...args) => {
      active++; peak = Math.max(peak, active); const ordinal = ++calls;
      try {
        await new Promise(resolve => setTimeout(resolve, 5));
        if (failUpload && ordinal === 1) throw Error('synthetic worker failure');
        return await put(...args);
      } finally { active--; }
    };
    if (failUpload) { await assert.rejects(publish(output, r.options)); assert.equal(r.writes.includes(INDEX), false); assert.ok(calls <= 4); }
    else { await publish(output, r.options); assert.equal(r.writes.at(-1), INDEX); assert.equal(r.writes.length, 10); }
    assert.equal(active, 0); assert.equal(peak, 4);
  }
});

test('actual workflow cadence uses remote KST-day attempts across all events, includes failed/cancelled, and fails closed', async () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../.github/workflows/ownership_backfill.yml'), 'utf8');
  const block = source.split('  cadence:\n')[1].split('  backfill:\n')[0];
  const script = block.split('script: |\n')[1].split('\n').map(line => line.replace(/^ {12}/u, '')).join('\n');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const runScript = new AsyncFunction('github', 'context', 'core', script);
  async function run(eventName, createdAt, previous = [], slot = '2026-10-21T19:40:00Z', failQuery = false) {
    const outputs = {}, queries = [];
    const context = { runId: 100, eventName, repo: { owner: 'offline', repo: 'offline' }, payload: {
      repository: { default_branch: 'main' }, client_payload: { schedule_slot: slot } } };
    const github = { rest: { actions: { getWorkflowRun: async () => ({ data: { created_at: createdAt, run_attempt: 1 } }), listWorkflowRuns: () => {} } },
      paginate: async (_, args) => {
        queries.push(args); assert.equal(args.workflow_id, 'ownership_backfill.yml'); assert.equal(args.branch, 'main');
        if (failQuery) throw Error('synthetic history lookup failure');
        return previous.filter(r => Date.parse(r.created_at) >= Date.parse(args.created.slice(2)));
      } };
    await runScript(github, context, { setOutput: (key, value) => outputs[key] = value, info: () => {} });
    return { outputs, queries };
  }
  const first = await run('repository_dispatch', '2026-10-21T19:41:00Z');
  assert.equal(first.outputs.run, 'true'); assert.equal(first.queries[0].created, '>=2026-10-21T15:00:00.000Z');
  for (const conclusion of ['failure', 'cancelled', null]) {
    const duplicate = await run('schedule', '2026-10-21T23:03:42Z', [{ id: 99, created_at: '2026-10-21T19:41:00Z', conclusion }]);
    assert.equal(duplicate.outputs.run, 'false'); assert.equal(duplicate.outputs.status, 'idle-already-attempted');
  }
  const manual = { id: 98, created_at: '2026-10-21T18:30:00Z', event: 'workflow_dispatch', conclusion: 'cancelled' };
  assert.equal((await run('schedule', '2026-10-21T19:40:00Z', [manual])).outputs.run, 'false');
  assert.equal((await run('workflow_dispatch', '2026-10-21T19:00:00Z', [manual])).outputs.run, 'false');
  const next = await run('workflow_dispatch', '2026-10-22T15:01:00Z', [{ ...manual, created_at: '2026-10-22T14:59:59Z' }]);
  assert.equal(next.outputs.run, 'true'); assert.equal(next.queries[0].created, '>=2026-10-22T15:00:00.000Z');
  await assert.rejects(run('schedule', '2026-10-21T22:36:54Z', [], undefined, true), /lookup/u);
  await assert.rejects(run('repository_dispatch', '2026-10-21T19:41:00Z', [], '2026-10-20T19:40:00Z'), /schedule_slot/u);
  assert.doesNotMatch(source, /^concurrency:/mu); assert.doesNotMatch(block, /concurrency:|if: github\.event_name/u);
  assert.match(source, /needs\.cadence\.result == 'success' && needs\.cadence\.outputs\.run == 'true'/u);
  assert.match(source, /repository_dispatch:\n\s+types: \[ownership_backfill\]/u);
  assert.match(source, /actions: read/u);
});

function cachedUsSource(review = false) {
  const cik = '0000001234', accession = '0000001234-26-000001';
  const exhibit = { schema: 'sec-company-subsidiaries-v1', cik, accession, filedDate: '2026-02-01', periodEnd: '2025-12-31',
    url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm', documentSha256: 'a'.repeat(64),
    status: review ? 'needs-review' : 'parsed', rows: [], html: 'PRIVATE', sourceRow: { text: 'PRIVATE' } };
  const source = { tickerAliases: ['ABC', 'ABC.A'], attemptStatus: review ? 'needs-review' : 'HTTP403', attemptedAt: at,
    metadataCheckedAt: at, filingMetadata: { issuer_id: 'US:ABC', issuer_name: 'ABC Corp.', cik, accession, filed_date: '2026-02-01',
      period_end: '2025-12-31', form: '10-K', primary_document: 'annual.htm',
      url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/annual.htm',
      filings: { recent: ['PRIVATE'] }, rawResponse: 'PRIVATE', member: { name: 'PRIVATE' } } };
  if (review) source.reviewExhibit = exhibit;
  else Object.assign(source, { exhibit, lastSuccessAt: '2026-10-03T10:00:00Z', checkedAt: '2026-10-03T10:00:00Z' });
  return { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at,
    issuers: { [cik]: source }, submissions: { raw: 'PRIVATE' }, member: 'PRIVATE' };
}

function cachedRefreshOffline(document, directory) {
  // Run the real tracked collector with every network/helper path forbidden.
  // Synthetic fixtures live only in the test directory; no source store is saved.
  const code = `
import importlib.util, json, sys
from datetime import datetime
from types import SimpleNamespace
spec = importlib.util.spec_from_file_location('offline_us_refresh', 'api/collectors/company_structure_us_refresh.py')
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
doc = json.load(sys.stdin)
now = datetime.fromisoformat('2026-10-22T10:00:00+00:00')
doc = core.build_document(sys.argv[1], doc, now)
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected source request/helper; saved metadata was not reused')
helpers = SimpleNamespace(get_public=forbidden, latest_metadata=forbidden, find_exhibit=forbidden, parse_exhibit=forbidden)
result, summary = core.refresh(doc, source_dir=sys.argv[1], limit=1, fetch_public=True, now=now,
    checkpoint=lambda _: None, helpers=helpers, clock=lambda: 0, sleep=lambda _: None)
print(json.dumps({'document': result, 'summary': summary}))
`;
  return JSON.parse(execFileSync('python3', ['-c', code, directory], { cwd: path.resolve(__dirname, '..'), input: JSON.stringify(document),
    encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, maxBuffer: 1024 * 1024 }));
}

test('US filing metadata round-trips durably and the real collector reuses it with zero synthetic HTTP calls', t => {
  const { dir } = fixture(t);
  fs.writeFileSync(path.join(dir, 'universe_search.json'), JSON.stringify({ stocks: [{ ticker: 'ABC', name: 'ABC Corp.', market: 'US' }] }));
  fs.writeFileSync(path.join(dir, 'sec_ticker_cik_map.json'), JSON.stringify({ ABC: '0000001234' }));
  const doc = cachedUsSource(), before = JSON.stringify(doc), safe = sanitizeUsSources(doc), source = safe.issuers['0000001234'];
  assert.equal(JSON.stringify(doc), before); assert.deepEqual(sanitizeUsSources(JSON.parse(JSON.stringify(safe))), safe);
  assert.equal(source.metadataCheckedAt, at); assert.equal(source.lastSuccessAt, '2026-10-03T10:00:00Z'); assert.equal(source.checkedAt, source.lastSuccessAt);
  assert.equal(source.filingMetadata.form, '10-K'); assert.equal(source.filingMetadata.primary_document, 'annual.htm');
  assert.ok(Buffer.byteLength(JSON.stringify(source.filingMetadata)) <= 4096);
  assert.equal(JSON.stringify(safe).includes('PRIVATE'), false);
  for (const key of ['filings', 'rawResponse', 'member']) assert.equal(Object.hasOwn(source.filingMetadata, key), false);
  const replay = cachedRefreshOffline(safe, dir), reused = replay.document.issuers['0000001234'];
  assert.equal(replay.summary.cached, 1); assert.equal(replay.summary.dailyRequests, 0); assert.equal(replay.summary.error, 0);
  assert.equal(reused.lastSuccessAt, source.lastSuccessAt); assert.equal(reused.metadataCheckedAt, at);
  assert.deepEqual(sanitizeUsSources(replay.document).issuers['0000001234'].filingMetadata, source.filingMetadata);
  const input = { universe: { stocks: [{ ticker: 'ABC', name: 'ABC Corp.', market: 'US' }] }, cikMap: { ABC: '1234' }, generatedAt: at };
  const first = buildArtifacts({ ...input, usSources: safe }).manifest.issuers['US:ABC'].sha256;
  const cacheOnlyUpdate = JSON.parse(JSON.stringify(safe)); cacheOnlyUpdate.issuers['0000001234'].metadataCheckedAt = '2026-10-22T10:00:00Z';
  assert.equal(buildArtifacts({ ...input, usSources: cacheOnlyUpdate }).manifest.issuers['US:ABC'].sha256, first);
  // A metadata check may find a newer filing without refreshing the old relationship snapshot.
  const newer = cachedUsSource(); newer.issuers['0000001234'].filingMetadata.filed_date = '2026-10-15';
  assert.equal(sanitizeUsSources(newer).issuers['0000001234'].lastSuccessAt, source.lastSuccessAt);
});

test('US cached filing metadata validates issuer identity, bounded fields, annual form, dates and exact SEC path', () => {
  const mutations = [
    (m, s) => m.cik = '0000009999', m => m.issuer_id = 'US:OTHER', m => m.issuer_id = 'KR:ABC',
    m => m.accession = '0000001234-26-000002', m => m.primary_document = '../annual.htm',
    m => m.url += '?token=PRIVATE', m => m.url = 'https://evil.example/annual.htm', m => m.form = '10-K/A',
    m => m.form = '6-K', m => m.period_end = '2026-03-01', m => m.filed_date = '2026-02-30',
    m => m.issuer_name = 'A'.repeat(181), m => m.issuer_name = '<html>PRIVATE</html>',
    (m, s) => s.metadataCheckedAt = null, (m, s) => s.metadataCheckedAt = '2026-02-30T10:00:00Z',
    (m, s) => s.metadataCheckedAt = '2026-01-31T10:00:00Z',
    (m, s) => s.metadataCheckedAt = '2026-10-21T24:00:00Z',
  ];
  for (const mutate of mutations) {
    const doc = cachedUsSource(), source = doc.issuers['0000001234']; mutate(source.filingMetadata, source);
    assert.throws(() => sanitizeUsSources(doc));
  }
  const foreign = cachedUsSource(); foreign.schema = 'another-source-v1'; assert.throws(() => sanitizeUsSources(foreign));
  foreign.schema = 'alphanest-company-structure-us-sources-v1'; foreign.issuers = true; assert.throws(() => sanitizeUsSources(foreign));
  const doc = cachedUsSource(); doc.issuers['0000001234'].filingMetadata.form = '20-F';
  assert.equal(sanitizeUsSources(doc).issuers['0000001234'].filingMetadata.form, '20-F');
  delete doc.issuers['0000001234'].filingMetadata;
  assert.equal(sanitizeUsSources(doc).issuers['0000001234'].metadataCheckedAt, undefined);
});

test('unresolved reviewExhibit retains only safe original identifiers for zero-HTTP reuse, never rows or source success', t => {
  const { dir } = fixture(t);
  fs.writeFileSync(path.join(dir, 'universe_search.json'), JSON.stringify({ stocks: [{ ticker: 'ABC', name: 'ABC Corp.', market: 'US' }] }));
  fs.writeFileSync(path.join(dir, 'sec_ticker_cik_map.json'), JSON.stringify({ ABC: '0000001234' }));
  const doc = cachedUsSource(true), safe = sanitizeUsSources(doc), source = safe.issuers['0000001234'];
  assert.equal(source.reviewExhibit.status, 'needs-review'); assert.equal(source.reviewExhibit.rows, undefined);
  assert.equal(source.lastSuccessAt, undefined); assert.equal(source.exhibit, undefined); assert.equal(JSON.stringify(safe).includes('PRIVATE'), false);
  assert.deepEqual(sanitizeUsSources(JSON.parse(JSON.stringify(safe))), safe);
  const replay = cachedRefreshOffline(safe, dir), reused = replay.document.issuers['0000001234'];
  assert.equal(replay.summary.cached, 1); assert.equal(replay.summary.dailyRequests, 0); assert.equal(reused.attemptStatus, 'needs-review');
  assert.equal(reused.lastSuccessAt, undefined); assert.equal(reused.exhibit, undefined);
  for (const mutate of [e => e.cik = '0000009999', e => e.accession = '0000001234-26-000002',
    e => e.url += '?member=PRIVATE', e => e.status = 'parsed', e => e.periodEnd = '2026-03-01', e => e.filedDate = '2026-02-30',
    e => e.schema = 'raw-html-v1', e => e.documentSha256 = 'PRIVATE']) {
    const invalid = cachedUsSource(true); mutate(invalid.issuers['0000001234'].reviewExhibit);
    const result = sanitizeUsSources(invalid).issuers['0000001234'];
    assert.equal(result.reviewExhibit, undefined); assert.equal(result.attemptStatus, 'needs-review'); assert.equal(result.lastSuccessAt, undefined);
  }
});
