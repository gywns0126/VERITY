'use strict';

const { createHash } = require('node:crypto');

const SCHEMA = 'alphanest-company-structure-v1';
const MAX = 3000;
// Recorded web verification, not the time of an offline rebuild.
const OFFICIAL_VERIFIED_AT = '2026-10-21T08:14:06Z';
const TICKER = /^\d{6}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const COMPANY_FORM = /(?:\(주\)|㈜|주식회사|유한회사|합자회사|유한공사|股份有限公司|\b(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|LLC|LLP|PLC|GmbH|Sdn\s*Bhd)\b|\b(?:L\.P\.|B\.V\.|S\.A\.|S\.R\.L\.|W\.L\.L\.))/iu;
const VEHICLE = /(?:펀드|투자신탁|사모투자|증권자투자|신탁$|연금기금|투자조합|신기술조합|공제조합|\b(?:fund|trust)\b)/iu;
const ALIASES = new Map([
  ['sk하이닉스', 'KR:000660'], ['sk hynix', 'KR:000660'], ['sk hynix inc.', 'KR:000660'],
  ['sk스퀘어', 'KR:402340'], ['sk스퀘어(주)', 'KR:402340'], ['sk square', 'KR:402340'],
  // The 2026 reorganization distinguishes the legacy NAND company from Solidigm Inc.
  ['solidigm', 'FOREIGN:solidigm-inc'], ['solidigm inc.', 'FOREIGN:solidigm-inc'],
]);

function clean(value, max = 180) {
  return typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f<>\u202a-\u202e\u2066-\u2069]/gu, ' ').replace(/\s+/gu, ' ').trim().slice(0, max) : '';
}

