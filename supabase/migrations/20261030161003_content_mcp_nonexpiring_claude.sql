-- Explicit +infinity invitation opt-in permits new non-expiring Claude families.
-- Finite invitations and other clients retain the absolute annual deadline.
-- This migration changes no invitation/family rows. Access and codes stay finite.
-- Apply once, after 2026100202, as the existing RPC/table owner. Drift aborts.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(2026092602);
select pg_catalog.pg_advisory_xact_lock(2026092701);
select pg_catalog.pg_advisory_xact_lock(2026100201);
select pg_catalog.pg_advisory_xact_lock(2026100202);
select pg_catalog.pg_advisory_xact_lock(2026103016);
lock table public.content_mcp_invites, public.content_mcp_refresh_families in access exclusive mode;

create temporary table content_mcp_nonexpiring_expected (
    expires_at timestamptz not null check (pg_catalog.isfinite(expires_at)),
    rotation_count integer not null check (rotation_count between 0 and 20000)
) on commit drop;
revoke all on pg_temp.content_mcp_nonexpiring_expected from public, anon, authenticated, service_role;
create temporary table content_mcp_nonexpiring_security on commit drop as
    select oid, relowner, relacl, relrowsecurity, relforcerowsecurity
    from pg_catalog.pg_class where oid in (
        'public.content_mcp_invites'::pg_catalog.regclass,
        'public.content_mcp_codes'::pg_catalog.regclass,
        'public.content_mcp_tokens'::pg_catalog.regclass,
        'public.content_mcp_refresh_families'::pg_catalog.regclass,
        'public.content_mcp_refresh_hashes'::pg_catalog.regclass,
        'public.content_mcp_refresh_access'::pg_catalog.regclass);
revoke all on pg_temp.content_mcp_nonexpiring_security from public, anon, authenticated, service_role;

do $migration$
declare
    target record;
    replacement record;
    expected_body text;
    definition text;
