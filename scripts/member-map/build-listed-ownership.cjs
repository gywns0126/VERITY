'use strict';

const fs = require('node:fs');
const { verifiedRow } = require('./build-live-company-structure.cjs');

const SCHEMA = 'member-map-listed-ownership-v1';
const MAX_BYTES = 1024 * 1024;
const endpoints = ['hyslrSttus', 'otrCprInvstmntSttus'];
const ticker = /^[0-9]{6}$/u;
const corpCode = /^[0-9]{8}$/u;
const amount = /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/u;
const unsafe = /[\p{Cc}\p{Cf}<>]/u;
const vehicle = /펀드|투자조합|신기술조합|투자신탁|사모투자|연금기금|공제조합|투자회사|스팩|기업인수목적|리츠$|\b(?:fund|trust|ETF|ETN|SPAC|REIT)\b/iu;
const aggregate = /^(?:합계|소계|총계|계|기타|개인|친족|본인|자사주|자기주식|합산|total|subtotal|others?|-)$/iu;
const personalRole = /개인|친족|배우자|임원|친인척|자기주식|자사주|발행회사\s*본인/u;
const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const record = x => x !== null && typeof x === 'object' && !Array.isArray(x);

function legalName(value) {
  if (typeof value !== 'string' || value.length > 120 || unsafe.test(value)) return '';
  const normalized = value.normalize('NFKC').toLowerCase();
  if (vehicle.test(normalized)) return '';
  const name = normalized.replace(/\s+/gu, '')
    .replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/gu, '');
  return aggregate.test(name) || vehicle.test(name) ? '' : name;
}

function indexUniverse(universe) {
  const stocks = Array.isArray(universe) ? universe : universe?.stocks;
  if (!Array.isArray(stocks) || !stocks.length) throw Error('Missing public universe');
  const byName = new Map(), byTicker = new Map();
  for (const company of stocks) {
    if (!company || !['KR', 'KONEX'].includes(company.market)) continue;
    const key = legalName(company.name);
    if (!key) continue;
    // Ineligible listings still make a homonymous legal name ambiguous.
    const eligible = company.market === 'KR' && typeof company.ticker === 'string' && ticker.test(company.ticker)
      && !/ETF|ETN|FUND|TRUST|INDEX|REIT|SPAC/iu.test([company.type, company.kind, company.asset_type].join(' '));
    byName.set(key, byName.has(key) || !eligible ? null : company);
    if (eligible) byTicker.set(company.ticker, byTicker.has(company.ticker) ? null : company);
  }
  return { byName, byTicker };
}

function explicitIssuerMatches(fields, issuer) {
  for (const k of ['ticker', 'stock_code', 'issuer_ticker']) {
    if (Object.hasOwn(fields, k) && fields[k] !== issuer.ticker) return false;
  }
  for (const k of ['corp_name', 'issuer_name']) {
    if (Object.hasOwn(fields, k) && legalName(fields[k]) !== legalName(issuer.name)) return false;
  }
  return true;
}

function project(row, issuer, endpoint, block, identities) {
  const source = row?.sourceRow, raw = source?.fields, p = row?.provenance;
  if (!record(raw) || !record(p) || !Number.isSafeInteger(source.index) || source.index < 0 ||
      !explicitIssuerMatches(raw, issuer) || !explicitIssuerMatches(p, issuer) || !explicitIssuerMatches(row, issuer) ||
      (Object.hasOwn(raw, 'endpoint') && raw.endpoint !== endpoint) ||
      !block.reportPeriod || block.reportPeriod.year !== p.bsns_year || block.reportPeriod.reportCode !== p.reprt_code ||
      typeof p.rcept_no !== 'string' || !/^\d{14}$/u.test(p.rcept_no)) return null;
  const holder = endpoint === 'hyslrSttus';
  const name = raw[holder ? 'nm' : 'inv_prm'];
  const party = identities.byName.get(legalName(name));
  if (!party || identities.byTicker.get(party.ticker) !== party || party.ticker === issuer.ticker ||
      personalRole.test([row.relate, raw.relate].join(' '))) return null;
  const pct = raw[holder ? 'trmend_posesn_stock_qota_rt' : 'trmend_blce_qota_rt'];
  const qty = raw[holder ? 'trmend_posesn_stock_co' : 'trmend_blce_qy'];
  for (const field of ['party_ticker', 'counterparty_ticker']) {
    if ((Object.hasOwn(raw, field) && raw[field] !== party.ticker) ||
        (Object.hasOwn(row, field) && row[field] !== party.ticker)) return null;
  }
  if (typeof pct !== 'string' || !amount.test(pct.trim()) ||
      (qty != null && qty !== '-' && qty !== '' && (!amount.test(String(qty).trim()) || Number(String(qty).replaceAll(',', '')) <= 0))) return null;
  if (holder && row.stock_cnt != null && qty != null &&
      String(row.stock_cnt).trim().replaceAll(',', '') !== String(qty).trim().replaceAll(',', '')) return null;
  const proof = verifiedRow(row, endpoint, issuer.corp_code);
  if (!proof || proof.ownership_pct <= 0 || proof.asOf.slice(0, 4) !== p.bsns_year ||
      (Array.isArray(block.sourceActualSettlementDates) && !block.sourceActualSettlementDates.includes(proof.asOf))) return null;
  return { issuer: 'KR:' + issuer.ticker, party: 'KR:' + party.ticker, issuer_name: issuer.name,
    party_name: name.trim(), endpoint, receipt: p.rcept_no, settled_on: proof.asOf, pct: proof.ownership_pct, row_index: source.index };
}

