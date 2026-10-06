// Isolated in-memory PostgreSQL/WASM; no production calls or network.
// PGLITE_MODULE=/existing/path/to/@electric-sql/pglite node tests/public_survey_retention_sql.cjs
// pg_cron is unavailable in PGlite: its blocks are checked statically, never
// represented as a real scheduler run. The remaining SQL runs unchanged.
const {PGlite} = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const read = name => fs.readFileSync(path.join(__dirname, '../supabase/migrations', name), 'utf8');
const sql = read('2026100701_public_survey_retention.sql');
const cronPrerequisite = /DO \$cron_prerequisite\$[\s\S]*?\$cron_prerequisite\$;/;
const schedule = /DO \$schedule\$[\s\S]*?\$schedule\$;/;
assert.equal((sql.match(cronPrerequisite) || []).length, 1);
assert.equal((sql.match(schedule) || []).length, 1);
const cleanupSql = sql.replace(cronPrerequisite, '').replace(schedule, '');
const db = new PGlite();
const uuid = n => '00000000-0000-4000-8000-' + n.toString(16).padStart(12, '0');
const hash = n => n.toString(16).padStart(64, '0');
const answers = {purpose:'company', features:['report'], outcome:null, discovery:null, comment:'retention fixture'};
let passed = 0;
async function check(name, fn) { await fn(); passed++; console.log('PASS ' + name); }
async function scalar(query, args=[]) { return Object.values((await db.query(query, args)).rows[0])[0]; }
async function role(actor) { await db.exec('reset role'); if (actor) await db.exec('set role ' + actor); }
async function insert(n, age) {
  await db.query(`insert into public.public_survey_responses values
    ('2026-10-v1',$1,$2,$3,statement_timestamp()-$4::interval)`, [uuid(n),hash(n),JSON.stringify(answers),age]);
}
async function submit(n) {
  return scalar('select public.submit_public_survey($1,$2,$3,$4,$5)',
    ['2026-10-v1',uuid(n),hash(n),JSON.stringify(answers),hash(n)]);
}
async function migrationRejects(query, pattern) {
  await assert.rejects(() => db.exec(query), pattern);
  await db.exec('rollback');
}

