'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { buildArtifacts, writeArtifacts } = require('../scripts/member-map/build-live-company-structure.cjs');
const { publish, BASE, INDEX } = require('../scripts/member-map/publish-company-structure.cjs');

const at = '2026-10-29T10:00:00Z';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function fixture(t, issuerCount = 1) {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'structure-write-recovery-'));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const listed = {}, structures = {};
  for (let n = 0; n < issuerCount; n++) {
    const ticker = String(111111 + n);
    listed[ticker] = { name: `Issuer ${n} Corp.` };
    structures[ticker] = { collected_at: at, major_shareholders: [{ name: 'Holder Ltd.', ownership_pct: 30 }], subsidiaries: [] };
  }
  const result = buildArtifacts({
    listed, generatedAt: at, groups: { structures },
  });
  const dir = path.join(temp, 'public'); writeArtifacts(result, dir);
  const payloads = [...result.payloads.entries()].map(([sha, value]) => ({
    name: `company-structure/${sha}.json`, bytes: Buffer.from(value?.bytes ?? value),
  }));
  return { dir, result, payloads, payloadName: payloads[0].name, bytes: payloads[0].bytes };
}

function remote() {
  const store = new Map(), etags = new Map(), writes = [], reads = [], diagnostics = [], recoveryWarnings = [], pauses = [], starts = [];
  let now = 0, etagSerial = 0, active = 0, peak = 0;
  const hooks = { fetch: null, put: null };
  function setRemote(name, bytes, etag = `provider-etag-${++etagSerial}`) {
    store.set(name, Buffer.from(bytes)); etags.set(name, etag); return etag;
  }
  function getEtag(name) {
    if (!etags.has(name)) etags.set(name, `provider-etag-${hash(store.get(name))}`);
    return etags.get(name);
  }
  function start(kind) {
    starts.push({ kind, at: now }); active++; peak = Math.max(peak, active);
    return () => { active--; };
  }
  function precondition() {
    return Object.assign(new Error('synthetic provider precondition'), { name: 'BlobPreconditionFailedError', statusCode: 412 });
  }
  const options = {
    token: 'vercel_blob_rw_rte5guenhonw9fzn_OFFLINE_TEST_ONLY',
    clock: () => now,
    pause: async ms => { pauses.push(ms); now += ms; },
    diagnostic: value => diagnostics.push(value),
    recoveryWarning: value => recoveryWarnings.push(value),
    fetch: async url => {
      const done = start('GET');
      try {
        const name = new URL(url).pathname.slice(1); reads.push(name);
        await hooks.fetch?.(name);
        return store.has(name) ? new Response(store.get(name)) : new Response(null, { status: 404 });
      } finally { done(); }
    },
    head: async (url) => {
      const done = start('HEAD');
      try {
        const name = url.slice(BASE.length);
        return { etag: getEtag(name), url, pathname: name };
      } finally { done(); }
    },
    put: async (name, bytes, opts) => {
      const done = start('PUT');
      try {
        assert.equal(opts.token, options.token); assert.equal(opts.addRandomSuffix, false);
        assert.equal(opts.access, 'public');
        writes.push({ name, bytes: Buffer.from(bytes), options: { ...opts } });
        await hooks.put?.(name, bytes, opts);
        if (store.has(name)) {
          if (opts.allowOverwrite !== true || opts.ifMatch !== getEtag(name)) throw precondition();
        } else if (opts.allowOverwrite !== false || 'ifMatch' in opts) throw precondition();
        setRemote(name, bytes);
        return { url: BASE + name };
      } finally { done(); }
    },
  };
  return { store, etags, setRemote, writes, reads, diagnostics, recoveryWarnings, pauses, starts, get active() { return active; }, get peak() { return peak; }, hooks, options };
}

function reset(code = 'ECONNRESET', cause = undefined) {
  const error = new Error('synthetic connection reset');
  if (code !== null) error.code = code;
  if (cause !== undefined) error.cause = cause;
  return error;
}

function failManifestWrite(r) {
  const put = r.options.put;
  r.options.put = async (...args) => {
    if (args[0] === INDEX) { r.writes.push({ name: args[0], options: { ...args[2] } }); throw reset(); }
    return put(...args);
  };
}