function safeUrl(value) {
  if (typeof value !== 'string' || !/^https:\/\//iu.test(value) || value.length > 2048 || /[\u0000-\u0020\u007f\\]/u.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
}

function evidenceFromLinks(links) {
  if (!links || typeof links !== 'object' || Array.isArray(links)) return [];
  return Object.entries(links).flatMap(([key, value]) => {
    const url = primaryEvidenceUrl(value);
    return url ? [{ title: `Snapshot link: ${clean(key, 40)}`, url }] : [];
  }).slice(0, 10);
}

function primaryEvidenceUrl(value) {
  const safe = safeUrl(value);
  if (!safe) return null;
  const u = new URL(safe);
  // Profile/search/quote/share pages are discovery links, not ownership proof.
  if (/share|search|profile|quote/iu.test(u.pathname) || u.searchParams.get('command') === 'searchCompanyInfoDetail') return null;
  if (u.hostname === 'dart.fss.or.kr') return /^\d{14}$/u.test(u.searchParams.get('rcpNo') || '') ? safe : null;
  if (u.hostname === 'kind.krx.co.kr') return safe;
  // Company domains verified for the two explicit curations. Do not trust a raw
  // links.official label (the snapshot uses that label for stock quote pages).
  if (['www.skhynix.com', 'skhynix.com', 'www.solidigm.com', 'solidigm.com'].includes(u.hostname)) return safe;
  return null;
}

function date(value) {
  if (typeof value !== 'string' || !DATE.test(value)) return null;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? value : null;
}

function timestamp(value) {
  if (typeof value !== 'string' || !date(value.slice(0, 10)) || !Number.isFinite(Date.parse(value)) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u.test(value)) throw Error('Invalid observedAt');
  return value;
}

function pct(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null; }
function ticker(value) { return typeof value === 'string' && TICKER.test(value) ? value : null; }
function key(value) { return clean(value).toLocaleLowerCase('en-US'); }
function identityKey(value) { return clean(value, 10000).toLocaleLowerCase('en-US').replace(/\(주\)|㈜|주식회사/gu, '').replace(/\s+/gu, ''); }
function listedIdentity(row) {
  const symbol = ticker(row?.symbol) || ticker(row?.ticker) || /^(\d{6})\.K[QS]$/u.exec(row?.ticker_yf || '')?.[1];
  if (symbol) return { id: `KR:${symbol}`, ticker: symbol, market: 'KR', country: 'KR' };
  const us = row?.symbol || row?.ticker;
  if (['US', 'NASDAQ', 'NYSE', 'AMEX'].includes(row?.market) && typeof us === 'string' && /^[A-Z][A-Z0-9.-]{0,11}$/u.test(us)) return { id: `US:${us}`, ticker: us, market: 'US' };
  return null;
}
function companyLike(row) { return !VEHICLE.test(clean(row?.name)) && (!!listedIdentity(row) || ALIASES.has(key(row?.name)) || (!!clean(row?.name) && COMPANY_FORM.test(row.name))); }

function makeCatalog(input, options = {}) {
  if (!input || !input.structures || typeof input.structures !== 'object' || Array.isArray(input.structures)) throw Error('Invalid structures');
  const entries = Object.entries(input.structures);
  if (!entries.length || entries.length > MAX || input.count !== entries.length) throw Error('Invalid snapshot count');
  const snapshotAt = timestamp(input.updated_at);
  const officialObservedAt = timestamp(options.officialObservedAt || OFFICIAL_VERIFIED_AT);
  const companies = new Map();
  const relations = new Map();
  const skipped = { ambiguousShareholders: 0, unresolvedOrNonCompanyInvestments: 0, cooperation: 0, selfEdges: 0, duplicateEdges: 0 };
  const knownNames = new Map();
  const knownTickers = new Map();
  // Reconcile names against explicitly supplied local names and coded snapshot entities.
  function register(name, identity) {
    const k = identityKey(name);
    if (!k || !identity || /^\d{6}\.K[QS]$/u.test(name)) return;
    if (knownNames.has(k) && knownNames.get(k)?.id !== identity.id) knownNames.set(k, null);
    else if (!knownNames.has(k)) knownNames.set(k, identity);
    if (!knownTickers.has(identity.id)) knownTickers.set(identity.id, clean(name, 100));
  }
  for (const [code, name] of Object.entries(options.names || {})) if (TICKER.test(code)) register(name, { id: `KR:${code}`, ticker: code, market: 'KR', country: 'KR' });
  for (const [, row] of entries) for (const item of [row, row?.parent, ...(row?.subsidiaries || []), ...(row?.major_shareholders || [])]) if (item) register(item.name, listedIdentity(item));
  const eligible = row => !VEHICLE.test(clean(row?.name)) && (companyLike(row) || !!knownNames.get(identityKey(row?.name)));

  function entity(row, issuer = false) {
    const rawName = clean(row?.name, 100);
    const identity = listedIdentity(row);
    if (!rawName && !identity) return null;
    const alias = ALIASES.get(key(rawName));
    const resolved = identity || knownNames.get(identityKey(row?.name));
    const id = identity?.id || alias || resolved?.id || `FOREIGN:${createHash('sha256').update(identityKey(row?.name)).digest('hex').slice(0, 20)}`;
    const known = companies.get(id);
    const display = id === 'FOREIGN:solidigm-inc' ? 'Solidigm' : id === 'KR:000660' ? 'SK하이닉스' : id === 'KR:402340' ? 'SK스퀘어' : knownTickers.get(id) || (/^\d{6}\.K[QS]$/u.test(rawName) ? `기업 ${id.slice(3)}` : rawName);
    const code = /^KR:(\d{6})$/u.exec(id)?.[1];
    const next = { ...(resolved || {}), id, name: display || id,
      ...(code ? { ticker: code, market: 'KR', country: 'KR' } : {}),
      // Country is supplied by the FAQ, never inferred from a US listing.
      ...(id === 'FOREIGN:solidigm-inc' ? { country: 'US' } : {}) };
    if (!known) companies.set(id, next);
    else if (issuer || (!known.ticker && next.ticker)) companies.set(id, { ...known, ...next, name: issuer ? next.name : known.name });
    if (companies.size > MAX) throw Error('Company limit exceeded');
    return id;
  }

  function addRelation(from, to, type, source, observedAt, asOf = null, ownershipPct = null, evidence = []) {
    if (!from || !to) return;
    if (from === to) { skipped.selfEdges++; return; }
    const id = `${from}|${type}|${to}`;
    if (relations.has(id)) { skipped.duplicateEdges++; return; }
    relations.set(id, { id, from, to, type,
      label: type === 'major-shareholder' ? '주요주주' : type === 'investment' ? '투자 지분' : '자회사',
      asOf, observedAt, status: asOf ? 'source-dated' : 'undated-snapshot',
      ownershipPct: asOf ? pct(ownershipPct) : null, evidence: evidence.length ? evidence : evidenceFromLinks(source?.links) });
    if (relations.size > MAX) throw Error('Relation limit exceeded');
  }

  for (const [code, row] of entries) {
    if (!TICKER.test(code) || row?.ticker !== code || !Array.isArray(row.major_shareholders) || !Array.isArray(row.subsidiaries)) throw Error(`Invalid issuer ${code}`);
    const observedAt = timestamp(row.collected_at);
    const issuer = entity({ ...row, symbol: code }, true);
    const parent = row.parent;
    // Collector parent is the highest-ranked shareholder, not proof of control.
    if (parent && eligible(parent)) {
      const holder = entity(parent);
      addRelation(holder, issuer, 'major-shareholder', parent, observedAt, date(parent.as_of || parent.asOf || row.as_of || row.asOf), parent.ownership_pct);
    } else if (parent) skipped.ambiguousShareholders++;
    for (const investment of row.subsidiaries) {
      if (/\bTSMC\b|Taiwan Semiconductor Manufacturing/iu.test(clean(investment?.name)) || /협력|cooperation|partnership/iu.test(clean(investment?.relate))) { skipped.cooperation++; continue; }
      if (!eligible(investment)) { skipped.unresolvedOrNonCompanyInvestments++; continue; }
      const target = entity(investment);
      addRelation(issuer, target, 'investment', investment, observedAt, date(investment.as_of || investment.asOf || row.as_of || row.asOf), investment.ownership_pct);
    }
  }

  const hynix = entity({ name: 'SK하이닉스', symbol: '000660', ticker_yf: '000660.KS' });
  const square = entity({ name: 'SK스퀘어', symbol: '402340', ticker_yf: '402340.KS' });
  const solidigm = entity({ name: 'Solidigm' });
  function replacePair(from, to) { for (const [id, r] of relations) if (r.from === from && r.to === to) relations.delete(id); }
  replacePair(square, hynix);
  addRelation(square, hynix, 'major-shareholder', null, officialObservedAt, '2026-05-06', 20.5,
    [{ title: 'SK hynix ownership structure', url: 'https://www.skhynix.com/ir/UI-FR-IR04/', asOf: '2026-05-06' }]);
  replacePair(hynix, solidigm);
  addRelation(hynix, solidigm, 'subsidiary', null, officialObservedAt, null, null,
    [{ title: 'Solidigm company FAQ', url: 'https://www.solidigm.com/support/faqs.html' },
      { title: 'SK hynix filing: distinct legacy NAND company and Solidigm Inc.', url: 'https://kind.krx.co.kr/external/2026/03/03/001376/20260303001013/91765.htm', asOf: '2026-03-03' }]);
  relations.get(`${hynix}|subsidiary|${solidigm}`).status = 'official-undated';

  const sortedCompanies = [...companies.values()].sort((a, b) => a.id.localeCompare(b.id));
  const curatedIds = new Set([`${square}|major-shareholder|${hynix}`, `${hynix}|subsidiary|${solidigm}`]);
  const priority = r => {
    if (curatedIds.has(r.id)) return 0;
    const related = companies.get(r.type === 'major-shareholder' ? r.from : r.to);
    return related?.ticker && ['KR', 'US'].includes(related.market) ? 1 : 2;
  };
  // Renderer takes the first six outgoing branches: verified curations must win.
  const sortedRelations = [...relations.values()].sort((a, b) => priority(a) - priority(b) || a.id.localeCompare(b.id));
  return { schema: SCHEMA, observedAt: officialObservedAt, companies: sortedCompanies, relations: sortedRelations,
    coverage: { snapshotObservedAt: snapshotAt, sourceIssuers: entries.length, sourceMajorShareholderRows: entries.reduce((n, [, r]) => n + r.major_shareholders.length, 0),
      sourceInvestmentRows: entries.reduce((n, [, r]) => n + r.subsidiaries.length, 0), companies: sortedCompanies.length, relations: sortedRelations.length,
      skipped, limits: { companies: MAX, relations: MAX }, curatedRelations: 2,
      relationsWithoutOriginalUrls: sortedRelations.filter(r => r.evidence.length === 0).length,
      officialVerifiedAt: officialObservedAt,
      note: 'Parent means major shareholder; subsidiaries rows mean investment. Group labels create no edges. Undated percentages are suppressed. Other major_shareholders are counted but not expanded. Unresolved names and investment vehicles are excluded conservatively; this is not complete corporate coverage.',
      identityNote: 'FOREIGN is an opaque ID namespace, not a country assertion. Unknown country is omitted. Solidigm Inc. and SK hynix NAND Product Solutions Corp. are distinct legal entities in the 2026-03-03 filing; the legacy investment is not merged into the current Solidigm brand node.' } };
}

function selectedRootNeighbors(catalog, root) {
  const id = TICKER.test(root) ? `KR:${root}` : root;
  const relations = catalog.relations.filter(r => r.from === id || r.to === id);
  const ids = new Set([id, ...relations.flatMap(r => [r.from, r.to])]);
  return { companies: catalog.companies.filter(c => ids.has(c.id)), relations };
}

module.exports = { makeCatalog, selectedRootNeighbors, safeUrl, primaryEvidenceUrl, OFFICIAL_VERIFIED_AT };