function buildListedOwnership(sources, universe) {
  if (sources?.schema !== 'alphanest-company-structure-sources-v1' || !record(sources.issuers)) throw Error('Invalid company source document');
  const identities = indexUniverse(universe);
  const corpOwners = new Map();
  for (const [id, issuer] of Object.entries(sources.issuers)) {
    if (typeof issuer?.corp_code === 'string' && corpCode.test(issuer.corp_code)) {
      corpOwners.set(issuer.corp_code, corpOwners.has(issuer.corp_code) ? null : id);
    }
  }
  const byRow = new Map(), receiptOwners = new Map();
  for (const [id, issuer] of Object.entries(sources.issuers)) {
    const identity = identities.byName.get(legalName(issuer?.name));
    if (!identity || identities.byTicker.get(identity.ticker) !== identity || id !== 'KR:' + identity.ticker ||
        issuer.ticker !== identity.ticker || issuer.market !== 'KR' || issuer.mappingStatus !== 'mapped' ||
        corpOwners.get(issuer.corp_code) !== id) continue;
    for (const endpoint of endpoints) {
      const block = issuer.endpoints?.[endpoint];
      if (block?.status !== '000' || !Array.isArray(block.rows) ||
          (Object.hasOwn(block, 'corp_code') && block.corp_code !== issuer.corp_code) ||
          (Object.hasOwn(block, 'endpoint') && block.endpoint !== endpoint)) continue;
      for (const raw of block.rows) {
        const edge = project(raw, issuer, endpoint, block, identities);
        if (!edge) continue;
        const { receipt, row_index } = edge;
        if (!receiptOwners.has(receipt)) receiptOwners.set(receipt, id);
        else if (receiptOwners.get(receipt) !== id) receiptOwners.set(receipt, null);
        const key = [receipt, endpoint, row_index].join('/');
        if (!byRow.has(key)) byRow.set(key, edge);
        else if (JSON.stringify(byRow.get(key)) !== JSON.stringify(edge)) byRow.set(key, null);
      }
    }
  }
  const rows = [...byRow.values()].filter(row => row && receiptOwners.get(row.receipt) === row.issuer);
  rows.sort((a,b) => cmp(a.issuer,b.issuer) || cmp(a.party,b.party) || cmp(a.endpoint,b.endpoint) ||
    cmp(a.receipt,b.receipt) || a.row_index - b.row_index);
  const result = { schema: SCHEMA, rows };
  if (Buffer.byteLength(JSON.stringify(result) + '\n') > MAX_BYTES) throw Error('Listed ownership exceeds 1 MiB');
  return result;
}

if (require.main === module) {
  const [sourceFile, universeFile, outputFile] = process.argv.slice(2);
  if (!sourceFile || !universeFile || !outputFile) throw Error('Expected company-source, public-universe and candidate output paths');
  const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
  const result = buildListedOwnership(read(sourceFile), read(universeFile));
  if (!result.rows.length) throw Error('No publishable ownership rows; hold candidate');
  fs.writeFileSync(outputFile, JSON.stringify(result) + '\n', { flag: 'wx' });
  console.log('Staged ' + result.rows.length + ' dated listed ownership rows');
}

module.exports = { buildListedOwnership, MAX_BYTES };
