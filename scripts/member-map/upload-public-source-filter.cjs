// Publish only the validated path-free catalog. Never invoke the bulk uploader
// (it also retires unrelated blobs). Credentials stay in the process environment.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { publishSourceFilter } = require('./publish-source-filter.cjs');
const { MAX_PUBLIC_BYTES } = require('./publish-source-filter.cjs');
const HOST = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com';
const NAME = 'member_map_auto_evidence.json';
const sha256 = body => crypto.createHash('sha256').update(body).digest('hex');
// An overwrite can take up to 60s to propagate through the public Blob cache.
// Retry reads only; never retry a write or accept a different payload as success.
const READBACK_DELAYS_MS = [0, 10000, 20000, 30000];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const FAILURE_CLASSES = new Set(['request-failed', 'http-error', 'invalid-json',
  'invalid-generated-at', 'older-content', 'same-age-content', 'newer-content',
  'upload-failed', 'unexpected-destination']);
function diagnosticDate(value) {
  if (typeof value !== 'string'
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
      || !Number.isFinite(Date.parse(value))) return undefined;
  return new Date(value).toISOString();
}
function safeDiagnostics(value) {
  const result = {};
  for (const key of ['expectedSha256', 'observedSha256']) {
    if (typeof value?.[key] === 'string' && /^[a-f0-9]{64}$/.test(value[key])) result[key] = value[key];
  }
  for (const key of ['expectedGeneratedAt', 'observedGeneratedAt']) {
    const date = diagnosticDate(value?.[key]);
    if (date) result[key] = date;
  }
  if (Number.isInteger(value?.httpStatus) && value.httpStatus >= 100 && value.httpStatus <= 599) result.httpStatus = value.httpStatus;
  // Zero means preflight/upload; 1..4 counts readback requests, not writes.
  if (Number.isInteger(value?.attempts) && value.attempts >= 0 && value.attempts <= READBACK_DELAYS_MS.length) result.attempts = value.attempts;
  if (FAILURE_CLASSES.has(value?.classification)) result.classification = value.classification;
  return result;
}
function contentClass(observedAt, expectedAt) {
  const observed = Date.parse(observedAt), expected = Date.parse(expectedAt);
  if (!Number.isFinite(observed) || !Number.isFinite(expected)) return 'invalid-generated-at';
  return observed < expected ? 'older-content' : observed === expected ? 'same-age-content' : 'newer-content';
}

