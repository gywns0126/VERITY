-- Add Claude to the fixed refresh registration. Apply after 2026092701.
-- One-shot, fail-closed: exact predecessor bodies and parsed client constraint
-- are required. Only registration fragments change; preserve RPC OIDs/ACLs,
-- lock order, quota rollback, replay revocation and absolute/invite expiry.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(2026092701);
select pg_catalog.pg_advisory_xact_lock(2026100201);

-- Compare PostgreSQL's parsed expression rather than deparser formatting.
create temporary table content_mcp_claude_expected (
    client_id text not null check (client_id in ('alphanest-content-chatgpt', 'alphanest-content-perplexity'))
) on commit drop;
revoke all on pg_temp.content_mcp_claude_expected from public, anon, authenticated, service_role;
lock table public.content_mcp_refresh_families in access exclusive mode;

do $migration$
declare
    target record;
    definition text;
    old_clients constant text := $old$p_client_id not in ('alphanest-content-chatgpt', 'alphanest-content-perplexity')$old$;
    new_clients constant text := $new$p_client_id not in ('alphanest-content-chatgpt', 'alphanest-content-perplexity', 'alphanest-content-claude')$new$;
    old_redirect constant text := $old$or p_redirect_uri is distinct from (case p_client_id
            when 'alphanest-content-chatgpt' then 'https://chatgpt.com/connector_platform_oauth_redirect'
            when 'alphanest-content-perplexity' then 'https://www.perplexity.ai/rest/connections/oauth_callback' end)$old$;
    new_redirect constant text := $new$or (case when p_client_id = 'alphanest-content-claude' then
            coalesce(p_redirect_uri !~ '[[:space:][:cntrl:]]' and (p_redirect_uri in (
                'https://claude.ai/api/mcp/auth_callback',
                'https://claude.com/api/mcp/auth_callback'
            ) or p_redirect_uri ~ '^http://(localhost|127[.]0[.]0[.]1):([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])/callback$'), false)
            else p_redirect_uri is not distinct from (case p_client_id
                when 'alphanest-content-chatgpt' then 'https://chatgpt.com/connector_platform_oauth_redirect'
                when 'alphanest-content-perplexity' then 'https://www.perplexity.ai/rest/connections/oauth_callback' end)
            end) is not true$new$;
begin
    if (select count(*) from pg_catalog.pg_constraint
        where conrelid = 'public.content_mcp_refresh_families'::pg_catalog.regclass
            and conname = 'content_mcp_refresh_families_client_id_check'
            and contype = 'c' and convalidated and not connoinherit
            and pg_catalog.pg_get_expr(conbin, conrelid) = (
                select pg_catalog.pg_get_expr(conbin, conrelid) from pg_catalog.pg_constraint
                where conrelid = 'pg_temp.content_mcp_claude_expected'::pg_catalog.regclass
                    and contype = 'c')) <> 1 then
        raise exception 'Unexpected refresh client constraint; Claude migration aborted';
    end if;
    if (select count(*) from pg_catalog.pg_proc p
        join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname in
            ('content_mcp_exchange_code_refresh', 'content_mcp_rotate_refresh')) <> 2 then
        raise exception 'Missing or overloaded refresh RPC; Claude migration aborted';
    end if;
    for target in select p.*, expected.body_md5, expected.signature
        from (values
            ('public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)',
                '38ff4bdad55033088e5f82dbf96c03c5'),
            ('public.content_mcp_rotate_refresh(text,text,text,text,text,text)',
                'b7a101f2b6f524d1f540daa75412b179')
        ) expected(signature, body_md5)
        left join pg_catalog.pg_proc p on p.oid = pg_catalog.to_regprocedure(expected.signature)
    loop
        -- Body fingerprints are drift sentinels, not credential hashes.
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
            raise exception 'Unexpected refresh RPC %; Claude migration aborted', target.signature;
        end if;
        definition := pg_catalog.pg_get_functiondef(target.oid);
        if (length(definition) - length(pg_catalog.replace(definition, old_clients, '')))
            <> length(old_clients) then
            raise exception 'Unexpected client guard count; Claude migration aborted';
        end if;
        definition := pg_catalog.replace(definition, old_clients, new_clients);
        if target.proname = 'content_mcp_exchange_code_refresh' then
            if (length(definition) - length(pg_catalog.replace(definition, old_redirect, '')))
                <> length(old_redirect) then
                raise exception 'Unexpected callback guard count; Claude migration aborted';
            end if;
            definition := pg_catalog.replace(definition, old_redirect, new_redirect);
        end if;
        execute definition;
        if (select proacl is distinct from target.proacl or proowner <> target.proowner
            from pg_catalog.pg_proc where oid = target.oid) then
            raise exception 'Refresh RPC grants changed; Claude migration aborted';
        end if;
    end loop;
    alter table public.content_mcp_refresh_families
        drop constraint content_mcp_refresh_families_client_id_check,
        add constraint content_mcp_refresh_families_client_id_check
            check (client_id in ('alphanest-content-chatgpt', 'alphanest-content-perplexity', 'alphanest-content-claude'));
end;
$migration$;
commit;
