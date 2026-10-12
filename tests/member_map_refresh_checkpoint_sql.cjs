// Existing PGlite harness, in memory only. No credentials, AI, network or DB apply.
// PGLITE_MODULE=/existing/path/to/@electric-sql/pglite node tests/member_map_refresh_checkpoint_sql.cjs
// Serialized owner races do NOT attest to production two-session lock behavior.
const { PGlite } = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const sqlPath = path.join(__dirname, '../supabase/migrations/2026101201_member_map_refresh_checkpoint.sql');
const sql = fs.readFileSync(sqlPath, 'utf8');
const sha = text => createHash('sha256').update(text).digest('hex');
const sqlHash = sha(sql), testHash = sha(fs.readFileSync(__filename));
const A = '00000000-0000-4000-8000-000000000001';
const B = '00000000-0000-4000-8000-000000000002';
const cases = [];
const check = (name, run) => cases.push({ name, run });
const copy = value => structuredClone(value);
let db, fixtures, passed = 0;
const rows = async (statement, values = [], target = db) => (await target.query(statement, values)).rows;
async function role(name = '', target = db) {
    await target.exec('RESET ROLE');
    if (name) await target.exec('SET ROLE ' + name);
}
async function bootstrap(target, roles = true) {
    if (roles) await target.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
        GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;`);
    await target.exec(`CREATE TABLE public.original_schema_sentinel(id integer PRIMARY KEY, value text);
        INSERT INTO public.original_schema_sentinel VALUES(1,'retained');
        CREATE FUNCTION public.original_function_sentinel() RETURNS text LANGUAGE sql AS $$ SELECT 'retained'::text $$;`);
}
async function claim(source = 'DART', owner = A, budget = source === 'DART' ? 10 : 0, knownRevision = -1) {
    return (await rows('SELECT public.member_map_refresh_claim($1,$2,$3,$4) AS value', [source, owner, budget, knownRevision]))[0].value;
}
async function renew(source, owner, generation) {
    return (await rows('SELECT public.member_map_refresh_renew($1,$2,$3) AS value', [source, owner, generation]))[0].value;
}
async function save(source, owner, generation, revision, state) {
    return (await rows('SELECT public.member_map_refresh_save($1,$2,$3,$4,$5::jsonb) AS value',
        [source, owner, generation, revision, JSON.stringify(state)]))[0].value;
}
async function snapshot(source) {
    return (await rows('SELECT * FROM public.member_map_refresh_checkpoint WHERE source=$1', [source]))[0];
}
async function ownerExec(statement, values = []) {
    await role();
    try { return await rows(statement, values); } finally { await role('service_role'); }
}
async function expire(source) {
    await ownerExec("UPDATE public.member_map_refresh_checkpoint SET lease_until=clock_timestamp()-interval '1 second' WHERE source=$1", [source]);
}
async function invalid(state, source = 'DART') {
    const c = await claim(source);
    const before = await snapshot(source);
    await assert.rejects(() => save(source, A, c.generation, c.revision, state),
        e => e.code === '22023' && e.message === 'refresh-checkpoint-invalid-state');
    assert.deepEqual(await snapshot(source), before);
}
async function regression(state, source, c) {
    const before = await snapshot(source);
    await assert.rejects(() => save(source, A, c.generation, c.revision, state),
        e => e.code === '22023' && e.message === 'refresh-checkpoint-state-regression');
    assert.deepEqual(await snapshot(source), before);
}
async function seed(source = 'DART', state = fixtures[source]) {
    const c = await claim(source);
    assert.equal((await save(source, A, c.generation, c.revision, state)).status, 'saved');
    return state;
}

check('only three fixed rows; one table and exactly three granted RPCs', async () => {
    assert.deepEqual((await rows('SELECT source,state,revision FROM public.member_map_refresh_checkpoint ORDER BY source')).map(r => r.source), ['DART','SEC','news']);
    const table = await rows("SELECT relrowsecurity FROM pg_class WHERE oid='public.member_map_refresh_checkpoint'::regclass");
    assert.equal(table[0].relrowsecurity, true);
    assert.equal((await rows("SELECT count(*)::int n FROM pg_policy WHERE polrelid='public.member_map_refresh_checkpoint'::regclass"))[0].n, 0);
    const functions = await rows(`SELECT p.proname,p.prosecdef,p.proconfig,has_function_privilege('service_role',p.oid,'EXECUTE') granted
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'member_map_refresh_%' ORDER BY p.proname`);
    assert.equal(functions.length, 4);
    assert.equal(functions.filter(f => f.granted).length, 3);
    assert.ok(functions.every(f => f.proconfig.includes('search_path=""')));
    assert.ok(functions.filter(f => f.granted).every(f => f.prosecdef));
    await ownerExec("SELECT source FROM public.member_map_refresh_checkpoint");
    await assert.rejects(() => db.exec("SELECT public.member_map_refresh_state_valid('DART','{}')"), e => e.code === '42501');
});

for (const deniedRole of ['anon', 'authenticated']) check(`${deniedRole} runtime SELECT/DML/all RPCs denied`, async () => {
    await role(deniedRole);
    for (const statement of [
        'SELECT * FROM public.member_map_refresh_checkpoint',
        "INSERT INTO public.member_map_refresh_checkpoint(source) VALUES('other')",
        "UPDATE public.member_map_refresh_checkpoint SET state='{}'",
        'DELETE FROM public.member_map_refresh_checkpoint',
        'TRUNCATE public.member_map_refresh_checkpoint',
        `SELECT public.member_map_refresh_claim('SEC','${A}',0)`,
        `SELECT public.member_map_refresh_claim('SEC','${A}',0,0)`,
        `SELECT public.member_map_refresh_renew('SEC','${A}',1)`,
        `SELECT public.member_map_refresh_save('SEC','${A}',1,0,'{}')`,
        "SELECT public.member_map_refresh_state_valid('SEC','{}')",
    ]) await assert.rejects(() => db.exec(statement), e => e.code === '42501');
});

check('service role SELECT precise three sources; direct DML/TRUNCATE denied', async () => {
    assert.equal((await rows("SELECT source,state,revision FROM public.member_map_refresh_checkpoint WHERE source IN ('SEC','DART','news') LIMIT 3")).length, 3);
    for (const statement of ["INSERT INTO public.member_map_refresh_checkpoint(source) VALUES('other')",
        "UPDATE public.member_map_refresh_checkpoint SET revision=revision+1", 'DELETE FROM public.member_map_refresh_checkpoint',
        'TRUNCATE public.member_map_refresh_checkpoint']) await assert.rejects(() => db.exec(statement), e => e.code === '42501');
});

check('claim fields are bounded; UUID is identity; no owner/token returned', async () => {
    const c = await claim('SEC');
    assert.deepEqual(Object.keys(c).sort(), ['status','source','generation','revision','feed_revision','state','lease_until','request_day','requests_reserved','request_budget'].sort());
    assert.equal(c.status, 'claimed'); assert.equal(c.generation, 1); assert.equal(c.revision, 0);
    assert.deepEqual(c.state, {}); assert.equal(c.request_budget, 0);
    const remaining = new Date(c.lease_until) - Date.now();
    assert.ok(remaining > 290000 && remaining <= 300100);
});

check('ordered competing owners have one winner; same owner retry never extends/reserves', async () => {
    const first = await claim();
    assert.deepEqual(await claim('DART', B), {status:'busy'});
    const again = await claim();
    assert.equal(again.status, 'already-claimed');
    assert.equal(again.generation, first.generation); assert.equal(again.lease_until, first.lease_until);
    assert.equal(again.requests_reserved, 10);
    await expire('DART');
    const second = await claim('DART', B);
    assert.equal(second.generation, 2); assert.equal(second.requests_reserved, 20);
    assert.deepEqual(await claim(), {status:'busy'});
});

check('renew requires exact live owner/generation and does not reserve more', async () => {
    const c = await claim();
    assert.deepEqual(await renew('DART', B, c.generation), {status:'lease-lost'});
    assert.deepEqual(await renew('DART', A, c.generation + 1), {status:'lease-lost'});
    assert.equal((await renew('DART', A, c.generation)).status, 'renewed');
    assert.equal((await snapshot('DART')).requests_reserved, 10);
});

check('expired old owner cannot renew/save even before another owner acquires', async () => {
    const c = await claim(); await expire('DART');
    const before = await snapshot('DART');
    assert.deepEqual(await renew('DART', A, c.generation), {status:'lease-lost'});
    assert.deepEqual(await save('DART', A, c.generation, 0, fixtures.DART), {status:'lease-lost'});
    assert.deepEqual(await snapshot('DART'), before);
});

check('save CAS conflict and wrong generation leave lease/state untouched', async () => {
    const c = await claim(); const before = await snapshot('DART');
    assert.deepEqual(await save('DART', A, c.generation, 1, fixtures.DART), {status:'revision-conflict'});
    assert.deepEqual(await save('DART', A, c.generation + 1, 0, fixtures.DART), {status:'lease-lost'});
    assert.deepEqual(await snapshot('DART'), before);
});

for (const source of ['SEC', 'DART', 'news']) check(`${source} exact current Python collector/live state accepted unchanged`, async () => {
    const c = await claim(source);
    const saved = await save(source, A, c.generation, 0, fixtures[source]);
    assert.equal(saved.status, 'saved'); assert.equal(saved.revision, 1);
    assert.deepEqual(Object.keys(saved).sort(), ['status','source','generation','revision','feed_revision','updated_at'].sort());
    assert.equal(saved.feed_revision, 1);
    const row = await snapshot(source);
    assert.equal(row.lease_owner, null); assert.equal(row.lease_until, null);
    assert.deepEqual(row.state, fixtures[source]);
});

check('restart new owner reads exact retained state/revision; old generation fenced', async () => {
    await seed();
    const c = await claim('DART', B);
    assert.equal(c.generation, 2); assert.equal(c.revision, 1); assert.deepEqual(c.state, fixtures.DART);
    assert.deepEqual(await save('DART', A, 1, 0, fixtures.DART), {status:'lease-lost'});
    assert.equal(c.requests_reserved, 20); // prior reservation survives worker restart, no refund
});

check('partial merges new fact while preserving cursor/last_success; regression rejected', async () => {
    await seed(); const c = await claim();
    assert.deepEqual(fixtures.partial.cursor, fixtures.DART.cursor);
    assert.equal(fixtures.partial.last_success_at, fixtures.DART.last_success_at);
    assert.equal((await save('DART', A, c.generation, c.revision, fixtures.partial)).status, 'saved');
    const next = await claim(); const bad = copy(fixtures.partial); bad.cursor.ids = [];
    await regression(bad, 'DART', next);
});

check('error preserves feed/cursor/success; unsuccessful success-clock advancement rejected', async () => {
    await seed(); const c = await claim();
    assert.equal((await save('DART', A, c.generation, c.revision, fixtures.error)).status, 'saved');
    const next = await claim(); const bad = copy(fixtures.partial);
    bad.last_success_at = bad.last_attempt_at; bad.health = {status:'on-time',age_seconds:0};
    await regression(bad, 'DART', next);
});

check('complete empty discovery updates successful check without clearing retained facts', async () => {
    await seed(); const c = await claim();
    assert.equal((await save('DART', A, c.generation, c.revision, fixtures.empty)).status, 'saved');
    assert.deepEqual((await snapshot('DART')).state.feed, fixtures.DART.feed);
    const next = await claim(); const bad = copy(fixtures.empty); bad.feed = {items:[]};
    await regression(bad, 'DART', next);
});

check('initialized SEC bootstrap sets anchor but never success; first error has unknown freshness', async () => {
    const c = await claim('SEC');
    assert.equal((await save('SEC', A, c.generation, 0, fixtures.initialized)).status, 'saved');
    assert.equal(fixtures.initialized.last_success_at, undefined);
    assert.equal(fixtures.initialized.health.status, 'unknown');
    const d = await claim('DART');
    assert.equal((await save('DART', A, d.generation, 0, fixtures.firstError)).status, 'saved');
});

check('DART 10 reservation exact, repeated/invalid input never changes counters', async () => {
    for (const [source, budget] of [['DART',0],['DART',9],['DART',11],['SEC',10],['news',10],['DART',null]]) {
        await assert.rejects(() => claim(source,A,budget), e => e.code === '22023');
    }
    assert.equal((await snapshot('DART')).requests_reserved, 0);
    const c = await claim(); assert.equal(c.requests_reserved, 10);
    await save('DART', A, c.generation, 0, fixtures.firstError);
    assert.equal((await snapshot('DART')).requests_reserved, 10); // timeout consumed; unused budget not refunded
});

check('DB cadence gate prevents immediate post-save extra DART reservation', async () => {
    const c=await claim();
    const stamp=(await rows('SELECT clock_timestamp()::text stamp'))[0].stamp;
    const state=copy(fixtures.DART);
    const instant=new Date(stamp).toISOString();
    state.last_attempt_at=instant; state.last_success_at=instant; state.cursor.checked_at=instant;
    assert.equal((await save('DART',A,c.generation,c.revision,state)).status,'saved');
    const before=await snapshot('DART');
    const result=await claim('DART',B);
    assert.equal(result.status,'not-due'); assert.ok(result.retry_after_seconds>=1 && result.retry_after_seconds<=120);
    assert.deepEqual(await snapshot('DART'),before);
});

check('DART limit 8000 atomic; exhausted claim neither acquires nor increments', async () => {
    await ownerExec("UPDATE public.member_map_refresh_checkpoint SET request_day=(clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date,requests_reserved=7990 WHERE source='DART'");
    const c = await claim(); assert.equal(c.requests_reserved, 8000);
    await expire('DART'); const before = await snapshot('DART');
    assert.deepEqual(await claim('DART', B), {status:'budget-exhausted'});
    assert.deepEqual(await snapshot('DART'), before);
});

check('DART KST rollover derived from DB clock; budget and 020 block reset only next day', async () => {
    await ownerExec("UPDATE public.member_map_refresh_checkpoint SET request_day=(clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date-1,requests_reserved=8000,quota_blocked_day=(clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date-1 WHERE source='DART'");
    const c = await claim(); assert.equal(c.requests_reserved,10);
    const today = (await rows("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date::text d"))[0].d;
    assert.equal(c.request_day,today);
    const remaining = (await rows("SELECT extract(epoch FROM ((($1::date+1)::timestamp AT TIME ZONE 'Asia/Seoul')-$2::timestamptz))::float8 s", [today,c.lease_until]))[0].s;
    assert.ok(remaining >= 0);
});

check('DART old reservation day cannot renew/save even with artificially live lease', async () => {
    const c=await claim();
    await ownerExec("UPDATE public.member_map_refresh_checkpoint SET request_day=request_day-1 WHERE source='DART'");
    const before=await snapshot('DART');
    assert.deepEqual(await renew('DART',A,c.generation),{status:'lease-lost'});
    assert.deepEqual(await save('DART',A,c.generation,c.revision,fixtures.DART),{status:'lease-lost'});
    assert.deepEqual(await snapshot('DART'),before);
});

check('success cursor boundary day/IDs cannot regress; SEC historical gap retained', async () => {
    await seed(); let c=await claim();
    const earlier=copy(fixtures.empty);
    earlier.cursor.through_date='2000-01-01'; earlier.cursor.ids=[];
    await regression(earlier,'DART',c);
    const missing=copy(fixtures.empty);missing.cursor.ids=[];
    // The fixture might lie in the preceding KST day; pin same prior boundary.
    missing.cursor.through_date=fixtures.DART.cursor.through_date;
    assert.ok(fixtures.DART.cursor.ids.length > 0);
    await regression(missing,'DART',c);
    await seed('SEC');c=await claim('SEC');
    const gap=copy(fixtures.SEC);gap.cursor.historical_gap=false;
    await regression(gap,'SEC',c);
});

check('DART 020 saves fixed code, preserves evidence, blocks same KST day; SEC/news independent', async () => {
    await seed(); const c = await claim(); const state = copy(fixtures.error); state.error='dart-quota-exceeded';
    assert.equal((await save('DART',A,c.generation,c.revision,state)).status,'saved');
    assert.deepEqual(await claim('DART',B), {status:'quota-blocked'});
    assert.deepEqual((await snapshot('DART')).state.feed, fixtures.DART.feed);
    assert.equal((await claim('SEC')).status,'claimed'); assert.equal((await claim('news')).status,'claimed');
});

check('source input allowlist/null/zero identity rejected; three-row storage ceiling', async () => {
    for (const source of ['other','dart','SEC/../price',null]) await assert.rejects(() => claim(source), e=>e.code==='22023');
    for (const owner of [null,'00000000-0000-0000-0000-000000000000']) await assert.rejects(()=>claim('SEC',owner),e=>e.code==='22023');
    await ownerExec("SELECT 1"); await role();
    await assert.rejects(()=>db.exec("INSERT INTO public.member_map_refresh_checkpoint(source) VALUES('other')"),e=>e.code==='23514');
    await assert.rejects(()=>db.exec("INSERT INTO public.member_map_refresh_checkpoint(source) VALUES('SEC')"),e=>e.code==='23505');
});

check('private/unregistered fields rejected at every existing state layer without dropping', async () => {
    for (const mutate of [s=>s.member_id=A, s=>s.feed.portfolio=[], s=>s.feed.items[0].member_note='private',
        s=>s.feed.items[0].disclosures[0].api_key='private', s=>s.cursor.token='private',
        s=>s.coverage.provider_body='private', s=>s.health.secret='private', s=>s.feed._meta.raw='private']) {
        const bad=copy(fixtures.DART); mutate(bad); await invalid(bad);
    }
});

check('wrong/null/bool scalar types, delivery claims and malformed dates rejected', async () => {
    for (const mutate of [s=>s.requests=true,s=>s.requests=11,s=>s.screen_delivery_verified=true,
        s=>s.last_attempt_at='infinity',s=>s.last_attempt_at='2026-10-12T00:00:00',
        s=>s.health.age_seconds=true,s=>s.cursor.through_date=null,s=>s.cursor.ids=[null],
        s=>s.feed.items[0].latest=null,s=>s.feed.items[0].disclosures[0].date=null,
        s=>s.feed.items[0].disclosures[0].label=null,s=>s.feed.items[0].disclosures[0].id=null,
        s=>s.feed.items[0].disclosures[0].date='2026-02-30',s=>s.feed._meta.count=true,
        s=>s.feed.items[0].disclosures[0].is_correction='false']) {
        const bad=copy(fixtures.DART);mutate(bad);await invalid(bad);
    }
});

check('secret-shaped values, raw errors, external filing URLs and mismatched receipts rejected', async () => {
    for (const mutate of [s=>s.error='remote body with token',
        s=>s.feed.items[0].disclosures[0].title='Bearer not-a-real-secret',
        s=>s.feed.items[0].disclosures[0].title='sk-fixture_not_real_secret',
        s=>s.feed.items[0].disclosures[0].source_url='https://other.example/private',
        s=>s.feed.items[0].disclosures[0].source_url+='1',
        s=>s.coverage.raw_body_checked=true,s=>s.coverage.whole_market_coverage=true]) {
        const bad=copy(fixtures.DART);mutate(bad);await invalid(bad);
    }
});

check('record bounds: nine per issuer, duplicate issuer/IDs, 1001 DART cursor IDs rejected', async () => {
    for (const mutate of [s=>s.feed.items[0].disclosures=Array(9).fill(s.feed.items[0].disclosures[0]),
        s=>s.feed.items.push(copy(s.feed.items[0])),s=>s.feed.items[0].disclosures.push(copy(s.feed.items[0].disclosures[0])),
        s=>s.cursor.ids=Array(1001).fill(s.cursor.ids[0])]) {
        const bad=copy(fixtures.DART);mutate(bad);await invalid(bad);
    }
});

check('4MiB UTF-8 serialized bound enforced before nested values; previous state survives', async () => {
    function largeState(groups, title) {
        const state=copy(fixtures.DART), base=state.feed.items[0].disclosures[0];
        state.feed.items=Array.from({length:groups},(_,g)=>({ticker:String(g).padStart(6,'0'),name:'Public Issuer',
            latest:base.date,disclosures:Array.from({length:8},(_,i)=>{
                const receipt=String(BigInt(base.id.slice(5))+BigInt(g*8+i));
                return {...base,title,id:'DART:'+receipt,source_url:'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt};
            })}));
        state.feed._meta.count=groups;state.feed._meta.disclosure_count=groups*8;
        return state;
    }
    const valid=largeState(2,'한'.repeat(300));
    const positive=await ownerExec('SELECT public.member_map_refresh_state_valid($1,$2::jsonb) v',['DART',JSON.stringify(valid)]);
    assert.equal(positive[0].v,true); // same closed shape, no extra/invalid field hiding size checks
    for(const oversized of [largeState(2000,'x'.repeat(300)),largeState(800,'한'.repeat(300))]) {
        assert.ok(Buffer.byteLength(JSON.stringify(oversized))>4194304);
        await invalid(oversized);
    }
});

check('10000-issuer bound rejects 10001 closed empty groups independently of byte bound', async () => {
    const state=copy(fixtures.DART);
    state.feed.items=Array.from({length:10001},(_,i)=>({ticker:String(i).padStart(6,'0'),name:'Public Issuer',disclosures:[]}));
    state.feed._meta.count=10001;state.feed._meta.disclosure_count=0;
    assert.ok(Buffer.byteLength(JSON.stringify(state))<4194304);await invalid(state);
});

check('news exact lanes and closed rows; sensitive URLs/IPs/encoded queries rejected', async () => {
    for (const mutate of [s=>s.feed.prices=[],s=>s.feed.headlines[0].sentiment='positive',
        s=>s.feed.headlines[0].link='https://user:password@example.com/',
        s=>s.feed.headlines[0].link='https://127.0.0.1/private',
        s=>s.feed.headlines[0].link='https://example.com/?token=not-a-key',
        s=>s.feed.headlines[0].link='https://example.com/?%74oken=not-a-key',
        s=>s.feed.headlines=Array(101).fill(s.feed.headlines[0]),
        s=>s.status='success']) {
        const bad=copy(fixtures.news);mutate(bad);await invalid(bad,'news');
    }
});

check('future attempt, forged health and earlier attempt clock cannot overwrite', async () => {
    const bad=copy(fixtures.DART);bad.last_attempt_at='9999-01-01T00:00:00Z';await invalid(bad);
    const health=copy(fixtures.partial);health.health={status:'on-time',age_seconds:0};await invalid(health);
    await seed('DART',fixtures.empty);const c=await claim();await regression(fixtures.DART,'DART',c);
});

check('SEC id/source-date/url binding and nullable anchor rejected', async () => {
    for (const mutate of [s=>s.cursor.anchor_id=null,s=>s.feed.items[0].disclosures[0].source_url='https://www.sec.gov/Archives/edgar/data/2/000000000000000001/x.htm',
        s=>s.feed.items[0].disclosures[0].source_date_field='filingDate',
        s=>s.feed.items[0].disclosures[0].date='2000-01-01']) {
        const bad=copy(fixtures.SEC);mutate(bad);await invalid(bad,'SEC');
    }
});

check('original table/function/role/default-grants remain unchanged', async () => {
    await role();
    assert.deepEqual(await rows('SELECT * FROM public.original_schema_sentinel'), [{id:1,value:'retained'}]);
    assert.equal((await rows('SELECT public.original_function_sentinel() v'))[0].v,'retained');
    assert.deepEqual(await rows("SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') ORDER BY rolname"),
        [{rolname:'anon',rolsuper:false,rolbypassrls:false},{rolname:'authenticated',rolsuper:false,rolbypassrls:false},{rolname:'service_role',rolsuper:false,rolbypassrls:true}]);
    assert.equal((await rows("SELECT count(*)::int n FROM pg_default_acl"))[0].n,0);
});

check('existing table/function overload collision fails closed; previous schema untouched', async () => {
    for (const collision of ["CREATE TABLE public.member_map_refresh_checkpoint(original text)",
        "CREATE FUNCTION public.member_map_refresh_claim(integer) RETURNS integer LANGUAGE sql AS $$ SELECT 1 $$"]) {
        const isolated=new PGlite();
        try {
            await bootstrap(isolated); await isolated.exec(collision);
            await assert.rejects(()=>isolated.exec(sql), /refresh-checkpoint-name-collision/);
            await isolated.exec('ROLLBACK');
            assert.equal((await rows('SELECT value FROM public.original_schema_sentinel',[],isolated))[0].value,'retained');
            assert.equal((await rows("SELECT count(*)::int n FROM pg_proc WHERE proname='member_map_refresh_save'",[],isolated))[0].n,0);
        } finally {await isolated.close();}
    }
});

check('missing/unsafe existing roles fail closed without creating table or altering roles', async () => {
    for (const roles of [false, 'unsafe']) {
        const isolated=new PGlite();
        try {
            await bootstrap(isolated,roles!==false);
            if(roles==='unsafe') await isolated.exec('ALTER ROLE anon BYPASSRLS');
            await assert.rejects(()=>isolated.exec(sql),/refresh-checkpoint-unsafe-roles/);
            await isolated.exec('ROLLBACK');
            assert.equal((await rows("SELECT to_regclass('public.member_map_refresh_checkpoint') v",[],isolated))[0].v,null);
        } finally {await isolated.close();}
    }
});

check('inherited unsafe owner privileges abort instead of changing existing memberships', async () => {
    const isolated=new PGlite();
    try {
        await bootstrap(isolated);
        const owner=(await rows('SELECT current_user name',[],isolated))[0].name;
        assert.match(owner,/^[A-Za-z_][A-Za-z0-9_]*$/);
        await isolated.exec(`GRANT ${owner} TO authenticated`);
        await assert.rejects(()=>isolated.exec(sql),/refresh-checkpoint-unsafe-grants/);
        await isolated.exec('ROLLBACK');
        assert.equal((await rows("SELECT to_regclass('public.member_map_refresh_checkpoint') v",[],isolated))[0].v,null);
    } finally {await isolated.close();}
});

check('claim known revision returns JSON null; missing/stale/future revisions retain full state', async () => {
    const initial=(await rows('SELECT public.member_map_refresh_claim($1,$2) value',['SEC',A]))[0].value;
    assert.deepEqual(initial.state,{}); assert.equal(initial.feed_revision,0);
    const cached=await claim('SEC',A,0,0);
    assert.equal(cached.status,'already-claimed'); assert.equal(cached.state,null);
    assert.ok(Object.hasOwn(cached,'state'));
    assert.equal(cached.generation,initial.generation); assert.equal(cached.lease_until,initial.lease_until);
    assert.equal((await renew('SEC',A,initial.generation)).status,'renewed');
    assert.equal((await snapshot('SEC')).feed_revision,0);
    await seed(); // independent source; existing public state, compact accepted receipt
    const before=await snapshot('DART');
    const known=await claim('DART',A,10,before.revision);
    assert.equal(known.status,'claimed'); assert.equal(known.state,null); assert.equal(known.feed_revision,1);
    const active=await snapshot('DART');
    for(const revision of [-1,0,99]) {
        const full=await claim('DART',A,10,revision);
        assert.equal(full.status,'already-claimed'); assert.deepEqual(full.state,fixtures.DART);
    }
    assert.deepEqual(await snapshot('DART'),active); // repeat does not authorize or reserve a new provider batch
});

check('known revision invalid/null input rejects before lease/quota mutation', async () => {
    const before=await snapshot('DART');
    for(const revision of [null,-2,-100]) await assert.rejects(()=>claim('DART',A,10,revision),e=>e.code==='22023');
    assert.deepEqual(await snapshot('DART'),before);
});

check('feed_revision increments only for changed feed, not error/clock/identical saves', async () => {
    await seed(); assert.equal((await snapshot('DART')).feed_revision,1);
    for(const [state,expectedRevision,expectedFeed] of [
        [fixtures.error,2,1], [fixtures.partial,3,2],
        [{...copy(fixtures.empty),feed:copy(fixtures.partial.feed)},4,2],
        [{...copy(fixtures.empty),feed:copy(fixtures.partial.feed)},5,2],
    ]) {
        const c=await claim();
        const result=await save('DART',A,c.generation,c.revision,state);
        assert.deepEqual(Object.keys(result).sort(),['status','source','generation','revision','feed_revision','updated_at'].sort());
        assert.equal(result.status,'saved');assert.equal(result.revision,expectedRevision);assert.equal(result.feed_revision,expectedFeed);
        const stored=await snapshot('DART');assert.deepEqual(stored.state,state);
        assert.ok(stored.feed_revision<=stored.revision);
    }
});

check('counter CHECK rejects negative and feed_revision greater than revision without mutation', async () => {
    await seed();const before=await snapshot('DART');
    for(const statement of ["UPDATE public.member_map_refresh_checkpoint SET feed_revision=-1 WHERE source='DART'",
        "UPDATE public.member_map_refresh_checkpoint SET feed_revision=revision+1 WHERE source='DART'",
        "UPDATE public.member_map_refresh_checkpoint SET revision=0 WHERE source='DART'"]) {
        await assert.rejects(()=>ownerExec(statement),e=>e.code==='23514');
        assert.deepEqual(await snapshot('DART'),before);
    }
});

check('precise three-source metadata head is compact; revision-fenced changed-source SELECT holds races', async () => {
    await seed();
    const head=await rows("SELECT source,revision,feed_revision FROM public.member_map_refresh_checkpoint WHERE source IN ('SEC','DART','news') ORDER BY source LIMIT 3");
    assert.equal(head.length,3);assert.ok(head.every(row=>Object.keys(row).sort().join(',')==='feed_revision,revision,source'));
    const old=head.find(row=>row.source==='DART');const c=await claim();
    await save('DART',A,c.generation,c.revision,fixtures.partial);
    assert.deepEqual(await rows('SELECT source,state,revision,feed_revision FROM public.member_map_refresh_checkpoint WHERE source=$1 AND feed_revision=$2',['DART',old.feed_revision]),[]);
    const latest=(await snapshot('DART')).feed_revision;
    const fresh=await rows('SELECT source,state,revision,feed_revision FROM public.member_map_refresh_checkpoint WHERE source=$1 AND feed_revision=$2',['DART',latest]);
    assert.equal(fresh.length,1);assert.deepEqual(fresh[0].state,fixtures.partial);
});

check('other-role default grants fail closed without altering existing defaults', async () => {
    for(const kind of ['TABLES','FUNCTIONS']) {
        const isolated=new PGlite();
        try {
            await bootstrap(isolated);
            await isolated.exec(`CREATE ROLE other_service BYPASSRLS;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ${kind} TO other_service;`);
            const before=await rows('SELECT to_jsonb(d) value FROM pg_default_acl d',[],isolated);
            await assert.rejects(()=>isolated.exec(sql),/refresh-checkpoint-unsafe-default-grants/);
            await isolated.exec('ROLLBACK');
            assert.deepEqual(await rows('SELECT to_jsonb(d) value FROM pg_default_acl d',[],isolated),before);
            assert.equal((await rows("SELECT to_regclass('public.member_map_refresh_checkpoint') v",[],isolated))[0].v,null);
        } finally {await isolated.close();}
    }
});

async function loadFixtures() {
    // Direct existing producers with mock transports; no reimplemented parser.
    const now=new Date(Date.now()-300000).toISOString();
    return JSON.parse(execFileSync('python3',['-c',`
import json,sys
from datetime import datetime,timedelta,timezone
from api.collectors.member_map_listing_delta import collect_dart_delta,collect_sec_delta
from api.collectors.member_map_live_refresh import apply_result
now=sys.argv[1]; stamp=datetime.fromisoformat(now.replace('Z','+00:00')); day=stamp.astimezone(timezone(timedelta(hours=9))).strftime('%Y%m%d')
payload={'status':'000','page_no':1,'page_count':100,'total_count':1,'total_page':1,
 'list':[{'rcept_no':day+'000001','rcept_dt':day,'stock_code':'005930','report_nm':'공급 계약 체결','flr_nm':'공시회사'}]}
r=collect_dart_delta({'005930':'공시회사'},{'items':[]},None,now,'fixture-not-a-real-key',transport=lambda *a,**kw:json.dumps(payload).encode())
dart=apply_result('DART',{},r,now)
later=(stamp+timedelta(seconds=30)).isoformat()
payload['list'][0]['rcept_no']=day+'000002'
r2=collect_dart_delta({'005930':'공시회사'},dart['feed'],dart['cursor'],later,'fixture-not-a-real-key',transport=lambda *a,**kw:json.dumps(payload).encode())
r2.update(status='partial',complete=False,error='page_limit')
partial=apply_result('DART',dart,r2,later)
error=apply_result('DART',dart,{'status':'error','complete':False,'error':'collection-failed'},later)
empty=apply_result('DART',dart,{**r,'records':[],'cursor':{**r['cursor'],'checked_at':later}},later)
atom=f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>8-K - Public Issuer (1) (Filer)</title><category term="8-K"/><id>x?accession-number=0000000001-26-000001</id><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/filing.htm"/><updated>{now}</updated></entry></feed>'''.encode()
sr=collect_sec_delta({'1':[{'ticker':'PUB','name':'Public Issuer'}]},{'items':[]},None,now,transport=lambda *a,**kw:atom)
initialized=apply_result('SEC',{},sr,now)
sec=apply_result('SEC',{}, {**sr,'status':'success','complete':True,'cursor':sr['cursor']},now)
news=apply_result('news',{}, {'status':'partial','complete':False,'error':'per-feed-completeness-unavailable','requests':None,
 'feed':{'headlines':[{'title':'공개 공급 계약','source':'Public News','link':'https://example.com/public-news','time':now}],
 'bloomberg_google_headlines':[],'us_headlines':[]},'coverage':{'accepted':1,'rejected':0,'whole_market_coverage':False,'all_feeds_verified':False}},now)
print(json.dumps({'DART':dart,'SEC':sec,'news':news,'initialized':initialized,'partial':partial,'error':error,'empty':empty,
 'firstError':apply_result('DART',{}, {'status':'error','complete':False,'error':'collection-failed'},now)}))
`,now], {cwd:path.join(__dirname,'..'),env:{PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'},maxBuffer:1048576}).toString());
}

(async()=>{
    db=new PGlite(); await bootstrap(db); await db.exec(sql); fixtures=await loadFixtures();
    for(const item of cases) {
        await role();
        await db.exec("UPDATE public.member_map_refresh_checkpoint SET state='{}',revision=0,feed_revision=0,lease_owner=null,lease_generation=0,lease_until=null,request_day=null,requests_reserved=0,quota_blocked_day=null");
        await role('service_role');
        await item.run(); passed++; console.log('PASS '+item.name);
    }
    assert.equal(sha(fs.readFileSync(sqlPath)),sqlHash,'migration changed during test');
    assert.equal(sha(fs.readFileSync(__filename)),testHash,'test changed during run');
    console.log(JSON.stringify({migration_sha256:sqlHash,test_sha256:testHash}));
    console.log(`${passed}/${cases.length} passed; production two-connection race and REST/Railway acceptance NOT run`);
    await db.close();
})().catch(async error=>{
    console.error(`FAIL ${passed+1}/${cases.length} ${cases[passed]?.name || 'setup'}: ${error.code || ''} ${error.message}`);
    if(db) await db.close(); process.exitCode=1;
});
