// Disposable, local-only PostgreSQL. No URL, credentials or production DB accepted.
// Usage: node tests/content_mcp_nonexpiring_db.mjs /absolute/path/to/pglite/dist/index.js
// Uses an already installed PGlite module; does not install/download dependencies.
// Single-connection tests do not establish concurrent production acceptance.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';

assert(process.argv[2] && isAbsolute(process.argv[2]), 'Pass an installed local PGlite module path');
const { PGlite } = await import(pathToFileURL(process.argv[2]).href);
const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const migration = await read('supabase/migrations/20261030161003_content_mcp_nonexpiring_claude.sql');
const predecessors = await Promise.all([
  '2026092602_content_mcp_oauth.sql', '2026092701_content_mcp_refresh.sql',
  '2026100201_content_mcp_claude.sql', '2026100202_content_mcp_annual_refresh.sql',
].map(name => read(`supabase/migrations/${name}`)));
const resource = 'https://project-yw131.vercel.app/api/content_mcp';
const claude = 'alphanest-content-claude';
const callbacks = {
  [claude]: 'https://claude.ai/api/mcp/auth_callback',
  'alphanest-content-chatgpt': 'https://chatgpt.com/connector_platform_oauth_redirect',
  'alphanest-content-perplexity': 'https://www.perplexity.ai/rest/connections/oauth_callback',
};
let serial = 0;
const hash = () => createHash('sha256').update(`nonexpiring-fixture-${++serial}`).digest('hex');
const db = new PGlite();
const checks = [];
const query = async (sql, params = []) => (await db.query(sql, params)).rows;
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log(`PASS ${name}`);
}
const call = async (name, args) => (await query(
  `select public.${name}(${args.map((_, i) => `$${i + 1}::text`).join(',')}) as result`, args))[0].result;
const reject = promise => assert.rejects(promise, e => e.code === '23514');
async function invite(expires = 'infinity') {
  const id = hash();
  await query('insert into public.content_mcp_invites(invite_hash,label,expires_at) values ($1,$2,$3::timestamptz)',
    [id, 'synthetic-nonexpiring-test', expires]);
  return id;
}
async function issue(id, client = claude) {
  const code = hash();
  const r = await call('content_mcp_issue_code', [id, code, client, callbacks[client], resource, 'content:read', 'A'.repeat(43)]);
  assert.equal(r.status, 'allowed');
  return code;
}
async function exchange(id, client = claude) {
  const code = await issue(id, client), token = hash(), refresh = hash();
  const result = await call('content_mcp_exchange_code_refresh',
    [code, client, callbacks[client], resource, 'content:read', 'A'.repeat(43), token, refresh]);
  return { id, client, code, token, refresh, family: refresh, result };
}
async function rotate(f, overrides = {}) {
  const token = hash(), refresh = hash();
  const result = await call('content_mcp_rotate_refresh',
    [overrides.old ?? f.refresh, token, refresh, overrides.client ?? f.client, resource, overrides.scope ?? 'content:read']);
  return { ...f, token, refresh, result };
}
const consume = token => call('content_mcp_consume_token', [token, resource, 'content:read']);
function infinite(r) {
  assert.equal(r.status, 'allowed');
  assert.equal(r.refresh_expires_in, null);
  assert.equal(r.refresh_non_expiring, true);
  assert(r.expires_in > 0 && r.expires_in <= 3600);
}
function finite(r) {
  assert.equal(r.status, 'allowed');
  assert(!Object.hasOwn(r, 'refresh_non_expiring'));
  assert(Number.isInteger(r.refresh_expires_in) && r.refresh_expires_in > 0 && r.refresh_expires_in <= 31536000);
  assert(r.expires_in > 0 && r.expires_in <= 3600);
}
async function security() {
  return query(`select p.oid,p.proname,p.proowner,p.proacl::text,p.prosecdef,p.proconfig
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname like 'content_mcp_%' order by p.oid`);
}
async function tableSecurity() {
  return query(`select oid,relname,relowner,relacl::text,relrowsecurity,relforcerowsecurity
    from pg_class where relnamespace='public'::regnamespace and relkind='r'
      and relname like 'content_mcp_%' order by oid`);
}

