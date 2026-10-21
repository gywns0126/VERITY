#!/usr/bin/env node
'use strict';

// Closed public contract: never upload collector stores, raw rows or arbitrary URLs.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { primaryEvidenceUrl } = require('../../review/member-map/company-structure-data.cjs');
const { secUrl, MAX_BYTES, MAX_ISSUERS } = require('./build-live-company-structure.cjs');
const BASE = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/';
const INDEX = 'member_map_company_structure_index.json';
const SHA = /^[a-f0-9]{64}$/u;
const ID = /^(?:KR:[A-Z0-9]{6}|US:[A-Z][A-Z0-9.-]{0,11}|FOREIGN:[a-z0-9-]{1,80})$/u;
const STATUS = new Set(['not-attempted', 'legacy-only', 'curated-only', 'partial', 'source-checked', 'refresh-error']);
const corporateLabel = s => !/펀드|투자조합|개인|\b(?:fund|trust|individual)\b/iu.test(s) &&
  /(?:\(주\)|㈜|주식회사|유한회사|합자회사|유한공사|股份有限公司|\b(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|LLC|LLP|PLC|GmbH|SARL|Pte|BV|SA|Sdn\s*Bhd)\b|\b(?:L\.P\.|B\.V\.|S\.A\.|S\.R\.L\.|W\.L\.L\.)|^Solidigm$)/iu.test(s);
