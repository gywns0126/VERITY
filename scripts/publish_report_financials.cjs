// Correct explicitly reviewed annual financial cells in the existing public object only.
const fs = require('node:fs'), cp = require('node:child_process');
const assert = require('node:assert/strict');
const NAME = 'stock_report_public.json';
const URL = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/' + NAME;
const MANIFEST = 'data/metadata/report_fin_history_corrections_20261017.json';
const HISTORY = 'data/dart_kr_fin_history.json';

function repair(doc, manifest, history) {
    assert(['reviewed-kr-annual-net-corrections-v1', 'reviewed-kr-annual-financial-corrections-v2'].includes(manifest.schema));
    assert(Array.isArray(manifest.rows) && manifest.rows.length > 0);
    assert(Array.isArray(doc.stocks) && Array.isArray(history.rows));
    const next = structuredClone(doc), changed = [], seen = new Set();
    for (const correction of manifest.rows) {
        const metric = correction.metric ?? 'net';
        assert(['net', 'op'].includes(metric), 'unreviewed metric');
        assert(metric === 'net' || manifest.schema === 'reviewed-kr-annual-financial-corrections-v2', 'legacy net-only contract');
        const historyMetric = {net: 'net_income', op: 'operating_profit'}[metric];
        const key = correction.ticker + ':' + correction.year + (metric === 'net' ? '' : ':' + metric);
        assert(!seen.has(key), 'duplicate correction'); seen.add(key);
        assert(/^[0-9]{6}$/.test(correction.ticker));
        const reviewedMissingOp = manifest.schema === 'reviewed-kr-annual-financial-corrections-v2'
            && metric === 'op' && correction.before === null;
        assert(Number.isSafeInteger(correction.before) || reviewedMissingOp, 'unknown previous amount');
        assert(Number.isSafeInteger(correction.after));
        assert.equal(correction.currency, 'KRW');
        assert(['CFS', 'OFS'].includes(correction.fs_div));
        assert.equal(correction.start, correction.year + '-01-01');
        assert.equal(correction.end, correction.year + '-12-31');
        assert(correction.source_url.startsWith('https://dart.fss.or.kr/report/viewer.do?'));
        assert(correction.source_url.includes('rcpNo=' + correction.accession));
        assert(/^[a-f0-9]{64}$/.test(correction.source_sha256));
        const unit = correction.reported_unit;
        const multiplier = {원:1, 천원:1000, 백만원:1000000}[unit];
        assert(multiplier && multiplier === correction.unit_multiplier, 'unknown source unit');
        let raw = correction.raw_text.replaceAll(',', '');
        if (/^\(\d+\)$/.test(raw)) raw = '-' + raw.slice(1, -1);
        assert(/^-?\d+$/.test(raw) && Number(raw) * multiplier === correction.after, 'source amount/unit mismatch');
        const source = history.rows.filter(r => r.ticker === correction.ticker && r.fiscal_year === correction.year && r.period === 'annual');
        assert.equal(source.length, 1, 'history identity');
        assert.equal(source[0].name, correction.name);
        assert.equal(source[0].fundamentals[historyMetric], correction.after, 'history must already be corrected');
        const stocks = next.stocks.filter(s => s.ticker === correction.ticker);
        assert.equal(stocks.length, 1, 'public identity');
        assert.equal(stocks[0].name_ko || stocks[0].name, correction.name);
        const periods = stocks[0].fin_series.filter(p => p.year === correction.year);
        assert.equal(periods.length, 1, 'public annual identity');
        if (periods[0][metric] === correction.after) continue;
        assert.equal(periods[0][metric], correction.before, 'unreviewed public value; stop');
        periods[0][metric] = correction.after;
        changed.push(key);
    }
    return {next, changed};
}

function latestReviewedSources(exec = cp.execFileSync) {
    // Fetch immediately before the shared publish boundary. Read both inputs from one commit.
    exec('git', ['fetch', 'origin', 'main', '--depth=1', '--quiet']);
    const ref = exec('git', ['rev-parse', 'origin/main'], {encoding: 'utf8'}).trim();
    assert(/^[a-f0-9]{40}$/.test(ref), 'invalid main ref');
    const read = file => JSON.parse(exec('git', ['show', `${ref}:${file}`], {maxBuffer: 15000000}));
    return {manifest: read(MANIFEST), history: read(HISTORY), ref};
}

function repairStagedFile(file, loadSources = latestReviewedSources) {
    // Other callers may have no stock report. Do not fetch or change their staged files.
    if (!fs.existsSync(file)) return {skipped: true, changed: []};
    const {manifest, history, ref} = loadSources();
    const result = repair(JSON.parse(fs.readFileSync(file)), manifest, history);
    if (result.changed.length) fs.writeFileSync(file, JSON.stringify(result.next));
    return {ref, reviewed: manifest.rows.length, changed: result.changed};
}

async function main() {
    if (process.argv[2] === '--staged-public') {
        const result = repairStagedFile('_public_dist/' + NAME);
        console.log(JSON.stringify({target: '_public_dist/' + NAME, ...result}));
        return;
    }
    const manifest = JSON.parse(fs.readFileSync(MANIFEST));
    const history = JSON.parse(fs.readFileSync(HISTORY));
    if (process.argv[2] === '--github-file') {
        const path = '_report_published/' + NAME;
        const result = repair(JSON.parse(fs.readFileSync(path)), manifest, history);
        if (result.changed.length) fs.writeFileSync(path, JSON.stringify(result.next));
        console.log(JSON.stringify({target: 'VERITY-data/' + NAME, changed: result.changed}));
        return;
    }
    assert(process.env.BLOB_READ_WRITE_TOKEN, 'existing Blob secret required');
    const {head, put} = require('@vercel/blob');
    const metadata = await head(URL);
    const response = await fetch(URL + '?verify=' + Date.now(), {signal: AbortSignal.timeout(30000)});
    assert(response.ok, 'public read failed');
    const etag = metadata.etag;
    assert(etag && response.headers.get('etag')?.replace(/^W\//, '') === etag.replace(/^W\//, ''), 'storage/CDN mismatch');
    const previous = Buffer.from(await response.arrayBuffer());
    const {next, changed} = repair(JSON.parse(previous), manifest, history);
    cp.execFileSync('git', ['fetch', 'origin', 'main', '--quiet']);
    const latestHistory = JSON.parse(cp.execFileSync('git', ['show', 'origin/main:data/dart_kr_fin_history.json'], {maxBuffer: 15000000}));
    repair(next, manifest, latestHistory); // Stop if main no longer has the reviewed correction.
    const body = changed.length ? Buffer.from(JSON.stringify(next)) : previous;
    if (changed.length) {
        const result = await put(NAME, body, {access: 'public', addRandomSuffix: false,
            allowOverwrite: true, ifMatch: etag, contentType: 'application/json', cacheControlMaxAge: 3600});
        assert.equal(result.url, URL, 'unexpected public store');
    }
    for (let i = 0; i < 12; i++) {
        if (i) await new Promise(resolve => setTimeout(resolve, 10000));
        const check = await fetch(URL + '?verify=' + Date.now(), {signal: AbortSignal.timeout(30000)});
        if (check.ok && body.equals(Buffer.from(await check.arrayBuffer()))) {
            console.log(JSON.stringify({file: NAME, changed, readback: 'matched', reviewed: manifest.rows.length}));
            return;
        }
    }
    throw Error('public readback differs; no repeated write');
}
module.exports = {repair, repairStagedFile, latestReviewedSources};
if (require.main === module) main().catch(e => {
    console.error('report correction publish failed: ' + e.constructor.name);
    process.exitCode = 1;
});
