-- REVIEW PROPOSAL ONLY; main owns supported MCP migration/version persistence.
-- Apply only in the caller's migration transaction; deliberately no COMMIT here.
-- Source: read-only pg_get_functiondef, lykqebdcurreppowulsl, 2026-11-01 KST.
-- Existing put body/ACL and closed-key definition are preserved except for the
-- three exact matches below. No table/policy/grant/provider/budget changes.
set local lock_timeout = '5s';
set local statement_timeout = '15s';

do $migration$
declare
    v_oid oid := 'public.portfolio_ai_result_put(text,uuid,jsonb,jsonb)'::regprocedure;
    v_closed_oid oid := 'public.portfolio_ai_results_closed_keys(jsonb,integer)'::regprocedure;
    v_before text;
    v_after text;
    v_metadata text;
    v_change record;
    v_count integer;
    v_validator text := $validator$
 -- retained_context_v1: independently validate before the original closed-key floor.
 if p_document ? 'retained_context_v1' then
  declare
   v_context jsonb := p_document->'retained_context_v1';
   v_raw text;
   v_effective text;
   v_excerpt text;
   v_head text;
   v_mark text;
   v_last integer;
   v_index integer;
   v_cut boolean := false;
   v_safe text;
   v_pattern text;
   -- Python str.strip whitespace, not arbitrary internal whitespace removal.
   v_ws constant text := U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
  begin
   if p_result->>'task_version' is distinct from 'company-business-judgment-v1'
      or pg_catalog.jsonb_typeof(v_context) is distinct from 'object' then
    raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
   end if;
   if (select pg_catalog.count(*) from pg_catalog.jsonb_object_keys(v_context)) <> 6
      or not (v_context ?& array['issuer_name','receipt_no','filing_date','text','raw_sha256','excerpt_sha256'])
      or exists (select 1 from pg_catalog.jsonb_each(v_context) as e
                  where pg_catalog.jsonb_typeof(e.value) <> 'string')
      or p_document->>'issuer_id' !~ '^KR:[0-9]{6}$'
      or v_context->>'issuer_name' is distinct from p_document->>'issuer_name'
      or v_context->>'receipt_no' is distinct from v_receipt
      or v_context->>'filing_date' is distinct from p_document->>'as_of'
      or pg_catalog.char_length(v_context->>'text') not between 1 and 2500
      or v_context->>'raw_sha256' !~ '^[0-9a-f]{64}$'
      or v_context->>'excerpt_sha256' !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
   end if;
   -- Source/receipt/date/URL and base text <=600 already passed original guards.
   v_raw := v_context->>'text';
   if v_context->>'raw_sha256' is distinct from
      pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_raw,'UTF8')),'hex')
      or v_context->>'excerpt_sha256' is distinct from
      pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_document->>'text','UTF8')),'hex') then
    raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
   end if;
   v_effective := pg_catalog.btrim(pg_catalog.replace(pg_catalog.replace(
       pg_catalog.replace(v_raw,E'\r\n',' '),E'\r',' '),E'\n',' '),v_ws);
   -- Mirror safe_public_text plus the helper's instruction rejection. Apply to
   -- the whole raw projection (including its suffix), name, and original excerpt.
   foreach v_safe in array array[v_context->>'issuer_name',p_document->>'text',v_effective] loop
    v_safe := pg_catalog.btrim(v_safe,v_ws);
    if v_safe = '' or v_safe ~ U&'[\0001-\001F\007F]'
       or v_safe ~* 'ignore.{0,30}instruction|system\s*prompt|api[_ -]?key|비밀|지시를?\s*무시' then
     raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
    end if;
    foreach v_pattern in array array[
     '(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])',
     '(?<!\d)(?:\+?\d{1,3}[- .]?)?\(?\d{2,4}\)?[- .]\d{3,4}[- .]\d{4}(?!\d)',
     '(?<![0-9])[0-9]{10,}(?![0-9])',
     '(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])',
     '(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])',
     '(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])',
     '\y(?:secret|password|passwd|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|authorization|bearer|private[ _-]?key|owner[ _-]?id|member[ _-]?id|tenant[ _-]?id)\y|(?:비밀번호|인증토큰|접근토큰|개인키|주민등록번호)',
     '(?:file://|(?:^|[\s"''(])(?:/Users/|/home/|/private/|/var/|\.\.?/|[a-z]:\\))',
     '(?:https?|ftp|data|javascript):',
     '<[^>]*>|&(?:lt|gt|#(?:x[0-9a-f]+|\d+));'
    ] loop
     if v_safe ~* v_pattern then
      raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
     end if;
    end loop;
   end loop;
   -- Exact helper projection: _cut_at_sentence(600), cap, CR/LF -> space, strip.
   -- No fuzzy matching, whitespace collapse, case folding, or Unicode normalization.
   v_excerpt := v_raw;
   if pg_catalog.char_length(v_raw) > 600 then
    v_head := pg_catalog.substr(v_raw,1,600);
    foreach v_mark in array array['습니다.','합니다.','다.'] loop
     v_last := pg_catalog.strpos(pg_catalog.reverse(v_head),pg_catalog.reverse(v_mark));
     if v_last > 0 then
      v_index := pg_catalog.char_length(v_head) - v_last - pg_catalog.char_length(v_mark) + 1;
      if v_index > 300 then
       v_excerpt := pg_catalog.btrim(pg_catalog.substr(v_head,1,v_index + pg_catalog.char_length(v_mark)),v_ws);
       v_cut := true;
       exit;
      end if;
     end if;
    end loop;
    if not v_cut then v_excerpt := pg_catalog.rtrim(v_head,v_ws) || '…'; end if;
    if pg_catalog.char_length(v_excerpt) > 600 then
     v_excerpt := pg_catalog.substr(v_excerpt,1,599) || '…';
    end if;
   end if;
   v_excerpt := pg_catalog.btrim(pg_catalog.replace(pg_catalog.replace(
       pg_catalog.replace(v_excerpt,E'\r\n',' '),E'\r',' '),E'\n',' '),v_ws);
   if v_excerpt is distinct from p_document->>'text' then
    raise exception 'invalid_portfolio_ai_result_context' using errcode = '22023';
   end if;
  end;
 end if;