const digest = b => createHash('sha256').update(b).digest('hex');
const fail = () => { throw Error('Invalid public company structure artifact'); };
function keys(o, allowed) {
  if (!o || typeof o !== 'object' || Array.isArray(o) || Object.keys(o).some(k => !allowed.includes(k))) fail();
}
function text(s, max = 200) {
  if (typeof s !== 'string' || !s || s.length > max || /[<>\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]|https?:\/\/|vercel_blob_|Bearer\s|eyJ[a-zA-Z0-9_-]{20}/u.test(s)) fail();
}
function integer(n) { if (!Number.isSafeInteger(n) || n < 0) fail(); }
function time(s, nullable = false) {
  if (nullable && s === null) return;
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u.test(s) || !Number.isFinite(Date.parse(s))) fail();
}
function day(s) {
  if (s === null) return;
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/u.test(s) || new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) !== s) fail();
}
function counters(o, allowed) { keys(o, allowed); Object.values(o).forEach(integer); }
function coverage(c, manifest = false) {
  if (manifest) {
    keys(c, ['KR', 'US', 'excluded', 'limits', 'rawRowsExamined', 'rawMatchedRows', 'rawVerifiedRows', 'storedRows', 'unsupportedRows']);
    counters(c.KR, ['total', 'checked', 'pending', 'legacyOnly', 'failed', 'payloads']);
    counters(c.US, ['total', 'checked', 'pending', 'withCik', 'withoutCik', 'payloads', 'uniqueCiks', 'checkedCiks', 'pendingCiks']);
    counters(c.excluded, ['ETF', 'ETN', 'index', 'other', 'invalidTicker']);
    counters(c.limits, ['issuers', 'nodes', 'relations', 'payloadBytes', 'manifestBytes']);
    for (const k of ['rawRowsExamined', 'rawMatchedRows', 'rawVerifiedRows', 'storedRows', 'unsupportedRows']) integer(c[k]);
    for (const m of [c.KR, c.US]) if (m.total !== m.checked + m.pending || m.payloads > m.total) fail();
    return;
  }
  keys(c, ['status', 'sourceChecked', 'attemptStatus', 'endpoints', 'asOfNotCollectedAt', 'asOfMeaning', 'rawRowsExamined', 'rawMatchedRows',
    'rawVerifiedRows', 'storedRows', 'unsupportedRows', 'curatedRelations', 'displayedRelations', 'limits', 'note', 'canonicalId', 'securityIds',
    'cik', 'filedDate', 'periodEnd', 'documentSha256', 'attemptedAt', 'lastSuccessAt']);
  if (!STATUS.has(c.status) || typeof c.sourceChecked !== 'boolean' || c.asOfNotCollectedAt !== true ||
    !/^(?:success|error|partial|not-attempted|cached-same-accession|source-gap|attempting|HTTP[1-5][0-9]{2})$/u.test(c.attemptStatus)) fail();
  if (c.sourceChecked !== (c.status === 'source-checked') || c.sourceChecked && !['success', 'cached-same-accession'].includes(c.attemptStatus)) fail();
  for (const k of ['rawRowsExamined', 'rawMatchedRows', 'rawVerifiedRows', 'storedRows', 'unsupportedRows', 'curatedRelations', 'displayedRelations']) if (k in c) integer(c[k]);
  for (const k of ['note', 'asOfMeaning']) if (k in c) text(c[k], 1000);
  counters(c.limits, ['nodes', 'relations', 'bytes']);
  if (c.endpoints) {
    keys(c.endpoints, ['hyslrSttus', 'otrCprInvstmntSttus']);
    for (const e of Object.values(c.endpoints)) {
      keys(e, ['status', 'attemptStatus', 'attemptedAt', 'lastSuccessAt']);
      for (const k of ['status', 'attemptStatus']) if (k in e) text(e[k], 40);
      for (const k of ['attemptedAt', 'lastSuccessAt']) if (k in e) time(e[k], true);
    }
  }
  if (c.cik !== undefined) {
    if (!/^\d{10}$/u.test(c.cik) || !ID.test(c.canonicalId) || !Array.isArray(c.securityIds) || c.securityIds.length > 3000 || c.securityIds.some(i => !/^US:[A-Z][A-Z0-9.-]{0,11}$/u.test(i))) fail();
    day(c.filedDate); day(c.periodEnd); time(c.attemptedAt); time(c.lastSuccessAt, true);
    if (c.documentSha256 !== null && !SHA.test(c.documentSha256)) fail();
  }
}
function validatePayload(p) {
  keys(p, ['schema', 'observedAt', 'companies', 'relations', 'coverage']);
  if (p.schema !== 'alphanest-company-structure-v1' || !Array.isArray(p.companies) || !Array.isArray(p.relations) ||
    p.companies.length > 3000 || p.relations.length > 3000) fail();
  time(p.observedAt); coverage(p.coverage);
  const ids = new Set();
  for (const c of p.companies) {
    keys(c, ['id', 'name', 'ticker', 'market', 'country']); text(c.name, 180);
    if (!ID.test(c.id) || ids.has(c.id)) fail(); ids.add(c.id);
    if (c.id.startsWith('KR:') || c.id.startsWith('US:')) {
      if (c.ticker !== c.id.slice(3) || c.market !== c.id.slice(0, 2)) fail();
    } else if ('ticker' in c || 'market' in c || !corporateLabel(c.name)) fail();
    if ('country' in c && !/^[A-Z]{2}$/u.test(c.country)) fail();
  }
  const edges = new Set();
  for (const r of p.relations) {
    keys(r, ['id', 'from', 'to', 'type', 'label', 'asOf', 'observedAt', 'status', 'ownershipPct', 'evidence']);
    if (!ids.has(r.from) || !ids.has(r.to) || r.from === r.to || edges.has(r.id) || r.id !== `${r.from}|${r.type}|${r.to}` ||
      !['major-shareholder', 'investment', 'subsidiary'].includes(r.type) || !['source-dated', 'undated-snapshot', 'official-undated'].includes(r.status)) fail();
    edges.add(r.id); text(r.label, 60); day(r.asOf); time(r.observedAt);
    if (r.ownershipPct !== null && (typeof r.ownershipPct !== 'number' || !Number.isFinite(r.ownershipPct) || r.ownershipPct < 0 || r.ownershipPct > 100 || r.asOf === null)) fail();
    if (!Array.isArray(r.evidence) || r.evidence.length > 10 || (r.status === 'source-dated' && (!r.asOf || !r.evidence.length))) fail();
    for (const e of r.evidence) {
      keys(e, ['title', 'url', 'asOf']); text(e.title, 180);
      const accession = typeof e.url === 'string' && e.url.match(/\/(\d{10})(\d{2})(\d{6})\/[^/]+$/u);
      if (!(p.coverage.cik ? accession && secUrl(e.url, p.coverage.cik, `${accession[1]}-${accession[2]}-${accession[3]}`) : primaryEvidenceUrl(e.url))) fail();
      const u = new URL(e.url);
      if (u.port || u.hash || [...u.searchParams.keys()].some(k => u.hostname !== 'dart.fss.or.kr' || k !== 'rcpNo')) fail();
      if ('asOf' in e) day(e.asOf);
    }
    if (p.coverage.cik && (r.type !== 'subsidiary' || r.ownershipPct !== null || r.label !== '공시상 자회사·직간접 미구분')) fail();
  }
  if (p.coverage.cik && (!ids.has(p.coverage.canonicalId) || p.coverage.securityIds.some(id => !ids.has(id)))) fail();
}
function readLimited(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.size > MAX_BYTES) fail();
  return fs.readFileSync(file);
}
function loadArtifacts(dir) {
  const manifestBytes = readLimited(path.join(dir, INDEX)), manifest = JSON.parse(manifestBytes);
  keys(manifest, ['schema', 'generatedAt', 'coverage', 'issuers']);
  if (manifest.schema !== 'alphanest-company-structure-index-v1') fail(); time(manifest.generatedAt); coverage(manifest.coverage, true);
  if (!manifest.issuers || Array.isArray(manifest.issuers) || Object.keys(manifest.issuers).length > MAX_ISSUERS) fail();
  const payloads = new Map(), totals = { KR: 0, US: 0 };
  const child = path.join(dir, 'company-structure');
  if (fs.existsSync(child) && !fs.lstatSync(child).isDirectory()) fail();
  for (const [id, m] of Object.entries(manifest.issuers)) {
    keys(m, ['ticker', 'market', 'name', 'status', 'sha256', 'bytes']); text(m.name, 100);
    if (!/^(?:KR:[A-Z0-9]{6}|US:[A-Z][A-Z0-9.-]{0,11})$/u.test(id) || id !== `${m.market}:${m.ticker}` || !STATUS.has(m.status)) fail();
    totals[m.market]++;
    if (m.sha256 === undefined) { if (m.bytes !== undefined) fail(); continue; }
    if (!SHA.test(m.sha256)) fail(); integer(m.bytes);
    if (!payloads.has(m.sha256)) {
      const bytes = readLimited(path.join(child, m.sha256 + '.json'));
      if (digest(bytes) !== m.sha256) fail();
      const p = JSON.parse(bytes); validatePayload(p); payloads.set(m.sha256, { bytes, payload: p });
    }
    const value = payloads.get(m.sha256);
    if (value.bytes.length !== m.bytes || value.payload.coverage.status !== m.status || !value.payload.companies.some(c => c.id === id)) fail();
  }
  if (totals.KR !== manifest.coverage.KR.total || totals.US !== manifest.coverage.US.total) fail();
  return { manifest, manifestBytes, payloads };
}

