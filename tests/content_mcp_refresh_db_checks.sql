-- Run as migration owner after content OAuth migrations through 2026100202. Local
-- functional checks only; no raw credentials, network, extensions, or COMMIT.
-- Run whole file; on assertion error explicitly ROLLBACK if the client stops.
-- Concurrency boundary: this one-connection transaction cannot prove races.
-- Separate multi-session acceptance must cover same-code exchange, same-refresh
-- rotation/replay, and invite revocation racing rotation/consume. All RPCs lock
-- invite first; same-refresh race must yield one allowed then family revocation.
begin;
set local statement_timeout = '30s';
set local lock_timeout = '3s';
set local search_path = '';
set local timezone = 'UTC';
create temporary table pg_temp.refresh_qa_result (checks integer not null default 0, marker text) on commit drop;
alter table pg_temp.refresh_qa_result enable row level security;
revoke all on pg_temp.refresh_qa_result from public, anon, authenticated, service_role;
insert into pg_temp.refresh_qa_result default values;

create function pg_temp.refresh_assert(ok boolean, label text) returns void
language plpgsql set search_path = '' as $f$
begin
    if ok is distinct from true then raise exception 'CONTENT_MCP_REFRESH_CHECK_FAIL: %', label; end if;
    update pg_temp.refresh_qa_result set checks = checks + 1;
end;
$f$;
create function pg_temp.refresh_status(result jsonb, expected text, label text) returns void
language sql set search_path = '' as $f$
    select pg_temp.refresh_assert(result ->> 'status' = expected, label);
$f$;
create function pg_temp.refresh_issue(invite text, code text, client text default 'alphanest-content-perplexity') returns jsonb
language sql set search_path = '' as $f$
    select public.content_mcp_issue_code(invite, code, client,
        case when client = 'alphanest-content-chatgpt' then 'https://chatgpt.com/connector_platform_oauth_redirect'
            else 'https://www.perplexity.ai/rest/connections/oauth_callback' end,
        'https://project-yw131.vercel.app/api/content_mcp', 'content:read', repeat('A',43));
$f$;
create function pg_temp.refresh_exchange(code text, token text, refresh text, client text default 'alphanest-content-perplexity') returns jsonb
language sql set search_path = '' as $f$
    select public.content_mcp_exchange_code_refresh(code, client,
        case when client = 'alphanest-content-chatgpt' then 'https://chatgpt.com/connector_platform_oauth_redirect'
            else 'https://www.perplexity.ai/rest/connections/oauth_callback' end,
        'https://project-yw131.vercel.app/api/content_mcp', 'content:read', repeat('A',43), token, refresh);
$f$;
create function pg_temp.refresh_rotate(refresh text, token text, next_refresh text, client text default 'alphanest-content-perplexity') returns jsonb
language sql set search_path = '' as $f$
    select public.content_mcp_rotate_refresh(refresh, token, next_refresh, client,
        'https://project-yw131.vercel.app/api/content_mcp', 'content:read');
$f$;
create function pg_temp.refresh_consume(token text) returns jsonb
language sql set search_path = '' as $f$
    select public.content_mcp_consume_token(token, 'https://project-yw131.vercel.app/api/content_mcp', 'content:read');
$f$;

do $checks$
declare
    h text[];
    run_id text := pg_catalog.gen_random_uuid()::text;
    obj record;
    role_name text;
    privilege_name text;
    r jsonb;
    i integer;
    original_expiry timestamptz;
    resource text := 'https://project-yw131.vercel.app/api/content_mcp';
