#!/usr/bin/env node
'use strict';

// Optional public candidates only. Never imports the core publisher or collector.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const BASE = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/';
const RELEASE = 'member_map_company_release.json';
const PARENT = 'portfolio_public_business_release.json';
const PREFIX = 'member_map_company_snapshots/';
const RELEASE_MAX = 128 * 1024, BUCKET_MAX = 2 * 1024 * 1024;
// Same closed six-source limits as portfolio_public_sources.PUBLIC_SOURCE_MAX_BYTES.
const SOURCES = Object.freeze({
  'universe_search.json': 16 * 1024 * 1024,
  'stock_report_public.json': 64 * 1024 * 1024,
  'us_stock_report_public.json': 64 * 1024 * 1024,
  'public_disclosure_feed.json': 16 * 1024 * 1024,
  'us_disclosure_feed.json': 16 * 1024 * 1024,
  'kr_business_overview_public.json': 8 * 1024 * 1024,
});
const HASH = /^[0-9a-f]{64}$/u, BUCKET = /^[0-9a-f]{2}$/u;
const ID = /^(?:KR:[0-9]{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?)$/u;
const BINDING = ['source_revision', 'parent_source_revision', 'implementation_sha256', 'projection_sha256', 'utc_day', 'scope'];
const digest = raw => createHash('sha256').update(raw).digest('hex');
class CandidateError extends Error {
  constructor(code) { super('company snapshot candidate rejected'); this.code = code; }
}
const reject = code => { throw new CandidateError(code); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function keys(value, required, optional = []) {
  if (!object(value) || required.some(key => !Object.hasOwn(value, key)) ||
      Object.keys(value).some(key => !required.includes(key) && !optional.includes(key))) reject('shape');
}
function integer(value, min, max) {
  if (!Number.isSafeInteger(value) || value < min || value > max) reject('integer');
}
function text(value, max, empty = false) {
  if (typeof value !== 'string' || (!empty && !value) || value.length > max ||
      /[\u0000-\u001f\u007f]|vercel_blob_|(?:sk-proj-|sb_secret_|SUPABASE_SERVICE_ROLE_KEY|DART_API_KEY|Bearer\s)/iu.test(value)) reject('text');
}
function day(value) {
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/u.test(value) ||
      !Number.isFinite(Date.parse(value + 'T00:00:00Z')) ||
      new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) !== value) reject('day');
}

function factDate(value) {
  // Public financial series retain annual labels; never fabricate January 1.
  if (typeof value === 'string' && /^[0-9]{4}$/u.test(value) && Number(value) >= 1900 && Number(value) <= 2100) return;
  day(value);
}

