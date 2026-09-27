// Local-only PostgreSQL checks; no URL, credentials, or production data accepted.
// Usage: node tests/member_map_state_db.mjs /tmp/<test-dir>/node_modules/@electric-sql/pglite/dist/index.js
// PGlite runs real PostgreSQL SQL in memory. Auth claims below are test fixtures,
// not Supabase Auth/PostgREST verification. Its single connection cannot prove races.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { isAbsolute, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const modulePath = process.argv[2];
assert(modulePath && isAbsolute(modulePath), 'Pass an installed local PGlite module path');
const { PGlite } = await import(pathToFileURL(modulePath).href);
const migrationPath = resolve(fileURLToPath(new URL('../', import.meta.url)),
  'supabase/migrations/2026092701_member_map_state.sql');
const migration = await readFile(migrationPath, 'utf8');
const db = new PGlite();
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const checks = [];
const document = () => ({ layouts: [{
  map_key: 'nest', positions: [{ node_id: 'event-1', x: -18.5, y: 25 }],
  notes: [{ note_id: 'note-1', anchor: { kind: 'node', id: 'event-1' },
    x: 10, y: 20, text: 'fictional test note', done: false }],
  marks: { 'event-1': { read_revision: 2, important: true, disposition: 'later' } },
}] });

async function check(name, fn) {
  try { await fn(); checks.push({ name, passed: true }); }
  catch (error) {
    checks.push({ name, passed: false, message: error.message, code: error.code });
  }
}
async function as(role, uid, fn) {
  assert(['authenticated', 'anon', 'service_role'].includes(role));
  return db.transaction(async tx => {
    await tx.exec(`SET LOCAL ROLE ${role}`);
    await tx.query("SELECT set_config('request.jwt.claims', $1, true)",
      [JSON.stringify({ role, ...(uid ? { sub: uid } : {}) })]);
    return fn(tx);
  });
}
async function save(tx, revision, value) {
  const { rows } = await tx.query(
    'SELECT public.save_member_map_state_v1($1::bigint, $2::jsonb) AS result',
    [revision, JSON.stringify(value)]);
  return rows[0].result;
}
async function rejected(promise, code) {
  await assert.rejects(promise, error => error.code === code);
}

