// Offline, synthetic DART continuation contract. No network, credentials or DB apply.
// PGLITE_MODULE=/existing/package/dist/index.cjs node tests/member_map_dart_continuation_sql.cjs
// Optional MEMBER_MAP_DART_SQL selects a reviewed local draft/final migration.
// Serialized lease races below do not prove production two-connection locking.
const { PGlite } = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const draft = path.resolve(root, process.env.MEMBER_MAP_DART_SQL || 'supabase/migrations/20261101075403_member_map_dart_continuation.sql');
const forward = path.resolve(root, process.env.MEMBER_MAP_DART_DATE_SQL || 'supabase/migrations/20261101115404_member_map_dart_reported_date.sql');
const sha = value => createHash('sha256').update(value).digest('hex');
const inputs = [
    'supabase/migrations/2026101201_member_map_refresh_checkpoint.sql',
    'supabase/migrations/2026102401_member_map_dart_catchup.sql', draft, forward,
    'api/collectors/member_map_listing_delta.py', 'api/collectors/member_map_live_refresh.py',
    'api/collectors/member_map_refresh_store.py', __filename,
].map(name => {
    const file = path.resolve(root, name), body = fs.readFileSync(file);
    return {path:file, bytes:body.length, lines:body.toString().split('\n').length - (body.at(-1) === 10 ? 1 : 0), sha256:sha(body)};
});
const baseSQL = fs.readFileSync(inputs[0].path, 'utf8');
const catchupSQL = fs.readFileSync(inputs[1].path, 'utf8');
const draftSQL = fs.readFileSync(draft, 'utf8');
const forwardSQL = fs.readFileSync(forward, 'utf8');
const A = '00000000-0000-4000-8000-000000000001';
const B = '00000000-0000-4000-8000-000000000002';
const copy = value => structuredClone(value);
const cases = [];
const check = (name, run) => cases.push({name, run});
let db, fixtures, activationWitness, passed = 0;
const rows = async (sql, args = []) => (await db.query(sql, args)).rows;
const value = async (sql, args = []) => (await rows(sql, args))[0].v;
async function role(name = '') { await db.exec('RESET ROLE'); if (name) await db.exec('SET ROLE ' + name); }
async function owner(sql, args = []) {
    await role(); try { return await rows(sql, args); } finally { await role('service_role'); }
}
const snapshot = async (source = 'DART') => (await rows('SELECT * FROM public.member_map_refresh_checkpoint WHERE source=$1', [source]))[0];
const claim = (who = A, revision = -1, budget = 10) => value('SELECT public.member_map_refresh_claim_v2($1,$2,$3,$4) v', ['DART',who,budget,revision]);
const renew = (who, generation) => value('SELECT public.member_map_refresh_renew($1,$2,$3) v', ['DART',who,generation]);
const legacyClaim = source => value('SELECT public.member_map_refresh_claim($1,$2,$3) v', [source,A,source === 'DART' ? 10 : 0]);
const legacySave = (source, c, state) => value('SELECT public.member_map_refresh_save($1,$2,$3,$4,$5::jsonb) v', [source,A,c.generation,c.revision,JSON.stringify(state)]);
const save = (c, step, who = A) => value('SELECT public.member_map_refresh_save_v2($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7) v',
    ['DART',who,c.generation,c.revision,JSON.stringify(step.state),JSON.stringify(step.pages),step.catalog]);
async function reset() {
    await owner("UPDATE public.member_map_refresh_checkpoint SET state='{}',dart_checkpoint=null,revision=0,feed_revision=0,lease_owner=null,lease_generation=0,lease_until=null,request_day=null,requests_reserved=0,quota_blocked_day=null");
    // Synthetic prior legacy success is a fixture, never an operational cursor reset.
    await owner("UPDATE public.member_map_refresh_checkpoint SET state=$1::jsonb,revision=1,feed_revision=1 WHERE source='DART'", [JSON.stringify(fixtures.initial)]);
}
async function drive(steps, count = steps.length) {
    for (const step of steps.slice(0, count)) {
        const c = await claim(); assert.equal(c.status, 'claimed');
        assert.equal((await save(c, step)).status, 'saved');
        const stored = await snapshot();
        assert.deepEqual(stored.state, step.state);
        assert.deepEqual(stored.dart_checkpoint, step.checkpoint);
    }
}
async function rejected(step, c = null) {
    c = c || await claim(); const before = await snapshot();
    await assert.rejects(() => save(c, step), e => ['22023','P0001','23514'].includes(e.code));
    assert.deepEqual(await snapshot(), before, 'failed save changed retained state/evidence/lease');
}
async function helper(name, ...args) {
    return (await owner(`SELECT public.${name}(${args.map((_,i) => '$'+(i+1)+'::jsonb').join(',')}) v`, args.map(JSON.stringify)))[0].v;
}
async function validBundle(state, cp) {
    return (await owner('SELECT public.member_map_refresh_v2_valid($1,$2::jsonb,$3::jsonb) v', ['DART',JSON.stringify(state),JSON.stringify(cp)]))[0].v;
}

