'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { buildArtifacts, writeArtifacts, usCooperatieLabel, MAX_BYTES } = require('../scripts/member-map/build-live-company-structure.cjs');
const { loadArtifacts, publish, main, sanitizeUsSources, BASE, INDEX } = require('../scripts/member-map/publish-company-structure.cjs');
const at = '2026-10-21T10:00:00Z';
const parserRevision = /^PARSER_REVISION = "([^"]+)"$/m.exec(fs.readFileSync(path.join(__dirname, '../api/intelligence/company_structure_sec.py'), 'utf8'))[1];
const sha = b => createHash('sha256').update(b).digest('hex');
function fixture(t) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'structure-publish-')); t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const dir = path.join(temp, 'public');
  const result = buildArtifacts({ listed: { '111111': { name: 'Issuer Corp.' } }, generatedAt: at,
    groups: { structures: { '111111': { collected_at: at, major_shareholders: [{ name: 'Holder Ltd.', ownership_pct: 30 }], subsidiaries: [] } } } });
  writeArtifacts(result, dir); return { dir, result };
}
function mock() {
  const store = new Map(), writes = [], reads = [], diagnostics = [], readWarnings = []; let now = 0;
  const options = { token: 'vercel_blob_rw_rte5guenhonw9fzn_OFFLINE_TEST_ONLY', pause: async ms => { now += ms; }, clock: () => now,
    diagnostic: value => diagnostics.push(value), readWarning: value => readWarnings.push(value),
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
  return { store, writes, reads, diagnostics, readWarnings, options };
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
  await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.length, 0);
  assert.deepEqual(r.diagnostics.at(-1), { stage: 'initial-manifest-read', category: 'manifest-older' });
  r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-20T00:00:00Z' })));
  const put = r.options.put;
  r.options.put = async (...args) => { const value = await put(...args); r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-21T09:00:00Z' }))); return value; };
  await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.includes(INDEX), false);
  assert.deepEqual(r.diagnostics.at(-1), { stage: 'manifest-cas', category: 'manifest-changed' });
});
test('wrong store credential/endpoint, SDK destination and non-committed publication fail closed', async t => {
  const { dir } = fixture(t), r = mock();
  await assert.rejects(publish(dir, { ...r.options, token: 'other' })); assert.equal(r.writes.length, 0);
  r.options.put = async () => ({ url: 'https://other.public.blob.vercel-storage.com/a' });
  await assert.rejects(publish(dir, r.options)); assert.equal(r.writes.includes(INDEX), false);
  assert.deepEqual(r.diagnostics.at(-1), { stage: 'payload-write', category: 'destination-mismatch' });
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
  doc.requestBudget.requests = 2400;
  doc.requestBudget.ciks = Array.from({ length: 800 }, (_, i) => String(i + 1).padStart(10, '0'));
  assert.deepEqual(sanitizeUsSources(doc).requestBudget, { day: '2026-10-21', requests: 2400, ciks: doc.requestBudget.ciks });
  doc.requestBudget.requests = 2401; assert.throws(() => sanitizeUsSources(doc));
  doc.requestBudget.requests = 2400; doc.requestBudget.ciks.push('0000000801'); assert.throws(() => sanitizeUsSources(doc));
  doc.requestBudget.ciks.pop(); doc.requestBudget.ciks[0] = doc.requestBudget.ciks[1]; assert.throws(() => sanitizeUsSources(doc));
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
  assert.equal(p.relations.length, 1); // A failed refresh retains the verified prior relationship.
  assert.equal(p.relations[0].evidence[0].title.includes('EX-21'), false);
  assert.equal(p.relations[0].observedAt, '2026-10-03T00:00:00Z'); assert.equal(p.relations[0].ownershipPct, null);
  const r = mock(); await publish(output, r.options); assert.equal(r.writes.at(-1), INDEX);
});
test('workflow preserves schedule/concurrency, original annual backfill, explicit durable paths and no raw staging', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../.github/workflows/ownership_backfill.yml'), 'utf8');
  assert.match(source, /40 19 \* \* \*/u); assert.match(source, /group: verity-ownership-backfill/u); assert.match(source, /cancel-in-progress: false/u);
  assert.match(source, /--limit 800 --fetch-public/u); assert.match(source, /0 <= n <= 400/u);
  assert.match(source, /print\(min\(n, 300\)\)/u);
  for (const file of ['member_map_company_structure_sources.json', 'member_map_company_structure_us_sources.json', INDEX, 'kr_ownership.json', 'metadata/kr_ownership_cursor.json']) assert.ok(source.includes('git add data/' + file));
  assert.match(source, /steps\.durable\.outcome == 'success'/u); assert.match(source, /git merge-base --is-ancestor HEAD origin\/main/u);
  const durable = ownershipWorkflow().jobs.backfill.steps.find(s => s.id === 'durable').run;
  assert.match(durable, /git pull --rebase --autostash origin main\n\s+# Autostash[^\n]*\n\s+test -z "\$\(git ls-files -u\)"/u);
  assert.ok(durable.indexOf('test -z "$(git ls-files -u)"') < durable.indexOf('git push origin HEAD:main'));
  assert.ok(durable.includes('git diff --quiet "$persist_head" HEAD -- "${persist_paths[@]}"'));
  const publication = source.split('name: Publish verified immutable payloads then manifest')[1].split('name: Report collection failures')[0];
  assert.match(publication, /always\(\).*steps\.safe\.outcome == 'success'/u);
  assert.doesNotMatch(publication, /steps\.(?:kr|us)\.outcome/u);
  assert.match(source, /--source-dir "\$GITHUB_WORKSPACE\/data"/u);
  assert.doesNotMatch(source, /git add data\/$|git add .*raw|upload-artifact|kis_broker|KISBroker|build_mapping\(|sys\.modules/mu);
  assert.match(source, /python -m api\.builders\.ownership_backfill_builder/u);
  assert.match(source, /NOT a proven <=1100 physical/u);
});

function ownershipWorkflow() {
  return JSON.parse(execFileSync('python3', ['-c',
    'import json,yaml; print(json.dumps(yaml.safe_load(open(".github/workflows/ownership_backfill.yml"))))'],
  { cwd: path.resolve(__dirname, '..'), encoding: 'utf8' }));
}

test('publish-only is manual/main exclusive, collection still requires the daily guard, and credential checks precede source calls', () => {
  const doc = ownershipWorkflow(), triggers = doc.on || doc.true;
  assert.deepEqual(triggers.workflow_dispatch.inputs.publish_only, {
    description: 'Publish saved main sources only; no collection (counts as a daily attempt)', required: false, default: false, type: 'boolean' });
  const backfill = doc.jobs.backfill, recovery = doc.jobs['publish-only'];
  const eligible = (job, event, selected, daily, ref = 'refs/heads/main') => new Function('github', 'inputs', 'needs', 'always', 'cancelled',
    `return (${job.if})`)({ event_name: event, ref }, { publish_only: selected },
    { cadence: { result: 'success', outputs: { run: String(daily) } } }, () => true, () => false);
  for (const event of ['workflow_dispatch', 'repository_dispatch', 'schedule']) for (const selected of [true, false]) for (const daily of [true, false]) {
    const publishOnly = event === 'workflow_dispatch' && selected;
    assert.equal(eligible(backfill, event, selected, daily), daily && !publishOnly);
    assert.equal(eligible(recovery, event, selected, daily), publishOnly);
    assert.equal(eligible(recovery, event, selected, daily, 'refs/heads/other'), false);
  }
  assert.equal(recovery.needs, undefined); assert.deepEqual(recovery.concurrency, backfill.concurrency);
  assert.equal(recovery.concurrency['cancel-in-progress'], false);
  for (const job of [backfill, recovery]) {
    assert.equal(job.steps[0].with['fetch-depth'], 100);
    assert.equal(job.env, undefined);
    const check = job.steps.find(s => s.name === 'Check existing publication credential before source calls');
    assert.deepEqual(check.env, { BLOB_READ_WRITE_TOKEN: '${{ secrets.VERCEL_BLOB_TOKEN }}' });
    assert.equal(job.steps.indexOf(check), 1);
    for (const step of job.steps) {
      if (step.env?.BLOB_READ_WRITE_TOKEN) assert.ok(step === check || step.name === 'Publish verified immutable payloads then manifest');
      assert.equal(JSON.stringify(step).includes('secrets.BLOB_READ_WRITE_TOKEN'), false);
    }
    assert.throws(() => execFileSync('bash', ['-c', check.run], { env: { PATH: process.env.PATH, BLOB_READ_WRITE_TOKEN: '' }, stdio: 'pipe' }));
    const dummy = 'OFFLINE_DUMMY_DO_NOT_LOG';
    assert.equal(execFileSync('bash', ['-c', check.run], { env: { PATH: process.env.PATH, BLOB_READ_WRITE_TOKEN: dummy }, encoding: 'utf8' }).includes(dummy), false);
  }
});

test('publish-only reuses offline validation/publication steps and persists index alone with fail-closed replay binding', () => {
  const doc = ownershipWorkflow(), normal = doc.jobs.backfill.steps, steps = doc.jobs['publish-only'].steps;
  assert.equal(steps[0].with.ref, 'main'); assert.equal(steps[0].with['fetch-depth'], 100);
  for (const name of ['Install existing Blob dependency', 'Build and validate compact public artifacts offline', 'Publish verified immutable payloads then manifest']) {
    assert.deepEqual(steps.find(s => s.name === name), normal.find(s => s.name === name));
  }
  const scripts = steps.map(s => s.run || '').join('\n');
  assert.doesNotMatch(scripts, /--fetch-public|refresh-company|refresh-us|sanitize|atomic_json|rawResponse|DART_API_KEY|ownership_backfill_builder/u);
  const durable = steps.find(s => s.id === 'durable').run;
  assert.deepEqual([...durable.matchAll(/^git add (.+)$/gmu)].map(m => m[1]), ['data/member_map_company_structure_index.json']);
  assert.match(durable, /set -euo pipefail/u); assert.match(durable, /git pull --rebase --autostash origin main/u);
  assert.match(durable, /test -z "\$\(git ls-files -u\)"/u);
  assert.match(durable, /git diff --quiet "\$SOURCE_HEAD" HEAD -- .*data\/member_map_company_structure_sources.json .*data\/member_map_company_structure_us_sources.json/u);
  assert.ok(durable.indexOf('git diff --quiet "$SOURCE_HEAD" HEAD') < durable.indexOf('git push origin HEAD:main'));
  assert.match(durable, /git merge-base --is-ancestor HEAD origin\/main/u);
  assert.doesNotMatch(durable, /\|\| true|-X (?:ours|theirs)/u);
  const publication = steps.at(-1);
  for (const id of ['safe', 'build', 'durable']) assert.ok(publication.if.includes(`steps.${id}.outcome == 'success'`));
  assert.match(publication.run, /--committed-manifest data\/member_map_company_structure_index.json --publish$/u);
});

test('actual publish-only durable shell stops on rebase, conflict, input drift or push failure without running later commands', () => {
  const script = ownershipWorkflow().jobs['publish-only'].steps.find(s => s.id === 'durable').run;
  const stub = `git() {
    printf 'MOCK git %s\\n' "$*" >&2
    case "$*" in
      'pull --rebase --autostash origin main') [ "$FAIL_AT" != rebase ] ;;
      'ls-files -u') if [ "$FAIL_AT" = conflict ]; then printf 'unmerged'; fi ;;
      'diff --quiet offline-head HEAD -- '*) [ "$FAIL_AT" != inputs ] ;;
      'push origin HEAD:main') [ "$FAIL_AT" != push ] ;;
      *) return 0 ;;
    esac
  }\n`;
  for (const failAt of ['rebase', 'conflict', 'inputs', 'push']) {
    let error;
    try { execFileSync('bash', ['-c', stub + script], { env: { PATH: process.env.PATH, SOURCE_HEAD: 'offline-head', FAIL_AT: failAt }, stdio: 'pipe' }); }
    catch (e) { error = e; }
    assert.ok(error, failAt); const log = error.stderr.toString();
    // A refused push now reads main once to distinguish a race from a fixed rejection.
    assert.equal(log.includes('MOCK git fetch origin main'), failAt === 'push');
    if (failAt !== 'push') assert.equal(log.includes('MOCK git push origin HEAD:main'), false);
  }
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

test('one shared pacing gate spaces aggregate GET/HEAD/PUT starts by at least 100ms while retaining four workers', async t => {
  const { dir } = fixture(t), listed = {}, structures = {};
  for (let n = 0; n < 9; n++) {
    const ticker = String(300000 + n); listed[ticker] = { name: `Issuer ${n} Corp.` };
    structures[ticker] = { collected_at: at, major_shareholders: [{ name: 'Holder Ltd.' }], subsidiaries: [] };
  }
  const result = buildArtifacts({ listed, groups: { structures }, generatedAt: at });
  const output = path.join(path.dirname(dir), 'paced'); writeArtifacts(result, output);
  const r = mock(), starts = []; let active = 0, peak = 0;
  r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-20T00:00:00Z' })));
  for (const key of [...result.payloads.keys()].slice(0, 4)) r.store.set(`company-structure/${key}.json`, Buffer.from('corrupt'));
  for (const kind of ['fetch', 'head', 'put']) {
    const action = r.options[kind];
    r.options[kind] = async (...args) => {
      starts.push({ kind, at: r.options.clock() }); active++; peak = Math.max(peak, active);
      try { await new Promise(resolve => setImmediate(resolve)); return await action(...args); }
      finally { active--; }
    };
  }
  await publish(output, r.options);
  assert.equal(active, 0); assert.equal(peak, 4);
  assert.deepEqual(new Set(starts.map(s => s.kind)), new Set(['fetch', 'head', 'put']));
  for (let i = 1; i < starts.length; i++) assert.ok(starts[i].at - starts[i - 1].at >= 100);
  for (const start of starts) assert.ok(starts.filter(s => s.at >= start.at && s.at < start.at + 1000).length <= 10);
  assert.equal(r.writes.at(-1), INDEX); assert.equal(r.writes.length, 10);
  assert.equal(new Set(r.writes).size, r.writes.length); // No write retry.
});

test('fixed diagnostics identify every remote stage, redact HTTP bodies/SDK messages and preserve manifest-last failure boundaries', async t => {
  const cases = [
    ['initial-manifest-read', 'fetch', 'http', 429], ['payload-read', 'fetch', 'http', 503],
    ['payload-metadata', 'head', 'sdk', 'BlobAccessError'], ['manifest-metadata', 'head', 'sdk', 'BlobStoreSuspendedError'],
    ['payload-write', 'put', 'sdk', 'BlobServiceRateLimited'], ['payload-readback', 'fetch', 'http', 403],
    ['manifest-cas', 'fetch', 'http', 409], ['manifest-write', 'put', 'sdk', 'BlobPreconditionFailedError'],
    ['manifest-readback', 'fetch', 'http', 502],
  ];
  const secret = 'vercel_blob_rw_PRIVATE Bearer PRIVATE https://private.example/raw?token=PRIVATE ENV_PRIVATE';
  for (const [stage, method, category, detail] of cases) {
    const { dir, result } = fixture(t), r = mock(); let indexReads = 0, failures = 0;
    if (stage === 'manifest-metadata') r.store.set(INDEX, Buffer.from(JSON.stringify({ generatedAt: '2026-10-20T00:00:00Z' })));
    if (stage === 'payload-metadata') r.store.set(`company-structure/${[...result.payloads.keys()][0]}.json`, Buffer.from('corrupt'));
    const action = r.options[method];
    r.options[method] = async (...args) => {
      const name = method === 'put' ? args[0] : new URL(args[0]).pathname.slice(1), isIndex = name === INDEX;
      if (method === 'fetch' && isIndex) indexReads++;
      const actualStage = method === 'head' ? (isIndex ? 'manifest-metadata' : 'payload-metadata') :
        method === 'put' ? (isIndex ? 'manifest-write' : 'payload-write') :
        isIndex ? (r.writes.includes(INDEX) ? 'manifest-readback' : indexReads === 1 || stage === 'initial-manifest-read' && indexReads <= 3 ? 'initial-manifest-read' : 'manifest-cas') :
        r.writes.includes(name) ? 'payload-readback' : 'payload-read';
      if (actualStage === stage) {
        failures++;
        if (category === 'http') return new Response(secret, { status: detail });
        const error = new Error(secret); error.name = detail; error.body = secret; error.url = secret; error.env = secret;
        throw error;
      }
      return action(...args);
    };
    await assert.rejects(publish(dir, r.options), error => {
      assert.equal(error.message, 'Company structure publication failed'); assert.equal(error.cause, undefined); return true;
    });
    const attempts = category === 'http' && [429, 500, 502, 503, 504].includes(detail) ? 3 : 1;
    assert.equal(failures, attempts); assert.equal(r.diagnostics.length, 1);
    assert.equal(r.readWarnings.length, attempts - 1);
    assert.equal(JSON.stringify(r.readWarnings).includes('PRIVATE'), false);
    assert.deepEqual(r.diagnostics[0], { stage, category, ...(category === 'http' ? { httpStatus: detail } : { errorClass: detail }) });
    assert.equal(JSON.stringify(r.diagnostics).includes('PRIVATE'), false);
    assert.equal(new Set(r.writes).size, r.writes.length);
    if (stage !== 'manifest-readback') assert.equal(r.writes.includes(INDEX), false);
    else assert.equal(r.writes.at(-1), INDEX); // Already-written bytes are never reported as confirmed.
  }
});

test('transient GET readback recovery is bounded, paced and never rewrites an already uploaded payload', async t => {
  for (const status of [429, 500, 502, 503, 504]) {
    const { dir } = fixture(t), r = mock(); const fetch = r.options.fetch; let failures = 0;
    r.options.fetch = async (...args) => {
      const name = new URL(args[0]).pathname.slice(1);
      if (name !== INDEX && r.writes.includes(name) && failures < 2) {
        failures++; return new Response('PRIVATE_TOKEN https://secret.example', { status });
      }
      return fetch(...args);
    };
    const result = await publish(dir, r.options);
    assert.equal(failures, 2); assert.equal(result.uploaded, 2);
    assert.equal(r.writes.length, 2); assert.equal(new Set(r.writes).size, 2);
    assert.equal(r.writes.at(-1), INDEX); assert.deepEqual(r.diagnostics, []);
    assert.deepEqual(r.readWarnings, [1, 2].map(attempt => ({ stage: 'payload-readback', category: 'transient-http-read', httpStatus: status, attempt, maxAttempts: 3 })));
    assert.equal(JSON.stringify(r.readWarnings).includes('PRIVATE'), false);
    assert.ok(r.options.clock() >= 3000);
  }
});

test('transport diagnostics use only allowlisted names/codes and never inspect secret-like message/body/url/environment', async t => {
  for (const [name, code, expected] of [
    ['TypeError', 'ECONNRESET', { category: 'transport', errorClass: 'TypeError', transportCode: 'ECONNRESET' }],
    ['TimeoutError', 'UND_ERR_CONNECT_TIMEOUT', { category: 'transport', errorClass: 'TimeoutError', transportCode: 'UND_ERR_CONNECT_TIMEOUT' }],
    ['BlobServiceRateLimited', 'PRIVATE_ENV', { category: 'sdk', errorClass: 'BlobServiceRateLimited', httpStatus: 429 }],
    ['PRIVATE https://secret.example', 'PRIVATE_ENV', { category: 'unknown' }],
  ]) {
    const { dir } = fixture(t), r = mock(); let calls = 0;
    r.options.put = async () => {
      calls++; const error = new Error('PRIVATE_TOKEN'); error.name = name; error.cause = { code }; error.status = 'PRIVATE_STATUS';
      if (name === 'BlobServiceRateLimited') error.statusCode = 429;
      for (const key of ['message', 'body', 'url', 'env']) Object.defineProperty(error, key, { get() { throw Error('PRIVATE field was read'); } });
      throw error;
    };
    await assert.rejects(publish(dir, r.options), error => error.message === 'Company structure publication failed');
    assert.equal(calls, code === 'ECONNRESET' ? 2 : 1); assert.equal(r.writes.includes(INDEX), false);
    assert.deepEqual(r.diagnostics, [{ stage: 'payload-write', ...expected }]);
    assert.equal(JSON.stringify(r.diagnostics).includes('PRIVATE'), false);
  }
  // SDK 2.4 subclasses inherit name='BlobError'; retain the specific class.
  for (const ErrorClass of [class BlobServiceRateLimited extends Error {}, class BlobStoreSuspendedError extends Error {}]) {
    const { dir } = fixture(t), r = mock();
    r.options.put = async () => {
      const error = new ErrorClass('PRIVATE_TOKEN https://private.example ENV_PRIVATE'); error.name = 'BlobError'; throw error;
    };
    await assert.rejects(publish(dir, r.options), error => error.message === 'Company structure publication failed');
    assert.deepEqual(r.diagnostics, [{ stage: 'payload-write', category: 'sdk', errorClass: ErrorClass.name }]);
    assert.equal(JSON.stringify(r.diagnostics).includes('PRIVATE'), false); assert.equal(r.writes.includes(INDEX), false);
  }
  // Exercise the default formatter in a child with entirely mocked transport;
  // separately keep the real CLI's generic final failure boundary closed.
  const { dir } = fixture(t);
  const entrypoint = fs.readFileSync(path.resolve(__dirname, '../scripts/member-map/publish-company-structure.cjs'), 'utf8').split('if (require.main === module)')[1];
  assert.match(entrypoint, /\.catch\(\(\) =>/u);
  assert.match(entrypoint, /manifest publication not confirmed/u);
  assert.doesNotMatch(entrypoint, /\.message|\.stack|\.cause|console\./u);
  const code = `const {publish}=require(${JSON.stringify(path.resolve(__dirname, '../scripts/member-map/publish-company-structure.cjs'))});
    let now=0; publish(process.argv[1], {token:'vercel_blob_rw_rte5guenhonw9fzn_OFFLINE_TEST_ONLY',clock:()=>now,pause:async ms=>{now+=ms},
    fetch:async()=>new Response(null,{status:404}),head:async()=>{},put:async()=>{throw Object.assign(new Error('PRIVATE_TOKEN https://secret.example ENV_PRIVATE'),{name:'BlobServiceRateLimited'})}})
    .catch(()=>{process.stderr.write('Company structure validation/publication failed; manifest publication not confirmed.\\n');process.exitCode=1});`;
  let output;
  try { execFileSync(process.execPath, ['-e', code, dir], { env: { PATH: process.env.PATH }, stdio: 'pipe' }); }
  catch (error) { assert.equal(error.status, 1); output = error.stderr.toString(); }
  assert.ok(output); assert.doesNotMatch(output, /PRIVATE|secret\.example|vercel_blob_rw_/u);
  assert.match(output, /"stage":"payload-write","category":"sdk","errorClass":"BlobServiceRateLimited"/u);
  assert.match(output, /manifest publication not confirmed/u);
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
    parserRevision,
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
  assert.equal(source.reviewExhibit.parserRevision, parserRevision);
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

test('SEC co-filer archive preserves issuer/accession binding in review cache and public payload without changing primary metadata ownership', t => {
  const { dir } = fixture(t), cik = '0000006201', accession = '0000006201-26-000014';
  const url = 'https://www.sec.gov/Archives/edgar/data/4515/000000620126000014/ex21.htm';
  const source = { tickerAliases: ['AAL'], attemptedAt: at, attemptStatus: 'needs-review', metadataCheckedAt: at,
    filingMetadata: { issuer_id: 'US:AAL', issuer_name: 'American Airlines Group Inc.', cik, accession, form: '10-K',
      filed_date: '2026-02-01', period_end: '2025-12-31', primary_document: 'annual.htm',
      url: 'https://www.sec.gov/Archives/edgar/data/6201/000000620126000014/annual.htm' },
    reviewExhibit: { schema: 'sec-company-subsidiaries-v1', cik, accession, url, filedDate: '2026-02-01', periodEnd: '2025-12-31',
      status: 'needs-review', documentSha256: 'a'.repeat(64), rows: [{ name: 'PRIVATE' }], html: 'PRIVATE' } };
  const doc = { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at, issuers: { [cik]: source } };
  const safe = sanitizeUsSources(doc), item = safe.issuers[cik];
  assert.equal(item.reviewExhibit.url, url); assert.equal(item.reviewExhibit.accession, accession);
  assert.equal(item.reviewExhibit.rows, undefined); assert.equal(item.lastSuccessAt, undefined);
  assert.equal(item.attemptStatus, 'needs-review'); assert.equal(JSON.stringify(safe).includes('PRIVATE'), false);
  assert.deepEqual(sanitizeUsSources(safe), safe);
  for (const badUrl of [url.replace('www.sec.gov', 'evil.example'), url.replace('000000620126000014', '000000451526000014'),
    url.replace('000000620126000014', '000000620126000015'), url.replace('ex21.htm', '../ex21.htm'),
    url.replace('ex21.htm', 'nested/../ex21.htm'), url.replace('ex21.htm', 'nested/%2e%2e/ex21.htm'),
    url.replace('ex21.htm', '%2e%2e/ex21.htm'), url + '?token=PRIVATE', url + '#x', url.replace('https:', 'http:')]) {
    const bad = JSON.parse(JSON.stringify(doc)); bad.issuers[cik].reviewExhibit.url = badUrl;
    assert.equal(sanitizeUsSources(bad).issuers[cik].reviewExhibit, undefined, badUrl);
  }
  const wrongPrimary = JSON.parse(JSON.stringify(doc)); wrongPrimary.issuers[cik].filingMetadata.url = source.filingMetadata.url.replace('/6201/', '/4515/');
  assert.throws(() => sanitizeUsSources(wrongPrimary));
  // Synthetic accepted snapshot only; never upgrade the saved failed AAL state.
  const accepted = { ...source, attemptStatus: 'HTTP403', lastSuccessAt: at,
    exhibit: { ...source.reviewExhibit, status: 'parsed', rows: [{ name: 'Subsidiary Corp.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified' }] } };
  const result = buildArtifacts({ generatedAt: at, strictSources: true, universe: { stocks: [{ ticker: 'AAL', name: 'American Airlines Group Inc.', market: 'US' }] },
    cikMap: { AAL: cik }, usSources: sanitizeUsSources({ ...doc, issuers: { [cik]: accepted } }) });
  const output = path.join(path.dirname(dir), 'cofiler'); writeArtifacts(result, output);
  const p = [...loadArtifacts(output).payloads.values()][0].payload;
  assert.equal(p.relations.length, 1); assert.equal(p.relations[0].evidence[0].url, url);
  assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.attemptStatus, 'HTTP403');
});

const ballRecheck = { cik: '0000009389', accession: '0001104659-26-017410',
  url: 'https://www.sec.gov/Archives/edgar/data/9389/000110465926017410/ball-20251231xex21.htm',
  documentSha256: '531013e1bbb187ba0b4aa075ef1c02f12aae2eea5ae7966497106cae0af20c55' };
function explicitBaselineQuarantine(cik, s) {
  const e = s.reviewExhibit;
  return cik === ballRecheck.cik && !s.exhibit && s.attemptStatus === 'needs-review' &&
    s.sourceGap === 'source-gap:parser-recheck-needs-review' && e?.status === 'needs-review' &&
    Object.entries(ballRecheck).every(([key, value]) => e[key] === value);
}

test('ACU original six names survive parser, US sanitizer, builder and publication validation; Cooperatie is not a KR exception', async t => {
  const { dir } = fixture(t), cik = '0000002098';
  const names = ['Acme United Limited', 'Acme United Europe GmbH', 'Acme United (Asia Pacific) Limited',
    'Acme United China Limited', 'Acme United Netherlands Cooperatie U.A.', 'Acme United (APAC) Pte.Ltd.'];
  const jurisdictions = ['Canada', 'Germany', 'Hong Kong', 'China', 'Netherlands', 'Singapore'];
  const p = text => `<p><font>${text}</font></p>`;
  const single = names.slice(0, 4).map((name, i) => `<tr><td>${p(name)}</td><td>&nbsp;</td><td>${p(jurisdictions[i])}</td></tr>`).join('');
  const html = '<table><tr><th>Name</th><th></th><th>Country of Incorporation</th></tr>' + single +
    `<tr><td>${names.slice(4).map(p).join('')}</td><td>&nbsp;</td><td>${jurisdictions.slice(4).map(p).join('')}</td></tr></table>`;
  const metadata = { cik, accession: '0001193125-26-102079', filedDate: '2026-04-01', periodEnd: '2025-12-31',
    url: 'https://www.sec.gov/Archives/edgar/data/2098/000119312526102079/acu-ex21.htm', issuerName: 'Acme United Corporation' };
  const exhibit = JSON.parse(execFileSync('python3', ['-c',
    'import json,sys; from api.intelligence.company_structure_sec import parse_exhibit; d=json.load(sys.stdin); print(json.dumps(parse_exhibit(d["html"],d["metadata"])))'],
  { cwd: path.resolve(__dirname, '..'), input: JSON.stringify({ html, metadata }), encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }));
  assert.equal(exhibit.status, 'parsed'); assert.deepEqual(exhibit.rows.map(r => r.name), names);
  const doc = { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at, issuers: { [cik]: {
    tickerAliases: ['ACU'], attemptedAt: at, lastSuccessAt: at, attemptStatus: 'success', exhibit } } };
  const before = JSON.stringify(doc), safe = sanitizeUsSources(doc);
  assert.equal(JSON.stringify(doc), before); assert.deepEqual(safe.issuers[cik].exhibit.rows.map(r => r.name), names);
  const result = buildArtifacts({ generatedAt: at, strictSources: true, usSources: safe, cikMap: { ACU: cik },
    universe: { stocks: [{ ticker: 'ACU', market: 'US', name: 'Acme United Corporation' }] } });
  const output = path.join(path.dirname(dir), 'acu-six'); writeArtifacts(result, output);
  const payload = [...loadArtifacts(output).payloads.values()][0].payload;
  assert.equal(payload.companies.length, 7); assert.equal(payload.relations.length, 6);
  assert.deepEqual(payload.companies.filter(c => c.id !== 'US:ACU').map(c => c.name), names);
  assert.ok(payload.companies.every(c => !Object.hasOwn(c, 'country')));
  assert.ok(payload.relations.every(r => r.from === 'US:ACU' && r.ownershipPct === null && r.label === '공시상 자회사·직간접 미구분'));
  const remote = mock(); await publish(output, remote.options); assert.equal(remote.writes.at(-1), INDEX);
  for (const name of ['Cooperatie', 'U.A.', 'Example Cooperatie', 'Example Cooperatie U.A. Fund',
    'Individual Cooperatie U.A.', 'Trust Cooperatie U.A.', 'Example Fund Cooperatie U.A.', '개인 Cooperatie U.A.']) assert.equal(usCooperatieLabel(name), false, name);
  editPayload(dir, p => { p.companies.find(c => c.id.startsWith('FOREIGN:')).name = names[4]; });
  assert.throws(() => loadArtifacts(dir)); // KR public admission was not broadened.
});

test('only the original SHA-bound BALL parser-recheck quarantine can count toward the 22-document baseline', async t => {
  const { dir } = fixture(t), cik = ballRecheck.cik;
  const s = { tickerAliases: ['BALL'], attemptStatus: 'needs-review', attemptedAt: at, lastSuccessAt: '2026-10-03T10:00:00Z',
    sourceGap: 'source-gap:parser-recheck-needs-review', reviewExhibit: { ...ballRecheck, schema: 'sec-company-subsidiaries-v1',
      status: 'needs-review', filedDate: '2026-02-01', periodEnd: '2025-12-31', reviewReason: 'parser-table-ambiguous',
      rows: [{ name: 'PRIVATE' }], html: 'PRIVATE' } };
  assert.equal(explicitBaselineQuarantine(cik, s), true);
  for (const mutate of [s => delete s.sourceGap, s => s.sourceGap = 'source-gap:other', s => s.attemptStatus = 'success',
    s => s.reviewExhibit.documentSha256 = 'a'.repeat(64), s => s.reviewExhibit.url += '?x=1', s => s.reviewExhibit.status = 'parsed',
    s => s.reviewExhibit.accession = '0001104659-26-017411']) {
    const bad = JSON.parse(JSON.stringify(s)); mutate(bad); assert.equal(explicitBaselineQuarantine(cik, bad), false);
  }
  const doc = { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at, issuers: { [cik]: s },
    requestBudget: { day: '2026-10-22', requests: 198, ciks: [cik] } };
  const safe = sanitizeUsSources(doc);
  assert.equal(explicitBaselineQuarantine(cik, safe.issuers[cik]), true);
  assert.equal(safe.issuers[cik].lastSuccessAt, s.lastSuccessAt); assert.deepEqual(safe.requestBudget, doc.requestBudget);
  assert.equal(JSON.stringify(safe).includes('PRIVATE'), false);
  const result = buildArtifacts({ generatedAt: at, strictSources: true, usSources: safe, cikMap: { BALL: cik },
    universe: { stocks: [{ ticker: 'BALL', name: 'Ball Corporation', market: 'US' }] } });
  assert.equal(result.manifest.coverage.US.checkedCiks, 0);
  const output = path.join(path.dirname(dir), 'ball-review'); writeArtifacts(result, output);
  assert.equal((await main(['--output-dir', output])).validated, true);
  const payload = [...loadArtifacts(output).payloads.values()][0].payload;
  assert.equal(payload.relations.length, 0); assert.equal(payload.coverage.sourceChecked, false);
  assert.equal(payload.coverage.status, 'needs-review');
  assert.deepEqual(payload.coverage.pendingReview, { filedDate: '2026-02-01', periodEnd: '2025-12-31',
    documentSha256: ballRecheck.documentSha256, reason: 'parser-table-ambiguous' });
});

test('committed US snapshots preserve the 22-document baseline as parsed or explicitly SHA-bound parser quarantine, never fake parsed', async t => {
  const { dir } = fixture(t);
  const committed = name => JSON.parse(execFileSync('git', ['show', 'HEAD:data/' + name], {
    cwd: path.resolve(__dirname, '..'), encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }));
  const original = committed('member_map_company_structure_us_sources.json'), before = JSON.stringify(original);
  const parsed = Object.entries(original.issuers).filter(([, s]) => s.exhibit?.status === 'parsed');
  const quarantined = Object.entries(original.issuers).filter(([cik, s]) => explicitBaselineQuarantine(cik, s));
  assert.ok(parsed.length + quarantined.length >= 22, 'The 22-document baseline needs admitted proof or exact original parser-recheck quarantine');
  assert.ok(parsed.some(([cik, s]) => !s.exhibit.accession.startsWith(cik)), 'Includes ordinary own-CIK archives with filing-agent accessions');
  const safe = sanitizeUsSources(original);
  for (const [cik, s] of quarantined) {
    assert.equal(safe.issuers[cik].reviewExhibit.documentSha256, s.reviewExhibit.documentSha256);
    assert.equal(explicitBaselineQuarantine(cik, safe.issuers[cik]), true);
  }
  for (const [cik, s] of parsed) {
    assert.equal(safe.issuers[cik].exhibit.url, s.exhibit.url);
    assert.equal(safe.issuers[cik].exhibit.status, 'parsed');
    assert.equal(safe.issuers[cik].attemptStatus, s.attemptStatus);
    assert.equal(safe.issuers[cik].lastSuccessAt, s.lastSuccessAt);
  }
  assert.equal(JSON.stringify(original), before); assert.deepEqual(safe.requestBudget, original.requestBudget);
  const result = buildArtifacts({ universe: committed('universe_search.json'), cikMap: committed('sec_ticker_cik_map.json'),
    reviewedAliases: committed('member_map_company_structure_aliases.json'),
    generatedAt: original.generatedAt, usSources: safe, strictSources: true });
  assert.equal(result.manifest.coverage.US.checkedCiks, parsed.length);
  const boundPayloads = new Map([...result.payloads.values()].map(bytes => {
    const payload = JSON.parse(bytes); return [payload.coverage.cik, payload];
  }));
  for (const [cik, source] of parsed) {
    const payload = boundPayloads.get(cik);
    assert.ok(payload?.coverage.sourceChecked, `Original parsed source lost: ${cik}`);
    assert.equal(payload.coverage.documentSha256, source.exhibit.documentSha256);
    if (source.exhibit.rows.length) assert.ok(payload.relations.length, `Admitted relations lost: ${cik}`);
    else {
      // Some real exhibits contain only excluded entity labels. Keeping their
      // source receipt is required; inventing an edge to satisfy this test is not.
      assert.equal(source.exhibit.corporateRowCount, 0);
      assert.ok(Number.isSafeInteger(source.exhibit.sourceRowCount));
      assert.equal(payload.relations.length, 0);
    }
  }
  let retainedCollectorErrors = 0, retainedNeedsReview = 0;
  for (const [cik, s] of Object.entries(original.issuers).filter(([, s]) => !s.exhibit && s.attemptedAt && s.attemptStatus !== 'success' && s.attemptStatus !== 'not-attempted')) {
    assert.equal(safe.issuers[cik].attemptStatus, s.attemptStatus);
    const isHttpError = s.attemptStatus === 'error' || /^HTTP[1-5][0-9]{2}$/u.test(s.attemptStatus);
    if (isHttpError) retainedCollectorErrors++;
    if (s.attemptStatus === 'needs-review') retainedNeedsReview++;
    for (const ticker of s.tickerAliases) {
      const entry = result.manifest.issuers['US:' + ticker];
      if (entry) {
        const expectedStatus = ['needs-review', 'source-gap', 'budget-deferred', 'attempting'].includes(s.attemptStatus) ? s.attemptStatus : 'refresh-error';
        assert.equal(entry.status, expectedStatus);
        const payload = JSON.parse(result.payloads.get(entry.sha256));
        assert.equal(payload.coverage.sourceChecked, false);
        assert.equal(payload.coverage.attemptStatus, s.attemptStatus);
        if (s.attemptStatus === 'needs-review' && s.reviewExhibit) {
          assert.deepEqual(payload.coverage.pendingReview, {
            filedDate: s.reviewExhibit.filedDate, periodEnd: s.reviewExhibit.periodEnd,
            documentSha256: s.reviewExhibit.documentSha256,
            ...(s.reviewExhibit.reviewReason ? { reason: s.reviewExhibit.reviewReason } : {}),
          });
        }
      }
    }
  }
  assert.ok(retainedNeedsReview > 0, 'Committed parser holds must remain needs-review, not transport errors');
  assert.ok(retainedCollectorErrors > 0, 'Committed HTTP/collector errors must remain refresh-error');
  const output = path.join(path.dirname(dir), 'committed-us'); writeArtifacts(result, output);
  assert.equal((await main(['--output-dir', output])).validated, true);
  t.diagnostic(JSON.stringify({ parsedCiks: parsed.length, quarantinedCiks: quarantined.length, checkedCiks: result.manifest.coverage.US.checkedCiks,
    checkedSecurities: result.manifest.coverage.US.checked, payloads: result.payloads.size, retainedCollectorErrors, requestsPreserved: safe.requestBudget.requests }));
});
