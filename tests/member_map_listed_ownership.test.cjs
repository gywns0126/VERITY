'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const { buildListedOwnership } = require('../scripts/member-map/build-listed-ownership.cjs');

const investor = { ticker: '123456', market: 'KR', name: '가람전자' };
const investee = { ticker: '654321', market: 'KR', name: '모래기계' };
const endpoint = 'otrCprInvstmntSttus';
const receipt = '20260814001234';
function fixture() {
  const p = { endpoint, rcept_no: receipt, corp_code: '00123456', stlm_dt: '2026-06-30', bsns_year: '2026', reprt_code: '11012' };
  const raw = { corp_code: p.corp_code, rcept_no: receipt, stlm_dt: p.stlm_dt, inv_prm: '㈜모래기계',
    trmend_blce_qota_rt: '12.50', trmend_blce_qy: '1,000' };
  const row = { inv_corp_name: raw.inv_prm, ownership_pct: 12.5, end_balance_qty: 1000, sourceRow: { index: 2, fields: raw }, provenance: p };
  const block = { status: '000', reportPeriod: { year: '2026', reportCode: '11012' }, sourceActualSettlementDates: ['2026-06-30'], rows: [row] };
  const issuer = { ...investor, mappingStatus: 'mapped', corp_code: p.corp_code, endpoints: { [endpoint]: block } };
  const src = { schema: 'alphanest-company-structure-sources-v1', issuers: { 'KR:123456': issuer } };
  const universe = { stocks: [{ ...investor }, { ...investee }] };
  return { src, universe, row, p, raw, issuer, block, run: () => buildListedOwnership(src, universe) };
}

test('only the closed historical row is released for each original endpoint', () => {
  const f = fixture();
  Object.assign(f.raw, { stock_code: investor.ticker, corp_name: '주식회사 가람전자', party_ticker: investee.ticker });
  const expected = { issuer: 'KR:123456', party: 'KR:654321', issuer_name: '가람전자', party_name: '㈜모래기계',
    endpoint, receipt, settled_on: '2026-06-30', pct: 12.5, row_index: 2 };
  assert.deepEqual(f.run(), { schema:'member-map-listed-ownership-v1',rows:[expected] });
  const holder = 'hyslrSttus';
  f.issuer.endpoints = { [holder]: f.block };
  Object.assign(f.row, { nm: f.raw.inv_prm, stock_rate: '12.50', stock_cnt: '1,000' });
  Object.assign(f.raw, { nm: f.row.nm, trmend_posesn_stock_qota_rt: '12.50', trmend_posesn_stock_co: '1,000' });
  f.p.endpoint = holder;
  assert.deepEqual(f.run().rows, [{ ...expected, endpoint: holder }]);
  f.row.stock_cnt = '1001';
  assert.deepEqual(f.run().rows, []);
});

test('invalid bindings, measurements and endpoint periods fail closed', () => {
  const changes = [
    f=>f.issuer.ticker='000000', f=>f.issuer.name='다른 법인', f=>f.issuer.market='US',
    f=>f.raw.stock_code=123456, f=>f.raw.ticker='999999', f=>f.raw.corp_name='다른 법인', f=>f.raw.party_ticker='999999',
    f=>f.issuer.corp_code='11111111', f=>f.p.corp_code='00111111', f=>f.raw.corp_code='00111111',
    f=>f.raw.rcept_no='20260814001235', f=>f.raw.inv_prm='가람전자', f=>f.row.inv_corp_name='다른 표시',
    f=>f.row.ownership_pct=12, f=>f.row.ownership_pct=f.raw.trmend_blce_qota_rt='0',
    f=>f.row.ownership_pct=f.raw.trmend_blce_qota_rt='101', f=>f.row.ownership_pct=f.raw.trmend_blce_qota_rt='1,2',
    f=>f.row.end_balance_qty=0, f=>f.raw.trmend_blce_qy='0', f=>f.raw.endpoint='hyslrSttus',
    f=>f.block.corp_code='11111111', f=>f.block.endpoint='hyslrSttus', f=>f.row.issuer_name='불일치',
    f=>f.p.reprt_code='11011', f=>f.p.bsns_year='2025', f=>f.raw.reprt_code='11013',
    f=>f.raw.stlm_dt='2026-02-30', f=>f.raw.stlm_dt=f.p.stlm_dt='2027-06-30',
    f=>delete f.block.reportPeriod, f=>f.block.status='013', f=>f.block.sourceActualSettlementDates=['2025-12-31'],
    f=>f.row.sourceRow.index=-1, f=>delete f.row.sourceRow.fields, f=>delete f.row.provenance,
    f=>f.src.issuers['KR:999999']={ ...f.issuer, ticker:'999999' },
  ];
  for (const change of changes) { const f=fixture(); change(f); assert.deepEqual(f.run().rows, [],String(change)); }
});