function strictJson(raw) {
  // JSON.parse alone accepts duplicate keys and overflowing numeric constants.
  const input = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  let i = 0;
  const space = () => { while (/[\x20\t\n\r]/u.test(input[i] || '\0')) i++; };
  function string() {
    const start = i++;
    while (i < input.length) {
      const c = input[i++];
      if (c === '"') return JSON.parse(input.slice(start, i));
      if (c === '\\') i++;
    }
    reject('json');
  }
  function value(depth) {
    if (depth > 32) reject('depth');
    space();
    if (input[i] === '"') { string(); return; }
    if (input[i] === '{') {
      i++; space(); const seen = new Set();
      if (input[i] === '}') { i++; return; }
      while (i < input.length) {
        space(); if (input[i] !== '"') reject('json');
        const key = string(); if (seen.has(key)) reject('duplicate-key'); seen.add(key);
        space(); if (input[i++] !== ':') reject('json'); value(depth + 1); space();
        const c = input[i++]; if (c === '}') return; if (c !== ',') reject('json');
      }
      reject('json');
    }
    if (input[i] === '[') {
      i++; space(); if (input[i] === ']') { i++; return; }
      while (i < input.length) {
        value(depth + 1); space(); const c = input[i++];
        if (c === ']') return; if (c !== ',') reject('json');
      }
      reject('json');
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/u.exec(input.slice(i));
    if (!token || /^[-0-9]/u.test(token[0]) && !Number.isFinite(Number(token[0]))) reject('json');
    i += token[0].length;
  }
  value(0); space(); if (i !== input.length) reject('json');
  return JSON.parse(input);
}
function localRead(dir, name, limit) {
  const file = path.join(dir, name), stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size < 1 || stat.size > limit) reject('local-file');
  const raw = fs.readFileSync(file);
  if (raw.length < 1 || raw.length > limit) reject('local-file');
  return raw;
}
function sourceUrl(value, source) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) reject('source-url');
  if (source === 'DART') {
    if (url.hostname !== 'dart.fss.or.kr' || url.pathname !== '/dsaf001/main.do' ||
        [...url.searchParams.keys()].length !== 1 || !/^[0-9]{14}$/u.test(url.searchParams.get('rcpNo') || '')) reject('source-url');
  } else if (source === 'SEC') {
    if (url.hostname !== 'www.sec.gov' || !url.pathname.startsWith('/Archives/edgar/data/') || url.search) reject('source-url');
  } else reject('source-url');
}
function company(row, identifier) {
  keys(row, ['id', 'market', 'ticker', 'name', 'sector', 'facts', 'documents'], ['source_names']);
  if (row.id !== identifier || !ID.test(identifier) || row.market !== identifier.slice(0, 2) || row.ticker !== identifier.slice(3)) reject('company-id');
  text(row.name, 160); if (row.sector !== null) text(row.sector, 120);
  if ('source_names' in row && (!Array.isArray(row.source_names) || row.source_names.length > 4 ||
      row.source_names.some(value => { text(value, 160); return false; }))) reject('source-names');
  if (!Array.isArray(row.facts) || !Array.isArray(row.documents)) reject('company-fields');
  for (const fact of row.facts) {
    keys(fact, ['metric', 'value', 'unit', 'as_of', 'source'], ['provenance']);
    if (typeof fact.value !== 'number' || !Number.isFinite(fact.value) || !['DART', 'SEC', 'KRX'].includes(fact.source)) reject('fact');
    text(fact.metric, 80); text(fact.unit, 30); factDate(fact.as_of);
    if ('provenance' in fact) {
      keys(fact.provenance, [], ['kind', 'rcept_no', 'period_start', 'period_end', 'filed', 'fs_div',
        'account_name', 'source_url', 'cik', 'accession', 'form', 'tag', 'currency_verified']);
      for (const v of Object.values(fact.provenance)) if (typeof v !== 'boolean') text(v, 600);
    }
  }
  const ids = new Set();
  for (const doc of row.documents) {
    keys(doc, ['id', 'title', 'url', 'as_of', 'kind', 'source'], ['item_codes', 'filing']);
    text(doc.id, 400); text(doc.title, 300); text(doc.url, 2048); day(doc.as_of);
    if (doc.kind !== 'disclosure' || ids.has(doc.id)) reject('document');
    sourceUrl(doc.url, doc.source); ids.add(doc.id);
    if ('item_codes' in doc && (doc.source !== 'SEC' || !Array.isArray(doc.item_codes) || doc.item_codes.length > 32 ||
        doc.item_codes.some(code => typeof code !== 'string' || !/^[1-9]\.[0-9]{2}$/u.test(code)))) reject('item-codes');
    if ('filing' in doc) {
      keys(doc.filing, ['form', 'is_correction', 'cik', 'accession_number', 'primary_document',
        'filing_date', 'report_date', 'acceptance_datetime']);
      if (doc.source !== 'SEC' || typeof doc.filing.is_correction !== 'boolean') reject('filing');
      for (const [key, v] of Object.entries(doc.filing)) if (key !== 'is_correction' && v !== null) text(v, 240);
    }
  }
}

