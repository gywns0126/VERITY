// One fixed public overview only. No bulk uploader, deletes, dotenv or local writes.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { isDeepStrictEqual } = require('node:util');
const ROOT = path.resolve(__dirname, '../..');
const NAME = 'kr_business_overview_public.json';
const URL = `https://rte5guenhonw9fzn.public.blob.vercel-storage.com/${NAME}`;
// Also checked against the authoritative Python constant on every validation.
const LIMIT = 8 * 1024 * 1024;
const DELAYS = [0, 10000, 20000, 30000];
const sha = body => createHash('sha256').update(body).digest('hex');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const VALIDATOR = String.raw`
import json, re, sys
from api.intelligence.portfolio_public_sources import (
    project_public_business_overviews, PUBLIC_SOURCE_MAX_BYTES, _reject_duplicate_keys, safe_public_text,
    _PATH_RE, _EMAIL_RE, _JWT_RE, _SECRET_KEY_RE)
name = 'kr_business_overview_public.json'
assert PUBLIC_SOURCE_MAX_BYTES[name] == 8 * 1024 * 1024
raw = sys.stdin.buffer.read(PUBLIC_SOURCE_MAX_BYTES[name] + 1)
assert 0 < len(raw) <= PUBLIC_SOURCE_MAX_BYTES[name]
def invalid_constant(value):
    raise ValueError()
doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_reject_duplicate_keys,
                 parse_constant=invalid_constant)
def privacy(value):
    if isinstance(value, str):
        assert not any(p.search(value) for p in (_PATH_RE, _EMAIL_RE, _JWT_RE, _SECRET_KEY_RE))
        assert not re.search(r'vercel_blob_rw_|-----BEGIN .*PRIVATE KEY|Bearer\s+\S+', value, re.I)
    elif isinstance(value, dict):
        for key, item in value.items():
            privacy(key)
            privacy(item)
    elif isinstance(value, list):
        for item in value:
            privacy(item)
privacy(doc)
# These descriptive fields are not projected by the consumer; validate them too.
for field in ('source', 'note'):
    if field in doc['_meta']:
        assert safe_public_text(doc['_meta'][field], 1000) is not None
for row in doc['rows'].values():
    assert safe_public_text(row['source'], 240) is not None
result = project_public_business_overviews({name: doc})
accepted = {r['issuer_id'][3:] for r in result['rows']}
assert accepted
print(json.dumps({'accepted': len(accepted), 'rejected': sorted(set(doc['rows']) - accepted)}))
`;

function validateOverview(body) {
  const result = spawnSync('python3', ['-c', VALIDATOR], {
    cwd: ROOT, input: body, encoding: 'utf8', timeout: 15000, maxBuffer: 1024 * 1024,
    env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: '1' },
  });
  if (result.error || result.status !== 0) throw Error('Overview validation rejected');
  return JSON.parse(result.stdout);
}

const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
function keys(v, allowed, required = allowed) {
  if (!object(v) || Object.keys(v).some(k => !allowed.includes(k))
      || required.some(k => !Object.hasOwn(v, k))) throw Error();
}
function stamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
      || !Number.isFinite(Date.parse(value))) throw Error();
  return Date.parse(value);
}
function filed(value) {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) throw Error();
  const iso = `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}`;
  if (!Number.isFinite(Date.parse(iso)) || new Date(iso).toISOString().slice(0, 10) !== iso) throw Error();
  return value;
}
function parse(body) {
  if (!Buffer.isBuffer(body) || !body.length || body.length > LIMIT) throw Error();
  const doc = JSON.parse(body.toString('utf8'));
  keys(doc, ['_meta', 'rows']);
  keys(doc._meta, ['generated_at', 'source', 'count', 'universe', 'publish_chars', 'truncated_n', 'note', 'manual_recovery'],
    ['generated_at', 'count']);
  stamp(doc._meta.generated_at);
  if (!object(doc.rows) || doc._meta.count !== Object.keys(doc.rows).length) throw Error();
  if (doc._meta.manual_recovery !== undefined) {
    keys(doc._meta.manual_recovery, ['processed', 'requested', 'unresolved', 'source_as_of']);
  }
  for (const [ticker, row] of Object.entries(doc.rows)) {
    if (!/^\d{6}$/.test(ticker)) throw Error();
    keys(row, ['name', 'text', 'chars', 'truncated', 'fiscal_year', 'filed_at', 'report', 'source', 'url']);
    filed(row.filed_at);
    if (typeof row.url !== 'string' || !/^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(row.url)) throw Error();
  }
  return doc;
}
function validate(body, validator) {
  const doc = parse(body);
  const result = validator(body);
  if (!object(result) || !Number.isInteger(result.accepted) || result.accepted < 1
      || !Array.isArray(result.rejected) || new Set(result.rejected).size !== result.rejected.length
      || result.rejected.some(t => !Object.hasOwn(doc.rows, t))
      || result.accepted + result.rejected.length !== Object.keys(doc.rows).length) throw Error();
  return { doc, ...result };
}
function readLocal(source) {
  if (typeof source !== 'string' || path.basename(source) !== NAME || source.split(/[\\/]/).includes('..')) throw Error();
  if (!fs.lstatSync(source).isFile()) throw Error();
  const fd = fs.openSync(source, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const size = fs.fstatSync(fd).size;
    if (!size || size > LIMIT) throw Error();
    const body = Buffer.alloc(size + 1);
    const count = fs.readSync(fd, body, 0, body.length, 0);
    if (count !== size) throw Error();
    return body.subarray(0, count);
  } finally { fs.closeSync(fd); }
}
async function readResponse(response, url) {
  if (response.redirected || response.url && response.url !== url || response.status !== 200
      || Number(response.headers.get('content-length')) > LIMIT || !response.body) throw Error();
  const chunks = []; let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > LIMIT) throw Error();
    chunks.push(Buffer.from(chunk));
  }
  if (!size) throw Error();
  return Buffer.concat(chunks);
}

