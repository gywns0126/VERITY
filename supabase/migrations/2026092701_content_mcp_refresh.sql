-- Additive rotating refresh credentials. Apply after 2026092602_content_mcp_oauth.
-- Existing tables/RPC definitions are deliberately unchanged. This migration is
-- fail-closed on reapplication/name collisions (no IF NOT EXISTS / OR REPLACE).
-- Hashes only: HTTP generates fresh random credentials and sends SHA-256 digests.
-- HTTP validates registration; this wrapper also enforces exact callback/client
-- pairs plus the redirect + S256 challenge persisted by the original issuer.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(2026092701);
do $guard$
begin
    if exists (select 1 from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname in ('content_mcp_exchange_code_refresh', 'content_mcp_rotate_refresh')) then
        raise exception 'Refresh RPC already exists; refusing replacement or overload';
    end if;
end;
$guard$;

create table public.content_mcp_refresh_families (
    family_hash text primary key check (family_hash ~ '^[0-9a-f]{64}$'),
    invite_hash text not null references public.content_mcp_invites(invite_hash),
    client_id text not null check (client_id in ('alphanest-content-chatgpt', 'alphanest-content-perplexity')),
    resource text not null check (resource = 'https://project-yw131.vercel.app/api/content_mcp'),
    scope text not null check (scope = 'content:read'),
    expires_at timestamptz not null check (pg_catalog.isfinite(expires_at)),
    revoked_at timestamptz,
    rotation_count integer not null default 0 check (rotation_count between 0 and 1000),
    minute_start timestamptz not null default '-infinity',
    minute_used integer not null default 0 check (minute_used between 0 and 5)
);
create index content_mcp_refresh_families_invite_idx
    on public.content_mcp_refresh_families(invite_hash, expires_at);

-- Includes the current (unused) hash as well as every spent hash. Spent hashes
-- survive access-token expiry/revocation; remove only when the family expires.
create table public.content_mcp_refresh_hashes (
    refresh_hash text primary key check (refresh_hash ~ '^[0-9a-f]{64}$'),
    family_hash text not null references public.content_mcp_refresh_families(family_hash) on delete cascade,
    used_at timestamptz
);
create index content_mcp_refresh_hashes_family_idx on public.content_mcp_refresh_hashes(family_hash);
create unique index content_mcp_refresh_one_current_idx
    on public.content_mcp_refresh_hashes(family_hash) where used_at is null;

create table public.content_mcp_refresh_access (
    token_hash text primary key references public.content_mcp_tokens(token_hash) on delete cascade,
    family_hash text not null references public.content_mcp_refresh_families(family_hash) on delete cascade
);
create index content_mcp_refresh_access_family_idx on public.content_mcp_refresh_access(family_hash);

alter table public.content_mcp_refresh_families enable row level security;
alter table public.content_mcp_refresh_hashes enable row level security;
alter table public.content_mcp_refresh_access enable row level security;
revoke all on public.content_mcp_refresh_families, public.content_mcp_refresh_hashes, public.content_mcp_refresh_access
    from public, anon, authenticated, service_role;
grant select, insert, update, delete on
    public.content_mcp_refresh_families, public.content_mcp_refresh_hashes, public.content_mcp_refresh_access to service_role;

create function public.content_mcp_exchange_code_refresh(
    p_code_hash text, p_client_id text, p_redirect_uri text, p_resource text,
    p_scope text, p_code_challenge text, p_token_hash text, p_refresh_hash text
)
returns jsonb language plpgsql security definer set search_path = '' as $function$
declare
    parent_hash text;
    invitation public.content_mcp_invites%rowtype;
    checked_at timestamptz;
    family_expiry timestamptz;
    result jsonb;
    denied_status text := 'denied';
    refresh_lifetime integer;
    access_lifetime integer;
