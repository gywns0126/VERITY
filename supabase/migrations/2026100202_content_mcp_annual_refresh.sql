-- Apply after 2026100201_content_mcp_claude, as the existing RPC owner.
-- New families only: absolute 365-day maximum, still bounded by invite expiry.
-- No sliding renewal, invite extension, or changes to existing/expired/revoked
-- family expiries. Lifetime rotations increase to 20000; one-hour access,
-- 5/minute rotation and shared invite quotas/replay handling are unchanged.
-- One-shot: predecessor drift, missing/overloaded RPCs or reapplication aborts.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(2026092701);
select pg_catalog.pg_advisory_xact_lock(2026100201);
select pg_catalog.pg_advisory_xact_lock(2026100202);

create temporary table content_mcp_annual_expected (
    rotation_count integer not null,
    constraint old_rotation check (rotation_count between 0 and 1000),
    constraint new_rotation check (rotation_count between 0 and 20000)
) on commit drop;
revoke all on pg_temp.content_mcp_annual_expected from public, anon, authenticated, service_role;
lock table public.content_mcp_refresh_families in access exclusive mode;

do $migration$
declare
    target record;
    definition text;
    before_fragment text;
    after_fragment text;
    expected_body text;
    old_expiry constant text := $old$family_expiry := least(checked_at + interval '30 days', invitation.expires_at);$old$;
    new_expiry constant text := $new$family_expiry := least(checked_at + interval '365 days', invitation.expires_at);$new$;
begin
    if (select count(*) from pg_catalog.pg_constraint c
        where c.conrelid = 'public.content_mcp_refresh_families'::pg_catalog.regclass
            and c.conname = 'content_mcp_refresh_families_rotation_count_check'
            and c.contype = 'c' and c.convalidated and not c.connoinherit
            and pg_catalog.pg_get_expr(c.conbin, c.conrelid) = (
                select pg_catalog.pg_get_expr(e.conbin, e.conrelid)
                from pg_catalog.pg_constraint e
                where e.conrelid = 'pg_temp.content_mcp_annual_expected'::pg_catalog.regclass
                    and e.conname = 'old_rotation')) <> 1 then
        raise exception 'Unexpected rotation constraint; annual migration aborted';
    end if;
    if (select count(*) from pg_catalog.pg_proc p
        join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname in
            ('content_mcp_exchange_code_refresh', 'content_mcp_rotate_refresh')) <> 2 then
        raise exception 'Missing or overloaded refresh RPC; annual migration aborted';
    end if;
    -- Fingerprints are the exact bodies after the Claude registration migration.
    -- Validate rotation too: its fixed family expiry is what prevents sliding.
    for target in select p.*, expected.body_md5, expected.signature
        from (values
            ('public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)',
                '24100f51a557452ff43931f24cbc79b3'),
            ('public.content_mcp_rotate_refresh(text,text,text,text,text,text)',
                '8117a71992e3933a7debb3f627f94a17')
        ) expected(signature, body_md5)
        left join pg_catalog.pg_proc p on p.oid = pg_catalog.to_regprocedure(expected.signature)
    loop
        if target.oid is null or pg_catalog.md5(target.prosrc) <> target.body_md5
            or not target.prosecdef or target.proconfig is distinct from array['search_path=""']
            or target.prorettype <> 'jsonb'::pg_catalog.regtype or target.proretset
            or target.prokind <> 'f' or target.provolatile <> 'v' or target.proisstrict
            or target.prolang <> (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
            or target.proowner <> (select oid from pg_catalog.pg_roles where rolname = current_user)
            or pg_catalog.has_function_privilege('anon', target.oid, 'EXECUTE')
            or pg_catalog.has_function_privilege('authenticated', target.oid, 'EXECUTE')
            or not pg_catalog.has_function_privilege('service_role', target.oid, 'EXECUTE')
            or exists (select 1 from pg_catalog.aclexplode(coalesce(target.proacl,
                pg_catalog.acldefault('f', target.proowner))) a
                where a.grantee not in (target.proowner,
                    (select oid from pg_catalog.pg_roles where rolname = 'service_role')))
        then
            raise exception 'Unexpected refresh RPC %; annual migration aborted', target.signature;
        end if;
        before_fragment := case when target.proname = 'content_mcp_exchange_code_refresh'
            then old_expiry else 'family.rotation_count >= 1000' end;
        after_fragment := case when target.proname = 'content_mcp_exchange_code_refresh'
            then new_expiry else 'family.rotation_count >= 20000' end;
        definition := pg_catalog.pg_get_functiondef(target.oid);
        if (length(definition) - length(pg_catalog.replace(definition, before_fragment, '')))
            <> length(before_fragment) then
            raise exception 'Unexpected replacement count; annual migration aborted';
        end if;
        definition := pg_catalog.replace(definition, before_fragment, after_fragment);
        expected_body := pg_catalog.replace(target.prosrc, before_fragment, after_fragment);
        -- Keep the exchange cleanup comment consistent with the new finite cap.
        definition := pg_catalog.replace(definition, 'each has <=1001 hashes.', 'each has <=20001 hashes.');
        expected_body := pg_catalog.replace(expected_body, 'each has <=1001 hashes.', 'each has <=20001 hashes.');
        execute definition;
        if not exists (select 1 from pg_catalog.pg_proc p where p.oid = target.oid
            and p.prosrc = expected_body
            and p.proacl is not distinct from target.proacl
            and p.proowner = target.proowner
            and p.prosecdef = target.prosecdef
            and p.proconfig is not distinct from target.proconfig) then
            raise exception 'Refresh RPC preservation check failed; annual migration aborted';
        end if;
    end loop;
    alter table public.content_mcp_refresh_families
        drop constraint content_mcp_refresh_families_rotation_count_check,
        add constraint content_mcp_refresh_families_rotation_count_check
            check (rotation_count between 0 and 20000);
    if not exists (select 1 from pg_catalog.pg_constraint c
        where c.conrelid = 'public.content_mcp_refresh_families'::pg_catalog.regclass
            and c.conname = 'content_mcp_refresh_families_rotation_count_check'
            and c.convalidated and pg_catalog.pg_get_expr(c.conbin, c.conrelid) = (
                select pg_catalog.pg_get_expr(e.conbin, e.conrelid)
                from pg_catalog.pg_constraint e
                where e.conrelid = 'pg_temp.content_mcp_annual_expected'::pg_catalog.regclass
                    and e.conname = 'new_rotation')) then
        raise exception 'Rotation constraint verification failed; annual migration aborted';
    end if;
end;
$migration$;

comment on table public.content_mcp_refresh_families is
    'Service-only, fixed client/resource/scope refresh families. Initial hash is family ID. New families: absolute expiry <=365 days and invite expiry; existing family expiries unchanged, never extended by rotation. Five retained unexpired families/invite, including revoked ones. Invitation is always locked first.';
comment on function public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text) is
    'Service-only OAuth code exchange. New refresh families expire at the earlier of initial issuance plus 365 days or invite expiry (absolute, not sliding). Existing/expired/revoked families and invitations are not extended. One-hour access, registration/PKCE binding, quotas and replay protections remain unchanged.';
