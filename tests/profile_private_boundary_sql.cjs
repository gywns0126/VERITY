// In-memory PostgreSQL only: synthetic profiles, no network, credentials, or installs.
// PGLITE_MODULE=/absolute/path/to/@electric-sql/pglite \
//   node tests/profile_private_boundary_sql.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { PGlite } = require(process.env.PGLITE_MODULE || '@electric-sql/pglite');

const migrationPath = path.join(__dirname, '../supabase/migrations/2026092801_profile_private_boundary.sql');
const migration = fs.readFileSync(migrationPath, 'utf8');
const verificationPath = path.join(__dirname, '../scripts/verify_profile_private_boundary.sql');
const verification = fs.readFileSync(verificationPath, 'utf8');
const digest = text => createHash('sha256').update(text).digest('hex');
const db = new PGlite();
const uid = n => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const member = uid(1), other = uid(2), admin = uid(3), superAdmin = uid(4);
const fresh = uid(5), missing = uid(99);
const cases = [];
const check = (name, fn) => cases.push({ name, fn });
const rows = async (sql, params = []) => (await db.query(sql, params)).rows;
const scalar = async (sql, params = []) => Object.values((await rows(sql, params))[0])[0];
const memberActors = [
  { name: 'member', role: 'authenticated', id: member },
  { name: 'admin', role: 'authenticated', id: admin },
  { name: 'super-admin', role: 'authenticated', id: superAdmin },
];
const serviceActor = { name: 'service-role', role: 'service_role', id: '' };
const deniedActors = [
  memberActors[0],
  { name: 'anon', role: 'anon', id: '' },
  { name: 'NULL role with member uid', role: 'authenticated', id: member, claim: null },
  { name: 'NULL role with admin uid', role: 'authenticated', id: admin, claim: null },
  { name: 'anon claim with admin uid', role: 'authenticated', id: admin, claim: 'anon' },
  { name: 'service DB role without JWT role', role: 'service_role', id: admin, claim: null },
];
const rpcs = [
  { name: 'admin_approve_profile', status: 'approved' },
  { name: 'admin_reject_profile', status: 'rejected' },
];

async function actor({ role = '', id = '', claim = role } = {}) {
  assert.ok(['', 'anon', 'authenticated', 'service_role', 'untrusted'].includes(role));
  await db.exec('RESET ROLE');
  await db.query(`SELECT set_config('request.jwt.claim.sub', $1, false),
    set_config('request.jwt.claim.role', $2, false)`, [id, claim ?? '']);
  if (role) await db.exec(`SET ROLE ${role}`);
}

async function denied(sql, params = []) {
  await assert.rejects(() => db.query(sql, params), error => error.code === '42501');
}

async function profiles() {
  await actor();
  return (await rows('SELECT to_jsonb(p) AS value FROM public.profiles p ORDER BY id')).map(row => row.value);
}

async function policies() {
  await actor();
  return rows(`SELECT policyname, permissive, roles, cmd, qual, with_check
    FROM pg_policies WHERE schemaname = 'public' AND tablename = 'profiles' ORDER BY policyname`);
}

async function preservedObjects() {
  await actor();
  return {
    triggers: await rows(`SELECT t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) AS definition,
      pg_get_functiondef(t.tgfoid) AS function_definition
      FROM pg_trigger t WHERE t.tgrelid = 'public.profiles'::regclass AND NOT t.tgisinternal ORDER BY t.tgname`),
    helper: await scalar("SELECT pg_get_functiondef('public.is_caller_admin()'::regprocedure)"),
    view: await scalar("SELECT pg_get_viewdef('public.public_profiles'::regclass, true)"),
    grants: await rows(`SELECT c.relname, c.relacl::text, c.relrowsecurity, c.relforcerowsecurity
      FROM pg_class c WHERE c.oid IN ('public.profiles'::regclass, 'public.public_profiles'::regclass)
      ORDER BY c.relname`),
    signatures: await rows(`SELECT p.oid, p.proname, p.proargnames, p.prosecdef, p.proconfig,
      pg_get_function_identity_arguments(p.oid) AS arguments, pg_get_function_result(p.oid) AS result
      FROM pg_proc p WHERE p.oid IN ('public.admin_approve_profile(uuid)'::regprocedure,
        'public.admin_reject_profile(uuid)'::regprocedure) ORDER BY p.proname`),
  };
}

