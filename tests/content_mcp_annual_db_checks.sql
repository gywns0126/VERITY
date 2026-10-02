-- LOCAL disposable PostgreSQL only, as migration owner after 2026092602,
-- 2026092701, 2026100201 (Claude), and 2026100202 (annual refresh).
-- Run whole file with psql -X -v ON_ERROR_STOP=1 -f FILE. No production run.
-- Reuses the existing OAuth/refresh/Claude suites' temporary invoker helpers,
-- synthetic hash fixtures, fail-closed assertions and transaction rollback.
-- Run alongside the refresh/Claude suites updated for the same latest schema.
-- This suite covers 6 client/callback bindings x 2 invite lifetimes = 12 cases.
-- No credentials, extensions, network, sleeps or persistent helper objects.
-- On error explicitly ROLLBACK before reusing a connection. Sequential checks
-- do not prove concurrency, real elapsed-year behavior, or migration preservation
-- of pre-existing families; those require separate disposable-DB acceptance.
begin;
set local statement_timeout = '30s';
set local lock_timeout = '3s';
set local search_path = '';
set local timezone = 'UTC'; -- 365 days = 31536000 seconds, independent of DST.

create temporary table pg_temp.annual_qa (
    checks integer not null default 0, cases integer not null default 0, marker text
) on commit drop;
alter table pg_temp.annual_qa enable row level security;
revoke all on pg_temp.annual_qa from public, anon, authenticated, service_role;
insert into pg_temp.annual_qa default values;

create function pg_temp.annual_assert(ok boolean, label text) returns void
language plpgsql set search_path = '' as $f$
begin
    if ok is distinct from true then raise exception 'CONTENT_MCP_ANNUAL_CHECK_FAIL: %', label; end if;
    update pg_temp.annual_qa set checks = checks + 1;
end;
$f$;

create function pg_temp.annual_case(client text, callback text, short_invite boolean) returns void
language plpgsql set search_path = '' as $f$
declare
    h text[];
    run_id text := pg_catalog.gen_random_uuid()::text;
    resource constant text := 'https://project-yw131.vercel.app/api/content_mcp';
    r jsonb;
    started timestamptz;
    finished timestamptz;
    invite_expiry timestamptz;
    family_expiry timestamptz;
    access_expiry timestamptz;
    bounded_expiry timestamptz;
    inactive text;
