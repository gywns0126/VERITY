const {test} = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const cp = require('node:child_process');
const {repair, repairStagedFile, latestReviewedSources} = require('../scripts/publish_report_financials.cjs');
const c = require('../data/metadata/report_fin_history_corrections_20261017.json').rows.find(r => !r.metric || r.metric === 'net');
const manifest = {schema: 'reviewed-kr-annual-net-corrections-v1', rows: [c]};
const history = {rows: [{ticker:c.ticker,name:c.name,fiscal_year:c.year,period:'annual',fundamentals:{net_income:c.after}}]};
const doc = {_meta:{generated_at:'2026-10-16'},stocks:[{ticker:c.ticker,name:c.name,fin_series:[{year:c.year,net:c.before,revenue:100}]},{ticker:'000000',extra:'preserve'}]};
test('only the explicitly reviewed cell changes; input and dates preserved', () => {
    const result = repair(doc,manifest,history);
    assert.deepEqual(result.changed,[c.ticker+':'+c.year]);
    const original = structuredClone(result.next); original.stocks[0].fin_series[0].net=c.before;
    assert.deepEqual(original,doc);
    assert.equal(doc.stocks[0].fin_series[0].net,c.before);
    assert.deepEqual(repair(result.next,manifest,history).changed,[]);
});
test('unknown previous value and identity mismatch stop before any upload',()=>{
    for (const modify of [d=>d.stocks[0].fin_series[0].net=123,d=>d.stocks[0].name='다른회사',d=>d.stocks.push(structuredClone(d.stocks[0]))]) {
        const bad=structuredClone(doc);modify(bad);assert.throws(()=>repair(bad,manifest,history));
    }
});
test('uncorrected history and duplicate instructions are rejected',()=>{
    const bad=structuredClone(history);bad.rows[0].fundamentals.net_income=c.before;
    assert.throws(()=>repair(doc,manifest,bad));
    assert.throws(()=>repair(doc,{...manifest,rows:[c,c]},history));
});
test('raw unit mismatch cannot publish a differently scaled amount',()=>{
    assert.throws(()=>repair(doc,{...manifest,rows:[{...c,reported_unit:'천원',unit_multiplier:1000}]},history));
    assert.throws(()=>repair(doc,{...manifest,rows:[{...c,reported_unit:'미확인'}]},history));
    assert.throws(()=>repair(doc,{...manifest,rows:[{...c,reported_unit:undefined}]},history));
    assert.throws(()=>repair(doc,{...manifest,rows:[{...c,unit_multiplier:undefined}]},history));
});
test('reviewed operating profit maps only to operating_profit and preserves net',()=>{
    const op={...c,metric:'op',before:819360000000,after:1180900000000,
        raw_text:'1,180,900',reported_unit:'백만원',unit_multiplier:1000000};
    const newer={schema:'reviewed-kr-annual-financial-corrections-v2',rows:[c,op]};
    const d=structuredClone(doc);d.stocks[0].fin_series[0].op=op.before;
    const h=structuredClone(history);h.rows[0].fundamentals.operating_profit=op.after;
    const result=repair(d,newer,h);
    assert.equal(result.next.stocks[0].fin_series[0].op,op.after);
    assert.equal(result.next.stocks[0].fin_series[0].net,c.after);
    assert.equal(result.next.stocks[0].fin_series[0].revenue,100);
    assert.deepEqual(result.changed,[c.ticker+':'+c.year,c.ticker+':'+c.year+':op']);
    assert.deepEqual(repair(result.next,newer,h).changed,[]);
    assert.throws(()=>repair(d,{...newer,rows:[{...op,metric:'revenue'}]},h));
    assert.throws(()=>repair(d,{...newer,schema:manifest.schema},h));
    assert.throws(()=>repair(d,{...newer,rows:[op,op]},h));
    h.rows[0].fundamentals.operating_profit=op.before;
    assert.throws(()=>repair(d,newer,h));
});
test('explicit reviewed missing op may be filled; unknown and zero values never count as missing',()=>{
    const op={...c,metric:'op',before:null,after:298172334242,raw_text:'298,172,334,242',reported_unit:'원',unit_multiplier:1};
    const newer={schema:'reviewed-kr-annual-financial-corrections-v2',rows:[op]};
    const d=structuredClone(doc);d.stocks[0].fin_series[0].op=null;
    const h=structuredClone(history);h.rows[0].fundamentals.operating_profit=op.after;
    const result=repair(d,newer,h);
    assert.equal(result.next.stocks[0].fin_series[0].op,op.after);
    assert.equal(result.next.stocks[0].fin_series[0].net,c.before);
    assert.deepEqual(repair(result.next,newer,h).changed,[]);
    for (const value of [0,123,undefined]) {
        const bad=structuredClone(d);bad.stocks[0].fin_series[0].op=value;
        assert.throws(()=>repair(bad,newer,h));
    }
    assert.throws(()=>repair(d,{...newer,schema:manifest.schema},h));
    assert.throws(()=>repair(d,{...newer,rows:[{...op,after:null}]},h));
    assert.throws(()=>repair(d,{...newer,rows:[{...op,metric:'net'}]},h));
});