async function rpc(name, target = other) {
  return scalar(`SELECT to_jsonb(public.${name}($1::uuid)) AS value`, [target]);
}

function assertMasked(value, stored) {
  // Derive the denominator from the actual row, including subsequently added columns.
  const expected = Object.fromEntries(Object.keys(stored).map(key =>
    [key, key === 'id' || key === 'status' ? stored[key] : null]));
  assert.deepEqual(value, expected);
  assert.deepEqual(Object.keys(value).filter(key => value[key] !== null).sort(), ['id', 'status']);
}

async function assertRpcTransition(caller, operation) {
  await actor(serviceActor);
  await db.query('UPDATE public.profiles SET status = $1 WHERE id = $2',
    [operation.status === 'approved' ? 'rejected' : 'approved', other]);
  const before = await profiles();
  await actor(caller);
  const value = await rpc(operation.name);
  const after = await profiles();
  assert.deepEqual(after, before.map(row => row.id === other ? { ...row, status: operation.status } : row));
  assertMasked(value, after.find(row => row.id === other));
}

async function withPermissivePolicy(fn) {
  await actor();
  await db.exec(`CREATE POLICY fixture_allow_everything ON public.profiles
    AS PERMISSIVE FOR ALL TO anon, authenticated USING (true) WITH CHECK (true)`);
  try { await fn(); }
  finally {
    await actor();
    await db.exec('DROP POLICY fixture_allow_everything ON public.profiles');
  }
}

