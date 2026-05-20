-- 016_estate_decommission_drop_tables.sql
-- ESTATE 전격 폐기 (PM 결정 2026-05-21) — 주거 소비자 product 테이블 제거.
-- 부동산=주식 분석 보조수단으로만 생존: corp 테이블은 SALVAGE(보존).
--
-- ⚠ 비가역 (데이터 삭제). 적용 전 백업 권장. Supabase SQL Editor 에서 실행.
-- 실측 확인(2026-05-21): 아래 4개 존재(drop), corp 2개 존재(KEEP).
--   estate_landex_snapshots(100) / estate_user_watch_complexes(0) /
--   estate_alerts(294) / estate_market_reports(2)
-- CASCADE = 의존 RLS policy / index / view 동반 정리 (011 anon_select, 014, 015 등).

-- ── DROP (제거된 백엔드가 쓰던 소비자 테이블) ──
DROP TABLE IF EXISTS public.estate_landex_snapshots     CASCADE;  -- landex 스냅샷 (landex 패키지 제거됨)
DROP TABLE IF EXISTS public.estate_user_watch_complexes CASCADE;  -- 주거 관심단지 (residential 제거됨)
DROP TABLE IF EXISTS public.estate_alerts               CASCADE;  -- estate 알림 (estate_alerts endpoint 제거됨)
DROP TABLE IF EXISTS public.estate_market_reports       CASCADE;  -- estate 시장리포트 (market_report 제거됨)

-- ── KEEP (corp salvage — 종목 보유 부동산 자산가치, VERITY 보조신호) ──
--   public.estate_corp_holdings   (37 rows)  ← estate_corp_holdings/by_region/asset_discount endpoint
--   public.estate_corp_facilities (219 rows) ← estate_corp_facilities/disposals endpoint
--   위 2개는 절대 DROP 금지. corp 트랙이 계속 사용.