comment on function public.content_mcp_rotate_refresh(text,text,text,text,text,text) is
    'Service-only rotation: <=20000 successful rotations per family, <=5/minute and shared invite quotas (10/minute, 100/day). Absolute family expiry never extended. Spent-hash replay revokes family and mapped access tokens.';
comment on table public.content_mcp_refresh_hashes is
    'Current and spent SHA-256 refresh hashes; no raw credentials. Retain spent hashes until family expiry for replay revocation. <=20001 hashes/family (initial plus 20000 rotations). Never prune on access-token expiry.';
commit;

-- Read-only apply verification: expect two rows with definition_ok, security_ok
-- and service_only_execute all true. The exchange comment must describe 365
-- days. This checks installed definitions/grants, not an OAuth runtime exchange.
-- This SELECT may be rerun independently; do not rerun the one-shot migration.
select expected.signature,
    coalesce(case when p.proname = 'content_mcp_exchange_code_refresh' then
        pg_catalog.strpos(p.prosrc, $new$family_expiry := least(checked_at + interval '365 days', invitation.expires_at);$new$) > 0
        and pg_catalog.md5(pg_catalog.replace(pg_catalog.replace(p.prosrc,
            $new$family_expiry := least(checked_at + interval '365 days', invitation.expires_at);$new$,
            $old$family_expiry := least(checked_at + interval '30 days', invitation.expires_at);$old$),
            'each has <=20001 hashes.', 'each has <=1001 hashes.')) = expected.body_md5
        else pg_catalog.strpos(p.prosrc, 'family.rotation_count >= 20000') > 0
            and pg_catalog.md5(pg_catalog.replace(p.prosrc, 'family.rotation_count >= 20000',
                'family.rotation_count >= 1000')) = expected.body_md5 end, false) as definition_ok,
    coalesce(p.prosecdef and p.proconfig = array['search_path=""'], false) as security_ok,
    coalesce(pg_catalog.has_function_privilege('service_role', p.oid, 'EXECUTE')
        and not pg_catalog.has_function_privilege('anon', p.oid, 'EXECUTE')
        and not pg_catalog.has_function_privilege('authenticated', p.oid, 'EXECUTE')
        and not exists (select 1 from pg_catalog.aclexplode(coalesce(p.proacl,
            pg_catalog.acldefault('f', p.proowner))) a
            where a.grantee not in (p.proowner,
                (select oid from pg_catalog.pg_roles where rolname = 'service_role'))), false) as service_only_execute,
    pg_catalog.obj_description(p.oid, 'pg_proc') as function_comment
from (values
    ('public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)',
        '24100f51a557452ff43931f24cbc79b3'),
    ('public.content_mcp_rotate_refresh(text,text,text,text,text,text)',
        '8117a71992e3933a7debb3f627f94a17')
) expected(signature, body_md5)
left join pg_catalog.pg_proc p on p.oid = pg_catalog.to_regprocedure(expected.signature);

-- Expect one validated CHECK with rotation_count >= 0 AND <= 20000.
select c.convalidated, pg_catalog.pg_get_constraintdef(c.oid) as rotation_constraint
from pg_catalog.pg_constraint c
where c.conrelid = 'public.content_mcp_refresh_families'::pg_catalog.regclass
    and c.conname = 'content_mcp_refresh_families_rotation_count_check';
