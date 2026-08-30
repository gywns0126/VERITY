-- record_site_visit의 출력 컬럼명과 ON CONFLICT 식별자 충돌을 제거한다.
-- 익명 방문 계약은 유지한다: 날짜 단위 식별자만 기록하며 페이지·검색어·종목·IP는 저장하지 않는다.

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

    insert into public.site_visit_days as d (
        visitor_id, visit_date, first_seen_at, last_seen_at, visit_count
    ) values (
        p_visitor_id, v_today, now(), now(), 1
    )
    on conflict on constraint site_visit_days_pkey do update
      set last_seen_at = now(),
          visit_count = d.visit_count + 1;

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
