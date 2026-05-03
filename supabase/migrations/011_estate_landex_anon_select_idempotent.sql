-- ESTATE-P2-002 정정 (P3-1, 2026-05-03):
-- migration 004 의 estate_snapshots_public_read 정책 적용 누락 보강 (멱등).
--
-- 진단 (P3-1 보고):
--   - 004_estate_tables.sql 의 SQL 자체는 코드 주석 (vercel-api/api/landex_scores.py:66
--     "anon 키로 SELECT 가능 — RLS 공개 정책") 과 100% 정합.
--   - 004 이후 migration 들이 estate_landex_snapshots 정책 덮어쓰지 않음 (silent fail X).
--   - 그럼에도 V4 1차 시 anon 401 → migration 004 가 사용자 Supabase 인스턴스에
--     적용 누락 또는 dashboard 수동 변경 추정.
--
-- 정합 회복:
--   estate_landex_snapshots 는 공개 가격 데이터 (PIPA 무관) → anon SELECT 가 의도된 설계.
--   service_role 은 빌더 (서버사이드 cron) 만 사용 — Vercel landex_scores endpoint 는
--   anon 으로 통과하는 게 ESTATE 표준 (다른 endpoint 와 일관).
--
-- 사용자 작업:
--   Supabase Dashboard → SQL Editor → 이 파일 통째 복붙 → Run.
--
-- 검증 query (실행 후 정책 존재 확인):
--   SELECT policyname, cmd, roles FROM pg_policies
--     WHERE tablename = 'estate_landex_snapshots';
--
-- 추가 권장 (T34):
--   다른 migration 적용 상태 점검 — ESTATE-P2-002 가 누락이면 다른 것도 가능.
--   SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version;

DROP POLICY IF EXISTS "estate_snapshots_public_read" ON estate_landex_snapshots;

CREATE POLICY "estate_snapshots_public_read" ON estate_landex_snapshots
    FOR SELECT TO authenticated, anon USING (true);

-- 정책 등록 직후 RLS 가 enable 되어 있는지 보강 (멱등 — 이미 enable 이면 no-op).
ALTER TABLE estate_landex_snapshots ENABLE ROW LEVEL SECURITY;
