#!/usr/bin/env node
'use strict';

// Offline projection only. Raw DART rows never cross this public boundary.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { makeCatalog, primaryEvidenceUrl } = require('../../review/member-map/company-structure-data.cjs');

const KR = /^[A-Z0-9]{6}$/u, US = /^[A-Z][A-Z0-9.-]{0,11}$/u;
const MAX_ISSUERS = 25000, MAX_BYTES = 2 * 1024 * 1024;
const ENDPOINTS = ['hyslrSttus', 'otrCprInvstmntSttus'];
const SOURCE_SCHEMA = 'alphanest-company-structure-sources-v1';
const SEED_SCHEMA = 'alphaconsole-dart-structured-provenance-source-v1';
const clean = (v, max = 100) => typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f<>\u202a-\u202e\u2066-\u2069]/gu, ' ').replace(/\s+/gu, ' ').trim().slice(0, max) : '';
const norm = v => typeof v === 'string' ? v.replace(/\s+/gu, ' ').trim() : '';
const number = v => typeof v === 'number' ? (Number.isFinite(v) ? v : null) : typeof v === 'string' && /^-?[\d,]+(?:\.\d+)?%?$/u.test(v.trim()) ? Number(v.replace(/[,%]/gu, '')) : null;
function day(v) {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/u.test(v)) return null;
  const n = Date.parse(v + 'T00:00:00Z');
  return Number.isFinite(n) && new Date(n).toISOString().slice(0, 10) === v ? v : null;
}
function settlementDay(v) { return typeof v === 'string' ? day(v.trim().replace(/\./gu, '-').replace(/-$/u, '')) : null; }
function stamp(v) { return typeof v === 'string' && day(v.slice(0, 10)) && /T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u.test(v) && Number.isFinite(Date.parse(v)) ? v : null; }
const success = v => v === '000' || v === '013';
const aggregate = name => /^(?:계|합계|소계|총계|기타|합\s*계|total|subtotal|others?|-)$/iu.test(norm(name));
const cooperation = name => /\bTSMC\b|Taiwan Semiconductor Manufacturing/iu.test(name);
const jsonBytes = value => Buffer.from(JSON.stringify(value) + '\n', 'utf8');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function exclusion(row) {
  const type = String(row?.type || row?.kind || row?.asset_type || '').toUpperCase();
  const market = String(row?.market || '').toUpperCase();
  if (type.includes('ETF') || market === 'ETF' || /\bETF\b/u.test(row?.name || '')) return 'ETF';
  if (type.includes('ETN') || market === 'ETN') return 'ETN';
  if (type.includes('INDEX') || market === 'INDEX' || String(row?.ticker || '').startsWith('^')) return 'index';
  return null;
}

function targetSet(listed, universe, cikMap) {
  const targets = new Map(), excluded = { ETF: 0, ETN: 0, index: 0, other: 0, invalidTicker: 0 };
  const seenExcluded = new Set();
  function exclude(row, reason) { const id = `${row?.market}:${row?.ticker}`; if (!seenExcluded.has(id)) { seenExcluded.add(id); excluded[reason]++; } }
  function add(ticker, market, row) {
    const reason = exclusion(row);
    if (reason) return exclude({ ...row, ticker }, reason);
    if (!(market === 'KR' ? KR : US).test(ticker)) return exclude({ ...row, ticker, market }, 'invalidTicker');
    const id = `${market}:${ticker}`;
    const cik = cikMap[ticker];
    const cikValue = typeof cik === 'object' && cik ? cik.cik || cik.cik_str : cik;
    targets.set(id, { ticker, market, name: clean(row?.name || ticker),
      ...(market === 'US' && /^\d{1,10}$/u.test(String(cikValue || '')) && Number(cikValue) > 0 ? { cik: String(cikValue).padStart(10, '0') } : {}) });
  }
  for (const [ticker, row] of Object.entries(listed || {})) add(ticker, 'KR', typeof row === 'string' ? { name: row } : row);
  for (const row of Array.isArray(universe) ? universe : universe?.stocks || []) {
    const reason = exclusion(row);
    if (reason) { exclude(row, reason); continue; }
    if (row?.market === 'US') add(String(row.ticker || ''), 'US', row);
    else if (row?.market !== 'KR') exclude(row, 'other');
  }
  if (targets.size > MAX_ISSUERS) throw Error('Issuer limit exceeded (25000)');
  return { targets: new Map([...targets].sort(([a], [b]) => a.localeCompare(b))), excluded };
}

