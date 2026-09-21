-- AlphaConsole public observation records.
--
-- This extends the existing community thesis table without creating consumer-looking
-- accounts. System records are public, neutral observations sourced from official
-- DART/SEC filings. User RLS remains unchanged; only service_role can create them.

begin;

alter table public.user_thesis
    add column if not exists author_kind text not null default 'user',
    add column if not exists system_label text,
    add column if not exists data_as_of timestamptz,
    add column if not exists published_at timestamptz,
    add column if not exists source_url text,
    add column if not exists source_title text,
    add column if not exists source_key text,
    add column if not exists content_version integer,
    add column if not exists observation_meta jsonb not null default '{}'::jsonb;

-- Existing user rows keep user_id. System rows deliberately have no auth identity.
alter table public.user_thesis alter column user_id drop not null;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.user_thesis'::regclass
          and conname = 'user_thesis_author_contract'
    ) then
        alter table public.user_thesis
            add constraint user_thesis_author_contract check (
                (author_kind = 'user' and user_id is not null)
                or
                (
                    author_kind = 'system'
                    and user_id is null
                    and stance = 'watch'
                    and is_public is true
                    and system_label is not null
                    and data_as_of is not null
                    and published_at is not null
                    and source_key is not null
                    and source_url ~ '^https://(dart\\.fss\\.or\\.kr|www\\.sec\\.gov)/'
                    and content_version is not null
                    and char_length(note) between 1 and 5000
                )
            );
    end if;
end $$;

create unique index if not exists idx_ut_system_source_key
    on public.user_thesis(source_key)
    where author_kind = 'system';

create index if not exists idx_ut_system_public_created
    on public.user_thesis(created_at desc)
    where author_kind = 'system' and is_public and not hidden;

create or replace function public.guard_system_thesis_immutable()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
    if tg_op = 'DELETE' and old.author_kind = 'system' then
        raise exception 'system observation records are immutable; hide the record instead'
            using errcode = '42501';
    end if;

    if tg_op = 'UPDATE' and old.author_kind = 'system' and (
        new.author_kind is distinct from old.author_kind
        or new.user_id is distinct from old.user_id
        or new.ticker is distinct from old.ticker
        or new.market is distinct from old.market
        or new.stance is distinct from old.stance
        or new.note is distinct from old.note
        or new.entry_price is distinct from old.entry_price
        or new.created_at is distinct from old.created_at
        or new.system_label is distinct from old.system_label
        or new.data_as_of is distinct from old.data_as_of
        or new.published_at is distinct from old.published_at
        or new.source_url is distinct from old.source_url
        or new.source_title is distinct from old.source_title
        or new.source_key is distinct from old.source_key
        or new.content_version is distinct from old.content_version
        or new.observation_meta is distinct from old.observation_meta
    ) then
        raise exception 'system observation content is immutable; publish a new version'
            using errcode = '42501';
    end if;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_trigger
        where tgrelid = 'public.user_thesis'::regclass
          and tgname = 'trg_guard_system_thesis_immutable'
          and not tgisinternal
    ) then
        create trigger trg_guard_system_thesis_immutable
        before update or delete on public.user_thesis
        for each row execute function public.guard_system_thesis_immutable();
    end if;
end $$;

create table if not exists public.system_thesis_schedule (
    schedule_id text primary key,
    next_run_at timestamptz not null,
    last_run_at timestamptz,
    last_result jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    constraint system_thesis_schedule_id check (schedule_id = 'alphaconsole_public')
);

alter table public.system_thesis_schedule enable row level security;
revoke all on table public.system_thesis_schedule from anon, authenticated;

insert into public.system_thesis_schedule(schedule_id, next_run_at, last_result)
values ('alphaconsole_public', now(), '{"status":"ready"}'::jsonb)
on conflict (schedule_id) do nothing;

-- 039_site_usage_signals may already exist in production while its repo handoff is
-- being completed by another session. Preserve its current body and narrow only
-- the three community counters so system records never inflate member activity.
do $$
declare
    v_oid oid;
    v_before text;
    v_after text;
    v_total_pattern text := '(select count(*) from public.user_thesis)';
    v_public_pattern text := '(select count(*) from public.user_thesis where is_public is true and hidden is false)';
    v_week_pattern text := '(select count(*) from public.user_thesis where created_at>=((v_today-6)::timestamp at time zone ''Asia/Seoul''))';
begin
    select p.oid into v_oid
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'get_site_growth_stats'
      and pg_get_function_identity_arguments(p.oid) = '';

    if v_oid is not null then
        v_before := pg_get_functiondef(v_oid);
        if strpos(v_before, v_total_pattern) = 0
           or strpos(v_before, v_public_pattern) = 0
           or strpos(v_before, v_week_pattern) = 0 then
            raise exception 'get_site_growth_stats community counter shape changed; reconcile before migration';
        end if;
        v_after := replace(
            v_before,
            v_total_pattern,
            '(select count(*) from public.user_thesis where author_kind = ''user'')'
        );
        v_after := replace(
            v_after,
            v_public_pattern,
            '(select count(*) from public.user_thesis where author_kind = ''user'' and is_public is true and hidden is false)'
        );
        v_after := replace(
            v_after,
            v_week_pattern,
            '(select count(*) from public.user_thesis where author_kind = ''user'' and created_at>=((v_today-6)::timestamp at time zone ''Asia/Seoul''))'
        );
        execute v_after;
    end if;
end $$;

comment on column public.user_thesis.author_kind is
    'user = member-authored thesis; system = AlphaConsole neutral public observation';
comment on column public.user_thesis.observation_meta is
    'Machine-readable source and generator trail. Public copy is deterministic, not LLM-generated.';

commit;
