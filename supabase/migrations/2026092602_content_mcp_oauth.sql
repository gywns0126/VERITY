-- Private, read-only OAuth authorization; independent of the unapplied access draft.
-- Store lowercase SHA-256 hex digests only, never invites, codes, access tokens,
-- client secrets or PKCE verifiers. code_challenge is the public S256 challenge.
-- The HTTP layer validates redirect/resource registration and computes S256 before
-- exchange; these service-only RPCs enforce the exact persisted bindings.
begin;

-- Serialize reapplication. Never silently accept a different table definition.
select pg_catalog.pg_advisory_xact_lock(2026092602);
do $schema$
declare
    table_name text;
    definition text;
    target_oid oid;
    expected_oid oid;
    target_signature jsonb;
    expected_signature jsonb;
    relation_oid oid;
    signature jsonb;
begin
    for table_name, definition in select * from (values
        ('content_mcp_invites', $ddl$
            invite_hash text primary key check (invite_hash ~ '^[0-9a-f]{64}$'),
            label text not null check (length(label) between 1 and 80),
            expires_at timestamptz not null check (pg_catalog.isfinite(expires_at)),
            revoked_at timestamptz,
            minute_start timestamptz not null default '-infinity',
            minute_used integer not null default 0 check (minute_used between 0 and 10),
            day_start timestamptz not null default '-infinity',
            day_used integer not null default 0 check (day_used between 0 and 100)
        $ddl$),
        ('content_mcp_codes', $ddl$
            code_hash text primary key check (code_hash ~ '^[0-9a-f]{64}$'),
            invite_hash text not null references @schema@.content_mcp_invites(invite_hash),
            client_id text not null check (length(client_id) between 1 and 256
                and client_id !~ '[[:space:][:cntrl:]]'),
            redirect_uri text not null check (length(redirect_uri) between 1 and 2048
                and redirect_uri !~ '[[:space:][:cntrl:]]'),
            resource text not null check (length(resource) between 1 and 2048
                and resource !~ '[[:space:][:cntrl:]]'),
            scope text not null check (scope = 'content:read'),
            code_challenge text not null check (code_challenge ~ '^[A-Za-z0-9_-]{43}$'),
            expires_at timestamptz not null check (pg_catalog.isfinite(expires_at)),
            used_at timestamptz
        $ddl$),
        ('content_mcp_tokens', $ddl$
            token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
            invite_hash text not null references @schema@.content_mcp_invites(invite_hash),
            client_id text not null check (length(client_id) between 1 and 256
                and client_id !~ '[[:space:][:cntrl:]]'),
            resource text not null check (length(resource) between 1 and 2048
                and resource !~ '[[:space:][:cntrl:]]'),
            scope text not null check (scope = 'content:read'),
            expires_at timestamptz not null check (pg_catalog.isfinite(expires_at)),
            revoked_at timestamptz
        $ddl$)
    ) as definitions(name, body) loop
        execute pg_catalog.format('create temporary table pg_temp.%I (%s) on commit drop',
            table_name, pg_catalog.replace(definition, '@schema@', 'pg_temp'));
        execute pg_catalog.format('alter table pg_temp.%I enable row level security', table_name);
        execute pg_catalog.format('revoke all on pg_temp.%I from public, anon, authenticated, service_role', table_name);
        execute pg_catalog.format('create table if not exists public.%I (%s)',
            table_name, pg_catalog.replace(definition, '@schema@', 'public'));
        target_oid := pg_catalog.to_regclass('public.' || table_name);
        expected_oid := pg_catalog.to_regclass('pg_temp.' || table_name);
        execute pg_catalog.format('lock table public.%I in access exclusive mode', table_name);

        -- Compare parsed definitions, not merely column names or IF NOT EXISTS.
        foreach relation_oid in array array[target_oid, expected_oid] loop
            select pg_catalog.jsonb_build_object(
                'columns', (select pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
                    a.attname, a.atttypid, a.atttypmod, a.attnotnull, a.attcollation,
                    a.attidentity, a.attgenerated,
                    case when d.adbin is not null then pg_catalog.pg_get_expr(d.adbin, d.adrelid) end
                ) order by a.attnum)
                    from pg_catalog.pg_attribute a
                    left join pg_catalog.pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
                    where a.attrelid = relation_oid and a.attnum > 0 and not a.attisdropped),
                'constraints', (select pg_catalog.jsonb_agg(item order by item::text) from (
                    select pg_catalog.jsonb_build_array(c.contype, c.conkey, c.confkey,
                        c.condeferrable, c.condeferred, c.convalidated, c.connoinherit,
                        c.confupdtype, c.confdeltype, c.confmatchtype, r.relname,
                        -- Primary/foreign keys have no expression; compare their
                        -- key columns and FK metadata above, without deparsing NULL.
                        case when c.conbin is not null then
                            pg_catalog.pg_get_expr(c.conbin, c.conrelid) end) as item
                    from pg_catalog.pg_constraint c
                    left join pg_catalog.pg_class r on r.oid = c.confrelid
                    where c.conrelid = relation_oid
                ) as constraints)
            ) into signature;
            if relation_oid = target_oid then target_signature := signature;
            else expected_signature := signature;
            end if;
        end loop;
        if target_signature is distinct from expected_signature
            or exists (select 1 from pg_catalog.pg_class c where c.oid = target_oid
                and (c.relkind <> 'r' or c.relpersistence <> 'p' or c.relispartition
                    or c.relowner <> (select oid from pg_catalog.pg_roles where rolname = current_user)))
            or exists (select 1 from pg_catalog.pg_inherits where inhrelid = target_oid or inhparent = target_oid)
            or exists (select 1 from pg_catalog.pg_policy where polrelid = target_oid)
            or exists (select 1 from pg_catalog.pg_trigger where tgrelid = target_oid and not tgisinternal)
            or exists (select 1 from pg_catalog.pg_rewrite where ev_class = target_oid)
            or exists (select 1 from pg_catalog.pg_attribute where attrelid = target_oid and attacl is not null)
            or exists (select 1 from pg_catalog.pg_constraint c where c.conrelid = target_oid
                and c.contype = 'f' and c.confrelid <>
                    'public.content_mcp_invites'::pg_catalog.regclass)
            or exists (select 1 from pg_catalog.pg_index i where i.indrelid = target_oid
                and (not i.indisvalid or not i.indisready or not exists (
                    select 1 from pg_catalog.pg_constraint c where c.conindid = i.indexrelid)))
            or exists (select 1 from pg_catalog.pg_class c,
                lateral pg_catalog.aclexplode(c.relacl) acl
                where c.oid = target_oid and acl.grantee <> c.relowner and acl.grantee <> 0
                    and acl.grantee not in (select oid from pg_catalog.pg_roles
                        where rolname in ('anon', 'authenticated', 'service_role')))
        then
            raise exception 'Incompatible public.% definition; migration aborted', table_name;
        end if;
    end loop;
