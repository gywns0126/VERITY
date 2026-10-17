const {test} = require('node:test'), assert = require('node:assert/strict');
const {repair} = require('../scripts/publish_report_financials.cjs');
const c = require('../data/metadata/report_fin_history_corrections_20261017.json').rows[0];
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