function loadCandidate(dir) {
  if (!fs.lstatSync(dir).isDirectory() || fs.lstatSync(dir).isSymbolicLink()) reject('local-directory');
  const manifestBytes = localRead(dir, RELEASE, RELEASE_MAX), manifest = strictJson(manifestBytes);
  keys(manifest, ['schema', ...BINDING, 'parent_receipt_sha256', 'parent_artifact_sha256',
    'source_sha256', 'company_count', 'buckets']);
  if (manifest.schema !== 'member-map-company-release-v1' || manifest.scope !== 'core-facts-disclosures') reject('scope');
  for (const key of ['source_revision', 'parent_source_revision', 'implementation_sha256', 'projection_sha256',
    'parent_receipt_sha256', 'parent_artifact_sha256']) if (typeof manifest[key] !== 'string' || !HASH.test(manifest[key])) reject('hash');
  day(manifest.utc_day);
  if (manifest.utc_day !== new Date().toISOString().slice(0, 10)) reject('publisher-day');
  const modulePath = path.resolve(__dirname, '../../../vercel-api/api/portfolio_core/portfolio_company_snapshot.py');
  if (digest(fs.readFileSync(modulePath)) !== manifest.projection_sha256) reject('projection-code');
  keys(manifest.source_sha256, Object.keys(SOURCES));
  if (Object.values(manifest.source_sha256).some(value => typeof value !== 'string' || !HASH.test(value))) reject('source-hash');
  integer(manifest.company_count, 1, 50000); keys(manifest.buckets, [], Object.keys(manifest.buckets));
  if (Object.keys(manifest.buckets).length < 1 || Object.keys(manifest.buckets).length > 256) reject('buckets');
  const payloads = new Map(), expectedFiles = new Set([RELEASE]), identifiers = new Set();
  let count = 0;
  for (const [bucket, entry] of Object.entries(manifest.buckets)) {
    if (!BUCKET.test(bucket)) reject('bucket-id');
    keys(entry, ['sha256', 'bytes', 'companies']);
    if (typeof entry.sha256 !== 'string' || !HASH.test(entry.sha256)) reject('bucket-hash');
    integer(entry.bytes, 1, BUCKET_MAX); integer(entry.companies, 1, 50000);
    const name = entry.sha256 + '.json', raw = localRead(dir, name, BUCKET_MAX);
    if (raw.length !== entry.bytes || digest(raw) !== entry.sha256) reject('bucket-bytes');
    const body = strictJson(raw);
    keys(body, ['schema', ...BINDING, 'companies']);
    if (body.schema !== 'member-map-company-bucket-v1' || BINDING.some(key => body[key] !== manifest[key])) reject('bucket-generation');
    keys(body.companies, [], Object.keys(body.companies));
    if (Object.keys(body.companies).length !== entry.companies) reject('bucket-count');
    for (const [id, row] of Object.entries(body.companies)) {
      if (!ID.test(id) || digest(Buffer.from(id, 'ascii')).slice(0, 2) !== bucket || identifiers.has(id)) reject('company-bucket');
      company(row, id); identifiers.add(id);
    }
    count += entry.companies; expectedFiles.add(name); payloads.set(PREFIX + name, raw);
  }
  if (count !== manifest.company_count || fs.readdirSync(dir).some(name => !expectedFiles.has(name))) reject('candidate-denominator');
  return { manifest, manifestBytes, payloads };
}

async function readPublic(name, limit, fetcher, { missing = false } = {}) {
  if (name !== RELEASE && name !== PARENT && !Object.hasOwn(SOURCES, name) &&
      !(name.startsWith(PREFIX) && HASH.test(name.slice(PREFIX.length, -5)) && name.endsWith('.json'))) reject('remote-path');
  const url = BASE + name;
  const response = await fetcher(url, { method: 'GET', redirect: 'error', cache: 'no-store',
    headers: { Accept: 'application/json', 'Cache-Control': 'no-cache' }, signal: AbortSignal.timeout(30000) });
  if (response.redirected || response.url !== url) reject('remote-destination');
  if (response.status === 404 && missing) { await response.body?.cancel(); return null; }
  if (response.status !== 200 || !response.body) reject('remote-status');
  const mime = (response.headers.get('content-type') || '').split(';', 1)[0].trim();
  if (!['application/json', 'text/json'].includes(mime)) reject('remote-mime');
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^[0-9]+$/u.test(declared) || Number(declared) > limit)) reject('remote-limit');
  const chunks = []; let size = 0;
  try {
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > limit) reject('remote-limit');
      chunks.push(Buffer.from(chunk));
    }
  } catch (error) {
    try { await response.body.cancel(); } catch { /* Do not expose transport failures. */ }
    throw error;
  }
  if (!size) reject('remote-empty');
  return { bytes: Buffer.concat(chunks), etag: response.headers.get('etag') };
}

