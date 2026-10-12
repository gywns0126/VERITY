const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { publish, parseArgs } = require('../scripts/member-map/upload-ai-candidates.cjs');
const NAME = 'member_map_ai_candidates.json';
const URL = `https://rte5guenhonw9fzn.public.blob.vercel-storage.com/${NAME}`;
const TOKEN = 'vercel_blob_rw_rte5guenhonw9fzn_synthetic';
const SECRET = 'synthetic-secret-never-print';
const sha = body => createHash('sha256').update(body).digest('hex');
const forbidden = () => { throw Error('unexpected side effect'); };
const noSecrets = new Proxy({}, { get: forbidden, ownKeys: forbidden });
function response(body = null, status = 200, properties = {}) {
  return Object.defineProperties(new Response(body, { status }), Object.fromEntries(
    Object.entries({ url: URL, ...properties }).map(([key, value]) => [key, { value }])));
}
function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-publish-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const sourceDir = path.join(directory, 'sources'); fs.mkdirSync(sourceDir);
  const companies = [{ ticker: '111111', market: 'KR', name: 'Synthetic Issuer' },
    { ticker: '222222', market: 'KR', name: 'Synthetic A' }];
  for (const name of ['universe_search', 'stock_report_public', 'us_stock_report_public',
    'public_disclosure_feed', 'us_disclosure_feed']) fs.writeFileSync(path.join(sourceDir, name + '.json'),
    JSON.stringify(name === 'universe_search' ? { stocks: companies }
      : name.includes('disclosure') ? { items: [] } : { stocks: [] }));
  const document = { source_id: 'source:dart:20260312000001', issuer_id: 'KR:111111', issuer_name: 'Synthetic Issuer',
    as_of: '2026-03-12', url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001',
    text: '당사는 Synthetic A를 고객으로 두고 거래하고 있습니다.', counterparties: [{ id: 'KR:222222', name: 'Synthetic A' }] };
  const raw = { schema: 'local-ai-review-input-v1', entries: [{ document,
    answer: { candidates: [{ counterparty_id: 'KR:222222', role: 'customer', quote: document.text }] } }] };
  const input = path.join(directory, 'review.json');
  const save = () => fs.writeFileSync(input, JSON.stringify(raw)); save();
  let body, output;
  const run = (command, args, options) => {
    assert.equal(command, 'python3');
    assert.equal(path.basename(args[0]), 'export-ai-candidates.py');
    assert.deepEqual(Object.keys(options.env).sort(), ['PATH', 'PYTHONDONTWRITEBYTECODE']);
    output = args[args.indexOf('--output') + 1];
    const result = spawnSync(command, args, options);
    if (result.status === 0) body = fs.readFileSync(output);
    return result;
  };
  return { input, sourceDir, raw, save, run, get body() { return body; }, get output() { return output; } };
}
function mockExport(body) {
  return (_, args) => { fs.writeFileSync(args[args.indexOf('--output') + 1], body); return { status: 0 }; };
}
const EMPTY = Buffer.from(JSON.stringify({ schema: 'local-ai-review-v1', candidates: [],
  coverage: { input: 0, accepted: 0, rejected: 0, skipped: 0 } }));
function mocked(extra = {}) {
  return { env: { BLOB_READ_WRITE_TOKEN: TOKEN }, run: mockExport(EMPTY), fetch: forbidden, put: forbidden, sleep: forbidden, ...extra };
}
const options = { input: '/synthetic/review.json', sourceDir: '/synthetic/public', upload: true };
function claim(document, quote = document.text) {
  return { counterparty_id: 'KR:222222', role: 'customer', claim_kind: 'relation_fact',
    directness: 'direct', claim_state: 'asserted', quote,
    context: { object_quote: null, scale_quote: null, time_quote: null }, scope_quote: null,
    channel_quote: null, counter_evidence_quotes: [], missing_evidence: [] };
}

