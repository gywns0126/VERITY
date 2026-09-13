-- Opt-in only: existing pinned notices stay community-only.
-- Additive migration. No notice rows, policies or triggers are removed.
ALTER TABLE public.notices
    ADD COLUMN IF NOT EXISTS site_wide boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.notices.site_wide IS
    'Admin opt-in for the site-wide notice banner; independent of pinned ordering.';

NOTIFY pgrst, 'reload schema';
