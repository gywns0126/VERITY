-- 018_user_thesis — 사용자 본인 매매 논지(thesis) 서버 영속화 (cross-device).
-- AlphaNest 루프 Phase 3a: localStorage(verity_thesis_v1) → 로그인 시 서버 통합. 기기 변경 시 논지 소실 해결.
-- 🚨 RULE 7 = 사용자 자기 저널(관점/메모/기록가). VERITY 채점·점수 아님. user_holdings(003) 아키텍처 미러.

CREATE TABLE IF NOT EXISTS public.user_thesis (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    market      TEXT NOT NULL DEFAULT 'kr',
    stance      TEXT NOT NULL DEFAULT 'watch',   -- bull | watch | bear
    note        TEXT DEFAULT '',
    entry_price NUMERIC,                          -- 기록 시점 동결 가격 (복기 diff 기준)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ut_user ON public.user_thesis(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ut_uniq ON public.user_thesis(user_id, ticker);

ALTER TABLE public.user_thesis ENABLE ROW LEVEL SECURITY;

-- RLS = 본인 행만. auth.uid() = user_id 단순 eq (self-subquery 없음 → 재귀 없음).
CREATE POLICY ut_select ON public.user_thesis
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY ut_insert ON public.user_thesis
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY ut_update ON public.user_thesis
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY ut_delete ON public.user_thesis
    FOR DELETE USING (auth.uid() = user_id);