$validator$;
begin
    perform pg_catalog.pg_advisory_xact_lock(20261011,1101);
    v_before := pg_catalog.pg_get_functiondef(v_oid);
    if pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_before,'UTF8')),'hex')
       <> 'bcba3b377451e886b96af3dc470a74ba54fbecdbec0546fea9291d65eb0f6f7c'
       or pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
           pg_catalog.pg_get_functiondef(v_closed_oid),'UTF8')),'hex')
       <> 'ebc39facf7a9c442b14f0111e282008aded19bce9a43b10805cec7d39e1bff68' then
        raise exception 'retained_context_unexpected_live_definition';
    end if;
    select row(p.proacl,p.prosecdef,p.proconfig,p.proowner,p.provolatile,p.proparallel)::text
      into strict v_metadata from pg_catalog.pg_proc p where p.oid = v_oid;
    v_after := v_before;
    for v_change in select * from (values
        ('pg_catalog.jsonb_object_keys(p_document)',
         'pg_catalog.jsonb_object_keys(p_document - ''retained_context_v1'')',2),
        ('if not public.portfolio_ai_results_closed_keys(p_document,0)',
         v_validator || ' if not public.portfolio_ai_results_closed_keys(p_document - ''retained_context_v1'',0)',1)
    ) as changes(old_text,new_text,expected_count) loop
        v_count := (pg_catalog.char_length(v_after) - pg_catalog.char_length(
            pg_catalog.replace(v_after,v_change.old_text,''))) / pg_catalog.char_length(v_change.old_text);
        if v_count <> v_change.expected_count then
            raise exception 'retained_context_anchor_count_mismatch';
        end if;
        v_after := pg_catalog.replace(v_after,v_change.old_text,v_change.new_text);
    end loop;
    -- CREATE OR REPLACE the exact retrieved definition, preserving owner/ACL.
    execute v_after;
    if pg_catalog.pg_get_functiondef(v_oid) is distinct from v_after
       or (select row(p.proacl,p.prosecdef,p.proconfig,p.proowner,p.provolatile,p.proparallel)::text
             from pg_catalog.pg_proc p where p.oid = v_oid) is distinct from v_metadata
       or pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
           pg_catalog.pg_get_functiondef(v_closed_oid),'UTF8')),'hex')
          <> 'ebc39facf7a9c442b14f0111e282008aded19bce9a43b10805cec7d39e1bff68' then
        raise exception 'retained_context_post_transform_mismatch';
    end if;
end;
$migration$;
