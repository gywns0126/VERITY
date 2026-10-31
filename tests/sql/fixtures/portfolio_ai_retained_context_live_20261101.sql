-- Offline source fixture only: do not apply this original function definition.
-- Read-only pg_get_functiondef capture: project lykqebdcurreppowulsl, 2026-11-01 KST.
-- definition_sha256: bcba3b377451e886b96af3dc470a74ba54fbecdbec0546fea9291d65eb0f6f7c
CREATE OR REPLACE FUNCTION public.portfolio_ai_result_put(p_key text, p_reservation_id uuid, p_document jsonb, p_result jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
 v_budget public.portfolio_ai_budget_calls%rowtype; v_existing public.portfolio_ai_results%rowtype;
 v_source_id text; v_receipt text; v_party jsonb; v_relation jsonb; v_status text; v_usage jsonb;
 v_raw_answer jsonb; v_assessed_as_of text; v_inserted integer;
begin
 if p_key is null or p_key !~ '^[0-9a-f]{64}$' or p_reservation_id is null
  or p_document is null or p_result is null or pg_catalog.jsonb_typeof(p_document) <> 'object'
  or pg_catalog.jsonb_typeof(p_result) <> 'object'
  or pg_catalog.octet_length(p_document::text) + pg_catalog.octet_length(p_result::text) > 131072 then
  raise exception 'invalid_portfolio_ai_result_payload' using errcode = '22023';
 end if;
 if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(p_document)) not in (7,8)
  or not (p_document ?& array['source_id','issuer_id','issuer_name','as_of','url','text','counterparties'])
  or exists (select 1 from pg_catalog.jsonb_object_keys(p_document) as k(value) where value not in
   ('source_id','issuer_id','issuer_name','as_of','url','text','counterparties','resolved_relations'))
  or pg_catalog.jsonb_typeof(p_document->'source_id') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'issuer_id') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'issuer_name') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'as_of') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'url') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'text') <> 'string'
  or pg_catalog.jsonb_typeof(p_document->'counterparties') <> 'array'
  or p_document->>'issuer_id' !~ '^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$'
  or pg_catalog.char_length(p_document->>'issuer_name') not between 1 and 160
  or pg_catalog.char_length(p_document->>'text') not between 1 and 600 then
  raise exception 'invalid_portfolio_ai_result_document' using errcode = '22023';
 end if;
 v_source_id := p_document->>'source_id';
 if v_source_id !~ '^source:dart:[0-9]{14}$' then raise exception 'invalid_portfolio_ai_result_source' using errcode = '22023'; end if;
 v_receipt := pg_catalog.substr(v_source_id,13);
 begin
  if (p_document->>'as_of')::date is null or (p_document->>'as_of') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
   or (p_document->>'as_of') <> pg_catalog.substr(v_receipt,1,4) || '-' || pg_catalog.substr(v_receipt,5,2) || '-' || pg_catalog.substr(v_receipt,7,2)
   or (p_document->>'url') <> 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' || v_receipt then
   raise exception 'invalid_portfolio_ai_result_source' using errcode = '22023';
  end if;
 exception when others then raise exception 'invalid_portfolio_ai_result_source' using errcode = '22023';
 end;
 if pg_catalog.jsonb_array_length(p_document->'counterparties') not between 1 and 8 then
  raise exception 'invalid_portfolio_ai_result_parties' using errcode = '22023'; end if;
 for v_party in select e.value from pg_catalog.jsonb_array_elements(p_document->'counterparties') as e loop
  if pg_catalog.jsonb_typeof(v_party) <> 'object'
   or (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_party)) <> 2
   or not (v_party ?& array['id','name']) or pg_catalog.jsonb_typeof(v_party->'id') <> 'string'
   or pg_catalog.jsonb_typeof(v_party->'name') <> 'string'
   or v_party->>'id' !~ '^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$'
   or pg_catalog.char_length(v_party->>'name') not between 1 and 160 then
   raise exception 'invalid_portfolio_ai_result_party' using errcode = '22023'; end if;
 end loop;
 if (p_document ? 'resolved_relations') then
  if pg_catalog.jsonb_typeof(p_document->'resolved_relations') <> 'array'
   or pg_catalog.jsonb_array_length(p_document->'resolved_relations') > 24 then
   raise exception 'invalid_portfolio_ai_result_relations' using errcode = '22023'; end if;
  for v_relation in select e.value from pg_catalog.jsonb_array_elements(p_document->'resolved_relations') as e loop
   if pg_catalog.jsonb_typeof(v_relation) <> 'object'
    or (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_relation)) <> 2
    or not (v_relation ?& array['counterparty_id','role'])
    or pg_catalog.jsonb_typeof(v_relation->'counterparty_id') <> 'string'
    or v_relation->>'counterparty_id' !~ '^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$'
    or pg_catalog.jsonb_typeof(v_relation->'role') <> 'string'
    or v_relation->>'role' not in ('customer','supplier') then
    raise exception 'invalid_portfolio_ai_result_relation' using errcode = '22023'; end if;
  end loop;
 end if;
 if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(p_result)) <> 10
  or not (p_result ?& array['schema','provider','model','reasoning_effort','task_version','assessed_as_of','usage','charge_micro_usd','status','raw_answer'])
  or pg_catalog.jsonb_typeof(p_result->'schema') <> 'string' or p_result->>'schema' <> 'portfolio-ai-result-v1'
  or pg_catalog.jsonb_typeof(p_result->'provider') <> 'string' or p_result->>'provider' <> 'openai'
  or pg_catalog.jsonb_typeof(p_result->'model') <> 'string' or p_result->>'model' <> 'gpt-6-luna'
  or pg_catalog.jsonb_typeof(p_result->'reasoning_effort') <> 'string' or p_result->>'reasoning_effort' <> 'none'
  or pg_catalog.jsonb_typeof(p_result->'task_version') <> 'string' or pg_catalog.char_length(p_result->>'task_version') not between 1 and 128
  or (pg_catalog.jsonb_typeof(p_result->'assessed_as_of') <> 'null' and
   (pg_catalog.jsonb_typeof(p_result->'assessed_as_of') <> 'string' or p_result->>'assessed_as_of' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'))
  or pg_catalog.jsonb_typeof(p_result->'charge_micro_usd') <> 'number' or p_result->>'charge_micro_usd' !~ '^(0|[1-9][0-9]*)$'
  or (p_result->>'charge_micro_usd')::numeric > 10000 or pg_catalog.jsonb_typeof(p_result->'status') <> 'string'
  or pg_catalog.jsonb_typeof(p_result->'raw_answer') not in ('object','null') then
  raise exception 'invalid_portfolio_ai_result_envelope' using errcode = '22023'; end if;
 if pg_catalog.jsonb_typeof(p_result->'assessed_as_of') = 'string' then
  v_assessed_as_of := p_result->>'assessed_as_of';
  begin
   if v_assessed_as_of::date::text <> v_assessed_as_of then raise exception 'invalid_portfolio_ai_result_date'; end if;
  exception when others then raise exception 'invalid_portfolio_ai_result_envelope' using errcode = '22023';
  end;
 end if;
 v_status := p_result->>'status';
 if v_status not in ('ok','error') then raise exception 'invalid_portfolio_ai_result_status' using errcode = '22023'; end if;
 v_usage := p_result->'usage';
 if pg_catalog.jsonb_typeof(v_usage) = 'object' then
  if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_usage)) <> 4
   or not (v_usage ?& array['input_tokens','output_tokens','thinking_tokens','cached_input_tokens'])
   or exists (select 1 from pg_catalog.jsonb_each(v_usage) as e where pg_catalog.jsonb_typeof(e.value) <> 'number' or e.value #>> '{}' !~ '^(0|[1-9][0-9]*)$')
   or (v_usage->>'cached_input_tokens')::numeric > (v_usage->>'input_tokens')::numeric
   or (v_usage->>'thinking_tokens')::numeric > (v_usage->>'output_tokens')::numeric then
   raise exception 'invalid_portfolio_ai_result_usage' using errcode = '22023'; end if;
 elsif pg_catalog.jsonb_typeof(v_usage) <> 'null' then raise exception 'invalid_portfolio_ai_result_usage' using errcode = '22023';
 end if;
 v_raw_answer := p_result->'raw_answer';
 if v_status = 'ok' then
  if pg_catalog.jsonb_typeof(v_usage) <> 'object' or pg_catalog.jsonb_typeof(v_raw_answer) <> 'object' then
   raise exception 'invalid_portfolio_ai_result_answer' using errcode = '22023'; end if;
  if not (
   ((select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_raw_answer)) = 1
    and v_raw_answer ? 'candidates' and pg_catalog.jsonb_typeof(v_raw_answer->'candidates') = 'array' and pg_catalog.jsonb_array_length(v_raw_answer->'candidates') <= 4)
   or ((select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_raw_answer)) = 2
    and v_raw_answer ?& array['claims','remaining_count'] and pg_catalog.jsonb_typeof(v_raw_answer->'claims') = 'array'
    and pg_catalog.jsonb_array_length(v_raw_answer->'claims') <= 4 and pg_catalog.jsonb_typeof(v_raw_answer->'remaining_count') = 'number'
    and v_raw_answer->>'remaining_count' ~ '^(0|[1-9][0-9]*)$' and (v_raw_answer->>'remaining_count')::integer <= 500)
   or ((select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_raw_answer)) = 2
    and v_raw_answer ?& array['judgments','remaining_count'] and pg_catalog.jsonb_typeof(v_raw_answer->'judgments') = 'array'
    and pg_catalog.jsonb_array_length(v_raw_answer->'judgments') <= 16 and pg_catalog.jsonb_typeof(v_raw_answer->'remaining_count') = 'number'
    and v_raw_answer->>'remaining_count' ~ '^(0|[1-9][0-9]*)$' and (v_raw_answer->>'remaining_count')::integer <= 500)) then
   raise exception 'invalid_portfolio_ai_result_answer' using errcode = '22023'; end if;
 end if;
 if not public.portfolio_ai_results_closed_keys(p_document,0) or not public.portfolio_ai_results_closed_keys(p_result,0) then
  raise exception 'invalid_portfolio_ai_result_keys' using errcode = '22023'; end if;
 select * into v_budget from public.portfolio_ai_budget_calls where key = p_key for update;
 if not found or v_budget.reservation_id <> p_reservation_id
  or (p_result->>'charge_micro_usd')::bigint > v_budget.reserved
  or (v_budget.settled and v_budget.charge <> (p_result->>'charge_micro_usd')::bigint) then
  raise exception 'portfolio_ai_result_reservation_mismatch' using errcode = '22023'; end if;
 insert into public.portfolio_ai_results(key,reservation_id,document,result) values (p_key,p_reservation_id,p_document,p_result) on conflict (key) do nothing;
 get diagnostics v_inserted = row_count;
 if v_inserted = 1 then return pg_catalog.jsonb_build_object('status','stored','key',p_key); end if;
 select * into v_existing from public.portfolio_ai_results where key = p_key;
 if v_existing.reservation_id = p_reservation_id and v_existing.document = p_document and v_existing.result = p_result then
  return pg_catalog.jsonb_build_object('status','already-stored','key',p_key);
 else raise exception 'portfolio_ai_result_conflict' using errcode = '22023'; end if;