test('uncertain identities, personal holders, vehicles, aggregates and self stay out', () => {
  for (const name of ['개인','합 계','자기주식','Alpha Fund','대한기업인수목적','대한투자조합','가람전자']) {
    const f=fixture(); f.universe.stocks[1].name=name;f.raw.inv_prm=f.row.inv_corp_name=name;
    assert.deepEqual(f.run().rows, [],name);
  }
  for (const market of ['KR','KONEX']) {
    const f=fixture(); f.universe.stocks.push({ market,ticker:'222222',name:'모래 기계' });
    assert.deepEqual(f.run().rows, []);
  }
  for (const change of [f=>f.universe.stocks[1].type='ETF', f=>f.universe.stocks[1].market='KONEX',
    f=>f.raw.relate='친족', f=>f.row.relate='임원', f=>f.universe.stocks.push({...investee,name:'다른 종목'})]) {
    const f=fixture();change(f);assert.deepEqual(f.run().rows, []);
  }
});

test('literal repeated rows collapse; inconsistent original row locations are held', () => {
  const f=fixture(), second=structuredClone(f.row);second.sourceRow.index=4;
  f.block.rows=[second,structuredClone(f.row),f.row];const first=f.run();
  assert.deepEqual(first.rows.map(x=>x.row_index),[2,4]);
  f.block.rows.reverse(); f.universe.stocks.reverse();assert.deepEqual(f.run(),first);
  const conflict=structuredClone(f.row);conflict.ownership_pct=11;conflict.sourceRow.fields.trmend_blce_qota_rt='11';
  f.block.rows.push(conflict);assert.deepEqual(f.run().rows.map(x=>x.row_index),[4]);
  f.block.rows.reverse();assert.deepEqual(f.run().rows.map(x=>x.row_index),[4]);
});

test('byte ceiling and empty CLI results never replace the previous candidate', () => {
  const f=fixture();
  f.block.rows=Array.from({length:6000},(_,index)=>({...f.row,sourceRow:{...f.row.sourceRow,index}}));
  assert.throws(()=>f.run(),/1 MiB/);
  const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'ownership-test-'));
  try {
    const put=(name,v)=>{const file=path.join(scratch,name);fs.writeFileSync(file,JSON.stringify(v));return file};
    const cmd=path.resolve(__dirname,'../scripts/member-map/build-listed-ownership.cjs');
    f.block.rows=[f.row];const source=put('source.json',f.src), univ=put('universe.json',f.universe), out=path.join(scratch,'result.json');
    execFileSync(process.execPath,[cmd,source,univ,out]);
    const before=fs.readFileSync(out);f.block.rows=[];put('source.json',f.src);
    assert.notEqual(spawnSync(process.execPath,[cmd,source,univ,out]).status,0);assert.deepEqual(before,fs.readFileSync(out));
  } finally { fs.rmSync(scratch,{recursive:true,force:true}); }
});