begin
    if p_code_hash is null or p_code_hash !~ '^[0-9a-f]{64}$'
        or p_refresh_hash is null or p_refresh_hash !~ '^[0-9a-f]{64}$'
        or p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
        or p_client_id is null or p_client_id not in ('alphanest-content-chatgpt', 'alphanest-content-perplexity')
        or p_redirect_uri is distinct from (case p_client_id
            when 'alphanest-content-chatgpt' then 'https://chatgpt.com/connector_platform_oauth_redirect'
            when 'alphanest-content-perplexity' then 'https://www.perplexity.ai/rest/connections/oauth_callback' end)
        or p_resource is distinct from 'https://project-yw131.vercel.app/api/content_mcp'
        or p_scope is distinct from 'content:read'
    then return pg_catalog.jsonb_build_object('status', 'denied'); end if;

    select invite_hash into parent_hash from public.content_mcp_codes where code_hash = p_code_hash;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    -- All old/new RPCs serialize on the invitation FIRST. Family locks precede
    -- code/token locks; the original exchange reacquires the same invitation lock.
    select * into invitation from public.content_mcp_invites where invite_hash = parent_hash for update;
    checked_at := pg_catalog.clock_timestamp();
    if not found or invitation.revoked_at is not null or invitation.expires_at <= checked_at then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    -- Only expired families are pruned, at most five; each has <=1001 hashes.
    -- Revoked but unexpired families retain replay evidence and occupy capacity.
    delete from public.content_mcp_refresh_families where family_hash in (
        select family_hash from public.content_mcp_refresh_families
        where invite_hash = parent_hash and expires_at <= checked_at
        order by family_hash limit 5 for update);
    if (select count(*) from public.content_mcp_refresh_families where invite_hash = parent_hash) >= 5 then
        return pg_catalog.jsonb_build_object('status', 'limited');
    end if;
    family_expiry := least(checked_at + interval '30 days', invitation.expires_at);
    result := public.content_mcp_exchange_code(p_code_hash, p_client_id, p_redirect_uri,
        p_resource, p_scope, p_code_challenge, p_token_hash);
    if result ->> 'status' is distinct from 'allowed' then return result; end if;

    insert into public.content_mcp_refresh_families(family_hash, invite_hash, client_id, resource, scope, expires_at)
        values (p_refresh_hash, parent_hash, p_client_id, p_resource, p_scope, family_expiry);
    insert into public.content_mcp_refresh_hashes(refresh_hash, family_hash) values (p_refresh_hash, p_refresh_hash);
    insert into public.content_mcp_refresh_access(token_hash, family_hash) values (p_token_hash, p_refresh_hash);
    -- Reuse the invitation-wide 10/minute, 100/day budget; rotating cannot reset it.
    -- A denied quota check must roll back the original code consumption as well.
    result := public.content_mcp_consume_token(p_token_hash, p_resource, p_scope);
    if result ->> 'status' is distinct from 'allowed' then
        denied_status := case when result ->> 'status' = 'limited' then 'limited' else 'denied' end;
        raise exception using errcode = 'P4101', message = 'refresh issuance denied';
    end if;
    checked_at := pg_catalog.clock_timestamp();
    refresh_lifetime := pg_catalog.floor(extract(epoch from (family_expiry - checked_at)))::integer;
    select least(3600, pg_catalog.floor(extract(epoch from (expires_at - checked_at)))::integer)
        into access_lifetime from public.content_mcp_tokens where token_hash = p_token_hash;
    if refresh_lifetime < 1 or access_lifetime is null or access_lifetime < 1 then
        raise exception using errcode = 'P4101', message = 'refresh issuance denied';
    end if;
    return pg_catalog.jsonb_build_object('status', 'allowed',
        'expires_in', access_lifetime,
        'refresh_expires_in', refresh_lifetime);
exception
    when unique_violation then return pg_catalog.jsonb_build_object('status', 'denied');
    when sqlstate 'P4101' then return pg_catalog.jsonb_build_object('status', denied_status);
end;
$function$;

create function public.content_mcp_rotate_refresh(
    p_refresh_hash text, p_token_hash text, p_next_refresh_hash text,
    p_client_id text, p_resource text, p_scope text
)
returns jsonb language plpgsql security definer set search_path = '' as $function$
declare
    parent_hash text;
    parent_family text;
    invitation public.content_mcp_invites%rowtype;
    family public.content_mcp_refresh_families%rowtype;
    credential public.content_mcp_refresh_hashes%rowtype;
    checked_at timestamptz;
    expiry timestamptz;
    lifetime integer;
    refresh_lifetime integer;
    minute_count integer;
    reset_minute boolean;
    result jsonb;
    denied_status text := 'denied';