async function upload(source, { put, head, fetch: get = fetch, sleep = delay,
  token = process.env.BLOB_READ_WRITE_TOKEN, artifactSha256, replaceSha256, env = process.env } = {}) {
  let stageName = 'credential';
  let diagnostics;
  try {
  if ([artifactSha256, replaceSha256].some(v => v !== undefined)
      && ![artifactSha256, replaceSha256].every(v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v))) throw Error();
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')) throw Error('Expected public catalog store credential missing');
  stageName = 'local-validation';
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'member-map-upload-'));
  const validated = publishSourceFilter({ source, publishDirectory: stage });
  const body = fs.readFileSync(path.join(stage, NAME));
  if (artifactSha256 && validated.sha256 !== artifactSha256) throw Error();
  const url = `${HOST}/${NAME}`;
  const expected = { expectedSha256: validated.sha256, expectedGeneratedAt: diagnosticDate(validated.generatedAt) };
  stageName = 'public-preflight';
  diagnostics = { ...expected, attempts: 0, classification: 'request-failed' };
  const preflightUrl = replaceSha256 ? `${url}?verify=${validated.sha256}-${Date.now()}` : url;
  async function responseBytes(response) {
    if (!replaceSha256) return Buffer.from(await response.arrayBuffer());
    if (Number(response.headers.get('content-length')) > MAX_PUBLIC_BYTES) throw Error();
    const chunks = []; let bytes = 0;
    for await (const chunk of response.body) {
      bytes += chunk.length;
      if (bytes > MAX_PUBLIC_BYTES) throw Error();
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  }
  const prior = await get(preflightUrl, { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(30000) });
  if (replaceSha256 && (prior.redirected || prior.url !== preflightUrl)) throw Error();
  diagnostics.httpStatus = prior.status;
  let same = false, ifMatch;
  if (prior.ok) {
    const priorBody = await responseBytes(prior);
    diagnostics.observedSha256 = sha256(priorBody);
    same = diagnostics.observedSha256 === validated.sha256;
    if (same && !replaceSha256) return { ...validated, destination: url, uploaded: false, verified: true };
    if (replaceSha256 && !same && diagnostics.observedSha256 !== replaceSha256) throw Error();
    diagnostics.classification = 'invalid-json';
    const old = JSON.parse(priorBody.toString('utf8'));
    diagnostics.observedGeneratedAt = diagnosticDate(old?.generatedAt);
    diagnostics.classification = contentClass(old?.generatedAt, validated.generatedAt);
    if (!same && !(Date.parse(validated.generatedAt) > Date.parse(old?.generatedAt))) throw Error('Refusing to replace same-age or newer public catalog');
  } else if (prior.status !== 404) {
    diagnostics.classification = 'http-error';
    throw Error(`Catalog preflight HTTP ${prior.status}`);
  }
  if (replaceSha256 && prior.status === 404) throw Error();
  if (replaceSha256 && !same) {
    stageName = 'storage-precondition';
    if (Object.keys(env).some(key => /^(?:NEXT_PUBLIC_)?VERCEL_BLOB_(?:API_|PROXY_)/.test(key)
        || key === 'DEBUG' || key === 'VERCEL_DEBUG')) throw Error();
    const meta = await (head || require('@vercel/blob').head)(url, { token, abortSignal: AbortSignal.timeout(30000) });
    if (meta.url !== url || meta.pathname !== NAME || typeof meta.etag !== 'string'
        || !meta.etag || meta.etag === '*' || /[\r\n]/.test(meta.etag) || meta.etag.startsWith('W/')
        || !prior.headers.get('etag') || prior.headers.get('etag').replace(/^W\//, '') !== meta.etag) throw Error();
    ifMatch = meta.etag;
  }
  stageName = 'upload';
  diagnostics = { ...expected, attempts: 0, classification: 'upload-failed' };
  let result;
  if (!same) {
    const retries = env.VERCEL_BLOB_RETRIES;
    try {
      if (replaceSha256) env.VERCEL_BLOB_RETRIES = '0';
      result = await put(NAME, body, { token, access: 'public', addRandomSuffix: false,
        allowOverwrite: true, ...(ifMatch ? { ifMatch, multipart: false, abortSignal: AbortSignal.timeout(30000) } : {}),
        contentType: 'application/json', cacheControlMaxAge: 600 });
    } finally {
      if (replaceSha256) {
        if (retries === undefined) delete env.VERCEL_BLOB_RETRIES;
        else env.VERCEL_BLOB_RETRIES = retries;
      }
    }
  } else result = { url };
  stageName = 'destination-validation';
  diagnostics.classification = 'unexpected-destination';
  if (result.url !== url) throw Error('Unexpected upload destination');
  for (let attempt = 0; attempt < READBACK_DELAYS_MS.length; attempt++) {
    if (READBACK_DELAYS_MS[attempt]) await sleep(READBACK_DELAYS_MS[attempt]);
    stageName = 'public-readback';
    // Each request replaces the prior observation; a transport failure must not
    // inherit an earlier response's hash, date or HTTP status.
    diagnostics = { ...expected, attempts: attempt + 1, classification: 'request-failed' };
    const readbackUrl = replaceSha256 ? url : `${url}?sha=${validated.sha256}&attempt=${attempt}`;
    const response = await get(readbackUrl, { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(30000) });
    if (replaceSha256 && (response.redirected || response.url !== readbackUrl)) throw Error();
    diagnostics.httpStatus = response.status;
    const last = attempt === READBACK_DELAYS_MS.length - 1;
    if (!response.ok) {
      diagnostics.classification = 'http-error';
      // Do not hide denied access or malformed requests behind retries.
      if (!last && (response.status === 404 || response.status === 429 || response.status >= 500)) {
        await response.body?.cancel();
        continue;
      }
      throw Error(`Catalog readback HTTP ${response.status}`);
    }
    const readback = await responseBytes(response);
    stageName = 'readback-hash';
    diagnostics.observedSha256 = sha256(readback);
    if (diagnostics.observedSha256 === validated.sha256) {
      return { ...validated, destination: url, uploaded: !same, verified: true, readbackAttempts: attempt + 1 };
    }
    // Only an older, parseable catalog can plausibly be propagation lag.
    // Corrupt, same-age altered or newer content must fail immediately.
    diagnostics.classification = 'invalid-json';
    const observed = JSON.parse(readback.toString('utf8'));
    diagnostics.observedGeneratedAt = diagnosticDate(observed?.generatedAt);
    diagnostics.classification = contentClass(observed?.generatedAt, validated.generatedAt);
    if (last || !(Date.parse(observed?.generatedAt) < Date.parse(validated.generatedAt))) {
      throw Error('Catalog readback hash mismatch');
    }
  }
  } catch {
    // Only typed, allowlisted diagnostics. Never expose provider text or keys.
    const failure = new Error('Public catalog operation failed');
    failure.stage = stageName;
    if (diagnostics) failure.diagnostics = safeDiagnostics(diagnostics);
    throw failure;
  }
}
function failureSummary(error) {
  const stages = ['credential', 'local-validation', 'public-preflight', 'storage-precondition', 'upload',
    'destination-validation', 'public-readback', 'readback-hash'];
  const summary = { status: 'failed', stage: stages.includes(error?.stage) ? error.stage : 'unknown' };
  const diagnostics = safeDiagnostics(error?.diagnostics);
  if (Object.keys(diagnostics).length) summary.diagnostics = diagnostics;
  return summary;
}
module.exports = { upload, failureSummary };
if (require.main === module) {
  const args = process.argv.slice(2), source = args.shift(), options = {};
  try {
    while (args.length) {
      const key = { '--artifact-sha256': 'artifactSha256', '--replace-sha256': 'replaceSha256' }[args.shift()];
      const value = args.shift();
      if (!key || options[key] || !/^[a-f0-9]{64}$/.test(value || '')) throw Error();
      options[key] = value;
    }
    if (!source || Object.keys(options).length !== 0 && Object.keys(options).length !== 2) throw Error();
  } catch { console.error(JSON.stringify({ status: 'failed', stage: 'arguments' })); process.exit(1); }
  upload(source, { ...options, put: require('@vercel/blob').put })
    .then(result => console.log(JSON.stringify(result)))
    .catch(error => { console.error(JSON.stringify(failureSummary(error))); process.exitCode = 1; });
}
