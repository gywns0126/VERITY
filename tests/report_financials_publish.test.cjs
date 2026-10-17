const {test} = require('node:test'), assert = require('node:assert/strict');
const {repair} = require('../scripts/publish_report_financials.cjs');
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