test('dry-run uses the real offline exporter, closed projection only, and reads no credential', async t => {
  const f = fixture(t), before = fs.readFileSync(f.input);
  const result = await publish(f, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden });
  assert.deepEqual(result, { url: URL, sha256: sha(f.body), count: 1 });
  const artifact = JSON.parse(f.body);
  assert.deepEqual(Object.keys(artifact).sort(), ['candidates', 'coverage', 'schema']);
  assert.equal(artifact.candidates[0].status, 'ai_candidate');
  assert.equal(artifact.candidates[0].verification, 'unreviewed-model-extraction');
  assert.equal(artifact.candidates[0].quote, f.raw.entries[0].document.text);
  for (const key of ['entries', 'document', 'answer', 'ledger', 'token', 'members']) assert.equal(key in artifact, false);
  assert.deepEqual(fs.readFileSync(f.input), before);
  assert.equal(fs.existsSync(path.dirname(f.output)), false);
});

test('reviewed judgment options are explicit and reach only the offline exporter', async () => {
  const args = ['--input', 'raw.json', '--source-dir', 'public', '--judgment-input', 'answer.json',
    '--judgment-reviews', 'receipts.json', '--judgment-as-of', '2026-10-12', '--judgment-previous', 'prior.json'];
  const supplied = parseArgs(args);
  let called = false;
  await publish(supplied, { env: noSecrets, fetch: forbidden, put: forbidden, run: (command, values, settings) => {
    called = true;
    assert.equal(command, 'python3');
    assert.equal(values[values.indexOf('--judgment-input') + 1], path.resolve('answer.json'));
    assert.equal(values[values.indexOf('--judgment-reviews') + 1], path.resolve('receipts.json'));
    assert.equal(values[values.indexOf('--judgment-as-of') + 1], '2026-10-12');
    assert.equal(values[values.indexOf('--judgment-previous') + 1], path.resolve('prior.json'));
    assert.deepEqual(Object.keys(settings.env).sort(), ['PATH', 'PYTHONDONTWRITEBYTECODE']);
    return mockExport(EMPTY)(command, values);
  }});
  assert.equal(called, true);
  for (const extras of [['--judgment-input', 'only.json'], ['--judgment-previous', 'only.json'],
    ['--judgment-input', 'a', '--judgment-reviews', 'b']]) {
    assert.throws(() => parseArgs(['--input', 'raw.json', '--source-dir', 'public', ...extras]),
      { message: 'public-ai-publish-arguments-rejected' });
  }
});

test('unchanged public judgments are revalidated offline and retained without credential or PUT', async () => {
  const prior = Buffer.from(JSON.stringify({ ...JSON.parse(EMPTY),
    company_judgments: { schema: 'local-company-judgments-v1', judgments: [] } }));
  let exports = 0, reads = 0;
  const result = await publish({ ...options, replaceSha256: sha(prior) }, mocked({ env: noSecrets,
    run: (command, args, settings) => {
      exports++;
      assert.deepEqual(Object.keys(settings.env).sort(), ['PATH', 'PYTHONDONTWRITEBYTECODE']);
      if (exports === 1) assert.equal(args.includes('--retained-public-judgments'), false);
      else assert.deepEqual(fs.readFileSync(args[args.indexOf('--retained-public-judgments') + 1]), prior);
      return mockExport(exports === 1 ? EMPTY : prior)(command, args);
    }, fetch: async url => { reads++; return response(prior, 200, { url }); }
  }));
  assert.equal(exports, 2); assert.equal(reads, 2);
  assert.equal(result.sha256, sha(prior));
});

test('404 allows exactly one fixed no-overwrite PUT, then exact hash readback', async t => {
  const f = fixture(t); let reads = 0, puts = 0;
  const result = await publish({ ...f, upload: true }, { run: f.run, env: { BLOB_READ_WRITE_TOKEN: TOKEN },
    fetch: async (url, init) => {
      assert.equal(url, URL); assert.equal(init.redirect, 'error'); assert.equal(init.cache, 'no-store');
      assert.equal(init.headers, undefined);
      return ++reads === 1 ? response(null, 404) : response(f.body);
    }, put: async (name, body, settings) => {
      puts++; assert.equal(name, NAME); assert.deepEqual(body, f.body);
      assert.deepEqual({ ...settings, abortSignal: undefined }, { token: TOKEN, access: 'public', addRandomSuffix: false,
        allowOverwrite: false, multipart: false, contentType: 'application/json', cacheControlMaxAge: 600, abortSignal: undefined });
      return { url: URL };
    } });
  assert.equal(reads, 2); assert.equal(puts, 1);
  assert.deepEqual(result, { url: URL, sha256: sha(f.body), count: 1 });
  assert.equal(JSON.stringify(result).includes(TOKEN), false);
});