test('payload reset reconciles exact remote bytes without a second PUT', async t => {
  const f = fixture(t), r = remote(), put = r.options.put;
  r.options.put = async (...args) => {
    if (args[0] === f.payloadName) { r.writes.push({ name: args[0], options: { ...args[2] } }); r.setRemote(args[0], args[1]); throw reset(); }
    return put(...args);
  };
  const result = await publish(f.dir, r.options);
  assert.equal(r.writes.filter(w => w.name === f.payloadName).length, 1);
  assert.equal(r.writes.at(-1).name, INDEX);
  assert.deepEqual(r.store.get(f.payloadName), f.bytes);
  assert.deepEqual(r.diagnostics, []);
  assert.equal(r.recoveryWarnings.length, 1);
  assert.deepEqual(r.recoveryWarnings[0], {
    stage: 'payload-write', category: 'reset-reconciliation', transportCode: 'ECONNRESET', attempt: 1, maxAttempts: 2,
  });
  if ('reconciled' in result) assert.ok(result.reconciled <= result.uploaded);
});

test('missing bytes get at most three probes and one retry with the original create-only condition', async t => {
  const f = fixture(t), r = remote(), put = r.options.put;
  let failed = false, probes = 0;
  const fetch = r.options.fetch;
  r.options.fetch = async (...args) => {
    const name = new URL(args[0]).pathname.slice(1);
    if (name === f.payloadName && failed && !r.store.has(name)) probes++;
    return fetch(...args);
  };
  r.options.put = async (...args) => {
    if (args[0] === f.payloadName && !failed) { failed = true; r.writes.push({ name: args[0], options: { ...args[2] } }); throw reset(); }
    return put(...args);
  };
  await publish(f.dir, r.options);
  const writes = r.writes.filter(w => w.name === f.payloadName);
  assert.equal(writes.length, 2); assert.equal(probes, 3);
  assert.equal(writes[0].options.allowOverwrite, false);
  assert.equal(writes[1].options.allowOverwrite, false);
  assert.equal('ifMatch' in writes[0].options, false);
  assert.equal('ifMatch' in writes[1].options, false);
  assert.equal(r.writes.at(-1).name, INDEX);
});

test('a create-only concurrent write after the final recovery GET is rejected with 412', async t => {
  const f = fixture(t), r = remote(); let resetThrown = false, probes = 0, payloadPuts = 0;
  r.hooks.put = async name => {
    if (name === f.payloadName && ++payloadPuts === 1) { resetThrown = true; throw reset(); }
  };
  const fetch = r.options.fetch;
  r.options.fetch = async url => {
    const name = new URL(url).pathname.slice(1), response = await fetch(url);
    if (name !== f.payloadName || !resetThrown || ++probes !== 3) return response;
    let firstStatusRead = true;
    Object.defineProperty(response, 'status', { get() {
      if (firstStatusRead) { firstStatusRead = false; r.setRemote(name, f.bytes, 'concurrent-create-etag'); }
      return 404;
    } });
    return response;
  };
  await assert.rejects(publish(f.dir, r.options));
  const writes = r.writes.filter(write => write.name === f.payloadName);
  assert.equal(probes, 3); assert.equal(writes.length, 2);
  assert.equal(writes[0].options.allowOverwrite, false); assert.equal(writes[1].options.allowOverwrite, false);
  assert.equal(writes.some(write => write.name === INDEX), false);
  assert.deepEqual(r.diagnostics.at(-1), {
    stage: 'payload-write', category: 'sdk', errorClass: 'BlobPreconditionFailedError', httpStatus: 412,
  });
});