async function upload(source, { put, fetch: get = globalThis.fetch, sleep: wait = sleep,
  token = process.env.BLOB_READ_WRITE_TOKEN, validator = validateOverview } = {}) {
  let stage = 'credential';
  try {
    if (!/^vercel_blob_rw_rte5guenhonw9fzn_/i.test(token || '')
        || Object.keys(process.env).some(k => /^(?:NEXT_PUBLIC_)?VERCEL_BLOB_(?:API_|PROXY_)/.test(k)
          || k === 'DEBUG' || k === 'VERCEL_DEBUG')) throw Error();
    stage = 'local-validation';
    const body = readLocal(source), local = validate(body, validator), digest = sha(body);
    const summary = { filename: NAME, destination: URL, bytes: body.length, sha256: digest,
      generatedAt: local.doc._meta.generated_at, accepted: local.accepted, rejected: local.rejected.length };
    stage = 'public-preflight';
    const options = () => ({ redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(30000) });
    // Fresh query prevents the 7200-second consumer cache from deciding replacement safety.
    const preflightUrl = `${URL}?preflight=${digest}-${Date.now()}`;
    const response = await get(preflightUrl, options());
    if (response.redirected || response.url && response.url !== preflightUrl) throw Error();
    let prior;
    if (response.status === 200) {
      const priorBody = await readResponse(response, preflightUrl);
      if (sha(priorBody) === digest) return { ...summary, uploaded: false, verified: true };
      prior = validate(priorBody, validator).doc;
      if (stamp(local.doc._meta.generated_at) <= stamp(prior._meta.generated_at)) throw Error();
      for (const [ticker, row] of Object.entries(prior.rows)) {
        if (!Object.hasOwn(local.doc.rows, ticker) || filed(local.doc.rows[ticker].filed_at) < filed(row.filed_at)) throw Error();
      }
    } else if (response.status === 404) await response.body?.cancel();
    else throw Error();
    // Rejected historical rows may survive unchanged, never enter or change here.
    for (const ticker of local.rejected) {
      if (!prior || !Object.hasOwn(prior.rows, ticker) || !isDeepStrictEqual(local.doc.rows[ticker], prior.rows[ticker])) throw Error();
    }
    stage = 'upload';
    const retries = process.env.VERCEL_BLOB_RETRIES;
    let result;
    try {
      process.env.VERCEL_BLOB_RETRIES = '0';
      result = await (put || require('@vercel/blob').put)(NAME, body, {
        token, access: 'public', addRandomSuffix: false, allowOverwrite: true, multipart: false,
        contentType: 'application/json', cacheControlMaxAge: 7200, abortSignal: AbortSignal.timeout(30000),
      });
    } finally {
      if (retries === undefined) delete process.env.VERCEL_BLOB_RETRIES;
      else process.env.VERCEL_BLOB_RETRIES = retries;
    }
    stage = 'destination-validation';
    if (result.url !== URL) throw Error();
    for (let attempt = 0; attempt < DELAYS.length; attempt++) {
      if (DELAYS[attempt]) await wait(DELAYS[attempt]);
      stage = 'public-readback';
      const url = `${URL}?sha=${digest}&attempt=${attempt}`;
      const readback = await get(url, options());
      if (readback.redirected || readback.url && readback.url !== url) throw Error();
      if (readback.status !== 200) {
        await readback.body?.cancel();
        if (attempt < DELAYS.length - 1 && [404, 429, 500, 502, 503, 504].includes(readback.status)) continue;
        throw Error();
      }
      const observed = await readResponse(readback, url);
      stage = 'readback-hash';
      if (sha(observed) === digest) return { ...summary, uploaded: true, verified: true, readbackAttempts: attempt + 1 };
      if (attempt === DELAYS.length - 1 || stamp(parse(observed)._meta.generated_at) >= stamp(local.doc._meta.generated_at)) throw Error();
    }
  } catch {
    const failure = Error('Public overview operation failed');
    failure.stage = stage;
    throw failure;
  }
}
function failureSummary(error) {
  const stages = ['credential', 'local-validation', 'public-preflight', 'upload',
    'destination-validation', 'public-readback', 'readback-hash'];
  return { status: 'failed', stage: stages.includes(error?.stage) ? error.stage : 'unknown' };
}
module.exports = { upload, failureSummary, validateOverview, NAME, URL, LIMIT };
if (require.main === module) Promise.resolve().then(() => {
  if (process.argv.length !== 3) throw Error();
  return upload(process.argv[2]);
}).then(result => console.log(JSON.stringify(result)))
  .catch(error => { console.error(JSON.stringify(failureSummary(error))); process.exitCode = 1; });