async function setup() {
  // Self-contained fixture: do not import the untracked profile_security_sql.cjs.
  // Use the deployed column shape supplied for this change, NOT historical 003's updated_at.
  await db.exec(`
    CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
    CREATE ROLE untrusted;
    CREATE SCHEMA auth;
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
      SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$
      SELECT nullif(current_setting('request.jwt.claim.role', true), '') $$;
    GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role, untrusted;
    CREATE TABLE public.profiles (
      id uuid PRIMARY KEY, email text, display_name text, phone text, consent_given_at timestamptz,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
      created_at timestamptz DEFAULT now(), approved_at timestamptz, notes text,
      order_enabled boolean DEFAULT false, max_order_krw integer DEFAULT 10000000,
      daily_order_count_limit integer DEFAULT 50, is_admin boolean NOT NULL DEFAULT false,
      nickname text NOT NULL DEFAULT '', avatar text NOT NULL DEFAULT '', bio text NOT NULL DEFAULT '',
      is_banned boolean NOT NULL DEFAULT false, ban_reason text, banned_at timestamptz,
      is_super_admin boolean NOT NULL DEFAULT false, avatar_url text DEFAULT '', broker_slug text, seed_krw bigint
    );
    INSERT INTO public.profiles (
      id, email, display_name, phone, consent_given_at, status, created_at, approved_at, notes,
      order_enabled, max_order_krw, daily_order_count_limit, is_admin, nickname, avatar, bio,
      is_banned, ban_reason, banned_at, is_super_admin, avatar_url, broker_slug, seed_krw
    ) SELECT id, label || '@example.invalid', label, 'synthetic-phone', '2026-01-01Z',
      CASE WHEN admin_flag THEN 'approved' ELSE 'pending' END, '2026-01-01Z', '2026-01-02Z',
      'synthetic private note', true, 123456, 7, admin_flag, label, 'synthetic-avatar', 'synthetic-bio',
      false, 'synthetic restriction history', '2026-01-03Z', super_flag,
      'https://example.invalid/avatar', 'test_' || label, 987654
      FROM (VALUES ('${member}'::uuid, 'member', false, false), ('${other}'::uuid, 'other', false, false),
        ('${admin}'::uuid, 'admin', true, false), ('${superAdmin}'::uuid, 'owner', true, true))
        AS seed(id, label, admin_flag, super_flag);
    CREATE FUNCTION public.is_caller_admin() RETURNS boolean LANGUAGE plpgsql STABLE
      SECURITY DEFINER SET search_path = '' AS $$
      DECLARE result boolean; BEGIN
        IF auth.role() = 'service_role' THEN RETURN true; END IF;
        SELECT p.is_admin INTO result FROM public.profiles p WHERE p.id = auth.uid();
        RETURN coalesce(result, false);
      END $$;
    ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
    GRANT ALL ON public.profiles TO anon, authenticated, service_role;
    CREATE POLICY profiles_select_own ON public.profiles FOR SELECT USING (auth.uid() = id);
    CREATE POLICY profiles_select_admin ON public.profiles FOR SELECT TO authenticated USING (public.is_caller_admin());
    CREATE POLICY profiles_update_own ON public.profiles FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
    CREATE POLICY profiles_update_admin ON public.profiles FOR UPDATE TO authenticated
      USING (public.is_caller_admin()) WITH CHECK (public.is_caller_admin());
    CREATE POLICY profiles_insert_own ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);
    CREATE POLICY "users can insert own profile" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);
    CREATE POLICY "users can view own profile" ON public.profiles FOR SELECT USING (auth.uid() = id);
    -- Representative pre-existing guards. The migration must leave both bindings and bodies intact.
    CREATE FUNCTION public.profiles_block_self_status_change() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = '' AS $$ BEGIN
      IF NEW.status IS DISTINCT FROM OLD.status AND NOT coalesce(auth.role() = 'service_role'
        OR (auth.role() = 'authenticated' AND public.is_caller_admin()), false) THEN
        RAISE EXCEPTION 'status denied' USING ERRCODE = '42501';
      END IF;
      RETURN NEW; END $$;
    CREATE TRIGGER profiles_block_self_status BEFORE UPDATE ON public.profiles
      FOR EACH ROW EXECUTE FUNCTION public.profiles_block_self_status_change();
    CREATE FUNCTION public.profiles_block_privileged_change() RETURNS trigger LANGUAGE plpgsql
      SECURITY DEFINER SET search_path = '' AS $$ BEGIN
      IF auth.role() = 'service_role' THEN RETURN NEW; END IF;
      IF TG_OP = 'INSERT' THEN
        IF NEW.is_admin OR NEW.is_super_admin OR NEW.is_banned OR NEW.order_enabled
          OR NEW.broker_slug IS NOT NULL OR NEW.status <> 'pending' THEN
          RAISE EXCEPTION 'privileged insert denied' USING ERRCODE = '42501';
        END IF;
      ELSE
        IF ROW(NEW.is_admin, NEW.is_super_admin, NEW.order_enabled, NEW.max_order_krw,
          NEW.daily_order_count_limit, NEW.broker_slug) IS DISTINCT FROM
          ROW(OLD.is_admin, OLD.is_super_admin, OLD.order_enabled, OLD.max_order_krw,
          OLD.daily_order_count_limit, OLD.broker_slug) THEN
          RAISE EXCEPTION 'privileged update denied' USING ERRCODE = '42501';
        END IF;
      END IF;
      RETURN NEW; END $$;
    CREATE TRIGGER trg_block_privileged_profile BEFORE INSERT OR UPDATE ON public.profiles
      FOR EACH ROW EXECUTE FUNCTION public.profiles_block_privileged_change();
    CREATE VIEW public.public_profiles AS SELECT id, nickname, avatar, bio FROM public.profiles WHERE nickname <> '';
    GRANT SELECT ON public.public_profiles TO anon, authenticated, service_role;
  `);
  for (const operation of rpcs) {
    // A legacy full-row RPC reproduces the response leak without depending on historical SQL.
    await db.exec(`CREATE FUNCTION public.${operation.name}(target_id uuid) RETURNS public.profiles
      LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
      DECLARE result public.profiles; BEGIN
        IF auth.role() <> 'service_role' AND NOT public.is_caller_admin() THEN
          RAISE EXCEPTION 'legacy permission denied' USING ERRCODE = '42501';
        END IF;
        UPDATE public.profiles SET status = '${operation.status}' WHERE id = target_id RETURNING * INTO result;
        RETURN result;
      END $$;
      GRANT EXECUTE ON FUNCTION public.${operation.name}(uuid) TO anon, authenticated, service_role`);
  }
}

check('fixture has four synthetic full rows and no updated_at column', async () => {
  const seeded = await profiles();
  assert.equal(seeded.length, 4);
  for (const row of seeded) {
    assert.equal(Object.hasOwn(row, 'updated_at'), false);
    assert.ok(Object.values(row).every(value => value !== null));
  }
});

for (const caller of memberActors.slice(1)) check(`before: ${caller.name} can read another raw financial profile`, async () => {
  await actor(caller);
  assert.equal(await scalar('SELECT count(*)::int FROM public.profiles'), 4);
  assert.deepEqual(await rows('SELECT broker_slug, seed_krw FROM public.profiles WHERE id = $1', [other]),
    [{ broker_slug: 'test_other', seed_krw: 987654 }]);
});