test('same hash performs zero writes and does not need credential access', async () => {
  assert.deepEqual(await publish(options, mocked({ env: noSecrets, fetch: async () => response(EMPTY) })),
    { url: URL, sha256: sha(EMPTY), count: 0 });
});
test('different existing bytes cannot be overwritten regardless of date or content', async () => {
  await assert.rejects(publish(options, mocked({ env: noSecrets, fetch: async () => response('{}') })),
    { message: 'public-ai-publish-existing-content-rejected' });
});

for (const status of [301, 302, 307, 308, 401, 403, 429, 500]) test(`preflight ${status} fails without PUT`, async () => {
  await assert.rejects(publish(options, mocked({ fetch: async () => response(null, status) })),
    { message: 'public-ai-publish-public-preflight-rejected' });
});
for (const properties of [{ redirected: true }, { url: 'https://other.invalid/' }]) {
  test('redirected or wrong-host preflight cannot authorize even an apparent 404', async () => {
    await assert.rejects(publish(options, mocked({ fetch: async () => response(null, 404, properties) })),
      { message: 'public-ai-publish-public-preflight-rejected' });
  });
}
for (const token of ['', 'vercel_blob_rw_other_synthetic']) test('wrong credential prefix blocks PUT', async () => {
  await assert.rejects(publish(options, mocked({ env: { BLOB_READ_WRITE_TOKEN: token }, fetch: async () => response(null, 404) })),
    { message: 'public-ai-publish-credential-rejected' });
});
test('SDK endpoint override is rejected before credential lookup', async () => {
  const env = { VERCEL_BLOB_API_URL: 'https://other.invalid/' };
  Object.defineProperty(env, 'BLOB_READ_WRITE_TOKEN', { get: forbidden });
  await assert.rejects(publish(options, mocked({ env, fetch: async () => response(null, 404) })),
    { message: 'public-ai-publish-credential-rejected' });
});

for (const readback of [() => response(null, 403), () => response(null, 503), () => response(null, 302),
  () => response(EMPTY, 200, { redirected: true }), () => response(EMPTY, 200, { url: 'https://other.invalid/' }),
  () => response(Buffer.alloc(2_000_001))]) test('bad readback fails without retrying a read or write', async () => {
  let reads = 0, puts = 0;
  await assert.rejects(publish(options, mocked({ fetch: async () => ++reads === 1 ? response(null, 404) : readback(),
    put: async () => { puts++; return { url: URL }; } })), { message: 'public-ai-publish-readback-rejected' });
  assert.equal(puts, 1); assert.equal(reads, 2);
});
for (const intermediate of [() => response(null, 404), () => response('{}')]) {
  test('transient readback 404/hash mismatch retries GET only and requires exact hash', async () => {
    let reads = 0, puts = 0; const waits = [];
    const result = await publish(options, mocked({ sleep: async ms => waits.push(ms),
      fetch: async () => ++reads === 1 ? response(null, 404) : reads === 2 ? intermediate() : response(EMPTY),
      put: async () => { puts++; return { url: URL }; } }));
    assert.deepEqual(result, { url: URL, sha256: sha(EMPTY), count: 0 });
    assert.deepEqual(waits, [10000]); assert.equal(reads, 3); assert.equal(puts, 1);
  });
  test('readback retries exhaust four GET attempts without a second PUT', async () => {
    let reads = 0, puts = 0; const waits = [];
    await assert.rejects(publish(options, mocked({ sleep: async ms => waits.push(ms),
      fetch: async () => ++reads === 1 ? response(null, 404) : intermediate(),
      put: async () => { puts++; return { url: URL }; } })), { message: 'public-ai-publish-readback-rejected' });
    assert.deepEqual(waits, [10000, 20000, 30000]); assert.equal(reads, 5); assert.equal(puts, 1);
  });
}
test('wrong SDK destination fails before readback', async () => {
  let reads = 0;
  await assert.rejects(publish(options, mocked({ fetch: async () => { reads++; return response(null, 404); },
    put: async () => ({ url: 'https://other.invalid/' }) })), { message: 'public-ai-publish-destination-rejected' });
  assert.equal(reads, 1);
});
test('provider errors disclose neither credentials, input paths nor raw exception text', async () => {
  let puts = 0;
  await assert.rejects(publish(options, mocked({ fetch: async () => response(null, 404),
    put: async () => { puts++; throw Error(SECRET + TOKEN); } })), error => {
    assert.equal(error.message, 'public-ai-publish-upload-rejected');
    assert.equal(error.cause, undefined); assert.equal(error.stack.includes(SECRET), false); return true;
  });
  assert.equal(puts, 1);
});

