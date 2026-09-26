-- Notice artwork only; existing notices, dates, RLS and storage buckets are preserved.
ALTER TABLE public.notices
    ADD COLUMN IF NOT EXISTS thumbnail_theme text NOT NULL DEFAULT 'auto',
    ADD COLUMN IF NOT EXISTS thumbnail_url text NOT NULL DEFAULT '';

COMMENT ON COLUMN public.notices.thumbnail_theme IS
    'auto or a built-in vector theme selected by the administrator; no generative API';
COMMENT ON COLUMN public.notices.thumbnail_url IS
    'Optional public notice-images URL; artwork only, never private attachments';

-- Public artwork is uploaded exclusively by the authenticated admin API using service role.
-- No anon/authenticated write policy is added. Do not reuse the private operator bucket.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('notice-images', 'notice-images', true, 262144, ARRAY['image/png'])
ON CONFLICT (id) DO NOTHING;

NOTIFY pgrst, 'reload schema';
