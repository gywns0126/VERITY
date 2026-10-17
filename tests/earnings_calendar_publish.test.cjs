const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {makePatch, repair, publish, repairGithubFile} = require('../scripts/publish_earnings_calendar.cjs');
const checkedAt = '2026-10-18T00:00:00+09:00';
const event = {date:'2026-10-30',event:'실적발표 (회사 공시)',kind:'실적',is_estimated:false,
    source:'DART issuer IR notice',url:'https://dart.fss.or.kr/report/viewer.do?rcpNo=20261014800271',
    receipt:'20261014800271',filed:'20261014',observed_at:checkedAt,basis:'회사 공시'};
const source = () => ({_meta:{checked_at:checkedAt},records:[{...event,ticker:'000270',
    status:'confirmed',purpose:'2026년 3분기 경영실적 발표',body_sha256:'a'.repeat(64)}]});
const patch = () => ({checkedAt,rows:[{ticker:'000270',receipt:event.receipt,calendar:[{...event}]}]});
const report = () => ({_meta:{generated_at:'2026-10-01'},stocks:[
    {ticker:'000270',financials:{latest:12345},fin_series:[{year:2025,net:76543}],
        calendar:[{date:'2026-10-23',kind:'실적',is_estimated:true},
                  {date:'2026-12-31',kind:'배당',event:'배당기준일'}],unrelated:'preserve'},
    {ticker:'005930',calendar:[{date:'2026-10-29'}],facts:{value:44}},
],unknown:{a:[1,2]}});
const response = (body, etag='"v1"') => ({ok:true,headers:{get:()=>etag},
    arrayBuffer:async()=>Buffer.from(typeof body === 'string' ? body : JSON.stringify(body))});

test('real collector selection, corrections, cancellation and stale observation', () => {
    assert.deepEqual(makePatch(source(),'2026-10-18'),patch());
    const cancelled=source();cancelled.records.push({...cancelled.records[0],
        receipt:'20261015800271',status:'cancelled'});
    assert.deepEqual(makePatch(cancelled,'2026-10-18').rows[0].calendar,[]);
    assert.deepEqual(makePatch(source(),'2026-10-23').rows[0].calendar,[]);
});

test('changes only targeted calendar and dedicated observation metadata', () => {
    const original=report(), before=structuredClone(original), result=repair(original,patch());
    assert.deepEqual(original,before);
    assert.deepEqual(result.changed,['000270']);
    const expected=structuredClone(before);expected.stocks[0].calendar=[before.stocks[0].calendar[1],event];
    expected._meta.calendar_checked_at=checkedAt;
    assert.deepEqual(result.next,expected);
    assert.deepEqual(repair(result.next,patch()).changed,[]);
});

test('empty calendar removes cancelled estimate without affecting other fields', () => {
    const p=patch();p.rows[0].calendar=[];
    assert.deepEqual(repair(report(),p).next.stocks[0].calendar,[report().stocks[0].calendar[1]]);
});

test('rejects private/nested fields, wrong issuer URL and duplicate identity', () => {
    for (const bad of [{private_account:'secret'}, {url:'https://example.com/?rcpNo='+event.receipt},
        {url:event.url.replace(event.receipt,'20261015800271')}, {basis:{private:true}}]) {
        const p=patch();Object.assign(p.rows[0].calendar[0],bad);
        assert.throws(()=>repair(report(),p));
    }
});

test('rejects duplicate report issuer and stale overwrite of newer official data', () => {
    const duplicatedPatch=patch();duplicatedPatch.rows.push({...duplicatedPatch.rows[0]});
    assert.throws(()=>repair(report(),duplicatedPatch),/duplicate/);
    const dup=report();dup.stocks.push(structuredClone(dup.stocks[0]));
    assert.throws(()=>repair(dup,patch()),/ambiguous/);
    const newer=report();newer.stocks[0].calendar=[{...event,receipt:'20261015800271'}];
    assert.throws(()=>repair(newer,patch()),/newer official receipt/);
});

test('conditional conflict does not retry writes', async () => {
    let puts=0;
    await assert.rejects(publish(patch(),{head:async()=>({etag:'"v1"'}),
        fetch:async()=>response(report()),put:async()=>{puts++;throw Error('precondition failed');},
        sleep:async()=>{}}),/precondition failed/);
    assert.equal(puts,1);
});

test('already updated public object is verified without another write', async () => {
    const current=repair(report(),patch()).next;
    const result=await publish(patch(),{head:async()=>({etag:'"v1"'}),
        fetch:async()=>response(current),put:async()=>assert.fail('unnecessary write'),sleep:async()=>{}});
    assert.deepEqual(result.changed,[]);assert.equal(result.readback,'matched');
});

test('conditional write uses current ETag and exact body readback once', async () => {
    let body, puts=0, reads=0;
    const result=await publish(patch(),{
        head:async()=>({etag:'"v1"'}),
        fetch:async()=>++reads===1 ? response(report()):response(body),
        put:async(name, b, options)=>{puts++;body=b.toString();assert.equal(options.ifMatch,'"v1"');
            assert.equal(options.allowOverwrite,true);
            return {url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/'+name};},
        sleep:async()=>{},
    });
    assert.equal(puts,1);assert.equal(result.readback,'matched');
    assert.equal(JSON.parse(body).stocks[0].financials.latest,12345);
});

test('CDN mismatch stops before write and readback failure never rewrites', async () => {
    let puts=0;
    const io={head:async()=>({etag:'"v1"'}),fetch:async()=>response(report(),'"v2"'),
        put:async()=>{puts++;return {url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json'};},
        sleep:async()=>{}};
    await assert.rejects(publish(patch(),io),/mismatch/);assert.equal(puts,0);
    io.fetch=async()=>response(report());
    await assert.rejects(publish(patch(),io),/readback differs/);assert.equal(puts,1);
});

test('GitHub fallback file receives identical selective mutation', () => {
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'calendar-publish-test-'));
    const file=path.join(dir,'stock_report_public.json');
    try {fs.writeFileSync(file,JSON.stringify(report()));
        assert.equal(repairGithubFile(file,patch()).readback,'matched');
        assert.deepEqual(JSON.parse(fs.readFileSync(file)),repair(report(),patch()).next);
    } finally {fs.rmSync(file);fs.rmdirSync(dir);}
});
