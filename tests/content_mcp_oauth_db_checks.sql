-- Run this WHOLE file as the migration owner in a fresh SQL-editor transaction,
-- after 2026092602_content_mcp_oauth.sql. No extensions or real credentials needed.
-- Only catalog metadata and collision-checked synthetic keys are queried.
-- Success result: CONTENT_MCP_OAUTH_DB_CHECKS_PASS, followed by ROLLBACK.
-- Any failed assertion raises an exception and aborts the transaction. If the
-- client stops on error before the final statement, execute ROLLBACK explicitly.
-- No COMMIT: fixtures, helper functions and the result table are rolled back.
-- These are sequential functional checks, not a multi-session concurrency test.
begin;
set local statement_timeout = '30s';
set local lock_timeout = '3s';
set local search_path = '';

create temporary table pg_temp.content_mcp_qa_result (marker text not null) on commit drop;
alter table pg_temp.content_mcp_qa_result enable row level security;
revoke all on pg_temp.content_mcp_qa_result from public, anon, authenticated, service_role;

create function pg_temp.content_mcp_qa_assert(ok boolean, label text)
returns void language plpgsql set search_path = '' as $assert$
begin
    if ok is distinct from true then
        raise exception 'CONTENT_MCP_OAUTH_DB_CHECKS_FAIL: %', label;
    end if;
end;
$assert$;

create function pg_temp.content_mcp_qa_status(actual jsonb, expected text, label text)
returns void language plpgsql set search_path = '' as $status$
begin
    perform pg_temp.content_mcp_qa_assert(actual ->> 'status' = expected, label);
end;
$status$;

-- Fixed public test bindings; helper functions run as invoker, not definer.
create function pg_temp.content_mcp_qa_issue(invite text, code text)
returns jsonb language sql set search_path = '' as $issue$
    select public.content_mcp_issue_code(invite, code, 'qa-public-client',
        'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp',
        'content:read', repeat('A', 43));
$issue$;
create function pg_temp.content_mcp_qa_exchange(code text, token text)
returns jsonb language sql set search_path = '' as $exchange$
    select public.content_mcp_exchange_code(code, 'qa-public-client',
        'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp',
        'content:read', repeat('A', 43), token);
$exchange$;
create function pg_temp.content_mcp_qa_consume(token text)
returns jsonb language sql set search_path = '' as $consume$
    select public.content_mcp_consume_token(token, 'https://oauth-qa.invalid/mcp', 'content:read');
$consume$;

do $checks$
declare
    h text[];
    run_id text := pg_catalog.gen_random_uuid()::text;
    obj record;
    bindings record;
    role_name text;
    privilege_name text;
    result jsonb;
    i integer;
    batch integer;
    stamp timestamptz;