end;
$function$

-- definition_sha256: ebc39facf7a9c442b14f0111e282008aded19bce9a43b10805cec7d39e1bff68
CREATE OR REPLACE FUNCTION public.portfolio_ai_results_closed_keys(p_value jsonb, p_depth integer)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_key text; v_child jsonb;
begin
 if p_value is null or p_depth < 0 or p_depth > 32 then return false; end if;
 if pg_catalog.jsonb_typeof(p_value) = 'object' then
  for v_key, v_child in select e.key, e.value from pg_catalog.jsonb_each(p_value) as e loop
   if v_key <> all (array[
    'source_id','issuer_id','issuer_name','as_of','url','text','counterparties',
    'resolved_relations','id','name','role','status','schema','judgments','rejected',
    'candidates','claims','context','claim_kind','claim_state','directness',
    'quality_review','coverage','remaining_count','index','reason','version','findings',
    'judgment_id','axis','code','evidence_quotes','input','retained','remaining_reported',
    'truncated','scope','assessed_as_of','proposal','source_url','published_on',
    'evidence_refs','start','end','review_reasons','missing_evidence','verification',
    'current_validity','display','degree','impact','revision','materiality_review_reasons',
    'company_id','counterparty_id','source_version','quote','scope_quote','period_quote',
    'basis','direction','channel','channel_quote','condition','counter_evidence_quotes','review_trigger',
    'economic_v2','period_context_v2','materiality','value','scope_quote','period_quote',
    'mechanism_quote','object_quote','scale_quote','time_quote','importance','error_type',
    'provider','model','reasoning_effort','task_version','usage','input_tokens',
    'output_tokens','thinking_tokens','cached_input_tokens','charge_micro_usd','raw_answer'
   ]) then return false; end if;
   if v_key = 'status' and (pg_catalog.jsonb_typeof(v_child) <> 'string'
    or v_child #>> '{}' not in ('ok','error','judgment_candidate','needs_context')) then return false; end if;
   if not public.portfolio_ai_results_closed_keys(v_child,p_depth + 1) then return false; end if;
  end loop;
 elsif pg_catalog.jsonb_typeof(p_value) = 'array' then
  for v_child in select e.value from pg_catalog.jsonb_array_elements(p_value) as e loop
   if not public.portfolio_ai_results_closed_keys(v_child,p_depth + 1) then return false; end if;
  end loop;
 end if;
 return true;
end;
$function$