begin
    if (select count(*) from pg_temp.content_mcp_nonexpiring_security) <> 6
        or exists (select 1 from pg_temp.content_mcp_nonexpiring_security
            where not relrowsecurity or relowner <>
                (select oid from pg_catalog.pg_roles where rolname = current_user)) then
        raise exception 'Unexpected content table security; non-expiring migration aborted';
    end if;
    for target in select * from (values
        ('public.content_mcp_invites', 'content_mcp_invites_expires_at_check',
            'content_mcp_nonexpiring_expected_expires_at_check'),
        ('public.content_mcp_refresh_families', 'content_mcp_refresh_families_expires_at_check',
            'content_mcp_nonexpiring_expected_expires_at_check'),
        ('public.content_mcp_refresh_families', 'content_mcp_refresh_families_rotation_count_check',
            'content_mcp_nonexpiring_expected_rotation_count_check')
    ) expected(relation_name, constraint_name, expected_name) loop
        if (select count(*) from pg_catalog.pg_constraint c
            where c.conrelid = pg_catalog.to_regclass(target.relation_name)
                and c.conname = target.constraint_name and c.contype = 'c'
                and c.convalidated and not c.connoinherit
                and pg_catalog.pg_get_expr(c.conbin, c.conrelid) = (
                    select pg_catalog.pg_get_expr(e.conbin, e.conrelid)
                    from pg_catalog.pg_constraint e
                    where e.conrelid = 'pg_temp.content_mcp_nonexpiring_expected'::pg_catalog.regclass
                        and e.conname = target.expected_name)) <> 1 then
            raise exception 'Unexpected constraint %; non-expiring migration aborted', target.constraint_name;
        end if;
    end loop;
    if not exists (select 1 from pg_catalog.pg_attribute
        where attrelid = 'public.content_mcp_refresh_families'::pg_catalog.regclass
            and attname = 'rotation_count' and atttypid = 'integer'::pg_catalog.regtype
            and attnotnull and not attisdropped)
        or (select count(*) from pg_catalog.pg_proc p
            join pg_catalog.pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.proname in
                ('content_mcp_exchange_code_refresh', 'content_mcp_rotate_refresh')) <> 2 then
        raise exception 'Unexpected rotation type or overloaded RPC; non-expiring migration aborted';
    end if;
    for target in select p.*, expected.body_md5, expected.signature
        from (values
            ('public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)',
                '5c313bae613d3f024015053d2fd3b6b7'),
            ('public.content_mcp_rotate_refresh(text,text,text,text,text,text)',
                'dc98d97d832d02298bd9e6fb015984b5')
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
                    (select oid from pg_catalog.pg_roles where rolname = 'service_role'))) then
            raise exception 'Unexpected RPC %; non-expiring migration aborted', target.signature;
        end if;
        definition := pg_catalog.pg_get_functiondef(target.oid);
        expected_body := target.prosrc;
        for replacement in select * from (values
            ('content_mcp_exchange_code_refresh',
                $old$family_expiry := least(checked_at + interval '365 days', invitation.expires_at);$old$,
                $new$family_expiry := case when p_client_id = 'alphanest-content-claude'
        and invitation.expires_at = 'infinity'::timestamptz then 'infinity'::timestamptz
        else least(checked_at + interval '365 days', invitation.expires_at) end;$new$),
            ('content_mcp_exchange_code_refresh',
                $old$refresh_lifetime := pg_catalog.floor(extract(epoch from (family_expiry - checked_at)))::integer;$old$,
                $new$refresh_lifetime := case when family_expiry = 'infinity'::timestamptz
        and invitation.expires_at = 'infinity'::timestamptz then null
        else pg_catalog.floor(extract(epoch from (family_expiry - checked_at)))::integer end;$new$),
            ('content_mcp_exchange_code_refresh',
                $old$'refresh_expires_in', refresh_lifetime);$old$,
                $new$'refresh_expires_in', refresh_lifetime) || case when family_expiry = 'infinity'::timestamptz
        and invitation.expires_at = 'infinity'::timestamptz
        then pg_catalog.jsonb_build_object('refresh_non_expiring', true) else '{}'::jsonb end;$new$),
            ('content_mcp_exchange_code_refresh',
                $old$-- Only expired families are pruned, at most five; each has <=20001 hashes.$old$,
                $new$-- Only expired families are pruned, at most five; infinite replay evidence is retained.$new$),
            ('content_mcp_rotate_refresh',
                $old$family.rotation_count >= 20000$old$,
                $new$(family.rotation_count >= 20000 and not (family.client_id = 'alphanest-content-claude'
        and family.expires_at = 'infinity'::timestamptz))$new$),
            ('content_mcp_rotate_refresh',
                $old$refresh_lifetime := pg_catalog.floor(extract(epoch from (least(family.expires_at, invitation.expires_at) - checked_at)))::integer;$old$,
                $new$refresh_lifetime := case when family.expires_at = 'infinity'::timestamptz
        and invitation.expires_at = 'infinity'::timestamptz then null
        else least(31536001, pg_catalog.floor(extract(epoch from (least(family.expires_at, invitation.expires_at) - checked_at))))::integer end;
    -- Reject an unsupported finite parent-policy transition before spending the refresh.
    -- Bound the numeric value before casting; an arbitrary future date may exceed int32.
    if refresh_lifetime > 31536000 then return pg_catalog.jsonb_build_object('status', 'denied'); end if;$new$),
            ('content_mcp_rotate_refresh',
                $old$'refresh_expires_in', refresh_lifetime);$old$,
                $new$'refresh_expires_in', refresh_lifetime) || case when family.expires_at = 'infinity'::timestamptz
        and invitation.expires_at = 'infinity'::timestamptz
        then pg_catalog.jsonb_build_object('refresh_non_expiring', true) else '{}'::jsonb end;$new$)
        ) changes(function_name, before_fragment, after_fragment)
        where function_name = target.proname
        loop
            if (length(expected_body) - length(pg_catalog.replace(expected_body, replacement.before_fragment, '')))
                <> length(replacement.before_fragment) then
                raise exception 'Unexpected replacement count for %; non-expiring migration aborted', target.signature;
            end if;
            definition := pg_catalog.replace(definition, replacement.before_fragment, replacement.after_fragment);
            expected_body := pg_catalog.replace(expected_body, replacement.before_fragment, replacement.after_fragment);
        end loop;
        execute definition;
        if not exists (select 1 from pg_catalog.pg_proc p where p.oid = target.oid
            and p.prosrc = expected_body and p.proacl is not distinct from target.proacl
            and p.proowner = target.proowner and p.prosecdef = target.prosecdef
            and p.proconfig is not distinct from target.proconfig) then
            raise exception 'RPC preservation failed; non-expiring migration aborted';
        end if;
    end loop;
    alter table public.content_mcp_invites
        drop constraint content_mcp_invites_expires_at_check,
        add constraint content_mcp_invites_expires_at_check
            check (pg_catalog.isfinite(expires_at) or expires_at = 'infinity'::timestamptz);
    alter table public.content_mcp_refresh_families
        drop constraint content_mcp_refresh_families_expires_at_check,
        drop constraint content_mcp_refresh_families_rotation_count_check,
        alter column rotation_count type bigint,
        add constraint content_mcp_refresh_families_expires_at_check
            check (pg_catalog.isfinite(expires_at) or
                (expires_at = 'infinity'::timestamptz and client_id = 'alphanest-content-claude')),
        add constraint content_mcp_refresh_families_rotation_count_check
            check (rotation_count >= 0 and (rotation_count <= 20000 or
                (expires_at = 'infinity'::timestamptz and client_id = 'alphanest-content-claude')));
    if exists (select 1 from pg_temp.content_mcp_nonexpiring_security old
        left join pg_catalog.pg_class c on c.oid = old.oid
        where c.oid is null or c.relowner <> old.relowner or c.relacl is distinct from old.relacl
            or c.relrowsecurity <> old.relrowsecurity or c.relforcerowsecurity <> old.relforcerowsecurity) then
        raise exception 'Table security preservation failed; non-expiring migration aborted';
    end if;
end;
$migration$;

comment on table public.content_mcp_invites is
    'Service-only invite hashes. Positive infinity is explicit non-expiring opt-in; no rows changed by migration. Revocation still denies all child credentials. Lock invitation before children.';
comment on table public.content_mcp_refresh_families is
    'New Claude family plus explicitly infinite invitation may be non-expiring. Other families retain absolute <=365 days and invite expiry. Existing deadlines never auto-extend. Five retained unexpired families/invite including revoked; lock invitation first.';
comment on table public.content_mcp_refresh_hashes is
    'Current and every spent refresh hash retained until family expiry, indefinitely for non-expiring Claude families. Replay revokes the family and mapped access. Never prune on access expiry. Finite families retain <=20001 hashes.';
comment on function public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text) is
    'Service-only PKCE exchange. Explicitly infinite invite plus Claude creates non-expiring refresh; finite and other-client families remain absolute annual. Access <=1h. No existing invitations/families extended.';
comment on function public.content_mcp_rotate_refresh(text,text,text,text,text,text) is
    'Service-only rotation. No cumulative limit for infinite Claude families; finite families <=20000. All families <=5/minute plus shared invite 10/minute and 100/day. Full spent-hash replay revocation and fixed family expiry preserved.';
commit;