test('staged full report reconciles seven stale cells and preserves all other data', t => {
    const rows = require('../data/metadata/report_fin_history_corrections_20261017.json').rows.slice(0, 7);
    const stocks = new Map(), histories = new Map();
    for (const row of rows) {
        if (!stocks.has(row.ticker)) stocks.set(row.ticker, {ticker:row.ticker,name:row.name,fin_series:[]});
        const stock = stocks.get(row.ticker);
        let period = stock.fin_series.find(p => p.year === row.year);
        if (!period) { period = {year:row.year,revenue:123,other:'preserve'}; stock.fin_series.push(period); }
        period[row.metric ?? 'net'] = row.before;
        const key = `${row.ticker}:${row.year}`;
        if (!histories.has(key)) histories.set(key, {ticker:row.ticker,name:row.name,fiscal_year:row.year,period:'annual',fundamentals:{}});
        histories.get(key).fundamentals[row.metric === 'op' ? 'operating_profit' : 'net_income'] = row.after;
    }
    const input = {_meta:{generated_at:'old-full-run'},stocks:[...stocks.values(),{ticker:'000000',extra:'untouched'}]};
    const sources = () => ({manifest:{schema:'reviewed-kr-annual-financial-corrections-v2',rows},history:{rows:[...histories.values()]},ref:'latest-main'});
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'report-stage-'));
    t.after(() => fs.rmSync(dir, {recursive:true,force:true}));
    const file = path.join(dir, 'stock_report_public.json');
    fs.writeFileSync(file, JSON.stringify(input));
    const result = repairStagedFile(file, sources);
    assert.equal(result.changed.length, 7);
    assert.equal(result.ref, 'latest-main');
    const output = JSON.parse(fs.readFileSync(file));
    assert.deepEqual(repair(output, sources().manifest, sources().history).changed, []);
    assert.equal(output._meta.generated_at, input._meta.generated_at);
    assert.deepEqual(output.stocks.at(-1), input.stocks.at(-1));
    for (const stock of output.stocks.slice(0, -1)) for (const period of stock.fin_series) {
        assert.equal(period.revenue, 123);
        assert.equal(period.other, 'preserve');
    }
    const bytes = fs.readFileSync(file);
    assert.deepEqual(repairStagedFile(file, sources).changed, []);
    assert.deepEqual(fs.readFileSync(file), bytes);

    for (const bad of [
        () => { const d=structuredClone(input); d.stocks[0].fin_series[0].op=0; return JSON.stringify(d); },
        () => { const d=structuredClone(input); d.stocks.shift(); return JSON.stringify(d); },
        () => '{invalid-json',
    ]) {
        const original = bad(); fs.writeFileSync(file, original);
        assert.throws(() => repairStagedFile(file, sources));
        assert.equal(fs.readFileSync(file, 'utf8'), original, 'failed validation must not rewrite staged report');
    }
    fs.writeFileSync(file, JSON.stringify(input));
    assert.throws(() => repairStagedFile(file, () => {throw Error('fetch or source failure');}));
    assert.deepEqual(JSON.parse(fs.readFileSync(file)), input);
    fs.rmSync(file);
    assert.deepEqual(repairStagedFile(file, () => {throw Error('must not fetch');}), {skipped:true,changed:[]});
});

