-- DART-only continuation. Deploy v1/v2 readers and worker before applying.
-- Migration is the activation gate; no provider calls are made by this SQL.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';
select pg_catalog.pg_advisory_xact_lock(20261012,1001);
do $$
begin
 if (select md5(prosrc) from pg_proc where oid='public.member_map_refresh_state_valid(text,jsonb)'::regprocedure) <> 'adcb68fa2b0dd146469fb60c0eb277a1'
 or (select md5(prosrc) from pg_proc where oid='public.member_map_refresh_catchup_valid(text,jsonb)'::regprocedure) <> '1f7dedc20319e5c164b2619749cd60c7'
 or (select md5(prosrc) from pg_proc where oid='public.member_map_refresh_claim(text,uuid,integer,bigint)'::regprocedure) <> '53a9798d5af538985e0805839d4e679d'
 or (select md5(prosrc) from pg_proc where oid='public.member_map_refresh_renew(text,uuid,bigint)'::regprocedure) <> '882d350db34659f472941b64872a7b50'
 or (select md5(prosrc) from pg_proc where oid='public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb)'::regprocedure) <> 'b30f0fcd8a7cd4ef87361fadd392e113' then
  raise exception 'refresh-continuation-function-drift';
 end if;
end $$;

create function public.member_map_dart_ids(p_ids jsonb) returns text
language sql immutable set search_path='' as $$
 select pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(coalesce(
  (select pg_catalog.string_agg(v#>>'{}',E'\n' order by (v#>>'{}') collate "C")
   from pg_catalog.jsonb_array_elements(p_ids) v),''),'UTF8')),'hex')
