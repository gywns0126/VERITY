-- ═════════════════════════════════════════════════════════════════
-- 012: verity-reports storage bucket (private)
-- ─────────────────────────────────────────────────────────────────
-- 배경 (2026-05-03):
--   기존 PDF 서빙은 https://raw.githubusercontent.com/.../data/reports/<file>.pdf
--   를 직접 새창으로 여는 방식. 그런데
--     1) data/.gitignore line 18 의 `reports/` 가 VERITY 자동 생성 PDF 까지
--        잡아서 cron 의 `git add data/reports/` 가 침묵 → GitHub 에 한 번도
--        업로드된 적 없음 → raw URL 항상 404.
--     2) 설사 commit 됐더라도 admin 리포트는 검증 전 종목 점수/추천을 포함하므로
--        public raw URL 로 노출하면 안 됨 (feedback_scope: 시스템 트랙 비공개).
--
--   해결: PDF 를 Supabase Storage private bucket 에 업로드, vercel-api 가
--         JWT/admin 검증 후 signed URL 발급. cron 은 service_role 키로 PUT.
--
-- 변경 항목:
--   1) bucket verity-reports (public=false)
--   2) RLS — 누구도 직접 read/write 불가. 모든 접근은 service_role 또는
--      vercel-api 함수의 signed URL 경로로만.
-- ═════════════════════════════════════════════════════════════════

-- 1) bucket (idempotent)
INSERT INTO storage.buckets (id, name, public)
VALUES ('verity-reports', 'verity-reports', FALSE)
ON CONFLICT (id) DO UPDATE SET public = FALSE;


-- 2) RLS — anon/authenticated 모두 차단. service_role 만 PUT/GET.
--    Storage 의 storage.objects 테이블에 정책을 건다.
DROP POLICY IF EXISTS verity_reports_block_all_select ON storage.objects;
CREATE POLICY verity_reports_block_all_select ON storage.objects
    FOR SELECT TO anon, authenticated
    USING (bucket_id <> 'verity-reports');

DROP POLICY IF EXISTS verity_reports_block_all_insert ON storage.objects;
CREATE POLICY verity_reports_block_all_insert ON storage.objects
    FOR INSERT TO anon, authenticated
    WITH CHECK (bucket_id <> 'verity-reports');

DROP POLICY IF EXISTS verity_reports_block_all_update ON storage.objects;
CREATE POLICY verity_reports_block_all_update ON storage.objects
    FOR UPDATE TO anon, authenticated
    USING (bucket_id <> 'verity-reports');

DROP POLICY IF EXISTS verity_reports_block_all_delete ON storage.objects;
CREATE POLICY verity_reports_block_all_delete ON storage.objects
    FOR DELETE TO anon, authenticated
    USING (bucket_id <> 'verity-reports');

-- service_role 은 RLS 우회하므로 정책 불필요 (cron upload + signed URL 발급용).