async function publishCandidate(data, { put, fetch: fetcher, token }) {
  // Blob's public hostname folds store ID case; keep the original token intact.
  // Match the same fixed store as the established public-source publishers.
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/iu.test(token || '')) reject('credential-store');
  const before = await readPublic(RELEASE, RELEASE_MAX, fetcher, { missing: true });
  if (before && (!before.etag || !/^"[\x21\x23-\x7e]{1,126}"$/u.test(before.etag))) reject('release-etag');
  async function parent() {
    const value = await readPublic(PARENT, 4096, fetcher);
    if (digest(value.bytes) !== data.manifest.parent_receipt_sha256) reject('parent-changed');
    const body = strictJson(value.bytes);
    keys(body, ['schema', 'artifact_sha256', 'source_revision', 'implementation_sha256', 'utc_day']);
    if (body.schema !== 'portfolio-public-business-release-v1' || body.artifact_sha256 !== data.manifest.parent_artifact_sha256 ||
        body.source_revision !== data.manifest.parent_source_revision || body.implementation_sha256 !== data.manifest.implementation_sha256 ||
        body.utc_day !== data.manifest.utc_day) reject('parent-binding');
  }
  await parent();
  // Exactly one raw GET for each fixed source. ETag/HEAD never substitutes for bytes.
  for (const [name, limit] of Object.entries(SOURCES)) {
    const value = await readPublic(name, limit, fetcher);
    if (digest(value.bytes) !== data.manifest.source_sha256[name]) reject('source-changed');
  }
  await parent();
  let uploaded = 0, unchanged = 0;
  for (const [name, bytes] of data.payloads) {
    const prior = await readPublic(name, BUCKET_MAX, fetcher, { missing: true });
    if (prior) {
      if (!prior.bytes.equals(bytes)) reject('immutable-conflict');
      unchanged++; continue;
    }
    const written = await put(name, bytes, { token, access: 'public', addRandomSuffix: false,
      allowOverwrite: false, contentType: 'application/json', cacheControlMaxAge: 31536000,
      abortSignal: AbortSignal.timeout(30000) });
    if (written?.url !== BASE + name || written?.pathname !== name) reject('write-destination');
    const actual = await readPublic(name, BUCKET_MAX, fetcher);
    if (!actual.bytes.equals(bytes)) reject('bucket-readback');
    uploaded++;
  }
  const current = await readPublic(RELEASE, RELEASE_MAX, fetcher, { missing: true });
  if ((before === null) !== (current === null) || before && !before.bytes.equals(current.bytes)) reject('release-changed');
  await parent();
  if (before && before.bytes.equals(data.manifestBytes)) return { uploaded, unchanged, release: 'unchanged' };
  // Original first-GET condition is never relaxed/retried. The root is always last.
  const written = await put(RELEASE, data.manifestBytes, { token, access: 'public', addRandomSuffix: false,
    allowOverwrite: before !== null, ...(before ? { ifMatch: before.etag } : {}),
    contentType: 'application/json', cacheControlMaxAge: 60, abortSignal: AbortSignal.timeout(30000) });
  if (written?.url !== BASE + RELEASE || written?.pathname !== RELEASE) reject('write-destination');
  const actual = await readPublic(RELEASE, RELEASE_MAX, fetcher);
  if (!actual.bytes.equals(data.manifestBytes)) reject('release-readback');
  return { uploaded, unchanged, release: 'published' };
}
function sdkMetadata(resolve = require.resolve) {
  // package.json is not an exported package subpath in @vercel/blob2.4.1.
  const entry = resolve('@vercel/blob');
  const metadata = strictJson(fs.readFileSync(path.join(path.dirname(entry), '../package.json')));
  if (metadata.name !== '@vercel/blob' || metadata.version !== '2.4.1') reject('conditional-sdk');
  return metadata;
}
async function publishWithSdk(data) {
  if (Object.keys(process.env).some(key => /^(?:NEXT_PUBLIC_)?VERCEL_BLOB_(?:API_|PROXY_)/u.test(key)) ||
      process.env.DEBUG || process.env.VERCEL_DEBUG || process.env.NEXT_PUBLIC_DEBUG ||
      process.env.BLOB_STORE_ID || process.env.VERCEL_OIDC_TOKEN) reject('environment');
  process.env.VERCEL_BLOB_RETRIES = '0';
  sdkMetadata();
  const sdk = require('@vercel/blob');
  if (typeof sdk.BlobPreconditionFailedError !== 'function' || typeof sdk.put !== 'function') reject('conditional-sdk');
  return publishCandidate(data, { put: sdk.put, fetch: globalThis.fetch, token: process.env.BLOB_READ_WRITE_TOKEN });
}

