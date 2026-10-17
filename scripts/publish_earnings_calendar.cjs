// Selectively publish reviewed official earnings dates; never replace financial cells.
const fs = require('node:fs'), cp = require('node:child_process');
const assert = require('node:assert/strict');
const NAME = 'stock_report_public.json';
const URL = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/' + NAME;
const SOURCE = 'data/kr_earnings_calendar.json';
const FIELDS = new Set(['event', 'kind', 'date', 'time_kst', 'is_estimated', 'source',
    'url', 'receipt', 'filed', 'observed_at', 'basis']);

function validateCalendar(rows) {
    assert(Array.isArray(rows), 'calendar must be an array');
    for (const row of rows) {
        assert(row && typeof row === 'object' && !Array.isArray(row));
        assert(Object.keys(row).every(k => FIELDS.has(k)), 'non-public calendar field');
        assert.equal(row.source, 'DART issuer IR notice');
        assert.equal(row.is_estimated, false);
        assert.equal(row.kind, '실적');
        assert(/^\d{4}-\d{2}-\d{2}$/.test(row.date));
        assert(/^\d{14}$/.test(row.receipt));
        const url = new globalThis.URL(row.url);
        assert.equal(url.protocol, 'https:');
        assert.equal(url.hostname, 'dart.fss.or.kr');
        assert.equal(url.username + url.password, '');
        assert(['/dsaf001/main.do', '/report/viewer.do'].includes(url.pathname));
        assert.equal(url.searchParams.get('rcpNo'), row.receipt);
        assert(Number.isFinite(Date.parse(row.observed_at)), 'missing source observation');
        for (const value of Object.values(row)) {
            assert(typeof value === 'string' || typeof value === 'boolean', 'nested/private calendar data');
            if (typeof value === 'string') assert(value.length <= 4000, 'oversized public field');
        }
    }
}

function makePatch(doc, today, exec = cp.execFileSync) {
    assert(doc && Array.isArray(doc.records), 'official calendar source missing');
    const checkedAt = doc._meta?.checked_at;
    assert(Number.isFinite(Date.parse(checkedAt)), 'source observation missing');
    assert(/^\d{4}-\d{2}-\d{2}$/.test(today));
    // Reuse the actual collector selection contract, including corrections, cancellation and age.
    const program = [
        'import sys,json',
        'from datetime import date',
        'from api.collectors.kr_earnings_calendar import select_calendar',
        'doc=json.load(sys.stdin)',
        'tickers=sorted(set(r["ticker"] for r in doc["records"] if isinstance(r,dict) and r.get("ticker")))',
        'print(json.dumps([{ "ticker":t,"calendar":select_calendar(doc,t,date.fromisoformat(sys.argv[1]))} for t in tickers],ensure_ascii=False))',
    ].join('\n');
    const selected = JSON.parse(exec('python3', ['-c', program, today], {
        input: JSON.stringify(doc), encoding: 'utf8', maxBuffer: 15000000,
    }));
    assert(Array.isArray(selected));
    const rows = [], seen = new Set();
    for (const row of selected) {
        assert(/^\d{6}$/.test(row.ticker), 'invalid issuer');
        assert(!seen.has(row.ticker), 'duplicate issuer'); seen.add(row.ticker);
        if (row.calendar === null) continue;
        validateCalendar(row.calendar);
        const receipts = doc.records.filter(r => r.ticker === row.ticker && r.status !== 'not_earnings')
            .map(r => r.receipt);
        if (!receipts.length) continue;
        assert(receipts.every(r => /^\d{14}$/.test(r)), 'invalid source receipt');
        rows.push({ticker: row.ticker, calendar: row.calendar, receipt: receipts.sort().at(-1)});
    }
    return {checkedAt, rows};
}

