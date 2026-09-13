const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs');
const {validate} = require('../scripts/publish_nest_exposure.cjs');
const doc = JSON.parse(fs.readFileSync('data/portfolio_exposure_map.json'));
test('public classification has explicit coverage and source dates',()=>assert.equal(validate(doc).count,Object.keys(doc.stocks).length));
test('empty rows rejected',()=>assert.throws(()=>validate({...doc,stocks:{}})));
test('private member fields rejected',()=>{const bad=structuredClone(doc);Object.values(bad.stocks)[0].user_id='private';assert.throws(()=>validate(bad));});
test('older source rejected',()=>{const current=structuredClone(doc);current._meta.kr_generated_at='2099-01-01';assert.throws(()=>validate(doc,current));});
test('incorrect denominator rejected',()=>{const bad=structuredClone(doc);bad._meta.count++;assert.throws(()=>validate(bad));});
test('no price or score published',()=>assert(Object.values(doc.stocks).every(r=>Object.keys(r).length===3)));
