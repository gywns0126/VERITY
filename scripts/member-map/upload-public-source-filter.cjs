// Publish only the validated path-free catalog. Never invoke the bulk uploader
// (it also retires unrelated blobs). Credentials stay in the process environment.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { publishSourceFilter } = require('./publish-source-filter.cjs');
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

async function upload(source, { put, fetch: get = fetch, sleep = delay, token = process.env.BLOB_READ_WRITE_TOKEN } = {}) {
  let stageName = 'credential';
  let diagnostics;
  try {
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')) throw Error('Expected public catalog store credential missing');
  stageName = 'local-validation';
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'member-map-upload-'));
  const validated = publishSourceFilter({ source, publishDirectory: stage });
  const body = fs.readFileSync(path.join(stage, NAME));
  const url = `${HOST}/${NAME}`;
  const expected = { expectedSha256: validated.sha256, expectedGeneratedAt: diagnosticDate(validated.generatedAt) };
  stageName = 'public-preflight';
  diagnostics = { ...expected, attempts: 0, classification: 'request-failed' };
  const prior = await get(url, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
  diagnostics.httpStatus = prior.status;
  if (prior.ok) {
    const priorBody = Buffer.from(await prior.arrayBuffer());
    diagnostics.observedSha256 = sha256(priorBody);
    if (diagnostics.observedSha256 === validated.sha256) return { ...validated, destination: url, uploaded: false, verified: true };
    diagnostics.classification = 'invalid-json';
    const old = JSON.parse(priorBody.toString('utf8'));
    diagnostics.observedGeneratedAt = diagnosticDate(old?.generatedAt);
    diagnostics.classification = contentClass(old?.generatedAt, validated.generatedAt);
    if (!(Date.parse(validated.generatedAt) > Date.parse(old?.generatedAt))) throw Error('Refusing to replace same-age or newer public catalog');
  } else if (prior.status !== 404) {
    diagnostics.classification = 'http-error';
    throw Error(`Catalog preflight HTTP ${prior.status}`);
  }
  stageName = 'upload';
  diagnostics = { ...expected, attempts: 0, classification: 'upload-failed' };
  const result = await put(NAME, body, { token, access: 'public', addRandomSuffix: false,
    allowOverwrite: true, contentType: 'application/json', cacheControlMaxAge: 600 });
  stageName = 'destination-validation';
  diagnostics.classification = 'unexpected-destination';
  if (result.url !== url) throw Error('Unexpected upload destination');
  for (let attempt = 0; attempt < READBACK_DELAYS_MS.length; attempt++) {
    if (READBACK_DELAYS_MS[attempt]) await sleep(READBACK_DELAYS_MS[attempt]);
    stageName = 'public-readback';
    // Each request replaces the prior observation; a transport failure must not
    // inherit an earlier response's hash, date or HTTP status.
    diagnostics = { ...expected, attempts: attempt + 1, classification: 'request-failed' };
    const response = await get(`${url}?sha=${validated.sha256}&attempt=${attempt}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
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
    const readback = Buffer.from(await response.arrayBuffer());
    stageName = 'readback-hash';
    diagnostics.observedSha256 = sha256(readback);
    if (diagnostics.observedSha256 === validated.sha256) {
      return { ...validated, destination: url, uploaded: true, verified: true, readbackAttempts: attempt + 1 };
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
  const stages = ['credential', 'local-validation', 'public-preflight', 'upload',
    'destination-validation', 'public-readback', 'readback-hash'];
  const summary = { status: 'failed', stage: stages.includes(error?.stage) ? error.stage : 'unknown' };
  const diagnostics = safeDiagnostics(error?.diagnostics);
  if (Object.keys(diagnostics).length) summary.diagnostics = diagnostics;
  return summary;
}
module.exports = { upload, failureSummary };
if (require.main === module) {
  if (process.argv.length !== 3) throw Error('Usage: upload-public-source-filter.cjs SOURCE');
  upload(process.argv[2], { put: require('@vercel/blob').put })
    .then(result => console.log(JSON.stringify(result)))
    .catch(error => { console.error(JSON.stringify(failureSummary(error))); process.exitCode = 1; });
}