for (const operation of rpcs) check(`before: ${operation.name} leaks the private row`, async () => {
  await actor(memberActors[1]);
  const value = await rpc(operation.name);
  assert.equal(value.id, other);
  assert.equal(value.status, operation.status);
  assert.equal(value.broker_slug, 'test_other');
  assert.equal(value.seed_krw, 987654);
  assert.equal(value.notes, 'synthetic private note');
  await actor(serviceActor);
  await db.query("UPDATE public.profiles SET status = 'pending' WHERE id = $1", [other]);
});

check('actual migration applies twice, preserves data, seven policies, triggers, helper, view and signatures', async () => {
  const beforeData = await profiles();
  const beforePolicies = await policies();
  const beforeObjects = await preservedObjects();
  assert.equal(beforePolicies.length, 7);
  assert.equal(beforeObjects.triggers.length, 2);
  assert.equal(beforeObjects.signatures.length, 2);
  let firstPolicies;
  for (let pass = 0; pass < 2; pass++) {
    await actor();
    await db.exec(migration);
    assert.deepEqual(await profiles(), beforeData);
    assert.deepEqual(await preservedObjects(), beforeObjects);
    const current = await policies();
    assert.equal(current.length, 8);
    assert.deepEqual(current.filter(policy => policy.policyname !== 'profiles_private_row_boundary'), beforePolicies);
    if (pass === 0) firstPolicies = current;
    else assert.deepEqual(current, firstPolicies);
  }
});

check('private boundary is restrictive FOR ALL on anon/authenticated with matching USING/WITH CHECK', async () => {
  const boundary = (await policies()).find(policy => policy.policyname === 'profiles_private_row_boundary');
  assert.equal(boundary.permissive, 'RESTRICTIVE');
  assert.equal(boundary.cmd, 'ALL');
  assert.deepEqual(boundary.roles, ['anon', 'authenticated']);
  assert.equal(boundary.qual, boundary.with_check);
  assert.match(boundary.qual, /auth\.role\(\) = 'authenticated'/);
  assert.match(boundary.qual, /auth\.uid\(\) = id/);
});

for (const caller of memberActors) check(`${caller.name} raw SELECT returns only their own full row`, async () => {
  const own = (await profiles()).find(row => row.id === caller.id);
  await actor(caller);
  assert.deepEqual(await rows('SELECT * FROM public.profiles WHERE id = $1', [other]), []);
  assert.deepEqual((await rows('SELECT to_jsonb(p) AS value FROM public.profiles p')).map(row => row.value), [own]);
  assert.equal(await scalar('SELECT public.is_caller_admin()'), caller.name !== 'member');
});

for (const caller of memberActors) check(`${caller.name} cannot UPDATE another row through existing admin/own policies`, async () => {
  const before = await profiles();
  await actor(caller);
  assert.deepEqual(await rows("UPDATE public.profiles SET nickname = 'unauthorized' WHERE id = $1 RETURNING id", [other]), []);
  assert.deepEqual(await profiles(), before);
});

for (const caller of [
  { name: 'anon even with matching uid', role: 'anon', id: member },
  { name: 'NULL role even with admin uid', role: 'authenticated', id: admin, claim: null },
  { name: 'authenticated without uid', role: 'authenticated', id: '' },
]) check(`${caller.name} cannot read, update, or insert raw profiles`, async () => {
  const before = await profiles();
  await actor(caller);
  assert.deepEqual(await rows('SELECT * FROM public.profiles'), []);
  assert.deepEqual(await rows("UPDATE public.profiles SET nickname = 'bad' RETURNING id"), []);
  await actor({ ...caller, id: caller.id ? fresh : '' });
  await denied('INSERT INTO public.profiles(id) VALUES ($1)', [fresh]);
  assert.deepEqual(await profiles(), before);
});

check('member can edit own presentation, contact and seed fields', async () => {
  await actor(memberActors[0]);
  assert.deepEqual(await rows(`UPDATE public.profiles SET nickname = 'edited', display_name = 'Synthetic Member',
    avatar = 'new-avatar', bio = 'study', phone = 'synthetic-edited', seed_krw = 4321 WHERE id = $1
    RETURNING nickname, display_name, avatar, bio, phone, seed_krw`, [member]), [{ nickname: 'edited',
    display_name: 'Synthetic Member', avatar: 'new-avatar', bio: 'study', phone: 'synthetic-edited', seed_krw: 4321 }]);
});