try {
  await db.exec(`
    CREATE ROLE anon NOLOGIN;
    CREATE ROLE authenticated NOLOGIN;
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
    CREATE SCHEMA auth;
    CREATE TABLE auth.users (id uuid PRIMARY KEY);
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
      $$ SELECT (NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid $$;
    CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
      $$ SELECT NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role' $$;
    GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
  `);
  await db.query('INSERT INTO auth.users(id) VALUES ($1), ($2)', [A, B]);
  await db.exec(migration);
  const engine = (await db.query('SELECT version() AS version')).rows[0].version;

  await check('migration enables row isolation and fixes function search path', async () => {
    const table = (await db.query("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.member_map_state'::regclass")).rows[0];
    const fn = (await db.query("SELECT prosecdef, proconfig FROM pg_proc WHERE oid = 'public.save_member_map_state_v1(bigint,jsonb)'::regprocedure")).rows[0];
    assert.equal(table.relrowsecurity, true);
    assert.equal(fn.prosecdef, true);
    assert(fn.proconfig.some(value => value.startsWith('search_path=')));
  });
  await check('member A creates and reads own document', async () => {
    const result = await as('authenticated', A, tx => save(tx, 0, document()));
    assert.equal(Number(result.revision), 1);
    assert.equal(result.user_id, A);
    assert.deepEqual(Object.keys(result).sort(), ['document', 'public_event_cursor_at', 'revision', 'user_id']);
    assert.deepEqual(result.document, document());
    assert.equal(result.public_event_cursor_at, null);
  });
  await check('member B cannot see member A before creating own document', async () => {
    const result = await as('authenticated', B, tx => tx.query('SELECT * FROM public.member_map_state'));
    assert.equal(result.rows.length, 0);
  });
  await check('member B creates separate document', async () => {
    const other = document(); other.layouts[0].notes[0].text = 'member B fixture';
    const result = await as('authenticated', B, tx => save(tx, 0, other));
    assert.equal(Number(result.revision), 1);
    assert.equal(result.user_id, B);
  });
  for (const [who, other] of [[A, B], [B, A]]) {
    await check(`owner-filtered read ${who[0]}`, async () => {
      const result = await as('authenticated', who, tx => tx.query('SELECT user_id FROM public.member_map_state'));
      assert.deepEqual(result.rows, [{ user_id: who }]);
      const target = await as('authenticated', who, tx => tx.query(
        'SELECT * FROM public.member_map_state WHERE user_id=$1', [other]));
      assert.equal(target.rows.length, 0);
    });
  }
  for (const role of ['anon', 'service_role']) {
    await check(`${role} cannot read private table`, () => rejected(
      as(role, null, tx => tx.query('SELECT * FROM public.member_map_state')), '42501'));
    await check(`${role} cannot invoke save`, () => rejected(
      as(role, null, tx => save(tx, 0, document())), '42501'));
  }
  await check('authenticated role without a member identity cannot save', () => rejected(
    as('authenticated', null, tx => save(tx, 0, document())), '42501'));
  await check('direct table update cannot bypass revision checks', () => rejected(
    as('authenticated', A, tx => tx.query(
      'UPDATE public.member_map_state SET document=$1 WHERE user_id=$2', [document(), B])), '42501'));
  await check('direct insert cannot spoof owner', () => rejected(
    as('authenticated', A, tx => tx.query(
      'INSERT INTO public.member_map_state(user_id) VALUES($1)', [B])), '42501'));
  await check('direct delete is denied', () => rejected(
    as('authenticated', A, tx => tx.query('DELETE FROM public.member_map_state')), '42501'));
  await check('fresh revision saves; older tab receives conflict', async () => {
    const result = await as('authenticated', A, tx => save(tx, 1, document()));
    assert.equal(Number(result.revision), 2);
    await rejected(as('authenticated', A, tx => save(tx, 1, document())), 'PT409');
  });
  await check('replayed initial save cannot overwrite existing data', () => rejected(
    as('authenticated', B, tx => save(tx, 0, document())), 'PT409'));

  const invalid = [
    ['owner field', d => { d.user_id = B; }],
    ['missing layouts', d => { delete d.layouts; }],
    ['four layouts', d => { d.layouts = Array.from({ length: 4 }, (_, i) => ({ ...d.layouts[0], map_key: `map-${i}` })); }],
    ['duplicate layout keys', d => { d.layouts.push(structuredClone(d.layouts[0])); }],
    ['unknown layout field', d => { d.layouts[0].news_body = 'not private state'; }],
    ['position outside bound', d => { d.layouts[0].positions[0].x = 1000001; }],
    ['duplicate positions', d => { d.layouts[0].positions.push(structuredClone(d.layouts[0].positions[0])); }],
    ['null anchor kind', d => { d.layouts[0].notes[0].anchor.kind = null; }],
    ['oversized note', d => { d.layouts[0].notes[0].text = 'x'.repeat(2001); }],
    ['boolean mark', d => { d.layouts[0].marks['event-1'] = true; }],
    ['zero read revision', d => { d.layouts[0].marks['event-1'].read_revision = 0; }],
    ['unsafe read revision', d => { d.layouts[0].marks['event-1'].read_revision = Number.MAX_SAFE_INTEGER; }],
    ['list disposition', d => { d.layouts[0].marks['event-1'].disposition = []; }],
    ['unknown disposition', d => { d.layouts[0].marks['event-1'].disposition = 'resolved'; }],
    ['over 64KB document', d => { d.layouts[0].notes = Array.from({ length: 50 }, (_, i) => ({ ...d.layouts[0].notes[0], note_id: `note-${i}`, text: 'x'.repeat(1800) })); }],
  ];
  for (const [name, mutate] of invalid) {
    await check(`RPC rejects ${name}`, async () => {
      const value = document(); mutate(value);
      await rejected(as('authenticated', A, tx => save(tx, 2, value)), '22023');
    });
  }
  await check('failed writes preserve revision and private note', async () => {
    const result = await as('authenticated', A, tx => tx.query('SELECT revision, document FROM public.member_map_state'));
    assert.equal(Number(result.rows[0].revision), 2);
    assert.deepEqual(result.rows[0].document, document());
  });
  await check('read and layout save never advance event cursor', async () => {
    await db.query('UPDATE public.member_map_state SET public_event_cursor_at=$1 WHERE user_id=$2',
      ['2026-09-26T00:00:00Z', A]);
    const before = await as('authenticated', A, tx => tx.query('SELECT public_event_cursor_at FROM public.member_map_state'));
    await as('authenticated', A, tx => save(tx, 2, document()));
    const after = await as('authenticated', A, tx => tx.query('SELECT public_event_cursor_at FROM public.member_map_state'));
    assert.equal(String(after.rows[0].public_event_cursor_at), String(before.rows[0].public_event_cursor_at));
  });
  // Compare API byte accounting with the PostgreSQL engine, not a JS imitation.
  const boundary = { layouts: [{ map_key: 'nest', positions: [], marks: {},
    notes: Array.from({ length: 33 }, (_, i) => ({ note_id: `n${i}`, anchor: null,
      x: 0, y: 0, text: 'x'.repeat(1905), done: false })),
  }] };
  const sizeOf = async wire => Number((await db.query(
    'SELECT octet_length($1::jsonb::text) AS bytes', [wire])).rows[0].bytes);
  const initialSize = await sizeOf(JSON.stringify(boundary));
  const vectors = [];
  for (const delta of [-1, 0, 1]) {
    const value = structuredClone(boundary);
    value.layouts[0].notes.at(-1).text = 'x'.repeat(1905 + 65536 + delta - initialSize);
    vectors.push([`JSONB byte boundary ${65536 + delta}`, JSON.stringify(value)]);
  }
  const special = document();
  special.layouts[0].notes[0].text = '한🙂\n"\\';
  for (const numeric of ['1e-7', '5e-324', '-0.0', '1.0']) {
    vectors.push([`Unicode and numeric ${numeric}`, JSON.stringify(special).replace('"x":-18.5', `"x":${numeric}`)]);
  }
  let bRevision = 1;
  for (const [name, wire] of vectors) {
    await check(name, async () => {
      const python = spawnSync('python3', ['-B', '-c', `
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('validation', sys.argv[1])
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
d = json.load(sys.stdin)
try:
    v.validate_document(d)
    accepted = True
except v.InvalidDocument:
    accepted = False
print(json.dumps({'bytes': v.document_storage_bytes(d), 'accepted': accepted,
                  'wire': json.dumps(d, ensure_ascii=False)}))
`, resolve(fileURLToPath(new URL('../vercel-api/api/member_map_state_validation.py', import.meta.url)))],
      { input: wire, encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
      assert.equal(python.status, 0, python.stderr);
      const api = JSON.parse(python.stdout);
      const bytes = await sizeOf(api.wire);
      assert.equal(api.bytes, bytes);
      assert.equal(api.accepted, bytes <= 65536);
      const call = () => as('authenticated', B, tx => tx.query(
        'SELECT public.save_member_map_state_v1($1::bigint, $2::jsonb) AS result', [bRevision, api.wire]));
      if (api.accepted) {
        const saved = (await call()).rows[0].result;
        assert.equal(saved.user_id, B);
        assert.equal(Number(saved.revision), ++bRevision);
        // JSONB normalizes -0 to 0; browser JSON serialization does the same.
        assert.deepEqual(saved.document, JSON.parse(JSON.stringify(JSON.parse(api.wire))));
      } else {
        await rejected(call(), '22023');
      }
    });
  }
  console.log(JSON.stringify({ engine, migrationSha256: createHash('sha256').update(migration).digest('hex'),
    passed: checks.filter(c => c.passed).length, total: checks.length, checks,
    limitations: ['Auth claims are fixtures, not live login', 'No PostgREST/browser test',
      'Single connection: no concurrent-transaction race test', 'No production database was connected'],
  }, null, 2));
  if (checks.some(c => !c.passed)) process.exitCode = 1;
} finally { await db.close(); }
