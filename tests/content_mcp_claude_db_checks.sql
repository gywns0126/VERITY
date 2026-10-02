-- LOCAL disposable PostgreSQL only. Run as migration owner, after migrations
-- 2026092602, 2026092701 and 2026100201, with psql -X -v ON_ERROR_STOP=1 -f FILE.
-- Also run content_mcp_oauth_db_checks.sql and content_mcp_refresh_db_checks.sql
-- unchanged for legacy behavior, table/RPC grants, capacity and quota coverage.
-- Fixtures roll back. On error, ROLLBACK before reusing the connection.
-- Migration failure options (separate disposable databases): remove an RPC,
-- add an overload, change either RPC body/SECURITY DEFINER/search_path/grants,
-- or change/remove the client constraint; migration must fail without changes.
-- Reapplying 2026100201 must also fail. This single session does not test races.
begin;
set local statement_timeout = '30s';
set local lock_timeout = '3s';
set local search_path = '';
create temporary table pg_temp.claude_qa (checks integer not null default 0) on commit drop;
revoke all on pg_temp.claude_qa from public, anon, authenticated, service_role;
insert into pg_temp.claude_qa default values;
create function pg_temp.claude_assert(ok boolean, label text) returns void
language plpgsql set search_path = '' as $f$
begin
    if ok is distinct from true then raise exception 'CONTENT_MCP_CLAUDE_CHECK_FAIL: %', label; end if;
    update pg_temp.claude_qa set checks = checks + 1;
end;
$f$;

create function pg_temp.claude_case(callback text, accepted boolean,
    client text default 'alphanest-content-claude') returns void
language plpgsql set search_path = '' as $f$
declare
    h text[];
    run_id text := pg_catalog.gen_random_uuid()::text;
    resource constant text := 'https://project-yw131.vercel.app/api/content_mcp';
    r jsonb;
    original_expiry timestamptz;
    started timestamptz := pg_catalog.clock_timestamp();