check('normal own INSERT and ignore-duplicates signup remain valid', async () => {
  await actor({ role: 'authenticated', id: fresh });
  await db.query(`INSERT INTO public.profiles(id, email, nickname, status) VALUES ($1, 'fresh@example.invalid', 'fresh', 'pending')
    ON CONFLICT (id) DO NOTHING`, [fresh]);
  await db.query('INSERT INTO public.profiles(id) VALUES ($1) ON CONFLICT (id) DO NOTHING', [fresh]);
  assert.deepEqual(await rows('SELECT id, status, is_admin, is_super_admin, order_enabled FROM public.profiles'),
    [{ id: fresh, status: 'pending', is_admin: false, is_super_admin: false, order_enabled: false }]);
});

check('existing status and privilege guards still deny member elevation', async () => {
  const before = await profiles();
  await actor(memberActors[0]);
  await denied("UPDATE public.profiles SET status = 'approved' WHERE id = $1", [member]);
  await denied('UPDATE public.profiles SET is_admin = true WHERE id = $1', [member]);
  await actor({ role: 'authenticated', id: missing });
  await denied('INSERT INTO public.profiles(id, is_admin) VALUES ($1, true)', [missing]);
  assert.deepEqual(await profiles(), before);
});

for (const caller of memberActors.slice(1)) check(`${caller.name} still cannot change own privileged routing`, async () => {
  const before = await profiles();
  await actor(caller);
  await denied("UPDATE public.profiles SET broker_slug = 'test_escalated' WHERE id = $1", [caller.id]);
  await denied('UPDATE public.profiles SET is_super_admin = NOT is_super_admin WHERE id = $1', [caller.id]);
  assert.deepEqual(await profiles(), before);
});

for (const caller of [...memberActors,
  { name: 'anon', role: 'anon', id: member },
  { name: 'NULL role', role: 'authenticated', id: admin, claim: null },
]) check(`additional permissive ALL policy cannot bypass ${caller.name} row boundary`, async () => {
  const before = await profiles();
  await withPermissivePolicy(async () => {
    await actor(caller);
    const allowed = caller.role === 'authenticated' && caller.claim !== null;
    assert.deepEqual(await rows('SELECT id FROM public.profiles ORDER BY id'), allowed ? [{ id: caller.id }] : []);
    assert.deepEqual(await rows("UPDATE public.profiles SET nickname = 'bypass' WHERE id = $1 RETURNING id", [other]), []);
    assert.deepEqual(await rows('DELETE FROM public.profiles WHERE id = $1 RETURNING id', [other]), []);
    await denied('INSERT INTO public.profiles(id) VALUES ($1)', [missing]);
    if (allowed) {
      // USING can pass on the old row; WITH CHECK must reject moving it to another owner.
      await denied('UPDATE public.profiles SET id = $1 WHERE id = $2', [missing, caller.id]);
    }
  });
  assert.deepEqual(await profiles(), before);
});

check('service-role admin API database path retains cross-row SELECT and CRUD', async () => {
  const before = await profiles();
  await actor(serviceActor);
  assert.equal(await scalar('SELECT count(*)::int FROM public.profiles'), before.length);
  assert.equal(await scalar('SELECT broker_slug FROM public.profiles WHERE id = $1', [other]), 'test_other');
  await db.exec('BEGIN');
  try {
    assert.deepEqual(await rows(`UPDATE public.profiles SET is_banned = true, ban_reason = 'synthetic admin route',
      is_admin = true, broker_slug = 'test_service' WHERE id = $1 RETURNING id, is_banned, is_admin, broker_slug`, [other]),
    [{ id: other, is_banned: true, is_admin: true, broker_slug: 'test_service' }]);
    await db.query("INSERT INTO public.profiles(id, status, is_admin) VALUES ($1, 'approved', true)", [missing]);
    assert.deepEqual(await rows('DELETE FROM public.profiles WHERE id = $1 RETURNING id', [missing]), [{ id: missing }]);
  } finally { await db.exec('ROLLBACK'); }
  assert.deepEqual(await profiles(), before);
});