test('latest manifest and history are read from one freshly fetched main ref', () => {
    const sha = 'a'.repeat(40), calls = [];
    const exec = (command, args) => {
        calls.push([command, args]);
        if (args[0] === 'fetch') return '';
        if (args[0] === 'rev-parse') return sha + '\n';
        if (args[1] === sha + ':data/metadata/report_fin_history_corrections_20261017.json') return JSON.stringify(manifest);
        if (args[1] === sha + ':data/dart_kr_fin_history.json') return JSON.stringify(history);
        throw Error('unexpected git read');
    };
    const result = latestReviewedSources(exec);
    assert.equal(result.ref, sha);
    assert.deepEqual(result.manifest, manifest);
    assert.deepEqual(result.history, history);
    assert.deepEqual(calls.map(([,args]) => args[0]), ['fetch','rev-parse','show','show']);
    assert.throws(() => latestReviewedSources((_, args) => {
        if (args[0] === 'fetch') return '';
        if (args[0] === 'rev-parse') return sha;
        throw Error('missing latest manifest or history');
    }));
});

test('staged CLI uses the remote committed correction, not stale local inputs', t => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'report-publish-git-'));
    t.after(() => fs.rmSync(dir, {recursive:true,force:true}));
    const remote = path.join(dir, 'origin.git'), work = path.join(dir, 'work');
    fs.mkdirSync(work);
    const git = (...args) => cp.execFileSync('git', args, {cwd:work,stdio:'pipe'});
    cp.execFileSync('git', ['init','--bare','--initial-branch=main',remote], {stdio:'pipe'});
    git('init','--initial-branch=main');
    git('config','user.name','Report fixture');
    git('config','user.email','report-fixture@example.invalid');
    fs.mkdirSync(path.join(work,'data','metadata'), {recursive:true});
    fs.writeFileSync(path.join(work,'data','metadata','report_fin_history_corrections_20261017.json'),JSON.stringify(manifest));
    fs.writeFileSync(path.join(work,'data','dart_kr_fin_history.json'),JSON.stringify(history));
    git('add','data/metadata/report_fin_history_corrections_20261017.json','data/dart_kr_fin_history.json');
    git('commit','-m','fixture: reviewed source');
    git('remote','add','origin',remote);
    git('push','origin','main');
    fs.mkdirSync(path.join(work,'_public_dist'));
    const file = path.join(work,'_public_dist','stock_report_public.json');
    fs.writeFileSync(file,JSON.stringify(doc));
    const stale = structuredClone(history); stale.rows[0].fundamentals.net_income=c.before;
    fs.writeFileSync(path.join(work,'data','dart_kr_fin_history.json'),JSON.stringify(stale));
    // A dirty, old checkout must not replace the source loaded from the fetched commit.
    fs.writeFileSync(path.join(work,'data','metadata','report_fin_history_corrections_20261017.json'),'{}');
    const command = () => cp.spawnSync(process.execPath,
        [path.resolve(__dirname,'../scripts/publish_report_financials.cjs'),'--staged-public'],
        {cwd:work,encoding:'utf8'});
    const result = command();
    assert.equal(result.status,0,result.stderr);
    const logged = JSON.parse(result.stdout);
    assert.match(logged.ref,/^[a-f0-9]{40}$/);
    assert.deepEqual(logged.changed,[c.ticker+':'+c.year]);
    assert.deepEqual(JSON.parse(fs.readFileSync(file)),repair(doc,manifest,history).next);
    const bytes = fs.readFileSync(file);
    assert.equal(command().status,0);
    assert.deepEqual(fs.readFileSync(file),bytes);
    const bad = structuredClone(doc);bad.stocks[0].fin_series[0].net=123;
    fs.writeFileSync(file,JSON.stringify(bad));
    assert.equal(command().status,1);
    assert.deepEqual(JSON.parse(fs.readFileSync(file)),bad);
});
