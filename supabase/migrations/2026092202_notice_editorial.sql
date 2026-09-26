-- Additive editorial fields. Existing RLS/auth/audit and publication windows are unchanged.
BEGIN;
ALTER TABLE public.notices
    ADD COLUMN IF NOT EXISTS display_date date,
    ADD COLUMN IF NOT EXISTS home_visible boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS related_tickers text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS related_topics text[] NOT NULL DEFAULT '{}';
UPDATE public.notices SET display_date = (created_at AT TIME ZONE 'Asia/Seoul')::date
WHERE display_date IS NULL;
ALTER TABLE public.notices ALTER COLUMN display_date SET DEFAULT ((now() AT TIME ZONE 'Asia/Seoul')::date);
COMMENT ON COLUMN public.notices.display_date IS 'Editorial display date, independently editable; created_at remains the actual registration timestamp.';
COMMENT ON COLUMN public.notices.home_visible IS 'Explicit opt-in for the home news cards, independent of site-wide banner.';
COMMIT;
