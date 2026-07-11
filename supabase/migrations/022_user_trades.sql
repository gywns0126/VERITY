-- 022_user_trades — 사용자 본인 매매 거래 이력 + 실현손익(이동평균).
-- AlphaNest 보유종목 루프 확장: user_holdings(003)는 종목당 (user_id,ticker) UNIQUE 스냅샷 1행이라
-- 매도 시 실현손익이 소멸. 이 테이블은 매수/매도 이벤트를 append-only 로 누적 → 실현손익 복기 가능.
--
-- 🚨 RULE 7 = 사용자 자기 기록(사실). VERITY 채점·점수·등급·추천 0. 매수·매도 권유 0.
-- 🚨 법률(자본시장법 제101조의2②3호 "실현되지 아니한 수익률 제시" 금지 회피, 2026-07-11 법률 리서치):
--    · 실현손익 기반(미실현 평가손익 아님) → 문언 회피
--    · 본인 비공개 = RLS auth.uid()=user_id (공개/백분위/'상위 X%' 배지 없음)
--    · price = 사용자 본인 입력 체결가(실제 거래). 시세 재배포 아님(EOD 종가 미노출).
--    · 공개 성과 배지는 별도 레이어 + 변호사 게이트 통과 후에만.
-- user_holdings(003) / user_thesis(018) 아키텍처 미러. UNIQUE 제약만 제거(이력 누적형).

CREATE TABLE IF NOT EXISTS public.user_trades (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    market      TEXT NOT NULL DEFAULT 'kr',
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    shares      NUMERIC NOT NULL CHECK (shares > 0),
    price       NUMERIC NOT NULL CHECK (price >= 0),   -- 사용자 입력 체결가(실제 거래가)
    traded_at   DATE NOT NULL DEFAULT current_date,
    memo        TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_utr_user ON public.user_trades(user_id);
-- 실현손익 계산 = 종목별 시간순 순회 → (user_id, ticker, traded_at) 복합 인덱스.
CREATE INDEX IF NOT EXISTS idx_utr_user_ticker ON public.user_trades(user_id, ticker, traded_at);

ALTER TABLE public.user_trades ENABLE ROW LEVEL SECURITY;

-- RLS = 본인 행만. auth.uid() = user_id 단순 eq (self-subquery 없음 → 재귀 없음, RULE feedback_supabase_rls_no_self_subquery 정합).
CREATE POLICY utr_select ON public.user_trades
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY utr_insert ON public.user_trades
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY utr_update ON public.user_trades
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY utr_delete ON public.user_trades
    FOR DELETE USING (auth.uid() = user_id);