try {
  await db.exec('create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;');
  for (const sql of predecessors) await db.exec(sql);
  const old = await exchange(await invite('2027-01-01T00:00:00Z'));
  const before = await query('select to_jsonb(f) as value from public.content_mcp_refresh_families f where family_hash=$1', [old.family]);
  const secBefore = await security(), tablesBefore = await tableSecurity();
  await check('predecessor body drift fails closed without changing schema', async () => {
    const { definition } = (await query("select pg_get_functiondef('public.content_mcp_rotate_refresh(text,text,text,text,text,text)'::regprocedure) as definition"))[0];
    await db.exec(definition.replace('declare', 'declare\n    -- intentional fixture drift'));
    await assert.rejects(db.exec(migration), /Unexpected RPC/);
    await db.exec('rollback;');
    await db.exec(definition);
    await reject(invite());
  });
  await db.exec(migration);
  await check('existing deadlines/rows and function/table security preserved', async () => {
    assert.deepEqual(await security(), secBefore);
    assert.deepEqual(await tableSecurity(), tablesBefore);
    assert.deepEqual(await query('select to_jsonb(f) as value from public.content_mcp_refresh_families f where family_hash=$1', [old.family]), before);
    assert.equal((await query("select format_type(atttypid,atttypmod) as type from pg_attribute where attrelid='public.content_mcp_refresh_families'::regclass and attname='rotation_count'"))[0].type, 'bigint');
  });
  await check('repeat migration fails closed', async () => {
    await assert.rejects(db.exec(migration), /Unexpected constraint/);
    await db.exec('rollback;');
  });
  await check('positive infinity opt-in rejects negative infinity and non-Claude infinite families', async () => {
    await reject(invite('-infinity'));
    const f = await exchange(await invite());
    infinite(f.result);
    await reject(query("update public.content_mcp_refresh_families set expires_at='-infinity' where family_hash=$1", [f.family]));
    await reject(query("update public.content_mcp_refresh_families set client_id='alphanest-content-chatgpt' where family_hash=$1", [f.family]));
    await reject(query("update public.content_mcp_refresh_families set rotation_count=-1 where family_hash=$1", [f.family]));
    const dates = (await query(`select f.expires_at::text as family_expiry, pg_catalog.isfinite(t.expires_at) as finite_access,
      t.expires_at <= clock_timestamp()+interval '1 hour' as access_bound,
      pg_catalog.isfinite(c.expires_at) and c.expires_at <= clock_timestamp()+interval '5 minutes' as code_bound
      from public.content_mcp_refresh_families f join public.content_mcp_tokens t on t.token_hash=$2
      join public.content_mcp_codes c on c.code_hash=$3 where f.family_hash=$1`, [f.family, f.token, f.code]))[0];
    assert.deepEqual(dates, { family_expiry: 'infinity', finite_access: true, access_bound: true, code_bound: true });
  });
  await check('finite invitations and other clients retain annual finite replies', async () => {
    for (const client of Object.keys(callbacks)) {
      finite((await exchange(await invite('2030-01-01T00:00:00Z'), client)).result);
      if (client !== claude) {
        const f = await exchange(await invite(), client);
        finite(f.result); finite((await rotate(f)).result);
      }
    }
  });
  await check('non-expiring rotation survives 20000 and signed-int32 counts; replay still revokes', async () => {
    const initial = await exchange(await invite());
    await query('update public.content_mcp_refresh_families set rotation_count=2147483647 where family_hash=$1', [initial.family]);
    const f = await rotate(initial); infinite(f.result);
    assert.equal(Number((await query('select rotation_count from public.content_mcp_refresh_families where family_hash=$1', [f.family]))[0].rotation_count), 2147483648);
    assert.equal((await consume(initial.token)).status, 'denied');
    assert.equal((await consume(f.token)).status, 'allowed');
    assert.equal((await rotate(f, { old: initial.refresh, client: 'alphanest-content-chatgpt' })).result.status, 'denied');
    assert.equal((await consume(f.token)).status, 'allowed');
    assert.equal((await rotate(f, { old: initial.refresh })).result.status, 'denied');
    assert.equal((await consume(f.token)).status, 'denied');
    assert.equal((await rotate(f)).result.status, 'denied');
    assert.equal(Number((await query('select count(*) as n from public.content_mcp_refresh_hashes where family_hash=$1', [f.family]))[0].n), 2);
  });
  await check('infinite family respects shortened/expired/revoked invite and finite response boundary', async () => {
    let f = await exchange(await invite());
    await query("update public.content_mcp_invites set expires_at=clock_timestamp()+interval '90 seconds' where invite_hash=$1", [f.id]);
    f = await rotate(f); finite(f.result); assert(f.result.refresh_expires_in <= 90);
    for (const column of ['expires_at', 'revoked_at']) {
      await query(`update public.content_mcp_invites set ${column}=clock_timestamp()-interval '1 second' where invite_hash=$1`, [f.id]);
      assert.equal((await rotate(f)).result.status, 'denied');
      assert.equal((await consume(f.token)).status, 'denied');
      await query("update public.content_mcp_invites set expires_at='infinity',revoked_at=null where invite_hash=$1", [f.id]);
    }
  });
  await check('long finite parent transition denies without spending refresh or overflowing int32', async () => {
    for (const duration of ['730 days', '100 years']) {
      const f = await exchange(await invite());
      await query('update public.content_mcp_invites set expires_at=clock_timestamp()+$2::interval where invite_hash=$1', [f.id, duration]);
      const denied = await rotate(f);
      assert.deepEqual(denied.result, { status: 'denied' });
      assert.equal((await query('select used_at is null as unused from public.content_mcp_refresh_hashes where refresh_hash=$1', [f.refresh]))[0].unused, true);
      assert.equal((await consume(f.token)).status, 'allowed');
      assert.equal((await query('select exists(select 1 from public.content_mcp_tokens where token_hash=$1) as created', [denied.token]))[0].created, false);
      assert.deepEqual((await query('select expires_at::text as expiry,rotation_count from public.content_mcp_refresh_families where family_hash=$1', [f.family]))[0], { expiry: 'infinity', rotation_count: 0 });
      await query("update public.content_mcp_invites set expires_at='infinity' where invite_hash=$1", [f.id]);
      infinite((await rotate(f)).result);
    }
  });
  await check('five-per-minute rotation limit and invite quotas roll back denied changes', async () => {
    let f = await exchange(await invite());
    for (let i = 0; i < 5; i++) { f = await rotate(f); infinite(f.result); }
    assert.equal((await rotate(f)).result.status, 'limited');
    assert.equal((await query('select used_at is null as unused from public.content_mcp_refresh_hashes where refresh_hash=$1', [f.refresh]))[0].unused, true);
    for (const [field, limit] of [['minute_used', 10], ['day_used', 100]]) {
      await query("update public.content_mcp_refresh_families set minute_start='-infinity',minute_used=0 where family_hash=$1", [f.family]);
      await query('update public.content_mcp_invites set minute_start=clock_timestamp(),day_start=clock_timestamp(),minute_used=$2,day_used=$3 where invite_hash=$1',
        [f.id, field === 'minute_used' ? limit : 0, field === 'day_used' ? limit : 0]);
      const beforeCount = await query('select rotation_count from public.content_mcp_refresh_families where family_hash=$1', [f.family]);
      assert.equal((await rotate(f)).result.status, 'limited');
      assert.deepEqual(await query('select rotation_count from public.content_mcp_refresh_families where family_hash=$1', [f.family]), beforeCount);
      assert.equal((await query('select used_at is null as unused from public.content_mcp_refresh_hashes where refresh_hash=$1', [f.refresh]))[0].unused, true);
    }
  });
  await check('five retained families cap includes infinite and revoked families', async () => {
    const id = await invite();
    for (let i = 0; i < 5; i++) {
      const f = await exchange(id); infinite(f.result);
      await query('update public.content_mcp_refresh_families set revoked_at=clock_timestamp() where family_hash=$1', [f.family]);
      await query('update public.content_mcp_tokens set revoked_at=clock_timestamp() where token_hash=$1', [f.token]);
    }
    assert.equal((await exchange(id)).result.status, 'limited');
  });
  for (const suite of ['oauth', 'refresh', 'claude', 'annual']) {
    await check(`existing ${suite} SQL regression suite`, async () => {
      const results = await db.exec(await read(`tests/content_mcp_${suite}_db_checks.sql`));
      assert(results.some(result => result.rows?.some(row => Object.values(row).some(value =>
        typeof value === 'string' && value.endsWith('_DB_CHECKS_PASS')))), 'SQL suite must emit pass marker');
    });
  }
  console.log(JSON.stringify({ passed: checks.length, total: checks.length, engine: (await query('select version() as version'))[0].version }));
} catch (error) {
  console.error(JSON.stringify({ passed: checks.length, failure: error.message, code: error.code, where: error.where }));
  process.exitCode = 1;
} finally {
  await db.close();
}