async function readRemote(fetch, name) {
  const response = await fetch(BASE + name + '?verify=' + Date.now(), { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(30000) });
  if (response.status === 404) return null;
  if (!response.ok || Number(response.headers.get('content-length') || 0) > MAX_BYTES) throw Error('Blob read failed');
  const chunks = []; let size = 0;
  for await (const chunk of response.body) { size += chunk.length; if (size > MAX_BYTES) throw Error('Blob read limit'); chunks.push(chunk); }
  return Buffer.concat(chunks);
}
async function publish(dir, { put, head, fetch, token, pause = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const data = loadArtifacts(dir); // Validate EVERY local file before any remote mutation.
  if (!/^vercel_blob_rw_rte5guenhonw9fzn_/iu.test(token || '')) throw Error('Expected Blob store credential missing');
  let uploaded = 0, unchanged = 0;
  async function sync(name, bytes, expected) {
    const prior = expected ? expected.prior : await readRemote(fetch, name);
    if (prior?.equals(bytes)) { unchanged++; return; }
    const metadata = expected ? expected.metadata : prior ? await head(BASE + name, { token, abortSignal: AbortSignal.timeout(30000) }) : null;
    if (prior && !metadata?.etag) throw Error('Blob conditional write unavailable');
    if (metadata && (metadata.url !== BASE + name || metadata.pathname !== name)) throw Error('Unexpected Blob metadata');
    const result = await put(name, bytes, { token, access: 'public', addRandomSuffix: false, allowOverwrite: !!prior,
      ...(prior ? { ifMatch: metadata.etag } : {}), abortSignal: AbortSignal.timeout(30000), contentType: 'application/json', cacheControlMaxAge: name === INDEX ? 60 : 31536000 });
    if (result.url !== BASE + name) throw Error('Unexpected Blob store');
    uploaded++;
    for (let i = 0; i < 12; i++) {
      const actual = await readRemote(fetch, name);
      if (actual?.equals(bytes)) return;
      if (i < 11) await pause(5000);
    }
    throw Error('Blob exact-byte readback failed');
  }
  // Snapshot the index BEFORE uploads; a later/foreign publisher must not be overwritten.
  const before = await readRemote(fetch, INDEX);
  const indexMetadata = before ? await head(BASE + INDEX, { token, abortSignal: AbortSignal.timeout(30000) }) : null;
  if (before) {
    const prior = JSON.parse(before);
    if (!Number.isFinite(Date.parse(prior.generatedAt)) || Date.parse(prior.generatedAt) > Date.parse(data.manifest.generatedAt)) throw Error('Refusing older manifest');
  }
  const queue = [...data.payloads]; let next = 0, failure;
  async function worker() {
    while (!failure && next < queue.length) {
      const [sha, { bytes }] = queue[next++];
      try { await sync(`company-structure/${sha}.json`, bytes); }
      catch (error) { failure ||= error instanceof Error ? error : new Error('Payload publication failed'); }
    }
  }
  // Drain all in-flight requests even on failure. No manifest publication from a
  // rejected Promise.all while another payload worker is still mutating storage.
  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker));
  if (failure) throw failure;
  const current = await readRemote(fetch, INDEX);
  if ((before === null) !== (current === null) || before && !before.equals(current)) throw Error('Manifest changed during upload');
  await sync(INDEX, data.manifestBytes, { prior: before, metadata: indexMetadata }); // Last write, only after every immutable payload is verified.
  return { issuers: Object.keys(data.manifest.issuers).length, payloads: data.payloads.size, uploaded, unchanged };
}