for (const change of [f => { f.raw.private = SECRET; },
  f => { f.raw.entries[0].document.url += '1'; }]) test('real exporter malformed input stops before network or keys', async t => {
  const f = fixture(t); change(f); f.save();
  await assert.rejects(publish({ ...f, upload: true }, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden }),
    { message: 'public-ai-publish-local-validation-rejected' });
  assert.equal(fs.existsSync(path.dirname(f.output)), false);
});
for (const invalid of [{ quote: 'not in the preserved source' }, { private: SECRET }]) {
  test('real exporter retains valid candidates and nonzero rejection coverage without unsafe rows', async t => {
    const f = fixture(t), valid = f.raw.entries[0].answer.candidates[0];
    f.raw.entries[0].answer.candidates.push({ ...valid, ...invalid }); f.save();
    let reads = 0, puts = 0;
    const result = await publish({ ...f, upload: true }, mocked({ run: f.run,
      fetch: async () => ++reads === 1 ? response(null, 404) : response(f.body),
      put: async (_, body) => { puts++; assert.deepEqual(body, f.body); return { url: URL }; } }));
    const artifact = JSON.parse(f.body);
    assert.deepEqual(artifact.coverage, { input: 2, accepted: 1, rejected: 1, skipped: 0 });
    assert.equal(artifact.candidates.length, 1); assert.equal(result.count, 1); assert.equal(puts, 1);
    assert.equal(artifact.candidates[0].quote, valid.quote);
    assert.equal('private' in artifact.candidates[0], false); assert.equal(f.body.includes(SECRET), false);
  });
}
test('real exporter grouped claims may have both skipped and rejected coverage', async t => {
  const f = fixture(t), doc = f.raw.entries[0].document;
  const first = claim(doc), secondQuote = '당사는 Synthetic A에 부품을 공급하고 있습니다.';
  doc.text += ' ' + secondQuote;
  f.raw.entries[0].answer = { claims: [first, claim(doc, secondQuote),
    claim(doc, 'not in the preserved source')], remaining_count: 0 }; f.save();
  const result = await publish(f, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden });
  const artifact = JSON.parse(f.body);
  assert.deepEqual(artifact.coverage, { input: 3, accepted: 1, rejected: 1, skipped: 1 });
  assert.equal(artifact.candidates[0].claims.length, 2); assert.equal(result.count, 1);
  for (const row of artifact.candidates[0].claims) {
    assert.ok(doc.text.includes(row.quote)); assert.equal(row.degree, 'unrated');
  }
});
test('100 legacy entries plus one v2 archive use separate bounded exporter inputs without paid replay', async t => {
  const f = fixture(t), seed = structuredClone(f.raw.entries[0]);
  function entry(index) {
    const row = structuredClone(seed), receipt = '20260312' + String(index).padStart(6, '0');
    row.document.source_id = 'source:dart:' + receipt;
    row.document.url = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + receipt; return row;
  }
  f.raw.entries = Array.from({ length: 100 }, (_, i) => entry(i + 1)); f.save();
  const newer = entry(101);
  newer.answer = { claims: [claim(newer.document)], remaining_count: 0 };
  const second = path.join(path.dirname(f.input), 'latest-v2.json');
  fs.writeFileSync(second, JSON.stringify({ schema: 'local-ai-review-input-v1', entries: [newer] }));
  const before = [f.input, second].map(file => fs.readFileSync(file));
  const result = await publish({ ...f, input: [f.input, second] }, { env: noSecrets, fetch: forbidden, put: forbidden,
    run: (command, args, settings) => {
      assert.deepEqual(args.flatMap((arg, i) => arg === '--input' ? [args[i + 1]] : []), [f.input, second]);
      return f.run(command, args, settings);
    } });
  const artifact = JSON.parse(f.body);
  assert.equal(result.count, 101);
  assert.deepEqual(artifact.coverage, { input: 101, accepted: 101, rejected: 0, skipped: 0 });
  assert.equal(artifact.candidates.filter(row => row.claims).length, 1);
  assert.equal(new Set(artifact.candidates.map(row => row.id)).size, 101);
  assert.deepEqual([f.input, second].map(file => fs.readFileSync(file)), before);
});
test('exact repeated documents across two real archives are exported only once', async t => {
  const f = fixture(t), second = path.join(path.dirname(f.input), 'duplicate.json');
  fs.writeFileSync(second, fs.readFileSync(f.input));
  const result = await publish({ ...f, input: [f.input, second] }, mocked({ run: f.run, env: noSecrets }));
  assert.equal(result.count, 1);
  assert.deepEqual(JSON.parse(f.body).coverage, { input: 1, accepted: 1, rejected: 0, skipped: 0 });
});
test('conflicting answers for the same document fail before any public read or credential', async t => {
  const f = fixture(t), second = path.join(path.dirname(f.input), 'conflict.json');
  const other = structuredClone(f.raw); other.entries[0].answer.candidates = [];
  fs.writeFileSync(second, JSON.stringify(other));
  await assert.rejects(publish({ ...f, input: [f.input, second], upload: true }, mocked({
    run: f.run, env: noSecrets })), { message: 'public-ai-publish-local-validation-rejected' });
});
test('single archive remains limited to 100 entries', async t => {
  const f = fixture(t);
  f.raw.entries = Array.from({ length: 101 }, () => structuredClone(f.raw.entries[0])); f.save();
  await assert.rejects(publish({ ...f, upload: true }, mocked({ run: f.run, env: noSecrets })),
    { message: 'public-ai-publish-local-validation-rejected' });
});
test('programmatic input accepts a one-element array and rejects empty, non-string or over-two inputs before export', async () => {
  assert.equal((await publish({ ...options, input: ['one.json'], upload: false }, mocked({
    env: noSecrets, run: (cmd, args) => {
      assert.equal(args.filter(arg => arg === '--input').length, 1); return mockExport(EMPTY)(cmd, args);
    } }))).count, 0);
  for (const input of [[], ['', 'b'], ['a', 1], ['a', 'b', 'c'], {}]) {
    await assert.rejects(publish({ ...options, input }, mocked({ run: forbidden, env: noSecrets })),
      { message: 'public-ai-publish-local-validation-rejected' });
  }
});
test('raw-input symlink fails closed in the real exporter', async t => {
  const f = fixture(t), input = path.join(path.dirname(f.input), 'link.json'); fs.symlinkSync(f.input, input);
  await assert.rejects(publish({ ...f, input, upload: true }, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden }),
    { message: 'public-ai-publish-local-validation-rejected' });
});
test('export subprocess errors are fixed and temporary output is removed', async () => {
  let directory;
  await assert.rejects(publish(options, mocked({ env: noSecrets, run: (_, args) => {
    directory = path.dirname(args[args.indexOf('--output') + 1]);
    return { status: 1, stderr: SECRET, stdout: SECRET, error: Error(SECRET) };
  } })), { message: 'public-ai-publish-local-validation-rejected' });
  assert.equal(fs.existsSync(directory), false);
});

