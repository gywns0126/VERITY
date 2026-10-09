#!/usr/bin/env node
// NPS-only release: no other Blob writes/deletes and no global manifest mutation.
const fs = require('node:fs');
const crypto = require('node:crypto');
const PUBLIC_URL = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/nps_holdings.json';
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const digest = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value)) ?? 'undefined').digest('hex');

function validate(payload) {
  const history = payload?.detail_history;
  const selection = history?.selection;
  if (!Array.isArray(payload?.holdings) || payload.count !== payload.holdings.length || !payload.count)
    throw new Error('Invalid basic holdings; refuse release');
  if (!Array.isArray(payload.full) || payload.full_n !== payload.full.length || !payload.full_n)
    throw new Error('Invalid annual holdings; refuse release');
  if (history?.schema_version !== 1 || history.scope !== 'annual_domestic_evaluation_top100'
      || selection?.limit !== 100
      || !/^\d{4}-12-31$/.test(selection.as_of || '') || !Array.isArray(history.stocks)
      || selection.annual_top100_n !== 100
      || history.stocks.length + selection.annual_top100_unmatched_n !== 100
      || history.stocks.length !== selection.target_n)
    throw new Error('Invalid Top100 selection; refuse release');
  if (payload.full.some(row => row.as_of !== selection.as_of))
    throw new Error('Annual period and selection mismatch');
  const names = new Set(), tickerCounts = new Map();
  const mappedTicker = value => {
    const text = String(value || '').trim().toUpperCase().split('.')[0];
    return /^[0-9A-Z]{6}$/.test(text) && text !== '000000' ? text : null;
  };
  for (const row of payload.full) {
    const name = String(row.name || '').replace(/\s/g, '').toLowerCase();
    if (!name || names.has(name) || typeof row.eval_amt_100m !== 'number'
        || !Number.isFinite(row.eval_amt_100m) || row.eval_amt_100m < 0)
      throw new Error('Invalid or ambiguous annual source row');
    names.add(name);
    const ticker = mappedTicker(row.ticker);
    if (ticker) tickerCounts.set(ticker, (tickerCounts.get(ticker) || 0) + 1);
  }
  // Same source-order rule as select_top100: rank raw securities before mapping.
  const ranked = [...payload.full].sort((a, b) => b.eval_amt_100m - a.eval_amt_100m
    || (a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0));
  const expected = ranked.slice(0, 100).map((row, index) => ({...row, rank:index + 1, ticker:mappedTicker(row.ticker)}))
    .filter(row => row.ticker && tickerCounts.get(row.ticker) === 1);
  if (expected.length !== history.stocks.length || history.stocks.some((stock, index) => {
    const row = expected[index];
    return stock.ticker !== row.ticker || stock.rank !== row.rank || stock.name !== row.name
      || stock.eval_amt_100m !== row.eval_amt_100m || stock.selection_as_of !== selection.as_of;
  })) throw new Error('History selection is not the official annual source Top100');
  const tickers = new Set();
  let filings = 0, withHistory = 0;
  for (const stock of history.stocks) {
    if (!/^[0-9A-Z]{6}$/.test(stock.ticker || '') || tickers.has(stock.ticker) || !Array.isArray(stock.events))
      throw new Error('Invalid or duplicate stock');
    tickers.add(stock.ticker);
    if (stock.events.length) withHistory++;
    const receipts = new Set();
    for (const event of stock.events) {
      if (!/^\d{14}$/.test(event.rcept_no || '') || receipts.has(event.rcept_no)
          || event.date_basis !== 'filing_date' || event.trade_date != null)
        throw new Error('Invalid filing attribution');
      receipts.add(event.rcept_no);
      filings++;
    }
  }
  if (!filings) throw new Error('No retained filing history; refuse release');
  return {as_of: selection.as_of, annual_rows: payload.full_n, selected: history.stocks.length,
    with_history: withHistory, filings, sha256: digest(payload)};
}

function preserveBaseline(next, previous) {
  if (!previous) return;
  const nextDate = next.detail_history.selection.as_of;
  const previousDate = previous.detail_history?.selection?.as_of
    || (previous.full || []).map(row => row.as_of || '').sort().at(-1);
  if (previousDate && previousDate > nextDate) throw new Error('Annual input would move backward');
  // Manual release must preserve unrelated panels exactly. Scheduled basic collectors may refresh them.
  for (const key of ['holdings', 'count', 'fund', 'asset_mix', 'full_us', 'full_us_n']) {
    if (digest(next[key]) !== digest(previous[key])) throw new Error(`Unrelated panel changed: ${key}`);
  }
  const stocks = new Map(next.detail_history.stocks.map(stock => [stock.ticker, stock]));
  for (const old of previous.detail_history?.stocks || []) {
    const current = stocks.get(old.ticker);
    if (!current) continue; // An annual cohort can legitimately change.
    const receipts = new Set(current.events.map(event => event.rcept_no));
    if ((old.events || []).some(event => !receipts.has(event.rcept_no)))
      throw new Error(`Retained filings lost: ${old.ticker}`);
  }
}

async function readPublic(fetcher) {
  const response = await fetcher(PUBLIC_URL, {signal: AbortSignal.timeout(20000)});
  if (!response.ok) throw new Error(`Public NPS response ${response.status}`);
  return response.json();
}

async function verify(payload, {fetcher = fetch, attempts = 5, wait = ms => new Promise(resolve => setTimeout(resolve, ms))} = {}) {
  const expected = digest(payload);
  for (let attempt = 0; attempt < attempts; attempt++) {
    const actual = await readPublic(fetcher);
    if (digest(actual) === expected) return validate(actual);
    if (attempt + 1 < attempts) await wait(15000);
  }
  throw new Error('Normal public URL does not match committed NPS data; delivery remains unverified');
}

async function publish(payload, {sdk, token, fetcher = fetch, verifyOptions = {}}) {
  validate(payload);
  if (!token) throw new Error('Missing existing Blob token; no writes performed');
  const metadata = await sdk.head(PUBLIC_URL, {token});
  if (metadata.url !== PUBLIC_URL || metadata.pathname !== 'nps_holdings.json')
    throw new Error('Unexpected Blob store or pathname; no writes performed');
  const before = await readPublic(fetcher);
  preserveBaseline(payload, before);
  const unchanged = digest(payload) === digest(before);
  if (!unchanged) {
    const result = await sdk.put('nps_holdings.json', JSON.stringify(payload), {
      token, access: 'public', addRandomSuffix: false, allowOverwrite: true,
      contentType: 'application/json', cacheControlMaxAge: 600,
    });
    if (result.url !== PUBLIC_URL) throw new Error('Unexpected published URL; delivery unverified');
  }
  return {...await verify(payload, {fetcher, ...verifyOptions}), unchanged};
}

if (require.main === module) {
  const payload = JSON.parse(fs.readFileSync('data/nps_holdings.json', 'utf8'));
  validate(payload);
  const work = process.argv.includes('--verify-only') ? verify(payload)
    : publish(payload, {sdk: require('@vercel/blob'), token: process.env.BLOB_READ_WRITE_TOKEN});
  work.then(result => console.log(JSON.stringify({nps_public_delivery: 'verified', ...result})))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
module.exports = {PUBLIC_URL, digest, validate, preserveBaseline, verify, publish};
