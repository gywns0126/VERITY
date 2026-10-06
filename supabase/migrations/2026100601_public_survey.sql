-- Private anonymous survey. Requires 2026100301_api_rate_boundaries.sql.
-- Apply separately before deploying the API; this file does not modify members,
-- community_support, passive telemetry, their policies, or historical migrations.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';

create or replace function public.public_survey_answers_valid(p_answers jsonb)
returns boolean language plpgsql immutable set search_path = ''
as $$
begin
    if p_answers is null or jsonb_typeof(p_answers) is distinct from 'object' then return false; end if;
    if not (p_answers ?& array['purpose','features','outcome','discovery','comment'])
       or p_answers - array['purpose','features','outcome','discovery','comment'] <> '{}'::jsonb then return false; end if;
    if p_answers->'purpose' <> 'null'::jsonb and
       (jsonb_typeof(p_answers->'purpose') <> 'string' or p_answers->>'purpose' not in ('company','market','gurus','learn','browse','other')) then return false; end if;
    if p_answers->'outcome' <> 'null'::jsonb and
       (jsonb_typeof(p_answers->'outcome') <> 'string' or p_answers->>'outcome' not in ('yes','partly','no','not_yet','no_goal')) then return false; end if;
    if p_answers->'discovery' <> 'null'::jsonb and
       (jsonb_typeof(p_answers->'discovery') <> 'string' or p_answers->>'discovery' not in ('search','community','friend','unknown','other')) then return false; end if;
    if jsonb_typeof(p_answers->'features') <> 'array' then return false; end if;
    if jsonb_array_length(p_answers->'features') > 7 then return false; end if;
    if exists (select 1 from jsonb_array_elements(p_answers->'features') f
        where jsonb_typeof(f) <> 'string' or f #>> '{}' not in ('report','map','market','gurus','education','other','not_used')) then return false; end if;
    if (select count(*) <> count(distinct f) from jsonb_array_elements(p_answers->'features') f) then return false; end if;
    if p_answers->'features' ? 'not_used' and jsonb_array_length(p_answers->'features') <> 1 then return false; end if;
    if jsonb_typeof(p_answers->'comment') <> 'string' or char_length(p_answers->>'comment') > 500 then return false; end if;
    return p_answers->>'purpose' is not null or p_answers->>'outcome' is not null
        or p_answers->>'discovery' is not null or jsonb_array_length(p_answers->'features') > 0
        or p_answers->>'comment' ~ '[^[:space:]]';
end;
$$;
revoke all on function public.public_survey_answers_valid(jsonb) from public, anon, authenticated;
grant execute on function public.public_survey_answers_valid(jsonb) to service_role;

create table if not exists public.public_survey_responses (
    survey_version text not null check (survey_version = '2026-10-v1'),
    request_id uuid not null,
    client_hash text not null check (client_hash ~ '^[0-9a-f]{64}$'),
    answers jsonb not null check (public.public_survey_answers_valid(answers)),
    created_at timestamptz not null default now(),
    primary key (survey_version, request_id),
    unique (survey_version, client_hash)
);
alter table public.public_survey_responses enable row level security;
-- No client policies, views, public read RPC, or direct service insert endpoint.
revoke all on public.public_survey_responses from public, anon, authenticated, service_role;
grant select on public.public_survey_responses to service_role;
comment on table public.public_survey_responses is
    'Private survey answers; server HMAC browser identity, never a person count. No raw client ID, account ID, IP or contact fields. Retain rows for version-lifetime replay/deduplication; no automatic cleanup.';

-- Same policy and atomic decision as 2026100301, plus survey only.
-- 10/minute/IP-HMAC-bucket leaves room for normal low-frequency survey traffic
-- and shared networks while limiting fresh-ID abuse; this is a chosen policy,
-- not a measured audience threshold. 4096 anonymous buckets can collide.
-- Existing holdings 80/min, visitor 30/min, global 10000/hour are unchanged.
create or replace function public.consume_api_rate(p_scope text, p_subject text)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_minute timestamptz;
    v_hour timestamptz;
    v_user_used integer;
    v_global_used integer;
    v_cap integer;
    v_retry integer;
begin
    if p_scope = 'holdings' then v_cap := 80;
    elsif p_scope = 'visitor_ping' then v_cap := 30;
    elsif p_scope = 'survey' then v_cap := 10;
    else raise exception 'unsupported rate scope' using errcode = '22023';
    end if;
    if p_subject is null or p_subject !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid rate subject' using errcode = '22023';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('alphanest-api-rate:' || p_scope, 0));
    v_now := clock_timestamp();
    v_minute := pg_catalog.to_timestamp(floor(extract(epoch from v_now) / 60) * 60);
    v_hour := pg_catalog.to_timestamp(floor(extract(epoch from v_now) / 3600) * 3600);
    insert into public.api_rate_buckets values (p_scope, 'global', v_hour, 0)
        on conflict (scope, subject) do nothing;
    select case when window_start = v_hour then used else 0 end into v_global_used
        from public.api_rate_buckets where scope = p_scope and subject = 'global';
    select case when window_start = v_minute then used else 0 end into v_user_used
        from public.api_rate_buckets where scope = p_scope and subject = p_subject;
    if v_global_used >= 10000 then
        v_retry := greatest(1, ceil(extract(epoch from v_hour + interval '1 hour' - v_now))::integer);
        return jsonb_build_object('allowed', false, 'retry_after_sec', v_retry, 'limit_type', 'global_hour');
    elsif coalesce(v_user_used, 0) >= v_cap then
        v_retry := greatest(1, ceil(extract(epoch from v_minute + interval '1 minute' - v_now))::integer);
        return jsonb_build_object('allowed', false, 'retry_after_sec', v_retry, 'limit_type', 'subject_minute');
    end if;
    update public.api_rate_buckets set window_start = v_hour, used = v_global_used + 1
        where scope = p_scope and subject = 'global';
    insert into public.api_rate_buckets values (p_scope, p_subject, v_minute, coalesce(v_user_used, 0) + 1)
        on conflict (scope, subject) do update set window_start = excluded.window_start, used = excluded.used;
    return jsonb_build_object('allowed', true);
end;
$$;
revoke all on function public.consume_api_rate(text,text) from public, anon, authenticated;
grant execute on function public.consume_api_rate(text,text) to service_role;

create or replace function public.submit_public_survey(
    p_version text, p_request_id uuid, p_client_hash text, p_answers jsonb, p_rate_subject text
)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
    v_existing public.public_survey_responses%rowtype;
    v_answers jsonb;
    v_rate jsonb;
begin
    if p_version is distinct from '2026-10-v1' or p_request_id is null
       or p_client_hash is null or p_client_hash !~ '^[0-9a-f]{64}$'
       or p_rate_subject is null or p_rate_subject !~ '^[0-9a-f]{64}$'
       or not public.public_survey_answers_valid(p_answers) then
        return jsonb_build_object('error', 'invalid_payload');
    end if;
    v_answers := jsonb_set(p_answers, '{features}',
        (select coalesce(jsonb_agg(f order by f), '[]'::jsonb) from jsonb_array_elements(p_answers->'features') f));
    -- A short version-wide transaction lock orders both unique-key decisions,
    -- including same request/different client races. No application-local lock.
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('alphanest-survey:' || p_version, 0));
    select * into v_existing from public.public_survey_responses
        where survey_version = p_version and request_id = p_request_id;
    if found then
        if v_existing.client_hash = p_client_hash and v_existing.answers = v_answers then
            return jsonb_build_object('ok', true, 'duplicate', true);
        end if;
        return jsonb_build_object('error', 'idempotency_conflict');
    end if;
    if exists (select 1 from public.public_survey_responses
        where survey_version = p_version and client_hash = p_client_hash) then
        return jsonb_build_object('error', 'already_submitted');
    end if;
    -- Replay and one-browser/version checks precede the new-submission budget.
    -- Limit and insert commit together; a failed insert cannot spend the budget.
    v_rate := public.consume_api_rate('survey', p_rate_subject);
    if v_rate->'allowed' is distinct from 'true'::jsonb then
        return jsonb_build_object('error', 'rate_limited', 'retry_after_sec', v_rate->'retry_after_sec');
    end if;
    insert into public.public_survey_responses(survey_version, request_id, client_hash, answers)
        values (p_version, p_request_id, p_client_hash, v_answers);
    return jsonb_build_object('ok', true, 'duplicate', false);
end;
$$;
revoke all on function public.submit_public_survey(text,uuid,text,jsonb,text) from public, anon, authenticated;
grant execute on function public.submit_public_survey(text,uuid,text,jsonb,text) to service_role;

do $$ begin
    if has_function_privilege('anon','public.submit_public_survey(text,uuid,text,jsonb,text)','EXECUTE')
       or has_function_privilege('authenticated','public.submit_public_survey(text,uuid,text,jsonb,text)','EXECUTE')
       or not has_function_privilege('service_role','public.submit_public_survey(text,uuid,text,jsonb,text)','EXECUTE')
       or has_table_privilege('anon','public.public_survey_responses','SELECT')
       or has_table_privilege('authenticated','public.public_survey_responses','SELECT') then
        raise exception 'survey privileges are unsafe';
    end if;
end $$;
commit;