test('CLI defaults to dry-run, allows two inputs, rejects other duplicates and invalid options without echoing input', () => {
  assert.deepEqual(parseArgs(['--input', 'raw.json', '--source-dir', 'public']), { input: 'raw.json', sourceDir: 'public' });
  assert.deepEqual(parseArgs(['--upload', '--source-dir', 'public', '--input', 'raw.json']),
    { upload: true, input: 'raw.json', sourceDir: 'public' });
  assert.deepEqual(parseArgs(['--input', 'old100.json', '--source-dir', 'public', '--input', 'v2.json']),
    { input: ['old100.json', 'v2.json'], sourceDir: 'public' });
  for (const args of [[], ['--input', SECRET], ['--token', SECRET], ['--input', '--upload'],
    ['--upload', '--upload'], ['--input', 'a', '--input', 'b', '--input', 'c'],
    ['--input', 'a', '--source-dir', 'b', '--source-dir', 'c'],
    ['--input', 'a', '--source-dir', 'b', 'constructor', SECRET]]) {
    assert.throws(() => parseArgs(args), { message: 'public-ai-publish-arguments-rejected' });
  }
  const cli = spawnSync(process.execPath, [path.resolve(__dirname, '../scripts/member-map/upload-ai-candidates.cjs'), '--token', SECRET],
    { env: {}, encoding: 'utf8' });
  assert.equal(cli.status, 1); assert.equal(cli.stdout, '');
  assert.equal(cli.stderr, 'public-ai-publish-arguments-rejected\n');
});

