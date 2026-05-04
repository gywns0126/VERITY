-- ═════════════════════════════════════════════════════════════════
-- 013: action_queue.actor — Claude vs User 액터 분리
-- ─────────────────────────────────────────────────────────────────
-- 배경 (2026-05-04):
--   UserActionBell 도입 후 audit 결과 = 25건 pending 중 24건이 Claude 스스로
--   끝낼 수 있는 일정 마일스톤 (날짜 묶임 verification/monitoring), 1건만
--   사용자 직접 액션 (Framer paste). 사용자 의도와 어긋남 — bell 은 "내가
--   직접 해야 하는 일" 만 보여야 함.
--
-- 정책:
--   - actor='user'   = 사용자 손가락 필요 (Framer paste, Supabase SQL Editor,
--                                     KIS 토큰 갱신, 외부 사이트 클릭 등)
--   - actor='claude' = Claude 가 끝낼 수 있는 일 (코드 변경/커밋, 스크립트 실행,
--                                       정량 분석, cron 작성). 끝나면 Claude 가
--                                       즉시 done <id> 호출 → 사라짐
--
-- 새 룰 (action_queue.py / 메모리):
--   - cmd_add 의 default actor='claude' (대부분 Claude 가 자기 일정 적는 패턴)
--   - 사용자 액션이면 명시적 --actor user
--   - Bell 은 actor='user' 만 노출. claude 행은 DB 에 살아있되 invisible
--
-- 멱등성:
--   - DEFAULT 'user' 로 컬럼 추가 → 기존 row 자동 'user' 배정
--   - 그다음 alleged Claude-actor 24건을 명시적 UPDATE 로 'claude' 강등
--   - 재실행 시 ALTER 는 IF NOT EXISTS, UPDATE 는 idempotent
-- ═════════════════════════════════════════════════════════════════

ALTER TABLE public.user_action_queue
    ADD COLUMN IF NOT EXISTS actor TEXT NOT NULL DEFAULT 'user';

-- CHECK 제약 — 재적용 안전 (DROP IF EXISTS 후 재생성)
ALTER TABLE public.user_action_queue
    DROP CONSTRAINT IF EXISTS user_action_queue_actor_check;
ALTER TABLE public.user_action_queue
    ADD CONSTRAINT user_action_queue_actor_check
    CHECK (actor IN ('user', 'claude'));

-- 필터 인덱스 — Bell 은 status='pending' AND actor='user' 만 조회
CREATE INDEX IF NOT EXISTS idx_user_action_queue_actor_status
    ON public.user_action_queue(actor, status)
    WHERE status = 'pending';

-- ─────────────────────────────────────────────────────────────────
-- Backfill — 2026-05-04 audit 기준 Claude-actor 24건
-- (DigestPublishPanel d466eac1 만 user, 나머지 모두 claude)
-- ─────────────────────────────────────────────────────────────────

UPDATE public.user_action_queue
   SET actor = 'claude'
 WHERE id IN (
    'cef70562-1ddc-4cb8-ab57-0b82fe8ae31b',  -- 5/8 cross-link Gate A
    '389665e0-54c8-4fac-bbcd-75365ad5a3f6',  -- KI-9 backtest_stats_history cron 신설
    '741758f1-2563-42d8-8483-578036864e7f',  -- 5/11 Stage 2 진입 재판정
    '57ac6bd0-f58d-4e9b-bc6b-7f5f3e7afc46',  -- 5/17 P0e-b 4-cell 백테스트
    '41926867-fc2f-47cf-9932-72648f369540',  -- 5/26 D3 정식 verdict
    '7f2b51b5-bbc0-4aba-a479-5921e046651c',  -- 5/5 D3 첫 cron sanity
    '8c96aef5-89ea-4ce4-b7d0-8a521431e70f',  -- 5/16 ATR Phase 0 마이그레이션 검증
    '8b15703c-7ad3-403c-b2a0-297e6122fcc1',  -- 8/4 EveryTicker 5건 90일 재검토
    '49228ff1-afa3-46c4-ab7f-e1ac94316e35',  -- 8/4 Cross-link 12주 v1.5 재평가
    '9528e458-1fae-4632-a420-e2708c0bbaf0',  -- Cross-link P2 wire (api/main.py)
    '70793d08-502a-4fbb-ad1f-b994971b5a3b',  -- 5/20 KR 기관 대량보유 sprint
    '51bc0e0b-a295-4780-9f92-71232d130874',  -- 5/17 P0a 신호 3 정량 룰
    'a39d77a7-2a8e-4fbb-a8d1-963e941262cc',  -- ATR-stop 운영 재검증
    '0b7aadbc-3ada-4078-87d3-24dee2a560b6',  -- 5/10 Gemini 캐시 hit ratio
    'b445ba47-16f2-45c3-916a-f2920f500472',  -- 5/17 PR#26 (c) Druckenmiller
    '839dc388-c9e5-41bc-9df1-4b3dab4037ca',  -- 5/17 PR#26 (b) Ackman
    '2b06e593-3d75-45cf-ace1-d9cd78bc5138',  -- 5/17 PR#26 (a) Hohn
    '64d145cc-fa73-4659-89d7-6c3be52a5d4e',  -- P1a VAMS 프로필 alpha 비교
    '8d762b0a-ab02-4d87-a733-890144808281',  -- Bessembinder 운영 함의
    '0f6dce6a-4877-4eba-beb0-c23e813a279a',  -- P0e-c ATR multiplier 재검토
    'a76f7dd5-c753-4bba-9a39-ae73b4b97520',  -- P0d-3 Candle bonus 출처 검증
    'a760aaff-add0-4048-be0e-8b08c7681070',  -- P0b Brain 가중치 7:3 OOS
    'ea3d607b-3af9-455c-ab65-11f8cf4762da',  -- 5/12 D3 mid-checkpoint
    '453e244f-f9ca-4d56-9db4-5b41d64cc6a9'   -- 5/7 1주 운영 점검
 );

-- DigestPublishPanel (d466eac1) 은 default 'user' 그대로 유지 — 명시 update 불필요.

COMMENT ON COLUMN public.user_action_queue.actor IS
    '"user" = 사용자 손가락 필요 (Framer paste 등). "claude" = Claude 가 끝내고 즉시 done. Bell 은 user 만 노출.';