function repair(doc, patch) {
    assert(Array.isArray(doc?.stocks), 'public report identity');
    assert(patch && Array.isArray(patch.rows));
    assert(Number.isFinite(Date.parse(patch.checkedAt)));
    const next = structuredClone(doc), changed = [], seen = new Set(), pending = [];
    for (const row of patch.rows) {
        assert(/^\d{6}$/.test(row.ticker) && !seen.has(row.ticker), 'duplicate/invalid issuer');
        seen.add(row.ticker); validateCalendar(row.calendar);
        assert(/^\d{14}$/.test(row.receipt));
        const matches = next.stocks.filter(s => s.ticker === row.ticker);
        if (!matches.length) continue; // A sparse public report need not contain every listed issuer.
        assert.equal(matches.length, 1, 'ambiguous public issuer');
        const stock = matches[0];
        for (const previous of stock.calendar || []) {
            if (previous.source !== 'DART issuer IR notice') continue;
            assert(!previous.receipt || previous.receipt <= row.receipt, 'newer official receipt exists');
            assert(!previous.observed_at || Date.parse(previous.observed_at) <= Date.parse(patch.checkedAt),
                'newer official observation exists');
        }
        pending.push({stock, row});
    }
    if (pending.length) {
        const program = 'import sys,json\nfrom api.collectors.kr_earnings_calendar import merge_calendar\n' +
            'print(json.dumps([merge_calendar(r["existing"],r["official"]) for r in json.load(sys.stdin)],ensure_ascii=False))';
        const merged = JSON.parse(cp.execFileSync('python3', ['-c', program], {
            input: JSON.stringify(pending.map(({stock,row}) => ({existing:stock.calendar || [],official:row.calendar}))),
            encoding:'utf8',maxBuffer:15000000,
        }));
        assert(Array.isArray(merged) && merged.length === pending.length);
        pending.forEach(({stock,row}, i) => {
            if (JSON.stringify(stock.calendar || []) === JSON.stringify(merged[i])) return;
            stock.calendar = merged[i]; changed.push(row.ticker);
        });
    }
    if (changed.length) {
        next._meta ||= {};
        assert(!next._meta.calendar_checked_at ||
            Date.parse(next._meta.calendar_checked_at) <= Date.parse(patch.checkedAt), 'newer calendar snapshot exists');
        next._meta.calendar_checked_at = patch.checkedAt;
    }
    return {next, changed};
}

async function publish(patch, io) {
    const metadata = await io.head(URL);
    const response = await io.fetch(URL + '?verify=' + Date.now());
    assert(response.ok, 'public read failed');
    const etag = metadata.etag;
    assert(etag && response.headers.get('etag')?.replace(/^W\//, '') === etag.replace(/^W\//, ''),
        'storage/CDN mismatch');
    const previous = Buffer.from(await response.arrayBuffer());
    const {next, changed} = repair(JSON.parse(previous), patch);
    const body = changed.length ? Buffer.from(JSON.stringify(next)) : previous;
    if (changed.length) {
        const result = await io.put(NAME, body, {access: 'public', addRandomSuffix: false,
            allowOverwrite: true, ifMatch: etag, contentType: 'application/json', cacheControlMaxAge: 3600});
        assert.equal(result.url, URL, 'unexpected public store');
    }
    for (let i = 0; i < 12; i++) {
        if (i) await io.sleep(10000);
        const response = await io.fetch(URL + '?verify=' + Date.now());
        if (response.ok && body.equals(Buffer.from(await response.arrayBuffer())))
            return {file: NAME, changed, readback: 'matched', reviewed: patch.rows.length};
    }
    throw Error('public readback differs; no repeated write');
}

function repairGithubFile(file, patch) {
    const result = repair(JSON.parse(fs.readFileSync(file)), patch);
    if (result.changed.length) fs.writeFileSync(file, JSON.stringify(result.next));
    assert.deepEqual(JSON.parse(fs.readFileSync(file)), result.next, 'local staged readback mismatch');
    return {target: 'VERITY-data/' + NAME, changed: result.changed, readback: 'matched'};
}

async function main() {
    assert(['--github-file', '--blob'].includes(process.argv[2]), 'choose --github-file or --blob explicitly');
    cp.execFileSync('git', ['ls-files', '--error-unmatch', SOURCE], {stdio: 'pipe'});
    const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Seoul',
        year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
    const patch = makePatch(JSON.parse(fs.readFileSync(SOURCE)), today);
    if (process.argv[2] === '--github-file') {
        console.log(JSON.stringify(repairGithubFile('_report_published/' + NAME, patch)));
        return;
    }
    assert(process.env.BLOB_READ_WRITE_TOKEN, 'existing Blob secret required');
    const {head, put} = require('@vercel/blob');
    console.log(JSON.stringify(await publish(patch, {head, put,
        fetch: url => fetch(url, {signal: AbortSignal.timeout(30000)}),
        sleep: ms => new Promise(resolve => setTimeout(resolve, ms))})));
}
module.exports = {makePatch, repair, publish, repairGithubFile, validateCalendar};
if (require.main === module) main().catch(e => {
    console.error('calendar publish failed: ' + e.constructor.name);
    process.exitCode = 1;
});