end;
$schema$;

alter table public.content_mcp_invites enable row level security;
alter table public.content_mcp_codes enable row level security;
alter table public.content_mcp_tokens enable row level security;
revoke all on public.content_mcp_invites, public.content_mcp_codes, public.content_mcp_tokens
    from public, anon, authenticated, service_role;
grant select, insert, update, delete
    on public.content_mcp_invites, public.content_mcp_codes, public.content_mcp_tokens to service_role;

-- Reapplication accepts identical RPC definitions only. Any changed definition,
-- signature or unexpected overload aborts this transaction without replacing it.
create temporary table content_mcp_oauth_previous_functions on commit drop as
    select p.oid, pg_catalog.pg_get_functiondef(p.oid) as definition
    from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname in
        ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token');
alter table pg_temp.content_mcp_oauth_previous_functions enable row level security;
revoke all on pg_temp.content_mcp_oauth_previous_functions from public, anon, authenticated, service_role;

create or replace function public.content_mcp_issue_code(
    p_invite_hash text, p_code_hash text, p_client_id text, p_redirect_uri text,
    p_resource text, p_scope text, p_code_challenge text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    invitation public.content_mcp_invites%rowtype;
    checked_at timestamptz;
begin
    if p_invite_hash is null or p_invite_hash !~ '^[0-9a-f]{64}$'
        or p_code_hash is null or p_code_hash !~ '^[0-9a-f]{64}$'
        or p_client_id is null or length(p_client_id) not between 1 and 256
        or p_client_id ~ '[[:space:][:cntrl:]]'
        or p_redirect_uri is null or length(p_redirect_uri) not between 1 and 2048
        or p_redirect_uri ~ '[[:space:][:cntrl:]]'
        or p_resource is null or length(p_resource) not between 1 and 2048
        or p_resource ~ '[[:space:][:cntrl:]]'
        or p_scope is distinct from 'content:read'
        or p_code_challenge is null or p_code_challenge !~ '^[A-Za-z0-9_-]{43}$'
    then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;

    select * into invitation from public.content_mcp_invites
        where invite_hash = p_invite_hash for update;
    checked_at := pg_catalog.clock_timestamp();
    if not found or invitation.revoked_at is not null or invitation.expires_at <= checked_at then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    -- Opportunistic, invite-local retention and a bounded pending authorization
    -- set. Pruning uses the same invite -> code -> token lock order as the RPCs.
    delete from public.content_mcp_codes
        where invite_hash = p_invite_hash and expires_at <= checked_at;
    delete from public.content_mcp_tokens
        where invite_hash = p_invite_hash and expires_at <= checked_at;
    checked_at := pg_catalog.clock_timestamp(); -- Pruning can also wait for locks.
    if invitation.expires_at <= checked_at then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    if (select count(*) from public.content_mcp_codes where invite_hash = p_invite_hash
        and used_at is null and expires_at > checked_at) >= 5 then
        return pg_catalog.jsonb_build_object('status', 'limited');
    end if;
    -- A pending-code cap alone can be bypassed by repeated issue/exchange cycles.
    if (select count(*) from public.content_mcp_tokens where invite_hash = p_invite_hash
        and revoked_at is null and expires_at > checked_at) >= 5 then
        return pg_catalog.jsonb_build_object('status', 'limited');
    end if;
    insert into public.content_mcp_codes
        (code_hash, invite_hash, client_id, redirect_uri, resource, scope, code_challenge, expires_at)
    values (p_code_hash, p_invite_hash, p_client_id, p_redirect_uri, p_resource,
        p_scope, p_code_challenge, least(checked_at + interval '5 minutes', invitation.expires_at));
    return pg_catalog.jsonb_build_object('status', 'allowed');
exception when unique_violation then
    -- Never overwrite an existing code, including one that has already been used.
    return pg_catalog.jsonb_build_object('status', 'denied');
end;
$function$;

create or replace function public.content_mcp_exchange_code(
    p_code_hash text, p_client_id text, p_redirect_uri text, p_resource text,
    p_scope text, p_code_challenge text, p_token_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    parent_hash text;
    invitation public.content_mcp_invites%rowtype;
    issued_code public.content_mcp_codes%rowtype;
    checked_at timestamptz;
    lifetime integer;
begin
    if p_code_hash is null or p_code_hash !~ '^[0-9a-f]{64}$'
        or p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
        or p_client_id is null or length(p_client_id) not between 1 and 256
        or p_client_id ~ '[[:space:][:cntrl:]]'
        or p_redirect_uri is null or length(p_redirect_uri) not between 1 and 2048
        or p_redirect_uri ~ '[[:space:][:cntrl:]]'
        or p_resource is null or length(p_resource) not between 1 and 2048
        or p_resource ~ '[[:space:][:cntrl:]]'
        or p_scope is distinct from 'content:read'
        or p_code_challenge is null or p_code_challenge !~ '^[A-Za-z0-9_-]{43}$'
    then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;

    -- Unlocked lookup discovers the parent only. Authorization is checked again
    -- under locks, always in invite -> code/token order (also for admin batches).
    select invite_hash into parent_hash from public.content_mcp_codes where code_hash = p_code_hash;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select * into invitation from public.content_mcp_invites where invite_hash = parent_hash for update;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select * into issued_code from public.content_mcp_codes where code_hash = p_code_hash for update;
    checked_at := pg_catalog.clock_timestamp();
    if not found or issued_code.invite_hash is distinct from parent_hash
        or issued_code.used_at is not null or issued_code.expires_at <= checked_at
        or invitation.revoked_at is not null or invitation.expires_at <= checked_at
        or issued_code.client_id is distinct from p_client_id
        or issued_code.redirect_uri is distinct from p_redirect_uri
        or issued_code.resource is distinct from p_resource
        or issued_code.scope is distinct from p_scope
        or issued_code.code_challenge is distinct from p_code_challenge
    then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;

    -- Recheck under the same invite lock: codes issued before the fifth token
    -- must not create a sixth. A denied exchange leaves the code unused.
    if (select count(*) from public.content_mcp_tokens where invite_hash = parent_hash
        and revoked_at is null and expires_at > checked_at) >= 5 then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;

    -- Normally 3600; never advertise a lifetime beyond the invite's expiration.
    lifetime := least(3600, pg_catalog.floor(extract(epoch from (invitation.expires_at - checked_at))))::integer;
    if lifetime < 1 then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    update public.content_mcp_codes set used_at = checked_at where code_hash = p_code_hash;
    insert into public.content_mcp_tokens
        (token_hash, invite_hash, client_id, resource, scope, expires_at)
    values (p_token_hash, parent_hash, p_client_id, p_resource, p_scope,
        least(checked_at + interval '1 hour', invitation.expires_at));
    return pg_catalog.jsonb_build_object('status', 'allowed', 'expires_in', lifetime);
exception when unique_violation then
    -- This exception block rolls back BOTH the used_at update and token insert.
    return pg_catalog.jsonb_build_object('status', 'denied');
end;
$function$;

create or replace function public.content_mcp_consume_token(
    p_token_hash text, p_resource text, p_scope text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    parent_hash text;
    invitation public.content_mcp_invites%rowtype;
    credential public.content_mcp_tokens%rowtype;
    checked_at timestamptz;
    minute_count integer;
    day_count integer;
    reset_minute boolean;
    reset_day boolean;
begin
    if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
        or p_resource is null or length(p_resource) not between 1 and 2048
        or p_resource ~ '[[:space:][:cntrl:]]'
        or p_scope is distinct from 'content:read'
    then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    select invite_hash into parent_hash from public.content_mcp_tokens where token_hash = p_token_hash;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select * into invitation from public.content_mcp_invites where invite_hash = parent_hash for update;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    -- Re-read and lock the token AFTER waiting for the invite: a concurrent
    -- revocation/deletion/rebinding cannot slip through an earlier token snapshot.
    select * into credential from public.content_mcp_tokens where token_hash = p_token_hash for update;
    checked_at := pg_catalog.clock_timestamp();
    if not found or credential.invite_hash is distinct from parent_hash
        or credential.revoked_at is not null or credential.expires_at <= checked_at
        or invitation.revoked_at is not null or invitation.expires_at <= checked_at
        or credential.resource is distinct from p_resource
        or credential.scope is distinct from p_scope
    then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;

    -- Elapsed windows anchored to the first accepted request, not UTC minute/day
    -- boundaries. Two counters do not represent an exact sliding event history.
    -- All tokens for an invite share these counters; denied/limited calls use none.
    reset_minute := invitation.minute_start + interval '1 minute' <= checked_at;
    reset_day := invitation.day_start + interval '24 hours' <= checked_at;
    minute_count := case when reset_minute then 1 else invitation.minute_used + 1 end;
    day_count := case when reset_day then 1 else invitation.day_used + 1 end;
    if minute_count > 10 or day_count > 100 then
        return pg_catalog.jsonb_build_object('status', 'limited');
    end if;
    update public.content_mcp_invites set
        minute_start = case when reset_minute then checked_at else minute_start end,
        minute_used = minute_count,
        day_start = case when reset_day then checked_at else day_start end,
        day_used = day_count
    where invite_hash = parent_hash;
    return pg_catalog.jsonb_build_object('status', 'allowed');
end;
$function$;

do $rpc_guard$
begin
    if exists (select 1 from pg_temp.content_mcp_oauth_previous_functions old
        where old.definition is distinct from pg_catalog.pg_get_functiondef(old.oid))
        or (select count(*) from pg_catalog.pg_proc p
            join pg_catalog.pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.proname in
                ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token')) <> 3
        or exists (select 1 from pg_catalog.pg_proc p
            join pg_catalog.pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.proname in
                ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token')
                and p.proowner <> (select oid from pg_catalog.pg_roles where rolname = current_user))
        or exists (select 1 from pg_catalog.pg_proc p
            join pg_catalog.pg_namespace n on n.oid = p.pronamespace,
            lateral pg_catalog.aclexplode(p.proacl) acl
            where n.nspname = 'public' and p.proname in
                ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token')
                and acl.grantee <> p.proowner and acl.grantee <> 0
                and acl.grantee not in (select oid from pg_catalog.pg_roles
                    where rolname in ('anon', 'authenticated', 'service_role')))
    then
        raise exception 'Incompatible content MCP OAuth RPC definition or grants; migration aborted';
    end if;
end;
$rpc_guard$;

revoke all on function public.content_mcp_issue_code(text, text, text, text, text, text, text)
    from public, anon, authenticated, service_role;
revoke all on function public.content_mcp_exchange_code(text, text, text, text, text, text, text)
    from public, anon, authenticated, service_role;
revoke all on function public.content_mcp_consume_token(text, text, text)
    from public, anon, authenticated, service_role;
grant execute on function public.content_mcp_issue_code(text, text, text, text, text, text, text) to service_role;
grant execute on function public.content_mcp_exchange_code(text, text, text, text, text, text, text) to service_role;
grant execute on function public.content_mcp_consume_token(text, text, text) to service_role;

comment on table public.content_mcp_invites is
    'Private OAuth invites: SHA-256 hashes only. Revoke via service_role. Lock invites before child codes/tokens in multi-row administration.';
comment on table public.content_mcp_codes is
    'Single-use OAuth codes; S256 challenge only, never verifiers. Issue prunes expired rows for its invite and caps active unused codes at five. Manually prune other expired rows with service_role; no new cron.';
comment on table public.content_mcp_tokens is
    'OAuth access-token hashes, at most one hour and bounded by invite expiry; no refresh tokens. Issue and exchange cap active unrevoked tokens at five per invite. Issue prunes expired rows for its invite. Manually prune other expired rows with service_role; delete children before invites. No new cron.';

commit;