for (const operation of rpcs) {
  check(`${operation.name} signature and ACL allow only authenticated/service execution`, async () => {
    await actor();
    const signature = `public.${operation.name}(uuid)`;
    assert.equal(await scalar('SELECT pg_get_function_result($1::regprocedure)', [signature]), 'profiles');
    for (const role of ['authenticated', 'service_role', 'anon', 'untrusted']) {
      assert.equal(await scalar("SELECT has_function_privilege($1, $2, 'EXECUTE')", [role, signature]),
        role === 'authenticated' || role === 'service_role', role);
    }
    assert.equal(await scalar(`SELECT count(*)::int FROM pg_proc p,
      LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
      WHERE p.oid = $1::regprocedure AND a.grantee = 0 AND a.privilege_type = 'EXECUTE'`, [signature]), 0);
    assert.doesNotMatch(await scalar('SELECT pg_get_functiondef($1::regprocedure)', [signature]), /\bupdated_at\b/i);
  });
  for (const caller of [...memberActors.slice(1), serviceActor]) {
    check(`${caller.name} ${operation.name}: status only changes, only id/status returned`,
      () => assertRpcTransition(caller, operation));
  }
  for (const caller of deniedActors) check(`${operation.name} denies ${caller.name} without changing data`, async () => {
    const before = await profiles();
    await actor(caller);
    await denied(`SELECT public.${operation.name}($1::uuid)`, [other]);
    assert.deepEqual(await profiles(), before);
  });
  for (const caller of [memberActors[1], serviceActor]) check(`${operation.name} missing/NULL target returns SQL NULL for ${caller.name}`, async () => {
    const before = await profiles();
    await actor(caller);
    assert.equal(await rpc(operation.name, missing), null);
    assert.equal(await rpc(operation.name, null), null);
    assert.deepEqual(await profiles(), before);
  });
}

check('add future private fields with non-NULL defaults after RPCs have already run', async () => {
  await actor();
  await db.exec(`ALTER TABLE public.profiles
    ADD COLUMN future_private_text text NOT NULL DEFAULT 'synthetic future secret',
    ADD COLUMN future_private_json jsonb NOT NULL DEFAULT '{"account":"synthetic"}',
    ADD COLUMN future_private_flag boolean NOT NULL DEFAULT true`);
  const target = (await profiles()).find(row => row.id === other);
  assert.equal(target.future_private_text, 'synthetic future secret');
  assert.deepEqual(target.future_private_json, { account: 'synthetic' });
  assert.equal(target.future_private_flag, true);
});

for (const operation of rpcs) for (const caller of [memberActors[1], serviceActor]) {
  check(`${caller.name} ${operation.name} masks every future private column too`, () => assertRpcTransition(caller, operation));
}

for (const caller of [{ name: 'anon', role: 'anon' }, ...memberActors,
  { name: 'NULL role', role: 'authenticated', id: admin, claim: null }, serviceActor,
]) check(`public safe view stays readable by ${caller.name} without private columns`, async () => {
  await actor();
  const expected = await rows("SELECT id, nickname, avatar, bio FROM public.profiles WHERE nickname <> '' ORDER BY id");
  await actor(caller);
  const visible = await rows('SELECT * FROM public.public_profiles ORDER BY id');
  assert.deepEqual(visible, expected);
  assert.ok(visible.length > 1);
  for (const row of visible) assert.deepEqual(Object.keys(row).sort(), ['avatar', 'bio', 'id', 'nickname']);
});

check('read-only acceptance script passes its seven role/grant checks on the synthetic fixture', async () => {
  const before = await profiles();
  const results = await db.exec(verification);
  const reports = results.flatMap(result => result.rows).filter(row => Object.hasOwn(row, 'checks'));
  assert.equal(reports.length, 1);
  const checks = reports[0].checks;
  assert.deepEqual(checks.map(result => result.case).sort(),
    ['admin_server', 'anon_and_public_view', 'deputy', 'member', 'missing_role', 'owner', 'rpc_grants']);
  for (const result of checks) assert.equal(result.pass, true, result.case);
  assert.deepEqual(await profiles(), before);
});

check('SQL source files stayed unchanged during the run', async () => {
  assert.equal(digest(fs.readFileSync(migrationPath, 'utf8')), digest(migration));
  assert.equal(digest(fs.readFileSync(verificationPath, 'utf8')), digest(verification));
});

(async () => {
  let passed = 0;
  try {
    await setup();
    console.log(`Migration: ${migrationPath}\nSHA-256: ${digest(migration)}`);
    for (const { name, fn } of cases) {
      try { await fn(); }
      catch (error) { console.error(`FAIL ${name}`); throw error; }
      passed++;
      console.log(`PASS ${name}`);
    }
  } finally {
    console.log(`Profile private-boundary SQL: ${passed}/${cases.length} passed`);
    await db.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
