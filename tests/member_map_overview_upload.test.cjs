const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { upload, failureSummary, validateOverview, NAME, URL, LIMIT } = require('../scripts/member-map/upload-public-overview.cjs');
const token = 'vercel_blob_rw_rte5guenhonw9fzn_synthetic';
function row(changes = {}) {
  return { name: '시험회사', text: '공개 사업 설명입니다.', chars: 12, truncated: false,
    fiscal_year: '2025', filed_at: '20260319', report: '사업보고서 (2025.12)', source: 'DART 사업보고서',
    url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260319000001', ...changes };
}
function doc(generated = '2026-10-11T00:00:00Z', rows = { '000001': row() }) {
  return { _meta: { generated_at: generated, count: Object.keys(rows).length }, rows };
}
const bytes = value => Buffer.from(JSON.stringify(value));
// Transport tests inject just the consumer verdict. Separate tests run the real
// offline Python consumer, without any provider/network subprocess.
function validator(body) {
  const rows = JSON.parse(body).rows;
  const rejected = Object.keys(rows).filter(t => rows[t].text.startsWith('<'));
  return { accepted: Object.keys(rows).length - rejected.length, rejected };
}
function fixture(t, value = doc()) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'overview-upload-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const source = path.join(directory, NAME), body = bytes(value);
  fs.writeFileSync(source, body);
  return { directory, source, body, value };
}
function transport(responses) {
  const calls = { gets: [], puts: [], waits: [] };
  return { calls, deps: { token, validator,
    fetch: async (url, options) => {
      calls.gets.push(url);
      assert.equal(new globalThis.URL(url).origin + new globalThis.URL(url).pathname, URL);
      assert.equal(options.redirect, 'error'); assert.equal(options.cache, 'no-store');
      assert.ok(options.signal);
      assert.ok(responses.length, 'unexpected GET');
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
    put: async (name, body, options) => {
      calls.puts.push({ name, body, options });
      assert.equal(process.env.VERCEL_BLOB_RETRIES, '0');
      return { url: URL };
    }, sleep: async ms => calls.waits.push(ms),
  } };
}
const absent = () => new Response(null, { status: 404 });

test('fixed file, one PUT, cache 7200, exact byte readback and no local writes', async t => {
  const f = fixture(t), mock = transport([absent(), new Response(f.body)]);
  const retries = process.env.VERCEL_BLOB_RETRIES;
  const result = await upload(f.source, mock.deps);
  assert.equal(result.uploaded, true); assert.equal(result.verified, true);
  assert.equal(result.destination, URL); assert.equal(result.readbackAttempts, 1);
  assert.equal(mock.calls.puts.length, 1);
  const put = mock.calls.puts[0];
  assert.equal(put.name, NAME); assert.deepEqual(put.body, f.body);
  assert.equal(put.options.access, 'public'); assert.equal(put.options.cacheControlMaxAge, 7200);
  assert.equal(put.options.addRandomSuffix, false); assert.equal(put.options.multipart, false);
  assert.equal(process.env.VERCEL_BLOB_RETRIES, retries);
  assert.deepEqual(fs.readdirSync(f.directory), [NAME]); assert.deepEqual(fs.readFileSync(f.source), f.body);
  assert.equal(JSON.stringify(result).includes(f.directory), false);
});

test('unchanged SHA makes no PUT or readback', async t => {
  const f = fixture(t), mock = transport([new Response(f.body)]);
  const result = await upload(f.source, mock.deps);
  assert.equal(result.uploaded, false); assert.equal(result.verified, true);
  assert.equal(mock.calls.puts.length, 0); assert.equal(mock.calls.gets.length, 1);
});

for (const [label, prior] of [
  ['same timestamp changed bytes', doc(undefined, { '000001': row({ text: '변경된 본문입니다.' }) })],
  ['newer public timestamp', doc('2026-10-12T00:00:00Z')],
  ['equivalent offset timestamp', doc('2026-10-11T09:00:00+09:00')],
  ['row loss', doc('2026-10-10T00:00:00Z', { '000001': row(), '000002': row() })],
  ['per-row date regression', doc('2026-10-10T00:00:00Z', { '000001': row({ filed_at: '20260401' }) })],
]) test(`preflight refuses ${label}`, async t => {
  const f = fixture(t), mock = transport([Response.json(prior)]);
  await assert.rejects(upload(f.source, mock.deps), { stage: 'public-preflight' });
  assert.equal(mock.calls.puts.length, 0);
});

test('strictly newer snapshot retains old rows and can add a valid row', async t => {
  const f = fixture(t, doc(undefined, { '000001': row(), '000002': row() }));
  const mock = transport([Response.json(doc('2026-10-10T00:00:00Z')), new Response(f.body)]);
  assert.equal((await upload(f.source, mock.deps)).verified, true);
  assert.equal(mock.calls.puts.length, 1);
});

test('unchanged rejected historical row can be retained with accepted rows', async t => {
  const rows = { '000001': row(), '000002': row({ text: '<종속회사> 공개 설명' }) };
  const f = fixture(t, doc(undefined, rows));
  const mock = transport([Response.json(doc('2026-10-10T00:00:00Z', rows)), new Response(f.body)]);
  const result = await upload(f.source, mock.deps);
  assert.equal(result.accepted, 1); assert.equal(result.rejected, 1);
  assert.equal(mock.calls.puts.length, 1);
});

for (const mode of ['new', 'changed', 'first-upload']) test(`rejected ${mode} row cannot publish`, async t => {
  const f = fixture(t, doc(undefined, { '000001': row(), '000002': row({ text: '<b>invalid</b>' }) }));
  const prior = doc('2026-10-10T00:00:00Z', { '000001': row(), ...(mode === 'changed'
    ? { '000002': row({ text: '<old>invalid</old>' }) } : {}) });
  const mock = transport([mode === 'first-upload' ? absent() : Response.json(prior)]);
  await assert.rejects(upload(f.source, mock.deps), { stage: 'public-preflight' });
  assert.equal(mock.calls.puts.length, 0);
});

test('zero consumer acceptance and validator exceptions fail before GET', async t => {
  const f = fixture(t), mock = transport([]);
  for (const validate of [() => ({ accepted: 0, rejected: ['000001'] }), () => { throw Error('private-input'); }]) {
    await assert.rejects(upload(f.source, { ...mock.deps, validator: validate }), { stage: 'local-validation' });
  }
  assert.equal(mock.calls.gets.length, 0); assert.equal(mock.calls.puts.length, 0);
});

test('wrong name, symlink, oversized local file and private extra fields fail before GET', async t => {
  const f = fixture(t), mock = transport([]);
  const wrong = path.join(f.directory, 'private.json'); fs.writeFileSync(wrong, f.body);
  await assert.rejects(upload(wrong, mock.deps), { stage: 'local-validation' });
  fs.unlinkSync(f.source); fs.symlinkSync(wrong, f.source);
  await assert.rejects(upload(f.source, mock.deps), { stage: 'local-validation' });
  fs.unlinkSync(f.source); fs.writeFileSync(f.source, Buffer.alloc(LIMIT + 1));
  await assert.rejects(upload(f.source, mock.deps), { stage: 'local-validation' });
  fs.writeFileSync(f.source, bytes({ ...f.value, private_member: 'synthetic' }));
  await assert.rejects(upload(f.source, mock.deps), { stage: 'local-validation' });
  assert.equal(mock.calls.gets.length, 0);
});

test('real Python consumer: valid, retained invalid, duplicate JSON, paths and credentials', () => {
  const good = doc(); good.rows['000001'].chars = good.rows['000001'].text.length;
  assert.deepEqual(validateOverview(bytes(good)), { accepted: 1, rejected: [] });
  good.rows['000002'] = row({ text: '<종속회사> 공개 설명' }); good._meta.count = 2;
  assert.deepEqual(validateOverview(bytes(good)), { accepted: 1, rejected: ['000002'] });
  for (const value of ['/Users/synthetic/private.txt', 'vercel_blob_rw_synthetic', 'Bearer synthetic', 'a@example.com', 'member_id synthetic']) {
    const bad = doc(); bad.rows['000001'].source = value;
    assert.throws(() => validateOverview(bytes(bad)), /Overview validation rejected/);
  }
  const badMeta = doc(); badMeta._meta.note = 'password synthetic';
  assert.throws(() => validateOverview(bytes(badMeta)), /Overview validation rejected/);
  assert.throws(() => validateOverview(Buffer.from('{"rows":{},"rows":{}}')), /Overview validation rejected/);
});

test('credential, provider error and untrusted error stages never expose messages', async t => {
  const f = fixture(t), mock = transport([]), secret = 'synthetic-private-provider-message';
  await assert.rejects(upload(f.source, { ...mock.deps, token: 'wrong' }), { stage: 'credential' });
  const uploadMock = transport([absent()]);
  await assert.rejects(upload(f.source, { ...uploadMock.deps, put: async () => { throw Error(secret); } }), error => {
    assert.deepEqual(failureSummary(error), { status: 'failed', stage: 'upload' });
    assert.equal(error.stack.includes(secret), false); assert.equal(error.cause, undefined);
    return true;
  });
  assert.deepEqual(failureSummary({ stage: secret }), { status: 'failed', stage: 'unknown' });
});

test('preflight denial, redirect, malformed JSON and unbounded stream fail with no PUT', async t => {
  const f = fixture(t);
  const redirected = new Response(f.body); Object.defineProperty(redirected, 'redirected', { value: true });
  for (const response of [new Response(null, { status: 403 }), redirected, new Response('{'),
    new Response(f.body, { headers: { 'content-length': String(LIMIT + 1) } }),
    new Response(Buffer.alloc(LIMIT + 1))]) {
    const mock = transport([response]);
    await assert.rejects(upload(f.source, mock.deps), { stage: 'public-preflight' });
    assert.equal(mock.calls.puts.length, 0);
  }
});

test('wrong PUT destination fails without fetching that destination', async t => {
  const f = fixture(t), mock = transport([absent()]);
  await assert.rejects(upload(f.source, { ...mock.deps, put: async () => ({ url: 'https://example.com/private' }) }),
    { stage: 'destination-validation' });
  assert.equal(mock.calls.gets.length, 1);
});

test('stale readback and transient HTTP retry only bounded GETs', async t => {
  const f = fixture(t), mock = transport([absent(), Response.json(doc('2026-10-10T00:00:00Z')),
    new Response(null, { status: 503 }), new Response(f.body)]);
  assert.equal((await upload(f.source, mock.deps)).readbackAttempts, 3);
  assert.equal(mock.calls.puts.length, 1); assert.deepEqual(mock.calls.waits, [10000, 20000]);
});

test('stale readback exhausts at four attempts, never retries PUT', async t => {
  const f = fixture(t), mock = transport([absent(), ...Array.from({ length: 4 }, () => Response.json(doc('2026-10-10T00:00:00Z')))]);
  await assert.rejects(upload(f.source, mock.deps), { stage: 'readback-hash' });
  assert.equal(mock.calls.puts.length, 1); assert.equal(mock.calls.gets.length, 5);
  assert.deepEqual(mock.calls.waits, [10000, 20000, 30000]);
});

test('corrupt, altered same-age, newer and denied readbacks fail without retry', async t => {
  const f = fixture(t);
  for (const response of [new Response('{'), Response.json(doc(undefined, { '000001': row({ text: 'changed' }) })),
    Response.json(doc('2026-10-12T00:00:00Z')), new Response(null, { status: 403 })]) {
    const mock = transport([absent(), response]);
    await assert.rejects(upload(f.source, mock.deps));
    assert.equal(mock.calls.gets.length, 2); assert.equal(mock.calls.puts.length, 1);
    assert.deepEqual(mock.calls.waits, []);
  }
});