test('conditional repair retry preserves the original ETag and stops if remote bytes changed', async t => {
  const f = fixture(t), r = remote(), original = Buffer.from('pre-existing-corrupt-bytes');
  const originalEtag = r.setRemote(f.payloadName, original, 'provider-etag-original');
  const put = r.options.put; let attempts = 0;
  r.options.put = async (...args) => {
    if (args[0] === f.payloadName && attempts++ === 0) { r.writes.push({ name: args[0], options: { ...args[2] } }); throw reset(null, { code: 'ECONNRESET' }); }
    return put(...args);
  };
  await publish(f.dir, r.options);
  const writes = r.writes.filter(w => w.name === f.payloadName);
  assert.equal(writes.length, 2);
  assert.equal(writes[0].options.allowOverwrite, true);
  assert.equal(writes[1].options.allowOverwrite, true);
  assert.equal(writes[0].options.ifMatch, originalEtag);
  assert.equal(writes[1].options.ifMatch, writes[0].options.ifMatch);

  const changed = fixture(t), other = remote(), putOther = other.options.put;
  const changedPrior = Buffer.from('original-remote-bytes'); other.setRemote(changed.payloadName, changedPrior);
  let resetOnce = true;
  other.options.put = async (...args) => {
    if (args[0] === changed.payloadName && resetOnce) {
      resetOnce = false; other.writes.push({ name: args[0], options: { ...args[2] } });
      other.setRemote(args[0], Buffer.from('concurrent-writer-bytes')); throw reset();
    }
    return putOther(...args);
  };
  await assert.rejects(publish(changed.dir, other.options));
  assert.equal(other.writes.filter(w => w.name === changed.payloadName).length, 1);
  assert.equal(other.writes.some(w => w.name === INDEX), false);
});

test('same prior bytes with a changed provider ETag fail the sole retry precondition', async t => {
  const f = fixture(t), r = remote(), prior = Buffer.from('pre-existing-corrupt-bytes');
  const originalEtag = r.setRemote(f.payloadName, prior, 'provider-etag-original');
  let resetThrown = false, probes = 0, payloadPuts = 0;
  r.hooks.put = async name => {
    if (name === f.payloadName && ++payloadPuts === 1) { resetThrown = true; throw reset(); }
  };
  const fetch = r.options.fetch;
  r.options.fetch = async url => {
    const name = new URL(url).pathname.slice(1), response = await fetch(url);
    if (name !== f.payloadName || !resetThrown || ++probes !== 3) return response;
    const bytes = Buffer.from(await response.arrayBuffer());
    const finalRead = new Response(bytes);
    Object.defineProperty(finalRead, 'body', { value: {
      async *[Symbol.asyncIterator]() {
        yield bytes; // Same bytes as the original ETag-bound object.
        r.etags.set(name, 'provider-etag-changed-with-same-bytes');
      },
    } });
    return finalRead;
  };
  await assert.rejects(publish(f.dir, r.options));
  const writes = r.writes.filter(write => write.name === f.payloadName);
  assert.equal(probes, 3); assert.equal(writes.length, 2); assert.equal(payloadPuts, 2);
  assert.equal(writes[0].options.allowOverwrite, true); assert.equal(writes[1].options.allowOverwrite, true);
  assert.equal(writes[0].options.ifMatch, originalEtag); assert.equal(writes[1].options.ifMatch, originalEtag);
  assert.equal(writes.some(write => write.name === INDEX), false);
  assert.deepEqual(r.diagnostics.at(-1), {
    stage: 'payload-write', category: 'sdk', errorClass: 'BlobPreconditionFailedError', httpStatus: 412,
  });
});

test('a second reset is bounded to two PUTs total and never permits the manifest', async t => {
  const f = fixture(t), r = remote(); let calls = 0;
  r.options.put = async (name, bytes, opts) => {
    if (name === f.payloadName) { calls++; r.writes.push({ name, options: { ...opts } }); throw reset(); }
    assert.fail('manifest must not be attempted');
  };
  await assert.rejects(publish(f.dir, r.options));
  assert.equal(calls, 2);
  assert.ok(r.reads.filter(name => name === f.payloadName).length <= 7); // Initial read plus <=3 probes per reset.
  assert.equal(r.writes.some(w => w.name === INDEX), false);
});

test('workers drain a held reset-reconciliation GET after sibling failure and preserve the shared rate gate', async t => {
  const f = fixture(t, 2), r = remote();
  assert.equal(f.payloads.length, 2);
  const [reconciling, failing] = f.payloads.map(payload => payload.name);
  let resetThrown = false, recoveryEnteredResolve, siblingFailedResolve, releaseRecovery;
  const recoveryEntered = new Promise(resolve => { recoveryEnteredResolve = resolve; });
  const siblingFailed = new Promise(resolve => { siblingFailedResolve = resolve; });
  const held = new Promise(resolve => { releaseRecovery = resolve; });
  r.hooks.put = async name => {
    if (name === reconciling && !resetThrown) { resetThrown = true; throw reset(); }
    if (name === failing) { siblingFailedResolve(); throw Error('synthetic sibling worker failure'); }
  };
  r.hooks.fetch = async name => {
    if (name === reconciling && resetThrown) { recoveryEnteredResolve(); await held; }
  };
  const pending = publish(f.dir, r.options); let settled = false;
  pending.then(() => { settled = true; }, () => { settled = true; });
  await Promise.all([recoveryEntered, siblingFailed]);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(settled, false, 'publisher must wait for the in-flight reconciliation read');
  assert.ok(r.active > 0); assert.ok(r.peak <= 4);
  releaseRecovery();
  await assert.rejects(pending);
  assert.equal(r.active, 0); assert.equal(r.writes.some(write => write.name === INDEX), false);
  for (let i = 1; i < r.starts.length; i++) assert.ok(r.starts[i].at - r.starts[i - 1].at >= 100);
});

