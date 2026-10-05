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

async function upload(source, { put, fetch: get = fetch, token = process.env.BLOB_READ_WRITE_TOKEN } = {}) {
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')) throw Error('Expected public catalog store credential missing');
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), 'member-map-upload-'));
  const validated = publishSourceFilter({ source, publishDirectory: stage });
  const body = fs.readFileSync(path.join(stage, NAME));
  const url = `${HOST}/${NAME}`;
  const prior = await get(url, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
  if (prior.ok) {
    const priorBody = Buffer.from(await prior.arrayBuffer());
    if (sha256(priorBody) === validated.sha256) return { ...validated, destination: url, uploaded: false, verified: true };
    const old = JSON.parse(priorBody.toString('utf8'));
    if (!(Date.parse(validated.generatedAt) > Date.parse(old.generatedAt))) throw Error('Refusing to replace same-age or newer public catalog');
  } else if (prior.status !== 404) throw Error(`Catalog preflight HTTP ${prior.status}`);
  const result = await put(NAME, body, { token, access: 'public', addRandomSuffix: false,
    allowOverwrite: true, contentType: 'application/json', cacheControlMaxAge: 600 });
  if (result.url !== url) throw Error('Unexpected upload destination');
  const response = await get(`${url}?sha=${validated.sha256}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw Error(`Catalog readback HTTP ${response.status}`);
  const readback = Buffer.from(await response.arrayBuffer());
  if (sha256(readback) !== validated.sha256) throw Error('Catalog readback hash mismatch');
  return { ...validated, destination: url, uploaded: true, verified: true };
}
module.exports = { upload };
if (require.main === module) {
  if (process.argv.length !== 3) throw Error('Usage: upload-public-source-filter.cjs SOURCE');
  upload(process.argv[2], { put: require('@vercel/blob').put })
    .then(result => console.log(JSON.stringify(result)))
    .catch(() => { console.error('Public catalog upload failed; no credential details logged'); process.exitCode = 1; });
}
