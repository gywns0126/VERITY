// Correct explicitly reviewed annual financial cells in the existing public object only.
const fs = require('node:fs'), cp = require('node:child_process');
const assert = require('node:assert/strict');
const NAME = 'stock_report_public.json';
const URL = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/' + NAME;
const MANIFEST = 'data/metadata/report_fin_history_corrections_20261017.json';
const HISTORY = 'data/dart_kr_fin_history.json';
// Original first fiscal period only. It must never become a year-only public annual row.
const INCEPTION_489790 = {
    ticker:'489790',name:'한화비전',corp_code:'01867758',year:2024,
    start:'2024-09-01',end:'2024-12-31',period_kind:'inception_partial',
    currency:'KRW',fs_div:'CFS',accession:'20250317000812',filed:'2025-03-17',
    source_column:'제 1 기',
    source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20250317000812&dcmNo=10415585&eleId=21&offset=273070&length=19363&dtd=dart4.xsd',
    source_sha256:'3adf9e10ce84dc053c73264f9721f14d4a306da7ca828cb3f6eaf83846d01bf3',
    revenue:493322362934,op:-120362075,net:3210792631,stale_net:31701255717,
    accounts:{revenue:'I.매출 (주25,26,32)',net:'XV.당기순이익'},
    raw:{revenue:'493,322,362,934',net:'3,210,792,631'},
};
// Directly reviewed issuer-specific renames, not a general alias resolver. Additional issuers
// require a new primary-source review before this publication identity gate expands.
const REVIEWED_RENAMES = {
    '056190': {corp_code:'00358271',old_name:'에스에프에이',new_name:'SFA',
        accession:'20260622900507',filed:'2026-06-22',kind:'market_short_name',
        listing_effective_date:'2026-06-25',shareholders_meeting_date:null,legal_effective_date:null,
        source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260622900507&dcmNo=11441645&eleId=0&offset=0&length=0&dtd=HTML',
        source_sha256:'b7548875f2112d4b5ddc707d0c0ef8f29c56c5d3ed13a555ca48b80dd0b5ae3f'},
    '030520': {corp_code:'00204262',old_name:'한글과컴퓨터',new_name:'한컴',
        accession:'20260702900166',filed:'2026-07-02',
        source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260702900166&dcmNo=11459671&eleId=0&offset=0&length=0&dtd=HTML',
        source_sha256:'0fae6196efd3e838fc1dd2162706c789aae56aece8c96361691c9f6d68cf497c'},
    '282880': {corp_code:'01211232',old_name:'코윈테크',new_name:'코윈로보틱스',
        accession:'20260901900255',source_sha256:'662296dd661611d7b77eb1a3957d63406fc41f8d02cc45d513bc9200182fd6b8'},
    '070300': {corp_code:'00683007',old_name:'엑스큐어',new_name:'퀀텀레일',
        accession:'20260722900410',filed:'2026-07-22',
        source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260722900410&dcmNo=11489311&eleId=0&offset=0&length=0&dtd=HTML',
        source_sha256:'767f9313904798540f702f1dd46136cd90e2aa845404d1e3db7a98d2a3a2dca9'},
};
// A separately reviewed legal-name -> listed-short-name chain for this issuer only.
// Meeting date and listing date are distinct; no legal effective date is inferred.
const NAMU_NAME_CHAIN = [
    {ticker:'242040',corp_code:'01136348',old_name:'나무기술',new_name:'나무에이엑스',
        accession:'20260630900344',filed:'2026-06-30',
        source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260630900344&dcmNo=11453971&eleId=0&offset=0&length=0&dtd=HTML',
        source_sha256:'28d0a9cbf3779c1b106b161ebbb19f827b4e665caafa5ed1c0af7a8e9364e7a7',
        kind:'legal_name',shareholders_meeting_date:'2026-06-30',listing_effective_date:null},
    {ticker:'242040',corp_code:'01136348',old_name:'나무에이엑스',new_name:'나무AX',
        accession:'20260904900556',filed:'2026-09-04',
        source_url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260904900556&dcmNo=11567827&eleId=0&offset=0&length=0&dtd=HTML',
        source_sha256:'336db62a8a834f3489215a142f82fa5de04aca1d668d34f2e1ec2ec181b282a8',
        kind:'market_short_name',shareholders_meeting_date:null,listing_effective_date:'2026-09-09'},
];