function loadFixtures(clock) {
    // Real collector -> real transition -> real apply_result. Only the fixed
    // public-list transport is synthetic, and socket access is forbidden.
    return JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', String.raw`
import json,sys,socket,urllib.request
from copy import deepcopy
from datetime import datetime,timedelta,timezone
def forbidden(*a,**kw): raise AssertionError('offline harness forbids network')
socket.socket.connect=forbidden
urllib.request.urlopen=forbidden
from api.collectors import member_map_listing_delta as d
from api.collectors.member_map_live_refresh import apply_result
from api.collectors.member_map_refresh_store import validate_state,validate_dart_bundle
now=datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))
kst=timezone(timedelta(hours=9)); today=now.astimezone(kst).date(); history=today-timedelta(days=2)
# Keep synthetic attempts on SQL's current KST day and never in the future.
# Near midnight compress the simulated window, not the production SQL guards.
midnight=datetime.combine(today,datetime.min.time(),tzinfo=kst)
window=min(timedelta(seconds=1200),now-midnight)
def tick_before(seconds): return (now-window*(seconds/1200)).isoformat()
old=datetime.combine(history,datetime.min.time(),tzinfo=kst)+timedelta(hours=1)
stamp=old.isoformat(); day=history.isoformat(); prefix=history.strftime('%Y%m%d')
cursor={'source':'DART','through_date':day,'checked_at':stamp,'ids':['DART:'+prefix+f'{i:06d}' for i in range(1,996)]}
initial=apply_result('DART',{}, {'status':'success','complete':True,'cursor':cursor,'requests':1,'records':[],
 'coverage':{'pages_succeeded':1,'listing_records':0,'total_pages':0,'total_records':0,'whole_market_coverage':False,'raw_body_checked':False,'bounded':True}},stamp)
validate_state('DART',initial)
universe={'123456':'Synthetic Issuer'}
def run(mapped=True,mode='stable'):
 prior=deepcopy(initial); cp=None; steps=[]
 for index in range(8 if mode=='stable' else (2 if mode in ('guard','empty','quota') else 4)):
  tick=tick_before(1200-index*130)
  calls=[]
  def transport(endpoint,**kw):
   assert endpoint==d.DART_LIST
   p=kw['params']; assert 'corp_cls' not in p and 'corp_code' not in p
   assert p['bgn_de']==p['end_de'] and p['page_count']=='100'
   assert kw['max_bytes']==2*1024*1024
   page=int(p['page_no']); calls.append(page)
   if mode=='quota' and index==1: return b'{"status":"020"}'
   total=0 if mode=='empty' or p['bgn_de']!=prefix else 1062
   if not total: return b'{"status":"013"}'
   entries=[{'rcept_no':prefix+f'{i:06d}','rcept_dt':prefix,'stock_code':'123456' if mapped else '',
     'report_nm':('Changed title' if (mode=='guard' and index==1 and i==1) or (mode=='middle' and index>=2 and i==501) else 'Synthetic filing'),
     'flr_nm':'Synthetic Issuer'} for i in range((page-1)*100+1,min(page*100,total)+1)]
   return json.dumps({'status':'000','page_no':page,'page_count':100,'total_count':total,'total_page':11,'list':entries}).encode()
  result=d.collect_dart_continuation(universe,prior['feed'],prior.get('cursor'),tick,'synthetic-not-a-real-key',cp,transport=transport)
  state=apply_result('DART',prior,result,tick)
  validate_state('DART',state);validate_dart_bundle(state,result['dart_checkpoint'])
  steps.append({'state':state,'pages':result['dart_pages'],'catalog':result['dart_catalog'],
    'checkpoint':result['dart_checkpoint'],'sealed':result['dart_sealed'],'calls':calls})
  prior=deepcopy(state);cp=deepcopy(result['dart_checkpoint'])
 return steps
def receipt_resume():
 prior=deepcopy(initial); cp=None; steps=[]
 oldprefix=(history-timedelta(days=1)).strftime('%Y%m%d')
 stable=run(False)[0]
 first_pages=stable['pages'][:9]
 cp=d.dart_replay_pages(None,prior['cursor'],stable['state']['last_attempt_at'],stable['catalog'],first_pages)[0]
 seed=deepcopy(stable['state']);seed.update(error='incomplete_unique_records',requests=10)
 seed['coverage'].update(pages_succeeded=9,listing_records=900)
 prior=deepcopy(seed)
 for index in range(7):
  tick=tick_before(1000-index*130);calls=[]
  def transport(endpoint,**kw):
   assert endpoint==d.DART_LIST
   p=kw['params'];page=int(p['page_no']);calls.append(page)
   assert p['bgn_de']==p['end_de'] and p['page_count']=='100'
   if p['bgn_de']!=prefix:return b'{"status":"013"}'
   entries=[{'rcept_no':(oldprefix if 901<=i<=907 else prefix)+f'{i:06d}',
      'rcept_dt':prefix,'stock_code':'','report_nm':'Synthetic filing','flr_nm':'Synthetic Issuer'}
      for i in range((page-1)*100+1,min(page*100,1062)+1)]
   return json.dumps({'status':'000','page_no':page,'page_count':100,'total_count':1062,'total_page':11,'list':entries}).encode()
  result=d.collect_dart_continuation(universe,prior['feed'],prior['cursor'],tick,'synthetic',cp,transport=transport)
  state=apply_result('DART',prior,result,tick);validate_state('DART',state);validate_dart_bundle(state,result['dart_checkpoint'])
  steps.append({'state':state,'pages':result['dart_pages'],'catalog':result['dart_catalog'],
   'checkpoint':result['dart_checkpoint'],'sealed':result['dart_sealed'],'calls':calls})
  prior=deepcopy(state);cp=deepcopy(result['dart_checkpoint'])
 return {'seed':seed,'checkpoint':d.dart_replay_pages(None,initial['cursor'],seed['last_attempt_at'],stable['catalog'],first_pages)[0],
   'catalog':stable['catalog'],'steps':steps}

def bootstrap():
 prior={};cp=None;steps=[]
 for index in range(4):
  tick=tick_before(600-index*130)
  result=d.collect_dart_continuation(universe,prior.get('feed',{'items':[]}),prior.get('cursor'),tick,
   'synthetic-not-a-real-key',cp,transport=lambda *a,**kw:b'{"status":"013"}')
  state=apply_result('DART',prior,result,tick)
  validate_state('DART',state);validate_dart_bundle(state,result['dart_checkpoint'])
  steps.append({'state':state,'pages':result['dart_pages'],'catalog':result['dart_catalog'],
    'checkpoint':result['dart_checkpoint'],'sealed':result['dart_sealed']})
  prior=deepcopy(state);cp=deepcopy(result['dart_checkpoint'])
 return steps