const REASONS = new Set([
  'published', 'unchanged', 'validation-only', 'publisher-error', 'candidate-rejected',
  'arguments', 'shape', 'integer', 'text', 'day', 'json', 'depth', 'duplicate-key',
  'local-file', 'local-directory', 'source-url', 'company-id', 'source-names', 'company-fields',
  'fact', 'document', 'item-codes', 'filing', 'scope', 'hash', 'publisher-day', 'projection-code',
  'source-hash', 'buckets', 'bucket-id', 'bucket-hash', 'bucket-bytes', 'bucket-generation',
  'bucket-count', 'company-bucket', 'candidate-denominator', 'remote-path', 'remote-destination',
  'remote-status', 'remote-mime', 'remote-limit', 'remote-empty', 'credential-store', 'release-etag',
  'parent-changed', 'parent-binding', 'source-changed', 'immutable-conflict', 'write-destination',
  'bucket-readback', 'release-changed', 'release-readback', 'environment', 'conditional-sdk',
  'summary-path', 'publication-result',
]);
function openSummary(dir, output) {
  const candidate = fs.realpathSync(dir), requested = path.resolve(output);
  const parent = fs.realpathSync(path.dirname(requested)), target = path.join(parent, path.basename(requested));
  if (target === candidate || parent === candidate || parent.startsWith(candidate + path.sep)) reject('summary-path');
  return fs.openSync(target, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
}
function summaryValue(data, status, reason) {
  return {
    status: ['published', 'unchanged'].includes(status) ? status : 'held',
    reason_code: REASONS.has(reason) ? reason : 'publisher-error',
    buckets: data ? data.payloads.size : null,
    companies: data ? data.manifest.company_count : null,
    manifest_sha256: data ? digest(data.manifestBytes) : null,
    manifest_bytes: data ? data.manifestBytes.length : null,
    parent_receipt_sha256: data ? data.manifest.parent_receipt_sha256 : null,
    source_revision: data ? data.manifest.source_revision : null,
  };
}
async function processCandidate(dir, { publish = false, summaryOutput, perform = publishWithSdk } = {}) {
  // No environment-selected destination: the caller must supply this new path.
  const fd = summaryOutput ? openSummary(dir, summaryOutput) : null;
  let data = null, status = 'held', reason = 'candidate-rejected';
  try {
    data = loadCandidate(dir);
    if (!publish) {
      reason = 'validation-only';
      return { validated: true, buckets: data.payloads.size, companies: data.manifest.company_count };
    }
    const result = await perform(data);
    if (!['published', 'unchanged'].includes(result?.release)) reject('publication-result');
    status = result.release; reason = result.release;
    return result;
  } catch (error) {
    reason = error instanceof CandidateError && REASONS.has(error.code) ? error.code : 'publisher-error';
    throw error;
  } finally {
    if (fd !== null) {
      try { fs.writeFileSync(fd, JSON.stringify(summaryValue(data, status, reason)) + '\n'); }
      finally { fs.closeSync(fd); }
    }
  }
}
async function main(argv = process.argv.slice(2)) {
  let dir, publish = false, summaryOutput;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--publish' && !publish) { publish = true; continue; }
    if (argv[i] === '--output-dir' && !dir && argv[i + 1]) { dir = argv[++i]; continue; }
    if (argv[i] === '--summary-output' && !summaryOutput && argv[i + 1]) { summaryOutput = argv[++i]; continue; }
    reject('arguments');
  }
  if (!dir) reject('arguments');
  return processCandidate(path.resolve(dir), { publish, summaryOutput });
}
module.exports = { loadCandidate, strictJson, readPublic, publishCandidate, main, processCandidate, sdkMetadata, BASE, RELEASE, PARENT, PREFIX, SOURCES };
if (require.main === module) main().then(result => console.log(JSON.stringify(result))).catch(() => {
  // Fixed warning only. SDK/HTTP exceptions can contain tokens, URLs or bodies.
  console.error('company snapshot candidate held'); process.exitCode = 1;
});