for (const prior of [undefined, '7']) for (const fails of [false, true]) {
  test('public put is called once with SDK retries disabled and env restored on success/failure', async () => {
    const env = { BLOB_READ_WRITE_TOKEN: TOKEN, ...(prior === undefined ? {} : { VERCEL_BLOB_RETRIES: prior }) };
    let reads = 0, puts = 0;
    const result = publish(options, mocked({ env,
      fetch: async () => ++reads === 1 ? response(null, 404) : response(EMPTY),
      put: async () => {
        puts++; assert.equal(env.VERCEL_BLOB_RETRIES, '0');
        if (fails) throw Error(SECRET); return { url: URL };
      } }));
    if (fails) await assert.rejects(result, { message: 'public-ai-publish-upload-rejected' });
    else assert.equal((await result).sha256, sha(EMPTY));
    assert.equal(puts, 1); assert.equal(reads, fails ? 1 : 2);
    assert.equal(env.VERCEL_BLOB_RETRIES, prior);
    assert.equal(Object.hasOwn(env, 'VERCEL_BLOB_RETRIES'), prior !== undefined);
  });
}
test('publisher uses the public SDK only, without a transport patch or internal endpoint', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../scripts/member-map/upload-ai-candidates.cjs'), 'utf8');
  assert.match(source, /require\('@vercel\/blob'\)\.put/);
  assert.doesNotMatch(source, /undici|createRequire|client\.fetch|vercel\.com\/api\/blob/);
});

const OLD = Buffer.from('{}');
const replaceOptions = { ...options, replaceSha256: sha(OLD) };