$$;
-- PostgreSQL accepts 24:00:00 and leap-second spelling; Python readers do not.
create function public.member_map_dart_stamp_valid(p_value jsonb) returns boolean
language plpgsql immutable set search_path='' as $$
begin
 if pg_catalog.jsonb_typeof(p_value) is distinct from 'string' or p_value#>>'{}' !~
  '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$'
 then return false; end if;
 return pg_catalog.isfinite((p_value#>>'{}')::timestamptz);
exception when others then return false;
end $$;
create function public.member_map_dart_cursor(p_c jsonb) returns jsonb
language sql immutable set search_path='' as $$
 select pg_catalog.jsonb_build_object('source','DART','version',2,'through_date',p_c->'date',
  'checked_at',p_c->'checked_at','id_count',pg_catalog.jsonb_array_length(p_c->'ids'),
  'ids_sha256',public.member_map_dart_ids(p_c->'ids'))
$$;
create function public.member_map_dart_map_valid(p_map jsonb) returns boolean
language sql immutable set search_path='' as $$
 select coalesce(pg_catalog.jsonb_typeof(p_map)='object' and not exists
  (select 1 from pg_catalog.jsonb_each(case when pg_catalog.jsonb_typeof(p_map)='object' then p_map else '{}' end) e
   where e.key !~ '^DART:[0-9]{14}$' or pg_catalog.jsonb_typeof(e.value)<>'string' or e.value#>>'{}' !~ '^[0-9a-f]{64}$'),false)
$$;
create function public.member_map_dart_checkpoint_valid(p_cp jsonb) returns boolean
language plpgsql set search_path='' as $$
declare c jsonb; p jsonb; ids jsonb; m text; total integer; n integer; d date; stamp timestamptz;
begin
 if p_cp is null or p_cp='null'::jsonb then return true; end if;
 if pg_catalog.jsonb_typeof(p_cp)<>'object' or not (p_cp ?& array['version','committed','pending'])
 or exists(select 1 from pg_catalog.jsonb_object_keys(p_cp) k where k not in ('version','committed','pending'))
 or pg_catalog.jsonb_typeof(p_cp->'version')<>'number' or p_cp->>'version' is distinct from '2'
 or pg_catalog.octet_length(pg_catalog.convert_to(p_cp::text,'UTF8'))>4194304 then return false; end if;
 c:=p_cp->'committed'; p:=p_cp->'pending';
 if c<>'null'::jsonb then
  if pg_catalog.jsonb_typeof(c)<>'object' or not(c ?& array['date','ids','checked_at'])
  or exists(select 1 from pg_catalog.jsonb_object_keys(c) k where k not in ('date','ids','checked_at'))
  or pg_catalog.jsonb_typeof(c->'date')<>'string' or c->>'date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  or not public.member_map_dart_stamp_valid(c->'checked_at')
  then return false; end if;
  d:=(c->>'date')::date; stamp:=(c->>'checked_at')::timestamptz;
  if not pg_catalog.isfinite(d) or not pg_catalog.isfinite(stamp) then return false; end if;
 end if;
 -- Every retained receipt set is exact, unique and sorted. No truncation.
 for ids in select v from (values(c->'ids'),(p->'observed')) t(v) where v is not null loop
  if pg_catalog.jsonb_typeof(ids)<>'array' or exists(select 1 from pg_catalog.jsonb_array_elements(ids) e
    where pg_catalog.jsonb_typeof(e)<>'string' or e#>>'{}' !~ '^DART:[0-9]{14}$') then return false; end if;
  if ids is distinct from (select coalesce(pg_catalog.jsonb_agg(v order by v collate "C"),'[]')
    from (select distinct e#>>'{}' v from pg_catalog.jsonb_array_elements(ids) e) q) then return false; end if;
 end loop;
 if p<>'null'::jsonb then
  if pg_catalog.jsonb_typeof(p)<>'object' or not(p ?& array['date','catalog','started_at','phase','next_page','total','rows','baseline','first','last','observed'])
  or exists(select 1 from pg_catalog.jsonb_object_keys(p) k where k not in ('date','catalog','started_at','phase','next_page','total','rows','baseline','first','last','observed'))
  or pg_catalog.jsonb_typeof(p->'date')<>'string' or p->>'date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  or pg_catalog.jsonb_typeof(p->'catalog')<>'string' or p->>'catalog' !~ '^[0-9a-f]{64}$'
  or not public.member_map_dart_stamp_valid(p->'started_at')
  or pg_catalog.jsonb_typeof(p->'phase')<>'string' or p->>'phase' not in ('scan','verify') or pg_catalog.jsonb_typeof(p->'next_page')<>'number'
  or p->>'next_page' !~ '^[0-9]+$' then return false; end if;
  d:=(p->>'date')::date; stamp:=(p->>'started_at')::timestamptz; n:=(p->>'next_page')::integer;
  if not pg_catalog.isfinite(d) or not pg_catalog.isfinite(stamp) or n<1 or n>10000000 then return false; end if;
  foreach m in array array['rows','baseline','first','last'] loop
   if not public.member_map_dart_map_valid(p->m) or exists(select 1 from pg_catalog.jsonb_object_keys(p->m) k
       where pg_catalog.substr(k,6,8)<>pg_catalog.replace(p->>'date','-','')) then return false; end if;
  end loop;
  if p->'total'='null'::jsonb then
   if n<>1 or p->>'phase'<>'scan' or p->'rows'<>'{}'::jsonb or p->'baseline'<>'{}'::jsonb
    or p->'first'<>'{}'::jsonb or p->'last'<>'{}'::jsonb then return false; end if;
  else
   if pg_catalog.jsonb_typeof(p->'total')<>'number' or p->>'total' !~ '^[0-9]{1,9}$' then return false; end if;
   total:=(p->>'total')::integer;
   if (select count(*) from pg_catalog.jsonb_object_keys(p->'rows'))<>least((n-1)*100,total)
    or n>greatest(1,(total+99)/100)
    or (p->>'phase'='scan' and p->'baseline'<>'{}'::jsonb)
    or (p->>'phase'='verify' and (select count(*) from pg_catalog.jsonb_object_keys(p->'baseline'))<>total) then return false; end if;
  end if;
  if n=1 then
   if p->'first'<>'{}'::jsonb or p->'last'<>'{}'::jsonb then return false; end if;
  elsif (select count(*) from pg_catalog.jsonb_object_keys(p->'first'))<>100
    or (select count(*) from pg_catalog.jsonb_object_keys(p->'last'))<>100
    or not((p->'rows') @> (p->'first')) or not((p->'rows') @> (p->'last')) then return false;
  end if;
  if exists(select 1 from pg_catalog.jsonb_object_keys((p->'rows')||(p->'baseline')) k where not (p->'observed' ? k)) then return false; end if;
  if c<>'null'::jsonb and (d<(c->>'date')::date or d>(c->>'date')::date+1) then return false; end if;
 end if;
 return true;
exception when others then return false;
end $$;

create function public.member_map_dart_pending(p_day text,p_catalog text,p_now text,p_ids jsonb default '[]') returns jsonb
language sql immutable set search_path='' as $$
 select pg_catalog.jsonb_build_object('date',p_day,'catalog',p_catalog,'started_at',p_now,
  'phase','scan','next_page',1,'total',null,'rows','{}'::jsonb,'baseline','{}'::jsonb,
  'first','{}'::jsonb,'last','{}'::jsonb,'observed',p_ids)
$$;

create function public.member_map_dart_replay(p_cp jsonb,p_cursor jsonb,p_now text,p_catalog text,p_pages jsonb) returns jsonb
language plpgsql set search_path='' as $$
declare cp jsonb:=p_cp; c jsonb; p jsonb; proof jsonb; r jsonb; observed jsonb; ids jsonb;
 d date; today date:=(p_now::timestamptz at time zone 'Asia/Seoul')::date;
 guards integer[]:='{}'; idx integer:=0; page integer; total integer; expected integer;
 changed boolean; nproof integer;
begin
 if not public.member_map_dart_checkpoint_valid(cp) or p_catalog is null or p_catalog !~ '^[0-9a-f]{64}$'
  or pg_catalog.jsonb_typeof(p_pages)<>'array' or pg_catalog.jsonb_array_length(p_pages)>10 then
  raise exception 'refresh-dart-evidence-invalid';
 end if;
 nproof:=pg_catalog.jsonb_array_length(p_pages);
 if cp is null or cp='null'::jsonb then
  if p_cursor ? 'version' then raise exception 'refresh-dart-evidence-invalid'; end if;
  c:=null;
  if p_cursor is not null and p_cursor<>'null'::jsonb then
   select coalesce(pg_catalog.jsonb_agg(v order by v collate "C"),'[]') into ids
    from (select distinct e#>>'{}' v from pg_catalog.jsonb_array_elements(p_cursor->'ids') e) q;
   c:=pg_catalog.jsonb_build_object('date',p_cursor->'through_date','ids',ids,'checked_at',p_cursor->'checked_at');
  end if;
  cp:=pg_catalog.jsonb_build_object('version',2,'committed',c,'pending',null);
 end if;
 c:=cp->'committed'; p:=cp->'pending';
 if c<>'null'::jsonb then
  if (c->>'date')::date>today or (c->>'checked_at')::timestamptz>p_now::timestamptz
    or (p_cursor->'version'='2'::jsonb and p_cursor<>public.member_map_dart_cursor(c)) then
   raise exception 'refresh-dart-evidence-invalid';
  end if;
 end if;
 if p='null'::jsonb then
  d:=case when c='null'::jsonb then today-1 else (c->>'date')::date end;
  if c<>'null'::jsonb and d<today and ((c->>'checked_at')::timestamptz at time zone 'Asia/Seoul')::date>d then d:=d+1; end if;
  p:=public.member_map_dart_pending(d::text,p_catalog,p_now);
 elsif p->>'catalog'<>p_catalog then
  p:=public.member_map_dart_pending(p->>'date',p_catalog,p_now,p->'observed');
 end if;
 if (p->>'date')::date>today or (p->>'started_at')::timestamptz>p_now::timestamptz then raise exception 'refresh-dart-evidence-invalid'; end if;
 if (p->>'next_page')::integer>1 then
  guards:=array[1];
  if (p->>'next_page')::integer>2 then guards:=guards||((p->>'next_page')::integer-1); end if;
 end if;
 for proof in select * from pg_catalog.jsonb_array_elements(p_pages) loop
  idx:=idx+1;
  if pg_catalog.jsonb_typeof(proof)<>'object' or not(proof ?& array['page_no','total_count','rows'])
   or exists(select 1 from pg_catalog.jsonb_object_keys(proof) k where k not in ('page_no','total_count','rows'))
   or pg_catalog.jsonb_typeof(proof->'page_no')<>'number' or proof->>'page_no' !~ '^[0-9]{1,9}$'
   or pg_catalog.jsonb_typeof(proof->'total_count')<>'number' or proof->>'total_count' !~ '^[0-9]{1,9}$'
   or pg_catalog.jsonb_typeof(proof->'rows')<>'array' or pg_catalog.jsonb_array_length(proof->'rows')>100 then
   raise exception 'refresh-dart-evidence-invalid';
  end if;
  if exists(select 1 from pg_catalog.jsonb_array_elements(proof->'rows') e where pg_catalog.jsonb_typeof(e)<>'array'
    or pg_catalog.jsonb_array_length(e)<>2 or pg_catalog.jsonb_typeof(e->0)<>'string'
    or pg_catalog.jsonb_typeof(e->1)<>'string') then raise exception 'refresh-dart-evidence-invalid'; end if;
  select coalesce(pg_catalog.jsonb_object_agg(e->>0,e->1),'{}') into r from pg_catalog.jsonb_array_elements(proof->'rows') e;
  page:=(proof->>'page_no')::integer; total:=(proof->>'total_count')::integer;
  if not public.member_map_dart_map_valid(r) or exists(select 1 from pg_catalog.jsonb_object_keys(r) k
    where pg_catalog.substr(k,6,8)<>pg_catalog.replace(p->>'date','-',''))
   or (select count(*) from pg_catalog.jsonb_object_keys(r))<>pg_catalog.jsonb_array_length(proof->'rows')
   or page<1 or page>greatest(1,(total+99)/100) or pg_catalog.jsonb_array_length(proof->'rows')<>least(100,greatest(0,total-(page-1)*100)) then
   raise exception 'refresh-dart-evidence-invalid';
  end if;
  expected:=case when idx<=cardinality(guards) then guards[idx] else (p->>'next_page')::integer end;
  if page<>expected then raise exception 'refresh-dart-evidence-invalid'; end if;
  select coalesce(pg_catalog.jsonb_agg(v order by v collate "C"),'[]') into observed from
   (select e#>>'{}' v from pg_catalog.jsonb_array_elements(p->'observed') e union select k from pg_catalog.jsonb_object_keys(r) k) q;
  p:=p||pg_catalog.jsonb_build_object('observed',observed);
  changed:=p->'total'<>'null'::jsonb and (p->>'total')::integer<>total;
  if idx<=cardinality(guards) then
   changed:=changed or r<>p->(case when page=1 then 'first' else 'last' end);
  elsif exists(select 1 from pg_catalog.jsonb_object_keys(r) k where p->'rows' ? k) then changed:=true;
  end if;
  if changed then
   if idx<>nproof then raise exception 'refresh-dart-evidence-invalid'; end if;
   cp:=cp||pg_catalog.jsonb_build_object('pending',public.member_map_dart_pending(p->>'date',p_catalog,p_now,observed));
   return pg_catalog.jsonb_build_object('checkpoint',cp,'sealed',false,'error','pagination_changed');
  end if;
  if idx<=cardinality(guards) then continue; end if;
  p:=p||pg_catalog.jsonb_build_object('total',total,'rows',(p->'rows')||r,'last',r,'next_page',page+1);
  if page=1 then p:=p||pg_catalog.jsonb_build_object('first',r); end if;
  if page>=greatest(1,(total+99)/100) then
   if idx<>nproof or (select count(*) from pg_catalog.jsonb_object_keys(p->'rows'))<>total then raise exception 'refresh-dart-evidence-invalid'; end if;
   if p->>'phase'='scan' then
    p:=p||pg_catalog.jsonb_build_object('phase','verify','next_page',1,'baseline',p->'rows','rows','{}'::jsonb,'first','{}'::jsonb,'last','{}'::jsonb);
    return pg_catalog.jsonb_build_object('checkpoint',cp||pg_catalog.jsonb_build_object('pending',p),'sealed',false,'error',null);
   end if;
   if p->'baseline'<>p->'rows' then
    cp:=cp||pg_catalog.jsonb_build_object('pending',public.member_map_dart_pending(p->>'date',p_catalog,p_now,observed));
    return pg_catalog.jsonb_build_object('checkpoint',cp,'sealed',false,'error','pagination_changed');
   end if;
   select coalesce(pg_catalog.jsonb_agg(v order by v collate "C"),'[]') into ids from
    (select e#>>'{}' v from pg_catalog.jsonb_array_elements(observed) e union
     select e#>>'{}' from pg_catalog.jsonb_array_elements(case when c->>'date'=p->>'date' then c->'ids' else '[]' end) e) q;
   c:=pg_catalog.jsonb_build_object('date',p->'date','ids',ids,'checked_at',p_now);
   return pg_catalog.jsonb_build_object('checkpoint',pg_catalog.jsonb_build_object('version',2,'committed',c,'pending',null),'sealed',true,'error',null);
  end if;
 end loop;
 return pg_catalog.jsonb_build_object('checkpoint',cp||pg_catalog.jsonb_build_object('pending',p),'sealed',false,'error',null);
end $$;

create function public.member_map_refresh_v2_valid(p_source text,p_state jsonb,p_cp jsonb) returns boolean
language plpgsql security definer set search_path='' as $$
declare s jsonb:=p_state; cur jsonb; c jsonb; p jsonb; stamp jsonb; attempt timestamptz; today date;
begin
 if p_source<>'DART' then
  return p_cp is null and coalesce(public.member_map_refresh_state_valid(p_source,s),false);
 end if;
 if not public.member_map_dart_checkpoint_valid(p_cp) or
  pg_catalog.octet_length(pg_catalog.convert_to(s::text,'UTF8'))+
  coalesce(pg_catalog.octet_length(pg_catalog.convert_to(p_cp::text,'UTF8')),0)>4194304 then return false; end if;
 cur:=s->'cursor'; c:=p_cp->'committed'; p:=p_cp->'pending';
 if cur ? 'version' then
  if pg_catalog.jsonb_typeof(cur->'version')<>'number' or cur->>'version' is distinct from '2'
   or pg_catalog.jsonb_typeof(cur->'id_count')<>'number' or cur->>'id_count' !~ '^[0-9]{1,9}$'
   or c is null or c='null'::jsonb
   or cur is distinct from public.member_map_dart_cursor(c) or s ? 'catchup_phase' then return false; end if;
  s:=pg_catalog.jsonb_set(s,'{cursor}',(cur-'version'-'id_count'-'ids_sha256')||'{"ids":[]}'::jsonb);
 end if;
 if not (coalesce(public.member_map_refresh_state_valid('DART',s),false)
    or coalesce(public.member_map_refresh_catchup_valid('DART',s),false)) then return false; end if;
 if p_cp is null then return not coalesce(cur ? 'version',false); end if;
 if p_state='{}'::jsonb then return false; end if;
 -- Close every timestamp carried by a v2 public state, including feed facts.
 for stamp in select v from (values(p_state->'last_attempt_at'),(p_state->'last_success_at'),
    (cur->'checked_at'),(p_state#>'{feed,_meta,generated_at}')) t(v)
    where v is not null and v<>'null'::jsonb
   union all select disclosure->'observed_at'
    from pg_catalog.jsonb_array_elements(p_state#>'{feed,items}') g,
      lateral pg_catalog.jsonb_array_elements(g->'disclosures') disclosure loop
  if not public.member_map_dart_stamp_valid(stamp) then return false; end if;
 end loop;
 if (cur is not null and cur<>'null'::jsonb) is distinct from (c is not null and c<>'null'::jsonb) then return false; end if;
 attempt:=(p_state->>'last_attempt_at')::timestamptz; today:=(attempt at time zone 'Asia/Seoul')::date;
 if c<>'null'::jsonb then
  if (c->>'date')::date>today or (c->>'checked_at')::timestamptz>attempt then return false; end if;
  if not coalesce(cur ? 'version',false) and (c->>'date' is distinct from cur->>'through_date'
    or c->>'checked_at' is distinct from cur->>'checked_at'
    or c->'ids' is distinct from (select coalesce(pg_catalog.jsonb_agg(v order by v collate "C"),'[]')
       from (select distinct e#>>'{}' v from pg_catalog.jsonb_array_elements(cur->'ids') e) q)) then return false; end if;
 end if;
 if p<>'null'::jsonb and ((p->>'date')::date>today or (p->>'started_at')::timestamptz>attempt) then return false; end if;
 if cur ? 'version' and p_state->>'status'='success' and (cur->>'through_date')::date<>today then return false; end if;
 return true;
exception when others then return false;
end $$;

alter table public.member_map_refresh_checkpoint add column dart_checkpoint jsonb;
alter table public.member_map_refresh_checkpoint drop constraint member_map_refresh_checkpoint_state_valid_check;
alter table public.member_map_refresh_checkpoint add constraint member_map_refresh_checkpoint_state_valid_check
 check(coalesce(public.member_map_refresh_v2_valid(source,state,dart_checkpoint),false));

-- Keep the old implementations private for SEC/news and the unchanged reservation
-- logic. Both public v1 DART entry points are fenced as soon as v2 is activated.
alter function public.member_map_refresh_claim(text,uuid,integer,bigint) rename to member_map_refresh_claim_v1_private;
alter function public.member_map_refresh_save(text,uuid,bigint,bigint,jsonb) rename to member_map_refresh_save_v1_private;
revoke all on function public.member_map_refresh_claim_v1_private(text,uuid,integer,bigint) from public,anon,authenticated,service_role;
revoke all on function public.member_map_refresh_save_v1_private(text,uuid,bigint,bigint,jsonb) from public,anon,authenticated,service_role;

create function public.member_map_refresh_claim(p_source text,p_owner uuid,p_request_budget integer default 0,p_known_revision bigint default -1)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
 if p_source='DART' then raise exception using errcode='22023',message='refresh-writer-version-required'; end if;
 return public.member_map_refresh_claim_v1_private(p_source,p_owner,p_request_budget,p_known_revision);
end $$;
create function public.member_map_refresh_save(p_source text,p_owner uuid,p_generation bigint,p_expected_revision bigint,p_state jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
 if p_source='DART' then raise exception using errcode='22023',message='refresh-writer-version-required'; end if;
 return public.member_map_refresh_save_v1_private(p_source,p_owner,p_generation,p_expected_revision,p_state);
end $$;
create function public.member_map_refresh_claim_v2(p_source text,p_owner uuid,p_request_budget integer default 10,p_known_revision bigint default -1)
returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb; cp jsonb;
begin
 if p_source is distinct from 'DART' then raise exception using errcode='22023',message='refresh-source-rejected'; end if;
 result:=public.member_map_refresh_claim_v1_private(p_source,p_owner,p_request_budget,p_known_revision);
 if result->>'status' in ('claimed','already-claimed') then
  select dart_checkpoint into cp from public.member_map_refresh_checkpoint where source='DART';
  result:=result||pg_catalog.jsonb_build_object('dart_checkpoint',cp);
 end if;
 return result;
end $$;

create function public.member_map_refresh_save_v2(p_source text,p_owner uuid,p_generation bigint,p_expected_revision bigint,
 p_state jsonb,p_pages jsonb,p_catalog text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare r public.member_map_refresh_checkpoint%rowtype; now_at timestamptz; day date;
 transition jsonb; cp jsonb; sealed boolean:=false; discard boolean; n integer; listed integer; cur jsonb;
begin
 if p_source is distinct from 'DART' or p_owner is null or p_generation is null or p_generation<1
  or p_expected_revision is null or p_expected_revision<0 or p_state is null or p_state='{}'::jsonb
  or p_catalog is null or p_catalog !~ '^[0-9a-f]{64}$' or p_pages is null or pg_catalog.jsonb_typeof(p_pages)<>'array'
  or pg_catalog.jsonb_array_length(p_pages)>10 or not public.member_map_dart_stamp_valid(p_state->'last_attempt_at') then
  raise exception using errcode='22023',message='refresh-checkpoint-save-input';
 end if;
 select * into strict r from public.member_map_refresh_checkpoint where source='DART' for update;
 now_at:=pg_catalog.clock_timestamp(); day:=(now_at at time zone 'Asia/Seoul')::date;
 if r.lease_owner is distinct from p_owner or r.lease_generation<>p_generation or r.lease_until is null or r.lease_until<=now_at
  or r.request_day is distinct from day or r.quota_blocked_day=day then return '{"status":"lease-lost"}'::jsonb; end if;
 if r.revision<>p_expected_revision then return '{"status":"revision-conflict"}'::jsonb; end if;
 n:=pg_catalog.jsonb_array_length(p_pages);
 discard:=coalesce(p_state->>'error' in ('dart-quota-exceeded','record_limit') and n=0,false);
 if discard then cp:=r.dart_checkpoint;
 else
  transition:=public.member_map_dart_replay(r.dart_checkpoint,r.state->'cursor',p_state->>'last_attempt_at',p_catalog,p_pages);
  cp:=transition->'checkpoint'; sealed:=(transition->>'sealed')::boolean;
 end if;
 if not coalesce(public.member_map_refresh_v2_valid('DART',p_state,cp),false) then
  raise exception using errcode='22023',message='refresh-checkpoint-invalid-state';
 end if;
 if p_state ? 'catchup_phase' or p_state->'requests'='null'::jsonb or (p_state->>'requests')::integer<n
  or (not discard and (p_state->>'requests')::integer>n+1)
  or (p_state->>'error' is null and (p_state->>'requests')::integer<>n) then
  raise exception using errcode='22023',message='refresh-dart-evidence-invalid';
 end if;
 if not discard then
  select coalesce(sum(pg_catalog.jsonb_array_length(e->'rows')),0)::integer into listed from pg_catalog.jsonb_array_elements(p_pages) e;
  if p_state#>'{coverage,pages_succeeded}' is distinct from pg_catalog.to_jsonb(n)
   or p_state#>'{coverage,listing_records}' is distinct from pg_catalog.to_jsonb(listed)
   or (transition->>'error' is not null and p_state->'error' is distinct from transition->'error')
   or (n>0 and (p_state#>'{coverage,total_records}' is distinct from (p_pages->(n-1)->'total_count')
       or p_state#>'{coverage,total_pages}' is distinct from pg_catalog.to_jsonb(((p_pages->(n-1)->>'total_count')::integer+99)/100))) then
   raise exception using errcode='22023',message='refresh-dart-evidence-invalid';
  end if;
 end if;
 if sealed then
  cur:=public.member_map_dart_cursor(cp->'committed');
  if p_state->'cursor' is distinct from cur or p_state->>'error' is not null
   or p_state->>'status' is distinct from (case when (cur->>'through_date')::date=day then 'success' else 'partial' end) then
   raise exception using errcode='22023',message='refresh-checkpoint-state-regression';
  end if;
 else
  if coalesce(p_state->'cursor','null'::jsonb) is distinct from coalesce(r.state->'cursor','null'::jsonb)
   or p_state->>'status' not in ('partial','error') then
   raise exception using errcode='22023',message='refresh-checkpoint-state-regression';
  end if;
 end if;
 if (r.state ? 'last_attempt_at' and (p_state->>'last_attempt_at')::timestamptz<(r.state->>'last_attempt_at')::timestamptz)
  or (p_state->>'status'<>'success' and coalesce(p_state->'last_success_at','null'::jsonb)
       is distinct from coalesce(r.state->'last_success_at','null'::jsonb))
  or (p_state->>'status'='error' and r.state ? 'feed' and p_state->'feed' is distinct from r.state->'feed')
  or exists(select 1 from pg_catalog.jsonb_array_elements(coalesce(r.state#>'{feed,items}','[]')) old_group
    where not exists(select 1 from pg_catalog.jsonb_array_elements(p_state#>'{feed,items}') new_group
      where new_group->>'ticker'=old_group->>'ticker' and (pg_catalog.jsonb_array_length(old_group->'disclosures')=0
        or pg_catalog.jsonb_array_length(new_group->'disclosures')>0))) then
  raise exception using errcode='22023',message='refresh-checkpoint-state-regression';
 end if;
 now_at:=pg_catalog.clock_timestamp();day:=(now_at at time zone 'Asia/Seoul')::date;
 if r.lease_until<=now_at or r.request_day is distinct from day then return '{"status":"lease-lost"}'::jsonb; end if;
 update public.member_map_refresh_checkpoint set state=p_state,dart_checkpoint=cp,revision=revision+1,
  feed_revision=feed_revision+(case when state->'feed' is distinct from p_state->'feed' then 1 else 0 end),updated_at=now_at,
  lease_owner=null,lease_until=null,quota_blocked_day=case when p_state->>'error'='dart-quota-exceeded' then day else quota_blocked_day end
  where source='DART' returning * into r;
 return pg_catalog.jsonb_build_object('status','saved','source','DART','generation',r.lease_generation,'revision',r.revision,
   'feed_revision',r.feed_revision,'updated_at',r.updated_at);
end $$;

-- No member-facing policies, roles or table grants are added. Internal helpers
-- and preserved v1 implementations are not callable even by service_role.
do $$
declare f regprocedure; name text; role_name text; allowed boolean;
begin
 for f,name in select p.oid::regprocedure,p.proname from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and (p.proname like 'member_map_dart_%' or p.proname in
   ('member_map_refresh_v2_valid','member_map_refresh_claim','member_map_refresh_save','member_map_refresh_claim_v2','member_map_refresh_save_v2',
    'member_map_refresh_claim_v1_private','member_map_refresh_save_v1_private')) loop
  execute pg_catalog.format('revoke all on function %s from public,anon,authenticated,service_role',f);
  allowed:=name in ('member_map_refresh_claim','member_map_refresh_save','member_map_refresh_claim_v2','member_map_refresh_save_v2');
  if allowed then execute pg_catalog.format('grant execute on function %s to service_role',f); end if;
  if exists(select 1 from pg_catalog.pg_proc pr,
    lateral pg_catalog.aclexplode(coalesce(pr.proacl,pg_catalog.acldefault('f',pr.proowner))) a
    where pr.oid=f::oid and a.grantee<>pr.proowner
     and not(allowed and a.grantee=(select oid from pg_catalog.pg_roles where rolname='service_role')
       and a.privilege_type='EXECUTE' and not a.is_grantable)) then
   raise exception 'refresh-continuation-unsafe-grants';
  end if;
  foreach role_name in array array['anon','authenticated','service_role'] loop
   if pg_catalog.has_function_privilege(role_name,f,'EXECUTE') is distinct from (role_name='service_role' and allowed) then
    raise exception 'refresh-continuation-unsafe-grants';
   end if;
  end loop;
 end loop;
end $$;
commit;