begin
    -- 3/3 tables: RLS, no policies, no PUBLIC/anon/authenticated ACL entries,
    -- and no effective anon/authenticated table or column privileges.
    perform pg_temp.content_mcp_qa_assert((select count(*) = 3
        from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and c.relname in
            ('content_mcp_invites', 'content_mcp_codes', 'content_mcp_tokens')), 'three tables exist');
    for obj in select c.oid, c.relname, c.relrowsecurity, c.relacl
        from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname in
            ('content_mcp_invites', 'content_mcp_codes', 'content_mcp_tokens')
    loop
        perform pg_temp.content_mcp_qa_assert(obj.relrowsecurity, obj.relname || ' RLS');
        perform pg_temp.content_mcp_qa_assert(not exists (
            select 1 from pg_catalog.pg_policy where polrelid = obj.oid), obj.relname || ' no policies');
        perform pg_temp.content_mcp_qa_assert(not exists (
            select 1 from pg_catalog.aclexplode(obj.relacl) a where a.grantee = 0 or a.grantee in
                (select oid from pg_catalog.pg_roles where rolname in ('anon', 'authenticated'))),
            obj.relname || ' no public-facing grants');
        foreach role_name in array array['anon', 'authenticated'] loop
            foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] loop
                perform pg_temp.content_mcp_qa_assert(not pg_catalog.has_table_privilege(role_name, obj.oid, privilege_name),
                    obj.relname || ' denies ' || role_name || ' ' || privilege_name);
            end loop;
            foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'REFERENCES'] loop
                perform pg_temp.content_mcp_qa_assert(not pg_catalog.has_any_column_privilege(role_name, obj.oid, privilege_name),
                    obj.relname || ' denies column ' || role_name || ' ' || privilege_name);
            end loop;
        end loop;
        foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
            perform pg_temp.content_mcp_qa_assert(pg_catalog.has_table_privilege('service_role', obj.oid, privilege_name),
                obj.relname || ' service_role ' || privilege_name);
        end loop;
    end loop;

    -- 3/3 RPCs, including absence of extra overloads and implicit PUBLIC execute.
    perform pg_temp.content_mcp_qa_assert((select count(*) = 3
        from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname in
            ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token')), 'three RPCs only');
    for obj in select p.oid, p.proname, p.prosecdef, p.proconfig, p.proacl, p.proowner
        from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname in
            ('content_mcp_issue_code', 'content_mcp_exchange_code', 'content_mcp_consume_token')
    loop
        perform pg_temp.content_mcp_qa_assert(obj.prosecdef and obj.proconfig @> array['search_path=""'],
            obj.proname || ' SECURITY DEFINER and empty search_path');
        perform pg_temp.content_mcp_qa_assert(not exists (
            select 1 from pg_catalog.aclexplode(coalesce(obj.proacl, pg_catalog.acldefault('f', obj.proowner))) a
            where a.grantee = 0), obj.proname || ' no PUBLIC execute');
        foreach role_name in array array['anon', 'authenticated'] loop
            perform pg_temp.content_mcp_qa_assert(not pg_catalog.has_function_privilege(role_name, obj.oid, 'EXECUTE'),
                obj.proname || ' denies ' || role_name);
        end loop;
        perform pg_temp.content_mcp_qa_assert(pg_catalog.has_function_privilege('service_role', obj.oid, 'EXECUTE'),
            obj.proname || ' service_role execute');
    end loop;

    -- Fresh SHA-256 hashes for this run. No existing invite rows are inspected.
    select array_agg(encode(sha256(convert_to('content-mcp-db-qa/' || run_id || '/' || n::text, 'UTF8')), 'hex') order by n)
        into h from pg_catalog.generate_series(1, 128) n;
    perform pg_temp.content_mcp_qa_assert(not exists (
        select 1 from public.content_mcp_invites where invite_hash = any(h)) and not exists (
        select 1 from public.content_mcp_codes where code_hash = any(h)) and not exists (
        select 1 from public.content_mcp_tokens where token_hash = any(h)), 'synthetic hash collision check');
    insert into public.content_mcp_invites(invite_hash, label, expires_at)
        select h[n], 'content-mcp-db-qa-' || n::text, clock_timestamp() + interval '2 hours'
        from pg_catalog.generate_series(1, 5) n;

    -- Malformed input and nonexistent invitation fail without creating codes.
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(null, h[10]), 'denied', 'null invite digest');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], 'invalid'), 'denied', 'invalid code digest');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[128], h[10]), 'denied', 'missing invite');
    perform pg_temp.content_mcp_qa_status(public.content_mcp_issue_code(h[1], h[10], repeat('x', 257),
        'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp', 'content:read', repeat('A', 43)),
        'denied', 'oversized client id');
    perform pg_temp.content_mcp_qa_status(public.content_mcp_issue_code(h[1], h[10], 'qa-public-client',
        'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp', 'content:read', 'not-S256'),
        'denied', 'invalid PKCE format');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[10]), 'allowed', 'issue initial code');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[10]), 'denied', 'duplicate code cannot upsert');
    perform pg_temp.content_mcp_qa_assert((select expires_at <= clock_timestamp() + interval '5 minutes'
        and expires_at > clock_timestamp() from public.content_mcp_codes where code_hash = h[10]), 'five-minute code TTL');

    -- Each persisted binding, including a well-formed but wrong S256 challenge.
    for bindings in select * from (values
        ('other-client', 'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp', 'content:read', repeat('A', 43)),
        ('qa-public-client', 'https://oauth-qa.invalid/other', 'https://oauth-qa.invalid/mcp', 'content:read', repeat('A', 43)),
        ('qa-public-client', 'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/other', 'content:read', repeat('A', 43)),
        ('qa-public-client', 'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp', 'content:write', repeat('A', 43)),
        ('qa-public-client', 'https://oauth-qa.invalid/callback', 'https://oauth-qa.invalid/mcp', 'content:read', repeat('B', 43))
    ) as cases(client_id, redirect_uri, resource, scope, challenge) loop
        perform pg_temp.content_mcp_qa_status(public.content_mcp_exchange_code(h[10], bindings.client_id,
            bindings.redirect_uri, bindings.resource, bindings.scope, bindings.challenge, h[81]), 'denied', 'binding mismatch');
    end loop;
    perform pg_temp.content_mcp_qa_assert((select used_at is null from public.content_mcp_codes where code_hash = h[10])
        and not exists (select 1 from public.content_mcp_tokens where token_hash = h[81]), 'mismatches have no writes');
    result := pg_temp.content_mcp_qa_exchange(h[10], h[81]);
    perform pg_temp.content_mcp_qa_status(result, 'allowed', 'valid exchange');
    perform pg_temp.content_mcp_qa_assert((result ->> 'expires_in')::integer = 3600, 'normal expires_in');
    perform pg_temp.content_mcp_qa_assert((select used_at is not null from public.content_mcp_codes where code_hash = h[10]),
        'successful exchange consumes code');
    perform pg_temp.content_mcp_qa_assert((select expires_at <= clock_timestamp() + interval '1 hour'
        and expires_at > clock_timestamp() from public.content_mcp_tokens where token_hash = h[81]), 'one-hour token TTL');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[10], h[82]), 'denied', 'single use');
    perform pg_temp.content_mcp_qa_assert(not exists (select 1 from public.content_mcp_tokens where token_hash = h[82]), 'replay creates no token');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[11]), 'allowed', 'second code');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[11], h[81]), 'denied', 'duplicate token rejected');
    perform pg_temp.content_mcp_qa_assert((select used_at is null from public.content_mcp_codes where code_hash = h[11]), 'duplicate token rolls back used_at');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[11], h[82]), 'allowed', 'code retry with fresh token');
    perform pg_temp.content_mcp_qa_status(public.content_mcp_consume_token(h[81], 'https://oauth-qa.invalid/other', 'content:read'),
        'denied', 'token resource mismatch');
    perform pg_temp.content_mcp_qa_status(public.content_mcp_consume_token(h[81], 'https://oauth-qa.invalid/mcp', 'content:write'),
        'denied', 'token scope mismatch');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[128]), 'denied', 'missing token');
    perform pg_temp.content_mcp_qa_assert((select minute_used = 0 and day_used = 0
        from public.content_mcp_invites where invite_hash = h[1]), 'denied binding calls do not consume quota');

    -- Expiry and revocation are changed ONLY on this run's fixture keys.
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[12]), 'allowed', 'expiring code setup');
    update public.content_mcp_codes set expires_at = clock_timestamp() - interval '1 second' where code_hash = h[12];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[12], h[83]), 'denied', 'expired code');
    update public.content_mcp_tokens set expires_at = clock_timestamp() - interval '1 second' where token_hash = h[82];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[82]), 'denied', 'expired token');
    update public.content_mcp_tokens set expires_at = clock_timestamp() + interval '1 hour', revoked_at = clock_timestamp()
        where token_hash = h[82];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[82]), 'denied', 'revoked token');
    update public.content_mcp_tokens set revoked_at = null where token_hash = h[82];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[13]), 'allowed', 'invite expiry setup');
    update public.content_mcp_invites set expires_at = clock_timestamp() - interval '1 second' where invite_hash = h[1];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[14]), 'denied', 'expired invite issue');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[13], h[83]), 'denied', 'expired invite exchange');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[81]), 'denied', 'expired invite consume');
    update public.content_mcp_invites set expires_at = clock_timestamp() + interval '2 hours', revoked_at = clock_timestamp()
        where invite_hash = h[1];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[1], h[14]), 'denied', 'revoked invite issue');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[13], h[83]), 'denied', 'revoked invite exchange');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[81]), 'denied', 'revoked invite consume');
    perform pg_temp.content_mcp_qa_assert((select used_at is null from public.content_mcp_codes where code_hash = h[13]), 'inactive invite leaves code unused');

    stamp := clock_timestamp() + interval '2 minutes';
    update public.content_mcp_invites set expires_at = stamp where invite_hash = h[5];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[5], h[15]), 'allowed', 'short invite code');
    perform pg_temp.content_mcp_qa_assert((select expires_at = stamp from public.content_mcp_codes where code_hash = h[15]), 'code bounded by invite expiry');
    result := pg_temp.content_mcp_qa_exchange(h[15], h[83]);
    perform pg_temp.content_mcp_qa_status(result, 'allowed', 'short invite token');
    perform pg_temp.content_mcp_qa_assert((result ->> 'expires_in')::integer between 1 and 120
        and (select expires_at = stamp from public.content_mcp_tokens where token_hash = h[83]), 'shortened token expires_in and expiry');

    -- Shared quota: 100 real accepted calls across two tokens, ten per elapsed
    -- minute window. Advance only fixture timestamps; never sleep or change time.
    for i in 16..17 loop
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[2], h[i]), 'allowed', 'quota code');
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[i], h[i + 68]), 'allowed', 'quota token');
    end loop;
    for batch in 1..10 loop
        if batch > 1 then
            update public.content_mcp_invites set minute_start = clock_timestamp() - interval '2 minutes' where invite_hash = h[2];
        end if;
        for i in 1..10 loop
            perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[84 + (i % 2)]), 'allowed', 'shared quota accepted call');
        end loop;
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[84]), 'limited', 'eleventh shared minute call');
        perform pg_temp.content_mcp_qa_assert((select minute_used = 10 and day_used = batch * 10
            from public.content_mcp_invites where invite_hash = h[2]), 'accepted counts only');
    end loop;
    update public.content_mcp_invites set minute_start = clock_timestamp() - interval '2 minutes' where invite_hash = h[2];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[85]), 'limited', '101st daily call despite minute reset');
    perform pg_temp.content_mcp_qa_assert((select day_used = 100 from public.content_mcp_invites where invite_hash = h[2]), 'daily limit does not increment');
    update public.content_mcp_invites set day_start = clock_timestamp() - interval '25 hours' where invite_hash = h[2];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_consume(h[84]), 'allowed', '24-hour window reset');
    perform pg_temp.content_mcp_qa_assert((select day_used = 1 and minute_used = 1
        from public.content_mcp_invites where invite_hash = h[2]), 'elapsed windows restart at one');

    -- Five pending codes; expired code/token pruning frees the pending slot.
    for i in 20..24 loop
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[3], h[i]), 'allowed', 'pending code capacity');
    end loop;
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[3], h[25]), 'limited', 'sixth pending code');
    perform pg_temp.content_mcp_qa_assert(not exists (select 1 from public.content_mcp_codes where code_hash = h[25]), 'pending cap creates no code');
    update public.content_mcp_codes set expires_at = clock_timestamp() - interval '1 second' where code_hash = h[20];
    insert into public.content_mcp_tokens(token_hash, invite_hash, client_id, resource, scope, expires_at)
        values (h[90], h[3], 'qa-public-client', 'https://oauth-qa.invalid/mcp', 'content:read', clock_timestamp() - interval '1 second');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[3], h[25]), 'allowed', 'expired code frees slot');
    perform pg_temp.content_mcp_qa_assert(not exists (select 1 from public.content_mcp_codes where code_hash = h[20])
        and not exists (select 1 from public.content_mcp_tokens where token_hash = h[90]), 'issue prunes expired children');

    -- Preissue a spare code while below five tokens, then fill the token quota:
    -- both new issuance and exchange of the spare must fail at five active tokens.
    for i in 30..34 loop
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[4], h[i]), 'allowed', 'active cap code setup');
    end loop;
    for i in 30..33 loop
        perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[i], h[i + 61]), 'allowed', 'first four active tokens');
    end loop;
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[4], h[35]), 'allowed', 'spare code before token cap');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[34], h[95]), 'allowed', 'fifth active token');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[4], h[36]), 'limited', 'issue blocked at token cap');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[35], h[96]), 'denied', 'exchange blocked at token cap');
    perform pg_temp.content_mcp_qa_assert(not exists (select 1 from public.content_mcp_codes where code_hash = h[36])
        and not exists (select 1 from public.content_mcp_tokens where token_hash = h[96])
        and (select used_at is null from public.content_mcp_codes where code_hash = h[35]), 'active cap has no writes');
    update public.content_mcp_tokens set revoked_at = clock_timestamp() where token_hash = h[91];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_issue(h[4], h[36]), 'allowed', 'revocation frees issue capacity');
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[35], h[96]), 'allowed', 'revocation frees exchange capacity');
    update public.content_mcp_tokens set expires_at = clock_timestamp() - interval '1 second' where token_hash = h[92];
    perform pg_temp.content_mcp_qa_status(pg_temp.content_mcp_qa_exchange(h[36], h[97]), 'allowed', 'expiry frees exchange capacity');
    perform pg_temp.content_mcp_qa_assert((select count(*) = 5 from public.content_mcp_tokens
        where invite_hash = h[4] and revoked_at is null and expires_at > clock_timestamp()), 'exactly five active tokens');

    insert into pg_temp.content_mcp_qa_result values ('CONTENT_MCP_OAUTH_DB_CHECKS_PASS');
end;
$checks$;

-- This row is reachable only if the assertion block completed successfully.
-- Do not select a literal success string after ROLLBACK: clients continuing on
-- errors could otherwise display a false success marker after a failed test.
select marker from pg_temp.content_mcp_qa_result;
rollback;
