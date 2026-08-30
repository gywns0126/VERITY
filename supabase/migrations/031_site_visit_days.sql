-- 익명 재방문을 날짜 단위로만 측정한다. 페이지 본문·검색어·종목·IP는 저장하지 않는다.
-- 유료 기능 활성화와 분리된 측정 전용 계약이다.

create table if not exists public.site_visit_days (
    visitor_id text not null check (char_length(visitor_id) between 16 and 64),
    visit_date date not null default (timezone('Asia/Seoul', now()))::date,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    visit_count integer not null default 1 check (visit_count > 0),
    primary key (visitor_id, visit_date)
);

alter table public.site_visit_days enable row level security;
revoke all on public.site_visit_days from anon, authenticated;

create or replace function public.record_site_visit(p_visitor_id text)
returns table (
    visit_date date,
    visit_count integer,
    distinct_days_30 integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_today date := (timezone('Asia/Seoul', now()))::date;
begin
    if p_visitor_id is null
       or char_length(p_visitor_id) < 16
       or char_length(p_visitor_id) > 64
       or p_visitor_id !~ '^[A-Za-z0-9_-]+$' then
        raise exception 'invalid visitor id';
    end if;

    insert into public.site_visit_days (
        visitor_id, visit_date, first_seen_at, last_seen_at, visit_count
    ) values (
        p_visitor_id, v_today, now(), now(), 1
    )
    on conflict (visitor_id, visit_date) do update
      set last_seen_at = now(),
          visit_count = public.site_visit_days.visit_count + 1;

    return query
    select
        v_today,
        d.visit_count,
        (
            select count(*)::integer
            from public.site_visit_days h
            where h.visitor_id = p_visitor_id
              and h.visit_date >= v_today - 29
        )
    from public.site_visit_days d
    where d.visitor_id = p_visitor_id
      and d.visit_date = v_today;
end;
$$;

revoke all on function public.record_site_visit(text) from public;
grant execute on function public.record_site_visit(text) to anon, authenticated;

comment on table public.site_visit_days is
    'Anonymous daily revisit measurement. No page content, ticker, query, IP, or paid entitlement.';
