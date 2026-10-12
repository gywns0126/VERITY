-- PRIVATE public-fact checkpoints only. No member/price/AI tables or roles change.
-- Apply once as migration owner; any existing name/unsafe role aborts the whole
-- transaction. After an SQL editor error, explicitly ROLLBACK before retrying.
-- Three fixed rows, three service-only RPCs, one non-callable CHECK helper.
-- Claim known revision suppresses state (JSON null); save is metadata-only.
-- feed_revision increments only when state.feed differs, never for health alone.
-- state UTF-8 JSON <= 4 MiB; <=10000 issuers, <=50000 disclosures, <=8/issuer;
-- news <=100/lane (three existing lanes); DART cursor <=1000 receipt IDs.
-- lease=300s (DART capped at KST midnight); runner heartbeat target=60s, not SLA.
-- DART new generation reserves exactly 10 requests, <=8000/KST day, no refund.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
select pg_catalog.pg_advisory_xact_lock(20261012, 1001);

do $$
begin
    if (select pg_catalog.count(*) from pg_catalog.pg_roles
        where rolname in ('anon','authenticated','service_role')) <> 3
       or exists (select 1 from pg_catalog.pg_roles where rolname in ('anon','authenticated')
                  and (rolsuper or rolbypassrls))
       or not exists (select 1 from pg_catalog.pg_roles
                      where rolname='service_role' and rolbypassrls and not rolsuper)
       or current_user in ('anon','authenticated','service_role') then
        raise exception 'refresh-checkpoint-unsafe-roles';
    end if;
    if pg_catalog.to_regclass('public.member_map_refresh_checkpoint') is not null
       or exists (select 1 from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                  where n.nspname='public' and p.proname in
                  ('member_map_refresh_state_valid','member_map_refresh_claim',
                   'member_map_refresh_renew','member_map_refresh_save')) then
        raise exception 'refresh-checkpoint-name-collision';
    end if;
end;
$$;

-- Closed keys mirror apply_result/merge_feed/news_result, NOT arbitrary JSON.
-- Invalid types/casts return false; never include payloads in database errors.
create function public.member_map_refresh_state_valid(p_source text, p_state jsonb)
returns boolean language plpgsql set search_path = '' as $$
declare
    v_key text;
    v_value jsonb;
    v_feed jsonb;
    v_group jsonb;
    v_row jsonb;
    v_cursor jsonb;
    v_attempt timestamptz;
    v_success timestamptz;
    v_stamp timestamptz;
    v_count integer := 0;
    v_total integer := 0;
    v_age numeric;
    v_id text;
    v_date date;
    v_status text;