(async () => {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create role outsider; grant usage on schema public to anon,authenticated,service_role,outsider;
    alter default privileges in schema public grant all on functions to anon,authenticated,service_role;
    create table public.unrelated_retention_fixture(marker text);
    insert into public.unrelated_retention_fixture values ('preserve');`);
  await check('missing survey prerequisite fails clearly', async () => {
    await migrationRejects(sql, /public_survey_retention_requires_2026100601/);
  });
  await db.exec(read('2026100301_api_rate_boundaries.sql'));
  await db.exec(read('2026100601_public_survey.sql'));
  const rpcBefore = await scalar("select pg_get_functiondef('public.submit_public_survey(text,uuid,text,jsonb,text)'::regprocedure)");
  await check('missing pg_cron fails clearly without partial installation', async () => {
    await migrationRejects(sql, /public_survey_retention_requires_existing_pg_cron/);
    assert.equal(await scalar("select to_regprocedure('public.maintain_public_survey_responses()')"), null);
  });
  await check('cleanup migration applies twice and preserves submission RPC/schema access', async () => {
    await db.exec(cleanupSql); await db.exec(cleanupSql);
    assert.equal(await scalar("select pg_get_functiondef('public.submit_public_survey(text,uuid,text,jsonb,text)'::regprocedure)"), rpcBefore);
    assert.equal(await scalar("select relrowsecurity from pg_class where oid='public.public_survey_responses'::regclass"), true);
    assert.equal(await scalar("select count(*)::int from pg_policies where schemaname='public' and tablename='public_survey_responses'"), 0);
    assert.equal(await scalar("select count(*)::int from pg_indexes where schemaname='public' and indexname='public_survey_responses_created_at_idx'"), 1);
    const fn = (await db.query("select prosecdef,proconfig,pronargs from pg_proc where oid='public.maintain_public_survey_responses()'::regprocedure")).rows[0];
    assert.equal(fn.prosecdef, true); assert.equal(fn.pronargs, 0); assert.ok(fn.proconfig.includes('search_path=""'));
  });
  for (const actor of ['anon','authenticated','outsider']) {
    await check(actor + ' cannot clean up or read/write responses', async () => {
      await role(actor);
      for (const query of ['select public.maintain_public_survey_responses()',
        'select * from public.public_survey_responses', 'delete from public.public_survey_responses',
        'update public.public_survey_responses set answers=null']) {
        await assert.rejects(() => db.query(query), e => e.code === '42501');
      }
      await role();
    });
  }
  await check('service-only cleanup deletes expired whole rows and preserves younger/future rows', async () => {
    await insert(1, '2161 hours'); await insert(2, '2159 hours'); await insert(3, '-1 hour');
    const ratesBefore = (await db.query('select * from public.api_rate_buckets')).rows;
    await role('service_role');
    await assert.rejects(() => db.query('delete from public.public_survey_responses'), e => e.code === '42501');
    assert.equal(Number(await scalar('select public.maintain_public_survey_responses()')), 1);
    assert.deepEqual((await db.query('select request_id from public.public_survey_responses order by request_id')).rows,
      [{request_id:uuid(2)}, {request_id:uuid(3)}]);
    assert.equal(Number(await scalar('select public.maintain_public_survey_responses()')), 0);
    await role();
    assert.deepEqual((await db.query('select * from public.api_rate_buckets')).rows, ratesBefore);
    assert.equal(await scalar('select marker from public.unrelated_retention_fixture'), 'preserve');
  });
  await check('exact 90-day boundary is inclusive; one microsecond younger survives in a non-UTC timezone', async () => {
    await db.exec("set timezone='America/New_York'");
    // A single statement shares statement_timestamp() across inserts and function.
    await db.exec(`DO $test$ DECLARE v_removed bigint; BEGIN
      INSERT INTO public.public_survey_responses VALUES
        ('2026-10-v1','${uuid(4)}','${hash(4)}','${JSON.stringify(answers)}', statement_timestamp()-interval '2160 hours'),
        ('2026-10-v1','${uuid(5)}','${hash(5)}','${JSON.stringify(answers)}', statement_timestamp()-interval '2160 hours'+interval '1 microsecond');
      v_removed := public.maintain_public_survey_responses();
      IF v_removed <> 1 OR NOT EXISTS (SELECT 1 FROM public.public_survey_responses WHERE request_id='${uuid(5)}') THEN
        RAISE EXCEPTION 'incorrect_retention_boundary';
      END IF;
    END $test$;`);
    await db.exec("set timezone='UTC'");
  });
  await check('deleted response can submit again; retained response still deduplicates', async () => {
    await role('service_role');
    assert.deepEqual(await submit(1), {ok:true,duplicate:false});
    assert.deepEqual(await submit(2), {ok:true,duplicate:true});
    await role();
  });
  await check('reapplication removes overdue rows on activation but keeps fresh responses', async () => {
    await insert(6, '3000 hours');
    await db.exec(cleanupSql);
    assert.equal(await scalar('select count(*)::int from public.public_survey_responses where request_id=$1',[uuid(6)]), 0);
    assert.equal(await scalar('select count(*)::int from public.public_survey_responses where request_id=$1',[uuid(1)]), 1);
  });
  await check('STATIC ONLY: one named hourly job, collision guards, bounded own-job log deletion', async () => {
    const block = sql.match(schedule)[0];
    assert.equal((block.match(/PERFORM cron\.schedule\(/g) || []).length, 1);
    assert.match(block, /cron\.schedule\('alphanest-public-survey-retention', '23 \* \* \* \*', v_command\)/);
    assert.match(block, /COUNT\(\*\) FROM cron\.job WHERE jobname = 'alphanest-public-survey-retention'\) > 1/);
    for (const guard of ['command IS DISTINCT FROM v_command','username IS DISTINCT FROM current_user',
      'database IS DISTINCT FROM current_database()', 'AND active', 'public_survey_retention_schedule_not_active']) {
      assert.ok(block.includes(guard));
    }
    assert.match(block, /DELETE FROM cron\.job_run_details\s+WHERE jobid = \(SELECT jobid FROM cron\.job WHERE jobname = 'alphanest-public-survey-retention'\)\s+AND end_time < now\(\) - INTERVAL '30 days'/);
    assert.match(block, /SELECT public\.maintain_public_survey_responses\(\)/);
    assert.doesNotMatch(sql, /cron\.unschedule|DELETE FROM cron\.job\s|UPDATE cron\.job|CREATE EXTENSION/i);
  });
  console.log(`Survey retention checks: ${passed}/${passed}. Actual pg_cron dispatch/job idempotence remains unverified.`);
})().catch(error => {console.error(error);process.exitCode=1;}).finally(() => db.close());