test('fixed worker-state export is explicit, offline by default, and cannot mix arbitrary input', async () => {
  const workerOptions = { workerState: true, sourceDir: '/synthetic/public' };
  assert.deepEqual(parseArgs(['--worker-state', '--source-dir', '/synthetic/public']), workerOptions);
  const result = await publish(workerOptions, mocked({ env: noSecrets, run: (command, args) => {
    assert.equal(command, 'python3');
    assert.equal(args.filter(arg => arg === '--worker-state').length, 1);
    assert.equal(args.includes('--input'), false);
    return mockExport(EMPTY)(command, args);
  } }));
  assert.equal(result.sha256, sha(EMPTY));
  for (const bad of [{ ...workerOptions, input: 'a' }, { ...workerOptions, input: [] },
    { ...workerOptions, workerState: 'true' },
    { ...workerOptions, workerState: false }]) {
    await assert.rejects(publish(bad, mocked({ run: forbidden, env: noSecrets })),
      { message: 'public-ai-publish-local-validation-rejected' });
  }
  for (const args of [['--worker-state', '--input', 'a', '--source-dir', 'b'],
    ['--worker-state', '--worker-state', '--source-dir', 'b'], ['--worker-state']]) {
    assert.throws(() => parseArgs(args), { message: 'public-ai-publish-arguments-rejected' });
  }
});
const storageMeta = { url: URL, pathname: NAME, etag: '"storage-v1"' };
function freshResponse(body, url, etag = 'W/"storage-v1"') {
  assert.ok(url.startsWith(URL + '?verify='));
  return response(body, 200, { url, headers: new Headers(etag ? { etag } : {}) });
}
test('explicit expected hash and matching storage ETag permit one conditional replacement', async () => {
  const urls = []; let puts = 0, heads = 0;
  const result = await publish(replaceOptions, mocked({
    fetch: async url => {
      urls.push(url);
      if (urls.length === 1) return freshResponse(OLD, url);
      assert.equal(url, URL); return response(EMPTY);
    },
    head: async (url, settings) => {
      heads++; assert.equal(url, URL); assert.equal(settings.token, TOKEN); return storageMeta;
    },
    put: async (name, body, settings) => {
      puts++; assert.equal(name, NAME); assert.deepEqual(body, EMPTY);
      assert.equal(settings.ifMatch, storageMeta.etag); assert.equal(settings.allowOverwrite, true);
      assert.equal(settings.addRandomSuffix, false); assert.equal(settings.cacheControlMaxAge, 600);
      return { url: URL };
    },
  }));
  assert.equal(result.sha256, sha(EMPTY)); assert.equal(puts, 1); assert.equal(heads, 1);
  assert.equal(urls.length, 2); assert.notEqual(urls[0], urls[1]);
});
test('replacement mode unchanged content is free of storage writes and credential access', async () => {
  const result = await publish(replaceOptions, mocked({ env: noSecrets, head: forbidden,
    fetch: async url => url === URL ? response(EMPTY) : freshResponse(EMPTY, url) }));
  assert.equal(result.sha256, sha(EMPTY));
});
for (const body of [null, Buffer.from('unexpected concurrent bytes')]) {
  test('missing or changed expected public content refuses replacement before credential access', async () => {
    await assert.rejects(publish(replaceOptions, mocked({ env: noSecrets, head: forbidden,
      fetch: async url => body === null ? response(null, 404, { url }) : freshResponse(body, url) })),
    { message: 'public-ai-publish-existing-content-rejected' });
  });
}
for (const meta of [null, { ...storageMeta, etag: '' }, { ...storageMeta, etag: 'W/"storage-v1"' },
  { ...storageMeta, etag: '"concurrent-v2"' }, { ...storageMeta, url: 'https://other.invalid/' },
  { ...storageMeta, pathname: 'another.json' }]) {
  test('missing, stale or foreign storage metadata refuses a conditional PUT', async () => {
    await assert.rejects(publish(replaceOptions, mocked({ head: async () => meta,
      fetch: async url => freshResponse(OLD, url) })), { message: 'public-ai-publish-storage-precondition-rejected' });
  });
}
test('missing public ETag cannot authorize replacement', async () => {
  await assert.rejects(publish(replaceOptions, mocked({ head: async () => storageMeta,
    fetch: async url => freshResponse(OLD, url, null) })), { message: 'public-ai-publish-storage-precondition-rejected' });
});
test('wildcard ETag cannot turn replacement into an unconditional overwrite', async () => {
  await assert.rejects(publish(replaceOptions, mocked({ head: async () => ({ ...storageMeta, etag: '*' }),
    fetch: async url => freshResponse(OLD, url, '*') })), { message: 'public-ai-publish-storage-precondition-rejected' });
});
test('write race refuses publication without retrying the conditional PUT', async () => {
  let puts = 0, reads = 0;
  await assert.rejects(publish(replaceOptions, mocked({ head: async () => storageMeta,
    fetch: async url => { reads++; return freshResponse(OLD, url); },
    put: async (_, __, settings) => {
      puts++; assert.equal(settings.ifMatch, storageMeta.etag); throw Error('412 ' + SECRET);
    } })), { message: 'public-ai-publish-upload-rejected' });
  assert.equal(puts, 1); assert.equal(reads, 1);
});
test('conditional upload is not delivered until the canonical consumer URL changes', async () => {
  let puts = 0, reads = 0; const waits = [];
  await assert.rejects(publish(replaceOptions, mocked({ head: async () => storageMeta,
    sleep: async ms => waits.push(ms),
    fetch: async url => {
      reads++;
      if (reads === 1) return freshResponse(OLD, url);
      assert.equal(url, URL); return response(OLD); // Stale CDN despite accepted PUT.
    },
    put: async () => { puts++; return { url: URL }; } })), { message: 'public-ai-publish-readback-rejected' });
  assert.equal(puts, 1); assert.equal(reads, 5); assert.deepEqual(waits, [10000, 20000, 30000]);
});
test('retry after prior accepted replacement verifies canonical delivery without another write', async () => {
  let reads = 0; const waits = [];
  await assert.rejects(publish(replaceOptions, mocked({ env: noSecrets, head: forbidden,
    sleep: async ms => waits.push(ms),
    fetch: async url => { reads++; return url === URL ? response(OLD) : freshResponse(EMPTY, url); }
  })), { message: 'public-ai-publish-readback-rejected' });
  assert.equal(reads, 5); assert.deepEqual(waits, [10000, 20000, 30000]);
});
test('conditional replacement needs valid explicit SHA; CLI still defaults to dry-run', async () => {
  assert.deepEqual(parseArgs(['--input', 'raw.json', '--source-dir', 'public', '--replace-sha256', sha(OLD)]),
    { input: 'raw.json', sourceDir: 'public', replaceSha256: sha(OLD) });
  for (const replaceSha256 of ['', '*', 'abc', 'F'.repeat(64), 1, null]) {
    await assert.rejects(publish({ ...options, replaceSha256 }, mocked({ run: forbidden, env: noSecrets })),
      { message: 'public-ai-publish-local-validation-rejected' });
  }
  assert.throws(() => parseArgs(['--input', 'a', '--source-dir', 'b', '--replace-sha256', '*']),
    { message: 'public-ai-publish-arguments-rejected' });
});

