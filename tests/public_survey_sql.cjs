// Isolated in-memory PostgreSQL/WASM only. No network or production DB.
// PGLITE_MODULE=/existing/path/to/@electric-sql/pglite node tests/public_survey_sql.cjs
// Promise.all here checks queued competing requests, not multi-connection load.
const {PGlite} = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, 'supabase/migrations', name), 'utf8');
const db = new PGlite();
const version = '2026-10-v1';
const uuid = n => '00000000-0000-4000-8000-' + n.toString(16).padStart(12, '0');
const hash = n => n.toString(16).padStart(64, '0');
const answers = {purpose:'company', features:['report','map'], outcome:'yes', discovery:null, comment:''};
const empty = {purpose:null, features:[], outcome:null, discovery:null, comment:''};
let passed = 0;
async function check(name, fn) { await fn(); passed++; console.log('PASS ' + name); }
async function role(name) { await db.exec('reset role'); if (name) await db.exec('set role ' + name); }
async function scalar(sql, args=[]) { return Object.values((await db.query(sql, args)).rows[0])[0]; }
async function submit(request=1, client=1, body=answers, bucket=hash(1), v=version) {
  return scalar('select public.submit_public_survey($1,$2::uuid,$3,$4::jsonb,$5)',
    [v, typeof request === 'number' ? uuid(request) : request, typeof client === 'number' ? hash(client) : client, JSON.stringify(body), bucket]);
}
async function rate(scope, subject) { return scalar('select public.consume_api_rate($1,$2)', [scope, subject]); }
async function rows() { return scalar('select count(*)::int from public.public_survey_responses'); }
async function counters() { return (await db.query('select * from public.api_rate_buckets order by scope,subject')).rows; }

