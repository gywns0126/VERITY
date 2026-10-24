-- A partial catch-up result completes exactly one DART date. The explicit
-- phase distinguishes replay of the saved boundary from the next-date pass.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(20261012, 1001);

do $$
begin
    if (select pg_catalog.md5(p.prosrc) from pg_catalog.pg_proc p
        where p.oid='public.member_map_refresh_state_valid(text,jsonb)'::regprocedure)
            is distinct from 'adcb68fa2b0dd146469fb60c0eb277a1'
       or (select pg_catalog.md5(p.prosrc) from pg_catalog.pg_proc p
        where p.oid='public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)'::regprocedure)
            is distinct from '687eadd229ca3130bf8adaa492492058' then
        raise exception 'refresh-catchup-function-drift';
    end if;
end;
$$;

create function public.member_map_refresh_catchup_valid(p_source text, p_state jsonb)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
    v_pages integer;
begin
    if p_source is distinct from 'DART'
       or p_state->>'catchup_phase' is null
       or p_state->>'catchup_phase' not in ('replayed','advanced')
       or not coalesce(public.member_map_refresh_state_valid(p_source,p_state-'catchup_phase'),false) then
        return false;
    end if;
    if p_state->>'status' in ('partial','error') and p_state->>'error' is not null
       and p_state#>>'{coverage,historical_gap}' is distinct from 'true' then
        return coalesce((p_state#>>'{cursor,checked_at}')::timestamptz <= (p_state->>'last_attempt_at')::timestamptz,false);
    end if;
    if p_state->>'status' is distinct from 'partial' or p_state->>'error' is not null
       or p_state#>>'{coverage,historical_gap}' is distinct from 'true' then return false; end if;
    v_pages := (p_state#>>'{coverage,total_pages}')::integer;
    return coalesce(v_pages <= 10
       and (p_state#>>'{coverage,pages_succeeded}')::integer = greatest(1,v_pages)
       and (p_state#>>'{coverage,listing_records}')::integer = (p_state#>>'{coverage,total_records}')::integer
       and (p_state->>'requests')::integer = (p_state#>>'{coverage,pages_succeeded}')::integer
       and (p_state#>>'{cursor,checked_at}')::timestamptz = (p_state->>'last_attempt_at')::timestamptz
       and (p_state#>>'{cursor,through_date}')::date < ((p_state->>'last_attempt_at')::timestamptz at time zone 'Asia/Seoul')::date,false);
exception when others then
    return false;
end;
$$;
revoke all on function public.member_map_refresh_catchup_valid(text,jsonb) from public, anon, authenticated, service_role;

do $$
begin
    if public.member_map_refresh_catchup_valid('DART','{"catchup_phase":"replayed"}'::jsonb) is distinct from false
       or public.member_map_refresh_catchup_valid('DART','{"status":"partial","error":null,"coverage":{"historical_gap":true}}'::jsonb) is distinct from false
       or public.member_map_refresh_catchup_valid('SEC','{"catchup_phase":"replayed"}'::jsonb) is distinct from false then
        raise exception 'refresh-catchup-null-validation';
    end if;
end;
$$;

-- Replace only the checkpoint's state CHECK; retain the legacy validator for
-- ordinary states and accept the additional phase only through the narrow helper.
do $$
declare
    v_name text;
    v_count integer;
begin
    select count(*), min(c.conname) into v_count, v_name
      from pg_catalog.pg_constraint c
     where c.conrelid='public.member_map_refresh_checkpoint'::regclass and c.contype='c'
       and pg_catalog.pg_get_constraintdef(c.oid) like '%member_map_refresh_state_valid%';
    if v_count <> 1 then raise exception 'refresh-checkpoint-state-constraint'; end if;
    execute pg_catalog.format('alter table public.member_map_refresh_checkpoint drop constraint %I',v_name);
end;
$$;
alter table public.member_map_refresh_checkpoint add constraint member_map_refresh_checkpoint_state_valid_check
    check (coalesce(public.member_map_refresh_state_valid(source,state),false)
           or coalesce(public.member_map_refresh_catchup_valid(source,state),false));

-- Ordinary partial failures still retain the prior cursor. One-date replay
-- may update same-date IDs; only a completed replay permits next-date advance.
create or replace function public.member_map_refresh_save(p_source text, p_owner uuid, p_generation bigint,
                                               p_expected_revision bigint, p_state jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_row public.member_map_refresh_checkpoint%rowtype;
    v_now timestamptz;
    v_day date;
    v_catchup_valid boolean;
begin
    if p_source is null or p_source not in ('SEC','DART','news') or p_owner is null or p_generation is null or p_generation<1
       or p_expected_revision is null or p_expected_revision<0 then
        raise exception using errcode='22023', message='refresh-checkpoint-save-input';
    end if;
    select * into strict v_row from public.member_map_refresh_checkpoint where source=p_source for update;
    v_now := pg_catalog.clock_timestamp();
    v_day := (v_now at time zone 'Asia/Seoul')::date;
    if v_row.lease_owner is distinct from p_owner or v_row.lease_generation <> p_generation
       or v_row.lease_until is null or v_row.lease_until <= v_now
       or (p_source='DART' and v_row.request_day is distinct from v_day) then
        return pg_catalog.jsonb_build_object('status','lease-lost');
    end if;
    if v_row.revision <> p_expected_revision then return pg_catalog.jsonb_build_object('status','revision-conflict'); end if;
    if p_state='{}'::jsonb or not (coalesce(public.member_map_refresh_state_valid(p_source,p_state),false)
                                     or coalesce(public.member_map_refresh_catchup_valid(p_source,p_state),false)) then
        raise exception using errcode='22023', message='refresh-checkpoint-invalid-state';
    end if;
    v_catchup_valid := coalesce(public.member_map_refresh_catchup_valid(p_source,p_state)
        and ((v_row.state#>>'{cursor,through_date}' is null
              and p_state->>'catchup_phase'='replayed'
              and p_state#>>'{coverage,historical_gap}'='true')
          or (v_row.state#>>'{cursor,through_date}' is not null
              and p_state->>'catchup_phase' = v_row.state->>'catchup_phase'
              and p_state->>'error' is not null
              and p_state->'cursor' is not distinct from v_row.state->'cursor')
          or (v_row.state#>>'{cursor,through_date}' is not null
              and p_state#>>'{coverage,historical_gap}'='true'
              and ((p_state->>'catchup_phase'='replayed'
              and (p_state#>>'{cursor,through_date}')::date=(v_row.state#>>'{cursor,through_date}')::date
              and v_row.state->>'catchup_phase' is distinct from 'replayed'
              and not exists (select 1 from pg_catalog.jsonb_array_elements(v_row.state#>'{cursor,ids}') old_id
                              where not (p_state#>'{cursor,ids}' @> pg_catalog.jsonb_build_array(old_id))))
          or (p_state->>'catchup_phase'='advanced' and v_row.state->>'catchup_phase'='replayed'
              and (p_state#>>'{cursor,through_date}')::date=(v_row.state#>>'{cursor,through_date}')::date+1)))), false);
    if (v_row.state ? 'last_attempt_at' and (p_state->>'last_attempt_at')::timestamptz < (v_row.state->>'last_attempt_at')::timestamptz)
       or (v_row.state->>'last_success_at' is not null and (p_state->>'last_success_at')::timestamptz < (v_row.state->>'last_success_at')::timestamptz)
       or (p_state->>'status' <> 'success' and p_state->'last_success_at' is distinct from v_row.state->'last_success_at')
       or (p_state ? 'catchup_phase' and not v_catchup_valid)
       or (p_state->>'status' in ('partial','error') and p_state->'cursor' is distinct from v_row.state->'cursor'
           and not v_catchup_valid)
       or (p_state->>'status'='initialized' and v_row.state->'cursor' is not null
           and v_row.state->'cursor' <> 'null'::jsonb and p_state->'cursor' is distinct from v_row.state->'cursor')
       or (p_state->>'status' in ('error','initialized') and v_row.state ? 'feed' and p_state->'feed' is distinct from v_row.state->'feed')
       or (p_state->>'status'='success' and p_source='DART' and v_row.state#>>'{cursor,through_date}' is not null and
           ((p_state#>>'{cursor,through_date}')::date < (v_row.state#>>'{cursor,through_date}')::date
            or ((p_state#>>'{cursor,through_date}')::date=(v_row.state#>>'{cursor,through_date}')::date and exists
                (select 1 from pg_catalog.jsonb_array_elements(v_row.state#>'{cursor,ids}') old_id
                 where not (p_state#>'{cursor,ids}' @> pg_catalog.jsonb_build_array(old_id))))))
       or (p_state->>'status'='success' and p_source='SEC' and v_row.state#>>'{cursor,historical_gap}' is not null
           and p_state#>'{cursor,historical_gap}' is distinct from v_row.state#>'{cursor,historical_gap}')
       or (p_source <> 'news' and exists
           (select 1 from pg_catalog.jsonb_array_elements(coalesce(v_row.state#>'{feed,items}','[]'::jsonb)) old_group
            where not exists (select 1 from pg_catalog.jsonb_array_elements(p_state#>'{feed,items}') new_group
                              where new_group->>'ticker'=old_group->>'ticker'
                                and (pg_catalog.jsonb_array_length(old_group->'disclosures')=0
                                     or pg_catalog.jsonb_array_length(new_group->'disclosures')>0)))) then
        raise exception using errcode='22023', message='refresh-checkpoint-state-regression';
    end if;
    v_now := pg_catalog.clock_timestamp();
    v_day := (v_now at time zone 'Asia/Seoul')::date;
    if v_row.lease_until <= v_now or (p_source='DART' and v_row.request_day is distinct from v_day) then
        return pg_catalog.jsonb_build_object('status','lease-lost');
    end if;
    update public.member_map_refresh_checkpoint set state=p_state, revision=revision+1,
        feed_revision=feed_revision+(case when state->'feed' is distinct from p_state->'feed' then 1 else 0 end), updated_at=v_now,
        lease_owner=null, lease_until=null,
        quota_blocked_day=case when p_source='DART' and p_state->>'error'='dart-quota-exceeded' then v_day else quota_blocked_day end
        where source=p_source returning * into v_row;
    return pg_catalog.jsonb_build_object('status','saved','source',p_source,'generation',v_row.lease_generation,
        'revision',v_row.revision,'feed_revision',v_row.feed_revision,'updated_at',v_row.updated_at);
end;
$$;

revoke all on function public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb) from public, anon, authenticated, service_role;
grant execute on function public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb) to service_role;

do $$
declare v_role text;
begin
    if exists (select 1 from pg_catalog.pg_proc p,
               lateral pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
               where p.oid='public.member_map_refresh_catchup_valid(text,jsonb)'::regprocedure and a.grantee<>p.proowner)
       or exists (select 1 from pg_catalog.pg_proc p,
                  lateral pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
                  where p.oid='public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)'::regprocedure
                    and a.grantee not in (p.proowner,(select oid from pg_catalog.pg_roles where rolname='service_role'))) then
        raise exception 'refresh-catchup-unsafe-grants';
    end if;
    foreach v_role in array array['anon','authenticated','service_role'] loop
        if pg_catalog.has_function_privilege(v_role,'public.member_map_refresh_catchup_valid(text,jsonb)','EXECUTE')
           or pg_catalog.has_function_privilege(v_role,'public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)','EXECUTE')
              is distinct from (v_role='service_role') then
            raise exception 'refresh-catchup-unsafe-rpc-grants';
        end if;
    end loop;
end;
$$;
commit;
