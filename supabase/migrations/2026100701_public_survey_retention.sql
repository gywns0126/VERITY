-- Approved survey retention: delete whole responses after 90 elapsed days.
-- Requires 2026100601_public_survey.sql and the existing pg_cron installation.
-- Hourly execution is traffic-independent; normal deletion lag is < 1 hour.
-- Deletion also expires replay/browser deduplication for the deleted rows.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $prerequisite$
BEGIN
    IF to_regclass('public.public_survey_responses') IS NULL
       OR to_regprocedure('public.submit_public_survey(text,uuid,text,jsonb,text)') IS NULL THEN
        RAISE EXCEPTION 'public_survey_retention_requires_2026100601';
    END IF;
END;
$prerequisite$;

DO $cron_prerequisite$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RAISE EXCEPTION 'public_survey_retention_requires_existing_pg_cron';
    END IF;
END;
$cron_prerequisite$;

CREATE INDEX IF NOT EXISTS public_survey_responses_created_at_idx
    ON public.public_survey_responses (created_at);

CREATE OR REPLACE FUNCTION public.maintain_public_survey_responses()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    -- Hours express exactly 90 * 24 elapsed hours, independent of DST/timezone.
    v_cutoff TIMESTAMPTZ := statement_timestamp() - INTERVAL '2160 hours';
    v_removed BIGINT;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('alphanest-public-survey-retention', 0));
    DELETE FROM public.public_survey_responses WHERE created_at <= v_cutoff;
    GET DIAGNOSTICS v_removed = ROW_COUNT;
    RETURN v_removed;
END;
$function$;
REVOKE ALL ON FUNCTION public.maintain_public_survey_responses()
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.maintain_public_survey_responses() TO service_role;

COMMENT ON TABLE public.public_survey_responses IS
    'Private survey answers; backend/operator access only. Whole rows, including answers and HMAC identity, expire after 90 elapsed days and are deleted hourly by pg_cron. Replay/browser deduplication ends on deletion. No raw client ID, account ID, IP or contact fields.';
COMMENT ON FUNCTION public.maintain_public_survey_responses() IS
    'Service/owner/scheduler only: delete whole survey responses aged at least 90 elapsed days. Fixed cutoff, no caller parameters; returns only removed count.';

DO $schedule$
DECLARE
    v_command TEXT := $job$SET statement_timeout = '30s';
SET lock_timeout = '5s';
SELECT public.maintain_public_survey_responses();
DELETE FROM cron.job_run_details
 WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'alphanest-public-survey-retention')
   AND end_time < now() - INTERVAL '30 days';$job$;
BEGIN
    -- Same named-job pattern as 046; never remove or rewrite another job.
    IF (SELECT COUNT(*) FROM cron.job WHERE jobname = 'alphanest-public-survey-retention') > 1
       OR EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'alphanest-public-survey-retention'
                  AND (command IS DISTINCT FROM v_command
                       OR username IS DISTINCT FROM current_user
                       OR database IS DISTINCT FROM current_database())) THEN
        RAISE EXCEPTION 'existing_survey_retention_job_changed_reconcile_first';
    END IF;
    PERFORM cron.schedule('alphanest-public-survey-retention', '23 * * * *', v_command);
    IF (SELECT COUNT(*) FROM cron.job
         WHERE jobname = 'alphanest-public-survey-retention' AND active
           AND schedule = '23 * * * *' AND command = v_command
           AND username = current_user AND database = current_database()) <> 1 THEN
        RAISE EXCEPTION 'public_survey_retention_schedule_not_active';
    END IF;
END;
$schedule$;

-- Remove any already-expired payloads on activation, then continue hourly.
SELECT public.maintain_public_survey_responses();
COMMIT;