async function main(argv = process.argv.slice(2)) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--publish') { args.publish = true; continue; }
    if (!['--output-dir', '--committed-manifest'].includes(argv[i]) || !argv[i + 1]) fail();
    const key = argv[i]; args[key] = argv[++i];
  }
  if (!args['--output-dir']) fail();
  const dir = path.resolve(args['--output-dir']), data = loadArtifacts(dir);
  if (!args.publish) return { validated: true, issuers: Object.keys(data.manifest.issuers).length, payloads: data.payloads.size };
  // A local working copy alone is not durable publication authority.
  if (args['--committed-manifest'] !== 'data/' + INDEX) fail();
  const committed = execFileSync('git', ['show', 'HEAD:data/' + INDEX], { maxBuffer: MAX_BYTES + 1 });
  if (!committed.equals(data.manifestBytes)) throw Error('Manifest is not the committed artifact');
  if (Object.keys(process.env).some(k => /^(?:NEXT_PUBLIC_)?VERCEL_BLOB_(?:API_|PROXY_)/u.test(k))) throw Error('Blob endpoint override is forbidden');
  if (process.env.DEBUG || process.env.VERCEL_DEBUG) throw Error('Debug logging is forbidden');
  process.env.VERCEL_BLOB_RETRIES = '0'; // No SDK write retries (readback retries are bounded separately).
  const { put, head } = require('@vercel/blob');
  return publish(dir, { put, head, fetch: globalThis.fetch, token: process.env.BLOB_READ_WRITE_TOKEN });
}
function sanitizeUsSources(doc) {
  if (doc?.schema !== 'alphanest-company-structure-us-sources-v1' || !doc.issuers || typeof doc.issuers !== 'object' || Array.isArray(doc.issuers)) fail();
  const clean = { schema: doc.schema, generatedAt: doc.generatedAt, issuers: {} }; time(clean.generatedAt);
  // Only company labels and document provenance survive into PUBLIC Git. No HTML,
  // complete submissions cache, raw sourceRow text, server paths or request URLs.
  for (const [cik, source] of Object.entries(doc.issuers)) {
    if (!/^\d{10}$/u.test(cik)) fail();
    const item = { cik, tickerAliases: source.tickerAliases, attemptStatus: source.attemptStatus, attemptedAt: source.attemptedAt ?? null };
    if (!Array.isArray(item.tickerAliases) || item.tickerAliases.some(t => !/^[A-Z][A-Z0-9.-]{0,11}$/u.test(t))) fail();
    text(item.attemptStatus, 60); time(item.attemptedAt, true);
    for (const k of ['lastSuccessAt', 'checkedAt']) if (k in source) { time(source[k], true); item[k] = source[k]; }
    if (source.filingMetadata != null) {
      const m = source.filingMetadata;
      if (!m || typeof m !== 'object' || Array.isArray(m) || m.cik !== cik ||
        !item.tickerAliases.includes(typeof m.issuer_id === 'string' && m.issuer_id.startsWith('US:') ? m.issuer_id.slice(3) : null) ||
        !/^\d{10}-\d{2}-\d{6}$/u.test(m.accession || '') || !['10-K', '20-F'].includes(m.form) ||
        typeof m.primary_document !== 'string' || !/^[A-Za-z0-9_.-]+\.(?:htm|html|txt)$/u.test(m.primary_document) ||
        typeof m.filed_date !== 'string' || typeof m.period_end !== 'string') fail();
      text(m.issuer_name, 180); text(m.primary_document, 180);
      day(m.filed_date); day(m.period_end); time(source.metadataCheckedAt); day(source.metadataCheckedAt.slice(0, 10));
      if (Number(source.metadataCheckedAt.slice(11, 13)) > 23) fail(); // Match Python datetime cache parsing.
      const url = `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${m.accession.replace(/-/gu, '')}/${m.primary_document}`;
      if (m.url !== url || !secUrl(m.url, cik, m.accession) || m.period_end > m.filed_date || m.filed_date > source.metadataCheckedAt.slice(0, 10)) fail();
      item.filingMetadata = { issuer_id: m.issuer_id, issuer_name: m.issuer_name, cik, accession: m.accession,
        filed_date: m.filed_date, period_end: m.period_end, form: m.form, primary_document: m.primary_document, url };
      if (Buffer.byteLength(JSON.stringify(item.filingMetadata)) > 4096) fail();
      // This timestamp validates metadata-cache reuse only. It never advances
      // checkedAt/lastSuccessAt or the filing/relationship's original dates.
      item.metadataCheckedAt = source.metadataCheckedAt;
    }
    if (source.reviewExhibit) {
      const e = source.reviewExhibit;
      try {
        if (e.schema !== 'sec-company-subsidiaries-v1' || e.cik !== cik || e.status !== 'needs-review' ||
          !/^\d{10}-\d{2}-\d{6}$/u.test(e.accession || '') || !SHA.test(e.documentSha256 || '') || !secUrl(e.url, cik, e.accession) ||
          typeof e.filedDate !== 'string' || typeof e.periodEnd !== 'string' || !item.attemptedAt) fail();
        day(e.filedDate); day(e.periodEnd); day(item.attemptedAt.slice(0, 10));
        if (e.periodEnd > e.filedDate || e.filedDate > item.attemptedAt.slice(0, 10)) fail();
        // Cache the unresolved original, not its rows, HTML or a success claim.
        item.reviewExhibit = { schema: e.schema, cik, accession: e.accession, filedDate: e.filedDate,
          periodEnd: e.periodEnd, url: e.url, documentSha256: e.documentSha256, status: 'needs-review' };
      } catch { /* An unsafe review snapshot is omitted, never copied raw. */ }
    }
    if ('sourceGap' in source) {
      if (source.sourceGap !== null && !/^[a-z0-9:-]{1,100}$/u.test(source.sourceGap)) fail();
      item.sourceGap = source.sourceGap;
    }
    if (source.exhibit) {
      const e = source.exhibit;
      if (e.schema !== 'sec-company-subsidiaries-v1' || e.cik !== cik || !secUrl(e.url, cik, e.accession) || !SHA.test(e.documentSha256 || '') || !Array.isArray(e.rows)) fail();
      day(e.filedDate); day(e.periodEnd); text(e.status, 40);
      const rows = [];
      for (const r of e.rows) {
        text(r.name, 180);
        if (r.ownershipPct !== null || r.directOwnership !== 'unspecified') fail();
        if (!corporateLabel(r.name)) continue;
        const jurisdiction = r.jurisdiction ?? '';
        if (typeof jurisdiction !== 'string') fail();
        if (jurisdiction) text(jurisdiction, 160);
        rows.push({ name: r.name, jurisdiction, ownershipPct: null, directOwnership: 'unspecified' });
      }
      item.exhibit = { schema: e.schema, cik, accession: e.accession, url: e.url, filedDate: e.filedDate,
        periodEnd: e.periodEnd, documentSha256: e.documentSha256, status: e.status, rows,
        sourceRowCount: Number.isSafeInteger(e.sourceRowCount) ? Math.max(e.sourceRowCount, e.rows.length) : e.rows.length,
        corporateRowCount: rows.length };
      if (!/^\d{10}-\d{2}-\d{6}$/u.test(e.accession || '')) fail();
    }
    clean.issuers[cik] = item;
  }
  if (doc.requestBudget) {
    const b = doc.requestBudget;
    integer(b.requests); day(b.day);
    if (b.requests > 200 || !Array.isArray(b.ciks) || b.ciks.length > 100 || new Set(b.ciks).size !== b.ciks.length || b.ciks.some(c => !/^\d{10}$/u.test(c))) fail();
    clean.requestBudget = { day: b.day, requests: b.requests, ciks: [...b.ciks] };
  }
  return clean;
}
module.exports = { loadArtifacts, validatePayload, sanitizeUsSources, publish, main, BASE, INDEX };
if (require.main === module) main().then(r => process.stdout.write(JSON.stringify(r) + '\n')).catch(() => {
  process.stderr.write('Company structure validation/publication failed; manifest publication not confirmed.\n'); process.exitCode = 1;
});