test('public artifact mode validates exact bytes offline and cannot mix raw inputs', async t => {
  const f = fixture(t);
  await publish(f, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden });
  const artifact = path.join(path.dirname(f.input), NAME);
  fs.writeFileSync(artifact, f.body);
  const args = { artifact: fs.realpathSync(artifact), artifactSha256: sha(f.body), sourceDir: f.sourceDir };
  const result = await publish(args, { env: noSecrets, fetch: forbidden, put: forbidden });
  assert.equal(result.sha256, args.artifactSha256);
  assert.equal(result.count, 1);
  assert.deepEqual(parseArgs(['--artifact', args.artifact, '--artifact-sha256', args.artifactSha256,
    '--source-dir', f.sourceDir]), args);
  for (const bad of [{ ...args, input: f.input }, { ...args, workerState: true },
    { ...args, artifactSha256: '0'.repeat(64) }, { ...args, judgmentInput: 'private.json' }]) {
    await assert.rejects(publish(bad, { env: noSecrets, fetch: forbidden, put: forbidden }),
      { message: 'public-ai-publish-local-validation-rejected' });
  }
});

test('artifact mode rejects unsafe optional grades and does not leak or silently drop them', async t => {
  const f = fixture(t);
  await publish(f, { run: f.run, env: noSecrets, fetch: forbidden, put: forbidden });
  const artifact = path.join(path.dirname(f.input), NAME);
  const payload = { ...JSON.parse(f.body), company_judgments: {
    schema: 'local-company-judgments-v1', judgments: [{ private: SECRET }] } };
  const body = JSON.stringify(payload); fs.writeFileSync(artifact, body);
  await assert.rejects(publish({ artifact: fs.realpathSync(artifact), artifactSha256: sha(body), sourceDir: f.sourceDir,
    upload: true }, { env: noSecrets, fetch: forbidden, put: forbidden }),
    { message: 'public-ai-publish-local-validation-rejected' });
});