(async () => {
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls; create role outsider;
    grant usage on schema public to anon,authenticated,service_role,outsider;
    alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
    create table public.community_support(marker text); insert into public.community_support values ('preserve');
    create table public.site_signal_days(marker text); insert into public.site_signal_days values ('preserve');
  `);
  await db.exec(read('2026100301_api_rate_boundaries.sql'));
  const sql = read('2026100601_public_survey.sql');
  await check('migration applies twice, retaining unrelated fixtures', async () => {
    await db.exec(sql); await db.exec(sql);
    assert.equal(await scalar('select marker from public.community_support'), 'preserve');
    assert.equal(await scalar('select marker from public.site_signal_days'), 'preserve');
    assert.equal(await scalar("select relrowsecurity from pg_class where oid='public.public_survey_responses'::regclass"), true);
    assert.equal(await scalar("select count(*)::int from pg_policies where tablename='public_survey_responses'"), 0);
  });
  for (const actor of ['anon','authenticated','outsider']) {
    await role(actor);
    await check(actor + ' cannot read, write or invoke survey RPC', async () => {
      for (const q of ['select * from public.public_survey_responses',
        "insert into public.public_survey_responses(survey_version) values ('2026-10-v1')",
        'update public.public_survey_responses set answers=null', 'delete from public.public_survey_responses']) {
        await assert.rejects(() => db.query(q), e => e.code === '42501');
      }
      await assert.rejects(() => submit(), e => e.code === '42501');
      await assert.rejects(() => rate('survey',hash(1)), e => e.code === '42501');
    });
  }
  await role('service_role');
  await check('service can submit and inspect; direct writes remain RPC-only', async () => {
    assert.deepEqual(await submit(), {ok:true,duplicate:false});
    assert.equal(await rows(), 1);
    await assert.rejects(() => db.query('delete from public.public_survey_responses'), e => e.code === '42501');
    await assert.rejects(() => db.query('update public.public_survey_responses set answers=null'), e => e.code === '42501');
    await assert.rejects(() => db.query("insert into public.public_survey_responses(survey_version) values ('2026-10-v1')"), e => e.code === '42501');
  });
  await check('stored fields exclude raw identity/IP and request time', async () => {
    const names = (await db.query("select column_name from information_schema.columns where table_schema='public' and table_name='public_survey_responses'")).rows.map(r=>r.column_name).sort();
    assert.deepEqual(names, ['answers','client_hash','created_at','request_id','survey_version']);
    const saved = (await db.query('select * from public.public_survey_responses')).rows[0];
    assert.deepEqual(saved.answers.features, ['map','report']);
    assert.ok(saved.created_at);
  });
  await check('same request/answers replays without consuming quota', async () => {
    const before = await counters();
    assert.deepEqual(await submit(), {ok:true,duplicate:true});
    assert.deepEqual(await submit(1,1,{...answers,features:['map','report']}), {ok:true,duplicate:true});
    assert.deepEqual(await counters(), before); assert.equal(await rows(),1);
  });
  await check('same request changed answer/client conflicts; same client new request limited', async () => {
    const before = await counters();
    assert.deepEqual(await submit(1,1,{...answers,comment:'changed'}), {error:'idempotency_conflict'});
    assert.deepEqual(await submit(1,2), {error:'idempotency_conflict'});
    assert.deepEqual(await submit(2,1), {error:'already_submitted'});
    assert.deepEqual(await counters(), before); assert.equal(await rows(),1);
  });
  await check('malformed direct service inputs are rejected before any writes', async () => {
    const bad = [null, [], {}, {...answers, extra:'not allowed'}, {...answers, purpose:[]},
      {...answers, purpose:'invalid'}, {...answers, outcome:true}, {...answers, discovery:1},
      {...answers, features:null}, {...answers, features:['not_used','map']},
      {...answers, features:['map','map']}, {...answers, features:[{}]}, {...answers, features:['invalid']},
      {...answers, comment:null}, {...answers, comment:'🙂'.repeat(501)}, {...empty,comment:' \t\n'}];
    const before = await counters();
    for (const body of bad) assert.deepEqual(await submit(3,3,body), {error:'invalid_payload'});
    for (const params of [[null,3,answers], [3,null,answers], [3,'raw-browser-id',answers],
      [3,3,answers,'raw-ip'], [3,3,answers,hash(3),'future-version']]) {
      assert.deepEqual(await submit(...params), {error:'invalid_payload'});
    }
    assert.deepEqual(await counters(), before); assert.equal(await rows(),1);
  });
  await check('single optional answer and 500 Unicode code points accepted', async () => {
    const choices = [{purpose:'browse'}, {features:['not_used']}, {outcome:'not_yet'},
      {discovery:'unknown'}, {comment:'🙂'.repeat(500)}];
    for (let i=0; i<choices.length; i++) {
      assert.deepEqual(await submit(10+i,10+i,{...empty,...choices[i]},hash(10+i)), {ok:true,duplicate:false});
    }
  });
  await check('competing repeated requests create exactly one row', async () => {
    const before = await rows();
    const results = await Promise.all(Array.from({length:8},()=>submit(30,30,answers,hash(30))));
    assert.equal(results.filter(r=>r.ok && !r.duplicate).length,1);
    assert.equal(results.filter(r=>r.duplicate).length,7);
    assert.equal(await rows(),before+1);
  });
  await check('competing fresh requests from same browser accept exactly one', async () => {
    const before = await rows();
    const results = await Promise.all(Array.from({length:8},(_,i)=>submit(40+i,40,answers,hash(40))));
    assert.equal(results.filter(r=>r.ok).length,1);
    assert.equal(results.filter(r=>r.error==='already_submitted').length,7);
    assert.equal(await rows(),before+1);
  });
  await check('survey minute cap 10; 11th stores nothing and consumes no extra quota', async () => {
    for (let i=0;i<10;i++) assert.equal((await submit(100+i,100+i,answers,hash(100))).ok,true);
    const before = await counters(); const count = await rows();
    const blocked = await submit(111,111,answers,hash(100));
    assert.equal(blocked.error,'rate_limited'); assert.ok(blocked.retry_after_sec>=1);
    assert.deepEqual(await counters(),before); assert.equal(await rows(),count);
    assert.deepEqual(await submit(100,100,answers,hash(100)),{ok:true,duplicate:true});
  });
  await check('existing holdings/visitor limits and scope independence preserved', async () => {
    for (const [scope,cap] of [['holdings',80],['visitor_ping',30]]) {
      for (let i=0;i<cap;i++) assert.equal((await rate(scope,hash(150))).allowed,true);
      assert.equal((await rate(scope,hash(150))).allowed,false);
    }
    assert.equal((await submit(150,150,answers,hash(150))).ok,true);
  });
  await role();
  await check('new migration can reapply without losing survey answers', async () => {
    const count = await rows(); await db.exec(sql); assert.equal(await rows(),count);
  });
  await check('table constraints reject invalid direct owner writes', async () => {
    await assert.rejects(()=>db.query('insert into public.public_survey_responses values ($1,$2,$3,$4,now())',
      [version,uuid(500),hash(500),JSON.stringify(empty)]), e=>e.code==='23514');
    await assert.rejects(()=>db.query('insert into public.public_survey_responses values ($1,$2,$3,$4,now())',
      [version,uuid(500),hash(1),JSON.stringify(answers)]), e=>e.code==='23505');
  });
  await check('insert failure rolls back the shared rate mutation', async () => {
    await db.exec(`create function public.test_survey_fail() returns trigger language plpgsql as $$
      begin raise exception 'synthetic_insert_failure'; end $$;
      create trigger test_survey_fail before insert on public.public_survey_responses
      for each row execute function public.test_survey_fail();`);
    const before = await counters(); const count = await rows();
    await role('service_role');
    await assert.rejects(()=>submit(600,600,answers,hash(600)), e=>e.code==='P0001');
    assert.deepEqual(await counters(),before); assert.equal(await rows(),count);
    await role(); await db.exec('drop trigger test_survey_fail on public.public_survey_responses; drop function public.test_survey_fail();');
  });
  await check('version-lifetime dedup does not expire by age or reset at midnight', async () => {
    await db.exec("update public.public_survey_responses set created_at=now()-interval '365 days' where request_id='"+uuid(1)+"'");
    await role('service_role');
    assert.deepEqual(await submit(999,1),{error:'already_submitted'});
    assert.deepEqual(await submit(),{ok:true,duplicate:true});
  });
  await role();
  await db.exec("update public.api_rate_buckets set used=10000,window_start=to_timestamp(floor(extract(epoch from clock_timestamp())/3600)*3600) where scope='survey' and subject='global'");
  await role('service_role');
  await check('global ceiling denies fresh client but allows committed replay', async () => {
    const before=await rows();
    assert.equal((await submit(700,700,answers,hash(700))).error,'rate_limited');
    assert.equal(await rows(),before);
    assert.deepEqual(await submit(),{ok:true,duplicate:true});
  });
  console.log(`Survey SQL checks: ${passed}/${passed}`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>db.close());