test('Blob alone sees the candidate during upload; local failure leaves the core upload and prior Blob intact', () => {
  const action = fs.readFileSync(path.resolve(__dirname, '../.github/actions/publish-data/action.yml'), 'utf8');
  const blobStep = action.split('    - name: Dual-write to Vercel Blob')[1].split('\n    - name:')[0];
  const gitEnd = action.indexOf('    - name: Dual-write to Vercel Blob');
  assert.match(action.slice(0,gitEnd), /Recover VERITY-data publish/);
  assert.doesNotMatch(action.slice(0,gitEnd), /member_map_listed_ownership|build-listed-ownership/);
  assert.match(action, /public_commit=\$\(git rev-parse --verify 'origin\/main\^\{commit\}'\)/);
  assert.match(action, /git show "\$public_commit:data\/\$f" > "_public_dist\/\$f"/);
  assert.match(blobStep, /PUBLIC_COMMIT: \$\{\{ steps.stage_public_data.outputs.commit \}\}/);
  const start = blobStep.indexOf('        public_dist=');
  const upload = '        node blob_upload.js "${{ github.workspace }}/_public_dist"';
  assert.ok(start > 0 && blobStep.indexOf(upload) > start);
  const script = blobStep.slice(start,blobStep.indexOf(upload) + upload.length)
    .split('\n').map(line => line.replace(/^        /u, '')).join('\n')
    .replace('${{ github.workspace }}','$GITHUB_WORKSPACE');
  assert.doesNotMatch(script, /\bcurl\b|\bfetch\b|--check-prior/);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ownership-blob-test-'));
  try {
    const f=fixture(), dist=path.join(root,'_public_dist'), name='member_map_listed_ownership.json';
    fs.mkdirSync(dist);fs.mkdirSync(path.join(root,'bin'));fs.mkdirSync(path.join(root,'temp'));
    fs.symlinkSync(path.resolve(__dirname,'../scripts'),path.join(root,'scripts'),'dir');
    fs.writeFileSync(path.join(dist,'universe_search.json'),JSON.stringify(f.universe));
    fs.writeFileSync(path.join(root,'fixture-source.json'),JSON.stringify(f.src));
    fs.writeFileSync(path.join(root,'bin','git'),
      '#!/bin/sh\n[ "$GIT_NO_LAZY_FETCH" = 1 ] && [ "$1" = -C ] && [ "$2" = "$GITHUB_WORKSPACE" ] && [ "$3" = show ] && [ "$4" = pinned:data/member_map_company_structure_sources.json ] && [ "$CASE" != missing ] && cat fixture-source.json\n',{mode:0o755});
    fs.writeFileSync(path.join(root,'blob_upload.js'),`
      const fs=require('node:fs'),path=require('node:path'),dir=process.argv[2];
      const files=fs.readdirSync(dir);fs.writeFileSync('seen.json',JSON.stringify(files));
      if(process.env.CASE==='upload-error')process.exit(7);
      if(files.includes('${name}'))fs.copyFileSync(path.join(dir,'${name}'),'fake-blob');
    `);
    for (const mode of ['ok','missing','empty','upload-error']) {
      fs.writeFileSync(path.join(root,'fake-blob'),'prior');
      const input=structuredClone(f.src);if(mode==='empty')input.issuers['KR:123456'].endpoints[endpoint].rows=[];
      fs.writeFileSync(path.join(root,'fixture-source.json'),JSON.stringify(input));
      const result=spawnSync('bash',['-e','-c',script],{cwd:root,env:{...process.env,PATH:path.join(root,'bin')+':'+process.env.PATH,
        PUBLIC_COMMIT:'pinned',GITHUB_WORKSPACE:root,RUNNER_TEMP:path.join(root,'temp'),CASE:mode}});
      assert.equal(result.status,mode==='upload-error'?7:0,result.stderr.toString());
      const files=JSON.parse(fs.readFileSync(path.join(root,'seen.json')));
      assert.deepEqual(files.sort(),(mode==='ok'||mode==='upload-error'?[name,'universe_search.json']:['universe_search.json']).sort());
      const previous=fs.readFileSync(path.join(root,'fake-blob'),'utf8');
      if(mode==='ok')assert.deepEqual(JSON.parse(previous),f.run());else assert.equal(previous,'prior');
      assert.deepEqual(fs.readdirSync(dist),['universe_search.json']);
      assert.deepEqual(fs.readdirSync(path.join(root,'temp')),[]);
    }
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