other_stamp=(now-timedelta(seconds=300)).isoformat()
atom=f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>8-K - Public Issuer (1) (Filer)</title><category term="8-K"/><id>x?accession-number=0000000001-26-000001</id><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/filing.htm"/><updated>{other_stamp}</updated></entry></feed>'''.encode()
sec_result=d.collect_sec_delta({'1':[{'ticker':'PUB','name':'Public Issuer'}]},{'items':[]},None,(now-timedelta(seconds=300)).isoformat(),transport=lambda *a,**k:atom)
sec=apply_result('SEC',{},sec_result,(now-timedelta(seconds=300)).isoformat())
news=apply_result('news',{}, {'status':'partial','complete':False,'error':'per-feed-completeness-unavailable','requests':None,
 'feed':{'headlines':[{'title':'Synthetic public story','source':'Public News','link':'https://example.com/public','time':other_stamp}],'bloomberg_google_headlines':[],'us_headlines':[]},
 'coverage':{'accepted':1,'rejected':0,'whole_market_coverage':False,'all_feeds_verified':False}},other_stamp)
validate_state('SEC',sec)
# News URL Python validator has an optional module absent in this worktree.
# Its actual apply_result output is still checked by the unchanged SQL below.
print(json.dumps({'initial':initial,'mapped':run(),'unmapped':run(False),'guard':run(mode='guard'),
 'middle':run(mode='middle'),'empty':run(mode='empty'),'quota':run(mode='quota'),'bootstrap':bootstrap(),
 'SEC':sec,'news':news,'today':today.isoformat(),'receipt_resume':receipt_resume()}))