function repair(doc, manifest, history) {
    const v3 = manifest.schema === 'reviewed-kr-annual-financial-corrections-v3';
    const financial = v3 || manifest.schema === 'reviewed-kr-annual-financial-corrections-v2';
    assert(financial || manifest.schema === 'reviewed-kr-annual-net-corrections-v1');
    assert(Array.isArray(manifest.rows) && manifest.rows.length > 0);
    assert(Array.isArray(doc.stocks) && Array.isArray(history.rows));
    assert(!doc._meta?.review_quarantine?.includes(INCEPTION_489790.ticker), 'quarantined first close cannot publish');
    const partialRows = manifest.rows.filter(r => r.ticker === INCEPTION_489790.ticker && r.year === INCEPTION_489790.year);
    if (partialRows.length) {
        assert(v3, 'inception partial requires v3');
        assert.deepEqual(partialRows.map(r => r.metric).sort(), ['net','revenue'], 'complete original column corrections required');
    }
    const next = structuredClone(doc), changed = [], seen = new Set();
    for (const correction of manifest.rows) {
        const metric = correction.metric ?? 'net';
        assert(['net', 'op'].includes(metric) || (v3 && metric === 'revenue'), 'unreviewed metric');
        assert(metric === 'net' || financial, 'legacy net-only contract');
        const historyMetric = {net: 'net_income', op: 'operating_profit', revenue:'revenue'}[metric];
        const key = correction.ticker + ':' + correction.year + (metric === 'net' ? '' : ':' + metric);
        assert(!seen.has(key), 'duplicate correction'); seen.add(key);
        assert(/^[0-9]{6}$/.test(correction.ticker));
        const reviewedMissingMetric = ((financial && metric === 'op') || (v3 && metric === 'revenue'))
            && correction.before === null;
        assert(Number.isSafeInteger(correction.before) || reviewedMissingMetric, 'unknown previous amount');
        assert(Number.isSafeInteger(correction.after));
        assert.equal(correction.currency, 'KRW');
        assert(['CFS', 'OFS'].includes(correction.fs_div));
        const inception = correction.ticker === INCEPTION_489790.ticker && correction.year === INCEPTION_489790.year;
        if (inception) {
            for (const field of ['ticker','name','corp_code','year','start','end','period_kind','currency','fs_div',
                'accession','filed','source_column','source_url','source_sha256']) {
                assert.equal(correction[field], INCEPTION_489790[field], 'inception source/issuer/column binding');
            }
            assert.equal(correction.publication_target, 'history_only');
            assert.equal(correction.before, metric === 'revenue' ? null : INCEPTION_489790.stale_net,
                'known old partial cell');
            assert.equal(correction.after, INCEPTION_489790[metric], 'original partial amount');
            assert.equal(correction.account_name, INCEPTION_489790.accounts[metric], 'original account identity');
            assert.equal(correction.raw_text, INCEPTION_489790.raw[metric], 'original column raw amount');
        } else {
            assert.equal(correction.publication_target, undefined, 'unreviewed publication target');
            assert.equal(correction.start, correction.year + '-01-01');
        }
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
        const historyName = correction.history_name ?? correction.name;
        if (correction.history_name !== undefined) {
            // Only a reviewed issuer-specific rename may bridge two exact names; no fuzzy aliases.
            assert(financial, 'legacy rename unsupported');
            assert(historyName && historyName !== correction.name, 'unreviewed historical name');
            if (correction.ticker === '242040') {
                assert(correction.name_change === undefined, 'two-stage evidence required');
                assert.deepEqual(correction.name_change_chain, NAMU_NAME_CHAIN, 'rename chain/source/issuer binding');
                assert.equal(historyName, NAMU_NAME_CHAIN[0].old_name);
                assert.equal(correction.name, NAMU_NAME_CHAIN[1].new_name);
            } else {
                const rename = correction.name_change;
                assert(rename, 'unreviewed historical name');
                const approved = REVIEWED_RENAMES[correction.ticker];
                assert(approved, 'issuer rename has not been independently reviewed');
                for (const field of Object.keys(approved)) assert.equal(rename[field], approved[field], 'rename source/issuer binding');
                assert.equal(rename.old_name, historyName);
                assert.equal(rename.new_name, correction.name);
                assert.equal(rename.ticker, correction.ticker);
                assert(/^[0-9]{8}$/.test(rename.corp_code), 'rename issuer identity');
                assert(/^[0-9]{14}$/.test(rename.accession), 'rename accession');
                assert(rename.source_url.startsWith('https://dart.fss.or.kr/report/viewer.do?'));
                assert(rename.source_url.includes('rcpNo=' + rename.accession));
                assert(/^[a-f0-9]{64}$/.test(rename.source_sha256), 'rename original source');
            }
        }
        assert.equal(source[0].name, historyName);
        assert.equal(source[0].fundamentals[historyMetric], correction.after, 'history must already be corrected');
        if (inception) {
            for (const field of ['corp_code','start','end','period_kind','currency','fs_div','accession','filed',
                'source_column','source_url','source_sha256']) {
                assert.equal(source[0][field], INCEPTION_489790[field], 'corrected history provenance');
            }
            assert.equal(source[0].fundamentals.operating_profit, INCEPTION_489790.op, 'one original OP column');
            assert.equal(source[0].fundamentals.revenue, INCEPTION_489790.revenue, 'one original revenue column');
            assert.equal(source[0].fundamentals.net_income, INCEPTION_489790.net, 'one original total net column');
        }
        const stocks = next.stocks.filter(s => s.ticker === correction.ticker);
        assert.equal(stocks.length, 1, 'public identity');
        assert.equal(stocks[0].name_ko || stocks[0].name, correction.name);
        const periods = stocks[0].fin_series.filter(p => p.year === correction.year);
        if (inception) {
            assert(periods.length <= 1, 'duplicate public partial year');
            if (periods.length) {
                const old = periods[0];
                assert.deepEqual(Object.keys(old).sort(), ['net','op','revenue','year'], 'unknown partial public fields');
                assert.deepEqual(old, {year:2024,revenue:null,op:INCEPTION_489790.op,net:INCEPTION_489790.stale_net},
                    'unknown partial public amount');
                stocks[0].fin_series.splice(stocks[0].fin_series.indexOf(old), 1);
                changed.push('489790:2024:remove_partial');
            }
            continue;
        }
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

async function publishBlob({head, put, fetcher = globalThis.fetch, loadSources = latestReviewedSources}) {
    const metadata = await head(URL);
    const response = await fetcher(URL + '?verify=' + Date.now(), {signal: AbortSignal.timeout(30000)});
    assert(response.ok, 'public read failed');
    const etag = metadata.etag;
    assert(etag && response.headers.get('etag')?.replace(/^W\//, '') === etag.replace(/^W\//, ''), 'storage/CDN mismatch');
    const previous = Buffer.from(await response.arrayBuffer());
    const reviewed = loadSources();
    const {next, changed} = repair(JSON.parse(previous), reviewed.manifest, reviewed.history);
    const latest = loadSources();
    assert.equal(latest.ref, reviewed.ref, 'main changed before Blob write');
    assert.deepEqual(repair(next, latest.manifest, latest.history).changed, [],
        'latest reviewed correction not reflected before Blob write');
    const body = changed.length ? Buffer.from(JSON.stringify(next)) : previous;
    if (changed.length) {
        const result = await put(NAME, body, {access: 'public', addRandomSuffix: false,
            allowOverwrite: true, ifMatch: etag, contentType: 'application/json', cacheControlMaxAge: 3600});
        assert.equal(result.url, URL, 'unexpected public store');
    }
    for (let i = 0; i < 12; i++) {
        if (i) await new Promise(resolve => setTimeout(resolve, 10000));
        const check = await fetcher(URL + '?verify=' + Date.now(), {signal: AbortSignal.timeout(30000)});
        if (check.ok && body.equals(Buffer.from(await check.arrayBuffer()))) {
            return {file: NAME, changed, readback: 'matched', reviewed: reviewed.manifest.rows.length};
        }
    }
    throw Error('public readback differs; no repeated write');
}

async function main() {
    if (process.argv[2] === '--staged-public') {
        const result = repairStagedFile('_public_dist/' + NAME);
        console.log(JSON.stringify({target: '_public_dist/' + NAME, ...result}));
        return;
    }
    if (process.argv[2] === '--github-file') {
        const manifest = JSON.parse(fs.readFileSync(MANIFEST));
        const history = JSON.parse(fs.readFileSync(HISTORY));
        const path = '_report_published/' + NAME;
        const result = repair(JSON.parse(fs.readFileSync(path)), manifest, history);
        if (result.changed.length) fs.writeFileSync(path, JSON.stringify(result.next));
        console.log(JSON.stringify({target: 'VERITY-data/' + NAME, changed: result.changed}));
        return;
    }
    assert(process.env.BLOB_READ_WRITE_TOKEN, 'existing Blob secret required');
    console.log(JSON.stringify(await publishBlob(require('@vercel/blob'))));
}
module.exports = {repair, repairStagedFile, latestReviewedSources, publishBlob};
if (require.main === module) main().catch(e => {
    console.error('report correction publish failed: ' + e.constructor.name);
    process.exitCode = 1;
});