function sourceIndex(doc, schema) {
  if (!doc) return {};
  if (doc.schema !== schema || !doc.issuers || typeof doc.issuers !== 'object') throw Error(`Invalid source schema: ${schema}`);
  if (schema === SEED_SCHEMA) {
    if (!Array.isArray(doc.issuers)) throw Error('Seed issuers must be an array');
    return Object.fromEntries(doc.issuers.filter(i => i && KR.test(i.ticker)).map(i => [`KR:${i.ticker}`, i]));
  }
  if (Array.isArray(doc.issuers)) throw Error('Source issuers must be an object');
  return doc.issuers;
}

// A refresh error must not erase an older successful snapshot, or masquerade as
// its collection time. The selected latest attempt and row observation differ.
function endpointsFor(id, live, seed) {
  const a = live[id], b = seed[id], valid = i => i && i.ticker === id.slice(3) && (!i.market || i.market === 'KR') && /^\d{8}$/u.test(i.corp_code || '');
  const issuer = valid(a) ? a : valid(b) ? b : null;
  if (!issuer) return { issuer: null, endpoints: {} };
  const endpoints = {};
  for (const key of ENDPOINTS) {
    const candidates = [a, b].filter(i => valid(i) && i.corp_code === issuer.corp_code && i.endpoints?.[key]).map(i => {
      const e = i.endpoints[key];
      const collectedAt = stamp(i.collectedAt || i.collected_at);
      const attemptedAt = stamp(e.attemptedAt) || collectedAt;
      const attemptStatus = String(e.attemptStatus || e.status || 'unknown');
      const retainedPreviousPeriod = attemptStatus === '013' && e.status === '000' && Array.isArray(e.rows) && e.rows.length > 0 &&
        stamp(e.lastSuccessAt) && attemptedAt && Date.parse(e.lastSuccessAt) < Date.parse(attemptedAt);
      return { ...e, rows: attemptStatus === '013' && !retainedPreviousPeriod ? [] : Array.isArray(e.rows) ? e.rows : [], attemptedAt, attemptStatus, retainedPreviousPeriod: !!retainedPreviousPeriod,
        rowObservedAt: stamp(e.lastSuccessAt) || (success(attemptStatus) ? attemptedAt : null) };
    }).filter(e => e.attemptStatus !== 'not-attempted' && (e.attemptedAt || e.rows.length))
      .sort((x, y) => (Date.parse(y.attemptedAt || '') || 0) - (Date.parse(x.attemptedAt || '') || 0));
    if (!candidates.length) continue;
    const latest = candidates[0], previous = candidates.find(e => e.rows.length && e.rowObservedAt);
    endpoints[key] = { ...latest, rows: latest.rows.length ? latest.rows : success(latest.attemptStatus) ? [] : previous?.rows || [],
      rowObservedAt: latest.rows.length ? latest.rowObservedAt : success(latest.attemptStatus) ? latest.rowObservedAt : previous?.rowObservedAt || null };
  }
  return { issuer, endpoints };
}