`,clock], {cwd:root, env:{PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'}, maxBuffer:32*1024*1024}).toString());
}

check('forward migration preserves every source row, live legacy pending and function ACL bytes', async () => {
    assert.deepEqual(activationWitness.after,activationWitness.before);
    assert.deepEqual(activationWitness.afterACL,activationWitness.beforeACL);
    const dart=activationWitness.after.find(r=>r.source==='DART');
    assert.equal(dart.dart_checkpoint.pending.next_page,10);
    assert.equal(Object.keys(dart.dart_checkpoint.pending.rows).length,900);
});
check('fixture clocks preserve KST dates; SQL rejects 119-second cadence and accepts 120 seconds', async () => {
    for(const clock of ['2026-11-01T01:00:00Z','2026-11-01T14:59:00Z',
        '2026-11-01T15:00:00Z','2026-11-01T15:03:00Z','2026-11-01T15:05:04Z','2026-11-01T16:00:00Z']) {
        // These boundary projections test collector dates, not RPC eligibility:
        // a compressed midnight fixture can legitimately be too recent to claim.
        const sample=loadFixtures(clock);
        for(const steps of [sample.mapped,sample.unmapped,sample.receipt_resume.steps,sample.bootstrap]) {
            let previous=-Infinity;
            for(const step of steps) {
                const attempt=Date.parse(step.state.last_attempt_at);
                assert.ok(attempt>=previous && attempt<=Date.parse(clock),clock);
                assert.equal(new Date(attempt+9*3600000).toISOString().slice(0,10),sample.today,clock);
                previous=attempt;
            }
            assert.ok(steps.slice(0,-1).every(step=>step.state.status==='partial'),clock);
            assert.equal(steps.at(-1).state.status,'success',clock);
            assert.equal(steps.at(-1).state.cursor.through_date,sample.today,clock);
        }
    }
    const clock=Number(await value('SELECT extract(epoch FROM clock_timestamp())::float8 v'))*1000;
    for(const steps of [fixtures.mapped,fixtures.unmapped,fixtures.receipt_resume.steps,fixtures.bootstrap])
        assert.ok(steps.every(step=>clock-Date.parse(step.state.last_attempt_at)>=120000),'RPC fixtures must be due');
    for(const age of [119,120]) {
        const recent=copy(fixtures.mapped[0]);
        recent.state.last_attempt_at=new Date(clock-age*1000).toISOString();
        recent.state.health.age_seconds=(Date.parse(recent.state.last_attempt_at)-Date.parse(recent.state.last_success_at))/1000;
        await owner("UPDATE public.member_map_refresh_checkpoint SET state=$1::jsonb,dart_checkpoint=$2::jsonb WHERE source='DART'",
            [JSON.stringify(recent.state),JSON.stringify(recent.checkpoint)]);
        const before=await snapshot(), result=await claim();
        if(age===119) {
            assert.deepEqual(result,{status:'not-due',retry_after_seconds:1});
            assert.deepEqual(await snapshot(),before,'cadence rejection changed state or reservation');
        } else assert.equal(result.status,'claimed');
    }
});
check('legacy 900-row pending resumes with seven differing receipt prefixes through verify and current date', async () => {
    const fixture=fixtures.receipt_resume;
    await owner("UPDATE public.member_map_refresh_checkpoint SET state=$1::jsonb,dart_checkpoint=$2::jsonb WHERE source='DART'",
        [JSON.stringify(fixture.seed),JSON.stringify(fixture.checkpoint)]);
    assert.deepEqual(fixture.steps[0].calls,[1,9,10,11]);
    assert.equal(fixture.steps[0].checkpoint.pending.phase,'verify');
    for(const [index,step] of fixture.steps.entries()) {
        assert.ok(step.calls.length<=10);assert.ok(step.state.coverage.listing_records<=1000);
        assert.equal(step.state.error,null);
        const c=await claim();assert.equal(c.status,'claimed');assert.equal((await save(c,step)).status,'saved');
        const stored=await snapshot();assert.deepEqual(stored.state,step.state);assert.deepEqual(stored.dart_checkpoint,step.checkpoint);
        if(index<fixture.steps.length-1) assert.equal(stored.state.last_success_at,fixture.seed.last_success_at);
    }
    const historical=fixture.steps[2];assert.equal(historical.sealed,true);
    const ids=historical.checkpoint.committed.ids, prefix=historical.checkpoint.committed.date.replaceAll('-','');
    assert.equal(ids.filter(id=>id.slice(5,13)!==prefix).length,7);
    // Legacy boundary IDs are preserved, including IDs not present in new sweeps.
    assert.ok(fixture.seed.cursor.ids.every(id=>ids.includes(id)));
    const final=await snapshot();assert.equal(final.state.status,'success');
    assert.equal(final.state.cursor.through_date,fixtures.today);
});
check('old nonempty proof lacks queried_date and cannot save or advance after activation', async () => {
    const step=copy(fixtures.mapped[0]);for(const page of step.pages) delete page.queried_date;
    await rejected(step);
});
check('altered valid digest in a resumed guard invalidates sweep without advancing committed success', async () => {
    await drive(fixtures.mapped,1);
    const step=copy(fixtures.mapped[1]);step.pages=step.pages.slice(0,1);
    step.pages[0].rows[0][1]='f'.repeat(64);
    const r=(await owner('SELECT public.member_map_dart_replay($1::jsonb,$2::jsonb,$3,$4,$5::jsonb) v',
        [JSON.stringify(fixtures.mapped[0].checkpoint),JSON.stringify(fixtures.initial.cursor),
         step.state.last_attempt_at,step.catalog,JSON.stringify(step.pages)]))[0].v;
    assert.equal(r.error,'pagination_changed');assert.equal(r.sealed,false);
    assert.deepEqual(r.checkpoint.committed,fixtures.mapped[0].checkpoint.committed);
    // A caller cannot submit the original expected state while concealing that reset.
    await rejected(step);
});
check('forward migration rejects unexpected helper grant and rolls back definitions without touching rows', async () => {
    const isolated=new PGlite();
    try {
        await isolated.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE ROLE unrelated_service; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;');
        await isolated.exec(baseSQL);await isolated.exec(catchupSQL);await isolated.exec(draftSQL);
        await isolated.exec('GRANT EXECUTE ON FUNCTION public.member_map_dart_replay(jsonb,jsonb,text,text,jsonb) TO unrelated_service');
        const before=(await isolated.query("SELECT prosrc,proacl FROM pg_proc WHERE proname='member_map_dart_replay'")).rows;
        await assert.rejects(()=>isolated.exec(forwardSQL),/refresh-reported-date-unsafe-grants/);
        await isolated.exec('ROLLBACK');
        assert.deepEqual((await isolated.query("SELECT prosrc,proacl FROM pg_proc WHERE proname='member_map_dart_replay'")).rows,before);
    } finally {await isolated.close();}
});

check('schema/ACL: exactly three sources, RLS, five public RPC grants, private helpers inaccessible', async () => {
    assert.deepEqual((await rows('SELECT source FROM public.member_map_refresh_checkpoint ORDER BY source')).map(x=>x.source), ['DART','SEC','news']);
    const flags = await rows("SELECT relrowsecurity FROM pg_class WHERE oid='public.member_map_refresh_checkpoint'::regclass");
    assert.equal(flags[0].relrowsecurity,true);
    const functions = await rows(`SELECT p.proname,p.prosecdef,p.proconfig,
        has_function_privilege('service_role',p.oid,'EXECUTE') service,
        has_function_privilege('anon',p.oid,'EXECUTE') anon,
        has_function_privilege('authenticated',p.oid,'EXECUTE') authenticated
        FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid
        WHERE n.nspname='public' AND (p.proname LIKE 'member_map_refresh_%' OR p.proname LIKE 'member_map_dart_%')`);
    const allowed=['member_map_refresh_claim','member_map_refresh_save','member_map_refresh_renew','member_map_refresh_claim_v2','member_map_refresh_save_v2'];
    assert.deepEqual(functions.filter(f=>f.service).map(f=>f.proname).sort(),allowed.sort());
    assert.ok(functions.every(f=>!f.anon && !f.authenticated && f.proconfig.includes('search_path=""')));
    assert.ok(functions.filter(f=>f.service).every(f=>f.prosecdef));
});
for (const denied of ['anon','authenticated']) check(`${denied}: table and continuation/legacy RPC access denied`, async () => {
    await role(denied);
    for (const sql of ['SELECT * FROM public.member_map_refresh_checkpoint',
        `SELECT public.member_map_refresh_claim_v2('DART','${A}',10)`,
        `SELECT public.member_map_refresh_save_v2('DART','${A}',1,0,'{}','[]','${'a'.repeat(64)}')`,
        `SELECT public.member_map_refresh_claim('SEC','${A}',0)`,
        `SELECT public.member_map_refresh_renew('DART','${A}',1)`,
        "SELECT public.member_map_dart_checkpoint_valid(null)"])
        await assert.rejects(()=>db.exec(sql),e=>e.code==='42501');
});
check('service role cannot mutate table, call internal validators or preserved v1 implementations', async () => {
    for (const sql of ["UPDATE public.member_map_refresh_checkpoint SET revision=revision+1",'DELETE FROM public.member_map_refresh_checkpoint',
        'TRUNCATE public.member_map_refresh_checkpoint',"SELECT public.member_map_dart_checkpoint_valid(null)",
        `SELECT public.member_map_refresh_claim_v1_private('DART','${A}',10)`,
        `SELECT public.member_map_refresh_save_v1_private('DART','${A}',1,0,'{}')`])
        await assert.rejects(()=>db.exec(sql),e=>e.code==='42501');
});
check('old DART writers fenced before lease/reservation/state changes, even before first v2 save', async () => {
    const before=await snapshot();
    await assert.rejects(()=>legacyClaim('DART'),e=>e.code==='22023' && e.message==='refresh-writer-version-required');
    await assert.rejects(()=>legacySave('DART',{generation:1,revision:1},fixtures.initial),e=>e.code==='22023' && e.message==='refresh-writer-version-required');
    assert.deepEqual(await snapshot(),before);
});
check('SEC/news retain original legacy RPC/state behavior and never carry DART evidence', async () => {
    for (const source of ['SEC','news']) {
        assert.equal((await owner('SELECT public.member_map_refresh_state_valid($1,$2::jsonb) v',[source,JSON.stringify(fixtures[source])]))[0].v,true,source+' fixture rejected by baseline SQL');
        const c=await legacyClaim(source);assert.equal(c.status,'claimed');
        assert.equal((await legacySave(source,c,fixtures[source])).status,'saved');
        assert.deepEqual((await snapshot(source)).state,fixtures[source]);
        assert.equal((await snapshot(source)).dart_checkpoint,null);
        const before=await snapshot(source);
        await assert.rejects(()=>owner('UPDATE public.member_map_refresh_checkpoint SET dart_checkpoint=$1::jsonb WHERE source=$2',
            [JSON.stringify(fixtures.mapped[0].checkpoint),source]),e=>e.code==='23514');
        assert.deepEqual(await snapshot(source),before,'other-source checkpoint accepted DART evidence');
        assert.equal(await validBundle(fixtures[source],null),false); // DART validator rejects other-source state.
        await assert.rejects(()=>value('SELECT public.member_map_refresh_claim_v2($1,$2,10) v',[source,A]),e=>e.code==='22023');
    }
});
check('migration refuses inherited extra-role function grants and rolls back atomically', async () => {
    const isolated=new PGlite();
    try {
        await isolated.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE ROLE unrelated_service; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;');
        await isolated.exec(baseSQL);await isolated.exec(catchupSQL);
        await isolated.exec('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO unrelated_service');
        await assert.rejects(()=>isolated.exec(draftSQL),/refresh-continuation-unsafe-grants/);
        await isolated.exec('ROLLBACK');
        assert.equal((await isolated.query("SELECT count(*)::int n FROM information_schema.columns WHERE table_schema='public' AND table_name='member_map_refresh_checkpoint' AND column_name='dart_checkpoint'")).rows[0].n,0);
        assert.equal((await isolated.query("SELECT count(*)::int n FROM pg_proc WHERE proname='member_map_refresh_claim_v1_private'")).rows[0].n,0);
        assert.equal((await isolated.query("SELECT count(*)::int n FROM public.member_map_refresh_checkpoint")).rows[0].n,3);
    } finally {await isolated.close();}
});
check('lease owner/generation and save revision CAS fail without mutation; renewal does not reserve', async () => {
    const c=await claim();const before=await snapshot();
    assert.deepEqual(await claim(B),{status:'busy'});
    const again=await claim(A,c.revision);assert.equal(again.status,'already-claimed');assert.equal(again.state,null);
    assert.equal(again.lease_until,c.lease_until);assert.equal(again.requests_reserved,10);
    assert.deepEqual(await save(c,fixtures.mapped[0],B),{status:'lease-lost'});
    assert.deepEqual(await save({...c,generation:c.generation+1},fixtures.mapped[0]),{status:'lease-lost'});
    assert.deepEqual(await save({...c,revision:c.revision+1},fixtures.mapped[0]),{status:'revision-conflict'});
    assert.deepEqual(await snapshot(),before);
    assert.equal((await renew(A,c.generation)).status,'renewed');assert.equal((await snapshot()).requests_reserved,10);
    await owner("UPDATE public.member_map_refresh_checkpoint SET lease_until=clock_timestamp()-interval '1 second' WHERE source='DART'");
    const expired=await snapshot();assert.deepEqual(await save(c,fixtures.mapped[0]),{status:'lease-lost'});assert.deepEqual(await snapshot(),expired);
    assert.equal((await claim(B)).generation,c.generation+1);
});
check('day cap 8000, exact ten reservation, no refund and old-day lease fence', async () => {
    for (const budget of [0,9,11,null]) await assert.rejects(()=>claim(A,-1,budget),e=>e.code==='22023');
    await owner("UPDATE public.member_map_refresh_checkpoint SET request_day=(clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date,requests_reserved=7990 WHERE source='DART'");
    const c=await claim();assert.equal(c.requests_reserved,8000);
    await owner("UPDATE public.member_map_refresh_checkpoint SET lease_until=clock_timestamp()-interval '1 second' WHERE source='DART'");
    const before=await snapshot();assert.deepEqual(await claim(B),{status:'budget-exhausted'});assert.deepEqual(await snapshot(),before);
    await reset();const next=await claim();
    await owner("UPDATE public.member_map_refresh_checkpoint SET request_day=request_day-1 WHERE source='DART'");
    const old=await snapshot();assert.deepEqual(await renew(A,next.generation),{status:'lease-lost'});
    assert.deepEqual(await save(next,fixtures.mapped[0]),{status:'lease-lost'});assert.deepEqual(await snapshot(),old);
});
for (const mode of ['mapped','unmapped']) check(`${mode}: Python/SQL 1062-page resume, two sweeps, historical seal, current-day-only success clock`, async () => {
    const steps=fixtures[mode], start=fixtures.initial.last_success_at;
    assert.deepEqual(steps.slice(0,4).map(s=>s.calls),[Array.from({length:10},(_,i)=>i+1),[1,10,11],Array.from({length:10},(_,i)=>i+1),[1,10,11]]);
    let previousFeedRevision=1;
    for (const [index,step] of steps.entries()) {
        assert.ok(step.calls.length<=10);assert.equal(step.state.requests,step.calls.length);
        const c=await claim();assert.equal(c.status,'claimed');
        assert.deepEqual(c.dart_checkpoint,index ? steps[index-1].checkpoint : null);
        const valid=await validBundle(step.state,step.checkpoint);
        if(!valid) console.error(JSON.stringify({mode,cycle:index+1,checkpoint_valid:await helper('member_map_dart_checkpoint_valid',step.checkpoint),
            legacy_state_valid:(await owner('SELECT public.member_map_refresh_state_valid($1,$2::jsonb) v',['DART',JSON.stringify(step.state)]))[0].v,
            checkpoint_checks:(await owner(`SELECT
                public.member_map_dart_map_valid($1::jsonb#>'{pending,rows}') rows_valid,
                public.member_map_dart_map_valid($1::jsonb#>'{pending,baseline}') baseline_valid,
                public.member_map_dart_map_valid($1::jsonb#>'{pending,first}') first_valid,
                public.member_map_dart_map_valid($1::jsonb#>'{pending,last}') last_valid,
                (SELECT count(*)::int FROM jsonb_object_keys($1::jsonb#>'{pending,rows}')) row_count,
                (SELECT count(*)::int FROM jsonb_object_keys($1::jsonb#>'{pending,first}')) first_count,
                (SELECT count(*)::int FROM jsonb_object_keys($1::jsonb#>'{pending,last}')) last_count,
                ($1::jsonb#>'{pending,rows}') @> ($1::jsonb#>'{pending,first}') first_subset,
                ($1::jsonb#>'{pending,rows}') @> ($1::jsonb#>'{pending,last}') last_subset,
                $1::jsonb#>>'{pending,next_page}' next_page,$1::jsonb#>>'{pending,total}' total`,[JSON.stringify(step.checkpoint)]))[0],
            health:step.state.health,last_attempt:step.state.last_attempt_at,last_success:step.state.last_success_at}));
        assert.equal(valid,true,`${mode} cycle ${index+1}: Python bundle rejected by SQL validator`);
        let saved;
        try {saved=await save(c,step);} catch(error) {error.message=`${mode} cycle ${index+1}: ${error.message}`;throw error;}
        assert.equal(saved.status,'saved');
        const stored=await snapshot();assert.deepEqual(stored.state,step.state);assert.deepEqual(stored.dart_checkpoint,step.checkpoint);
        assert.equal(stored.revision,index+2);assert.equal(stored.requests_reserved,(index+1)*10);
        if (mode==='unmapped') assert.equal(stored.feed_revision,previousFeedRevision);
        previousFeedRevision=stored.feed_revision;
        assert.equal(stored.state.last_success_at,index===steps.length-1 ? step.state.last_attempt_at : start);
        if(index<3) assert.deepEqual(stored.state.cursor,fixtures.initial.cursor);
        if(index===3) {
            assert.equal(step.sealed,true);assert.equal(step.state.status,'partial');
            assert.equal(step.checkpoint.pending,null);assert.equal(step.checkpoint.committed.ids.length,1062);
            assert.equal(step.state.cursor.id_count,1062);assert.equal(step.state.cursor.ids,undefined);
            assert.ok(fixtures.initial.cursor.ids.every(id=>step.checkpoint.committed.ids.includes(id)));
        }
        for (const group of stored.state.feed.items) assert.ok(group.disclosures.length<=8);
    }
    assert.equal(steps.at(-1).state.status,'success');assert.equal(steps.at(-1).state.cursor.through_date,fixtures.today);
    assert.equal(Boolean(steps[3].state.feed.items.length),mode==='mapped');
});
check('013 requires scan + verify and preserves legacy IDs; cannot advance success clock on historical date', async () => {
    await drive(fixtures.empty);
    const last=fixtures.empty.at(-1);assert.equal(last.sealed,true);assert.equal(last.state.status,'partial');
    assert.deepEqual(last.checkpoint.committed.ids,fixtures.initial.cursor.ids);
    assert.equal(last.state.last_success_at,fixtures.initial.last_success_at);
});
check('empty bootstrap saves partial with missing cursor/success, seals yesterday, then verifies today before success', async () => {
    await owner("UPDATE public.member_map_refresh_checkpoint SET state='{}',revision=0,feed_revision=0 WHERE source='DART'");
    const steps=fixtures.bootstrap;
    assert.equal(steps.length,4);
    for(const [index,step] of steps.entries()) {
        const c=await claim();assert.equal(c.status,'claimed');
        assert.deepEqual(c.state,index ? steps[index-1].state : {});
        assert.deepEqual(c.dart_checkpoint,index ? steps[index-1].checkpoint : null);
        assert.equal((await save(c,step)).status,'saved');
        const stored=await snapshot();assert.deepEqual(stored.state,step.state);assert.deepEqual(stored.dart_checkpoint,step.checkpoint);
        assert.equal(stored.revision,index+1);assert.equal(stored.requests_reserved,(index+1)*10);
        if(index===0) {assert.equal(stored.state.cursor,undefined);assert.equal(stored.dart_checkpoint.committed,null);}
        if(index<3) {assert.equal(stored.state.last_success_at,undefined);assert.deepEqual(stored.state.health,{status:'unknown',age_seconds:null});}
        if(index===1) {assert.equal(step.sealed,true);assert.equal(stored.state.status,'partial');assert.ok(stored.state.cursor.through_date<fixtures.today);}
        if(index===2) assert.equal(step.sealed,false);
    }
    const final=await snapshot();assert.equal(final.state.status,'success');assert.equal(final.state.cursor.through_date,fixtures.today);
    assert.equal(final.state.last_success_at,steps[3].state.last_attempt_at);assert.deepEqual(final.state.health,{status:'on-time',age_seconds:0});
});
for(const mode of ['guard','middle']) check(`${mode} same-count changed row resets pending safely instead of sealing`, async () => {
    await drive(fixtures[mode]);const last=fixtures[mode].at(-1);
    assert.equal(last.state.error,'pagination_changed');assert.equal(last.sealed,false);
    assert.deepEqual(last.state.cursor,fixtures.initial.cursor);
    assert.equal(last.checkpoint.pending.phase,'scan');assert.equal(last.checkpoint.pending.next_page,1);
    assert.deepEqual(last.checkpoint.committed.ids,fixtures.initial.cursor.ids);
});
check('020 keeps checkpoint and feed, consumes reservation and blocks only DART that day', async () => {
    await drive(fixtures.quota);const state=await snapshot();
    assert.equal(state.state.error,'dart-quota-exceeded');assert.deepEqual(state.dart_checkpoint,fixtures.quota[0].checkpoint);
    assert.deepEqual(state.state.feed,fixtures.quota[0].state.feed);assert.equal(state.requests_reserved,20);
    assert.deepEqual(await claim(B),{status:'quota-blocked'});
    assert.equal((await legacyClaim('SEC')).status,'claimed');assert.equal((await legacyClaim('news')).status,'claimed');
});
check('page/order/duplicate-ID/wrong-day proof and coverage mutations rejected atomically', async () => {
    assert.equal(await validBundle(fixtures.mapped[0].state,fixtures.mapped[0].checkpoint),true,'positive proof control rejected before mutation checks');
    const mutations=[s=>s.pages[0].page_no=2,s=>s.pages[0].page_no='1',s=>s.pages[0].rows.push(s.pages[0].rows[0]),
        s=>s.pages[0].rows[0][0]='DART:invalid',
        s=>s.pages[0].queried_date='2000-01-01',s=>delete s.pages[0].queried_date,
        s=>s.pages[0].queried_date=null,s=>s.pages[0].queried_date=20261030,s=>s.pages[0].rows[0][1]='not-a-digest',
        s=>s.pages.push(s.pages[0]),s=>s.state.coverage.listing_records--,s=>s.state.requests=11,
        s=>s.state.coverage.total_records++,s=>s.state.member_id=A];
    for(const mutate of mutations) {const s=copy(fixtures.mapped[0]);mutate(s);await rejected(s);}
});
check('SQL replay agrees with Python and accepts its own generated first-cycle checkpoint', async () => {
    const step=fixtures.mapped[0];
    const transition=(await owner('SELECT public.member_map_dart_replay($1::jsonb,$2::jsonb,$3,$4,$5::jsonb) v',
        [null,JSON.stringify(fixtures.initial.cursor),step.state.last_attempt_at,step.catalog,JSON.stringify(step.pages)]))[0].v;
    assert.deepEqual(transition.checkpoint,step.checkpoint);
    assert.equal(transition.sealed,false);
    assert.equal(await helper('member_map_dart_checkpoint_valid',transition.checkpoint),true,'SQL rejects its own replay checkpoint');
});
check('checkpoint/cursor strict version and inconsistent retained guard membership rejected', async () => {
    const step=fixtures.mapped[0];assert.equal(await helper('member_map_dart_checkpoint_valid',step.checkpoint),true);
    for(const mutate of [cp=>cp.version='2',cp=>cp.version=true,cp=>cp.pending.next_page='11',cp=>{
        const key=Object.keys(cp.pending.rows)[0], digest=cp.pending.rows[key];delete cp.pending.rows[key];cp.pending.rows['DART:20000101000001']=digest;
    }]) {const cp=copy(step.checkpoint);mutate(cp);assert.equal(await helper('member_map_dart_checkpoint_valid',cp),false);}
    const sealed=copy(fixtures.mapped[3]);sealed.state.cursor.version='2';assert.equal(await validBundle(sealed.state,sealed.checkpoint),false);
    await drive(fixtures.mapped,3);await rejected(sealed);
});
check('strict DART timestamps reject 24-hour/leap-second spellings in checkpoint and state facts', async () => {
    const step=fixtures.mapped[0], day=step.state.cursor.through_date;
    const previous=new Date(Date.parse(day+'T00:00:00Z')-86400000).toISOString().slice(0,10);
    for(const stamp of [previous+'T24:00:00Z',previous+'T23:59:60Z',day+'T00:60:00Z',day+'T00:00:00+24:00']) {
        assert.equal(await helper('member_map_dart_stamp_valid',stamp),false);
        for(const part of ['pending','committed']) {
            const cp=copy(step.checkpoint);cp[part][part==='pending' ? 'started_at' : 'checked_at']=stamp;
            assert.equal(await helper('member_map_dart_checkpoint_valid',cp),false);
        }
    }
    assert.equal(await helper('member_map_dart_stamp_valid',day+'T00:00:00.123456+09:00'),true);
    for(const layer of ['metadata','disclosure']) {
        const normal=copy(step), changed=copy(step);
        const set=(s,stamp)=>{if(layer==='metadata') s.state.feed._meta.generated_at=stamp;else s.state.feed.items[0].disclosures[0].observed_at=stamp;};
        set(normal,day+'T00:00:00Z');set(changed,previous+'T24:00:00Z');
        assert.equal(await validBundle(normal.state,normal.checkpoint),true,'normalized timestamp positive control');
        assert.equal((await owner('SELECT public.member_map_refresh_state_valid($1,$2::jsonb) v',['DART',JSON.stringify(changed.state)]))[0].v,true,'legacy validator normalizes the equivalent timestamp');
        assert.equal(await validBundle(changed.state,changed.checkpoint),false);
        await rejected(changed);
    }
    const badAttempt=copy(step);badAttempt.state.last_attempt_at=previous+'T24:00:00Z';await rejected(badAttempt);
});
check('unsealed/old-date full success and premature last_success advancement rejected', async () => {
    const premature=copy(fixtures.mapped[0]);premature.state.status='success';premature.state.last_success_at=premature.state.last_attempt_at;
    premature.state.health={status:'on-time',age_seconds:0};await rejected(premature);
    await reset();await drive(fixtures.mapped,3);
    const old=copy(fixtures.mapped[3]);old.state.status='success';old.state.last_success_at=old.state.last_attempt_at;
    old.state.health={status:'on-time',age_seconds:0};await rejected(old);
    const clock=copy(fixtures.mapped[3]);clock.state.last_success_at=clock.state.last_attempt_at;clock.state.health={status:'on-time',age_seconds:0};await rejected(clock);
});
check('aggregate 4MiB bound rejects two individually valid components without trimming IDs', async () => {
    const normal=copy(fixtures.mapped[3]), bigCP=copy(normal.checkpoint), day=normal.state.cursor.through_date.replaceAll('-','');
    bigCP.committed.ids=Array.from({length:85000},(_,i)=>'DART:'+day+String(i+1).padStart(6,'0'));
    const bigState=copy(normal.state), template=bigState.feed.items[0].disclosures[0];
    bigState.feed.items=Array.from({length:450},(_,g)=>({ticker:String(200000+g),name:'Synthetic Issuer',latest:template.date,
        disclosures:Array.from({length:8},(_,i)=>{const receipt=day+String(g*8+i+1).padStart(6,'0');return {...template,title:'x'.repeat(300),id:'DART:'+receipt,source_url:'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt};})}));
    bigState.feed._meta.count=450;bigState.feed._meta.disclosure_count=3600;
    const withCP=(state,cp)=>({...state,cursor:{...state.cursor,id_count:cp.committed.ids.length,ids_sha256:sha(cp.committed.ids.join('\n'))}});
    assert.equal(await helper('member_map_dart_checkpoint_valid',bigCP),true);
    assert.equal(await validBundle(bigState,normal.checkpoint),true,'large feed itself malformed');
    assert.equal(await validBundle(withCP(normal.state,bigCP),bigCP),true,'large ledger itself malformed');
    const combined=withCP(bigState,bigCP);
    const bytes=(await owner('SELECT octet_length($1::jsonb::text) state,octet_length($2::jsonb::text) checkpoint',[JSON.stringify(combined),JSON.stringify(bigCP)]))[0];
    assert.ok(bytes.state<4194304 && bytes.checkpoint<4194304 && bytes.state+bytes.checkpoint>4194304);
    assert.equal(await validBundle(combined,bigCP),false);
});

(async()=>{
    db=new PGlite();
    // Only this ephemeral, in-memory database has a synthetic clock. Production
    // SQL is loaded byte-for-byte below; cadence, lease and date guards still run.
    // Noon KST leaves the full 20-minute fixture window regardless of CI wall time.
    await db.exec(`CREATE OR REPLACE FUNCTION pg_catalog.clock_timestamp() RETURNS timestamptz
        LANGUAGE SQL VOLATILE AS $$ SELECT '2026-11-02T03:00:00Z'::timestamptz $$`);
    await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;');
    await db.exec(baseSQL);await db.exec(catchupSQL);
    const clock=new Date(Number(await value('SELECT extract(epoch FROM clock_timestamp())::float8 v'))*1000).toISOString();
    fixtures=loadFixtures(clock);
    // Exercise actual v1 adoption, then load the unmodified continuation SQL.
    await role('service_role');const legacy=await legacyClaim('DART');assert.equal((await legacySave('DART',legacy,fixtures.initial)).status,'saved');
    await role();await db.exec(draftSQL);
    const seed=fixtures.receipt_resume;
    await db.query("UPDATE public.member_map_refresh_checkpoint SET state=$1::jsonb,dart_checkpoint=$2::jsonb WHERE source='DART'",
        [JSON.stringify(seed.seed),JSON.stringify(seed.checkpoint)]);
    const before=await rows('SELECT * FROM public.member_map_refresh_checkpoint ORDER BY source');
    const beforeACL=await rows("SELECT oid,proacl FROM pg_proc WHERE proname LIKE 'member_map_%' ORDER BY oid");
    await db.exec(forwardSQL);
    activationWitness={before,after:await rows('SELECT * FROM public.member_map_refresh_checkpoint ORDER BY source'),
        beforeACL,afterACL:await rows("SELECT oid,proacl FROM pg_proc WHERE proname LIKE 'member_map_%' ORDER BY oid")};
    const failures=[];
    for(const item of cases) {
        await reset();await role('service_role');
        try {await item.run();passed++;console.log('PASS '+item.name);}
        catch(error) {failures.push({name:item.name,code:error.code || '',message:error.message});console.error('FAIL CASE '+item.name+': '+error.message);}
    }
    for(const input of inputs) assert.equal(sha(fs.readFileSync(input.path)),input.sha256,'input changed during run: '+input.path);
    console.log(JSON.stringify({passed,total:cases.length,failures,inputs,scope:'in-memory PGlite + synthetic Python transport; no production SQL/source request; serialized races only'}));
    await db.close();
    if(failures.length) process.exitCode=1;
})().catch(async error=>{
    console.error('FAIL '+(error.code || '')+' '+(error.stderr ? error.stderr.toString().slice(-2000) : error.message));
    console.error(JSON.stringify({passed,total:cases.length,inputs}));
    if(db) await db.close();process.exitCode=1;
});