begin
    perform pg_temp.refresh_assert((select count(*) = 3 from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid=c.relnamespace where n.nspname='public'
        and c.relname in ('content_mcp_refresh_families','content_mcp_refresh_hashes','content_mcp_refresh_access')),
        'three new tables');
    for obj in select c.oid,c.relname,c.relrowsecurity,c.relacl from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid=c.relnamespace where n.nspname='public'
        and c.relname in ('content_mcp_refresh_families','content_mcp_refresh_hashes','content_mcp_refresh_access') loop
        perform pg_temp.refresh_assert(obj.relrowsecurity and not exists
            (select 1 from pg_catalog.pg_policy where polrelid=obj.oid), obj.relname || ' RLS without policies');
        perform pg_temp.refresh_assert(not exists (select 1 from pg_catalog.aclexplode(obj.relacl) a
            where a.grantee=0), obj.relname || ' no PUBLIC grant');
        foreach role_name in array array['anon','authenticated'] loop
            foreach privilege_name in array array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] loop
                perform pg_temp.refresh_assert(not pg_catalog.has_table_privilege(role_name,obj.oid,privilege_name),
                    obj.relname || ' role privilege denied');
            end loop;
            perform pg_temp.refresh_assert(not pg_catalog.has_any_column_privilege(role_name,obj.oid,'SELECT,INSERT,UPDATE,REFERENCES'),
                obj.relname || ' column privileges denied');
        end loop;
        foreach privilege_name in array array['SELECT','INSERT','UPDATE','DELETE'] loop
            perform pg_temp.refresh_assert(pg_catalog.has_table_privilege('service_role',obj.oid,privilege_name),
                obj.relname || ' service role grant');
        end loop;
    end loop;
    perform pg_temp.refresh_assert((select count(*)=2 from pg_catalog.pg_proc p
        join pg_catalog.pg_namespace n on n.oid=p.pronamespace where n.nspname='public'
        and p.proname in ('content_mcp_exchange_code_refresh','content_mcp_rotate_refresh')), 'two RPCs no overloads');
    for obj in select p.* from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname in ('content_mcp_exchange_code_refresh','content_mcp_rotate_refresh') loop
        perform pg_temp.refresh_assert(obj.prosecdef and obj.proconfig @> array['search_path=""'], 'definer empty search path');
        perform pg_temp.refresh_assert(not exists (select 1 from pg_catalog.aclexplode(obj.proacl) a where a.grantee=0), 'no PUBLIC execute');
        foreach role_name in array array['anon','authenticated'] loop
            perform pg_temp.refresh_assert(not pg_catalog.has_function_privilege(role_name,obj.oid,'EXECUTE'), 'no public client RPC execute');
        end loop;
        perform pg_temp.refresh_assert(pg_catalog.has_function_privilege('service_role',obj.oid,'EXECUTE'), 'service RPC execute');
    end loop;

    select array_agg(encode(sha256(convert_to('refresh-qa/'||run_id||'/'||n::text,'UTF8')),'hex') order by n)
        into h from pg_catalog.generate_series(1,160) n;
    perform pg_temp.refresh_assert(not exists(select 1 from public.content_mcp_invites where invite_hash=any(h))
        and not exists(select 1 from public.content_mcp_codes where code_hash=any(h))
        and not exists(select 1 from public.content_mcp_tokens where token_hash=any(h))
        and not exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=any(h))
        and not exists(select 1 from public.content_mcp_refresh_families where family_hash=any(h)), 'fixture collision check');
    insert into public.content_mcp_invites(invite_hash,label,expires_at)
        select h[n],'refresh-qa-'||n::text,clock_timestamp()
            + case when n=1 then interval '400 days' else interval '45 days' end
            from pg_catalog.generate_series(1,6) n;

    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[1],h[10]),'allowed','issue');
    -- Old generic issuer stays unchanged; the new wrapper independently rejects
    -- even a persisted callback which is not registered for this client.
    perform pg_temp.refresh_status(public.content_mcp_issue_code(h[1],h[150],'alphanest-content-perplexity',
        'https://chatgpt.com/connector_platform_oauth_redirect',resource,'content:read',repeat('A',43)),
        'allowed','generic issuer unchanged');
    perform pg_temp.refresh_status(public.content_mcp_exchange_code_refresh(h[150],'alphanest-content-perplexity',
        'https://chatgpt.com/connector_platform_oauth_redirect',resource,'content:read',repeat('A',43),h[151],h[152]),
        'denied','callback client mismatch');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_codes where code_hash=h[150]),
        'callback mismatch leaves code unused');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[10],h[20],null),'denied','null refresh');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[10],h[20],'bad'),'denied','bad refresh');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[10],h[20],h[30],'unregistered'),'denied','unregistered client');
    perform pg_temp.refresh_status(public.content_mcp_exchange_code_refresh(h[10],'alphanest-content-perplexity',
        'https://www.perplexity.ai/rest/connections/oauth_callback',resource,'content:read',repeat('B',43),h[20],h[30]),
        'denied','wrong PKCE');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_codes where code_hash=h[10]), 'bad exchange leaves code unused');
    r:=pg_temp.refresh_exchange(h[10],h[20],h[30]);
    perform pg_temp.refresh_status(r,'allowed','initial exchange');
    perform pg_temp.refresh_assert((r->>'expires_in')::integer between 1 and 3600
        and (r->>'refresh_expires_in')::integer between 31535900 and 31536000,'access and 365-day TTL');
    select expires_at into original_expiry from public.content_mcp_refresh_families where family_hash=h[30];
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[10],h[21],h[31]),'denied','code replay');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[30],h[21],h[31],'alphanest-content-chatgpt'),'denied','other registered client');
    perform pg_temp.refresh_status(public.content_mcp_rotate_refresh(h[30],h[21],h[31],'alphanest-content-perplexity',resource||'/wrong','content:read'),
        'denied','wrong resource');
    perform pg_temp.refresh_status(public.content_mcp_rotate_refresh(h[30],h[21],h[31],'alphanest-content-perplexity',resource,'content:write'),
        'denied','wrong scope');
    perform pg_temp.refresh_assert((select revoked_at is null and rotation_count=0 from public.content_mcp_refresh_families where family_hash=h[30]),
        'wrong bindings cannot revoke or spend family');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[30],h[20],h[31]),'denied','duplicate access hash rolls back');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[30])
        and (select revoked_at is null from public.content_mcp_tokens where token_hash=h[20]),'collision preserves prior credentials');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[30],h[21],h[31]),'allowed','rotate');
    perform pg_temp.refresh_assert((select expires_at=original_expiry and rotation_count=1 from public.content_mcp_refresh_families where family_hash=h[30]),
        'rotation never extends family expiry');
    perform pg_temp.refresh_status(pg_temp.refresh_consume(h[20]),'denied','old access retired');
    perform pg_temp.refresh_status(pg_temp.refresh_consume(h[21]),'allowed','new access live');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[31],h[22],h[30]),'denied','duplicate refresh rolls back');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[31]),'duplicate refresh unspent');
    -- Wrong binding of a SPENT hash must not activate replay revocation either.
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[30],h[22],h[32],'alphanest-content-chatgpt'),'denied','spent hash wrong-client no DoS');
    perform pg_temp.refresh_assert((select revoked_at is null from public.content_mcp_refresh_families where family_hash=h[30]),'family still live');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[30],h[22],h[32]),'denied','valid replay');
    perform pg_temp.refresh_assert((select revoked_at is not null from public.content_mcp_refresh_families where family_hash=h[30]),'replay revokes family');
    perform pg_temp.refresh_status(pg_temp.refresh_consume(h[21]),'denied','replay revokes current access');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[31],h[22],h[32]),'denied','revoked family cannot rotate');
    perform pg_temp.refresh_assert((select count(*)=2 from public.content_mcp_refresh_hashes where family_hash=h[30]),'spent history retained');

    -- Short invitation bounds both tokens. Revocation/expiry checked on every RPC.
    update public.content_mcp_invites set expires_at=clock_timestamp()+interval '2 minutes' where invite_hash=h[2];
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[2],h[11],'alphanest-content-chatgpt'),'allowed','ChatGPT issue');
    r:=pg_temp.refresh_exchange(h[11],h[23],h[33],'alphanest-content-chatgpt');
    perform pg_temp.refresh_status(r,'allowed','ChatGPT refresh exchange');
    perform pg_temp.refresh_assert((r->>'refresh_expires_in')::integer between 1 and 120
        and (r->>'expires_in')::integer between 1 and (r->>'refresh_expires_in')::integer,'short invitation TTL');
    update public.content_mcp_invites set expires_at=clock_timestamp()+interval '0.5 seconds' where invite_hash=h[2];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[33],h[24],h[34],'alphanest-content-chatgpt'),
        'denied','subsecond remaining lifetime denied');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[33]),
        'subsecond denial preserves refresh');
    update public.content_mcp_invites set revoked_at=clock_timestamp() where invite_hash=h[2];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[33],h[24],h[34],'alphanest-content-chatgpt'),'denied','invite revoked rotation');
    perform pg_temp.refresh_status(pg_temp.refresh_consume(h[23]),'denied','invite revoked access');
    update public.content_mcp_invites set revoked_at=null, expires_at=clock_timestamp()-interval '1 second' where invite_hash=h[2];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[33],h[24],h[34],'alphanest-content-chatgpt'),'denied','invite expired rotation');

    -- Five retained families (even revoked) and five active access tokens.
    for i in 40..44 loop
        perform pg_temp.refresh_status(pg_temp.refresh_issue(h[3],h[i]),'allowed','capacity issue');
        perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[i],h[i+10],h[i+20]),'allowed','capacity exchange');
    end loop;
    update public.content_mcp_tokens set revoked_at=clock_timestamp() where token_hash=h[50];
    update public.content_mcp_refresh_families set revoked_at=clock_timestamp() where family_hash=h[60];
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[3],h[45]),'allowed','spare code after access revocation');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[45],h[55],h[65]),'limited','retained family cap');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_codes where code_hash=h[45]),'family cap preserves code');
    update public.content_mcp_refresh_families set expires_at=clock_timestamp()-interval '1 second' where family_hash=h[60];
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[45],h[55],h[65]),'allowed','expired family cleanup frees slot');
    perform pg_temp.refresh_assert(not exists(select 1 from public.content_mcp_refresh_hashes where family_hash=h[60]),'only expired family hashes pruned');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[61],h[56],h[66]),'allowed','rotation works at five active-token cap');
    perform pg_temp.refresh_assert((select count(*)=5 from public.content_mcp_tokens where invite_hash=h[3]
        and revoked_at is null and expires_at>clock_timestamp()),'active cap remains five');

    -- Family minute/cumulative bounds and shared invitation quota with rollback.
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[4],h[70]),'allowed','rate fixture issue');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[70],h[80],h[90]),'allowed','rate fixture exchange');
    for i in 90..94 loop
        perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[i],h[i+11],h[i+1]),'allowed','five rotations');
    end loop;
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[95],h[106],h[96]),'limited','sixth rotation limited');
    update public.content_mcp_refresh_families set minute_start=clock_timestamp()-interval '2 minutes' where family_hash=h[90];
    update public.content_mcp_invites set minute_used=10,minute_start=clock_timestamp() where invite_hash=h[4];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[95],h[106],h[96]),'limited','shared minute quota');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_refresh_hashes where refresh_hash=h[95])
        and (select revoked_at is null from public.content_mcp_tokens where token_hash=h[105]),'quota rollback restores refresh and access');
    update public.content_mcp_invites set minute_start=clock_timestamp()-interval '2 minutes',day_start=clock_timestamp(),day_used=100 where invite_hash=h[4];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[95],h[106],h[96]),'limited','shared daily quota');
    update public.content_mcp_invites set day_start=clock_timestamp()-interval '2 days' where invite_hash=h[4];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[95],h[106],h[96]),'allowed','quota reset permits rotation');
    update public.content_mcp_refresh_families set rotation_count=20000 where family_hash=h[90];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[96],h[107],h[97]),'limited','lifetime rotation cap');
    update public.content_mcp_refresh_families set rotation_count=6,expires_at=clock_timestamp()-interval '1 second' where family_hash=h[90];
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[96],h[107],h[97]),'denied','family expiry');

    -- Old issuer expiry cleanup must not destroy spent refresh replay evidence.
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[5],h[110]),'allowed','retention issue');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[110],h[111],h[112]),'allowed','retention exchange');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[112],h[113],h[114]),'allowed','retention rotation');
    update public.content_mcp_tokens set expires_at=clock_timestamp()-interval '1 second' where token_hash=h[111];
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[5],h[115]),'allowed','old issuer cleans expired access');
    perform pg_temp.refresh_assert(not exists(select 1 from public.content_mcp_refresh_access where token_hash=h[111])
        and exists(select 1 from public.content_mcp_refresh_hashes where refresh_hash=h[112] and used_at is not null), 'access prune retains spent hash');
    perform pg_temp.refresh_status(pg_temp.refresh_rotate(h[112],h[116],h[117]),'denied','replay after access expiry');
    perform pg_temp.refresh_status(pg_temp.refresh_consume(h[113]),'denied','replay after expiry revokes latest access');

    -- Initial exchange failures roll back old code consumption and every new row.
    perform pg_temp.refresh_status(pg_temp.refresh_issue(h[6],h[120]),'allowed','quota exchange issue');
    update public.content_mcp_invites set minute_start=clock_timestamp(),minute_used=10 where invite_hash=h[6];
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[120],h[121],h[122]),'limited','initial exchange quota');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_codes where code_hash=h[120])
        and not exists(select 1 from public.content_mcp_tokens where token_hash=h[121])
        and not exists(select 1 from public.content_mcp_refresh_families where family_hash=h[122]), 'initial quota fully rolls back');
    update public.content_mcp_invites set minute_start=clock_timestamp()-interval '2 minutes' where invite_hash=h[6];
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[120],h[121],h[112]),'denied','refresh collision fully rolls back');
    perform pg_temp.refresh_assert((select used_at is null from public.content_mcp_codes where code_hash=h[120]),'collision leaves code reusable');
    perform pg_temp.refresh_status(pg_temp.refresh_exchange(h[120],h[121],h[122]),'allowed','retry after rollback');
    update pg_temp.refresh_qa_result set marker='CONTENT_MCP_REFRESH_DB_CHECKS_PASS';
end;
$checks$;
select marker,checks from pg_temp.refresh_qa_result;
rollback;