begin
    if p_refresh_hash is null or p_refresh_hash !~ '^[0-9a-f]{64}$'
        or p_next_refresh_hash is null or p_next_refresh_hash !~ '^[0-9a-f]{64}$'
        or p_next_refresh_hash = p_refresh_hash
        or p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
        or p_client_id is null or p_client_id not in ('alphanest-content-chatgpt', 'alphanest-content-perplexity')
        or p_resource is distinct from 'https://project-yw131.vercel.app/api/content_mcp'
        or p_scope is distinct from 'content:read'
    then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select f.invite_hash, f.family_hash into parent_hash, parent_family
        from public.content_mcp_refresh_hashes h join public.content_mcp_refresh_families f using (family_hash)
        where h.refresh_hash = p_refresh_hash;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select * into invitation from public.content_mcp_invites where invite_hash = parent_hash for update;
    if not found then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    select * into family from public.content_mcp_refresh_families where family_hash = parent_family for update;
    if not found or family.invite_hash is distinct from parent_hash then
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    select * into credential from public.content_mcp_refresh_hashes where refresh_hash = p_refresh_hash for update;
    checked_at := pg_catalog.clock_timestamp();
    -- Check bindings BEFORE replay/revocation. Knowledge of a hash paired with
    -- another registered client (or wrong resource/scope) must not DoS its owner.
    if not found or credential.family_hash is distinct from parent_family
        or family.client_id is distinct from p_client_id or family.resource is distinct from p_resource
        or family.scope is distinct from p_scope
        or invitation.revoked_at is not null or invitation.expires_at <= checked_at
        or family.revoked_at is not null or family.expires_at <= checked_at
    then return pg_catalog.jsonb_build_object('status', 'denied'); end if;
    if credential.used_at is not null then
        update public.content_mcp_refresh_families set revoked_at = checked_at where family_hash = parent_family;
        update public.content_mcp_tokens set revoked_at = checked_at
            where token_hash in (select token_hash from public.content_mcp_refresh_access where family_hash = parent_family)
                and invite_hash = parent_hash and revoked_at is null;
        return pg_catalog.jsonb_build_object('status', 'denied');
    end if;
    reset_minute := family.minute_start + interval '1 minute' <= checked_at;
    minute_count := case when reset_minute then 1 else family.minute_used + 1 end;
    if minute_count > 5 or family.rotation_count >= 1000 then
        return pg_catalog.jsonb_build_object('status', 'limited');
    end if;
    expiry := least(checked_at + interval '1 hour', family.expires_at, invitation.expires_at);
    lifetime := pg_catalog.floor(extract(epoch from (expiry - checked_at)))::integer;
    refresh_lifetime := pg_catalog.floor(extract(epoch from (least(family.expires_at, invitation.expires_at) - checked_at)))::integer;
    if lifetime < 1 or refresh_lifetime < 1 then return pg_catalog.jsonb_build_object('status', 'denied'); end if;

    -- Old issuer cleanup can still delete expired tokens: mapping FK cascades,
    -- while spent refresh hashes remain until family expiry. Bounded local batch.
    delete from public.content_mcp_tokens where token_hash in (
        select token_hash from public.content_mcp_tokens where invite_hash = parent_hash and expires_at <= checked_at
        order by token_hash limit 100 for update);
    -- Retire only this family's older access credentials, freeing its active slot.
    update public.content_mcp_tokens set revoked_at = checked_at
        where token_hash in (select token_hash from public.content_mcp_refresh_access where family_hash = parent_family)
            and invite_hash = parent_hash and revoked_at is null;
    if (select count(*) from public.content_mcp_tokens where invite_hash = parent_hash
        and revoked_at is null and expires_at > checked_at) >= 5 then
        raise exception using errcode = 'P4101', message = 'refresh rotation denied';
    end if;
    update public.content_mcp_refresh_hashes set used_at = checked_at where refresh_hash = p_refresh_hash;
    insert into public.content_mcp_refresh_hashes(refresh_hash, family_hash) values (p_next_refresh_hash, parent_family);
    insert into public.content_mcp_tokens(token_hash, invite_hash, client_id, resource, scope, expires_at)
        values (p_token_hash, parent_hash, p_client_id, p_resource, p_scope, expiry);
    insert into public.content_mcp_refresh_access(token_hash, family_hash) values (p_token_hash, parent_family);
    update public.content_mcp_refresh_families set rotation_count = rotation_count + 1,
        minute_start = case when reset_minute then checked_at else minute_start end, minute_used = minute_count
        where family_hash = parent_family;
    result := public.content_mcp_consume_token(p_token_hash, p_resource, p_scope);
    if result ->> 'status' is distinct from 'allowed' then
        denied_status := case when result ->> 'status' = 'limited' then 'limited' else 'denied' end;
        raise exception using errcode = 'P4101', message = 'refresh rotation denied';
    end if;
    return pg_catalog.jsonb_build_object('status', 'allowed', 'expires_in', lifetime,
        'refresh_expires_in', refresh_lifetime);
exception
    when unique_violation then return pg_catalog.jsonb_build_object('status', 'denied');
    when sqlstate 'P4101' then return pg_catalog.jsonb_build_object('status', denied_status);
end;
$function$;

revoke all on function public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)
    from public, anon, authenticated, service_role;
revoke all on function public.content_mcp_rotate_refresh(text,text,text,text,text,text)
    from public, anon, authenticated, service_role;
grant execute on function public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text) to service_role;
grant execute on function public.content_mcp_rotate_refresh(text,text,text,text,text,text) to service_role;

comment on table public.content_mcp_refresh_families is
    'Service-only, fixed client/resource/scope refresh families. Initial hash is family ID. Absolute expiry <=30 days and invite expiry; five retained unexpired families/invite, including revoked ones. Invitation is always locked first.';
comment on table public.content_mcp_refresh_hashes is
    'Current and spent SHA-256 refresh hashes; no raw credentials. Retain spent hashes until family expiry for replay revocation. <=1001 hashes/family (initial plus 1000 rotations). Never prune on access-token expiry.';
comment on table public.content_mcp_refresh_access is
    'Access hash -> family mapping. Replay revokes mapped access rows so the unchanged consume RPC denies them. Expired-token deletion cascades only this mapping, not refresh replay evidence. Admin revocation must lock invitation first and revoke mapped tokens too.';
commit;
