-- Shared fixed-window counters for the two initial API consumers.
-- No member records are changed. Client roles cannot read or consume counters.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';

create table if not exists public.api_rate_buckets (
    scope text not null,
    subject text not null,
    window_start timestamptz not null,
    used integer not null check (used >= 0),
    primary key (scope, subject)
);
alter table public.api_rate_buckets enable row level security;
revoke all on public.api_rate_buckets from public, anon, authenticated;
grant select, insert, update on public.api_rate_buckets to service_role;

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
    -- Fixed policies, not caller-controlled limits. Only the backend can invoke.
    if p_scope = 'holdings' then v_cap := 80;
    elsif p_scope = 'visitor_ping' then v_cap := 30;
    else raise exception 'unsupported rate scope' using errcode = '22023';
    end if;
    if p_subject is null or p_subject !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid rate subject' using errcode = '22023';
    end if;
    -- All instances serialize the combined subject/global decision in Postgres.
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

do $$ begin
    if has_function_privilege('anon','public.consume_api_rate(text,text)','EXECUTE')
        or has_function_privilege('authenticated','public.consume_api_rate(text,text)','EXECUTE')
        or not has_function_privilege('service_role','public.consume_api_rate(text,text)','EXECUTE') then
        raise exception 'rate function privileges are unsafe';
    end if;
end $$;
commit;
