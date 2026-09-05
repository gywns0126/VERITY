-- 037_community_support — 커뮤니티 공지·Q&A 탭의 질문/피드백 수집과 답변 공개.
--
-- 원칙:
--   1) 질문과 피드백은 기본 비공개다.
--   2) 질문자가 공개에 동의한 질문만 답변 완료 뒤 공개 Q&A에 노출한다.
--   3) 일반 사용자는 본인 행 생성·조회와 미답변 행 삭제만 가능하다.
--   4) 답변·상태·숨김 변경은 service_role을 사용하는 관리자 API만 가능하다.

CREATE TABLE IF NOT EXISTS public.community_support (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL CHECK (kind IN ('question', 'feedback')),
    title            TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    body             TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
    publish_consent  BOOLEAN NOT NULL DEFAULT false,
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'closed')),
    answer           TEXT CHECK (answer IS NULL OR char_length(answer) <= 3000),
    answered_by      UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    answered_at      TIMESTAMPTZ,
    hidden           BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT community_support_feedback_private
        CHECK (kind = 'question' OR publish_consent = false),
    CONSTRAINT community_support_answer_state
        CHECK (
            (status = 'answered' AND answer IS NOT NULL AND answered_at IS NOT NULL)
            OR status <> 'answered'
        )
);

CREATE INDEX IF NOT EXISTS idx_community_support_user
    ON public.community_support(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_community_support_admin
    ON public.community_support(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_community_support_public
    ON public.community_support(answered_at DESC)
    WHERE kind = 'question' AND publish_consent AND status = 'answered' AND NOT hidden;

ALTER TABLE public.community_support ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'community_support' AND policyname = 'cs_select_own'
    ) THEN
        CREATE POLICY cs_select_own ON public.community_support
            FOR SELECT USING (auth.uid() = user_id);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'community_support' AND policyname = 'cs_select_public_answered'
    ) THEN
        CREATE POLICY cs_select_public_answered ON public.community_support
            FOR SELECT USING (
                kind = 'question'
                AND publish_consent = true
                AND status = 'answered'
                AND hidden = false
            );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'community_support' AND policyname = 'cs_insert_own'
    ) THEN
        CREATE POLICY cs_insert_own ON public.community_support
            FOR INSERT WITH CHECK (
                auth.uid() = user_id
                AND status = 'open'
                AND answer IS NULL
                AND answered_by IS NULL
                AND answered_at IS NULL
                AND hidden = false
                AND (kind = 'question' OR publish_consent = false)
            );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'community_support' AND policyname = 'cs_delete_own_open'
    ) THEN
        CREATE POLICY cs_delete_own_open ON public.community_support
            FOR DELETE USING (auth.uid() = user_id AND status = 'open');
    END IF;
END
$$;

-- UPDATE 정책 없음: 사용자 JWT로 답변·상태·숨김을 바꿀 수 없다.

CREATE OR REPLACE FUNCTION public.touch_community_support_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'community_support'
          AND t.tgname = 'trg_community_support_touch'
          AND NOT t.tgisinternal
    ) THEN
        CREATE TRIGGER trg_community_support_touch
            BEFORE UPDATE ON public.community_support
            FOR EACH ROW EXECUTE FUNCTION public.touch_community_support_updated_at();
    END IF;
END
$$;