begin
    select array_agg(encode(sha256(convert_to('annual-qa/' || run_id || '/' || n::text,'UTF8')),'hex') order by n)
        into h from pg_catalog.generate_series(1,16) n;
    perform pg_temp.annual_assert(
        not exists(select 1 from public.content_mcp_invites where invite_hash=any(h))
        and not exists(select 1 from public.content_mcp_codes where code_hash=any(h))
        and not exists(select 1 from public.content_mcp_tokens where token_hash=any(h))
        and not exists(select 1 from public.content_mcp_refresh_families where family_hash=any(h))
        and not exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=any(h)),
        'synthetic fixture collision guard');
    invite_expiry := clock_timestamp() + case when short_invite then interval '2 minutes' else interval '400 days' end;
    insert into public.content_mcp_invites(invite_hash,label,expires_at)
        values(h[1],'annual-sql-check',invite_expiry);
    r := public.content_mcp_issue_code(h[1],h[2],client,callback,resource,'content:read',repeat('A',43));
    perform pg_temp.annual_assert(r->>'status'='allowed','registered callback issue');
    started := clock_timestamp();
    r := public.content_mcp_exchange_code_refresh(h[2],client,callback,resource,
        'content:read',repeat('A',43),h[3],h[4]);
    finished := clock_timestamp();
    perform pg_temp.annual_assert(r->>'status'='allowed','registered callback exchange');
    select expires_at into family_expiry from public.content_mcp_refresh_families where family_hash=h[4];
    select expires_at into access_expiry from public.content_mcp_tokens where token_hash=h[3];
    if short_invite then
        perform pg_temp.annual_assert(family_expiry=invite_expiry and access_expiry=invite_expiry,
            'short invite caps stored family and access expiry');
    else
        perform pg_temp.annual_assert(invite_expiry > finished + interval '365 days'
            and family_expiry between started + interval '365 days' and finished + interval '365 days',
            'actual stored 365-day family with longer invite');
        perform pg_temp.annual_assert((r->>'refresh_expires_in')::integer between 31535970 and 31536000,
            'actual annual refresh TTL not legacy thirty days');
    end if;
    perform pg_temp.annual_assert((r->>'refresh_expires_in')::integer between
        floor(extract(epoch from (family_expiry-finished)))::integer and
        floor(extract(epoch from (family_expiry-started)))::integer,
        'returned refresh TTL matches stored expiry');
    perform pg_temp.annual_assert((r->>'expires_in')::integer between 1 and 3600
        and access_expiry > finished and access_expiry <= finished + interval '1 hour'
        and access_expiry <= family_expiry and access_expiry <= invite_expiry,
        'initial access remains at most one hour');

    r := public.content_mcp_rotate_refresh(h[4],h[5],h[6],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed','first rotation');
    perform pg_temp.annual_assert((select expires_at=family_expiry and rotation_count=1
        from public.content_mcp_refresh_families where family_hash=h[4]),
        'rotation preserves exact original absolute deadline');
    perform pg_temp.annual_assert((r->>'expires_in')::integer between 1 and 3600
        and (select expires_at > clock_timestamp() and expires_at <= clock_timestamp()+interval '1 hour'
            and expires_at <= family_expiry and expires_at <= invite_expiry
            from public.content_mcp_tokens where token_hash=h[5]),'rotated access remains at most one hour');
    r := public.content_mcp_consume_token(h[3],resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='denied','rotation retires old access');
    r := public.content_mcp_consume_token(h[5],resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed','rotated access usable');

    -- Model a nearly elapsed family using only our fixture. Extending its invite
    -- cannot replenish the family, and remaining family life must cap access.
    bounded_expiry := least(family_expiry,clock_timestamp()+interval '90 seconds');
    update public.content_mcp_refresh_families set expires_at=bounded_expiry where family_hash=h[4];
    update public.content_mcp_invites set expires_at=clock_timestamp()+interval '500 days' where invite_hash=h[1];
    started := clock_timestamp();
    r := public.content_mcp_rotate_refresh(h[6],h[7],h[8],client,resource,'content:read');
    finished := clock_timestamp();
    perform pg_temp.annual_assert(r->>'status'='allowed','near-expiry rotation');
    perform pg_temp.annual_assert((select expires_at=bounded_expiry and rotation_count=2
        from public.content_mcp_refresh_families where family_hash=h[4])
        and (select expires_at=bounded_expiry from public.content_mcp_tokens where token_hash=h[7])
        and (r->>'expires_in')::integer between 1 and 90
        and (r->>'refresh_expires_in')::integer between 1 and 90
        and (r->>'refresh_expires_in')::integer between
            floor(extract(epoch from (bounded_expiry-finished)))::integer and
            floor(extract(epoch from (bounded_expiry-started)))::integer,
        'extended invite cannot slide family or access beyond remaining deadline');
    r := public.content_mcp_consume_token(h[7],resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed','near-expiry access usable');

    -- Keep a pending code to check inactive invitations on every entry point.
    r := public.content_mcp_issue_code(h[1],h[9],client,callback,resource,'content:read',repeat('A',43));
    perform pg_temp.annual_assert(r->>'status'='allowed','pending code for inactive invite');
    foreach inactive in array array['expired','revoked'] loop
        update public.content_mcp_invites set
            expires_at=case when inactive='expired' then clock_timestamp()-interval '1 second'
                else clock_timestamp()+interval '500 days' end,
            revoked_at=case when inactive='revoked' then clock_timestamp() else null end
            where invite_hash=h[1];
        r := public.content_mcp_issue_code(h[1],h[12],client,callback,resource,'content:read',repeat('A',43));
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' invite denies issue');
        r := public.content_mcp_exchange_code_refresh(h[9],client,callback,resource,
            'content:read',repeat('A',43),h[10],h[11]);
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' invite denies exchange');
        r := public.content_mcp_rotate_refresh(h[8],h[10],h[11],client,resource,'content:read');
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' invite denies rotation');
        r := public.content_mcp_consume_token(h[7],resource,'content:read');
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' invite denies access');
    end loop;
    update public.content_mcp_invites set revoked_at=null,expires_at=clock_timestamp()+interval '500 days'
        where invite_hash=h[1];
    foreach inactive in array array['expired','revoked'] loop
        update public.content_mcp_refresh_families set
            expires_at=case when inactive='expired' then clock_timestamp()-interval '1 second' else bounded_expiry end,
            revoked_at=case when inactive='revoked' then clock_timestamp() else null end
            where family_hash=h[4];
        r := public.content_mcp_rotate_refresh(h[8],h[10],h[11],client,resource,'content:read');
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' family denies rotation');
    end loop;
    -- Direct family edits do not revoke mapped access; exercise token denial
    -- separately, as required by the existing consume RPC/admin contract.
    foreach inactive in array array['expired','revoked'] loop
        update public.content_mcp_tokens set
            expires_at=case when inactive='expired' then clock_timestamp()-interval '1 second' else bounded_expiry end,
            revoked_at=case when inactive='revoked' then clock_timestamp() else null end
            where token_hash=h[7];
        r := public.content_mcp_consume_token(h[7],resource,'content:read');
        perform pg_temp.annual_assert(r->>'status'='denied',inactive || ' access token denied');
    end loop;
    perform pg_temp.annual_assert((select used_at is null from public.content_mcp_codes where code_hash=h[9])
        and (select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[8])
        and not exists(select 1 from public.content_mcp_codes where code_hash=h[12])
        and not exists(select 1 from public.content_mcp_tokens where token_hash=h[10])
        and not exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=h[11])
        and not exists(select 1 from public.content_mcp_refresh_families where family_hash=h[11]),
        'inactive denials preserve pending credentials and create no replacements');
    -- Seed counters, not thousands of hashes/calls. Restore only our family;
    -- keep its exact deadline and leave invitation/family quotas unchanged.
    update public.content_mcp_refresh_families set revoked_at=null,
        expires_at=bounded_expiry,rotation_count=1000 where family_hash=h[4];
    r := public.content_mcp_rotate_refresh(h[8],h[10],h[11],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed'
        and (select rotation_count=1001 and expires_at=bounded_expiry
            from public.content_mcp_refresh_families where family_hash=h[4]),
        'old 1000 ceiling no longer blocks rotation');
    update public.content_mcp_refresh_families set rotation_count=19999 where family_hash=h[4];
    r := public.content_mcp_rotate_refresh(h[11],h[13],h[14],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed'
        and (select rotation_count=20000 and expires_at=bounded_expiry
            from public.content_mcp_refresh_families where family_hash=h[4]),
        '19999 to 20000 succeeds without extending expiry');
    r := public.content_mcp_rotate_refresh(h[14],h[15],h[16],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='limited'
        and (select rotation_count=20000 and revoked_at is null
            from public.content_mcp_refresh_families where family_hash=h[4])
        and (select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[14])
        and not exists(select 1 from public.content_mcp_tokens where token_hash=h[15])
        and not exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=h[16]),
        '20001st rotation limited without spending current refresh');
    begin
        update public.content_mcp_refresh_families set rotation_count=20001 where family_hash=h[4];
        raise exception 'CONTENT_MCP_ANNUAL_CHECK_FAIL: rotation constraint accepted 20001';
    exception when check_violation then
        perform pg_temp.annual_assert(true,'finite rotation constraint rejects 20001');
    end;
    r := public.content_mcp_consume_token(h[13],resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='allowed','limited rotation leaves current access usable');
    -- Replay must still revoke at the ceiling, before the cumulative cap check.
    r := public.content_mcp_rotate_refresh(h[11],h[15],h[16],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='denied'
        and (select revoked_at is not null and rotation_count=20000
            from public.content_mcp_refresh_families where family_hash=h[4]),
        'spent refresh at ceiling denies and revokes family');
    r := public.content_mcp_consume_token(h[13],resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='denied','ceiling replay revokes current access');
    r := public.content_mcp_rotate_refresh(h[14],h[15],h[16],client,resource,'content:read');
    perform pg_temp.annual_assert(r->>'status'='denied','ceiling replay prevents current refresh reuse');
    update pg_temp.annual_qa set cases=cases+1;
end;
$f$;

do $checks$
declare
    binding record;
begin
    for binding in select * from (values
        ('alphanest-content-chatgpt','https://chatgpt.com/connector_platform_oauth_redirect'),
        ('alphanest-content-perplexity','https://www.perplexity.ai/rest/connections/oauth_callback'),
        ('alphanest-content-claude','https://claude.ai/api/mcp/auth_callback'),
        ('alphanest-content-claude','https://claude.com/api/mcp/auth_callback'),
        ('alphanest-content-claude','http://localhost:1/callback'),
        ('alphanest-content-claude','http://127.0.0.1:65535/callback')
    ) as bindings(client,callback) loop
        perform pg_temp.annual_case(binding.client,binding.callback,false);
        perform pg_temp.annual_case(binding.client,binding.callback,true);
    end loop;
    perform pg_temp.annual_assert((select cases=12 from pg_temp.annual_qa),'12/12 annual cases');
    update pg_temp.annual_qa set marker='CONTENT_MCP_ANNUAL_DB_CHECKS_PASS';
end;
$checks$;
-- Success is recorded inside the assertion block, never printed after rollback.
select marker,checks,cases,12 as expected_cases from pg_temp.annual_qa;
rollback;