begin
    select array_agg(md5(run_id || n::text) || md5(n::text || run_id) order by n)
        into h from pg_catalog.generate_series(1,10) n;
    insert into public.content_mcp_invites(invite_hash,label,expires_at)
        values(h[1],'claude-sql-check',started + interval '45 days');
    -- Generic issuer deliberately remains generic. Invalid but syntactically
    -- well-formed callbacks are persisted, proving the refresh guard is needed.
    r := public.content_mcp_issue_code(h[1],h[2],client,
        case when callback is null or callback ~ '[[:space:][:cntrl:]]'
            then 'https://claude.ai/api/mcp/auth_callback' else callback end,
        resource,'content:read',repeat('A',43));
    perform pg_temp.claude_assert(r->>'status' = 'allowed','generic issue: ' || coalesce(callback,'NULL'));
    r := public.content_mcp_exchange_code_refresh(h[2],client,callback,resource,
        'content:read',repeat('A',43),h[3],h[4]);
    perform pg_temp.claude_assert(r->>'status' = case when accepted then 'allowed' else 'denied' end,
        'registration: ' || coalesce(callback,'NULL') || ' / ' || client);
    if not accepted then
        perform pg_temp.claude_assert((select used_at is null from public.content_mcp_codes where code_hash=h[2])
            and not exists(select 1 from public.content_mcp_tokens where token_hash=h[3])
            and not exists(select 1 from public.content_mcp_refresh_families where family_hash=h[4])
            and (select minute_used=0 and day_used=0 from public.content_mcp_invites where invite_hash=h[1]),
            'registration denial has no credential/quota side effects');
        return;
    end if;
    select expires_at into original_expiry from public.content_mcp_refresh_families where family_hash=h[4];
    perform pg_temp.claude_assert(original_expiry between started + interval '30 days'
        and clock_timestamp() + interval '30 days'
        and (r->>'expires_in')::integer between 1 and 3600
        and (r->>'refresh_expires_in')::integer between 2591900 and 2592000,
        'one hour access and absolute thirty day family');
    r := public.content_mcp_exchange_code_refresh(h[2],client,callback,resource,
        'content:read',repeat('A',43),h[5],h[6]);
    perform pg_temp.claude_assert(r->>'status'='denied','code replay');
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],
        case when client='alphanest-content-chatgpt' then 'alphanest-content-claude'
            else 'alphanest-content-chatgpt' end,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','cross-client rotation');
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],client,resource || '/wrong','content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','wrong resource');
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],client,resource,'content:write');
    perform pg_temp.claude_assert(r->>'status'='denied','wrong scope');
    r := public.content_mcp_rotate_refresh(h[4],h[3],h[6],client,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','access collision rolls back');
    update public.content_mcp_invites set minute_start=clock_timestamp(),minute_used=10 where invite_hash=h[1];
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],client,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='limited','shared quota rotation');
    perform pg_temp.claude_assert((select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[4])
        and (select revoked_at is null from public.content_mcp_tokens where token_hash=h[3])
        and (select rotation_count=0 and revoked_at is null from public.content_mcp_refresh_families where family_hash=h[4])
        and not exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=h[6]),
        'failed rotation preserves existing credentials and family');
    update public.content_mcp_invites set minute_start=clock_timestamp()-interval '2 minutes' where invite_hash=h[1];
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],client,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='allowed','rotate registered client');
    perform pg_temp.claude_assert((select expires_at=original_expiry and rotation_count=1
        from public.content_mcp_refresh_families where family_hash=h[4]),'rotation cannot extend expiry');
    r := public.content_mcp_consume_token(h[3],resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','previous access retired');
    r := public.content_mcp_consume_token(h[5],resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='allowed','new access accepted');
    r := public.content_mcp_rotate_refresh(h[4],h[7],h[8],
        case when client='alphanest-content-chatgpt' then 'alphanest-content-claude'
            else 'alphanest-content-chatgpt' end,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied'
        and (select revoked_at is null from public.content_mcp_refresh_families where family_hash=h[4]),
        'wrong-client spent hash cannot revoke family');
    r := public.content_mcp_rotate_refresh(h[4],h[7],h[8],client,resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied'
        and (select revoked_at is not null from public.content_mcp_refresh_families where family_hash=h[4]),
        'spent hash revokes family');
    r := public.content_mcp_consume_token(h[5],resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','replay revokes current access');
end;
$f$;

do $checks$
declare
    callback text;
    host text;
    port text;
    client text;
    h text[];
    r jsonb;
    resource constant text := 'https://project-yw131.vercel.app/api/content_mcp';
    run_id text := pg_catalog.gen_random_uuid()::text;
    callback_pattern text;
begin
    -- Test the actual installed PostgreSQL regex, not a copied test expression
    -- or another language's anchor semantics. Include terminal LF/CR/CRLF.
    select (pg_catalog.regexp_match(prosrc, 'p_redirect_uri ~ ''([^'']+)'''))[1]
        into callback_pattern from pg_catalog.pg_proc
        where oid='public.content_mcp_exchange_code_refresh(text,text,text,text,text,text,text,text)'::pg_catalog.regprocedure;
    perform pg_temp.claude_assert(callback_pattern is not null,'installed callback pattern found');
    foreach host in array array['localhost','127.0.0.1'] loop
        perform pg_temp.claude_assert((select bool_and(
            (('http://' || host || ':' || n::text || '/callback') ~ callback_pattern)
                = (n between 1 and 65535)) from pg_catalog.generate_series(0,65536) n),
            'PostgreSQL port range 0..65536: ' || host);
        foreach callback in array array[E'\n',E'\r',E'\r\n'] loop
            perform pg_temp.claude_assert(('http://' || host || ':1234/callback' || callback) !~ callback_pattern,
                'PostgreSQL terminal newline anchor: ' || host);
        end loop;
    end loop;
    foreach callback in array array['https://claude.ai/api/mcp/auth_callback',
        'https://claude.com/api/mcp/auth_callback'] loop
        perform pg_temp.claude_case(callback,true);
    end loop;
    foreach host in array array['localhost','127.0.0.1'] loop
        foreach port in array array['1','9','10','9999','10000','59999','60000','64999',
            '65000','65499','65500','65529','65530','65535'] loop
            perform pg_temp.claude_case('http://' || host || ':' || port || '/callback',true);
        end loop;
        foreach port in array array['0','00','01','080','65536','65599','66000','70000',
            '99999','100000','999999999999999999999','-1','+1','1.0','1e2','%31'] loop
            perform pg_temp.claude_case('http://' || host || ':' || port || '/callback',false);
        end loop;
    end loop;
    foreach callback in array array[null,
        'https://claude.ai/api/mcp/auth_callback/',
        'https://claude.com/api/mcp/auth_callback?x=1',
        'https://claude.ai/api/mcp/auth_callback#x',
        'https://claude.ai:443/api/mcp/auth_callback',
        'http://claude.ai/api/mcp/auth_callback',
        'https://CLAUDE.ai/api/mcp/auth_callback',
        'https://claude.ai.evil.test/api/mcp/auth_callback',
        'https://user@claude.com/api/mcp/auth_callback',
        'https://claude.ai@evil.test/api/mcp/auth_callback',
        'https://claude.ai/api/mcp/%61uth_callback',
        'http://localhost/callback','http://127.0.0.1/callback',
        'http://localhost:/callback','http://localhost:80/callback/',
        'http://localhost:80/callback?','http://localhost:80/callback#',
        'http://127.0.0.1:80/callback?x=1','http://127.0.0.1:80/callback#x',
        'http://user@localhost:80/callback','http://127.0.0.1@evil.test:80/callback',
        'http://localhost.evil.test:80/callback','http://127.0.0.1.evil.test:80/callback',
        'http://localhost.:80/callback','http://LOCALHOST:80/callback',
        'https://localhost:80/callback','http://[::1]:80/callback',
        'http://127.1:80/callback','http://127.0.0.2:80/callback',
        'http://2130706433:80/callback','http://localhost:80/%63allback',
        E'http://localhost:80/callback\n',E'http://localhost:80/callback\r',
        ' http://localhost:80/callback','http://localhost:80/callback ',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        'https://www.perplexity.ai/rest/connections/oauth_callback'] loop
        perform pg_temp.claude_case(callback,false);
    end loop;
    perform pg_temp.claude_case('https://chatgpt.com/connector_platform_oauth_redirect',true,'alphanest-content-chatgpt');
    perform pg_temp.claude_case('https://www.perplexity.ai/rest/connections/oauth_callback',true,'alphanest-content-perplexity');
    foreach client in array array['alphanest-content-chatgpt','alphanest-content-perplexity','unregistered'] loop
        perform pg_temp.claude_case('https://claude.ai/api/mcp/auth_callback',false,client);
        perform pg_temp.claude_case('http://localhost:1234/callback',false,client);
    end loop;

    select array_agg(md5(run_id || n::text) || md5(n::text || run_id) order by n)
        into h from pg_catalog.generate_series(1,8) n;
    insert into public.content_mcp_invites(invite_hash,label,expires_at)
        values(h[1],'claude-binding-check',clock_timestamp()+interval '2 minutes');
    r := public.content_mcp_issue_code(h[1],h[2],'alphanest-content-claude',
        'http://localhost:1234/callback',resource,'content:read',repeat('A',43));
    perform pg_temp.claude_assert(r->>'status'='allowed','binding fixture');
    foreach callback in array array['http://localhost:1235/callback','http://127.0.0.1:1234/callback',
        'https://claude.ai/api/mcp/auth_callback'] loop
        r := public.content_mcp_exchange_code_refresh(h[2],'alphanest-content-claude',callback,
            resource,'content:read',repeat('A',43),h[3],h[4]);
        perform pg_temp.claude_assert(r->>'status'='denied','registered but different persisted callback');
    end loop;
    r := public.content_mcp_exchange_code_refresh(h[2],'alphanest-content-claude','http://localhost:1234/callback',
        resource,'content:read',repeat('B',43),h[3],h[4]);
    perform pg_temp.claude_assert(r->>'status'='denied','wrong S256 challenge');
    update public.content_mcp_invites set day_start=clock_timestamp(),day_used=100 where invite_hash=h[1];
    r := public.content_mcp_exchange_code_refresh(h[2],'alphanest-content-claude','http://localhost:1234/callback',
        resource,'content:read',repeat('A',43),h[3],h[4]);
    perform pg_temp.claude_assert(r->>'status'='limited'
        and (select used_at is null from public.content_mcp_codes where code_hash=h[2])
        and not exists(select 1 from public.content_mcp_tokens where token_hash=h[3])
        and not exists(select 1 from public.content_mcp_refresh_families where family_hash=h[4]),
        'issuance quota rollback preserves code');
    update public.content_mcp_invites set day_start=clock_timestamp()-interval '2 days' where invite_hash=h[1];
    r := public.content_mcp_exchange_code_refresh(h[2],'alphanest-content-claude','http://localhost:1234/callback',
        resource,'content:read',repeat('A',43),h[3],h[4]);
    perform pg_temp.claude_assert(r->>'status'='allowed'
        and (r->>'refresh_expires_in')::integer between 1 and 120
        and (select f.expires_at=i.expires_at and t.expires_at<=i.expires_at
            from public.content_mcp_refresh_families f join public.content_mcp_invites i using(invite_hash)
            join public.content_mcp_tokens t using(invite_hash) where f.family_hash=h[4] and t.token_hash=h[3]),
        'short invite bounds family and access');
    update public.content_mcp_invites set revoked_at=clock_timestamp() where invite_hash=h[1];
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],'alphanest-content-claude',resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','invite revocation');
    update public.content_mcp_invites set revoked_at=null,expires_at=clock_timestamp()-interval '1 second' where invite_hash=h[1];
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],'alphanest-content-claude',resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','invite expiry');
    update public.content_mcp_invites set expires_at=clock_timestamp()+interval '45 days' where invite_hash=h[1];
    update public.content_mcp_refresh_families set expires_at=clock_timestamp()-interval '1 second' where family_hash=h[4];
    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],'alphanest-content-claude',resource,'content:read');
    perform pg_temp.claude_assert(r->>'status'='denied','absolute family expiry');
    -- Constraint still rejects any fourth client, independently of RPC guards.
    begin
        update public.content_mcp_refresh_families set client_id='unregistered' where family_hash=h[4];
        raise exception 'CONTENT_MCP_CLAUDE_CHECK_FAIL: unknown client constraint accepted';
    exception when check_violation then
        perform pg_temp.claude_assert(true,'unknown client constraint denied');
    end;
end;
$checks$;
select 'CONTENT_MCP_CLAUDE_DB_CHECKS_PASS' as marker, checks from pg_temp.claude_qa;
rollback;