test('only pure ECONNRESET payload PUT failures recover; SDK, HTTP, TLS, DNS and unknown failures do not', async t => {
  const cases = [
    ['sdk-precondition', () => Object.assign(new Error('precondition'), { name: 'BlobPreconditionFailedError', code: 'ECONNRESET' })],
    ['http-unauthorized', () => Object.assign(new Error('http'), { status: 401 })],
    ['http-server-error', () => Object.assign(new Error('http'), { statusCode: 503 })],
    ['tls', () => reset('CERT_HAS_EXPIRED')],
    ['dns', () => reset('ENOTFOUND')],
    ['other-transport', () => reset('ETIMEDOUT')],
    ['unknown', () => new Error('unknown')],
  ];
  for (const [label, makeError] of cases) {
    const f = fixture(t), r = remote(); let calls = 0;
    r.options.put = async (name, bytes, opts) => {
      if (name === f.payloadName) { calls++; r.writes.push({ name, options: { ...opts } }); throw makeError(); }
      assert.fail(`${label}: manifest must not be attempted`);
    };
    await assert.rejects(publish(f.dir, r.options));
    assert.equal(calls, 1, label);
    assert.equal(r.reads.filter(name => name === f.payloadName).length, 1, label); // Initial read only; no recovery probe.
    assert.equal(r.writes.some(w => w.name === INDEX), false, label);
  }
});

test('recovery read failure blocks retry and manifest write reset is never retried', async t => {
  const f = fixture(t), r = remote(); let payloadPuts = 0;
  r.options.put = async (name, bytes, opts) => {
    if (name === f.payloadName) { payloadPuts++; r.writes.push({ name, options: { ...opts } }); throw reset(); }
    assert.fail('manifest must not be attempted');
  };
  const fetch = r.options.fetch;
  r.options.fetch = async url => {
    if (new URL(url).pathname.slice(1) === f.payloadName && payloadPuts) throw reset('ENOTFOUND');
    return fetch(url);
  };
  await assert.rejects(publish(f.dir, r.options));
  assert.equal(payloadPuts, 1); assert.equal(r.writes.some(w => w.name === INDEX), false);

  const m = fixture(t), mr = remote(); failManifestWrite(mr);
  await assert.rejects(publish(m.dir, mr.options));
  assert.equal(mr.writes.filter(w => w.name === INDEX).length, 1);
});

test('manifest CAS still rejects a concurrent change after successful payload reconciliation', async t => {
  const f = fixture(t), r = remote(), put = r.options.put; let payloadFailed = false, indexReads = 0;
  r.options.put = async (...args) => {
    if (args[0] === f.payloadName && !payloadFailed) {
      payloadFailed = true; r.writes.push({ name: args[0], options: { ...args[2] } });
      r.store.set(args[0], Buffer.from(args[1])); throw reset();
    }
    return put(...args);
  };
  const fetch = r.options.fetch;
  r.options.fetch = async (...args) => {
    const name = new URL(args[0]).pathname.slice(1);
    if (name === INDEX && ++indexReads === 2) return new Response(JSON.stringify({ generatedAt: '2026-10-28T00:00:00Z' }));
    return fetch(...args);
  };
  await assert.rejects(publish(f.dir, r.options));
  assert.equal(r.writes.filter(w => w.name === f.payloadName).length, 1);
  assert.equal(r.writes.some(w => w.name === INDEX), false);
  assert.deepEqual(r.diagnostics.at(-1), { stage: 'manifest-cas', category: 'manifest-changed' });
});