function verifiedRow(row, endpoint, corp) {
  const p = row?.provenance, raw = row?.sourceRow?.fields || row?.sourceRow;
  if (!p || !raw || typeof raw !== 'object' || p.corp_code !== corp || raw.corp_code !== corp ||
      !/^\d{14}$/u.test(p.rcept_no || '') || p.rcept_no !== raw.rcept_no ||
      !settlementDay(p.stlm_dt) || p.stlm_dt !== raw.stlm_dt || p.endpoint !== endpoint) return null;
  const receiptDate = day(`${p.rcept_no.slice(0, 4)}-${p.rcept_no.slice(4, 6)}-${p.rcept_no.slice(6, 8)}`);
  if (!receiptDate || settlementDay(p.stlm_dt) > receiptDate) return null;
  if (!/^\d{4}$/u.test(p.bsns_year || '') || !['11011', '11012', '11013', '11014'].includes(p.reprt_code) ||
      (raw.bsns_year !== undefined && String(raw.bsns_year) !== p.bsns_year) ||
      (raw.reprt_code !== undefined && raw.reprt_code !== p.reprt_code)) return null;
  const holder = endpoint === 'hyslrSttus';
  const name = holder ? row.nm : row.inv_corp_name;
  const original = holder ? raw.nm : raw.inv_prm;
  const pct = number(holder ? row.stock_rate : row.ownership_pct);
  const rawPct = number(holder ? raw.trmend_posesn_stock_qota_rt : raw.trmend_blce_qota_rt);
  if (!norm(name) || norm(name) !== norm(original) || pct === null || rawPct === null || pct !== rawPct || pct < 0 || pct > 100) return null;
  if (!holder && raw.trmend_blce_qy !== undefined && number(row.end_balance_qty) !== number(raw.trmend_blce_qy)) return null;
  return { name: clean(name), ownership_pct: pct, asOf: settlementDay(p.stlm_dt),
    links: { original: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${p.rcept_no}` } };
}

function reusableCurations(legacy) {
  const pairs = new Set(['KR:402340|KR:000660', 'KR:000660|FOREIGN:solidigm-inc']);
  if (legacy?.schema !== 'alphanest-company-structure-v1') return [];
  return (legacy.relations || []).filter(r => pairs.has(`${r.from}|${r.to}`) && stamp(r.observedAt) &&
    ['source-dated', 'official-undated'].includes(r.status) && (r.asOf === null || day(r.asOf)) && r.evidence?.length && r.evidence.every(e => primaryEvidenceUrl(e.url))).map(r => ({ ...r, evidence: r.evidence.map(e => ({ title: clean(e.title), url: e.url, ...(day(e.asOf) ? { asOf: e.asOf } : {}) })) }));
}

function secUrl(value, cik) {
  if (typeof value !== 'string' || value.length > 2048) return null;
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && u.hostname === 'www.sec.gov' && !u.port && !u.username && !u.password && !u.search && !u.hash &&
      new RegExp(`^/Archives/edgar/data/${Number(cik)}/[0-9]{18}/[A-Za-z0-9_.-]+\\.(?:htm|html|txt)$`, 'u').test(u.pathname) ? value : null;
  } catch { return null; }
}

function usPayload(aliases, source, generatedAt) {
  if (!source || !stamp(source.attemptedAt)) return null;
  const e = source.exhibit, cik = aliases[0].cik;
  const observedAt = stamp(source.lastSuccessAt);
  const valid = e?.schema === 'sec-company-subsidiaries-v1' && e.cik === cik && Array.isArray(e.rows) && observedAt &&
    secUrl(e.url, cik) && /^\d{10}-\d{2}-\d{6}$/u.test(e.accession || '') && e.url.includes('/' + e.accession.replace(/-/gu, '') + '/') &&
    day(e.periodEnd) && day(e.filedDate) && e.periodEnd <= e.filedDate && e.filedDate <= observedAt.slice(0, 10) && /^[a-f0-9]{64}$/u.test(e.documentSha256 || '') &&
    ['ok', 'success', 'parsed', 'source-checked'].includes(e.status);
  const checked = !!valid && ['success', 'cached-same-accession'].includes(source.attemptStatus);
  const status = checked ? 'source-checked' : 'refresh-error';
  const companies = new Map(aliases.map(a => [`US:${a.ticker}`, { id: `US:${a.ticker}`, ticker: a.ticker, market: 'US', name: a.name }]));
  const relations = new Map(), canonicalId = `US:${aliases[0].ticker}`;
  let unsupported = 0;
  if (valid) for (const row of e.rows) {
    const name = clean(row?.name);
    // SEC reported lists can include direct AND indirect entities, never a direct-control tree.
    if (!name || row.ownershipPct !== null || row.directOwnership !== 'unspecified' || aggregate(name) || /\b(?:fund|trust|individual)\b|펀드|개인|투자조합/iu.test(name) ||
      !/(?:\b(?:inc|incorporated|corp|corporation|company|co|ltd|limited|llc|llp|plc|gmbh|sarl|pte|bv|sa)\b|주식회사|유한회사|有限公司)/iu.test(name) ||
      aliases.some(a => norm(a.name).toLowerCase() === norm(name).toLowerCase())) { unsupported++; continue; }
    if (row.jurisdiction != null && (typeof row.jurisdiction !== 'string' || row.jurisdiction.length > 160)) { unsupported++; continue; }
    const peer = `FOREIGN:${hash(Buffer.from(`${cik}|${norm(row.name).toLowerCase()}|${norm(row.jurisdiction).toLowerCase()}`)).slice(0, 20)}`;
    companies.set(peer, { id: peer, name }); // Jurisdiction text is not a country code.
    const id = `${canonicalId}|subsidiary|${peer}`, asOf = day(e.periodEnd);
    relations.set(id, { id, from: canonicalId, to: peer, type: 'subsidiary', label: '공시상 자회사·직간접 미구분',
      asOf, observedAt, status: asOf ? 'source-dated' : 'undated-snapshot', ownershipPct: null,
      evidence: [{ title: 'SEC reported subsidiary list (direct/indirect unspecified)', url: e.url, asOf: e.filedDate }] });
  }
  const payload = { schema: 'alphanest-company-structure-v1', observedAt: valid ? observedAt : source.attemptedAt,
    companies: [...companies.values()], relations: [...relations.values()], coverage: {
      status, sourceChecked: checked, attemptStatus: /^(?:success|cached-same-accession|error|source-gap|attempting|HTTP[1-5][0-9]{2})$/u.test(source.attemptStatus) ? source.attemptStatus : 'error', attemptedAt: source.attemptedAt,
      lastSuccessAt: observedAt, asOfNotCollectedAt: true, canonicalId, securityIds: aliases.map(a => `US:${a.ticker}`),
      cik, filedDate: valid ? e.filedDate : null, periodEnd: valid ? day(e.periodEnd) : null,
      documentSha256: valid ? e.documentSha256 : null, rawRowsExamined: valid ? e.rows.length : 0,
      rawVerifiedRows: relations.size, storedRows: 0, unsupportedRows: unsupported,
      displayedRelations: relations.size, limits: { nodes: 3000, relations: 3000, bytes: MAX_BYTES },
      note: 'SEC exhibit lists direct or indirect subsidiaries; no direct ownership or currentness is inferred. Filing date and period end are distinct. Collection is deduped by CIK; security roots remain distinct.' } };
  if (companies.size > 3000 || relations.size > 3000) throw Error('Payload node/relation limit exceeded');
  return payload;
}

function buildArtifacts({ listed = {}, universe = {}, cikMap = {}, sources, usSources, seed, groups = {}, ownership = {}, legacy, strictSources = false, generatedAt = new Date().toISOString() }) {
  if (!stamp(generatedAt)) throw Error('Invalid generatedAt');
  const { targets, excluded } = targetSet(listed, universe, cikMap);
  const live = sourceIndex(sources, SOURCE_SCHEMA), seeded = sourceIndex(seed, SEED_SCHEMA);
  const us = sourceIndex(usSources, 'alphanest-company-structure-us-sources-v1');
  const cikGroups = new Map();
  for (const target of targets.values()) if (target.market === 'US' && target.cik) {
    if (!cikGroups.has(target.cik)) cikGroups.set(target.cik, []);
    cikGroups.get(target.cik).push(target);
  }
  const names = Object.fromEntries([...targets.values()].filter(i => i.market === 'KR').map(i => [i.ticker, i.name]));
  const identities = new Map([...targets.values()].map(i => [norm(i.name), i]));
  if (targets.has('US:TSM')) identities.set('TSMC', targets.get('US:TSM'));
  const curations = reusableCurations(legacy), legacyCompanies = new Map((legacy?.companies || []).map(c => [c.id, c]));
  const manifest = { schema: 'alphanest-company-structure-index-v1', generatedAt, coverage: {
    KR: { total: 0, checked: 0, pending: 0, legacyOnly: 0, failed: 0, payloads: 0 },
    US: { total: 0, checked: 0, pending: 0, withCik: 0, withoutCik: 0, payloads: 0, uniqueCiks: cikGroups.size, checkedCiks: 0, pendingCiks: cikGroups.size }, excluded,
    limits: { issuers: MAX_ISSUERS, nodes: 3000, relations: 3000, payloadBytes: MAX_BYTES, manifestBytes: MAX_BYTES },
    rawRowsExamined: 0, rawMatchedRows: 0, rawVerifiedRows: 0, storedRows: 0, unsupportedRows: 0,
  }, issuers: {} };
  const payloads = new Map();
  const usCache = new Map();
  for (const [id, target] of targets) {
    const marketCoverage = manifest.coverage[target.market]; marketCoverage.total++;
    const meta = { ticker: target.ticker, market: target.market, name: target.name, status: 'not-attempted' };
    manifest.issuers[id] = meta;
    if (target.market === 'US') {
      marketCoverage[target.cik ? 'withCik' : 'withoutCik']++;
      if (target.cik && !usCache.has(target.cik)) {
        const s = us[target.cik] || us[String(Number(target.cik))];
        const p = usPayload([target], s, generatedAt);
        if (strictSources && ['success', 'cached-same-accession'].includes(s?.attemptStatus) && !p?.coverage.sourceChecked) throw Error('SEC source binding failed');
        usCache.set(target.cik, s || null);
        if (p?.coverage.sourceChecked) { marketCoverage.checkedCiks++; marketCoverage.pendingCiks--; }
      }
      const p = target.cik ? usPayload([target], usCache.get(target.cik), generatedAt) : null;
      marketCoverage[p?.coverage.sourceChecked ? 'checked' : 'pending']++;
      if (p) {
        const bytes = jsonBytes(p);
        if (bytes.length > MAX_BYTES) throw Error('Payload byte limit exceeded');
        meta.status = p.coverage.status; meta.sha256 = hash(bytes); meta.bytes = bytes.length;
        payloads.set(meta.sha256, bytes); marketCoverage.payloads++;
      }
      continue; // A CIK alone never means SEC was checked.
    }
    const { issuer, endpoints } = endpointsFor(id, live, seeded);
    const old = groups.structures?.[target.ticker];
    const oldHolders = ownership.holders?.[target.ticker]?.top || [];
    const observedAt = stamp(old?.collected_at) || stamp(legacy?.coverage?.snapshotObservedAt) || stamp(legacy?.observedAt) ||
      stamp(ownership._meta?.generated_at) || stamp(issuer?.collectedAt || issuer?.collected_at) || '1970-01-01T00:00:00Z';
    const sourceObservedAt = Object.values(endpoints).map(e => e.rowObservedAt).filter(stamp).sort((a, b) => Date.parse(b) - Date.parse(a))[0];
    const rows = { hyslrSttus: [], otrCprInvstmntSttus: [] };
    let rawVerified = 0, stored = 0, unsupported = 0;
    for (const endpoint of ENDPOINTS) {
      const e = endpoints[endpoint];
      if (!e) continue;
      for (const row of e.rows) {
        const holder = endpoint === 'hyslrSttus', name = holder ? row?.nm : row?.inv_corp_name;
        const amount = number(holder ? row?.stock_rate : row?.ownership_pct);
        const original = row?.sourceRow?.fields || row?.sourceRow;
        const rawEnded = !holder && original?.trmend_blce_qy !== undefined && number(original.trmend_blce_qy) === 0;
        if (!norm(name) || aggregate(name) || amount === 0 || rawEnded) { unsupported++; continue; }
        let proof = verifiedRow(row, endpoint, issuer.corp_code);
        if (proof && e.rowObservedAt && proof.asOf > e.rowObservedAt.slice(0, 10)) {
          if (strictSources) throw Error('DART source date ordering failed');
          proof = null;
        }
        if (strictSources && live[id]?.endpoints?.[endpoint] && e.attemptStatus === '000' && Date.parse(e.rowObservedAt) === Date.parse(e.attemptedAt) && !proof) throw Error('DART source row binding failed');
        // No signed/raw/private source fields are copied into the public model.
        const identity = identities.get(norm(name));
        const normalized = proof && e.rowObservedAt ? { ...proof, observedAt: e.rowObservedAt, ...(identity ? { symbol: identity.ticker, market: identity.market } : {}) } : { name: clean(name), ownership_pct: null };
        if (!proof && cooperation(name)) { unsupported++; continue; }
        if (proof && e.rowObservedAt) rawVerified++; else stored++;
        rows[endpoint].push(normalized);
      }
    }
    // Only use a legacy axis when there is no response for that axis. A real 013
    // supersedes old records, and is not repopulated from an undated artifact.
    if (!endpoints.hyslrSttus) for (const row of old?.major_shareholders || oldHolders) {
      if (!aggregate(row.name || row.nm) && number(row.ownership_pct ?? row.pct) !== 0) { rows.hyslrSttus.push({ name: clean(row.name || row.nm) }); stored++; }
      else unsupported++;
    }
    if (!endpoints.otrCprInvstmntSttus) for (const row of old?.subsidiaries || []) {
      if (!aggregate(row.name) && !cooperation(row.name) && number(row.ownership_pct) !== 0) { rows.otrCprInvstmntSttus.push({ name: clean(row.name), symbol: row.symbol }); stored++; }
      else unsupported++;
    }
    const model = makeCatalog({ updated_at: observedAt, count: 1, structures: { [target.ticker]: {
      ticker: target.ticker, name: target.name, collected_at: observedAt,
      major_shareholders: rows.hyslrSttus, subsidiaries: rows.otrCprInvstmntSttus,
    } } }, { names, allowAlphanumericKR: true, includeCurations: false, allCorporateShareholders: true, sourceVerified: true, officialObservedAt: generatedAt });
    const relations = new Map(model.relations.map(r => [`${r.from}|${r.to}`, r]));
    const companies = new Map(model.companies.map(c => [c.id, c]));
    let curatedCount = 0;
    const curatedIds = new Set();
    for (const r of curations.filter(r => r.from === id || r.to === id)) {
      const previous = relations.get(`${r.from}|${r.to}`);
      // Settlement dates compare only with settlement dates, never build time.
      if (previous?.asOf && r.asOf && previous.asOf > r.asOf) continue;
      if (previous?.asOf && !r.asOf && previous.observedAt > r.observedAt) continue;
      for (const peer of [r.from, r.to]) { const c = legacyCompanies.get(peer); if (c) companies.set(peer, { id: c.id, name: clean(c.name), ...(c.ticker ? { ticker: c.ticker, market: c.market } : {}), ...(c.country ? { country: c.country } : {}) }); }
      if (!companies.has(r.from) || !companies.has(r.to)) continue;
      relations.set(`${r.from}|${r.to}`, r); curatedCount++; curatedIds.add(r.id);
    }
    const endpointStates = Object.fromEntries(ENDPOINTS.map(k => { const e = endpoints[k]; return [k, e ? { status: String(e.status || 'unknown'), attemptStatus: e.attemptStatus, attemptedAt: e.attemptedAt, lastSuccessAt: e.rowObservedAt } : { attemptStatus: 'not-attempted' }]; }));
    const checked = ENDPOINTS.every(k => endpoints[k] && success(endpoints[k].attemptStatus) && !endpoints[k].retainedPreviousPeriod && !!endpoints[k].attemptedAt);
    const failed = ENDPOINTS.some(k => endpoints[k] && !success(endpoints[k].attemptStatus));
    const attempted = ENDPOINTS.some(k => !!endpoints[k]);
    const legacyPresent = !!old || oldHolders.length > 0;
    meta.status = failed ? 'refresh-error' : checked ? 'source-checked' : attempted ? 'partial' : legacyPresent ? 'legacy-only' : curatedCount ? 'curated-only' : 'not-attempted';
    marketCoverage[checked ? 'checked' : 'pending']++;
    if (failed) marketCoverage.failed++;
    if (meta.status === 'legacy-only') marketCoverage.legacyOnly++;
    const rawRowsExamined = rawVerified + stored + unsupported;
    const admittedVerified = model.relations.filter(r => r.asOf && r.evidence.length).length;
    const admittedStored = model.relations.length - admittedVerified;
    const rejected = rawRowsExamined - admittedVerified - admittedStored;
    manifest.coverage.rawRowsExamined += rawRowsExamined;
    manifest.coverage.rawMatchedRows += rawVerified;
    manifest.coverage.rawVerifiedRows += admittedVerified;
    manifest.coverage.storedRows += admittedStored;
    manifest.coverage.unsupportedRows += rejected;
    if (!relations.size && !attempted) continue;
    const priority = r => curatedIds.has(r.id) ? 0 : companies.get(r.type === 'major-shareholder' ? r.from : r.to)?.ticker ? 1 : 2;
    const sorted = [...relations.values()].sort((a, b) => priority(a) - priority(b) ||
      (a.evidence.length ? 0 : 1) - (b.evidence.length ? 0 : 1) || a.id.localeCompare(b.id));
    const used = new Set([id, ...sorted.flatMap(r => [r.from, r.to])]);
    const payload = { schema: 'alphanest-company-structure-v1', observedAt: sourceObservedAt || observedAt, companies: [...companies.values()].filter(c => used.has(c.id)).sort((a, b) => a.id.localeCompare(b.id)), relations: sorted,
      coverage: { status: meta.status, sourceChecked: checked, attemptStatus: failed ? 'error' : checked ? 'success' : attempted ? 'partial' : 'not-attempted', endpoints: endpointStates,
        asOfNotCollectedAt: true, asOfMeaning: 'stlm_dt is the settlement date, not the filing receipt date', rawRowsExamined, rawMatchedRows: rawVerified,
        rawVerifiedRows: admittedVerified, storedRows: admittedStored, unsupportedRows: rejected,
        curatedRelations: curatedCount, displayedRelations: sorted.length, limits: { nodes: 3000, relations: 3000, bytes: MAX_BYTES },
        note: 'Unsupported rows include personal/fund/aggregate/zero/unresolved/duplicate entries. Stored names do not prove current ownership or subsidiary status. FOREIGN IDs do not imply country. Collection time is not an as-of date. Quantity is checked only when the original quantity is preserved; parsed zero alone is not evidence of an ended investment.' } };
    if (payload.companies.length > 3000 || sorted.length > 3000) throw Error('Payload node/relation limit exceeded');
    const bytes = jsonBytes(payload);
    if (bytes.length > MAX_BYTES) throw Error(`Payload byte limit exceeded: ${id}`);
    const sha256 = hash(bytes); payloads.set(sha256, bytes);
    meta.sha256 = sha256; meta.bytes = bytes.length; marketCoverage.payloads++;
  }
  const manifestBytes = jsonBytes(manifest);
  if (manifestBytes.length > MAX_BYTES) throw Error('Manifest byte limit exceeded (2 MiB)');
  return { manifest, manifestBytes, payloads };
}

function readJson(file, fallback) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { if (e.code === 'ENOENT' && fallback !== undefined) return fallback; throw e; } }
function writeArtifacts(result, outputDir) {
  if (fs.existsSync(outputDir)) throw Error('Use a new output directory; existing artifacts are immutable');
  fs.mkdirSync(path.join(outputDir, 'company-structure'), { recursive: true });
  for (const [sha, bytes] of result.payloads) fs.writeFileSync(path.join(outputDir, 'company-structure', sha + '.json'), bytes, { flag: 'wx' });
  fs.writeFileSync(path.join(outputDir, 'member_map_company_structure_index.json'), result.manifestBytes, { flag: 'wx' });
}

function main(argv = process.argv.slice(2)) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--source-dir', '--sources', '--us-sources', '--output-dir', '--seed-structured', '--generated-at'].includes(argv[i]) || !argv[i + 1] || argv[i + 1].startsWith('--')) throw Error('Invalid build arguments');
    args[argv[i]] = argv[i + 1];
  }
  for (const key of ['--source-dir', '--sources', '--output-dir']) if (!args[key]) throw Error(`Required ${key}`);
  const sourceDir = fs.realpathSync(args['--source-dir']);
  const outputDir = path.resolve(args['--output-dir']);
  const inputs = [sourceDir, path.dirname(fs.realpathSync(args['--sources'])), ...['--seed-structured', '--us-sources'].filter(k => args[k]).map(k => path.dirname(fs.realpathSync(args[k])))];
  if (inputs.some(p => outputDir === p || outputDir.startsWith(p + path.sep))) throw Error('Output must be outside source directories');
  if (fs.existsSync(outputDir)) throw Error('Use a new output directory; existing artifacts are immutable');
  const legacyPath = path.resolve(__dirname, '../../vercel-api/public/member-map-review/company-structure.json');
  const result = buildArtifacts({
    listed: readJson(path.join(sourceDir, 'kr_listed.json'), {}), universe: readJson(path.join(sourceDir, 'universe_search.json'), {}),
    cikMap: readJson(path.join(sourceDir, 'sec_ticker_cik_map.json'), {}), groups: readJson(path.join(sourceDir, 'group_structure.json'), {}),
    ownership: readJson(path.join(sourceDir, 'kr_ownership.json'), {}), sources: readJson(args['--sources']),
    usSources: args['--us-sources'] ? readJson(args['--us-sources']) : undefined,
    seed: args['--seed-structured'] ? readJson(args['--seed-structured']) : undefined, legacy: readJson(legacyPath, {}),
    strictSources: true, ...(args['--generated-at'] ? { generatedAt: args['--generated-at'] } : {}),
  });
  writeArtifacts(result, outputDir);
  process.stdout.write(JSON.stringify({ outputDir, issuers: Object.keys(result.manifest.issuers).length, payloads: result.payloads.size, manifestBytes: result.manifestBytes.length, coverage: result.manifest.coverage }) + '\n');
  return result;
}

module.exports = { buildArtifacts, writeArtifacts, main, verifiedRow, secUrl, MAX_BYTES, MAX_ISSUERS };
if (require.main === module) { try { main(); } catch (e) { process.stderr.write(e.message + '\n'); process.exitCode = 1; } }
