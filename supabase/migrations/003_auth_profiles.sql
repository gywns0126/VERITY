-- ═══════════════════════════════════════════════════════════════
-- 003: Supabase Auth 기반 프로필 + 유저별 홀딩스 + 워치그룹 auth 전환
-- Supabase Dashboard SQL Editor에서 실행
-- ═══════════════════════════════════════════════════════════════

-- 1) profiles 테이블 (auth.users 트리거로 자동 생성)
CREATE TABLE IF NOT EXISTS public.profiles (
    id           UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email        TEXT,
    display_name TEXT DEFAULT '',
    avatar_url   TEXT DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_select_own ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY profiles_update_own ON public.profiles
    FOR UPDATE USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

CREATE POLICY profiles_insert_own ON public.profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

-- auth.users INSERT 시 profiles 자동 생성
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data ->> 'name', split_part(NEW.email, '@', 1))
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 2) user_holdings (유저별 보유 종목)
CREATE TABLE IF NOT EXISTS public.user_holdings (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    market      TEXT NOT NULL DEFAULT 'kr',
    shares      NUMERIC NOT NULL DEFAULT 0,
    avg_cost    NUMERIC NOT NULL DEFAULT 0,
    memo        TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_uh_user ON public.user_holdings(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_uh_uniq ON public.user_holdings(user_id, ticker);

ALTER TABLE public.user_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY uh_select ON public.user_holdings
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY uh_insert ON public.user_holdings
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY uh_update ON public.user_holdings
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY uh_delete ON public.user_holdings
    FOR DELETE USING (auth.uid() = user_id);

-- 3) user_alert_prefs (유저별 알림 설정)
CREATE TABLE IF NOT EXISTS public.user_alert_prefs (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    alert_type  TEXT NOT NULL DEFAULT 'all',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_uap_user ON public.user_alert_prefs(user_id);

ALTER TABLE public.user_alert_prefs ENABLE ROW LEVEL SECURITY;

CREATE POLICY uap_select ON public.user_alert_prefs
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY uap_insert ON public.user_alert_prefs
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY uap_update ON public.user_alert_prefs
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY uap_delete ON public.user_alert_prefs
    FOR DELETE USING (auth.uid() = user_id);

-- 4) watch_groups auth 전환 (기존 x-user-id → auth.uid() 마이그레이션)
-- 기존 TEXT user_id 컬럼에 auth_user_id UUID 컬럼 추가 (점진적 전환)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'watch_groups' AND column_name = 'auth_user_id'
    ) THEN
        ALTER TABLE watch_groups ADD COLUMN auth_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
        CREATE INDEX IF NOT EXISTS idx_wg_auth_user ON watch_groups(auth_user_id);
    END IF;
END $$;