begin
    if p_source is null or p_source not in ('SEC','DART','news') or p_state is null
       or pg_catalog.jsonb_typeof(p_state) <> 'object'
       or pg_catalog.octet_length(pg_catalog.convert_to(p_state::text,'UTF8')) > 4194304 then return false; end if;
    if p_state = '{}'::jsonb then return true; end if; -- migration bootstrap only; save rejects it
    if not (p_state ?& array['last_attempt_at','status','error','coverage','requests','health',
                            'screen_delivery_verified','analysis_delivery_verified'])
       or exists (select 1 from pg_catalog.jsonb_object_keys(p_state) k where k <> all
           (array['feed','cursor','last_attempt_at','last_success_at','status','error','coverage',
                  'requests','health','screen_delivery_verified','analysis_delivery_verified']))
       or p_state->'screen_delivery_verified' <> 'false'::jsonb
       or p_state->'analysis_delivery_verified' <> 'false'::jsonb then return false; end if;
    -- Known secret-shaped text is rejected in every leaf, including URLs. This
    -- does not replace the existing Vercel public projection/URL sanitizer.
    for v_value in select * from pg_catalog.jsonb_path_query(p_state, 'strict $.** ? (@.type() == "string")') loop
        if v_value #>> '{}' ~ '[[:cntrl:]<>]'
           or v_value #>> '{}' ~* '(sk-[a-z0-9_-]{8,}|eyJ[a-z0-9_-]{20,}|Bearer[[:space:]]|SUPABASE_SERVICE_ROLE_KEY|VERCEL_BLOB_TOKEN|DART_API_KEY|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})' then return false; end if;
    end loop;
    if pg_catalog.jsonb_typeof(p_state->'status') <> 'string'
       or p_state->>'status' not in ('success','partial','error','initialized') then return false; end if;
    v_status := p_state->>'status';
    if v_status='initialized' and p_source <> 'SEC' then return false; end if;
    -- Existing news collectors cannot prove completeness; never invent success.
    if p_source='news' and v_status not in ('partial','error') then return false; end if;
    if p_state->'error' <> 'null'::jsonb and
       (pg_catalog.jsonb_typeof(p_state->'error') <> 'string' or p_state->>'error' <> all(array[
        'collection-failed','collection_failure','per-feed-completeness-unavailable','dart-quota-exceeded',
        'invalid_timestamp','invalid_text','invalid_cik','invalid_catalog','invalid_sec_index',
        'endpoint_rejected','invalid_transport_limits','http_failure','body_limit','transport_timeout',
        'transport_failure','invalid_atom_encoding','xml_declaration_rejected','invalid_atom',
        'invalid_sec_identity','invalid_accession','invalid_sec_link','invalid_dart','dart_api_failure',
        'invalid_pagination','invalid_dart_row','invalid_receipt','invalid_reported_date','invalid_stock_code',
        'invalid_limits','invalid_cursor','invalid_configuration','invalid_json','incomplete_page',
        'record_limit','cursor_not_found','pagination_stalled','page_limit','cursor_outside_window',
        'pagination_changed','date_outside_window','incomplete_unique_records','invalid_page_size'])) then return false; end if;
    if (v_status in ('success','initialized') and p_state->'error' <> 'null'::jsonb)
       or (p_state->>'error'='dart-quota-exceeded' and (p_source <> 'DART' or v_status <> 'error')) then return false; end if;
    if pg_catalog.jsonb_typeof(p_state->'last_attempt_at') <> 'string'
       or p_state->>'last_attempt_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' then return false; end if;
    v_attempt := (p_state->>'last_attempt_at')::timestamptz;
    if not pg_catalog.isfinite(v_attempt) or v_attempt > pg_catalog.clock_timestamp() then return false; end if;
    if p_state ? 'last_success_at' and p_state->'last_success_at' <> 'null'::jsonb then
        if pg_catalog.jsonb_typeof(p_state->'last_success_at') <> 'string'
           or p_state->>'last_success_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' then return false; end if;
        v_success := (p_state->>'last_success_at')::timestamptz;
        if not pg_catalog.isfinite(v_success) or v_success > v_attempt then return false; end if;
    end if;
    if v_status='success' and v_success is distinct from v_attempt then return false; end if;
    if p_state->'requests' <> 'null'::jsonb and
       (pg_catalog.jsonb_typeof(p_state->'requests') <> 'number'
        or p_state->>'requests' !~ '^[0-9]{1,2}$' or (p_state->>'requests')::integer > 10) then return false; end if;
    if p_state->'requests'='null'::jsonb and p_source <> 'news' then return false; end if;

    if pg_catalog.jsonb_typeof(p_state->'coverage') <> 'object' then return false; end if;
    for v_key,v_value in select * from pg_catalog.jsonb_each(p_state->'coverage') loop
        if v_key in ('whole_market_coverage','raw_body_checked','all_feeds_verified') then
            if v_value <> 'false'::jsonb then return false; end if;
        elsif v_key in ('bounded','historical_gap') then
            if pg_catalog.jsonb_typeof(v_value) <> 'boolean' then return false; end if;
            if v_key='bounded' and v_value <> 'true'::jsonb then return false; end if;
        elsif v_key='scope' then
            if p_source <> 'SEC' or v_value <> '"shared_latest_8-K"'::jsonb then return false; end if;
        elsif v_key in ('pages_succeeded','listing_records','total_pages','total_records','accepted','rejected') then
            if pg_catalog.jsonb_typeof(v_value) <> 'number' or v_value::text !~ '^[0-9]{1,9}$' then return false; end if;
            if (v_key='pages_succeeded' and v_value::text::integer > 10)
               or (v_key='listing_records' and v_value::text::integer > 1000)
               or (v_key='accepted' and v_value::text::integer > 300) then return false; end if;
        else return false;
        end if;
    end loop;
    if pg_catalog.jsonb_typeof(p_state->'health') <> 'object'
       or not (p_state->'health' ?& array['status','age_seconds'])
       or exists (select 1 from pg_catalog.jsonb_object_keys(p_state->'health') k where k not in ('status','age_seconds')) then return false; end if;
    if v_success is null then
        if p_state->'health' <> '{"status":"unknown","age_seconds":null}'::jsonb then return false; end if;
    else
        v_age := extract(epoch from v_attempt-v_success);
        if pg_catalog.jsonb_typeof(p_state#>'{health,age_seconds}') <> 'number'
           or abs((p_state#>>'{health,age_seconds}')::numeric-v_age) > 0.000001
           or p_state#>>'{health,status}' is distinct from
               (case when v_age <= (case when p_source='news' then 300 else 120 end)
                     then 'on-time' else 'delayed' end) then return false; end if;
    end if;

    v_cursor := p_state->'cursor';
    if v_cursor is not null and v_cursor <> 'null'::jsonb then
        if pg_catalog.jsonb_typeof(v_cursor) <> 'object' or p_source='news'
           or v_cursor->>'source' is distinct from p_source
           or pg_catalog.jsonb_typeof(v_cursor->'checked_at') <> 'string'
           or v_cursor->>'checked_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
           or (v_cursor->>'checked_at')::timestamptz > v_attempt then return false; end if;
        if v_status in ('success','initialized') and (v_cursor->>'checked_at')::timestamptz <> v_attempt then return false; end if;
        if p_source='SEC' then
            if not (v_cursor ?& array['source','anchor_id','checked_at','historical_gap'])
               or exists (select 1 from pg_catalog.jsonb_object_keys(v_cursor) k where k not in ('source','anchor_id','checked_at','historical_gap'))
               or pg_catalog.jsonb_typeof(v_cursor->'historical_gap') <> 'boolean'
               or pg_catalog.jsonb_typeof(v_cursor->'anchor_id') <> 'string'
               or v_cursor->>'anchor_id' !~ '^SEC:[1-9][0-9]{0,9}:[0-9]{18}$' then return false; end if;
        else
            if not (v_cursor ?& array['source','through_date','ids','checked_at'])
               or exists (select 1 from pg_catalog.jsonb_object_keys(v_cursor) k where k not in ('source','through_date','ids','checked_at'))
               or pg_catalog.jsonb_typeof(v_cursor->'through_date') <> 'string'
               or v_cursor->>'through_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
               or pg_catalog.jsonb_typeof(v_cursor->'ids') <> 'array'
               or pg_catalog.jsonb_array_length(v_cursor->'ids') > 1000 then return false; end if;
            v_date := (v_cursor->>'through_date')::date;
            if v_date > (v_attempt at time zone 'Asia/Seoul')::date
               or exists (select 1 from pg_catalog.jsonb_array_elements(v_cursor->'ids') e
                          where pg_catalog.jsonb_typeof(e) <> 'string' or e#>>'{}' !~ '^DART:[0-9]{14}$')
               or (select pg_catalog.count(*) <> pg_catalog.count(distinct e) from pg_catalog.jsonb_array_elements(v_cursor->'ids') e) then return false; end if;
        end if;
    elsif v_status='success' and p_source <> 'news' then return false;
    end if;

    v_feed := p_state->'feed';
    if v_feed is null then return p_source='news' and v_status in ('partial','error'); end if;
    if pg_catalog.jsonb_typeof(v_feed) <> 'object' then return false; end if;
    if p_source='news' then
        for v_key,v_value in select * from pg_catalog.jsonb_each(v_feed) loop
            if v_key not in ('headlines','bloomberg_google_headlines','us_headlines')
               or pg_catalog.jsonb_typeof(v_value) <> 'array' or pg_catalog.jsonb_array_length(v_value)>100 then return false; end if;
            for v_row in select * from pg_catalog.jsonb_array_elements(v_value) loop
                if pg_catalog.jsonb_typeof(v_row) <> 'object'
                   or not (v_row ?& array['title','source','link','time'])
                   or exists (select 1 from pg_catalog.jsonb_object_keys(v_row) k where k not in ('title','source','link','time'))
                   or pg_catalog.jsonb_typeof(v_row->'title') <> 'string' or pg_catalog.length(v_row->>'title') not between 1 and 240
                   or pg_catalog.jsonb_typeof(v_row->'source') <> 'string' or pg_catalog.length(v_row->>'source') not between 1 and 100
                   or pg_catalog.jsonb_typeof(v_row->'link') <> 'string' or pg_catalog.length(v_row->>'link') > 2048
                   or v_row->>'link' !~ '^https://[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:443)?/'
                   or v_row->>'link' ~* '(\.local(host)?[:/]|\.internal[:/]|[?&](token|access_token|key|api_key|password|secret|signature|auth)=|[?&][^#]*%)'
                   or v_row->>'link' ~ '^https://[0-9.]+[:/]'
                   or v_row->>'link' ~ '[[:space:]#]'
                   or pg_catalog.jsonb_typeof(v_row->'time') <> 'string'
                   or v_row->>'time' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
                   or (v_row->>'time')::timestamptz > v_attempt then return false; end if;
            end loop;
        end loop;
        return true;
    end if;
    if not (v_feed ? 'items') or pg_catalog.jsonb_typeof(v_feed->'items') <> 'array'
       or pg_catalog.jsonb_array_length(v_feed->'items') > 10000
       or exists (select 1 from pg_catalog.jsonb_object_keys(v_feed) k where k not in ('items','_meta')) then return false; end if;
    for v_group in select * from pg_catalog.jsonb_array_elements(v_feed->'items') loop
        if pg_catalog.jsonb_typeof(v_group) <> 'object' or not (v_group ?& array['ticker','name','disclosures'])
           or exists (select 1 from pg_catalog.jsonb_object_keys(v_group) k where k not in ('ticker','name','disclosures','latest'))
           or pg_catalog.jsonb_typeof(v_group->'ticker') <> 'string'
           or (p_source='DART' and v_group->>'ticker' !~ '^[0-9]{6}$')
           or (p_source='SEC' and v_group->>'ticker' !~ '^[A-Z][A-Z0-9.-]{0,14}$')
           or pg_catalog.jsonb_typeof(v_group->'name') <> 'string' or pg_catalog.length(v_group->>'name') not between 1 and 160
           or pg_catalog.jsonb_typeof(v_group->'disclosures') <> 'array'
           or pg_catalog.jsonb_array_length(v_group->'disclosures') > 8 then return false; end if;
        if v_group ? 'latest' then
            if pg_catalog.jsonb_typeof(v_group->'latest') <> 'string'
               or v_group->>'latest' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then return false; end if;
            v_date := (v_group->>'latest')::date;
        end if;
        v_count := v_count+1;
        for v_row in select * from pg_catalog.jsonb_array_elements(v_group->'disclosures') loop
            v_total := v_total+1;
            if v_total > 50000 or pg_catalog.jsonb_typeof(v_row) <> 'object'
               or not (v_row ?& array['id','title','label','date','date_precision','source_date_field',
                                     'source_url','source','is_correction','filer','observed_at'])
               or exists (select 1 from pg_catalog.jsonb_object_keys(v_row) k where k not in
                  ('id','title','label','date','date_precision','source_date_field','source_url','source',
                   'is_correction','filer','observed_at','source_reported_at'))
               or v_row->>'source' is distinct from p_source
               or pg_catalog.jsonb_typeof(v_row->'is_correction') <> 'boolean'
               or pg_catalog.jsonb_typeof(v_row->'title') <> 'string' or pg_catalog.length(v_row->>'title') not between 1 and 300
               or pg_catalog.jsonb_typeof(v_row->'filer') <> 'string' or pg_catalog.length(v_row->>'filer') > 160
               or pg_catalog.jsonb_typeof(v_row->'id') <> 'string'
               or pg_catalog.jsonb_typeof(v_row->'label') <> 'string'
               or pg_catalog.jsonb_typeof(v_row->'date') <> 'string'
               or v_row->>'date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
               or pg_catalog.jsonb_typeof(v_row->'observed_at') <> 'string'
               or v_row->>'observed_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
               or (v_row->>'observed_at')::timestamptz > v_attempt then return false; end if;
            v_date := (v_row->>'date')::date;
            v_id := v_row->>'id';
            if p_source='DART' then
                if v_id !~ '^DART:[0-9]{14}$' or v_row->>'label' is distinct from 'DART'
                   or v_row->>'date_precision' is distinct from 'date' or v_row->>'source_date_field' is distinct from 'rcept_dt'
                   or v_row ? 'source_reported_at' or v_row->>'source_url' is distinct from
                      'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' || pg_catalog.substr(v_id,6) then return false; end if;
            else
                if v_id !~ '^SEC:[1-9][0-9]{0,9}:[0-9]{18}$' or v_row->>'label' not in ('8-K','8-K/A')
                   or v_row->>'date_precision' is distinct from 'timestamp' or v_row->>'source_date_field' is distinct from 'atom.updated'
                   or pg_catalog.jsonb_typeof(v_row->'source_reported_at') <> 'string'
                   or v_row->>'source_reported_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
                   or v_row->>'source_url' !~ '^https://www\.sec\.gov/Archives/edgar/data/[1-9][0-9]{0,9}/[0-9]{18}/[A-Za-z0-9][A-Za-z0-9._-]{0,199}$'
                   or v_row->>'source_url' not like 'https://www.sec.gov/Archives/edgar/data/' || pg_catalog.split_part(v_id,':',2) || '/' || pg_catalog.split_part(v_id,':',3) || '/%' then return false; end if;
                v_stamp := (v_row->>'source_reported_at')::timestamptz;
                if v_stamp > v_attempt or (pg_catalog.substr(v_row->>'source_reported_at',1,10))::date <> v_date then return false; end if;
            end if;
            if v_date > (v_attempt at time zone 'Asia/Seoul')::date then return false; end if;
        end loop;
        if (select pg_catalog.count(*) <> pg_catalog.count(distinct e->>'id') from pg_catalog.jsonb_array_elements(v_group->'disclosures') e) then return false; end if;
    end loop;
    if (select pg_catalog.count(*) <> pg_catalog.count(distinct e->>'ticker') from pg_catalog.jsonb_array_elements(v_feed->'items') e) then return false; end if;
    if v_feed ? '_meta' then
        v_value := v_feed->'_meta';
        if pg_catalog.jsonb_typeof(v_value) <> 'object' or not (v_value ?& array['generated_at','count','disclosure_count'])
           or exists (select 1 from pg_catalog.jsonb_object_keys(v_value) k where k not in ('generated_at','count','disclosure_count'))
           or v_value->'count' is distinct from pg_catalog.to_jsonb(v_count)
           or v_value->'disclosure_count' is distinct from pg_catalog.to_jsonb(v_total)
           or pg_catalog.jsonb_typeof(v_value->'generated_at') <> 'string'
           or v_value->>'generated_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
           or (v_value->>'generated_at')::timestamptz > v_attempt then return false; end if;
    end if;
    return true;
exception when others then return false;
end;
$$;
revoke all on function public.member_map_refresh_state_valid(text,jsonb) from public, anon, authenticated, service_role;

create table public.member_map_refresh_checkpoint (
    source text primary key check (source in ('SEC','DART','news')),
    state jsonb not null default '{}'::jsonb,
    revision bigint not null default 0 check (revision >= 0),
    feed_revision bigint not null default 0 check (feed_revision between 0 and revision),
    lease_owner uuid,
    lease_generation bigint not null default 0 check (lease_generation >= 0),
    lease_until timestamptz,
    updated_at timestamptz not null default pg_catalog.clock_timestamp(),
    request_day date,
    requests_reserved integer not null default 0 check (requests_reserved between 0 and 8000),
    quota_blocked_day date,
    check ((lease_owner is null) = (lease_until is null)),
    check (source='DART' or (request_day is null and requests_reserved=0 and quota_blocked_day is null)),
    check (request_day is not null or requests_reserved=0),
    check (public.member_map_refresh_state_valid(source,state))
);
insert into public.member_map_refresh_checkpoint(source) values ('SEC'),('DART'),('news');
alter table public.member_map_refresh_checkpoint enable row level security;
revoke all on public.member_map_refresh_checkpoint from public, anon, authenticated, service_role;
grant select on public.member_map_refresh_checkpoint to service_role;

create function public.member_map_refresh_claim(p_source text, p_owner uuid, p_request_budget integer default 0,
                                              p_known_revision bigint default -1)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_row public.member_map_refresh_checkpoint%rowtype;
    v_now timestamptz;
    v_day date;
    v_until timestamptz;
begin
    if p_source is null or p_source not in ('SEC','DART','news') or p_owner is null
       or p_owner='00000000-0000-0000-0000-000000000000'::uuid or p_request_budget is null
       or p_known_revision is null or p_known_revision < -1
       or (p_source='DART' and p_request_budget <> 10) or (p_source <> 'DART' and p_request_budget <> 0) then
        raise exception using errcode='22023', message='refresh-checkpoint-claim-input';
    end if;
    select * into strict v_row from public.member_map_refresh_checkpoint where source=p_source for update;
    v_now := pg_catalog.clock_timestamp();
    v_day := (v_now at time zone 'Asia/Seoul')::date;
    if p_source='DART' and v_row.quota_blocked_day=v_day then return pg_catalog.jsonb_build_object('status','quota-blocked'); end if;
    if v_row.lease_until > v_now then
        if v_row.lease_owner <> p_owner then return pg_catalog.jsonb_build_object('status','busy'); end if;
        return pg_catalog.jsonb_build_object('status','already-claimed','source',p_source,'generation',v_row.lease_generation,
            'revision',v_row.revision,'feed_revision',v_row.feed_revision,
            'state',case when v_row.revision=p_known_revision then null else v_row.state end,'lease_until',v_row.lease_until,
            'request_day',v_row.request_day,'requests_reserved',v_row.requests_reserved,'request_budget',p_request_budget);
    end if;
    -- Database cadence gate precedes reservation; two workers cannot burn a
    -- second batch immediately after the first worker saves/releases its lease.
    if v_row.state ? 'last_attempt_at' and v_now-(v_row.state->>'last_attempt_at')::timestamptz
       < pg_catalog.make_interval(secs => case when p_source='news' then 300 else 120 end) then
        return pg_catalog.jsonb_build_object('status','not-due','retry_after_seconds',
            pg_catalog.ceil(case when p_source='news' then 300 else 120 end
                            -extract(epoch from v_now-(v_row.state->>'last_attempt_at')::timestamptz))::integer);
    end if;
    if p_source='DART' and v_row.request_day=v_day and v_row.requests_reserved+10 > 8000 then
        return pg_catalog.jsonb_build_object('status','budget-exhausted');
    end if;
    v_until := v_now+interval '300 seconds';
    if p_source='DART' then v_until := least(v_until,(v_day+1)::timestamp at time zone 'Asia/Seoul'); end if;
    update public.member_map_refresh_checkpoint set lease_owner=p_owner, lease_generation=lease_generation+1, lease_until=v_until,
        request_day=case when p_source='DART' then v_day else null end,
        requests_reserved=case when p_source='DART' then case when request_day=v_day then requests_reserved else 0 end+10 else 0 end,
        quota_blocked_day=null
        where source=p_source returning * into v_row;
    return pg_catalog.jsonb_build_object('status','claimed','source',p_source,'generation',v_row.lease_generation,
        'revision',v_row.revision,'feed_revision',v_row.feed_revision,
        'state',case when v_row.revision=p_known_revision then null else v_row.state end,'lease_until',v_row.lease_until,
        'request_day',v_row.request_day,'requests_reserved',v_row.requests_reserved,'request_budget',p_request_budget);
end;
$$;

create function public.member_map_refresh_renew(p_source text, p_owner uuid, p_generation bigint)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_row public.member_map_refresh_checkpoint%rowtype;
    v_now timestamptz;
    v_day date;
    v_until timestamptz;
begin
    if p_source is null or p_source not in ('SEC','DART','news') or p_owner is null or p_generation is null or p_generation < 1 then
        raise exception using errcode='22023', message='refresh-checkpoint-lease-input';
    end if;
    select * into strict v_row from public.member_map_refresh_checkpoint where source=p_source for update;
    v_now := pg_catalog.clock_timestamp();
    v_day := (v_now at time zone 'Asia/Seoul')::date;
    if v_row.lease_owner is distinct from p_owner or v_row.lease_generation <> p_generation
       or v_row.lease_until is null or v_row.lease_until <= v_now
       or (p_source='DART' and (v_row.request_day is distinct from v_day or v_row.quota_blocked_day=v_day)) then
        return pg_catalog.jsonb_build_object('status','lease-lost');
    end if;
    v_until := v_now+interval '300 seconds';
    if p_source='DART' then v_until := least(v_until,(v_day+1)::timestamp at time zone 'Asia/Seoul'); end if;
    update public.member_map_refresh_checkpoint set lease_until=v_until where source=p_source;
    return pg_catalog.jsonb_build_object('status','renewed','source',p_source,'generation',p_generation,
        'revision',v_row.revision,'lease_until',v_until);
end;
$$;

-- Save releases the lease. An ambiguous response is resolved by SELECT of
-- revision/state; never replay a provider request or silently overwrite a row.
create function public.member_map_refresh_save(p_source text, p_owner uuid, p_generation bigint,
                                               p_expected_revision bigint, p_state jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_row public.member_map_refresh_checkpoint%rowtype;
    v_now timestamptz;
    v_day date;
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
    if p_state='{}'::jsonb or not public.member_map_refresh_state_valid(p_source,p_state) then
        raise exception using errcode='22023', message='refresh-checkpoint-invalid-state';
    end if;
    if (v_row.state ? 'last_attempt_at' and (p_state->>'last_attempt_at')::timestamptz < (v_row.state->>'last_attempt_at')::timestamptz)
       or (v_row.state->>'last_success_at' is not null and (p_state->>'last_success_at')::timestamptz < (v_row.state->>'last_success_at')::timestamptz)
       or (p_state->>'status' <> 'success' and p_state->'last_success_at' is distinct from v_row.state->'last_success_at')
       or (p_state->>'status' in ('partial','error') and p_state->'cursor' is distinct from v_row.state->'cursor')
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
    -- Recheck after bounded validation while holding the row lock. A large
    -- payload may not complete under an expired lease or cross KST midnight.
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

revoke all on function public.member_map_refresh_claim(text,uuid,integer,bigint) from public, anon, authenticated, service_role;
revoke all on function public.member_map_refresh_renew(text,uuid,bigint) from public, anon, authenticated, service_role;
revoke all on function public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb) from public, anon, authenticated, service_role;
grant execute on function public.member_map_refresh_claim(text,uuid,integer,bigint) to service_role;
grant execute on function public.member_map_refresh_renew(text,uuid,bigint) to service_role;
grant execute on function public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb) to service_role;

-- Effective privileges include inherited role memberships/default grants.
-- Abort rather than modifying a pre-existing role, schema or global defaults.
do $$
declare v_role text; v_priv text; v_fn regprocedure;
begin
    if exists (select 1 from pg_catalog.pg_class c,
               lateral pg_catalog.aclexplode(coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
               where c.oid='public.member_map_refresh_checkpoint'::regclass
                 and a.grantee not in (c.relowner,(select oid from pg_catalog.pg_roles where rolname='service_role')))
       or exists (select 1 from pg_catalog.pg_proc p,
                  lateral pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
                  where p.oid='public.member_map_refresh_state_valid(text,jsonb)'::regprocedure and a.grantee<>p.proowner)
       or exists (select 1 from pg_catalog.pg_proc p,
                  lateral pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
                  where p.oid in ('public.member_map_refresh_claim(text,uuid,integer,bigint)'::regprocedure,
                                 'public.member_map_refresh_renew(text,uuid,bigint)'::regprocedure,
                                 'public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)'::regprocedure)
                    and a.grantee not in (p.proowner,(select oid from pg_catalog.pg_roles where rolname='service_role'))) then
        raise exception 'refresh-checkpoint-unsafe-default-grants';
    end if;
    foreach v_role in array array['anon','authenticated','service_role'] loop
        foreach v_priv in array array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] loop
            if pg_catalog.has_table_privilege(v_role,'public.member_map_refresh_checkpoint',v_priv)
               is distinct from (v_role='service_role' and v_priv='SELECT') then
                raise exception 'refresh-checkpoint-unsafe-grants';
            end if;
        end loop;
        if pg_catalog.has_function_privilege(v_role,'public.member_map_refresh_state_valid(text,jsonb)','EXECUTE') then
            raise exception 'refresh-checkpoint-validator-exposed';
        end if;
        foreach v_fn in array array['public.member_map_refresh_claim(text,uuid,integer,bigint)'::regprocedure,
                                   'public.member_map_refresh_renew(text,uuid,bigint)'::regprocedure,
                                   'public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)'::regprocedure] loop
            if pg_catalog.has_function_privilege(v_role,v_fn,'EXECUTE') is distinct from (v_role='service_role') then
                raise exception 'refresh-checkpoint-unsafe-rpc-grants';
            end if;
        end loop;
    end loop;
end;
$$;
commit;
