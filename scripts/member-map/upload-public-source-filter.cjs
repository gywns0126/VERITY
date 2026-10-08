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

async function upload(source, { put, fetch: get = fetch, sleep = delay, token = process.env.BLOB_READ_WRITE_TOKEN } = {}) {
  let stageName = 'credential';
  try {
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')) throw Error('Expected public catalog store credential missing');
  stageName = 'local-validation';
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'member-map-upload-'));
  const validated = publishSourceFilter({ source, publishDirectory: stage });
  const body = fs.readFileSync(path.join(stage, NAME));
  const url = `${HOST}/${NAME}`;
  stageName = 'public-preflight';
  const prior = await get(url, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
  if (prior.ok) {
    const priorBody = Buffer.from(await prior.arrayBuffer());
    if (sha256(priorBody) === validated.sha256) return { ...validated, destination: url, uploaded: false, verified: true };
    const old = JSON.parse(priorBody.toString('utf8'));
    if (!(Date.parse(validated.generatedAt) > Date.parse(old.generatedAt))) throw Error('Refusing to replace same-age or newer public catalog');
  } else if (prior.status !== 404) throw Error(`Catalog preflight HTTP ${prior.status}`);
  stageName = 'upload';
  const result = await put(NAME, body, { token, access: 'public', addRandomSuffix: false,
    allowOverwrite: true, contentType: 'application/json', cacheControlMaxAge: 600 });
  stageName = 'destination-validation';
  if (result.url !== url) throw Error('Unexpected upload destination');
  for (let attempt = 0; attempt < READBACK_DELAYS_MS.length; attempt++) {
    if (READBACK_DELAYS_MS[attempt]) await sleep(READBACK_DELAYS_MS[attempt]);
    stageName = 'public-readback';
    const response = await get(`${url}?sha=${validated.sha256}&attempt=${attempt}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
    const last = attempt === READBACK_DELAYS_MS.length - 1;
    if (!response.ok) {
      // Do not hide denied access or malformed requests behind retries.
      if (!last && (response.status === 404 || response.status === 429 || response.status >= 500)) {
        await response.body?.cancel();
        continue;
      }
      throw Error(`Catalog readback HTTP ${response.status}`);
    }
    const readback = Buffer.from(await response.arrayBuffer());
    stageName = 'readback-hash';
    if (sha256(readback) === validated.sha256) {
      return { ...validated, destination: url, uploaded: true, verified: true, readbackAttempts: attempt + 1 };
    }
    // Only an older, parseable catalog can plausibly be propagation lag.
    // Corrupt, same-age altered or newer content must fail immediately.
    const observed = JSON.parse(readback.toString('utf8'));
    if (last || !(Date.parse(observed.generatedAt) < Date.parse(validated.generatedAt))) {
      throw Error('Catalog readback hash mismatch');
    }
  }
  } catch {
    // Fixed internal stage only. Never expose provider exception text or keys.
    const failure = new Error('Public catalog operation failed');
    failure.stage = stageName;
    throw failure;
  }
}
function failureSummary(error) {
  const stages = ['credential', 'local-validation', 'public-preflight', 'upload',
    'destination-validation', 'public-readback', 'readback-hash'];
  return { status: 'failed', stage: stages.includes(error?.stage) ? error.stage : 'unknown' };
}
module.exports = { upload, failureSummary };
if (require.main === module) {
  if (process.argv.length !== 3) throw Error('Usage: upload-public-source-filter.cjs SOURCE');
  upload(process.argv[2], { put: require('@vercel/blob').put })
    .then(result => console.log(JSON.stringify(result)))
    .catch(error => { console.error(JSON.stringify(failureSummary(error))); process.exitCode = 1; });
}
