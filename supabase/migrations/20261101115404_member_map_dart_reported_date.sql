-- Forward-only repair for DART rcept_no/rcept_dt counterexamples.
-- Deploy updated checkpoint readers + queried_date producers before activation.
-- Existing digest includes normalized row.date from rcept_dt. Producer validates
-- every row.date == queried_date == pending.date before generating proof.
-- SQL checks the explicit query date and digest equality across guards/sweeps;
-- an opaque digest cannot independently prove source authenticity or its date.
-- No checkpoint rewrite, receipt pruning, cursor skip, or success promotion.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';
select pg_catalog.pg_advisory_xact_lock(20261012,1001);
do $$
begin
 if (select md5(prosrc) from pg_catalog.pg_proc where oid='public.member_map_dart_checkpoint_valid(jsonb)'::regprocedure) is distinct from 'f735f673f7da662c71ce6849bdcc55f4'
 or (select md5(prosrc) from pg_catalog.pg_proc where oid='public.member_map_dart_replay(jsonb,jsonb,text,text,jsonb)'::regprocedure) is distinct from 'b862d84486b7aa44498dc4c7bdaa6d22' then
  raise exception 'refresh-reported-date-function-drift';
 end if;
end $$;

create or replace function public.member_map_dart_checkpoint_valid(p_cp jsonb) returns boolean
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
   if not public.member_map_dart_map_valid(p->m) then return false; end if;
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

create or replace function public.member_map_dart_replay(p_cp jsonb,p_cursor jsonb,p_now text,p_catalog text,p_pages jsonb) returns jsonb
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
  if pg_catalog.jsonb_typeof(proof)<>'object' or not(proof ?& array['page_no','total_count','rows','queried_date'])
   or exists(select 1 from pg_catalog.jsonb_object_keys(proof) k where k not in ('page_no','total_count','rows','queried_date'))
   or pg_catalog.jsonb_typeof(proof->'queried_date') is distinct from 'string'
   or proof->>'queried_date' is distinct from p->>'date'
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
  if not public.member_map_dart_map_valid(r)
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

-- CREATE OR REPLACE preserves ACLs. Refuse unexpected grants rather than
-- adding a public capability or silently repairing unrelated privilege drift.
do $$
declare f regprocedure;
begin
 foreach f in array array[
  'public.member_map_dart_checkpoint_valid(jsonb)'::regprocedure,
  'public.member_map_dart_replay(jsonb,jsonb,text,text,jsonb)'::regprocedure] loop
  if exists(select 1 from pg_catalog.pg_proc p,
    lateral pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
    where p.oid=f::oid and a.grantee<>p.proowner)
   or pg_catalog.has_function_privilege('anon',f,'EXECUTE')
   or pg_catalog.has_function_privilege('authenticated',f,'EXECUTE')
   or pg_catalog.has_function_privilege('service_role',f,'EXECUTE') then
   raise exception 'refresh-reported-date-unsafe-grants';
  end if;
 end loop;
end $$;
commit;
